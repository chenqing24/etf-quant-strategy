"""
风控配置数据类型

设计原则:
- 类型安全: 使用@dataclass确保类型检查
- 默认值: 所有字段都有合理默认值

版本: 1.0
"""
from dataclasses import dataclass


@dataclass
class RiskConfig:
    """
    风控配置
    
    包含风控的所有参数:
    - 止损/止盈比例
    - 仓位限制
    - 持仓时间限制
    """
    stop_loss: float = -0.05      # 止损比例 (-5%)
    stop_profit: float = 0.10    # 止盈比例 (+10%)
    max_position: int = 1       # 最大持仓数
    max_loss: float = -0.15     # 最大总亏损 (-15%)
    hold_days: int = 5          # 最大持仓天数
    
    def __post_init__(self):
        """验证参数合法性"""
        if self.stop_loss > 0:
            raise ValueError("止损比例必须为负数")
        if self.stop_profit < 0:
            raise ValueError("止盈比例必须为正数")
        if self.stop_loss >= self.stop_profit:
            raise ValueError("止损比例必须小于止盈比例（绝对值比较）")
        if self.max_position < 1:
            raise ValueError("最大持仓数必须>=1")
        if self.hold_days < 1:
            raise ValueError("最大持仓天数必须>=1")