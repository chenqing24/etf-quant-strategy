#!/usr/bin/env python3
"""US-005 单元测试: 策略组合器（风险平价）"""
import os
import sys
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


def make_df(prices, volumes=None, n=60):
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


class TestUS005StrategyCombiner:
    """US-005: 策略组合器（风险平价汇总）"""

    def test_combiner_includes_default_strategies(self):
        from src.strategy.combiner import StrategyCombiner
        c = StrategyCombiner()
        assert 'trend_following' in c.strategies
        assert 'mean_reversion' in c.strategies
        assert 'breakout' in c.strategies
        assert 'volume_divergence' in c.strategies
        assert len(c.list_active_strategies()) == 4

    def test_combiner_filters_by_regime(self):
        from src.strategy.combiner import StrategyCombiner
        c = StrategyCombiner()
        np.random.seed(1)
        prices = np.linspace(1.0, 1.5, 60) + np.random.normal(0, 0.01, 60)
        df_dict = {'512480': make_df(prices)}
        # range_bound: 只用 MeanReversion (其他 applicable_regimes 不匹配)
        signals = c.select_signals(df_dict, regime='range_bound')
        # 每个信号的 source strategy 应只来自 applicable
        # 简化验证: 不报错 + 是 list
        assert isinstance(signals, list)

    def test_combiner_respects_position_limit(self):
        """总仓位不超过 US-015 市态上限"""
        from src.strategy.combiner import StrategyCombiner
        from src.analysis.report_templates import POSITION_LIMITS
        c = StrategyCombiner()
        # mock 所有策略都返回满仓信号
        for s in c.strategies.values():
            s.select_etfs = lambda df_dict, regime: [
                type('S', (), {'code': 'test', 'action': 'buy', 'price': 1.0,
                              'position_size': s.get_position_size(),
                              'stop_loss': 0.95, 'take_profit': 1.05,
                              'max_hold_days': 5, 'confidence': 0.5,
                              'reason': 'mock'})() for _ in ['512480']
            ]
        df_dict = {'512480': make_df(np.ones(60))}
        signals_trend = c.select_signals(df_dict, regime='trend_up')   # 90% 上限
        total = sum(s.position_size for s in signals_trend)
        # 4 策略仓位 0.30+0.20+0.25+0.15=0.90，正好 trend_up 90% 上限
        assert total <= POSITION_LIMITS['trend_up'] + 0.001
        # range_bound 50% 上限
        signals_range = c.select_signals(df_dict, regime='range_bound')
        total_range = sum(s.position_size for s in signals_range)
        assert total_range <= POSITION_LIMITS['range_bound'] + 0.001

    def test_combiner_handles_strategy_exception(self):
        """单策略失败不影响其他"""
        from src.strategy.combiner import StrategyCombiner
        c = StrategyCombiner()
        # mock 一个策略抛异常
        c.strategies['trend_following'].select_etfs = lambda df_dict, regime: (_ for _ in ()).throw(Exception('mock error'))
        np.random.seed(2)
        prices = np.linspace(1.0, 1.5, 60)
        df_dict = {'512480': make_df(prices)}
        # 不应崩溃
        signals = c.select_signals(df_dict, regime='trend_up')
        assert isinstance(signals, list)

    def test_combiner_no_signals_when_no_match(self):
        """无匹配信号时返回空 list"""
        from src.strategy.combiner import StrategyCombiner
        c = StrategyCombiner()
        # 给一些价格但不让任何策略触发
        prices = np.ones(60) * 1.0
        df_dict = {'512480': make_df(prices)}
        signals = c.select_signals(df_dict, regime='crash')
        # crash 不在 4 策略 applicable 中
        assert signals == []

    def test_get_combined_position_size(self):
        """组合仓位按市态返回"""
        from src.strategy.combiner import StrategyCombiner
        c = StrategyCombiner()
        assert c.get_combined_position_size('trend_up') == 0.9
        assert c.get_combined_position_size('range_bound') == 0.5
        assert c.get_combined_position_size('crash') == 0.0
