#!/usr/bin/env python3
"""
策略基类（US-004）

按 v3 纲要:
- 1 模型 = N 策略
- 每个策略独立风控和仓位
- 策略独立注册（用 StrategyRegistry）

接口:
    class MyStrategy(BaseStrategy):
        def select_etfs(self, df_dict, regime) -> List[Signal]
        def get_position_size(self) -> float
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import pandas as pd

from src.strategy.registry import StrategyMeta


@dataclass
class Signal:
    """策略信号（每个策略输出）"""
    code: str                          # ETF 代码
    action: str                        # 'buy' / 'sell' / 'hold'
    price: float                       # 当前价
    confidence: float = 1.0            # 置信度 [0, 1]
    reason: str = ''                   # 信号原因
    stop_loss: float = 0.0            # 止损价
    take_profit: float = 0.0          # 止盈价
    max_hold_days: int = 15           # 最大持仓天数
    position_size: float = 0.0        # 建议仓位 (0-1)


class BaseStrategy(ABC):
    """策略基类（v3 核心抽象）"""

    # 子类必须定义
    code: str = ''
    name: str = ''
    description: str = ''

    def __init__(self):
        self.meta = StrategyMeta(
            code=self.code,
            name=self.name,
            
        )

    @abstractmethod
    def select_etfs(self, df_dict: Dict[str, pd.DataFrame], regime: str) -> List[Signal]:
        """
        选择 ETF 并产生信号

        Args:
            df_dict: {code: df} 价格数据
            regime: 当前 market_state (trend_up/range_bound/trend_down/reversal_point)
        Returns:
            List[Signal]: 信号列表
        """
        pass

    @abstractmethod
    def get_position_size(self) -> float:
        """
        返回策略的最大仓位比例 (0-1)
        每个策略独立: 例 趋势策略 max=0.3
        """
        pass

    def get_max_hold_days(self) -> int:
        """策略最大持仓天数（独立）"""
        return 15

    def is_applicable(self, regime: str) -> bool:
        """该策略是否适用于指定市态"""
        return regime in self.meta.applicable_regimes

    @property
    def risk_limits(self) -> Dict[str, Any]:
        """策略风控限制"""
        return self.meta.risk_limits
