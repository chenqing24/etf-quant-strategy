#!/usr/bin/env python3
"""指标计算层"""
import pandas as pd
import numpy as np
from typing import Dict


class Indicator:
    """技术指标计算"""
    
    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标
        
        输出字段:
        - ma5, ma10, ma20, ma60, ma120: 移动平均线
        - ma_vol_20: 成交量均线
        - vol_ratio: 量比 (volume / ma_vol_20)
        - rsi_5, rsi_14: RSI指标
        - adx_14: ADX趋势强度指标（v9 双模式）
        """
        df = df.copy()
        
        # 移动平均线
        for d in [5, 10, 20, 60, 120]:
            df[f'ma{d}'] = df['close'].rolling(d).mean()
        
        # 成交量均线
        df['ma_vol_20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['ma_vol_20']
        
        # RSI
        for d in [5, 14]:
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(d).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(d).mean()
            rs = gain / (loss + 1e-10)
            df[f'rsi_{d}'] = 100 - (100 / (1 + rs))
        
        # ADX（v9 双模式）
        df = Indicator._calculate_adx(df, period=14)
        
        return df
    
    @staticmethod
    def _calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算 ADX 指标
        
        Args:
            df: 包含 high, low, close 的 DataFrame
            period: ADX 周期，默认14
            
        Returns:
            添加了 adx_{period} 列的 DataFrame
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range (TR)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement (DM)
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        plus_dm[minus_dm > plus_dm] = 0
        
        minus_dm[minus_dm < 0] = 0
        minus_dm[plus_dm > minus_dm] = 0
        
        # 平滑
        atr = tr.rolling(period).mean()
        plus_dm_smooth = plus_dm.rolling(period).mean()
        minus_dm_smooth = minus_dm.rolling(period).mean()
        
        # DI+ DI-
        plus_di = 100 * plus_dm_smooth / (atr + 1e-10)
        minus_di = 100 * minus_dm_smooth / (atr + 1e-10)
        
        # DX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        
        # ADX
        adx = dx.rolling(period).mean()
        
        df[f'adx_{period}'] = adx
        
        return df
    
    @staticmethod
    def calculate_all(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """批量计算"""
        return {code: Indicator.calculate(df) for code, df in data.items()}


__all__ = ['Indicator']