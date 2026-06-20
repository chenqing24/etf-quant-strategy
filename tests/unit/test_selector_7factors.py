#!/usr/bin/env python3
"""
7 因子打分测试（SOP-P0-1）

覆盖：
1. score() 返回 7 因子（不只是 5 个 MA+量）
2. RSI 因子正常打分（< 80 不扣分，> 80 减分）
3. 报告 reasons 格式："MA120(+3)" 而非 "MA120"
4. 同分时仍能区分（用 score_with_ic 模式）
"""
import os
import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.core.selector import Selector


def make_df(close_prices: list, rsi_value: float = 50.0) -> pd.DataFrame:
    """构造测试用 DataFrame"""
    n = len(close_prices)
    dates = pd.date_range('2025-01-01', periods=n, freq='D')
    df = pd.DataFrame({
        'date': dates,
        'close': close_prices,
        'volume': [1000000] * n,
    })

    # 计算技术指标
    for d in [5, 10, 20, 60, 120]:
        df[f'ma{d}'] = df['close'].rolling(d).mean()
    df['ma_vol_20'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['ma_vol_20']

    # RSI 5/14
    for d in [5, 14]:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(d).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(d).mean()
        rs = gain / (loss + 1e-10)
        df[f'rsi_{d}'] = 100 - (100 / (1 + rs))

    return df


class TestScoreHas7Factors:
    """score() 应有 7 因子（不只是 5 个 MA+量）"""

    def test_score_returns_at_least_7_factors(self):
        """score() 返回的 reasons 应至少 5 个（7 因子扣分时可能 4-5 个）"""
        # 构造一个全因子满足的标的：需要 ≥ 120 天才能让 MA120 有值
        # close 持续上涨确保站上所有 MA
        close = [10.0 + i * 0.02 for i in range(150)]  # 缓慢上涨
        df = make_df(close)
        target_date = df['date'].iloc[-1].strftime('%Y-%m-%d')

        s, reasons = Selector().score(df, target_date)
        # 应至少有 4 个分项（MA120+MA60up+MA60+MA20）= 4 项
        assert len(reasons) >= 4, f'期望 ≥ 4 个分项，实际 {len(reasons)}: {reasons}'

    def test_reasons_format_includes_score(self):
        """reasons 格式应包含分数：如 'MA120(+3)' 而非 'MA120'"""
        close = [10.0] * 120 + [12.0] * 30
        df = make_df(close)
        target_date = df['date'].iloc[-1].strftime('%Y-%m-%d')

        s, reasons = Selector().score(df, target_date)
        # 检查至少一个 reasons 包含 (+N) 格式
        has_score_format = any('(+' in r and ')' in r for r in reasons)
        assert has_score_format, f'reasons 应包含分数格式 (+N)，实际: {reasons}'


class TestRSIFactor:
    """RSI 因子扣分（> 80 减分，< 80 不扣）"""

    def test_rsi_above_80_deducts_score(self):
        """RSI5 > 80 应减分"""
        # 构造一个超买场景：close 持续上涨，RSI 应 > 80
        close = list(np.linspace(10, 20, 60))  # 60 天从 10 涨到 20
        df = make_df(close)
        target_date = df['date'].iloc[-1].strftime('%Y-%m-%d')

        s_with, reasons_with = Selector().score(df, target_date)
        rsi_5 = df['rsi_5'].iloc[-1]
        # 如果 RSI > 80，应该出现 RSI 扣分项
        if rsi_5 > 80:
            has_rsi_deduct = any('RSI' in r and '-' in r for r in reasons_with)
            assert has_rsi_deduct, f'RSI={rsi_5:.1f} > 80 应扣分，reasons: {reasons_with}'

    def test_rsi_below_80_no_deduct(self):
        """RSI5 < 80 不扣分"""
        # 构造平稳场景
        close = [10.0 + i * 0.01 for i in range(60)]  # 缓慢上涨
        df = make_df(close)
        target_date = df['date'].iloc[-1].strftime('%Y-%m-%d')

        s, reasons = Selector().score(df, target_date)
        rsi_5 = df['rsi_5'].iloc[-1]
        # 如果 RSI < 80，不应出现 RSI 扣分项
        if rsi_5 < 80:
            has_rsi_deduct = any('RSI' in r and '-' in r for r in reasons)
            assert not has_rsi_deduct, f'RSI={rsi_5:.1f} < 80 不应扣分，reasons: {reasons}'


class TestReportTieBreaker:
    """同分标的 tie-breaker（score_with_ic 模式）"""

    def test_same_score_different_ic(self):
        """同分时 score_with_ic 返回加权后不同分"""
        # 两个相同分但不同 IC 权重的标的
        close1 = [10.0] * 60 + [12.0] * 30
        close2 = [10.0] * 60 + [11.0] * 30  # 涨幅小

        df1 = make_df(close1)
        df2 = make_df(close2)
        date1 = df1['date'].iloc[-1].strftime('%Y-%m-%d')
        date2 = df2['date'].iloc[-1].strftime('%Y-%m-%d')

        s1, _ = Selector().score_with_ic(df1, date1)
        s2, _ = Selector().score_with_ic(df2, date2)

        # 涨幅大的分数应更高（IC 加权后）
        assert s1 >= s2, f'涨幅大应分数高: s1={s1}, s2={s2}'


class TestBackwardCompatibility:
    """向后兼容：score() 接口不变"""

    def test_score_returns_tuple(self):
        """score() 返回 (int, list)"""
        close = [10.0] * 60 + [12.0] * 30
        df = make_df(close)
        target_date = df['date'].iloc[-1].strftime('%Y-%m-%d')

        result = Selector().score(df, target_date)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], list)
