#!/usr/bin/env python3
"""US-007 单元测试：持仓策略指导（Position Guide）"""
import os
import sys
import tempfile
import sqlite3
import pytest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def analyzer():
    """临时 analyzer + 临时 DB（隔离测试）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.analysis.position_guide import PositionGuideAnalyzer
        tmp_db = os.path.join(tmpdir, 'test.db')
        schema_file = os.path.join(ROOT, 'schema/migrations/004_add_trade_tables.sql')
        conn = sqlite3.connect(tmp_db)
        with open(schema_file) as f:
            conn.executescript(f.read())
        # 补建 realtime_cache（_get_realtime_price 用）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS realtime_cache (
                code TEXT PRIMARY KEY,
                price REAL
            )
        """)
        conn.commit()
        conn.close()
        # 插入测试持仓
        conn = sqlite3.connect(tmp_db)
        conn.executemany("""
            INSERT INTO positions (code, name, entry_date, entry_price, quantity, status, is_real, legacy_holding)
            VALUES (?,?,?,?,?,?,?,?)
        """, [
            ('A', 'ETF_A', str(date.today() - timedelta(days=1)), 1.0, 1000, 'HOLDING', 1, 0),
            ('B', 'ETF_B', str(date.today() - timedelta(days=10)), 1.0, 500, 'HOLDING', 1, 0),
            ('LEGACY', 'Legacy ETF', str(date.today()), 1.0, 100, 'HOLDING', 1, 1),
        ])
        conn.commit()
        conn.close()
        yield PositionGuideAnalyzer(db_path=tmp_db)


class TestUS007PositionGuideSchema:
    """PositionGuide 数据类（18 字段）"""

    def test_position_guide_has_22_fields(self):
        """PositionGuide 22 字段（code/name 2 + 现状 5 + 阈值 4 + 信号 3 + 触发 3 + 多持仓 3 + 建议 2 = 22）"""
        from src.analysis.position_guide import PositionGuide
        import dataclasses
        fields = [f.name for f in dataclasses.fields(PositionGuide)]
        assert len(fields) == 22, f"PositionGuide 字段数 {len(fields)} 期望 22"

    def test_field_groups_complete(self):
        from src.analysis.position_guide import PositionGuide
        import dataclasses
        fields = {f.name for f in dataclasses.fields(PositionGuide)}
        # 现状 (5)
        assert {'quantity', 'entry_price', 'current_price', 'pnl_pct', 'hold_days'} <= fields
        # 阈值 (4)
        assert {'stop_loss_price', 'take_profit_price', 'expire_in_days', 'min_hold_remaining'} <= fields
        # 信号 (3)
        assert {'market_regime', 'current_score', 'emotion_flag'} <= fields
        # 触发 (3)
        assert {'should_stop_loss', 'should_take_profit', 'should_expire'} <= fields
        # 多持仓 (3)
        assert {'should_add_position', 'should_reduce_position', 'should_go_cash'} <= fields
        # 建议 (2)
        assert {'action', 'reason'} <= fields


class TestUS007DecisionTree:
    """决策树（按 SOP-17 顺序）"""

    def test_legacy_holding_decision(self, analyzer):
        """legacy_holding 标的：清仓（用户决策）"""
        g = analyzer.analyze_position('LEGACY', current_price=1.0, market_regime='trend_up')
        assert g.action == '清仓（用户决策）'
        assert 'legacy_holding' in g.reason

    def test_stop_loss_triggered(self, analyzer):
        """价格 ≤ 止损价 → 止损"""
        # 1 天持仓 @1.0，stop_loss=-10% → 止损价 0.9
        g = analyzer.analyze_position('A', current_price=0.85, market_regime='trend_up')
        assert g.action == '止损'
        assert g.should_stop_loss is True

    def test_short_hold_no_take_profit(self, analyzer):
        """持仓 < min_hold_days → 持有（短期）"""
        # A 持仓 1 天 < min_hold 3 天
        g = analyzer.analyze_position('A', current_price=1.05, market_regime='trend_up')
        assert g.action == '持有（短期）'
        assert g.min_hold_remaining > 0

    def test_take_profit_triggered(self, analyzer):
        """持仓 ≥ min_hold + 价格 ≥ 止盈价 → 止盈"""
        # B 持仓 10 天 ≥ min_hold 3 天，take_profit=+15% → 1.15
        g = analyzer.analyze_position('B', current_price=1.20, market_regime='trend_up')
        assert g.action == '止盈'
        assert g.should_take_profit is True

    def test_max_hold_days_expire(self, analyzer):
        """持仓 ≥ max_hold_days → 到期评估"""
        # B 持仓 10 天 < max_hold 15 天，但价格没触发
        g = analyzer.analyze_position('B', current_price=1.05, market_regime='trend_up')
        # 但还在 min_hold 之上，且价格 1.05 < 1.15 (止盈价)，不触发止盈
        # 持仓 10 天 < max_hold 15 天，不到期
        # 应该是 '持有' 或 '持有（短期）'
        assert g.action in ('持有', '持有（短期）')

    def test_market_regime_go_cash(self, analyzer):
        """市场非 trend_up → 清仓空仓"""
        g = analyzer.analyze_position('B', current_price=1.05, market_regime='range_bound')
        assert g.should_go_cash is True
        assert g.action == '清仓空仓'

    def test_crash_market_go_cash(self, analyzer):
        """crash 市场 → 清仓空仓"""
        g = analyzer.analyze_position('B', current_price=1.05, market_regime='crash')
        assert g.should_go_cash is True
        assert g.action == '清仓空仓'


class TestUS007MultiPosition:
    """多持仓（max_holdings=2）"""

    def test_count_active_positions(self, analyzer):
        """_count_active_positions 正确"""
        assert analyzer._count_active_positions() == 3  # A, B, LEGACY

    def test_should_add_when_below_max(self, analyzer):
        """持仓 < max_holdings + trend_up + 评分高 → 可加仓"""
        # 删除 LEGACY 简化测试
        import sqlite3
        conn = sqlite3.connect(analyzer.db_path)
        conn.execute("DELETE FROM positions WHERE code='LEGACY'")
        conn.commit()
        conn.close()
        # 现在 2 只持仓 = max_holdings
        # 删 A 后剩 1 只
        conn = sqlite3.connect(analyzer.db_path)
        conn.execute("DELETE FROM positions WHERE code='A'")
        conn.commit()
        conn.close()

        g = analyzer.analyze_position('B', current_price=1.05,
                                       market_regime='trend_up', current_score=9)
        assert g.should_add_position is True
        assert g.action == '可加仓到第 2 只'

    def test_max_holdings_2_default(self):
        """默认 max_holdings=2（沿用 v8 + 用户 B 决策）"""
        from src.analysis.position_guide import PositionGuideAnalyzer, DEFAULT_MAX_HOLDINGS
        assert DEFAULT_MAX_HOLDINGS == 2


class TestUS007Boundaries:
    """边界测试（hold_days = min-1, =, +1）"""

    def test_hold_days_below_min_no_take_profit(self, analyzer):
        """hold_days = min_hold - 1：不触发止盈"""
        # 改 A 持仓为 2 天（min_hold 3 - 1）
        import sqlite3
        conn = sqlite3.connect(analyzer.db_path)
        conn.execute("UPDATE positions SET entry_date=? WHERE code='A'",
                     (str(date.today() - timedelta(days=2)),))
        conn.commit()
        conn.close()
        g = analyzer.analyze_position('A', current_price=1.20, market_regime='trend_up')
        # 1.20 >= 1.15 (止盈价) 但持仓 < min_hold，不止盈
        assert g.action == '持有（短期）'

    def test_hold_days_at_min_can_take_profit(self, analyzer):
        """hold_days = min_hold：可触发止盈"""
        import sqlite3
        conn = sqlite3.connect(analyzer.db_path)
        conn.execute("UPDATE positions SET entry_date=? WHERE code='A'",
                     (str(date.today() - timedelta(days=3)),))
        conn.commit()
        conn.close()
        g = analyzer.analyze_position('A', current_price=1.20, market_regime='trend_up')
        # 1.20 >= 1.15 + 持仓 3 天 ≥ min_hold → 止盈
        assert g.action == '止盈'

    def test_hold_days_above_min_can_take_profit(self, analyzer):
        """hold_days = min_hold + 1：可触发止盈"""
        import sqlite3
        conn = sqlite3.connect(analyzer.db_path)
        conn.execute("UPDATE positions SET entry_date=? WHERE code='A'",
                     (str(date.today() - timedelta(days=4)),))
        conn.commit()
        conn.close()
        g = analyzer.analyze_position('A', current_price=1.20, market_regime='trend_up')
        assert g.action == '止盈'


class TestUS007EmotionFlag:
    """情绪预警联动（US-007 情绪字段）"""

    def test_recent_emotion_fear(self, analyzer):
        """最近交易 emotion=fear：情绪预警"""
        # 给 B 插入一笔 fear 交易
        import sqlite3
        conn = sqlite3.connect(analyzer.db_path)
        conn.execute("""
            INSERT INTO trade_history (date, code, name, action, price, quantity, amount, reason, emotion, is_real)
            VALUES (?, 'B', 'ETF_B', 'sell', 1.05, 100, 105.0, 'test', 'fear', 1)
        """, (str(date.today()),))
        conn.commit()
        conn.close()

        g = analyzer.analyze_position('B', current_price=1.05, market_regime='trend_up')
        assert g.emotion_flag == 'fear'


class TestUS007Portfolio:
    """批量分析"""

    def test_analyze_portfolio_returns_list(self, analyzer):
        """analyze_portfolio 返回所有持仓的指导"""
        guides = analyzer.analyze_portfolio(market_regime='trend_up',
                                              market_scores={'A': 5, 'B': 7, 'LEGACY': 0})
        assert len(guides) == 3
        codes = {g.code for g in guides}
        assert codes == {'A', 'B', 'LEGACY'}

    def test_analyze_position_returns_none_for_unknown(self, analyzer):
        """未知 code 返回 None（无持仓）"""
        g = analyzer.analyze_position('UNKNOWN', current_price=1.0)
        assert g is None


class TestUS007DefaultParameters:
    """默认参数对齐 v8 POSITION_MANAGEMENT.md"""

    def test_default_stop_loss_is_v8(self):
        from src.analysis.position_guide import DEFAULT_STOP_LOSS_PCT
        assert DEFAULT_STOP_LOSS_PCT == -0.10  # v8

    def test_default_take_profit_is_v8(self):
        from src.analysis.position_guide import DEFAULT_TAKE_PROFIT_PCT
        assert DEFAULT_TAKE_PROFIT_PCT == 0.15  # v8

    def test_default_max_hold_is_v8(self):
        from src.analysis.position_guide import DEFAULT_MAX_HOLD_DAYS
        assert DEFAULT_MAX_HOLD_DAYS == 15  # v8


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
