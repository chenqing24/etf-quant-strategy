#!/usr/bin/env python3
"""US-005 单元测试：TradeTracker 状态机 + 事务保护 + 换仓规则

US-024 更新:
- 用 515050（core 池）替代 510300（reference 池被 _rebuild 过滤）
- record_buy/sell 失败抛 BusinessConstraintError（替代 return None）
- 验证用 get_holdings()（真相源）替代 load_positions()（脏数据）
"""
import os
import sys
import json
import tempfile
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



class TestStatusTransitions:
    """状态机转换测试"""

    def test_valid_transitions(self, tracker):
        from src.trade.tracker import VALID_TRANSITIONS
        # EMPTY → PENDING
        assert tracker._validate_transition('EMPTY', 'PENDING') is True
        # PENDING → HOLDING
        assert tracker._validate_transition('PENDING', 'HOLDING') is True
        # HOLDING → CLOSING
        assert tracker._validate_transition('HOLDING', 'CLOSING') is True
        # CLOSING → EMPTY
        assert tracker._validate_transition('CLOSING', 'EMPTY') is True
        # HOLDING → REBALANCING
        assert tracker._validate_transition('HOLDING', 'REBALANCING') is True

    def test_invalid_transitions(self, tracker):
        from src.trade.tracker import VALID_TRANSITIONS
        # EMPTY 不能直接 HOLDING
        assert tracker._validate_transition('EMPTY', 'HOLDING') is False
        # HOLDING 不能直接 EMPTY（必须经过 CLOSING）
        assert tracker._validate_transition('HOLDING', 'EMPTY') is False
        # CLOSING 不能回到 HOLDING
        assert tracker._validate_transition('CLOSING', 'HOLDING') is False


class TestCanBuy:
    """can_buy 事务前置检查（US-024: 用真相源 _rebuild_positions_from_trades）"""

    def test_can_buy_when_empty(self, tracker):
        ok, reason = tracker.can_buy('515050')  # US-024: 用 515050（core 池）
        assert ok is True
        assert reason == ''

    def test_cannot_buy_duplicate_when_holding(self, tracker):
        # 模拟有持仓 - US-024: 用 save_trade 写 trade_history（真相源）
        from src.trade.tracker import TradeRecord
        tracker.save_trade(TradeRecord(
            date='2026-06-01', code='515050', name='test', action='buy',
            price=4.0, quantity=100, amount=400, reason='test', is_real=1
        ))
        ok, reason = tracker.can_buy('515050')
        assert ok is False
        # max_holdings=1 已触发，duplicate 检查在它后面
        assert '上限' in reason or '已持仓' in reason

    def test_cannot_buy_exceed_max_holdings(self, tracker):
        # US-024: 用 save_trade 写 trade_history（真相源）
        from src.trade.tracker import TradeRecord
        tracker.save_trade(TradeRecord(
            date='2026-06-01', code='588000', name='a', action='buy',
            price=1.0, quantity=100, amount=100, reason='test', is_real=1
        ))
        # 显式传 max_holdings=1，触发上限
        ok, reason = tracker.can_buy('512480', max_holdings=1)
        assert ok is False
        assert '上限' in reason


class TestCanSell:
    """can_sell 事务前置检查（US-024: 用真相源）"""

    def test_cannot_sell_when_empty(self, tracker):
        ok, reason, pos = tracker.can_sell('515050')  # US-024: 用 515050
        assert ok is False
        assert '未持有' in reason

    def test_can_sell_when_holding(self, tracker):
        # US-024: 用 save_trade 写 trade_history（真相源）
        from src.trade.tracker import TradeRecord
        tracker.save_trade(TradeRecord(
            date='2026-06-01', code='515050', name='test', action='buy',
            price=4.0, quantity=100, amount=400, reason='test', is_real=1
        ))
        ok, reason, pos = tracker.can_sell('515050')
        assert ok is True
        assert pos.code == '515050'

    def test_cannot_sell_when_empty_status(self, tracker):
        # US-024: 不存在的标的 can_sell 返回 False
        ok, reason, pos = tracker.can_sell('515050')
        assert ok is False
        assert '未持有' in reason

    def test_cannot_sell_quantity_exceed(self, tracker):
        # US-024: 用 save_trade 写 trade_history（真相源）
        from src.trade.tracker import TradeRecord
        tracker.save_trade(TradeRecord(
            date='2026-06-01', code='515050', name='test', action='buy',
            price=4.0, quantity=100, amount=400, reason='test', is_real=1
        ))
        ok, reason, pos = tracker.can_sell('515050', quantity=200)
        assert ok is False
        assert '超过持仓' in reason


class TestCheckPortfolio:
    """批量检查测试"""

    def _add_position(self, tracker, code, pnl_pct, hold_days, score=8):
        ...


class TestRecordBuySellTransaction:
    """record_buy/record_sell 事务保护（US-024: 抛 BusinessConstraintError）"""

    def test_record_buy_then_sell_cycle(self, tracker):
        """开仓→持仓→平仓→再开仓（同日）

        US-024: 用 515050（core 池）替代 510300（reference 池被 _rebuild 过滤）
        """
        # 1. 买入
        trade1 = tracker.record_buy('515050', 'test', 4.0, 100, reason='test')
        assert trade1 is not None
        # US-024: 用真相源 get_holdings 验证
        holdings = tracker.get_holdings()
        assert len(holdings) == 1
        assert holdings[0].status == 'HOLDING'
        # 2. 卖出
        trade2 = tracker.record_sell('515050', 4.2, actual_pnl=20)
        assert trade2 is not None
        holdings = tracker.get_holdings()
        assert len(holdings) == 0
        # 3. 再次买入
        trade3 = tracker.record_buy('515050', 'test2', 4.3, 100, reason='test2')
        assert trade3 is not None
        holdings = tracker.get_holdings()
        assert len(holdings) == 1

    def test_record_buy_rejects_duplicate(self, tracker):
        """重复买入被拒绝 - US-024: 抛 BusinessConstraintError 替代 return None"""
        from src.trade.exceptions import BusinessConstraintError
        tracker.record_buy('515050', 'test', 4.0, 100, reason='first')
        with pytest.raises(BusinessConstraintError) as ctx:
            tracker.record_buy('515050', 'test', 4.0, 100, reason='dup')
        assert '515050' in str(ctx.value)
        holdings = tracker.get_holdings()
        assert len(holdings) == 1

    def test_record_sell_rejects_when_empty(self, tracker):
        """空仓时卖出被拒绝 - US-024: 抛 BusinessConstraintError 替代 return None"""
        from src.trade.exceptions import BusinessConstraintError
        with pytest.raises(BusinessConstraintError) as ctx:
            tracker.record_sell('515050', 4.0)
        assert '未持有' in str(ctx.value) or '515050' in str(ctx.value)
