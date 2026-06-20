#!/usr/bin/env python3
"""
MACD / BOLL 指标生成测试（SOP-P1-2）

覆盖：
1. Indicator.calculate() 应生成 macd / boll_upper / boll_lower 列
2. MACD 金叉/死叉可识别
3. BOLL 上下轨可计算
"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
import sys
sys.path.insert(0, str(ROOT))

from src.analysis.indicator import Indicator


def make_test_df(n: int = 100) -> pd.DataFrame:
    """构造测试 DataFrame"""
    return pd.DataFrame({
        'date': pd.date_range('2025-01-01', periods=n, freq='D'),
        'close': np.linspace(10, 20, n) + np.random.randn(n) * 0.1,
        'volume': [1000000] * n,
    })


class TestIndicatorMacd:
    """MACD 指标测试"""

    def test_macd_columns_generated(self):
        """Indicator 应生成 macd 列"""
        df = make_test_df(100)
        df = Indicator.calculate(df)

        # 期望有 macd / macd_signal / macd_hist 列
        expected_cols = ['macd', 'macd_signal', 'macd_hist']
        for col in expected_cols:
            assert col in df.columns, f'缺少 {col} 列，现有列: {df.columns.tolist()}'

    def test_macd_golden_cross_detected(self):
        """MACD 金叉（DIF 上穿 DEA）可识别"""
        df = make_test_df(100)
        df = Indicator.calculate(df)

        # macd > macd_signal 即金叉
        df['is_golden_cross'] = df['macd'] > df['macd_signal']
        # 至少有一些 True
        assert df['is_golden_cross'].sum() > 0


class TestIndicatorBoll:
    """BOLL 指标测试"""

    def test_boll_columns_generated(self):
        """Indicator 应生成 boll_upper / boll_middle / boll_lower 列"""
        df = make_test_df(100)
        df = Indicator.calculate(df)

        expected_cols = ['boll_upper', 'boll_middle', 'boll_lower']
        for col in expected_cols:
            assert col in df.columns, f'缺少 {col} 列，现有列: {df.columns.tolist()}'

    def test_boll_relationship(self):
        """boll_upper > boll_middle > boll_lower"""
        df = make_test_df(100)
        df = Indicator.calculate(df)

        # 取中间数据
        mid_df = df.iloc[30:].dropna()
        if len(mid_df) > 0:
            valid = mid_df[mid_df['boll_upper'] > mid_df['boll_middle']]
            valid = valid[valid['boll_middle'] > valid['boll_lower']]
            assert len(valid) > 0, 'boll_upper > boll_middle > boll_lower 应成立'


class TestBackwardCompat:
    """向后兼容：原有指标仍存在"""

    def test_existing_columns_preserved(self):
        """ma5/ma20/rsi_5/vol_ratio 等原有列仍存在"""
        df = make_test_df(100)
        df = Indicator.calculate(df)

        for col in ['ma5', 'ma20', 'ma60', 'ma120', 'rsi_5', 'rsi_14', 'vol_ratio']:
            assert col in df.columns, f'原有列 {col} 缺失'
