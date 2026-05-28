"""
指标计算模块

提供各类技术指标计算功能

支持的指标：
- 趋势类：DMA, SAR, 均线交叉
- 动量类：RSI, KDJ, MACD, 动量
- 量能类：OBV, MAOBV, 放量
- 波动类：布林带, ATR, 波动率
- 趋势强度类：ADX, VHF
- 超买超卖类：CCI, WR

使用示例：
    from src.indicators import calculate_dma, calculate_kdj, calculate_rsi
    
    df = calculate_dma(df)
    df = calculate_kdj(df)
    df = calculate_rsi(df, window=5)
"""
from src.indicators.base import IndicatorBase, validate_price_data
from src.indicators.dma import calculate_dma, get_dma_signal, calculate_dma_crossover
from src.indicators.obv import calculate_obv, calculate_maobv, calculate_obv_maobv, get_obv_signal
from src.indicators.kdj import calculate_kdj, get_kdj_signal, get_kdj_extreme
from src.indicators.bollinger import calculate_bollinger_bands, get_bollinger_signal, get_bollinger_squeeze
from src.indicators.sar import calculate_sar, get_sar_signal, is_sar_below_price, is_sar_above_price
from src.indicators.adx import calculate_adx, get_adx_signal, is_trending, get_trend_direction
from src.indicators.rsi import calculate_rsi, get_rsi_signal, get_rsi_level
from src.indicators.macd import calculate_macd, get_macd_signal, detect_macd_divergence

__all__ = [
    # 基类和工具
    'IndicatorBase',
    'validate_price_data',
    
    # DMA
    'calculate_dma',
    'get_dma_signal',
    'calculate_dma_crossover',
    
    # OBV
    'calculate_obv',
    'calculate_maobv',
    'calculate_obv_maobv',
    'get_obv_signal',
    
    # KDJ
    'calculate_kdj',
    'get_kdj_signal',
    'get_kdj_extreme',
    
    # 布林带
    'calculate_bollinger_bands',
    'get_bollinger_signal',
    'get_bollinger_squeeze',
    
    # SAR
    'calculate_sar',
    'get_sar_signal',
    'is_sar_below_price',
    'is_sar_above_price',
    
    # ADX
    'calculate_adx',
    'get_adx_signal',
    'is_trending',
    'get_trend_direction',
    
    # RSI
    'calculate_rsi',
    'get_rsi_signal',
    'get_rsi_level',
    
    # MACD
    'calculate_macd',
    'get_macd_signal',
    'detect_macd_divergence',
]