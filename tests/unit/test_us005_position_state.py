#!/usr/bin/env python3
"""US-005 单元测试：TradeTracker 状态机 + 事务保护 + 换仓规则"""
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
def tracker():
    """临时 TradeTracker"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.trade.tracker import TradeTracker
        tt = TradeTracker(data_dir=tmpdir)
        yield tt


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
    """can_buy 事务前置检查"""

    def test_can_buy_when_empty(self, tracker):
        ok, reason = tracker.can_buy('510300')
        assert ok is True
        assert reason == ''

    def test_cannot_buy_duplicate_when_holding(self, tracker):
        # 模拟有持仓
        from src.trade.tracker import Position
        positions = [Position(
            code='510300', name='test', entry_date='2026-06-01',
            entry_price=4.0, quantity=100, status='HOLDING'
        )]
        tracker.save_positions(positions)
        ok, reason = tracker.can_buy('510300')
        assert ok is False
        # max_holdings=1 已触发，duplicate 检查在它后面
        assert '上限' in reason or '已持仓' in reason

    def test_cannot_buy_exceed_max_holdings(self, tracker):
        from src.trade.tracker import Position
        positions = [
            Position(code='588000', name='a', entry_date='2026-06-01',
                     entry_price=1.0, quantity=100, status='HOLDING'),
        ]
        tracker.save_positions(positions)
        # 默认 max_holdings=1
        ok, reason = tracker.can_buy('512480')
        assert ok is False
        assert '上限' in reason


class TestCanSell:
    """can_sell 事务前置检查"""

    def test_cannot_sell_when_empty(self, tracker):
        ok, reason, pos = tracker.can_sell('510300')
        assert ok is False
        assert '未持有' in reason

    def test_can_sell_when_holding(self, tracker):
        from src.trade.tracker import Position
        positions = [Position(
            code='510300', name='test', entry_date='2026-06-01',
            entry_price=4.0, quantity=100, status='HOLDING'
        )]
        tracker.save_positions(positions)
        ok, reason, pos = tracker.can_sell('510300')
        assert ok is True
        assert pos.code == '510300'

    def test_cannot_sell_when_empty_status(self, tracker):
        from src.trade.tracker import Position
        positions = [Position(
            code='510300', name='test', entry_date='2026-06-01',
            entry_price=4.0, quantity=100, status='EMPTY'
        )]
        tracker.save_positions(positions)
        ok, reason, pos = tracker.can_sell('510300')
        assert ok is False
        assert '不能卖出' in reason

    def test_cannot_sell_quantity_exceed(self, tracker):
        from src.trade.tracker import Position
        positions = [Position(
            code='510300', name='test', entry_date='2026-06-01',
            entry_price=4.0, quantity=100, status='HOLDING'
        )]
        tracker.save_positions(positions)
        ok, reason, pos = tracker.can_sell('510300', quantity=200)
        assert ok is False
        assert '超过持仓' in reason


class TestCheckPortfolio:
    """批量检查测试"""

    def _add_position(self, tracker, code, pnl_pct, hold_days, score=8):
        from src.trade.tracker import Position
        positions = tracker.load_positions()
        positions.append(Position(
            code=code, name=code, entry_date='2026-05-01',
            entry_price=1.0, quantity=100, current_price=1.0 * (1 + pnl_pct / 100),
            pnl_pct=pnl_pct, hold_days=hold_days, status='HOLDING', score=score
        ))
        tracker.save_positions(positions)

    def test_stop_loss_triggered(self, tracker):
        self._add_position(tracker, '510300', pnl_pct=-7, hold_days=3)
        actions = tracker.check_portfolio(stop_loss=-0.06)
        assert len(actions) == 1
        assert actions[0]['action'] == 'sell'
        assert '止损' in actions[0]['reason']

    def test_take_profit_triggered(self, tracker):
        self._add_position(tracker, '510300', pnl_pct=11, hold_days=3)
        actions = tracker.check_portfolio(stop_profit=0.10)
        assert len(actions) == 1
        assert actions[0]['action'] == 'sell'
        assert '止盈' in actions[0]['reason']

    def test_max_hold_days_triggered(self, tracker):
        self._add_position(tracker, '510300', pnl_pct=2, hold_days=16)
        actions = tracker.check_portfolio(max_hold_days=15)
        assert len(actions) == 1
        assert actions[0]['action'] == 'sell'
        assert '持仓' in actions[0]['reason']

    def test_rebalance_triggered_when_candidate_better(self, tracker):
        self._add_position(tracker, '510300', pnl_pct=2, hold_days=5, score=7)
        candidates = [{'code': '512480', 'name': '512480', 'score': 10, 'price': 1.0}]
        actions = tracker.check_portfolio(candidates=candidates, rebalance_threshold=2)
        rebalances = [a for a in actions if a['action'] == 'rebalance']
        assert len(rebalances) == 1
        assert '512480' in rebalances[0]['reason']

    def test_rebalance_not_triggered_when_too_close(self, tracker):
        self._add_position(tracker, '510300', pnl_pct=2, hold_days=5, score=9)
        candidates = [{'code': '512480', 'name': '512480', 'score': 10, 'price': 1.0}]
        # 差 1 分，不到阈值
        actions = tracker.check_portfolio(candidates=candidates, rebalance_threshold=2)
        rebalances = [a for a in actions if a['action'] == 'rebalance']
        assert len(rebalances) == 0


class TestAuditLog:
    """审计日志测试"""

    def test_audit_writes_to_file(self, tracker):
        from src.trade.tracker import Position
        positions = [Position(
            code='510300', name='test', entry_date='2026-06-01',
            entry_price=4.0, quantity=100, status='HOLDING'
        )]
        tracker.save_positions(positions)
        tracker.transition_position('510300', 'CLOSING', 'test reason')
        # 读 audit log
        with open(tracker.audit_log_file, 'r') as f:
            content = f.read()
        assert 'CLOSING' in content
        assert 'test reason' in content

    def test_invalid_transition_does_not_audit(self, tracker):
        from src.trade.tracker import Position
        positions = [Position(
            code='510300', name='test', entry_date='2026-06-01',
            entry_price=4.0, quantity=100, status='EMPTY'
        )]
        tracker.save_positions(positions)
        # EMPTY → HOLDING 非法
        result = tracker.transition_position('510300', 'HOLDING', 'should fail')
        assert result is False
        with open(tracker.audit_log_file, 'r') as f:
            content = f.read()
        assert 'should fail' not in content


class TestRecordBuySellTransaction:
    """record_buy/record_sell 事务保护"""

    def test_record_buy_then_sell_cycle(self, tracker):
        """开仓→持仓→平仓→再开仓（同日）"""
        # 1. 买入
        trade1 = tracker.record_buy('510300', 'test', 4.0, 100, reason='test')
        assert trade1 is not None
        positions = tracker.load_positions()
        assert len(positions) == 1
        assert positions[0].status == 'HOLDING'
        # 2. 卖出
        trade2 = tracker.record_sell('510300', 4.2, actual_pnl=20)
        assert trade2 is not None
        positions = tracker.load_positions()
        assert len(positions) == 0
        # 3. 再次买入
        trade3 = tracker.record_buy('510300', 'test2', 4.3, 100, reason='test2')
        assert trade3 is not None
        positions = tracker.load_positions()
        assert len(positions) == 1

    def test_record_buy_rejects_duplicate(self, tracker):
        """重复买入被拒绝"""
        tracker.record_buy('510300', 'test', 4.0, 100, reason='first')
        # 重复买入
        result = tracker.record_buy('510300', 'test', 4.0, 100, reason='dup')
        assert result is None
        positions = tracker.load_positions()
        assert len(positions) == 1

    def test_record_sell_rejects_when_empty(self, tracker):
        """空仓时卖出被拒绝"""
        result = tracker.record_sell('510300', 4.0)
        assert result is None
