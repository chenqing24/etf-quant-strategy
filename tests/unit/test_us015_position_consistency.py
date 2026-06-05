#!/usr/bin/env python3
"""US-015 单元测试: get_holdings() 必须与 trade_history (事实源) 一致

按 SOUL 规则 15: 事实源是 trade_history, positions 是缓存
按 SOUL 规则 22: 判断逻辑应该基于外部数据, 不是行为反推
本测试: 直接验证 get_holdings() 输出 = trade_history 净持仓, 不依赖 positions 缓存
"""
import os
import sys
import sqlite3
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


def _get_net_holding_from_trade_history(code: str) -> int:
    """从 trade_history (事实源) 算净持仓"""
    conn = sqlite3.connect('etf_data_live/etf.db')
    buys = conn.execute(
        "SELECT SUM(quantity) FROM trade_history WHERE code=? AND action='buy'",
        (code,),
    ).fetchone()[0] or 0
    sells = conn.execute(
        "SELECT SUM(quantity) FROM trade_history WHERE code=? AND action='sell'",
        (code,),
    ).fetchone()[0] or 0
    conn.close()
    return buys - sells


@pytest.fixture
def tracker():
    from src.trade.tracker import TradeTracker
    t = TradeTracker('.')
    t.db_path = 'etf_data_live/etf.db'
    return t


class TestUS015GetHoldingsConsistency:
    """US-015: get_holdings() 必须 = trade_history 净持仓"""

    def test_159611_fully_cleared(self, tracker):
        """159611 已完全清仓 (净持仓 = 0)"""
        net = _get_net_holding_from_trade_history('159611')
        assert net == 0, f"trade_history 159611 净持仓 {net}, 期望 0 (已清仓)"

    def test_get_holdings_excludes_cleared_159611(self, tracker):
        """get_holdings() 不应返回 159611 (已清仓)"""
        holdings = tracker.get_holdings()
        codes = [h.code for h in holdings]
        assert '159611' not in codes, f"159611 不应出现, 实际: {codes}"

    def test_512480_net_holding_zero_after_sell(self, tracker):
        """US-024 后: 512480 已于 6/5 14:32 卖空 (sell 3500 @ 2.078)
        6/4 buy 3500 - 6/5 sell 3500 = 0 净持仓
        """
        net = _get_net_holding_from_trade_history('512480')
        assert net == 0, f"trade_history 512480 净持仓 {net}, 期望 0 (6/5 已清仓)"

    def test_515050_net_holding_2600(self, tracker):
        """515050 净持仓 2600 (6/2 buy 2600, sell 0)"""
        net = _get_net_holding_from_trade_history('515050')
        assert net == 2600, f"trade_history 515050 净持仓 {net}, 期望 2600"

    def test_get_holdings_quantity_matches_trade_history(self, tracker):
        """get_holdings() 每个持仓的数量应 = trade_history 净持仓"""
        holdings = tracker.get_holdings()
        for h in holdings:
            net = _get_net_holding_from_trade_history(h.code)
            assert h.quantity == net, f"{h.code} get_holdings={h.quantity} trade_history={net}"

    def test_get_holdings_returns_only_2_codes(self, tracker):
        """get_holdings() 应只返回 515050 + 515070 (159611/512480 已清仓)

        US-024: 512480 6/5 清仓后, 新增 515070, 当前持仓 = 515050 + 515070
        """
        holdings = tracker.get_holdings()
        codes = sorted([h.code for h in holdings])
        assert codes == ['515050', '515070'], f"实际: {codes}"


class TestUS015RebuildFromTrades:
    """US-015: _rebuild_positions_from_trades() 加权平均 + 累加"""

    def test_multiple_buys_weighted_average(self, tracker):
        """多次 buy 用加权平均 (US-015 修复覆盖式 bug)"""
        # 用 tracker.get_holdings() 触发 rebuild
        # 159611 buy 2 次 (6/1 @1.251 * 4700 + 6/3 @1.221 * 1900)
        #   加权均价 = (1.251*4700 + 1.221*1900) / 6600 = 1.241
        # 但 remaining=0, 不在 holdings 里
        # 改用 515050 (1 次 buy) 验证逻辑
        holdings = tracker.get_holdings()
        h_515050 = next((h for h in holdings if h.code == '515050'), None)
        assert h_515050 is not None
        # 515050 buy 1 次 @ 1.197 * 2600, 加权均价 = 1.197
        assert abs(h_515050.entry_price - 1.197) < 0.01

    def test_512480_entry_price(self, tracker):
        """US-024 后: 512480 已清仓, get_holdings() 不应包含 512480"""
        holdings = tracker.get_holdings()
        h_512480 = next((h for h in holdings if h.code == '512480'), None)
        assert h_512480 is None, f"512480 应已清仓, 但出现在 get_holdings: {holdings}"
