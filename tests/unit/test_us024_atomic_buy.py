#!/usr/bin/env python3
"""US-024 TDD: record_buy/sell 原子性测试

5 个测试覆盖失败路径（事务回滚）+ 成功路径 + 异常类型
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, '.')

from src.trade.tracker import TradeTracker
from src.trade.exceptions import BusinessConstraintError


class TestUS024AtomicBuy(unittest.TestCase):
    """US-024 事务原子性测试"""

    def setUp(self):
        """每个测试用独立临时 db"""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'test.db')

        # 初始化 schema（004 + positions.is_reference）
        conn = sqlite3.connect(self.db_path)
        schema_sql = open('schema/migrations/004_add_trade_tables.sql').read()
        conn.executescript(schema_sql)
        try:
            conn.execute("ALTER TABLE positions ADD COLUMN is_reference INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()
        conn.close()

        self.tracker = TradeTracker(db_path=self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _insert_holding(self, code='515050', name='通信ETF华夏',
                        entry_date='2026-06-02', entry_price=1.197,
                        quantity=2600, is_real=1):
        """手工插入 trade_history 模拟已持仓"""
        from src.trade.tracker import TradeRecord
        self.tracker.save_trade(TradeRecord(
            date=entry_date, code=code, name=name, action='buy',
            price=entry_price, quantity=quantity,
            amount=entry_price * quantity, reason='test', is_real=is_real
        ))

    # ── 失败路径测试 ─────────────────────────────────────────

    def test_record_buy_rejected_does_not_persist_trade_history(self):
        """❶ 失败路径: can_buy 拒绝时 trade_history 不入库"""
        # 持仓 2 只已达 max_holdings
        self._insert_holding('515050')
        self._insert_holding('512480', '半导体ETF国联安', '2026-06-04', 2.174, 3500)

        # 调 record_buy 第 3 只
        with self.assertRaises(BusinessConstraintError):
            self.tracker.record_buy(
                code='515070', name='人工智能ETF华夏',
                price=2.574, quantity=1500, reason='test', is_real=1
            )

        # 验证 trade_history 无 515070
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT code FROM trade_history WHERE code='515070'").fetchall()
        conn.close()
        self.assertEqual(len(rows), 0, "失败路径不应写入 trade_history")

    def test_record_buy_rejected_does_not_modify_positions(self):
        """❷ 失败路径: positions 表无变化"""
        self._insert_holding('515050')
        self._insert_holding('512480', '半导体ETF国联安', '2026-06-04', 2.174, 3500)

        before_conn = sqlite3.connect(self.db_path)
        before_count = before_conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        before_conn.close()

        with self.assertRaises(BusinessConstraintError):
            self.tracker.record_buy(
                code='515070', name='人工智能ETF华夏',
                price=2.574, quantity=1500, reason='test', is_real=1
            )

        after_conn = sqlite3.connect(self.db_path)
        after_count = after_conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        after_conn.close()
        self.assertEqual(before_count, after_count, "失败路径不应修改 positions")

    def test_record_buy_rejected_does_not_create_audit_log(self):
        """❸ 失败路径: audit_log 不增记录"""
        self._insert_holding('515050')
        self._insert_holding('512480', '半导体ETF国联安', '2026-06-04', 2.174, 3500)

        before_conn = sqlite3.connect(self.db_path)
        before_count = before_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        before_conn.close()

        with self.assertRaises(BusinessConstraintError):
            self.tracker.record_buy(
                code='515070', name='人工智能ETF华夏',
                price=2.574, quantity=1500, reason='test', is_real=1
            )

        after_conn = sqlite3.connect(self.db_path)
        after_count = after_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        after_conn.close()
        self.assertEqual(before_count, after_count, "失败路径不应写 audit_log")

    # ── 成功路径测试 ─────────────────────────────────────────

    def test_record_buy_succeeds_when_can_buy_passes(self):
        """❹ 成功路径: can_buy 通过时全链路正确"""
        # 持仓 1 只（未达 max）
        self._insert_holding('515050')

        trade = self.tracker.record_buy(
            code='512480', name='半导体ETF国联安',
            price=2.174, quantity=3500, reason='test', is_real=1
        )

        self.assertIsNotNone(trade, "成功路径应返回 TradeRecord")
        self.assertEqual(trade.code, '512480')
        self.assertEqual(trade.is_real, 1)

        # 验证 trade_history + positions + audit_log 都有
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM trade_history WHERE code='512480'").fetchone()[0], 1
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM positions WHERE code='512480'").fetchone()[0], 1
        )
        self.assertGreater(
            conn.execute("SELECT COUNT(*) FROM audit_log WHERE code='512480'").fetchone()[0], 0
        )
        conn.close()

    def test_record_buy_raises_business_constraint_error(self):
        """❺ 失败路径: 应抛 BusinessConstraintError 而非 return None"""
        self._insert_holding('515050')
        self._insert_holding('512480', '半导体ETF国联安', '2026-06-04', 2.174, 3500)

        # 验证异常类型（不是 return None）
        with self.assertRaises(BusinessConstraintError) as ctx:
            self.tracker.record_buy(
                code='515070', name='人工智能ETF华夏',
                price=2.574, quantity=1500, reason='test', is_real=1
            )
        # 异常信息应包含原因
        self.assertIn('515070', str(ctx.exception))
        self.assertIn('上限', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
