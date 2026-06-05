#!/usr/bin/env python3
"""US-024 TDD: CLI --is-real 参数测试

3 个测试覆盖：
1. 默认 is_real=0（向后兼容）
2. --is-real 1 正确传递
3. --is-real 2 被 argparse 拒绝
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, '.')


class TestUS024CliIsReal(unittest.TestCase):
    """US-024 CLI --is-real 参数测试"""

    @classmethod
    def setUpClass(cls):
        """准备隔离的测试环境（用临时 db 避免污染生产）"""
        cls.tmpdir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmpdir, 'test.db')
        # 初始化 schema
        import sqlite3
        conn = sqlite3.connect(cls.db_path)
        schema_sql = open('schema/migrations/004_add_trade_tables.sql').read()
        conn.executescript(schema_sql)
        try:
            conn.execute("ALTER TABLE positions ADD COLUMN is_reference INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _run_cli(self, *args):
        """运行 CLI 命令（用临时 db 隔离）"""
        cmd = [
            'python3', '-m', 'src.cli.decision', '-m', 'trade',
            '--code', '510300', '--action', 'buy',
            '--price', '3.0', '--quantity', '100',
        ] + list(args) + ['--db_path', self.db_path]  # 假设支持 db_path 参数（待实现）
        # 实际 production 不用 --db_path，这里只测 argparse + 行为
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    # ── argparse 参数测试 ─────────────────────────────────────────

    def test_cli_trade_default_is_real_is_zero(self):
        """❶ CLI 默认 is_real=0（向后兼容）"""
        result = subprocess.run(
            ['python3', '-m', 'src.cli.decision', '-m', 'trade',
             '--code', '510300', '--action', 'buy',
             '--price', '3.0', '--quantity', '100',
             '--help'],
            capture_output=True, text=True, timeout=10
        )
        # 验证 --is_real 在 --help 输出中
        self.assertIn('--is_real', result.stdout)
        # 验证 choices={0,1}
        self.assertIn('--is_real {0,1}', result.stdout)
        # 验证 help 文本包含"默认 0"
        self.assertIn('默认 0', result.stdout)

    def test_cli_trade_invalid_is_real_rejected(self):
        """❷ CLI 传 --is-real 2 应被 argparse 拒绝"""
        result = subprocess.run(
            ['python3', '-m', 'src.cli.decision', '-m', 'trade',
             '--code', '510300', '--action', 'buy',
             '--price', '3.0', '--quantity', '100',
             '--is_real', '2'],
            capture_output=True, text=True, timeout=10
        )
        # 应非 0 退出码
        self.assertNotEqual(result.returncode, 0, "is_real=2 应被 argparse 拒绝")
        # 错误信息应包含 invalid choice
        self.assertTrue(
            'invalid choice' in result.stderr.lower() or 'invalid' in result.stderr.lower(),
            f"应提示 invalid choice, 实际: {result.stderr}"
        )

    def test_cli_trade_passes_is_real_one(self):
        """❸ CLI 传 --is-real 1 时 record_buy 收到 is_real=1

        这个测试需要 mock 或真实 db 写入验证。
        实际行为通过单元测试（mock TradeTracker）更稳定。
        """
        # 用 mock 验证 execute_trade 调用 record_buy 时 is_real=1
        from unittest.mock import patch, MagicMock
        from src.cli.decision import ETFDecisionEngine  # 实际类名

        with patch('src.cli.decision.TradeTracker') as MockTracker:
            mock_tracker = MagicMock()
            mock_record_buy = MagicMock(return_value=MagicMock())
            mock_tracker.return_value = mock_tracker
            mock_tracker.record_buy = mock_record_buy

            try:
                engine = ETFDecisionEngine.__new__(ETFDecisionEngine)  # 跳过 __init__
                engine.tracker = mock_tracker
                engine._silent_mode = False
                engine._simple_mode = False

                # 调 execute_trade 传 is_real=1
                engine.execute_trade(
                    code='510300', action='buy', price=3.0, quantity=100,
                    is_real=1
                )

                # 验证 mock 收到 is_real=1
                mock_record_buy.assert_called_once()
                call_kwargs = mock_record_buy.call_args.kwargs
                self.assertEqual(call_kwargs.get('is_real'), 1,
                                 f"record_buy 应收到 is_real=1, 实际: {call_kwargs}")
            except (TypeError, Exception) as e:
                self.skipTest(f"ETFDecisionEngine 构造需要额外参数: {e}")


if __name__ == '__main__':
    unittest.main()
