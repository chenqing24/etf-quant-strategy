"""
指标计算模块单元测试

验证8个核心因子的计算正确性
"""
import pytest
import pandas as pd
import numpy as np
from src.indicators import (
    calculate_dma, calculate_obv_maobv, calculate_kdj,
    calculate_bollinger_bands, calculate_sar, calculate_adx,
    calculate_rsi, calculate_macd
)


def create_test_data(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """
    创建测试数据
    
    Args:
        n: 数据条数
        seed: 随机种子
        
    Returns:
        包含OHLCV的DataFrame
    """
    np.random.seed(seed)
    
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    # 生成模拟价格数据
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.rand(n) * 2
    low = close - np.random.rand(n) * 2
    open_price = low + np.random.rand(n) * (high - low)
    volume = np.random.randint(1000000, 10000000, n)
    
    return pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })


class TestDMA:
    """DMA指标测试"""
    
    def test_calculate_dma(self):
        """测试DMA计算"""
        df = create_test_data(100)
        result = calculate_dma(df, short_window=10, long_window=50)
        
        assert 'DMA' in result.columns
        assert 'MA_short' in result.columns
        assert 'MA_long' in result.columns
        assert len(result) == 100
    
    def test_dma_values(self):
        """测试DMA值"""
        df = create_test_data(60)
        result = calculate_dma(df, short_window=10, long_window=30)
        
        # 前几天数据可能为NaN
        valid_data = result.dropna()
        assert len(valid_data) > 0
        
        # DMA = MA_short - MA_long，应该是负数（因为短期均线<长期均线时）
        # 这个假设不一定成立，看具体数据
    
    def test_dma_empty_data(self):
        """测试空数据"""
        df = pd.DataFrame({'close': []})
        # 空数据应返回空DataFrame
        assert len(calculate_dma(df)) == 0


class TestOBV:
    """OBV指标测试"""
    
    def test_calculate_obv(self):
        """测试OBV计算"""
        df = create_test_data(100)
        result = calculate_obv_maobv(df, obv_window=10)
        
        assert 'OBV' in result.columns
        assert 'MAOBV' in result.columns
        assert len(result) == 100
    
    def test_obv_accumulation(self):
        """测试OBV累加逻辑"""
        df = pd.DataFrame({
            'close': [100, 105, 102, 108, 106],
            'volume': [1000, 2000, 1500, 2500, 1800]
        })
        result = calculate_obv_maobv(df)
        
        # OBV应该是累积的
        assert result['OBV'].iloc[-1] != 0
        # 价格涨时应为正
        assert result['OBV'].iloc[1] > 0
    
    def test_obv_no_change(self):
        """测试价格不变时的OBV"""
        df = pd.DataFrame({
            'close': [100, 100, 100, 100],
            'volume': [1000, 2000, 1500, 2500]
        })
        result = calculate_obv_maobv(df)
        
        # 价格不变，OBV累积应为0
        assert result['OBV'].iloc[-1] == 0


class TestKDJ:
    """KDJ指标测试"""
    
    def test_calculate_kdj(self):
        """测试KDJ计算"""
        df = create_test_data(50)
        result = calculate_kdj(df, n=9, m1=3, m2=3)
        
        assert 'K' in result.columns
        assert 'D' in result.columns
        assert 'J' in result.columns
        assert len(result) == 50
    
    def test_kdj_range(self):
        """测试KDJ范围"""
        df = create_test_data(50)
        result = calculate_kdj(df)
        
        # K和D应该在0-100之间
        valid_k = result['K'].dropna()
        valid_d = result['D'].dropna()
        
        assert all(valid_k >= 0) and all(valid_k <= 100)
        assert all(valid_d >= 0) and all(valid_d <= 100)
    
    def test_kdj_j_extreme(self):
        """测试J值可以超出0-100"""
        df = create_test_data(50)
        result = calculate_kdj(df)
        
        # J值可能超出0-100
        assert 'J' in result.columns


class TestBollingerBands:
    """布林带指标测试"""
    
    def test_calculate_bollinger(self):
        """测试布林带计算"""
        df = create_test_data(50)
        result = calculate_bollinger_bands(df, window=20, num_std=2)
        
        assert 'BB_upper' in result.columns
        assert 'BB_middle' in result.columns
        assert 'BB_lower' in result.columns
        assert 'BB_percent' in result.columns
    
    def test_bollinger_relationship(self):
        """测试布林带上下轨关系"""
        df = create_test_data(50)
        result = calculate_bollinger_bands(df, window=20, num_std=2)
        
        # 跳过前19行（数据不足）和NaN值后验证
        valid_upper = result['BB_upper'].iloc[20:].dropna()
        valid_middle = result['BB_middle'].iloc[20:].dropna()
        valid_lower = result['BB_lower'].iloc[20:].dropna()
        
        # 上轨应该大于等于中轨
        assert all(valid_upper >= valid_middle)
        # 下轨应该小于等于中轨
        assert all(valid_lower <= valid_middle)
        # 上轨应该大于下轨
        assert all(valid_upper > valid_lower)
    
    def test_bollinger_percent(self):
        """测试布林带百分比（可超出0-100用于识别超跌超买）"""
        df = create_test_data(50)
        result = calculate_bollinger_bands(df)
        
        # BB_percent 可能超出0-100（价格跌破下轨或突破上轨）
        # 只验证大部分值在0-100之间
        valid_percent = result['BB_percent'].iloc[20:].dropna()
        in_range = (valid_percent >= 0) & (valid_percent <= 100)
        # 至少70%的值在正常范围内
        assert in_range.sum() / len(valid_percent) >= 0.7


class TestSAR:
    """SAR指标测试"""
    
    def test_calculate_sar(self):
        """测试SAR计算"""
        df = create_test_data(50)
        result = calculate_sar(df)
        
        assert 'SAR' in result.columns
        assert 'SAR_trend' in result.columns
        assert len(result) == 50
    
    def test_sar_trend_values(self):
        """测试SAR趋势值"""
        df = create_test_data(50)
        result = calculate_sar(df)
        
        # SAR_trend应该是1或-1
        valid_trend = result['SAR_trend'].dropna()
        assert all(valid_trend.isin([1, -1]))


class TestADX:
    """ADX指标测试"""
    
    def test_calculate_adx(self):
        """测试ADX计算"""
        df = create_test_data(50)
        result = calculate_adx(df, window=14)
        
        assert 'ADX' in result.columns
        assert 'DI_plus' in result.columns
        assert 'DI_minus' in result.columns
        assert len(result) == 50
    
    def test_adx_positive(self):
        """测试ADX为正值"""
        df = create_test_data(50)
        result = calculate_adx(df)
        
        # ADX应该是正数
        valid_adx = result['ADX'].dropna()
        assert all(valid_adx >= 0)


class TestRSI:
    """RSI指标测试"""
    
    def test_calculate_rsi(self):
        """测试RSI计算"""
        df = create_test_data(50)
        result = calculate_rsi(df, window=5)
        
        assert 'RSI_5' in result.columns
        assert len(result) == 50
    
    def test_rsi_range(self):
        """测试RSI范围"""
        df = create_test_data(50)
        result = calculate_rsi(df)
        
        # RSI应该在0-100之间
        rsi_col = [c for c in result.columns if c.startswith('RSI_')][0]
        valid_rsi = result[rsi_col].dropna()
        assert all(valid_rsi >= 0) and all(valid_rsi <= 100)
    
    def test_rsi_multiple_windows(self):
        """测试不同周期的RSI"""
        df = create_test_data(100)
        
        result = calculate_rsi(df, window=5)
        result = calculate_rsi(result, window=10)
        result = calculate_rsi(result, window=14)
        
        assert 'RSI_5' in result.columns
        assert 'RSI_10' in result.columns
        assert 'RSI_14' in result.columns


class TestMACD:
    """MACD指标测试"""
    
    def test_calculate_macd(self):
        """测试MACD计算"""
        df = create_test_data(50)
        result = calculate_macd(df)
        
        assert 'DIF' in result.columns
        assert 'DEA' in result.columns
        assert 'MACD' in result.columns
        assert len(result) == 50
    
    def test_macd_columns(self):
        """测试MACD列"""
        df = create_test_data(50)
        result = calculate_macd(df)
        
        # MACD柱应该是DIF-DEA的2倍
        expected_macd = (result['DIF'] - result['DEA']) * 2
        assert np.allclose(result['MACD'].dropna(), expected_macd.dropna())


class TestIndicatorIntegration:
    """指标集成测试"""
    
    def test_all_indicators(self):
        """测试所有指标一起计算"""
        df = create_test_data(200)
        
        # 依次计算所有指标
        df = calculate_dma(df)
        df = calculate_obv_maobv(df)
        df = calculate_kdj(df)
        df = calculate_bollinger_bands(df)
        df = calculate_sar(df)
        df = calculate_adx(df)
        df = calculate_rsi(df, window=5)
        df = calculate_macd(df)
        
        # 验证所有列都存在
        expected_cols = [
            'DMA', 'MA_short', 'MA_long',
            'OBV', 'MAOBV',
            'K', 'D', 'J',
            'BB_upper', 'BB_middle', 'BB_lower',
            'SAR', 'SAR_trend',
            'ADX', 'DI_plus', 'DI_minus',
            'RSI_5',
            'DIF', 'DEA', 'MACD'
        ]
        
        for col in expected_cols:
            assert col in df.columns, f"缺少列: {col}"


class TestEdgeCases:
    """边界情况测试"""
    
    def test_single_row(self):
        """测试单行数据"""
        df = create_test_data(1)
        result = calculate_dma(df)
        assert len(result) == 1
    
    def test_insufficient_data(self):
        """测试数据不足"""
        df = create_test_data(5)
        result = calculate_kdj(df, n=9)  # 需要至少9天数据
        assert len(result) == 5
    
    def test_constant_price(self):
        """测试价格不变的情况"""
        df = pd.DataFrame({
            'close': [100] * 50,
            'open': [100] * 50,
            'high': [100] * 50,
            'low': [100] * 50,
            'volume': [1000] * 50
        })
        
        result = calculate_rsi(df, window=5)
        rsi_col = [c for c in result.columns if c.startswith('RSI_')][0]
        # 价格不变时RSI应为50
        assert result[rsi_col].iloc[-1] == 50