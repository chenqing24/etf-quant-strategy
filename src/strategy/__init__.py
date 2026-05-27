"""
策略执行框架

包含:
- config: 配置类
- scorer: 因子评分器
- executor: 持仓执行器
- metrics: 绩效指标计算
- engine: 统一执行引擎
"""
from src.strategy.config import (
    ScoreConfig,
    FactorStrategy,
    BacktestConfig,
    DataConfig,
    ExperimentConfig
)
from src.strategy.scorer import FactorScorer
from src.strategy.executor import PositionExecutor
from src.strategy.metrics import BacktestResult, MetricsCalculator

__all__ = [
    'ScoreConfig',
    'FactorStrategy',
    'BacktestConfig',
    'DataConfig',
    'ExperimentConfig',
    'FactorScorer',
    'PositionExecutor',
    'BacktestResult',
    'MetricsCalculator'
]