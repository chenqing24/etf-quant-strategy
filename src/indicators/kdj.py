"""
KDJ指标计算

KDJ = 随机指标
参数：9日周期，3日平滑K，3日平滑D

K值和D值的取值范围：0-100
J值 = 3*K - 2*D
"""
import pandas as pd
import numpy as np
from typing import Tuple
from src.indicators.base import IndicatorBase


def calculate_kdj(
    df: pd.DataFrame,
    n: int = 9,
    m1: int = 3,
    m2: int = 3
) -> pd.DataFrame:
    """
    计算KDJ指标
    
    Args:
        df: 包含high, low, close列的DataFrame
        n: RSV计算周期，默认9日
        m1: K值平滑周期，默认3日
        m2: D值平滑周期，默认3日
        
    Returns:
        添加了以下列的DataFrame:
        - K: K值 (0-100)
        - D: D值 (0-100)
        - J: J值 = 3*K - 2*D
        - RSV: 原始RSV值
        
    信号判断:
        K > 80: 超买区域
        K < 20: 超卖区域
        K上穿D: 买入信号
        K下穿D: 卖出信号
        J > 100 或 J < 0: 警惕区域（极端信号）
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['high', 'low', 'close'])
    
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 计算N日内最高价和最低价
    lowest_low = low.rolling(window=n, min_periods=1).min()
    highest_high = high.rolling(window=n, min_periods=1).max()
    
    # 计算RSV (Raw Stochastic Value)
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    rsv = rsv.fillna(50)  # 避免除零
    
    # 计算K值（平滑RSV）
    k = rsv.ewm(com=m1-1, adjust=False).mean()
    
    # 计算D值（平滑K）
    d = k.ewm(com=m2-1, adjust=False).mean()
    
    # 计算J值
    j = 3 * k - 2 * d
    
    df['RSV'] = rsv
    df['K'] = k
    df['D'] = d
    df['J'] = j
    
    return df


def get_kdj_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成KDJ交易信号
    
    Args:
        df: 包含K和D列的DataFrame
        
    Returns:
        添加了KDJ_signal列的DataFrame:
        - 1: 买入信号 (K从下穿越D且<20)
        - -1: 卖出信号 (K从上穿越D且>80)
        - 0: 持有
    """
    df = df.copy()
    
    if 'K' not in df.columns or 'D' not in df.columns:
        raise ValueError("数据中缺少K或D列，请先调用calculate_kdj")
    
    k = df['K']
    d = df['D']
    prev_k = k.shift(1)
    prev_d = d.shift(1)
    
    signal = pd.Series(0, index=df.index)
    
    # 金叉：K从下穿越D且在超卖区域
    golden_cross = (prev_k <= prev_d) & (k > d) & (k < 20)
    signal[golden_cross] = 1
    
    # 死叉：K从上穿越D且在超买区域
    dead_cross = (prev_k >= prev_d) & (k < d) & (k > 80)
    signal[dead_cross] = -1
    
    df['KDJ_signal'] = signal
    
    return df


def get_kdj_extreme(df: pd.DataFrame) -> pd.DataFrame:
    """
    KDJ极值信号（用于抄底逃顶）
    
    Args:
        df: 包含K, D, J列的DataFrame
        
    Returns:
        添加了extreme_signal列:
        - 1: 超卖信号 (K<20, J<0)
        - -1: 超买信号 (K>80, J>100)
        - 0: 正常区域
    """
    df = df.copy()
    
    df['extreme_signal'] = 0
    
    # 超卖区域
    oversold = (df['K'] < 20) & (df['J'] < 0)
    df.loc[oversold, 'extreme_signal'] = 1
    
    # 超买区域
    overbought = (df['K'] > 80) & (df['J'] > 100)
    df.loc[overbought, 'extreme_signal'] = -1
    
    return df