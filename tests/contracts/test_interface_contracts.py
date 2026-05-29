"""接口契约测试（15个）"""
import pytest
import pandas as pd
from src.data.contracts import OHLCVSchema
from src.data.loader import DataLoader
from src.analysis.indicator import Indicator


class TestDataLoaderInterface:
    """DataLoader 接口契约测试"""
    
    def test_load_returns_dict(self, temp_db):
        """契约：load() 返回 Dict[str, DataFrame]"""
        loader = DataLoader(db_path=temp_db)
        result = loader.load(min_rows=1)
        
        assert isinstance(result, dict)
        assert len(result) > 0
    
    def test_load_keys_are_strings(self, temp_db):
        """契约：Dict key 应为 str（ETF代码）"""
        loader = DataLoader(db_path=temp_db)
        result = loader.load(min_rows=1)
        
        for key in result.keys():
            assert isinstance(key, str)
    
    def test_load_values_are_dataframes(self, temp_db):
        """契约：Dict value 应为 DataFrame"""
        loader = DataLoader(db_path=temp_db)
        result = loader.load(min_rows=1)
        
        for code, df in result.items():
            assert isinstance(df, pd.DataFrame)
    
    def test_load_dataframe_conforms_ohlcv(self, temp_db):
        """契约：返回的 DataFrame 必须符合 OHLCVSchema"""
        loader = DataLoader(db_path=temp_db)
        result = loader.load(min_rows=1)
        
        for code, df in result.items():
            errors = OHLCVSchema.validate(df, source=code)
            assert not errors, f"{code} 不符合 OHLCV 契约: {errors}"
    
    def test_load_date_sorted_asc(self, temp_db):
        """契约：date 列按 ASC 排序"""
        loader = DataLoader(db_path=temp_db)
        result = loader.load(min_rows=1)
        
        for code, df in result.items():
            dates = df['date'].tolist()
            assert dates == sorted(dates), f"{code} date 未按 ASC 排序"
    
    def test_load_single_returns_df_or_none(self, temp_db):
        """契约：load_single() 返回 DataFrame 或 None"""
        loader = DataLoader(db_path=temp_db)
        
        result = loader.load_single('510300')
        assert result is None or isinstance(result, pd.DataFrame)
    
    def test_load_nonexistent_returns_none(self, temp_db):
        """契约：不存在的 ETF 返回 None"""
        loader = DataLoader(db_path=temp_db)
        result = loader.load_single('nonexistent_code')
        assert result is None
    
    def test_get_date_range_returns_dict(self, temp_db):
        """契约：get_date_range() 返回 dict"""
        loader = DataLoader(db_path=temp_db)
        result = loader.get_date_range()
        
        assert isinstance(result, dict)
        assert 'min_date' in result
        assert 'max_date' in result


class TestIndicatorInterface:
    """Indicator 接口契约测试"""
    
    def test_calculate_preserves_input_columns(self, valid_ohlcv_df):
        """契约：calculate() 保留输入列"""
        result = Indicator.calculate(valid_ohlcv_df)
        
        for col in ['code', 'date', 'open', 'high', 'low', 'close', 'volume']:
            assert col in result.columns
    
    def test_calculate_returns_dataframe(self, valid_ohlcv_df):
        """契约：calculate() 返回 DataFrame"""
        result = Indicator.calculate(valid_ohlcv_df)
        assert isinstance(result, pd.DataFrame)
    
    def test_calculate_output_is_larger(self, valid_ohlcv_df):
        """契约：输出列数 >= 输入列数"""
        input_cols = len(valid_ohlcv_df.columns)
        result = Indicator.calculate(valid_ohlcv_df)
        assert len(result.columns) >= input_cols
    
    def test_calculate_all_returns_dict(self, temp_db):
        """契约：calculate_all() 返回 Dict[str, DataFrame]"""
        loader = DataLoader(db_path=temp_db)
        data = loader.load(min_rows=1)
        
        result = Indicator.calculate_all(data)
        assert isinstance(result, dict)
        for code, df in result.items():
            assert isinstance(df, pd.DataFrame)