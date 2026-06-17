#!/usr/bin/env python3
"""指标计算层"""
import pandas as pd
from typing import Dict


class Indicator:
    """技术指标计算"""

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标（SOP-P1-2 升级）

        输出字段:
        - ma5, ma10, ma20, ma60, ma120: 移动平均线
        - ma_vol_20: 成交量均线
        - vol_ratio: 量比 (volume / ma_vol_20)
        - rsi_5, rsi_14: RSI指标
        - macd, macd_signal, macd_hist: MACD 指标（SOP-P1-2 新增）
        - boll_upper, boll_middle, boll_lower: 布林带（SOP-P1-2 新增）
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

        # SOP-P1-2: MACD 指标
        # EMA12 - EMA26 = DIF (macd)
        # EMA9 of DIF = DEA (macd_signal)
        # DIF - DEA = macd_hist
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = (df['macd'] - df['macd_signal']) * 2

        # SOP-P1-2: BOLL 布林带
        # 中轨 = MA20
        # 上轨 = MA20 + 2*STD20
        # 下轨 = MA20 - 2*STD20
        df['boll_middle'] = df['ma20']
        std20 = df['close'].rolling(20).std()
        df['boll_upper'] = df['boll_middle'] + 2 * std20
        df['boll_lower'] = df['boll_middle'] - 2 * std20

        return df

    @staticmethod
    def calculate_all(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """批量计算"""
        return {code: Indicator.calculate(df) for code, df in data.items()}


__all__ = ['Indicator']