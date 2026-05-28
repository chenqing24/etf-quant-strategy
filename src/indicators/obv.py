"""
OBV和MAOBV指标计算

OBV = On Balance Volume，能量潮指标
MAOBV = OBV的移动平均线

OBV > MAOBV: 资金流入
OBV < MAOBV: 资金流出
"""
import pandas as pd
import numpy as np
from typing import Tuple
from src.indicators.base import IndicatorBase


def calculate_obv(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算OBV（能量潮指标）
    
    OBV计算规则：
    - 当日收盘价 > 前日收盘价：OBV += 当日成交量
    - 当日收盘价 < 前日收盘价：OBV -= 当日成交量
    - 当日收盘价 = 前日收盘价：OBV不变
    
    Args:
        df: 包含close和volume列的DataFrame
        
    Returns:
        添加了OBV列的DataFrame
        
    信号判断:
        OBV上升：资金流入
        OBV下降：资金流出
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['close', 'volume'])
    
    close = df['close']
    volume = df['volume']
    
    # 计算价格变化方向
    price_change = close.diff()
    price_change.iloc[0] = 0  # 第一天设为0，不影响OBV
    
    # 根据价格变化方向累加或累减成交量
    obv = pd.Series(0.0, index=df.index)
    obv[price_change > 0] = volume[price_change > 0]   # 价格上涨，加成交量
    obv[price_change < 0] = -volume[price_change < 0]  # 价格下跌，减成交量
    obv[price_change == 0] = 0  # 价格不变，OBV不变
    
    # 累计求和
    df['OBV'] = obv.cumsum()
    
    return df


def calculate_maobv(
    df: pd.DataFrame,
    obv_window: int = 10
) -> pd.DataFrame:
    """
    计算MAOBV（OBV的移动平均）
    
    Args:
        df: 包含OBV列的DataFrame
        obv_window: OBV均线周期，默认10日
        
    Returns:
        添加了MAOBV列的DataFrame
    """
    df = df.copy()
    
    if 'OBV' not in df.columns:
        df = calculate_obv(df)
    
    # 计算OBV的移动平均
    df['MAOBV'] = df['OBV'].rolling(window=obv_window, min_periods=1).mean()
    
    return df


def calculate_obv_maobv(
    df: pd.DataFrame,
    obv_window: int = 10
) -> pd.DataFrame:
    """
    同时计算OBV和MAOBV
    
    Args:
        df: 包含close和volume列的DataFrame
        obv_window: OBV均线周期，默认10日
        
    Returns:
        添加了OBV和MAOBV列的DataFrame
        
    信号判断:
        OBV > MAOBV: 资金流入，金叉
        OBV < MAOBV: 资金流出，死叉
    """
    df = df.copy()
    
    # 计算OBV
    close = df['close']
    volume = df['volume']
    
    price_change = close.diff()
    price_change.iloc[0] = 0
    
    obv = pd.Series(0.0, index=df.index)
    obv[price_change > 0] = volume[price_change > 0]
    obv[price_change < 0] = -volume[price_change < 0]
    obv[price_change == 0] = 0
    
    df['OBV'] = obv.cumsum()
    df['MAOBV'] = df['OBV'].rolling(window=obv_window, min_periods=1).mean()
    
    return df


def get_obv_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成OBV交易信号
    
    Args:
        df: 包含OBV和MAOBV列的DataFrame
        
    Returns:
        添加了以下列的DataFrame:
        - OBV_diff: OBV与MAOBV的差值
        - OBV_signal: 交叉信号 (1买入, -1卖出, 0持有)
    """
    df = df.copy()
    
    if 'OBV' not in df.columns or 'MAOBV' not in df.columns:
        raise ValueError("数据中缺少OBV或MAOBV列，请先调用calculate_obv_maobv")
    
    # 计算差值
    df['OBV_diff'] = df['OBV'] - df['MAOBV']
    
    # 生成交叉信号
    prev_diff = df['OBV_diff'].shift(1)
    
    df['OBV_signal'] = 0
    df.loc[(prev_diff <= 0) & (df['OBV_diff'] > 0), 'OBV_signal'] = 1   # 金叉买入
    df.loc[(prev_diff >= 0) & (df['OBV_diff'] < 0), 'OBV_signal'] = -1  # 死叉卖出
    
    return df