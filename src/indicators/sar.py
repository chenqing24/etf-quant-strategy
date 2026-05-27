"""
SAR指标计算

SAR = Stop and Reverse，抛物线止损指标
用于设置止损点或判断趋势反转

用法：
- SAR在价格上方：空头趋势，止损点
- SAR在价格下方：多头趋势，止损点
- 价格穿越SAR：趋势反转
"""
import pandas as pd
import numpy as np
from typing import Tuple
from src.indicators.base import IndicatorBase


def calculate_sar(
    df: pd.DataFrame,
    af_start: float = 0.02,
    af_increment: float = 0.02,
    af_max: float = 0.2
) -> pd.DataFrame:
    """
    计算SAR指标（抛物线止损）
    
    Args:
        df: 包含high, low, close列的DataFrame
        af_start: 初始加速因子，默认0.02
        af_increment: 加速因子增量，默认0.02
        af_max: 最大加速因子，默认0.2
        
    Returns:
        添加了以下列的DataFrame:
        - SAR: SAR值
        - SAR_trend: 趋势方向 (1多头, -1空头)
        - SAR_signal: 交叉信号 (1买入, -1卖出, 0持有)
        
    信号判断:
        SAR从上方穿越到下方：买入信号
        SAR从下方穿越到上方：卖出信号
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['high', 'low', 'close'])
    
    high = df['high']
    low = df['low']
    close = df['close']
    n = len(df)
    
    # 初始化
    sar = pd.Series(np.nan, index=df.index)
    trend = pd.Series(1, index=df.index)  # 1=多头, -1=空头
    ep = pd.Series(np.nan, index=df.index)  # 极点价
    af = pd.Series(af_start, index=df.index)  # 加速因子
    
    # 第一天初始化
    if n > 0:
        sar.iloc[0] = low.iloc[0]
        ep.iloc[0] = high.iloc[0]
        trend.iloc[0] = 1
    
    # 迭代计算SAR
    for i in range(1, n):
        # 获取前一天的SAR和趋势
        prev_sar = sar.iloc[i-1]
        prev_trend = trend.iloc[i-1]
        prev_ep = ep.iloc[i-1]
        prev_af = af.iloc[i-1]
        
        # 计算当前SAR
        current_sar = prev_sar + prev_af * (prev_ep - prev_sar)
        
        # 检查是否需要止损（价格反向穿越）
        if prev_trend == 1:  # 前一天是多头
            if low.iloc[i] < current_sar:
                # 价格跌破SAR，趋势反转
                current_sar = prev_ep
                current_trend = -1
                current_ep = low.iloc[i]
                current_af = af_start
            else:
                current_trend = 1
                current_ep = max(prev_ep, high.iloc[i])
                current_af = min(prev_af + af_increment, af_max)
        else:  # 前一天是空头
            if high.iloc[i] > current_sar:
                # 价格突破SAR，趋势反转
                current_sar = prev_ep
                current_trend = 1
                current_ep = high.iloc[i]
                current_af = af_start
            else:
                current_trend = -1
                current_ep = min(prev_ep, low.iloc[i])
                current_af = min(prev_af + af_increment, af_max)
        
        sar.iloc[i] = current_sar
        trend.iloc[i] = current_trend
        ep.iloc[i] = current_ep
        af.iloc[i] = current_af
    
    # 计算交叉信号
    signal = pd.Series(0, index=df.index)
    prev_trend = trend.shift(1)
    signal[(prev_trend <= 0) & (trend > 0)] = 1   # 金叉买入
    signal[(prev_trend >= 0) & (trend < 0)] = -1  # 死叉卖出
    
    df['SAR'] = sar
    df['SAR_trend'] = trend
    df['SAR_signal'] = signal
    
    return df


def get_sar_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    获取SAR交易信号
    
    Args:
        df: 包含SAR, SAR_trend列的DataFrame
        
    Returns:
        添加了SAR_signal列（已在calculate_sar中计算）
    """
    df = df.copy()
    return df


def is_sar_below_price(sar: pd.Series, close: pd.Series) -> pd.Series:
    """
    判断SAR是否在价格下方（多头趋势）
    
    Args:
        sar: SAR序列
        close: 收盘价序列
        
    Returns:
        布尔序列
    """
    return sar < close


def is_sar_above_price(sar: pd.Series, close: pd.Series) -> pd.Series:
    """
    判断SAR是否在价格上方（空头趋势）
    
    Args:
        sar: SAR序列
        close: 收盘价序列
        
    Returns:
        布尔序列
    """
    return sar > close