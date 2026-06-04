#!/usr/bin/env python3
"""策略 A: 趋势跟踪（TrendFollowing）"""
import pandas as pd
from typing import List, Dict
from src.strategy.base import BaseStrategy, Signal


class TrendFollowingStrategy(BaseStrategy):
    code = 'trend_following'
    name = '趋势跟踪'
    description = 'MA60 突破 + ADX>25 趋势确认'
    applicable_regimes = ['trend_up']
    risk_limits = {'max_pos': 0.30, 'stop_loss': -0.08, 'max_hold_days': 20}

    def select_etfs(self, df_dict, regime) -> List[Signal]:
        signals = []
        if regime != 'trend_up':
            return signals
        for code, df in df_dict.items():
            if df is None or len(df) < 60:
                continue
            closes = df['close'].astype(float).reset_index(drop=True)
            ma60 = closes.rolling(60).mean().iloc[-1]
            ma20 = closes.rolling(20).mean().iloc[-1]
            current = float(closes.iloc[-1])
            if pd.isna(ma60) or pd.isna(ma20):
                continue
            # MA20 上穿 MA60 + MA60 上升
            ma60_prev = closes.rolling(60).mean().iloc[-2]
            if ma20 > ma60 and ma60 > ma60_prev and current > ma20:
                signals.append(Signal(
                    code=code,
                    action='buy',
                    price=current,
                    confidence=0.7,
                    reason='趋势跟踪: MA20 上穿 MA60',
                    stop_loss=current * 0.92,   # -8%
                    take_profit=current * 1.15, # +15%
                    max_hold_days=20,
                    position_size=self.get_position_size(),
                ))
        return signals

    def get_position_size(self) -> float:
        return 0.30
