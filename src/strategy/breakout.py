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
    # US-011: 仓位 0.25→0.30 (略增)
    risk_limits = {'max_pos': 0.30, 'stop_loss': -0.05, 'max_hold_days': 10}

    def select_etfs(self, df_dict, regime) -> List[Signal]:
        signals = []
        if regime not in self.applicable_regimes:
            return signals
        for code, df in df_dict.items():
            # US-011: 数据要求 20→12 (Donchian 10 + 缓冲)
            if df is None or len(df) < 12:
                continue
            closes = df['close'].astype(float).reset_index(drop=True)
            volumes = df['volume'].astype(float).reset_index(drop=True) if 'volume' in df.columns else None
            # US-011: Donchian 20→10 (信号频率 2x)
            donchian_high = closes.rolling(10).max().iloc[-2]  # 10日高点（不含今日）
            current = float(closes.iloc[-1])
            if pd.isna(donchian_high):
                continue
            # 突破 Donchian 高点
            if current <= donchian_high:
                continue
            # 成交量异动 (US-011: 1.5x→1.2x, 降低门槛)
            if volumes is None or len(volumes) < 12:
                continue
            vol_ma10 = volumes.rolling(10).mean().iloc[-1]
            vol_ratio = volumes.iloc[-1] / vol_ma10 if vol_ma10 > 0 else 1.0
            if vol_ratio < 1.2:
                continue
            signals.append(Signal(
                code=code,
                action='buy',
                price=current,
                confidence=0.65,
                reason=f'反转突破: Donchian 10日 + vol={vol_ratio:.1f}x (US-011)',
                stop_loss=current * 0.95,  # -5%
                take_profit=current * 1.10, # +10%
                max_hold_days=10,
                position_size=self.get_position_size(),
            ))
        return signals

    def get_position_size(self) -> float:
        return 0.25
