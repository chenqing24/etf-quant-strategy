"""
配置类模块

包含:
- ScoreConfig: 评分配置
- FactorStrategy: 因子策略配置
- BacktestConfig: 回测配置
- DataConfig: 数据配置
- ExperimentConfig: 实验完整配置
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ScoreConfig:
    """评分配置"""
    threshold: float = 0.6         # 分数阈值
    min_active_factors: int = 2     # 最少有效因子数
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'threshold': self.threshold,
            'min_active_factors': self.min_active_factors
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'ScoreConfig':
        """从字典反序列化"""
        return cls(
            threshold=d.get('threshold', 0.6),
            min_active_factors=d.get('min_active_factors', 2)
        )


@dataclass
class FactorStrategy:
    """因子策略配置"""
    name: str                       # 策略名称
    factors: List[str]              # 因子列表
    weights: Dict[str, float]        # 因子权重
    direction: Dict[str, str]       # 因子方向 (long/short/neutral)
    score_config: ScoreConfig = None # 评分配置
    
    def __post_init__(self):
        if self.score_config is None:
            self.score_config = ScoreConfig()
    
    def get_valid_factors(self) -> List[str]:
        """获取有效因子（方向非neutral）"""
        return [f for f, d in self.direction.items() if d != 'neutral']
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'name': self.name,
            'factors': self.factors,
            'weights': self.weights,
            'direction': self.direction,
            'score_config': self.score_config.to_dict()
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'FactorStrategy':
        """从字典反序列化"""
        score_config = None
        if 'score_config' in d:
            score_config = ScoreConfig.from_dict(d['score_config'])
        
        return cls(
            name=d.get('name', ''),
            factors=d.get('factors', []),
            weights=d.get('weights', {}),
            direction=d.get('direction', {}),
            score_config=score_config
        )


@dataclass
class BacktestConfig:
    """回测配置"""
    stop_loss: float = -0.05        # 止损比例
    stop_profit: float = 0.10      # 止盈比例
    hold_days: int = 5              # 最大持仓天数
    max_positions: int = 2          # 最大持仓数
    commission: float = 0.0003      # 手续费
    slippage: float = 0.001         # 滑点
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'stop_loss': self.stop_loss,
            'stop_profit': self.stop_profit,
            'hold_days': self.hold_days,
            'max_positions': self.max_positions,
            'commission': self.commission,
            'slippage': self.slippage
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'BacktestConfig':
        """从字典反序列化"""
        return cls(
            stop_loss=d.get('stop_loss', -0.05),
            stop_profit=d.get('stop_profit', 0.10),
            hold_days=d.get('hold_days', 5),
            max_positions=d.get('max_positions', 2),
            commission=d.get('commission', 0.0003),
            slippage=d.get('slippage', 0.001)
        )


@dataclass
class DataConfig:
    """数据配置"""
    train_start: str = "2023-01-01"
    train_end: str = "2024-12-31"
    test_start: str = "2025-01-01"
    test_end: str = "2026-05-27"
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'train_start': self.train_start,
            'train_end': self.train_end,
            'test_start': self.test_start,
            'test_end': self.test_end
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'DataConfig':
        """从字典反序列化"""
        return cls(
            train_start=d.get('train_start', '2022-01-01'),
            train_end=d.get('train_end', '2024-12-31'),
            test_start=d.get('test_start', '2025-01-01'),
            test_end=d.get('test_end', '2026-05-27')
        )


@dataclass
class ExperimentConfig:
    """实验完整配置"""
    id: int = 0
    name: str = ""
    version: str = "v0.1.0"
    factor_strategy: FactorStrategy = None
    backtest: BacktestConfig = None
    data: DataConfig = None
    
    def __post_init__(self):
        if self.factor_strategy is None:
            self.factor_strategy = FactorStrategy(
                name="default",
                factors=[],
                weights={},
                direction={}
            )
        if self.backtest is None:
            self.backtest = BacktestConfig()
        if self.data is None:
            self.data = DataConfig()
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'factor_strategy': self.factor_strategy.to_dict(),
            'backtest': self.backtest.to_dict(),
            'data': self.data.to_dict()
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'ExperimentConfig':
        """从字典反序列化"""
        return cls(
            id=d.get('id', 0),
            name=d.get('name', ''),
            version=d.get('version', 'v0.1.0'),
            factor_strategy=FactorStrategy.from_dict(d.get('factor_strategy', {})),
            backtest=BacktestConfig.from_dict(d.get('backtest', {})),
            data=DataConfig.from_dict(d.get('data', {}))
        )
    
    @classmethod
    def from_experiment(cls, exp: Dict) -> 'ExperimentConfig':
        """从实验日志创建"""
        # 从现有的 experiments.json 格式转换
        factor_strategy = FactorStrategy(
            name=exp.get('name', ''),
            factors=exp.get('factors', []),
            weights=exp.get('weights', {}),
            direction=exp.get('factor_direction', {})
        )
        
        backtest_result = exp.get('backtest_result', {})
        backtest = BacktestConfig()
        
        # 从回测结果推断配置
        if backtest_result:
            if 'trade_count' in backtest_result:
                backtest.hold_days = 5  # 默认值
        
        return cls(
            id=exp.get('id', 0),
            name=exp.get('name', ''),
            version='v0.1.0',
            factor_strategy=factor_strategy,
            backtest=backtest,
            data=DataConfig()
        )