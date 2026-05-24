#!/usr/bin/env python3
"""指标计算测试"""
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.indicator import Indicator


class TestIndicator:
    """技术指标测试"""
    
    @pytest.fixture
    def sample_df(self):
        """创建测试数据"""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=150).strftime('%Y-%m-%d')
        
        # 模拟上涨趋势
        base = 100
        prices = []
        for i in range(150):
            base += np.random.randn() * 2 + (i * 0.1)  # 上涨趋势
            prices.append(base)
        
        # 成交量
        volumes = np.random.randint(1000000, 5000000, 150)
        
        df = pd.DataFrame({
            'date': dates,
            'close': prices,
            'volume': volumes,
        })
        
        return df
    
    def test_ma_calculation(self, sample_df):
        """测试均线计算"""
        result = Indicator.calculate(sample_df)
        
        # MA5应该是最后5个收盘价的均值
        expected_ma5 = sample_df['close'].iloc[-5:].mean()
        assert abs(result['ma5'].iloc[-1] - expected_ma5) < 0.01
        
        # MA60应该有效（数据有120天）
        assert not pd.isna(result['ma60'].iloc[-1])
    
    def test_vol_ratio(self, sample_df):
        """测试量比计算"""
        result = Indicator.calculate(sample_df)
        
        # 量比应该是 volume / ma_vol_20
        last_vol = sample_df['volume'].iloc[-1]
        last_ma_vol = result['ma_vol_20'].iloc[-1]
        expected_ratio = last_vol / last_ma_vol
        
        assert abs(result['vol_ratio'].iloc[-1] - expected_ratio) < 0.01
    
    def test_rsi(self, sample_df):
        """测试RSI计算"""
        result = Indicator.calculate(sample_df)
        
        # RSI应该在0-100之间
        rsi = result['rsi_14'].dropna()
        assert (rsi >= 0).all() and (rsi <= 100).all()
        
        # 最后一天的RSI应该有效
        assert not pd.isna(result['rsi_14'].iloc[-1])
    
    def test_empty_df(self):
        """空数据测试"""
        df = pd.DataFrame({'date': [], 'close': [], 'volume': []})
        result = Indicator.calculate(df)
        assert len(result) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])