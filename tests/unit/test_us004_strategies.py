#!/usr/bin/env python3
"""US-004 单元测试: 4 个基础策略（独立风控和仓位）"""
import os
import sys
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


def make_df(prices, volumes=None, n=60):
    """构造测试 DataFrame"""
    if volumes is None:
        volumes = np.random.randint(1000000, 5000000, n)
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=n).strftime('%Y-%m-%d'),
        'open': prices * 0.999,
        'high': prices * 1.002,
        'low': prices * 0.998,
        'close': prices,
        'volume': volumes,
    })


class TestUS004Strategies:
    """US-004: 4 个独立策略"""

    def test_trend_following_in_trend_up(self):
        from src.strategy.trend_following import TrendFollowingStrategy
        strat = TrendFollowingStrategy()
        # 强趋势数据
        np.random.seed(1)
        prices = np.linspace(1.0, 2.0, 60) + np.random.normal(0, 0.01, 60)
        df_dict = {'512480': make_df(prices)}
        signals = strat.select_etfs(df_dict, regime='trend_up')
        # 可能产生买入信号（趋势 + MA 上穿）
        assert isinstance(signals, list)
        for s in signals:
            assert s.action == 'buy'
            assert s.position_size == 0.30  # 独立仓位
            assert s.stop_loss < s.price  # 止损 < 入场
            assert s.take_profit > s.price  # 止盈 > 入场

    def test_trend_following_skips_range_bound(self):
        from src.strategy.trend_following import TrendFollowingStrategy
        strat = TrendFollowingStrategy()
        prices = np.random.uniform(1.0, 1.1, 60)
        df_dict = {'512480': make_df(prices)}
        signals = strat.select_etfs(df_dict, regime='range_bound')
        # 震荡市不应用趋势策略
        assert signals == []

    def test_mean_reversion_in_range_bound(self):
        from src.strategy.mean_reversion import MeanReversionStrategy
        strat = MeanReversionStrategy()
        # 震荡市 + 价格到 BB 下轨
        np.random.seed(2)
        prices = np.ones(60) * 1.0 + np.random.normal(0, 0.005, 60)
        # 让最后价格远低于均价（突破下轨）
        prices[-3:] = 0.95
        df_dict = {'512480': make_df(prices)}
        signals = strat.select_etfs(df_dict, regime='range_bound')
        assert isinstance(signals, list)
        for s in signals:
            assert s.position_size == 0.20
            assert s.max_hold_days <= 7

    def test_mean_reversion_skips_trend_up(self):
        from src.strategy.mean_reversion import MeanReversionStrategy
        strat = MeanReversionStrategy()
        prices = np.linspace(1.0, 1.5, 60)
        df_dict = {'512480': make_df(prices)}
        signals = strat.select_etfs(df_dict, regime='trend_up')
        assert signals == []

    def test_breakout_strategy(self):
        from src.strategy.breakout import BreakoutStrategy
        strat = BreakoutStrategy()
        np.random.seed(3)
        prices = np.ones(60) * 1.0 + np.random.normal(0, 0.01, 60)
        # 突破 + 放量
        prices[-1] = 1.5  # 突破 20日高点
        volumes = np.ones(60) * 1000000
        volumes[-1] = 3000000  # 3x 放量
        df_dict = {'512480': make_df(prices, volumes=volumes)}
        signals = strat.select_etfs(df_dict, regime='trend_up')
        for s in signals:
            assert s.position_size == 0.25
            assert 'Donchian' in s.reason

    def test_volume_divergence_strategy(self):
        from src.strategy.volume_divergence import VolumeDivergenceStrategy
        strat = VolumeDivergenceStrategy()
        np.random.seed(4)
        prices = np.ones(60) * 1.0 + np.random.normal(0, 0.01, 60)
        prices[-1] = 1.05  # 新高
        volumes = np.ones(60) * 1000000
        volumes[-1] = 500000  # 缩量 (0.5x)
        df_dict = {'512480': make_df(prices, volumes=volumes)}
        signals = strat.select_etfs(df_dict, regime='reversal_point')
        for s in signals:
            assert s.position_size == 0.15
            assert '量价背离' in s.reason

    def test_all_strategies_have_independent_risk_limits(self):
        """每策略独立仓位（关键原则 3）"""
        from src.strategy.trend_following import TrendFollowingStrategy
        from src.strategy.mean_reversion import MeanReversionStrategy
        from src.strategy.breakout import BreakoutStrategy
        from src.strategy.volume_divergence import VolumeDivergenceStrategy
        positions = [
            TrendFollowingStrategy().get_position_size(),
            MeanReversionStrategy().get_position_size(),
            BreakoutStrategy().get_position_size(),
            VolumeDivergenceStrategy().get_position_size(),
        ]
        # 每个策略仓位不同
        assert len(set(positions)) == 4
        # 仓位总和 ≤ 1.0（可组合）
        assert sum(positions) <= 1.0
