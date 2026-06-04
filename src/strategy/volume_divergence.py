#!/usr/bin/env python3
"""策略 D: 量价背离（VolumeDivergence）"""
import pandas as pd
from typing import List, Dict
from src.strategy.base import BaseStrategy, Signal


class VolumeDivergenceStrategy(BaseStrategy):
    code = 'volume_divergence'
    name = '量价背离'
    description = '价格新高 + 成交量背离 → 反转入场'
    applicable_regimes = ['reversal_point']
    risk_limits = {'max_pos': 0.15, 'stop_loss': -0.04, 'max_hold_days': 7}

    def select_etfs(self, df_dict, regime) -> List[Signal]:
        signals = []
        if regime != 'reversal_point':
            return signals
        for code, df in df_dict.items():
            if df is None or len(df) < 30:
                continue
            closes = df['close'].astype(float).reset_index(drop=True)
            volumes = df['volume'].astype(float).reset_index(drop=True) if 'volume' in df.columns else None
            if volumes is None or len(volumes) < 30:
                continue
            current = float(closes.iloc[-1])
            high_30 = closes.rolling(30).max().iloc[-1]
            vol_ma30 = volumes.rolling(30).mean().iloc[-1]
            vol_ratio = volumes.iloc[-1] / vol_ma30 if vol_ma30 > 0 else 1.0
            if pd.isna(high_30) or pd.isna(vol_ratio):
                continue
            # 价格新高 + 成交量萎缩（背离）→ 反转预警
            if current >= high_30 * 0.99 and vol_ratio < 0.7:
                signals.append(Signal(
                    code=code,
                    action='buy',
                    price=current,
                    confidence=0.5,
                    reason=f'量价背离: 价格新高 + 成交量 vol={vol_ratio:.2f}x',
                    stop_loss=current * 0.96,  # -4%
                    take_profit=current * 1.08, # +8%
                    max_hold_days=7,
                    position_size=self.get_position_size(),
                ))
        return signals

    def get_position_size(self) -> float:
        return 0.15
