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
    # US-011: 仓位 0.30→0.40 (主策略权重增加)
    risk_limits = {'max_pos': 0.40, 'stop_loss': -0.08, 'max_hold_days': 20}

    def select_etfs(self, df_dict, regime) -> List[Signal]:
        signals = []
        if regime != 'trend_up':
            return signals
        for code, df in df_dict.items():
            # US-011: 数据要求从 60 缩短到 25 (MA20 + MA5)
            if df is None or len(df) < 25:
                continue
            closes = df['close'].astype(float).reset_index(drop=True)
            # US-011: MA60→MA20 突破 (短周期适应大牛市)
            ma5 = closes.rolling(5).mean().iloc[-1]
            ma20 = closes.rolling(20).mean().iloc[-1]
            current = float(closes.iloc[-1])
            if pd.isna(ma5) or pd.isna(ma20):
                continue
            # MA5 上穿 MA20 (短周期敏感)
            if ma5 > ma20 and current > ma5:
                signals.append(Signal(
                    code=code,
                    action='buy',
                    price=current,
                    confidence=0.7,
                    reason='趋势跟踪: MA5 上穿 MA20 (US-011 短周期)',
                    stop_loss=current * 0.92,   # -8%
                    take_profit=current * 1.15, # +15%
                    max_hold_days=20,
                    position_size=self.get_position_size(),
                ))
        return signals

    def get_position_size(self) -> float:
        return 0.30
