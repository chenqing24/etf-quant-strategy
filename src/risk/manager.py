"""
风控管理器

功能:
- 入场检查 (check_entry)
- 退出检查 (check_exit)
- 持仓/组合信息管理

版本: 1.0
"""
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, timedelta
import math

from .config_types import RiskConfig
from .errors import PositionLimitError, LossLimitError


# ===== 浮点数比较容差 =====
PRECISION = 1e-9  # 浮点数比较容差


# ===== 数据类型 =====

@dataclass
class Position:
    """持仓信息"""
    code: str                           # ETF代码
    quantity: int                       # 持仓数量
    avg_price: float                    # 平均成本
    current_price: float                # 当前价格
    entry_date: str                     # 入场日期 (YYYY-MM-DD)
    
    @property
    def pnl_pct(self) -> float:
        """盈亏百分比"""
        if self.avg_price == 0:
            return 0
        return (self.current_price - self.avg_price) / self.avg_price
    
    @property
    def hold_days(self) -> int:
        """持仓天数"""
        try:
            entry = datetime.strptime(self.entry_date, '%Y-%m-%d')
            delta = datetime.now() - entry
            return delta.days
        except Exception:
            return 0
    
    @property
    def market_value(self) -> float:
        """市值"""
        return self.quantity * self.current_price
    
    @property
    def cost(self) -> float:
        """成本"""
        return self.quantity * self.avg_price
    
    @property
    def pnl(self) -> float:
        """盈亏金额"""
        return self.market_value - self.cost


@dataclass
class Portfolio:
    """组合信息"""
    positions: List[Position] = field(default_factory=list)
    cash: float = 0                          # 现金
    total_value: float = 0                   # 总价值（持仓市值 + 现金）
    initial_capital: float = 0               # 初始资金（用于计算总亏损）
    
    def __post_init__(self):
        """如果没有提供初始资金，使用 cash 作为初始资金"""
        if self.initial_capital == 0:
            # 估算初始资金 = 现金 + 所有持仓的成本
            self.initial_capital = self.cash + sum(p.cost for p in self.positions)
    
    @property
    def position_count(self) -> int:
        """持仓数量"""
        return len(self.positions)
    
    @property
    def total_pnl_pct(self) -> float:
        """
        总盈亏百分比
        
        计算方式: (当前总价值 - 初始资金) / 初始资金
        - 正数表示盈利
        - 负数表示亏损
        """
        if self.initial_capital == 0:
            return 0
        return (self.total_value - self.initial_capital) / self.initial_capital
    
    @property
    def invested_value(self) -> float:
        """已投资金额（市值）"""
        return sum(p.market_value for p in self.positions)
    
    @property
    def total_cost(self) -> float:
        """总成本"""
        return sum(p.cost for p in self.positions)


@dataclass
class CheckResult:
    """入场检查结果"""
    allowed: bool                          # 是否允许入场
    reason: Optional[str] = None          # 拒绝原因
    code: Optional[str] = None            # 错误码


@dataclass
class ExitSignal:
    """退出信号"""
    reason: str                            # "stop_loss" | "stop_profit" | "hold_days"
    pnl: Optional[float] = None           # 触发时的盈亏百分比
    days: Optional[int] = None            # 触发时的持仓天数


# ===== 风控管理器 =====

class RiskManager:
    """
    风控管理器 - 统一管理所有风控逻辑
    
    功能:
    - 入场检查: 仓位限制、亏损限制
    - 退出检查: 止损、止盈、持仓天数
    
    用法:
        risk = RiskManager(stop_loss=-0.05, stop_profit=0.10)
        
        # 检查是否可以入场
        result = risk.check_entry(portfolio)
        if not result.allowed:
            print(f"拒绝入场: {result.reason}")
        
        # 检查是否需要退出
        signal = risk.check_exit(position, current_price)
        if signal:
            print(f"退出信号: {signal.reason}")
    """
    
    def __init__(
        self,
        stop_loss: float = -0.05,
        stop_profit: float = 0.10,
        max_position: int = 1,
        max_loss: float = -0.15,
        hold_days: int = 5
    ):
        """
        初始化风控管理器
        
        Args:
            stop_loss: 止损比例 (负数，如 -0.05 表示亏损5%时止损)
            stop_profit: 止盈比例 (正数，如 0.10 表示盈利10%时止盈)
            max_position: 最大持仓数
            max_loss: 最大总亏损 (负数，如 -0.15 表示亏损15%时拒绝入场)
            hold_days: 最大持仓天数
        """
        self.stop_loss = stop_loss
        self.stop_profit = stop_profit
        self.max_position = max_position
        self.max_loss = max_loss
        self.hold_days = hold_days
    
    @classmethod
    def from_config(cls, config: RiskConfig) -> 'RiskManager':
        """
        从配置创建风控管理器
        
        Args:
            config: RiskConfig配置对象
            
        Returns:
            RiskManager实例
        """
        return cls(
            stop_loss=config.stop_loss,
            stop_profit=config.stop_profit,
            max_position=config.max_position,
            max_loss=config.max_loss,
            hold_days=config.hold_days
        )
    
    def check_entry(self, portfolio: Portfolio) -> CheckResult:
        """
        检查是否可以入场
        
        规则:
        1. 仓位限制: 已有持仓 < max_position
        2. 亏损限制: 总亏损 > max_loss
        
        Args:
            portfolio: 组合信息
            
        Returns:
            CheckResult:
                - allowed=True: 允许入场
                - allowed=False: 拒绝入场，包含reason和code
        """
        # 规则1: 仓位限制
        if portfolio.position_count >= self.max_position:
            return CheckResult(
                allowed=False,
                reason="max_position",
                code="E2001-01"
            )
        
        # 规则2: 亏损限制
        if portfolio.total_pnl_pct < self.max_loss:
            return CheckResult(
                allowed=False,
                reason="max_loss",
                code="E2001-02"
            )
        
        return CheckResult(allowed=True)
    
    def check_exit(self, position: Position, current_price: float) -> Optional[ExitSignal]:
        """
        检查是否需要退出
        
        规则:
        1. 止损: 盈亏 <= stop_loss
        2. 止盈: 盈亏 >= stop_profit
        3. 持仓到期: 持仓天数 >= hold_days
        
        Args:
            position: 持仓信息
            current_price: 当前价格
            
        Returns:
            ExitSignal: 需要退出，包含退出原因和触发时的盈亏
            None: 不需要退出
        """
        # 更新持仓价格
        position.current_price = current_price
        
        # 计算当前盈亏百分比
        pnl = position.pnl_pct
        
        # 规则1: 止损 (使用容差避免浮点数精度问题)
        if pnl <= self.stop_loss + PRECISION:
            return ExitSignal(
                reason="stop_loss",
                pnl=pnl
            )
        
        # 规则2: 止盈 (使用容差避免浮点数精度问题)
        if pnl >= self.stop_profit - PRECISION:
            return ExitSignal(
                reason="stop_profit",
                pnl=pnl
            )
        
        # 规则3: 持仓天数
        if position.hold_days >= self.hold_days:
            return ExitSignal(
                reason="hold_days",
                days=position.hold_days
            )
        
        return None
    
    def get_status(self, portfolio: Portfolio) -> dict:
        """
        获取风控状态摘要
        
        Args:
            portfolio: 组合信息
            
        Returns:
            dict: 风控状态信息
        """
        entry_result = self.check_entry(portfolio)
        
        return {
            "can_entry": entry_result.allowed,
            "entry_reason": entry_result.reason,
            "position_count": portfolio.position_count,
            "max_position": self.max_position,
            "total_pnl_pct": portfolio.total_pnl_pct,
            "max_loss": self.max_loss
        }