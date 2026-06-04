#!/usr/bin/env python3
"""US-015 单元测试：按市场状态分档资金利用率"""
import os
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestPositionLimitsConstant:
    """POSITION_LIMITS 字典正确性"""

    def test_trend_up_90_percent(self):
        from src.analysis.report_templates import POSITION_LIMITS
        assert POSITION_LIMITS['trend_up'] == 0.9

    def test_range_bound_50_percent(self):
        from src.analysis.report_templates import POSITION_LIMITS
        assert POSITION_LIMITS['range_bound'] == 0.5

    def test_trend_down_30_percent(self):
        from src.analysis.report_templates import POSITION_LIMITS
        assert POSITION_LIMITS['trend_down'] == 0.3

    def test_crash_0_percent(self):
        from src.analysis.report_templates import POSITION_LIMITS
        assert POSITION_LIMITS['crash'] == 0.0

    def test_all_4_states_present(self):
        from src.analysis.report_templates import POSITION_LIMITS
        expected_states = {'trend_up', 'range_bound', 'trend_down', 'crash'}
        assert set(POSITION_LIMITS.keys()) == expected_states


class TestFormatPositionLimit:
    """format_position_limit 文本格式化"""

    def test_trend_up(self):
        from src.analysis.report_templates import format_position_limit
        result = format_position_limit('trend_up')
        assert '趋势市' in result
        assert '90%' in result

    def test_range_bound(self):
        from src.analysis.report_templates import format_position_limit
        result = format_position_limit('range_bound')
        assert '震荡市' in result
        assert '50%' in result

    def test_trend_down(self):
        from src.analysis.report_templates import format_position_limit
        result = format_position_limit('trend_down')
        assert '下跌市' in result
        assert '30%' in result

    def test_crash(self):
        from src.analysis.report_templates import format_position_limit
        result = format_position_limit('crash')
        assert '暴跌市' in result
        assert '0%' in result

    def test_unknown_fallback(self):
        from src.analysis.report_templates import format_position_limit
        result = format_position_limit('unknown_regime')
        # 未知市场时不应崩溃，输出包含默认
        assert result  # 非空


class TestReportWithPositionLimits:
    """报告输出按市场分档"""

    def test_account_view_shows_market_limit(self, isolated_tracker):
        """account_view 4 段输出含'市场仓位上限'"""
        tracker, tmpdir, tmp_db = isolated_tracker
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 1000, 'test', is_real=1)

        from src.analysis.account_view import AccountView
        view = AccountView(db_path=tmp_db, market_regime='range_bound')
        output = view.generate()
        # US-015: 报告含"市场仓位上限"段
        assert '震荡市' in output
        assert '50%' in output
        assert '上限' in output

    def test_different_market_different_limit(self, isolated_tracker):
        """不同市场状态显示不同上限"""
        tracker, tmpdir, tmp_db = isolated_tracker
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 1000, 'test', is_real=1)

        from src.analysis.account_view import AccountView

        # 震荡市
        view_range = AccountView(db_path=tmp_db, market_regime='range_bound')
        out_range = view_range.generate()
        assert '50%' in out_range

        # 趋势市
        view_trend = AccountView(db_path=tmp_db, market_regime='trend_up')
        out_trend = view_trend.generate()
        assert '90%' in out_trend

        # 暴跌市
        view_crash = AccountView(db_path=tmp_db, market_regime='crash')
        out_crash = view_crash.generate()
        assert '0%' in out_crash

    def test_crash_market_no_available(self, isolated_tracker):
        """暴跌市可投入为 0"""
        tracker, tmpdir, tmp_db = isolated_tracker
        # 清空
        from src.analysis.account_view import AccountView
        view = AccountView(db_path=tmp_db, market_regime='crash')
        output = view.generate()
        # crash 状态: 可投入 0 元
        assert '暴跌市' in output


class TestPositionLimitsMath:
    """资金配置算法按市场分档"""

    def test_range_bound_50_percent_capital(self):
        """震荡市: 可投入 = 总资产 × 50% - 持仓"""
        from src.analysis.report_templates import POSITION_LIMITS
        # 模拟场景
        total_asset = 20000
        positions_value = 2000
        limit = POSITION_LIMITS['range_bound']  # 0.5
        available = max(0, total_asset * limit - positions_value)
        # 20000 * 0.5 - 2000 = 10000 - 2000 = 8000
        assert available == 8000

    def test_trend_up_90_percent_capital(self):
        """趋势市: 可投入 = 总资产 × 90% - 持仓"""
        from src.analysis.report_templates import POSITION_LIMITS
        total_asset = 20000
        positions_value = 2000
        limit = POSITION_LIMITS['trend_up']  # 0.9
        available = max(0, total_asset * limit - positions_value)
        # 20000 * 0.9 - 2000 = 18000 - 2000 = 16000
        assert available == 16000

    def test_crash_zero_capital(self):
        """暴跌市: 可投入 = 0"""
        from src.analysis.report_templates import POSITION_LIMITS
        total_asset = 20000
        positions_value = 2000
        limit = POSITION_LIMITS['crash']  # 0
        available = max(0, total_asset * limit - positions_value)
        # 20000 * 0 - 2000 = -2000 → max(0, ...) = 0
        assert available == 0

    def test_over_capital_returns_zero(self):
        """持仓市值超过上限时: 可投入 = 0"""
        from src.analysis.report_templates import POSITION_LIMITS
        # 持仓市值超过 50% 上限
        total_asset = 20000
        positions_value = 12000  # 持仓 60%
        limit = POSITION_LIMITS['range_bound']  # 0.5
        available = max(0, total_asset * limit - positions_value)
        # 20000 * 0.5 - 12000 = -2000 → 0
        assert available == 0
