"""
RSI指标计算

RSI = Relative Strength Index，相对强弱指数
用于判断超买超卖

RSI计算：
1. 计算N日内上涨平均涨幅和下跌平均跌幅
2. RSI = 上涨平均值 / (上涨平均值 + 下跌平均值) * 100

参数：
- RSI(5): 短期，更敏感
- RSI(10): 中期
- RSI(14): 标准

用法：
- RSI > 70: 超买区域，可能回调
- RSI < 30: 超卖区域，可能反弹
- RSI从下穿越50: 走强
- RSI从上穿越50: 走弱
"""
import pandas as pd
import numpy as np
from typing import Tuple
from src.indicators.base import IndicatorBase


def calculate_rsi(
    df: pd.DataFrame,
    window: int = 5
) -> pd.DataFrame:
    """
    计算RSI指标
    
    Args:
        df: 包含close列的DataFrame
        window: RSI周期，默认5日
        
    Returns:
        添加了RSI列的DataFrame
        
    信号判断:
        RSI > 70: 超买区域
        RSI < 30: 超卖区域
        RSI上穿50: 走强信号
        RSI下穿50: 走弱信号
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['close'])
    
    close = df['close']
    
    # 计算价格变化
    delta = close.diff()
    
    # 分离涨跌
    gain = delta.copy()
    loss = delta.copy()
    gain[gain < 0] = 0
    loss[loss > 0] = 0
    loss = loss.abs()
    
    # 计算平均涨跌幅（使用指数移动平均）
    avg_gain = gain.ewm(com=window-1, adjust=False).mean()
    avg_loss = loss.ewm(com=window-1, adjust=False).mean()
    
    # 计算RS和RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # 处理除零情况（avg_loss为0时RSI=100）
    rsi = rsi.fillna(50)
    
    df[f'RSI_{window}'] = rsi
    
    return df


def get_rsi_signal(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    生成RSI交易信号
    
    Args:
        df: 包含RSI列的DataFrame
        window: RSI周期
        
    Returns:
        添加了RSI_signal列的DataFrame:
        - 1: 买入信号（超卖或金叉50）
        - -1: 卖出信号（超买或死叉50）
        - 0: 持有
    """
    df = df.copy()
    
    rsi_col = f'RSI_{window}'
    if rsi_col not in df.columns:
        raise ValueError(f"数据中缺少{rsi_col}列，请先调用calculate_rsi")
    
    rsi = df[rsi_col]
    signal = pd.Series(0, index=df.index)
    
    # 超卖区域：RSI < 30
    signal[rsi < 30] = 1
    
    # 超买区域：RSI > 70
    signal[rsi > 70] = -1
    
    # 金叉50线
    prev_rsi = rsi.shift(1)
    signal[(prev_rsi <= 50) & (rsi > 50)] = 1
    signal[(prev_rsi >= 50) & (rsi < 50)] = -1
    
    df['RSI_signal'] = signal
    
    return df


def get_rsi_level(rsi: float) -> str:
    """
    获取RSI水平描述
    
    Args:
        rsi: RSI值
        
    Returns:
        水平描述字符串
    """
    if rsi > 80:
        return "极度超买"
    elif rsi > 70:
        return "超买"
    elif rsi > 60:
        return "偏强"
    elif rsi > 40:
        return "中性"
    elif rsi > 30:
        return "偏弱"
    elif rsi > 20:
        return "超卖"
    else:
        return "极度超卖"