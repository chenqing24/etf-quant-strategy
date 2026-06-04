#!/usr/bin/env python3
"""US-012 E2E 测试：eval + history 合并账户视图"""
import os
import sys
import json
import tempfile
import sqlite3
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_account(isolated_tracker):
    """US-014: 用 conftest 全局 fixture（自动加载所有 migrations）"""
    yield isolated_tracker



class TestAccountViewGeneration:
    """AccountView.generate() 输出 4 段"""

    def test_empty_account(self, isolated_account):
        """空仓账户只输出账户状态（无动作清单）"""
        from src.analysis.account_view import AccountView
        tracker, tmpdir, tmp_db = isolated_account
        # 用临时 db_path 创建 AccountView
        view = AccountView(db_path=tmp_db, market_regime='range_bound')
        output = view.generate()
        # 4 段都应输出（即使无持仓）
        assert '【一、当前持仓' in output
        assert '【二、今日推荐' in output
        assert '【三、动作清单' in output
        assert '【四、账户状态】' in output
        # 空仓时无动作
        assert '(无持仓，无动作)' in output or 'P9' not in output

    def test_with_legacy_holding(self, isolated_account):
        """legacy_holding 持仓输出 P1 动作 + ⚠️ 用户决策"""
        from src.analysis.account_view import AccountView
        tracker, tmpdir, tmp_db = isolated_account
        tracker.record_buy('159611', '电力ETF广发', 1.221, 1900, 'test', is_real=1)
        # 标 legacy_holding
        conn = sqlite3.connect(tmp_db)
        conn.execute("UPDATE positions SET legacy_holding=1 WHERE code='159611'")
        conn.commit()
        conn.close()

        view = AccountView(db_path=tmp_db, market_regime='range_bound')
        output = view.generate()
        # ① 持仓段
        assert '159611' in output
        assert '⚠️ legacy_holding' in output
        # ③ 动作清单
        assert 'P1' in output
        assert '清仓（用户决策）' in output
        assert '⚠️ 用户决策' in output
        # ④ 账户状态
        assert '1/2' in output or '1 / 2' in output

    def test_with_short_term_holding(self, isolated_account):
        """短期持有持仓输出 P3 动作"""
        from src.analysis.account_view import AccountView
        tracker, tmpdir, tmp_db = isolated_account
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 2600, 'test', is_real=1)

        view = AccountView(db_path=tmp_db, market_regime='range_bound')
        output = view.generate()
        # 持仓段
        assert '515050' in output
        # 动作清单
        assert 'P3' in output
        assert '持有（短期）' in output

    def test_action_list_priority_order(self, isolated_account):
        """动作清单按 9 步决策树 P1-P9 排序"""
        from src.analysis.account_view import AccountView
        tracker, tmpdir, tmp_db = isolated_account
        # legacy + 短期持有
        tracker.record_buy('159611', '电力ETF广发', 1.221, 1900, 'test', is_real=1)
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 2600, 'test', is_real=1)
        conn = sqlite3.connect(tmp_db)
        conn.execute("UPDATE positions SET legacy_holding=1 WHERE code='159611'")
        conn.commit()
        conn.close()

        view = AccountView(db_path=tmp_db, market_regime='range_bound')
        output = view.generate()
        # 提取动作清单段
        action_start = output.find('【三、动作清单')
        action_end = output.find('【四、')
        action_section = output[action_start:action_end]
        # P1 应该在 P3 之前
        p1_idx = action_section.find('P1')
        p3_idx = action_section.find('P3')
        assert p1_idx < p3_idx, f"P1 应在 P3 之前，实际 P1={p1_idx} P3={p3_idx}"


class TestAccountViewFineGrained:
    """细粒度字段：数量/价格/金额/止损止盈线"""

    def test_includes_quantity_price_amount(self, isolated_account):
        """动作清单含数量/价格/金额"""
        from src.analysis.account_view import AccountView
        tracker, tmpdir, tmp_db = isolated_account
        tracker.record_buy('159611', '电力ETF广发', 1.221, 1900, 'test', is_real=1)
        conn = sqlite3.connect(tmp_db)
        conn.execute("UPDATE positions SET legacy_holding=1 WHERE code='159611'")
        conn.commit()
        conn.close()

        view = AccountView(db_path=tmp_db, market_regime='range_bound')
        output = view.generate()
        # 数量
        assert '1900' in output
        # 价格
        assert '1.221' in output
        # 金额
        assert '2,320' in output  # 1900 × 1.221
        # 止损线
        assert '1.099' in output
        # 止盈线
        assert '1.404' in output


class TestAccountViewCLIMode:
    """CLI -m account 模式"""

    def test_cli_account_mode_runs(self):
        """CLI -m account 跑通"""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'src.cli.decision', '-m', 'account'],
            capture_output=True, text=True,
            cwd=str(ROOT), timeout=60
        )
        # 跑通即可（输出在 stdout）
        assert result.returncode == 0
        # 输出含 4 段
        assert '【一、当前持仓' in result.stdout
        assert '【二、今日推荐' in result.stdout
        assert '【三、动作清单' in result.stdout
        assert '【四、账户状态】' in result.stdout

    def test_cli_eval_still_works(self):
        """CLI -m eval 向后兼容"""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'src.cli.decision', '-m', 'eval', '--silent'],
            capture_output=True, text=True,
            cwd=str(ROOT), timeout=60
        )
        # 跑通即可
        assert result.returncode == 0

    def test_cli_history_still_works(self):
        """CLI -m history 向后兼容"""
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'src.cli.decision', '-m', 'history'],
            capture_output=True, text=True,
            cwd=str(ROOT), timeout=60
        )
        # 跑通即可
        assert result.returncode == 0
