"""
布林带指标计算

布林带 = 中轨(MA) ± K倍标准差
标准参数：N=20, K=2

上轨 = 中轨 + 2倍标准差
中轨 = 20日均线
下轨 = 中轨 - 2倍标准差

用法：
- 价格触及上轨：可能过热，回调风险
- 价格触及下轨：可能超跌，反弹机会
- 布林带收口：波动率降低，可能突破
- 布林带开口：波动率扩大
"""
import pandas as pd
import numpy as np
from typing import Tuple, Literal
from src.indicators.base import IndicatorBase


def calculate_bollinger_bands(
    df: pd.DataFrame,
    window: int = 20,
    num_std: float = 2.0
) -> pd.DataFrame:
    """
    计算布林带指标
    
    Args:
        df: 包含close列的DataFrame
        window: 均线周期，默认20日
        num_std: 标准差倍数，默认2倍
        
    Returns:
        添加了以下列的DataFrame:
        - BB_middle: 中轨（均线）
        - BB_upper: 上轨
        - BB_lower: 下轨
        - BB_width: 布林带宽度（上轨-下轨）
        - BB_percent: 价格在布林带中的位置 (0-100%)
        
    信号判断:
        BB_percent > 100%: 价格突破上轨
        BB_percent < 0%: 价格突破下轨
        BB_percent = 50%: 价格在均线附近
        BB_width收窄: 蓄势待发，可能突破
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['close'])
    
    close = df['close']
    
    # 计算中轨（均线）
    middle = close.rolling(window=window, min_periods=1).mean()
    
    # 计算标准差
    std = close.rolling(window=window, min_periods=1).std()
    
    # 计算上下轨
    upper = middle + num_std * std
    lower = middle - num_std * std
    
    # 布林带宽度
    width = upper - lower
    
    # 价格在布林带中的位置
    # percent = (close - lower) / (upper - lower) * 100
    # 当上下轨重合时，避免除零
    band_range = upper - lower
    band_range = band_range.replace(0, np.nan)
    percent = (close - lower) / band_range * 100
    percent = percent.fillna(50)
    
    df['BB_middle'] = middle
    df['BB_upper'] = upper
    df['BB_lower'] = lower
    df['BB_width'] = width
    df['BB_percent'] = percent
    
    return df


def get_bollinger_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成布林带交易信号
    
    Args:
        df: 包含BB_upper, BB_lower, BB_percent列的DataFrame
        
    Returns:
        添加了BB_signal列的DataFrame:
        - 1: 买入信号（价格触及下轨或超跌）
        - -1: 卖出信号（价格触及上轨或过热）
        - 0: 持有
    """
    df = df.copy()
    
    if 'BB_percent' not in df.columns:
        raise ValueError("数据中缺少BB_percent列，请先调用calculate_bollinger_bands")
    
    signal = pd.Series(0, index=df.index)
    
    # 价格跌破下轨：超卖，买入信号
    signal[df['BB_percent'] < 0] = 1
    
    # 价格突破上轨：过热，卖出信号
    signal[df['BB_percent'] > 100] = -1
    
    # 价格触及下轨附近（< 10%）
    signal[df['BB_percent'] < 10] = 1
    
    # 价格触及上轨附近（> 90%）
    signal[df['BB_percent'] > 90] = -1
    
    df['BB_signal'] = signal
    
    return df


def calculate_bollinger_position(
    close: pd.Series,
    upper: pd.Series,
    lower: pd.Series
) -> pd.Series:
    """
    计算价格在布林带中的位置
    
    Args:
        close: 收盘价
        upper: 上轨
        lower: 下轨
        
    Returns:
        位置序列 (0-100%)
    """
    band_range = upper - lower
    band_range = band_range.replace(0, np.nan)
    position = (close - lower) / band_range * 100
    return position.fillna(50)


def get_bollinger_squeeze(df: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    """
    检测布林带收口（压缩形态）
    
    布林带收口后常伴随大幅波动
    
    Args:
        df: 包含BB_width列的DataFrame
        threshold: 收口阈值（相对于历史均值的比例）
        
    Returns:
        添加了BB_squeeze列的DataFrame:
        - 1: 收口状态
        - 0: 正常
    """
    df = df.copy()
    
    if 'BB_width' not in df.columns:
        df = calculate_bollinger_bands(df)
    
    # 计算布林带宽度的移动平均
    width_ma = df['BB_width'].rolling(window=20, min_periods=1).mean()
    
    # 当前宽度小于均值的threshold倍视为收口
    df['BB_squeeze'] = (df['BB_width'] < width_ma * threshold).astype(int)
    
    return df