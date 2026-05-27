"""
MACD指标计算

MACD = Moving Average Convergence/Divergence，指数平滑异同移动平均线

组成：
- DIF: 快线 = EMA(12) - EMA(26)
- DEA: 慢线 = EMA(DIF, 9)
- MACD柱: (DIF - DEA) * 2

标准参数：12/26/9

用法：
- DIF上穿DEA（金叉）：买入信号
- DIF下穿DEA（死叉）：卖出信号
- MACD柱由绿转红：多头增强
- MACD柱由红转绿：空头增强
- 价格创新高但MACD未创新高：顶背离（卖出信号）
- 价格创新低但MACD未创新低：底背离（买入信号）
"""
import pandas as pd
import numpy as np
from typing import Tuple
from src.indicators.base import IndicatorBase


def calculate_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> pd.DataFrame:
    """
    计算MACD指标
    
    Args:
        df: 包含close列的DataFrame
        fast: 快线周期，默认12
        slow: 慢线周期，默认26
        signal: 信号线周期，默认9
        
    Returns:
        添加了以下列的DataFrame:
        - DIF: 快线（EMA(fast) - EMA(slow)）
        - DEA: 慢线（EMA(DIF, signal)）
        - MACD: 柱状图 (DIF - DEA) * 2
        
    信号判断:
        DIF上穿DEA: 买入信号
        DIF下穿DEA: 卖出信号
        MACD > 0: 多头区域
        MACD < 0: 空头区域
    """
    df = df.copy()
    
    # 验证数据
    IndicatorBase.validate_data(df, ['close'])
    
    close = df['close']
    
    # 计算快线和慢线
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    
    # DIF = 快线 - 慢线
    dif = ema_fast - ema_slow
    
    # DEA = DIF的移动平均
    dea = dif.ewm(span=signal, adjust=False).mean()
    
    # MACD柱 = (DIF - DEA) * 2
    macd = (dif - dea) * 2
    
    df['DIF'] = dif
    df['DEA'] = dea
    df['MACD'] = macd
    
    return df


def get_macd_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成MACD交易信号
    
    Args:
        df: 包含DIF, DEA列的DataFrame
        
    Returns:
        添加了MACD_signal列的DataFrame:
        - 1: 买入信号（金叉）
        - -1: 卖出信号（死叉）
        - 0: 持有
    """
    df = df.copy()
    
    if 'DIF' not in df.columns or 'DEA' not in df.columns:
        raise ValueError("数据中缺少DIF或DEA列，请先调用calculate_macd")
    
    dif = df['DIF']
    dea = df['DEA']
    
    # 前一天的DIF和DEA差值
    prev_diff = dif.shift(1) - dea.shift(1)
    current_diff = dif - dea
    
    signal = pd.Series(0, index=df.index)
    
    # 金叉：DIF从下穿越DEA
    golden_cross = (prev_diff <= 0) & (current_diff > 0)
    signal[golden_cross] = 1
    
    # 死叉：DIF从上穿越DEA
    dead_cross = (prev_diff >= 0) & (current_diff < 0)
    signal[dead_cross] = -1
    
    df['MACD_signal'] = signal
    
    return df


def get_macd_histogram_type(macd: float) -> str:
    """
    判断MACD柱状图类型
    
    Args:
        macd: MACD值
        
    Returns:
        类型描述
    """
    if macd > 0:
        return "红柱（多头）"
    elif macd < 0:
        return "绿柱（空头）"
    else:
        return "零轴"


def detect_macd_divergence(
    close: pd.Series,
    macd: pd.Series,
    lookback: int = 20
) -> Tuple[pd.Series, pd.Series]:
    """
    检测MACD背离
    
    Args:
        close: 收盘价
        macd: MACD柱状图
        lookback: 回溯窗口
        
    Returns:
        (顶背离信号, 底背离信号)
    """
    top_divergence = pd.Series(False, index=close.index)
    bottom_divergence = pd.Series(False, index=close.index)
    
    for i in range(lookback, len(close)):
        window_close = close.iloc[i-lookback:i+1]
        window_macd = macd.iloc[i-lookback:i+1]
        
        # 顶背离：价格创新高但MACD未创新高
        if (close.iloc[i] == window_close.max() and 
            macd.iloc[i] < window_macd.max()):
            top_divergence.iloc[i] = True
        
        # 底背离：价格创新低但MACD未创新低
        if (close.iloc[i] == window_close.min() and 
            macd.iloc[i] > window_macd.min()):
            bottom_divergence.iloc[i] = True
    
    return top_divergence, bottom_divergence