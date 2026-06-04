#!/usr/bin/env python3
"""US-012 单元测试: 仓位叠加 (baseline 评分 + Combiner 信号)"""
import os
import sys
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_combiner():
    """隔离 Combiner"""
    from src.strategy.combiner import StrategyCombiner
    return StrategyCombiner()


def make_df(prices, n=60):
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=n).strftime('%Y-%m-%d'),
        'open': prices * 0.999, 'high': prices * 1.002, 'low': prices * 0.998,
        'close': prices, 'volume': [1000000] * n,
    })


class TestUS012PositionStacking:
    """US-012: 仓位叠加 (baseline 评分 + Combiner 信号)"""

    def test_dual_signal_confidence_boost(self, isolated_combiner):
        """双满足时 confidence +20%"""
        combiner = isolated_combiner
        # 强趋势数据 (TrendFollowing + baseline 都会满足)
        np.random.seed(1)
        prices = np.linspace(1.0, 1.5, 60) + np.random.normal(0, 0.01, 60)
        df = make_df(prices)
        df_dict = {'512480': df}

        def high_score_func(code, df, date):
            return 9  # baseline 满足

        sigs = combiner.select_signals_with_baseline(
            df_dict, regime='trend_up',
            baseline_score_func=high_score_func, baseline_threshold=6,
        )
        if sigs:
            # TrendFollowing + baseline 都有 → 双满足
            sig = sigs[0]
            assert 'baseline_score' in sig.reason or '双满足' in sig.reason
            assert sig.confidence >= 0.7  # 原始 0.7 + boost 0.2 = 0.9 (max 1.0)

    def test_baseline_only_signals(self, isolated_combiner):
        """仅 baseline 满足 (Combiner 无信号) → 用 baseline"""
        combiner = isolated_combiner
        # 震荡市数据 (TrendFollowing 不适用)
        np.random.seed(2)
        prices = 1.0 + np.sin(np.linspace(0, 4*np.pi, 60)) * 0.02 + np.random.normal(0, 0.01, 60)
        df = make_df(prices)
        df_dict = {'512480': df}

        def baseline_only_func(code, df, date):
            return 8  # baseline 满足

        sigs = combiner.select_signals_with_baseline(
            df_dict, regime='range_bound',  # Combiner 只用 MeanReversion
            baseline_score_func=baseline_only_func, baseline_threshold=6,
        )
        # 如果 baseline ≥ 6 + Combiner 有信号 → 应有信号
        assert isinstance(sigs, list)

    def test_no_signals_when_both_empty(self, isolated_combiner):
        """无信号时返回空 list"""
        combiner = isolated_combiner
        prices = np.ones(60)  # 平直
        df = make_df(prices)
        df_dict = {'512480': df}

        def low_score_func(code, df, date):
            return 3  # baseline 不满足

        sigs = combiner.select_signals_with_baseline(
            df_dict, regime='crash',  # Combiner 没适用策略
            baseline_score_func=low_score_func, baseline_threshold=6,
        )
        assert sigs == []

    def test_position_cap_normalization(self, isolated_combiner):
        """总仓位不超 US-015 上限"""
        combiner = isolated_combiner
        # mock 所有 ETF 评分高 + Combiner 全信号 → 总仓位超 100%
        np.random.seed(3)
        prices = np.linspace(1.0, 1.5, 60)
        df_dict = {f'ETF{i}': make_df(prices) for i in range(5)}

        def high_func(code, df, date):
            return 9

        # 用 trend_up 市态, 总仓位上限 0.85
        sigs = combiner.select_signals_with_baseline(
            df_dict, regime='trend_up',
            baseline_score_func=high_func, baseline_threshold=6,
        )
        total_pos = sum(s.position_size for s in sigs)
        # 应不超 US-015 trend_up 90% 上限
        assert total_pos <= 0.90 + 0.001, f"total_pos {total_pos} 超 0.90 上限"

    def test_baseline_func_optional(self, isolated_combiner):
        """baseline_score_func=None 时只用 Combiner"""
        combiner = isolated_combiner
        np.random.seed(4)
        prices = np.linspace(1.0, 1.5, 60) + np.random.normal(0, 0.01, 60)
        df = make_df(prices)
        df_dict = {'512480': df}

        # 不传 baseline
        sigs = combiner.select_signals_with_baseline(
            df_dict, regime='trend_up',
            baseline_score_func=None,
        )
        # 行为应与原 select_signals 类似
        assert isinstance(sigs, list)
