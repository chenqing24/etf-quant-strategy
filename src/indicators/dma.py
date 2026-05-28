"""
DMA指标计算

DMA = 短期均线 - 长期均线
用于判断趋势方向和趋势强度
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple
from src.indicators.base import IndicatorBase


def calculate_dma(
    df: pd.DataFrame,
    short_window: int = 10,
    long_window: int = 50,
    adjust: bool = True
) -> pd.DataFrame:
    """
    计算DMA指标
    
    DMA = 短期均线 - 长期均线
    
    Args:
        df: 包含close列的DataFrame
        short_window: 短期均线周期，默认10日
        long_window: 长期均线周期，默认50日
        adjust: 是否前复权调整
        
    Returns:
        添加了以下列的DataFrame:
        - DMA: 短期均线-长期均线差值
        - MA_short: 短期均线
        - MA_long: 长期均线
        
    Examples:
        >>> df = calculate_dma(df, short_window=10, long_window=50)
        >>> df['DMA']  # 差值
        >>> df['MA_short']  # 短期均线
        >>> df['MA_long']  # 长期均线
        
    信号判断:
        DMA > 0: 多头排列，短期均线在长期均线上方
        DMA < 0: 空头排列
        DMA上穿0: 买入信号
        DMA下穿0: 卖出信号
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['close'])
    
    close = df['close']
    
    # 计算短期和长期均线
    ma_short = close.rolling(window=short_window, min_periods=1).mean()
    ma_long = close.rolling(window=long_window, min_periods=1).mean()
    
    # DMA = 短期 - 长期
    dma = ma_short - ma_long
    
    # 添加到DataFrame
    df['DMA'] = dma
    df['MA_short'] = ma_short
    df['MA_long'] = ma_long
    
    return df


def get_dma_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成DMA交易信号
    
    Args:
        df: 包含DMA列的DataFrame
        
    Returns:
        添加了signal列的DataFrame:
        - 1: 买入信号
        - -1: 卖出信号
        - 0: 持有
    """
    df = df.copy()
    
    if 'DMA' not in df.columns:
        raise ValueError("数据中缺少DMA列，请先调用calculate_dma")
    
    dma = df['DMA']
    
    # 金叉：DMA从负转正
    # 死叉：DMA从正转负
    signal = pd.Series(0, index=dma.index)
    signal[dma > 0] = 1   # 多头
    signal[dma < 0] = -1  # 空头
    
    # 检测交叉点
    prev_dma = dma.shift(1)
    golden_cross = (prev_dma <= 0) & (dma > 0)  # 金叉
    dead_cross = (prev_dma >= 0) & (dma < 0)   # 死叉
    
    signal[golden_cross] = 1
    signal[dead_cross] = -1
    
    df['DMA_signal'] = signal
    
    return df


def calculate_dma_crossover(
    df: pd.DataFrame,
    fast_window: int = 5,
    slow_window: int = 20
) -> pd.DataFrame:
    """
    计算DMA交叉信号（快慢线交叉）
    
    Args:
        df: 包含close列的DataFrame
        fast_window: 快线周期，默认5日
        slow_window: 慢线周期，默认20日
        
    Returns:
        添加了以下列的DataFrame:
        - DMA_fast: 快线
        - DMA_slow: 慢线
        - DMA_cross_signal: 交叉信号 (1买入, -1卖出, 0持有)
    """
    df = df.copy()
    
    # 计算快慢线
    ma_fast = df['close'].rolling(window=fast_window, min_periods=1).mean()
    ma_slow = df['close'].rolling(window=slow_window, min_periods=1).mean()
    
    df['DMA_fast'] = ma_fast
    df['DMA_slow'] = ma_slow
    
    # 计算差值
    df['DMA_diff'] = ma_fast - ma_slow
    
    # 生成交叉信号
    prev_diff = df['DMA_diff'].shift(1)
    
    df['DMA_cross_signal'] = 0
    df.loc[(prev_diff <= 0) & (df['DMA_diff'] > 0), 'DMA_cross_signal'] = 1   # 金叉买入
    df.loc[(prev_diff >= 0) & (df['DMA_diff'] < 0), 'DMA_cross_signal'] = -1  # 死叉卖出
    
    return df