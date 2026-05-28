"""
ADX指标计算

ADX = Average Directional Index，平均趋向指数
用于判断趋势强弱

组成：
- +DM: 正向趋向指标
- -DM: 负向趋向指标
- TR: 真实波幅
- +DI: 正向趋向指数
- -DI: 负向趋向指数
- ADX: 平均趋向指数

用法：
- ADX > 25: 趋势明显（强于震荡）
- ADX < 20: 震荡市场，无明显趋势
- +DI上穿-DI: 买入信号
- -DI上穿+DI: 卖出信号
"""
import pandas as pd
import numpy as np
from typing import Tuple
from src.indicators.base import IndicatorBase


def calculate_adx(
    df: pd.DataFrame,
    window: int = 14
) -> pd.DataFrame:
    """
    计算ADX指标
    
    Args:
        df: 包含high, low, close列的DataFrame
        window: 计算周期，默认14日
        
    Returns:
        添加了以下列的DataFrame:
        - TR: 真实波幅
        - DM_plus: 正向趋向
        - DM_minus: 负向趋向
        - DI_plus: 正向趋向指数
        - DI_minus: 负向趋向指数
        - DX: 趋向指数
        - ADX: 平均趋向指数
        
    信号判断:
        ADX > 25: 趋势明显
        ADX < 20: 无趋势（震荡）
        +DI > -DI: 多头趋势
        -DI > +DI: 空头趋势
        +DI上穿-DI: 买入信号
        -DI上穿+DI: 卖出信号
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['high', 'low', 'close'])
    
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 计算真实波幅 (True Range)
    high_low = high - low
    high_close = (high - close.shift(1)).abs()
    low_close = (low - close.shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # 计算趋向 (Directional Movement)
    up_move = high.diff()
    down_move = -low.diff()
    
    # +DM：价格上涨的趋向
    dm_plus = pd.Series(0.0, index=df.index)
    dm_plus[(up_move > down_move) & (up_move > 0)] = up_move
    
    # -DM：价格下跌的趋向
    dm_minus = pd.Series(0.0, index=df.index)
    dm_minus[(down_move > up_move) & (down_move > 0)] = down_move
    
    # 平滑处理
    tr_smooth = tr.rolling(window=window, min_periods=window).sum()
    dm_plus_smooth = dm_plus.rolling(window=window, min_periods=window).sum()
    dm_minus_smooth = dm_minus.rolling(window=window, min_periods=window).sum()
    
    # 计算趋向指数
    di_plus = dm_plus_smooth / tr_smooth * 100
    di_minus = dm_minus_smooth / tr_smooth * 100
    
    # DX = |+DI - -DI| / (+DI + -DI) * 100
    di_sum = di_plus + di_minus
    di_sum = di_sum.replace(0, np.nan)
    dx = (di_plus - di_minus).abs() / di_sum * 100
    
    # ADX = DX的平滑均值
    adx = dx.rolling(window=window, min_periods=1).mean()
    
    df['TR'] = tr
    df['DM_plus'] = dm_plus
    df['DM_minus'] = dm_minus
    df['DI_plus'] = di_plus
    df['DI_minus'] = di_minus
    df['DX'] = dx
    df['ADX'] = adx
    
    return df


def get_adx_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成ADX交易信号
    
    Args:
        df: 包含DI_plus, DI_minus, ADX列的DataFrame
        
    Returns:
        添加了ADX_signal列的DataFrame:
        - 1: 买入信号 (+DI上穿-DI且ADX>25)
        - -1: 卖出信号 (-DI上穿+DI且ADX>25)
        - 0: 持有
    """
    df = df.copy()
    
    if 'DI_plus' not in df.columns or 'DI_minus' not in df.columns:
        raise ValueError("数据中缺少DI_plus或DI_minus列，请先调用calculate_adx")
    
    di_plus = df['DI_plus']
    di_minus = df['DI_minus']
    adx = df.get('ADX', pd.Series(25, index=df.index))
    
    # 前一日的DI差值
    prev_diff = di_plus.shift(1) - di_minus.shift(1)
    current_diff = di_plus - di_minus
    
    signal = pd.Series(0, index=df.index)
    
    # 金叉：+DI从下穿越-DI且ADX>25（强趋势）
    golden_cross = (prev_diff <= 0) & (current_diff > 0) & (adx > 25)
    signal[golden_cross] = 1
    
    # 死叉：-DI从下穿越+DI且ADX>25
    dead_cross = (prev_diff >= 0) & (current_diff < 0) & (adx > 25)
    signal[dead_cross] = -1
    
    df['ADX_signal'] = signal
    
    return df


def is_trending(adx: pd.Series, threshold: float = 25) -> pd.Series:
    """
    判断是否有明显趋势
    
    Args:
        adx: ADX序列
        threshold: 阈值，默认25
        
    Returns:
        布尔序列
    """
    return adx > threshold


def get_trend_direction(di_plus: pd.Series, di_minus: pd.Series) -> pd.Series:
    """
    判断趋势方向
    
    Args:
        di_plus: 正向趋向指数
        di_minus: 负向趋向指数
        
    Returns:
        趋势方向序列 (1多头, -1空头, 0震荡)
    """
    diff = di_plus - di_minus
    direction = pd.Series(0, index=di_plus.index)
    direction[diff > 0] = 1
    direction[diff < 0] = -1
    return direction