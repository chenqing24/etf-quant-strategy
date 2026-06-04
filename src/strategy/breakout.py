#!/usr/bin/env python3
"""策略 C: 反转突破（Breakout）"""
import pandas as pd
from typing import List, Dict
from src.strategy.base import BaseStrategy, Signal


class BreakoutStrategy(BaseStrategy):
    code = 'breakout'
    name = '反转突破'
    description = 'Donchian 20日突破 + 成交量>1.5x'
    applicable_regimes = ['trend_up', 'reversal_point']
    risk_limits = {'max_pos': 0.25, 'stop_loss': -0.05, 'max_hold_days': 10}

    def select_etfs(self, df_dict, regime) -> List[Signal]:
        signals = []
        if regime not in self.applicable_regimes:
            return signals
        for code, df in df_dict.items():
            if df is None or len(df) < 20:
                continue
            closes = df['close'].astype(float).reset_index(drop=True)
            volumes = df['volume'].astype(float).reset_index(drop=True) if 'volume' in df.columns else None
            donchian_high = closes.rolling(20).max().iloc[-2]  # 20日高点（不含今日）
            current = float(closes.iloc[-1])
            if pd.isna(donchian_high):
                continue
            # 突破 Donchian 高点
            if current <= donchian_high:
                continue
            # 成交量异动 (vol_ratio > 1.5)
            if volumes is None or len(volumes) < 20:
                continue
            vol_ma20 = volumes.rolling(20).mean().iloc[-1]
            vol_ratio = volumes.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1.0
            if vol_ratio < 1.5:
                continue
            signals.append(Signal(
                code=code,
                action='buy',
                price=current,
                confidence=0.65,
                reason=f'反转突破: Donchian 突破 + vol={vol_ratio:.1f}x',
                stop_loss=current * 0.95,  # -5%
                take_profit=current * 1.10, # +10%
                max_hold_days=10,
                position_size=self.get_position_size(),
            ))
        return signals

    def get_position_size(self) -> float:
        return 0.25
