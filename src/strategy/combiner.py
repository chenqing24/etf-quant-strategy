#!/usr/bin/env python3
"""
策略组合器（US-005, v3 新增）

按 Q3 决策 = 风险平价（Risk Parity）:
- 每个策略有独立 risk_limits
- 组合仓位按风险平价汇总（不是简单求和）
- 总仓位不超过 US-015 市态上限

业界参考: Bridgewater "Risk Parity" (1996)
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
import pandas as pd

from src.strategy.base import BaseStrategy, Signal
from src.strategy.trend_following import TrendFollowingStrategy
from src.strategy.mean_reversion import MeanReversionStrategy
from src.strategy.breakout import BreakoutStrategy
from src.strategy.volume_divergence import VolumeDivergenceStrategy
from src.analysis.report_templates import POSITION_LIMITS


# US-015 仓位规则
POSITION_LIMITS = POSITION_LIMITS


class StrategyCombiner:
    """策略组合器（风险平价）"""

    # 默认策略库
    DEFAULT_STRATEGIES = {
        'trend_following': TrendFollowingStrategy,
        'mean_reversion': MeanReversionStrategy,
        'breakout': BreakoutStrategy,
        'volume_divergence': VolumeDivergenceStrategy,
    }

    def __init__(self, strategies: Optional[Dict[str, BaseStrategy]] = None):
        """
        Args:
            strategies: 策略字典 {code: instance}，None 用默认 4 策略
        """
        if strategies is None:
            strategies = {code: cls() for code, cls in self.DEFAULT_STRATEGIES.items()}
        self.strategies = strategies

    def select_signals(
        self,
        df_dict: Dict[str, pd.DataFrame],
        regime: str,
    ) -> List[Signal]:
        """
        组合所有策略的信号

        Args:
            df_dict: ETF 价格数据
            regime: market_state
        Returns:
            List[Signal]: 组合后的信号（按风险平价汇总仓位）
        """
        all_signals = []
        for code, strategy in self.strategies.items():
            if not strategy.is_applicable(regime):
                continue
            try:
                signals = strategy.select_etfs(df_dict, regime)
                all_signals.extend(signals)
            except Exception as e:
                # 单策略失败不影响其他
                continue

        # 风险平价汇总：按 position_size 归一化（避免超 US-015 上限）
        market_cap = POSITION_LIMITS.get(regime, 0.5)
        total_pos = sum(s.position_size for s in all_signals)
        if total_pos > market_cap:
            scale = market_cap / total_pos
            for s in all_signals:
                s.position_size = round(s.position_size * scale, 4)
        return all_signals

    def get_combined_position_size(self, regime: str) -> float:
        """组合仓位（按市态上限）"""
        return POSITION_LIMITS.get(regime, 0.5)

    def list_active_strategies(self) -> List[str]:
        """列出活跃策略"""
        return list(self.strategies.keys())
