"""
指标计算基类

定义指标计算的通用接口和工具函数
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from abc import ABC, abstractmethod


class IndicatorBase(ABC):
    """
    指标计算基类
    
    所有指标计算器应继承此类
    """
    
    @staticmethod
    def validate_data(df: pd.DataFrame, required_cols: List[str]) -> bool:
        """
        验证数据帧是否包含必需列
        
        Args:
            df: 数据帧
            required_cols: 必需列名列表
            
        Returns:
            True 如果验证通过
        """
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"缺少必需列: {missing}")
        return True
    
    @staticmethod
    def get_required_cols() -> List[str]:
        """
        获取指标所需的必需列
        
        Returns:
            列名列表
        """
        return ['close']
    
    @classmethod
    def calculate(cls, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        计算指标（子类需实现）
        
        Args:
            df: 包含OHLCV数据的DataFrame
            **kwargs: 指标特定参数
            
        Returns:
            添加了指标列的DataFrame
        """
        raise NotImplementedError("子类必须实现calculate方法")
    
    @staticmethod
    def smooth(values: pd.Series, window: int) -> pd.Series:
        """
        平滑处理
        
        Args:
            values: 数值序列
            window: 窗口大小
            
        Returns:
            平滑后的序列
        """
        return values.rolling(window=window, min_periods=1).mean()
    
    @staticmethod
    def ema(values: pd.Series, span: int) -> pd.Series:
        """
        指数移动平均
        
        Args:
            values: 数值序列
            span: 周期
            
        Returns:
            EMA序列
        """
        return values.ewm(span=span, adjust=False).mean()
    
    @staticmethod
    def sma(values: pd.Series, window: int) -> pd.Series:
        """
        简单移动平均
        
        Args:
            values: 数值序列
            window: 窗口大小
            
        Returns:
            SMA序列
        """
        return values.rolling(window=window, min_periods=1).mean()


def calculate_returns(close: pd.Series, periods: int = 1) -> pd.Series:
    """
    计算收益率
    
    Args:
        close: 收盘价序列
        periods: 周期数
        
    Returns:
        收益率序列
    """
    return close.pct_change(periods=periods)


def calculate_max_drawdown(cumulative_returns: pd.Series) -> float:
    """
    计算最大回撤
    
    Args:
        cumulative_returns: 累计收益率序列
        
    Returns:
        最大回撤值（负数）
    """
    rolling_max = cumulative_returns.cummax()
    drawdown = cumulative_returns - rolling_max
    return drawdown.min()


def validate_price_data(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    验证价格数据的有效性
    
    Args:
        df: 数据帧
        
    Returns:
        (是否有效, 错误信息列表)
    """
    errors = []
    
    # 检查必需列
    required = ['open', 'high', 'low', 'close', 'volume']
    for col in required:
        if col not in df.columns:
            errors.append(f"缺少列: {col}")
    
    if errors:
        return False, errors
    
    # 检查价格有效性
    if (df['close'] <= 0).any():
        errors.append("存在价格为0或负值的数据")
    
    if (df['volume'] < 0).any():
        errors.append("存在成交量为负的数据")
    
    # 检查OHLC关系
    if ((df['high'] < df['low'])).any():
        errors.append("存在高价低于低价的数据")
    
    if ((df['high'] < df['close']) | (df['high'] < df['open'])).any():
        errors.append("存在高价低于收盘/开盘价的数据")
    
    if ((df['low'] > df['close']) | (df['low'] > df['open'])).any():
        errors.append("存在低价高于收盘/开盘价的数据")
    
    return len(errors) == 0, errors