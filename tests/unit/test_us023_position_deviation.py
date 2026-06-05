#!/usr/bin/env python3
"""US-023 单元测试: 持仓偏离监控 (方案 E 分批处理)

设计: 5 个 E_RULES 价位 + 5 类预警 (BREAK_ABOVE/BELOW/TAKE_PROFIT/STOP_LOSS/MAX_HOLD_DAYS)
TDD: 红 → 绿
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))


# ─────────────────────────────────────────────────────────────
# 测试: E_RULES 规则完整性
# ─────────────────────────────────────────────────────────────

class TestERules:
    """方案 E 自定义规则"""

    def test_three_codes_covered(self):
        """3 只持仓都应有自定义规则"""
        from monitor_position_deviation import E_RULES
        assert '515050' in E_RULES
        assert '512480' in E_RULES
        assert '515070' in E_RULES

    def test_515050_break_above(self):
        """515050 突破 1.30 规则"""
        from monitor_position_deviation import E_RULES
        assert E_RULES['515050']['break_above'] == 1.30
        assert E_RULES['515050']['break_below'] is None

    def test_512480_break_below(self):
        """512480 跌破 2.10 规则"""
        from monitor_position_deviation import E_RULES
        assert E_RULES['512480']['break_below'] == 2.10
        assert E_RULES['512480']['break_above'] is None

    def test_515070_break_below(self):
        """515070 跌破 2.50 规则"""
        from monitor_position_deviation import E_RULES
        assert E_RULES['515070']['break_below'] == 2.50
        assert E_RULES['515070']['break_above'] is None


# ─────────────────────────────────────────────────────────────
# 测试: 止盈止损价正确
# ─────────────────────────────────────────────────────────────

class TestTakeProfitStopLoss:
    """止盈止损价 (来自 constants.py 6%/10%)"""

    def test_515050_tp_sl(self):
        from monitor_position_deviation import E_RULES
        # 成本 1.197 * 1.10 = 1.3167
        assert abs(E_RULES['515050']['take_profit'] - 1.3167) < 0.01
        # 成本 1.197 * 0.94 = 1.1252
        assert abs(E_RULES['515050']['stop_loss'] - 1.1252) < 0.01

    def test_512480_tp_sl(self):
        from monitor_position_deviation import E_RULES
        # 成本 2.174 * 1.10 = 2.3914
        assert abs(E_RULES['512480']['take_profit'] - 2.3914) < 0.01
        # 成本 2.174 * 0.94 = 2.0436
        assert abs(E_RULES['512480']['stop_loss'] - 2.0436) < 0.01

    def test_515070_tp_sl(self):
        from monitor_position_deviation import E_RULES
        # 成本 2.574 * 1.10 = 2.8314
        assert abs(E_RULES['515070']['take_profit'] - 2.8314) < 0.01
        # 成本 2.574 * 0.94 = 2.4196
        assert abs(E_RULES['515070']['stop_loss'] - 2.4196) < 0.01


# ─────────────────────────────────────────────────────────────
# 测试: 预警触发逻辑 (mock 价格)
# ─────────────────────────────────────────────────────────────

class TestAlertLogic:
    """5 类预警的触发逻辑"""

    @patch('monitor_position_deviation.TradeTracker')
    def test_break_above_515050(self, mock_tracker):
        """515050 突破 1.30 → BREAK_ABOVE 预警"""
        from monitor_position_deviation import check_holdings

        # Mock 持仓
        mock_holding = MagicMock()
        mock_holding.code = '515050'
        mock_holding.name = '通信ETF华夏'
        mock_holding.current_price = 1.32  # > 1.30
        mock_holding.pnl_pct = 10.27
        mock_holding.hold_days = 3
        mock_tracker.return_value.get_holdings.return_value = [mock_holding]

        alerts = check_holdings()
        break_above = [a for a in alerts if a['type'] == 'BREAK_ABOVE']
        assert len(break_above) == 1
        assert '突破 1.3' in break_above[0]['msg']

    @patch('monitor_position_deviation.TradeTracker')
    def test_break_below_512480(self, mock_tracker):
        """512480 跌破 2.10 → BREAK_BELOW 预警"""
        from monitor_position_deviation import check_holdings

        mock_holding = MagicMock()
        mock_holding.code = '512480'
        mock_holding.name = '国联安半导体ETF'
        mock_holding.current_price = 2.08  # < 2.10
        mock_holding.pnl_pct = -4.32
        mock_holding.hold_days = 1
        mock_tracker.return_value.get_holdings.return_value = [mock_holding]

        alerts = check_holdings()
        break_below = [a for a in alerts if a['type'] == 'BREAK_BELOW']
        assert len(break_below) == 1
        assert '跌破 2.1' in break_below[0]['msg']

    @patch('monitor_position_deviation.TradeTracker')
    def test_break_below_515070(self, mock_tracker):
        """515070 跌破 2.50 → BREAK_BELOW 预警"""
        from monitor_position_deviation import check_holdings

        mock_holding = MagicMock()
        mock_holding.code = '515070'
        mock_holding.name = '人工智能ETF华夏'
        mock_holding.current_price = 2.48  # < 2.50
        mock_holding.pnl_pct = -3.65
        mock_holding.hold_days = 0
        mock_tracker.return_value.get_holdings.return_value = [mock_holding]

        alerts = check_holdings()
        break_below = [a for a in alerts if a['type'] == 'BREAK_BELOW']
        assert len(break_below) == 1

    @patch('monitor_position_deviation.TradeTracker')
    def test_take_profit_trigger(self, mock_tracker):
        """任一持仓触发止盈 → TAKE_PROFIT 预警"""
        from monitor_position_deviation import check_holdings

        mock_holding = MagicMock()
        mock_holding.code = '515050'
        mock_holding.name = '通信ETF华夏'
        mock_holding.current_price = 1.32  # > 1.317 止盈价
        mock_holding.pnl_pct = 10.27
        mock_holding.hold_days = 3
        mock_tracker.return_value.get_holdings.return_value = [mock_holding]

        alerts = check_holdings()
        tp = [a for a in alerts if a['type'] == 'TAKE_PROFIT']
        assert len(tp) == 1

    @patch('monitor_position_deviation.TradeTracker')
    def test_no_alert_at_current_price(self, mock_tracker):
        """当前价格 (09:58 状态) 应无预警"""
        from monitor_position_deviation import check_holdings

        # 模拟实际持仓
        holdings = [
            MagicMock(code='515050', name='通信ETF华夏', current_price=1.286, pnl_pct=7.44, hold_days=3),
            MagicMock(code='512480', name='国联安半导体ETF', current_price=2.152, pnl_pct=-1.01, hold_days=1),
            MagicMock(code='515070', name='人工智能ETF华夏', current_price=2.558, pnl_pct=-0.62, hold_days=0),
        ]
        mock_tracker.return_value.get_holdings.return_value = holdings

        alerts = check_holdings()
        assert len(alerts) == 0, f"当前应无预警, 但有 {len(alerts)} 个"
