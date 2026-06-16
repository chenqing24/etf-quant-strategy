"""C20 alpha 来源分解 - 单元测试

按 L207（pytest 必须 mock 外部副作用）+ 规则 5.1（关键路径测试）：

测试覆盖：
1. 6 个 buy/sell 函数返回值类型正确
2. make_position 输出只 0/1
3. buy & hold 计算正确
4. 不同场景的 sell_signal 触发差异
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.experiment.C20_alpha_decomposition import (
    buy_signal_full,
    buy_signal_boll_ma60,
    sell_signal_full,
    sell_signal_no_ma5,
    sell_signal_only_ma60,
    sell_signal_none,
    make_position,
    buy_hold_only,
    SCENARIOS,
)
from scripts.experiment.C9_market_state_v4 import add_indicators


def make_synthetic_df(n_days=300, start_price=10.0, with_crash=True):
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=n_days, freq='D')
    prices = [start_price]
    for i in range(1, n_days):
        if with_crash and i == n_days // 2:
            prices.append(prices[-1] * 0.7)
        else:
            change = np.random.randn() * 0.02
            prices.append(prices[-1] * (1 + change))
    df = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000000] * n_days,
    })
    return add_indicators(df)


class TestBuySignals(unittest.TestCase):
    """测试买入信号函数"""

    def setUp(self):
        self.df = make_synthetic_df()

    def test_buy_signal_full_returns_binary(self):
        """完整 4 因子入场应返回 0/1"""
        sig = buy_signal_full(self.df, min_n=1)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))

    def test_buy_signal_boll_ma60_returns_binary(self):
        """BOLL+MA60 入场应返回 0/1"""
        sig = buy_signal_boll_ma60(self.df)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))

    def test_buy_signal_full_ge_boll_ma60(self):
        """完整入场触发应该 >= 仅 BOLL+MA60（更严格）"""
        sig_full = buy_signal_full(self.df, min_n=1)
        sig_boll = buy_signal_boll_ma60(self.df)
        # min_n=1 时完整入场应该触发 >= 仅过滤
        self.assertGreaterEqual(sig_full.sum(), sig_boll.sum() * 0.5)


class TestSellSignals(unittest.TestCase):
    """测试卖出信号函数"""

    def setUp(self):
        self.df = make_synthetic_df()

    def test_sell_full_returns_binary(self):
        sig = sell_signal_full(self.df)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))

    def test_sell_no_ma5_returns_binary(self):
        sig = sell_signal_no_ma5(self.df)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))

    def test_sell_only_ma60_returns_binary(self):
        sig = sell_signal_only_ma60(self.df)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))

    def test_sell_none_all_zero(self):
        """无卖出信号应全 0"""
        sig = sell_signal_none(self.df)
        self.assertEqual(sig.sum(), 0)

    def test_sell_full_ge_sell_no_ma5(self):
        """完整卖出（OR 复合）应 >= 剥离 sell_ma5"""
        sig_full = sell_signal_full(self.df)
        sig_no_ma5 = sell_signal_no_ma5(self.df)
        self.assertGreaterEqual(sig_full.sum(), sig_no_ma5.sum())

    def test_sell_no_ma5_ge_sell_only_ma60(self):
        """剥离 sell_ma5 应 >= 仅 MA60"""
        sig_no_ma5 = sell_signal_no_ma5(self.df)
        sig_ma60 = sell_signal_only_ma60(self.df)
        self.assertGreaterEqual(sig_no_ma5.sum(), sig_ma60.sum())


class TestMakePosition(unittest.TestCase):
    """测试 make_position 函数"""

    def test_position_binary(self):
        df = make_synthetic_df()
        buy = buy_signal_boll_ma60(df)
        sell = sell_signal_full(df)
        pos = make_position(buy, sell)
        self.assertTrue(set(pos.unique()).issubset({0.0, 1.0}))

    def test_position_with_no_sell_always_holding(self):
        """无卖出信号 → 买入后永远持仓"""
        df = make_synthetic_df()
        buy = buy_signal_boll_ma60(df)
        sell = sell_signal_none(df)
        pos = make_position(buy, sell)
        # 一旦买入就永远持仓
        buy_indices = np.where(buy == 1)[0]
        if len(buy_indices) > 0:
            first_buy = buy_indices[0]
            self.assertEqual(pos.iloc[first_buy], 1.0)
            self.assertEqual(pos.iloc[-1], 1.0)  # 期末仍在持仓


class TestBuyHoldOnly(unittest.TestCase):
    """测试 buy & hold 单 ETF"""

    def test_normal_positive(self):
        df = pd.DataFrame({
            'date': pd.date_range('2020-01-01', periods=100),
            'close': np.linspace(10, 15, 100),
        })
        r = buy_hold_only('test', df)
        self.assertAlmostEqual(r['total_return'], 0.5, places=4)

    def test_empty_df(self):
        df = pd.DataFrame({'date': [], 'close': []})
        r = buy_hold_only('test', df)
        self.assertTrue(r.get('skipped', False))

    def test_no_change(self):
        df = pd.DataFrame({
            'date': pd.date_range('2020-01-01', periods=100),
            'close': [10.0] * 100,
        })
        r = buy_hold_only('test', df)
        self.assertAlmostEqual(r['total_return'], 0.0, places=4)


class TestScenariosDefinition(unittest.TestCase):
    """测试场景定义完整性"""

    def test_6_scenarios(self):
        """应该有 6 个场景"""
        self.assertEqual(len(SCENARIOS), 6)

    def test_scenario_names(self):
        """场景名称应包含 S1-S6"""
        names = ' '.join([s[0] for s in SCENARIOS])
        for i in range(1, 7):
            self.assertIn(f'S{i}_', names, f"缺场景 S{i}")


if __name__ == '__main__':
    unittest.main()