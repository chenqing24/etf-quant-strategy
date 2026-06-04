#!/usr/bin/env python3
"""策略 B: 均值回归（MeanReversion）"""
import pandas as pd
from typing import List, Dict
from src.strategy.base import BaseStrategy, Signal


class MeanReversionStrategy(BaseStrategy):
    code = 'mean_reversion'
    name = '均值回归'
    description = 'BB 下轨 + RSI<30 超卖反弹'
    applicable_regimes = ['range_bound']
    risk_limits = {'max_pos': 0.20, 'stop_loss': -0.03, 'max_hold_days': 5}

    def select_etfs(self, df_dict, regime) -> List[Signal]:
        signals = []
        if regime != 'range_bound':
            return signals
        for code, df in df_dict.items():
            if df is None or len(df) < 20:
                continue
            closes = df['close'].astype(float).reset_index(drop=True)
            ma20 = closes.rolling(20).mean()
            std20 = closes.rolling(20).std()
            bb_lower = (ma20 - 2 * std20).iloc[-1]
            current = float(closes.iloc[-1])
            # RSI
            delta = closes.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            if pd.isna(bb_lower) or pd.isna(rsi):
                continue
            if current < bb_lower and rsi < 30:
                signals.append(Signal(
                    code=code,
                    action='buy',
                    price=current,
                    confidence=0.6,
                    reason=f'均值回归: BB下轨+RSI={rsi:.0f}',
                    stop_loss=current * 0.97,  # -3%
                    take_profit=current * 1.05, # +5%
                    max_hold_days=5,
                    position_size=self.get_position_size(),
                ))
        return signals

    def get_position_size(self) -> float:
        return 0.20
