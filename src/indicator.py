#!/usr/bin/env python3
"""指标计算层"""
import pandas as pd
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
        
        return df
    
    @staticmethod
    def calculate_all(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """批量计算"""
        return {code: Indicator.calculate(df) for code, df in data.items()}


__all__ = ['Indicator']