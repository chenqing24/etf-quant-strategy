"""数据契约测试（15个）"""
import pytest
import pandas as pd
from src.data.contracts import OHLCVSchema, IndicatorSchema, TradeRecordSchema


class TestOHLCVContract:
    """OHLCV 数据契约测试"""
    
    def test_valid_df_passes(self, valid_ohlcv_df):
        """契约：符合规范的 DataFrame 应通过验证"""
        errors = OHLCVSchema.validate(valid_ohlcv_df, source="test")
        assert len(errors) == 0, f"应通过验证，实际错误: {errors}"
    
    def test_missing_code_column(self):
        """契约：缺少 code 列应报错"""
        df = pd.DataFrame({
            'date': ['2024-01-02'],
            'open': [4.0], 'high': [4.1], 'low': [3.9], 
            'close': [4.0], 'volume': [1000000],
        })
        errors = OHLCVSchema.validate(df, source="test")
        assert any('code' in e for e in errors)
    
    def test_missing_date_column(self):
        """契约：缺少 date 列应报错"""
        df = pd.DataFrame({
            'code': ['510300'],
            'open': [4.0], 'high': [4.1], 'low': [3.9], 
            'close': [4.0], 'volume': [1000000],
        })
        errors = OHLCVSchema.validate(df, source="test")
        assert any('date' in e for e in errors)
    
    def test_date_format_valid(self, valid_ohlcv_df):
        """契约：YYYY-MM-DD 格式应通过"""
        errors = OHLCVSchema.validate(valid_ohlcv_df, source="test")
        assert not any('日期' in e for e in errors)
    
    def test_date_format_invalid(self, invalid_ohlcv_df):
        """契约：非法日期格式应报错"""
        errors = OHLCVSchema.validate(invalid_ohlcv_df, source="test")
        assert any('日期' in e for e in errors)
    
    def test_price_positive(self, valid_ohlcv_df):
        """契约：open/high/low/close 必须为正"""
        errors = OHLCVSchema.validate(valid_ohlcv_df, source="test")
        assert not any('非正值' in e for e in errors)
    
    def test_price_negative_fails(self):
        """契约：负价格应报错"""
        df = pd.DataFrame({
            'code': ['510300'], 'date': ['2024-01-02'],
            'open': [4.0], 'high': [4.1], 'low': [-0.1],
            'close': [4.0], 'volume': [1000000],
        })
        errors = OHLCVSchema.validate(df, source="test")
        assert any('非正值' in e for e in errors)
    
    def test_high_geq_low(self, valid_ohlcv_df):
        """契约：high >= low"""
        errors = OHLCVSchema.validate(valid_ohlcv_df, source="test")
        assert not any('high < low' in e for e in errors)
    
    def test_high_lt_low_fails(self, invalid_ohlcv_df):
        """契约：high < low 应报错"""
        errors = OHLCVSchema.validate(invalid_ohlcv_df, source="test")
        assert any('high < low' in e for e in errors)
    
    def test_close_in_range(self, valid_ohlcv_df):
        """契约：close ∈ [low, high]"""
        errors = OHLCVSchema.validate(valid_ohlcv_df, source="test")
        assert not any('close 超出' in e for e in errors)
    
    def test_volume_non_negative(self, valid_ohlcv_df):
        """契约：volume >= 0"""
        df = valid_ohlcv_df.copy()
        df['volume'] = [0, 100, 200, 300, 400]  # 允许零值
        errors = OHLCVSchema.validate(df, source="test")
        assert not errors


class TestIndicatorContract:
    """指标数据契约测试"""
    
    def test_output_has_required_columns(self, large_ohlcv_df):
        """契约：指标输出必须有必需列"""
        from src.analysis.indicator import Indicator
        
        result = Indicator.calculate(large_ohlcv_df)
        errors = IndicatorSchema.validate(result, source="test")
        
        assert not errors, f"缺少指标列: {errors}"
    
    def test_rsi_in_range(self, large_ohlcv_df):
        """契约：RSI ∈ [0, 100]"""
        from src.analysis.indicator import Indicator
        
        result = Indicator.calculate(large_ohlcv_df)
        errors = IndicatorSchema.validate(result, source="test")
        
        assert not any('RSI' in e and '范围' in e for e in errors)
    
    def test_indicator_preserves_original_columns(self, large_ohlcv_df):
        """契约：指标计算保留原始 OHLCV 列"""
        from src.analysis.indicator import Indicator
        
        result = Indicator.calculate(large_ohlcv_df)
        
        for col in OHLCVSchema.REQUIRED_COLUMNS:
            assert col in result.columns, f"缺少原始列: {col}"


class TestTradeRecordContract:
    """交易记录契约测试"""
    
    def test_valid_trade_record(self):
        """契约：合法交易记录应通过"""
        df = pd.DataFrame({
            'code': ['510300'],
            'name': ['沪深300'],
            'action': ['buy'],
            'price': [4.0],
            'quantity': [1000],
            'amount': [4000.0],
            'date': ['2024-01-02'],
            'reason': ['策略推荐'],
        })
        errors = TradeRecordSchema.validate(df, source="test")
        assert len(errors) == 0
    
    def test_invalid_action(self):
        """契约：action 必须是 buy/sell"""
        df = pd.DataFrame({
            'code': ['510300'], 'action': ['hold'],
            'price': [4.0], 'quantity': [1000],
            'date': ['2024-01-02'],
        })
        errors = TradeRecordSchema.validate(df, source="test")
        assert any('action' in e for e in errors)