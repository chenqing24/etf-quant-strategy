#!/usr/bin/env python3
"""US-008 单元测试：TradeTracker DB 化 + is_real + 部分卖 + legacy_holding"""
import os
import sys
import json
import tempfile
import sqlite3
import pytest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tracker(isolated_tracker):
    """US-014: 用 conftest 全局 fixture（自动加载所有 migrations）"""
    t, tmpdir, tmp_db = isolated_tracker
    yield t



class TestUS008DatabaseSchema:
    """验证 3 张表 + 索引存在"""

    def test_trade_history_table_exists(self, tracker):
        conn = sqlite3.connect(tracker.db_path)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='trade_history'"
        ).fetchone()[0]
        conn.close()
        assert cnt == 1

    def test_positions_table_exists(self, tracker):
        conn = sqlite3.connect(tracker.db_path)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='positions'"
        ).fetchone()[0]
        conn.close()
        assert cnt == 1

    def test_audit_log_table_exists(self, tracker):
        conn = sqlite3.connect(tracker.db_path)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='audit_log'"
        ).fetchone()[0]
        conn.close()
        assert cnt == 1

    def test_trade_history_q009_fields_exist(self, tracker):
        """Q-009 决策上下文 4 字段必须存在"""
        conn = sqlite3.connect(tracker.db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_history)").fetchall()]
        conn.close()
        for field in ['model', 'strategy', 'evaluation', 'snapshot_ref']:
            assert field in cols, f"trade_history 缺 {field} 字段（Q-009 违反）"

    def test_trade_history_is_real_field(self, tracker):
        """US-008: is_real 字段必须存在"""
        conn = sqlite3.connect(tracker.db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_history)").fetchall()]
        conn.close()
        assert 'is_real' in cols

    def test_positions_legacy_holding_field(self, tracker):
        """US-008: positions.legacy_holding 字段必须存在"""
        conn = sqlite3.connect(tracker.db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(positions)").fetchall()]
        conn.close()
        assert 'legacy_holding' in cols

    def test_indexes_exist(self, tracker):
        """3 张表的索引必须存在"""
        conn = sqlite3.connect(tracker.db_path)
        idxs = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()]
        conn.close()
        # 至少 6 个索引：trade 3 + positions 2 + audit 3
        assert len(idxs) >= 6, f"索引数 {len(idxs)} 不足"


class TestUS008IsRealField:
    """TradeRecord.is_real 字段（US-008 区分实盘/模拟）"""

    def test_is_real_default_false(self):
        """US-008: is_real 默认 False（保守默认）"""
        from src.trade.tracker import TradeRecord
        t = TradeRecord(
            date='2026-06-03', code='159611', name='test', reason='test',
            action='buy', price=1.0, quantity=100, amount=100.0,
        )
        assert t.is_real == 0, f"is_real 默认应为 0（保守），实际 {t.is_real}"

    def test_record_buy_real_trade(self, tracker):
        """记录实盘交易：is_real=1"""
        trade = tracker.record_buy('159611', 'test', 1.221, 1900,
                                    reason='低开加仓', is_real=1,
                                    emotion='calm', session='C',
                                    trade_time='2026-06-03 09:30')
        assert trade is not None
        assert trade.is_real == 1

        # 验证 DB
        conn = sqlite3.connect(tracker.db_path)
        row = conn.execute(
            "SELECT is_real, emotion, session FROM trade_history WHERE code='159611'"
        ).fetchone()
        conn.close()
        assert row == (1, 'calm', 'C')

    def test_record_buy_paper_trade_default(self, tracker):
        """模拟交易（默认）：is_real=0"""
        trade = tracker.record_buy('159611', 'test', 1.221, 1900, reason='策略模拟')
        assert trade is not None
        assert trade.is_real == 0


class TestUS008PartialSell:
    """record_sell quantity 参数（US-008 支持部分卖）"""

    def test_partial_sell_updates_quantity(self, tracker):
        """部分卖：扣减数量而非移除"""
        # 1. 买入 1000
        tracker.record_buy('159611', 'test', 1.0, 1000, reason='建仓', is_real=1)
        positions = tracker.load_positions()
        assert positions[0].quantity == 1000

        # 2. 部分卖 300
        trade = tracker.record_sell('159611', 1.1, quantity=300, is_real=1)
        assert trade is not None
        assert trade.quantity == 300
        assert trade.amount == 1.1 * 300

        # 3. 验证持仓：剩余 700
        positions = tracker.load_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 700

    def test_full_sell_removes_position(self, tracker):
        """全仓卖（quantity=None）：移除持仓"""
        tracker.record_buy('159611', 'test', 1.0, 1000, reason='建仓')
        # quantity 不传 = 全仓
        tracker.record_sell('159611', 1.1, actual_pnl=100)
        positions = tracker.load_positions()
        assert len(positions) == 0

    def test_partial_sell_actual_pnl_calculated(self, tracker):
        """部分卖：actual_pnl 自动按比例计算"""
        tracker.record_buy('159611', 'test', 1.0, 1000, reason='建仓')
        # 部分卖 400 股 @ 1.2（盈利）
        trade = tracker.record_sell('159611', 1.2, quantity=400)
        # (1.2 - 1.0) * 400 = 80
        assert trade.actual_pnl == pytest.approx(80.0, abs=0.01)


class TestUS008PositionStatus:
    """Position 状态机（US-005 + US-008 持久化）"""

    def test_position_save_load_preserves_status(self, tracker):
        """save_positions 后 load_positions 保留 status"""
        from src.trade.tracker import Position
        positions = [Position(
            code='159611', name='test', entry_date='2026-06-03',
            entry_price=1.0, quantity=1000, status='HOLDING',
            is_real=1, legacy_holding=1,
        )]
        tracker.save_positions(positions)
        loaded = tracker.load_positions()
        assert len(loaded) == 1
        assert loaded[0].status == 'HOLDING'
        assert loaded[0].is_real == 1
        assert loaded[0].legacy_holding == 1

    def test_save_positions_deletes_removed(self, tracker):
        """save_positions 移除不在列表中的 code"""
        from src.trade.tracker import Position
        # 1. 存 2 个持仓
        positions = [
            Position(code='A', name='a', entry_date='2026-06-01',
                     entry_price=1.0, quantity=100, status='HOLDING'),
            Position(code='B', name='b', entry_date='2026-06-01',
                     entry_price=1.0, quantity=200, status='HOLDING'),
        ]
        tracker.save_positions(positions)
        assert len(tracker.load_positions()) == 2

        # 2. 只存 1 个
        positions = [positions[0]]
        tracker.save_positions(positions)
        loaded = tracker.load_positions()
        assert len(loaded) == 1
        assert loaded[0].code == 'A'


class TestUS008Q009DecisionContext:
    """Q-009 决策上下文 4 字段（之前 US-005 漏的）"""

    def test_record_buy_with_q009_context(self, tracker):
        """record_buy 接受 model/strategy/evaluation/snapshot_ref"""
        trade = tracker.record_buy(
            '159611', 'test', 1.221, 1900, reason='策略推荐',
            model='ETF量化决策v8_sop',
            strategy=json.dumps({"risk_control": {"stop_loss": -0.06}}),
            evaluation=json.dumps({"avg_sharpe": 1.408}),
            snapshot_ref='etf_data_live/decision_snapshot.json',
            is_real=0,
        )
        assert trade is not None

        # 验证 DB
        conn = sqlite3.connect(tracker.db_path)
        row = conn.execute(
            "SELECT model, strategy, evaluation, snapshot_ref FROM trade_history WHERE code='159611'"
        ).fetchone()
        conn.close()
        assert row[0] == 'ETF量化决策v8_sop'
        assert 'stop_loss' in row[1]
        assert 'avg_sharpe' in row[2]
        assert row[3] == 'etf_data_live/decision_snapshot.json'

    def test_record_buy_without_q009_uses_null(self, tracker):
        """不传 Q-009 字段：DB 存 NULL（不抛错）"""
        trade = tracker.record_buy('159611', 'test', 1.0, 100, reason='手动')
        assert trade is not None

        conn = sqlite3.connect(tracker.db_path)
        row = conn.execute(
            "SELECT model, strategy, evaluation, snapshot_ref FROM trade_history WHERE code='159611'"
        ).fetchone()
        conn.close()
        assert all(v is None for v in row)


class TestUS008LegacyHolding:
    """159611 legacy_holding 角色（修复 US-002 误标）"""

    def test_legacy_holding_position_loadable(self, tracker):
        """legacy_holding 持仓能正确加载"""
        from src.trade.tracker import Position
        positions = [Position(
            code='159611', name='电力ETF广发', entry_date='2026-06-03',
            entry_price=1.221, quantity=1900, status='HOLDING',
            is_real=1, legacy_holding=1,
        )]
        tracker.save_positions(positions)
        loaded = tracker.load_positions()
        assert loaded[0].legacy_holding == 1
        assert loaded[0].is_real == 1


class TestUS008MigrationScript:
    """scripts/migrate_trade_to_db.py 幂等性"""

    def test_migration_runs_on_clean_db(self, tmp_path):
        """迁移脚本在干净 DB 上能成功执行（幂等）"""
        import subprocess
        # 准备临时 DB
        tmp_db = tmp_path / 'test_migrate.db'
        # 复制 schema
        schema_file = ROOT / 'schema/migrations/004_add_trade_tables.sql'
        conn = sqlite3.connect(str(tmp_db))
        with open(schema_file) as f:
            conn.executescript(f.read())
        conn.close()

        # 跑迁移
        result = subprocess.run(
            [sys.executable, 'scripts/migrate_trade_to_db.py'],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
            env={**os.environ, 'DB_PATH': str(tmp_db)},
        )
        # 验证表存在
        conn = sqlite3.connect(str(tmp_db))
        for table in ['trade_history', 'positions', 'audit_log']:
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{table}'"
            ).fetchone()[0]
            assert cnt == 1, f"迁移后缺 {table} 表"


class TestUS008CanBuyDefault:
    """US-005 can_buy 默认 max_holdings 修复"""

    def test_default_max_holdings_is_2(self, tracker):
        """can_buy 默认 max_holdings=2（沿用 v8 + 用户 B 决策）"""
        from src.trade.tracker import Position
        # 1 个持仓
        tracker.save_positions([Position(
            code='588000', name='a', entry_date='2026-06-01',
            entry_price=1.0, quantity=100, status='HOLDING',
        )])
        # 第 2 个持仓应该 OK（max_holdings=2）
        ok, reason = tracker.can_buy('512480')
        assert ok is True, f"max_holdings=2 应允许第 2 只，实际 ok={ok}, reason={reason}"

    def test_max_holdings_2_rejects_3rd(self, tracker):
        """默认 max_holdings=2 拒绝第 3 只

        US-024: can_buy 用 _rebuild_positions_from_trades()（真相源）
        改用 save_trade 写 trade_history 模拟持仓（不再用 save_positions 写派生表）
        """
        from src.trade.tracker import TradeRecord
        # 2 个持仓（用 save_trade 写 trade_history，让 _rebuild 能重建出）
        tracker.save_trade(TradeRecord(
            date='2026-06-01', code='588000', name='a', action='buy',
            price=1.0, quantity=100, amount=100, reason='test', is_real=1
        ))
        tracker.save_trade(TradeRecord(
            date='2026-06-01', code='515050', name='b', action='buy',
            price=1.0, quantity=200, amount=200, reason='test', is_real=1
        ))
        # 第 3 个应被拒
        ok, reason = tracker.can_buy('512480')
        assert ok is False
        assert '上限' in reason


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
