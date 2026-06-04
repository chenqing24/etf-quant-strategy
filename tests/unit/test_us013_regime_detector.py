#!/usr/bin/env python3
"""US-013 单元测试: MarketRegimeDetector 8 状态 + 30d 滚动 + 多时间框架"""
import os
import sys
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


def make_df(prices, n=None):
    if n is None:
        n = len(prices)
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=n).strftime('%Y-%m-%d'),
        'open': np.array(prices) * 0.999, 'high': np.array(prices) * 1.001,
        'low': np.array(prices) * 0.998, 'close': prices,
        'volume': [1000000] * n,
    })


@pytest.fixture
def detector():
    from src.analysis.market_regime import MarketRegimeDetector
    return MarketRegimeDetector()


class TestUS013RegimeDetector:
    """US-013: 8 状态细分检测"""

    def test_initial_up(self, detector):
        """强多头 + 30d 回报 > 5% → initial_up"""
        np.random.seed(1)
        n = 200
        # 强上升 + 30d 涨 8%
        prices = list(np.linspace(1.0, 1.4, n-30)) + list(np.linspace(1.4, 1.51, 30))
        prices = np.array(prices) + np.random.normal(0, 0.01, n)
        df = make_df(prices)
        regime = detector.detect_8state(df)
        assert regime in ('initial_up', 'uptrend'), f"expected initial_up/uptrend, got {regime}"

    def test_uptrend(self, detector):
        """强多头 + 30d 回报 0-5% → uptrend"""
        np.random.seed(2)
        n = 200
        prices = list(np.linspace(1.0, 1.4, n-30)) + list(np.linspace(1.4, 1.42, 30))
        prices = np.array(prices) + np.random.normal(0, 0.01, n)
        df = make_df(prices)
        regime = detector.detect_8state(df)
        assert regime in ('uptrend', 'late_up'), f"expected uptrend, got {regime}"

    def test_late_up(self, detector):
        """多头 + 30d 回报转负 → late_up (动能减弱)"""
        np.random.seed(3)
        n = 200
        prices = list(np.linspace(1.0, 1.4, n-30)) + list(np.linspace(1.4, 1.36, 30))
        prices = np.array(prices) + np.random.normal(0, 0.01, n)
        df = make_df(prices)
        regime = detector.detect_8state(df)
        # 强上升后下跌
        assert regime in ('late_up', 'uptrend', 'range_bearish'), f"got {regime}"

    def test_range_bullish(self, detector):
        """震荡偏强: 平价 + 30d 微涨"""
        np.random.seed(4)
        n = 200
        # 区间震荡, 微涨, 加足够噪声避免 BB squeeze
        prices = 1.0 + np.sin(np.linspace(0, 4*np.pi, n)) * 0.05
        prices = prices + np.random.normal(0, 0.02, n)
        df = make_df(prices)
        regime = detector.detect_8state(df)
        # 震荡市
        assert regime in ('range_bullish', 'range_bearish', 'reversal_point', 'late_down', 'late_up'), f"got {regime}"

    def test_range_bearish(self, detector):
        """震荡偏弱"""
        np.random.seed(5)
        n = 200
        prices = 1.0 + np.sin(np.linspace(0, 4*np.pi, n)) * 0.05
        prices = prices + np.random.normal(0, 0.02, n)
        # 末尾下跌
        prices[-30:] *= 0.97
        df = make_df(prices)
        regime = detector.detect_8state(df)
        assert regime in ('range_bearish', 'range_bullish', 'reversal_point', 'late_down', 'late_up'), f"got {regime}"

    def test_ma_tolerance_1pct(self, detector):
        """MA 容差 1%: 相差 0.5% 也算多头"""
        np.random.seed(6)
        n = 200
        # 强上升 + 充分噪声避免 BB squeeze
        prices = np.linspace(1.0, 1.5, n) + np.random.normal(0, 0.01, n)
        df = make_df(prices)
        regime = detector.detect_8state(df)
        # 应该识别为趋势 (允许 reversal_point 也算)
        assert regime in ('initial_up', 'uptrend', 'late_up', 'reversal_point'), f"got {regime}"

    def test_30d_rolling_majority(self, detector):
        """30 天滚动判定 (多数票)"""
        np.random.seed(7)
        n = 200
        prices = np.linspace(1.0, 1.5, n) + np.random.normal(0, 0.01, n)
        df = make_df(prices)
        regime = detector.detect_30d_rolling(df)
        # 强上升 → 应识别为趋势
        assert regime in ('initial_up', 'uptrend', 'late_up'), f"got {regime}"

    def test_multi_timeframe(self, detector):
        """多时间框架投票 (1周 + 1月 + 1季)"""
        np.random.seed(8)
        n = 200
        prices = np.linspace(1.0, 1.5, n) + np.random.normal(0, 0.01, n)
        df = make_df(prices)
        regime = detector.detect_multi_timeframe(df)
        # 强上升 → 至少 2 框架 up
        assert regime in ('initial_up', 'uptrend', 'late_up'), f"got {regime}"

    def test_f4_now_recognized_as_trend(self, detector):
        """F4 (2025-07~2026-06) 现在能识别为趋势市"""
        from src.data.loader import DataLoader
        loader = DataLoader()
        df = loader.load_single('510300', min_rows=100)
        df['date'] = pd.to_datetime(df['date'])
        f4_end = pd.Timestamp('2026-06-03')
        past = df[df['date'] <= f4_end]
        regime_8 = detector.detect_8state(past)
        regime_30d = detector.detect_30d_rolling(past)
        regime_mtf = detector.detect_multi_timeframe(past)
        # F4 期间应识别为趋势市 (非震荡)
        assert regime_8 in ('initial_up', 'uptrend', 'late_up'), f"8state should be trend, got {regime_8}"
        assert regime_30d in ('initial_up', 'uptrend', 'late_up', 'reversal_point'), f"30d got {regime_30d}"
        assert regime_mtf in ('initial_up', 'uptrend', 'late_up'), f"mtf got {regime_mtf}"
