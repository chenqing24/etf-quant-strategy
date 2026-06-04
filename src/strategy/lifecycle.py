#!/usr/bin/env python3
"""
策略生命周期管理（US-006, v3 新增）

按 Q4 决策 = 月度评估:
- 每个策略有 3 月 Sharpe 记录
- Sharpe < 0 持续 3 月 → 降权 50%
- Sharpe < 0 持续 6 月 → 自动退役
- 退役策略不再入选组合

业界参考: Bahnsen et al. "Strategy Lifecycle Management" (2015)
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.strategy.registry import StrategyRegistry, StrategyMeta


@dataclass
class PerformanceRecord:
    """策略月度表现记录"""
    strategy_code: str
    month: str                        # YYYY-MM
    sharpe: float
    total_return: float
    trades: int


class LifecycleManager:
    """策略生命周期管理（v3 核心）"""

    # 降权阈值
    DEMOTE_MONTHS_THRESHOLD = 3      # Sharpe<0 持续 3 月降权
    DEMOTE_FACTOR = 0.5              # 降权 50%

    # 退役阈值
    RETIRE_MONTHS_THRESHOLD = 6      # Sharpe<0 持续 6 月退役

    def __init__(self, registry: Optional[StrategyRegistry] = None):
        self.registry = registry or StrategyRegistry()
        self._records: Dict[str, List[PerformanceRecord]] = {}

    def record_performance(self, rec: PerformanceRecord) -> None:
        """记录策略月度表现"""
        self._records.setdefault(rec.strategy_code, []).append(rec)

    def get_recent_sharpe(self, code: str, n_months: int = 3) -> List[float]:
        """获取最近 N 个月的 Sharpe"""
        recs = self._records.get(code, [])
        if not recs:
            return []
        return [r.sharpe for r in recs[-n_months:]]

    def evaluate(self) -> Dict[str, str]:
        """
        月度评估所有策略

        Returns:
            {strategy_code: 'active' | 'demoted' | 'retired'}
        """
        results = {}
        for meta in self.registry.get_active():
            code = meta.code
            sharpe_3m = self.get_recent_sharpe(code, n_months=3)
            sharpe_6m = self.get_recent_sharpe(code, n_months=6)
            action = self._decide(sharpe_3m, sharpe_6m)
            if action == 'demoted':
                self._demote(code)
            elif action == 'retired':
                self.registry.deregister(code)
            results[code] = action
        return results

    def _decide(self, sharpe_3m: List[float], sharpe_6m: List[float]) -> str:
        """根据 Sharpe 序列决定动作"""
        # 退役: 最近 6 月都 < 0
        if len(sharpe_6m) >= self.RETIRE_MONTHS_THRESHOLD and all(s < 0 for s in sharpe_6m):
            return 'retired'
        # 降权: 最近 3 月都 < 0
        if len(sharpe_3m) >= self.DEMOTE_MONTHS_THRESHOLD and all(s < 0 for s in sharpe_3m):
            return 'demoted'
        return 'active'

    def _demote(self, code: str) -> None:
        """降权 50%（修改 position_size）"""
        meta = self.registry.get(code)
        if not meta:
            return
        for k in ['max_pos', 'position_size']:
            if k in meta.risk_limits:
                meta.risk_limits[k] *= self.DEMOTE_FACTOR
        self.registry.register(meta)  # 写回

    def get_lifecycle_stats(self) -> Dict[str, int]:
        """生命周期统计"""
        active = self.registry.get_active()
        all_strats = self.registry.list_all()
        return {
            'active': len(active),
            'retired': len(all_strats) - len(active),
            'total': len(all_strats),
        }
