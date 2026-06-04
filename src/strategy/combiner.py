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
        market_cap = self.get_combined_position_size(regime)
        total_pos = sum(s.position_size for s in all_signals)
        if total_pos > market_cap:
            scale = market_cap / total_pos
            for s in all_signals:
                s.position_size = round(s.position_size * scale, 4)
        return all_signals

    def get_combined_position_size(self, regime: str) -> float:
        """组合仓位（按市态上限）

        US-011: 动态化
        - trend_up: 0.85 (接近 US-015 90% 上限，激进利用趋势)
        - range_bound: 0.50 (US-015 50% 上限)
        - reversal_point: 0.20 (试探)
        - trend_down: 0.30
        - crash: 0.0
        """
        return POSITION_LIMITS.get(regime, 0.5)  # 复用 US-015 仓位规则

    def list_active_strategies(self) -> List[str]:
        """列出活跃策略"""
        return list(self.strategies.keys())

    def select_signals_with_baseline(
        self,
        df_dict,
        regime: str,
        baseline_score_func=None,
        baseline_threshold: int = 6,
        confidence_boost: float = 0.20,
    ):
        """
        US-012: 仓位叠加（baseline 评分 + Combiner 信号）

        Args:
            df_dict: ETF 价格数据
            regime: market_state
            baseline_score_func: 外部评分函数 (code, df, date) -> score
            baseline_threshold: baseline 评分阈值
            confidence_boost: 双满足时 confidence 加成

        Returns:
            叠加后的信号列表（按 US-015 市态上限归一化仓位）
        """
        from src.strategy.base import Signal

        # 1. Combiner 信号（按市态）
        combiner_signals = self.select_signals(df_dict, regime=regime)
        combiner_codes = {s.code: s for s in combiner_signals}

        # 2. Baseline 评分信号
        baseline_signals = {}
        if baseline_score_func is not None:
            for code, df in df_dict.items():
                if df is None or len(df) < 60:
                    continue
                try:
                    last_date = df['date'].iloc[-1]
                    score = baseline_score_func(code, df, last_date)
                    if score >= baseline_threshold:
                        baseline_signals[code] = Signal(
                            code=code,
                            action='buy',
                            price=float(df['close'].iloc[-1]),
                            confidence=score / 10.0,
                            reason=f'baseline_score={score}',
                        )
                except Exception:
                    pass

        # 3. 叠加 (union)
        all_codes = set(combiner_codes.keys()) | set(baseline_signals.keys())
        signals = []
        for code in all_codes:
            in_combiner = code in combiner_codes
            in_baseline = code in baseline_signals

            if in_combiner and in_baseline:
                # 双满足: 仓位加成
                sig = combiner_codes[code]
                sig.confidence = min(1.0, sig.confidence + confidence_boost)
                sig.reason = sig.reason + f' + baseline_score (双满足)'
            elif in_combiner:
                sig = combiner_codes[code]
            else:
                sig = baseline_signals[code]
            signals.append(sig)

        # 4. 仓位归一化（不超 US-015 市态上限）
        market_cap = self.get_combined_position_size(regime)
        total_pos = sum(s.position_size for s in signals)
        if total_pos > market_cap and total_pos > 0:
            scale = market_cap / total_pos
            for s in signals:
                s.position_size = round(s.position_size * scale, 4)
        return signals
