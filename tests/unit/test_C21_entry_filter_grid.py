"""C21 入场过滤网格 - 单元测试

按 L207（pytest 必须 mock 外部副作用）：
- 测试 entry_boll_ma 的 4 种 boll_mode × 3 种 ma_period 组合
- 测试触发频率的合理性
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.experiment.C21_entry_filter_grid import entry_boll_ma, ENTRY_FILTERS
from scripts.experiment.C9_market_state_v4 import add_indicators


def make_synthetic_df(n_days=400, start_price=10.0):
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=n_days, freq='D')
    prices = [start_price]
    for i in range(1, n_days):
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


class TestEntryBollMA(unittest.TestCase):
    """测试 BOLL+MA 入场过滤"""

    def setUp(self):
        self.df = make_synthetic_df()

    def test_middle_mode(self):
        """BOLL 中轨及以上：触发频率应该较高"""
        sig = entry_boll_ma(self.df, 'middle', 60)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))
        self.assertGreater(sig.sum(), 0)

    def test_middle_upper_mode(self):
        """中上轨：触发频率应该 < 中轨"""
        sig = entry_boll_ma(self.df, 'middle_upper', 60)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))
        # 中上轨比中轨更严格
        sig_middle = entry_boll_ma(self.df, 'middle', 60)
        self.assertLessEqual(sig.sum(), sig_middle.sum())

    def test_strict_middle_mode(self):
        """严格中轨：触发频率应该 < 中上轨"""
        sig = entry_boll_ma(self.df, 'strict_middle', 60)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))
        sig_middle_upper = entry_boll_ma(self.df, 'middle_upper', 60)
        self.assertLessEqual(sig.sum(), sig_middle_upper.sum())

    def test_lower_upper_mode(self):
        """下轨到上轨：触发频率应该 >= 中上轨（最宽松）"""
        sig = entry_boll_ma(self.df, 'lower_upper', 60)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))
        sig_middle_upper = entry_boll_ma(self.df, 'middle_upper', 60)
        self.assertGreaterEqual(sig.sum(), sig_middle_upper.sum())

    def test_ma60_strictest(self):
        """MA60 比 MA120 / MA250 更宽松（60 日均线更接近价格）"""
        sig_60 = entry_boll_ma(self.df, 'middle', 60)
        sig_120 = entry_boll_ma(self.df, 'middle', 120)
        sig_250 = entry_boll_ma(self.df, 'middle', 250)
        # MA 周期越长越严格
        self.assertGreaterEqual(sig_60.sum(), sig_120.sum())
        self.assertGreaterEqual(sig_120.sum(), sig_250.sum())

    def test_invalid_boll_mode_raises(self):
        """无效 boll_mode 应该抛 ValueError"""
        with self.assertRaises(ValueError):
            entry_boll_ma(self.df, 'INVALID', 60)

    def test_invalid_ma_period(self):
        """MA 周期不存在应该抛 KeyError（ma120/ma250 不存在）"""
        with self.assertRaises(KeyError):
            entry_boll_ma(self.df, 'middle', 999)


class TestEntryFiltersDefinition(unittest.TestCase):
    """测试入场过滤组合定义"""

    def test_12_filters(self):
        """应该有 12 个组合（4 boll × 3 ma）"""
        self.assertEqual(len(ENTRY_FILTERS), 12)

    def test_all_boll_modes(self):
        """4 种 BOLL 模式都应该有"""
        boll_modes = set(f[1] for f in ENTRY_FILTERS)
        self.assertEqual(boll_modes, {'middle', 'middle_upper', 'strict_middle', 'lower_upper'})

    def test_all_ma_periods(self):
        """3 种 MA 周期都应该有"""
        ma_periods = set(f[2] for f in ENTRY_FILTERS)
        self.assertEqual(ma_periods, {60, 120, 250})


if __name__ == '__main__':
    unittest.main()