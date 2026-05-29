"""业务约束测试（10个）"""
import pytest
import pandas as pd
from src.data.contracts import OHLCVSchema


class TestBusinessConstraints:
    """业务约束测试"""
    
    def test_high_always_ge_low(self):
        """约束：任意 K 线 high >= low"""
        df = pd.DataFrame({
            'code': ['TEST'] * 100,
            'date': pd.date_range('2024-01-01', periods=100).strftime('%Y-%m-%d'),
            'open': [4.0] * 100,
            'high': [4.1] * 100,
            'low': [4.0] * 100,
            'close': [4.05] * 100,
            'volume': [1000000] * 100,
        })
        
        errors = OHLCVSchema.validate(df, source="test")
        assert not any('high < low' in e for e in errors)
    
    def test_high_eq_low_valid(self):
        """约束：high = low 是有效的（十字星）"""
        df = pd.DataFrame({
            'code': ['TEST'], 'date': ['2024-01-01'],
            'open': [4.0], 'high': [4.0], 'low': [4.0],
            'close': [4.0], 'volume': [1000000],
        })
        
        errors = OHLCVSchema.validate(df, source="test")
        assert not errors
    
    def test_close_within_high_low(self):
        """约束：close ∈ [low, high]"""
        df = pd.DataFrame({
            'code': ['TEST'], 'date': ['2024-01-01'],
            'open': [4.0], 'high': [4.1], 'low': [3.9],
            'close': [4.0], 'volume': [1000000],
        })
        
        errors = OHLCVSchema.validate(df, source="test")
        assert not any('close 超出' in e for e in errors)
    
    def test_close_eq_high_valid(self):
        """约束：close = high 是有效的"""
        df = pd.DataFrame({
            'code': ['TEST'], 'date': ['2024-01-01'],
            'open': [3.9], 'high': [4.0], 'low': [3.9],
            'close': [4.0], 'volume': [1000000],
        })
        
        errors = OHLCVSchema.validate(df, source="test")
        assert not errors
    
    def test_close_eq_low_valid(self):
        """约束：close = low 是有效的"""
        df = pd.DataFrame({
            'code': ['TEST'], 'date': ['2024-01-01'],
            'open': [4.1], 'high': [4.1], 'low': [4.0],
            'close': [4.0], 'volume': [1000000],
        })
        
        errors = OHLCVSchema.validate(df, source="test")
        assert not errors
    
    def test_volume_zero_valid(self):
        """约束：volume = 0 是有效的（停牌）"""
        df = pd.DataFrame({
            'code': ['TEST'], 'date': ['2024-01-01'],
            'open': [4.0], 'high': [4.1], 'low': [3.9],
            'close': [4.0], 'volume': [0],
        })
        
        errors = OHLCVSchema.validate(df, source="test")
        assert not errors
    
    def test_date_montonic_increasing(self, valid_ohlcv_df):
        """约束：date 列单调递增"""
        dates = valid_ohlcv_df['date'].tolist()
        assert dates == sorted(dates)
    
    def test_ma_vol_positive(self, large_ohlcv_df):
        """约束：ma_vol_20 > 0（跳过前19个预热期）"""
        from src.analysis.indicator import Indicator
        result = Indicator.calculate(large_ohlcv_df)
        # 跳过预热期（前19个为NaN）
        valid_data = result['ma_vol_20'].dropna()
        assert (valid_data > 0).all()
    
    def test_rsi_bounded(self, large_ohlcv_df):
        """约束：RSI 有界 [0, 100]（跳过预热期）"""
        from src.analysis.indicator import Indicator
        result = Indicator.calculate(large_ohlcv_df)
        # 跳过预热期（RSI需要足够数据）
        valid_rsi = result['rsi_14'].dropna()
        assert valid_rsi.between(0, 100).all()
    
    def test_vol_ratio_non_negative(self, large_ohlcv_df):
        """约束：vol_ratio >= 0（跳过预热期）"""
        from src.analysis.indicator import Indicator
        result = Indicator.calculate(large_ohlcv_df)
        # 跳过预热期
        valid_ratio = result['vol_ratio'].dropna()
        assert (valid_ratio >= 0).all()