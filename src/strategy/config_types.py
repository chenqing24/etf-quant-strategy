"""
策略配置数据类型定义

设计原则:
- 类型安全: 使用@dataclass确保类型检查
- 版本控制: 支持配置版本验证
- 默认值: 所有字段都有合理默认值
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ===== 版本常量 =====
SUPPORTED_VERSIONS = ['1.0']
CURRENT_VERSION = '1.0'


@dataclass
class FactorConfig:
    """因子配置"""
    enabled: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)
    direction: Dict[str, str] = field(default_factory=dict)
    
    def get_weight(self, factor: str) -> float:
        """获取因子权重，默认0"""
        return self.weights.get(factor, 0)
    
    def get_direction(self, factor: str) -> str:
        """获取因子方向，默认'long'"""
        return self.direction.get(factor, 'long')


@dataclass
class RiskConfig:
    """风控配置"""
    stop_loss: float = -0.05      # 止损比例
    stop_profit: float = 0.10     # 止盈比例
    max_position: int = 1         # 最大持仓数
    max_loss: float = -0.15       # 最大总亏损
    hold_days: int = 5            # 最大持仓天数


@dataclass
class ExecutionConfig:
    """执行配置"""
    min_score: float = 0.6         # 最小分数
    top_n: int = 30               # 候选ETF数量
    hold_count: int = 2           # 持仓数量


@dataclass
class DataConfig:
    """数据配置"""
    market_code: str = '510300'   # 市场基准代码
    train_start: str = '2022-01-01'  # 训练开始日期
    train_end: str = '2024-12-31'    # 训练结束日期


@dataclass
class StrategyConfig:
    """
    策略配置 - 顶层配置对象
    
    包含策略的所有配置信息:
    - 版本信息
    - 策略名称
    - 因子配置
    - 风控配置
    - 执行配置
    - 数据配置
    """
    version: str = CURRENT_VERSION
    name: str = 'default'
    factors: FactorConfig = field(default_factory=FactorConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    data: DataConfig = field(default_factory=DataConfig)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StrategyConfig':
        """从字典创建配置对象"""
        return cls(
            version=data.get('version', CURRENT_VERSION),
            name=data.get('name', 'default'),
            factors=FactorConfig(**data.get('factors', {})),
            risk=RiskConfig(**data.get('risk', {})),
            execution=ExecutionConfig(**data.get('execution', {})),
            data=DataConfig(**data.get('data', {}))
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'version': self.version,
            'name': self.name,
            'factors': {
                'enabled': self.factors.enabled,
                'weights': self.factors.weights,
                'direction': self.factors.direction
            },
            'risk': {
                'stop_loss': self.risk.stop_loss,
                'stop_profit': self.risk.stop_profit,
                'max_position': self.risk.max_position,
                'max_loss': self.risk.max_loss,
                'hold_days': self.risk.hold_days
            },
            'execution': {
                'min_score': self.execution.min_score,
                'top_n': self.execution.top_n,
                'hold_count': self.execution.hold_count
            },
            'data': {
                'market_code': self.data.market_code,
                'train_start': self.data.train_start,
                'train_end': self.data.train_end
            }
        }
    
    @staticmethod
    def validate_version(version: str) -> bool:
        """验证版本是否支持"""
        return version in SUPPORTED_VERSIONS