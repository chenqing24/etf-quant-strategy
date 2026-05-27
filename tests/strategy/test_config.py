"""
配置类测试

测试配置类的序列化和反序列化
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.strategy.config import (
    ScoreConfig,
    FactorStrategy,
    BacktestConfig,
    DataConfig,
    ExperimentConfig
)


class TestScoreConfig:
    """评分配置测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = ScoreConfig()
        assert config.threshold == 0.6
        assert config.min_active_factors == 2
    
    def test_custom_values(self):
        """测试自定义值"""
        config = ScoreConfig(threshold=0.55, min_active_factors=3)
        assert config.threshold == 0.55
        assert config.min_active_factors == 3
    
    def test_to_dict(self):
        """测试序列化"""
        config = ScoreConfig(threshold=0.7, min_active_factors=1)
        d = config.to_dict()
        
        assert d['threshold'] == 0.7
        assert d['min_active_factors'] == 1
    
    def test_from_dict(self):
        """测试反序列化"""
        d = {'threshold': 0.8, 'min_active_factors': 2}
        config = ScoreConfig.from_dict(d)
        
        assert config.threshold == 0.8
        assert config.min_active_factors == 2


class TestFactorStrategy:
    """因子策略配置测试"""
    
    def test_default_values(self):
        """测试默认值"""
        strategy = FactorStrategy(
            name="test",
            factors=["ADX", "BB"],
            weights={"ADX": 0.5, "BB": 0.5},
            direction={"ADX": "long", "BB": "neutral"}
        )
        
        assert strategy.name == "test"
        assert strategy.factors == ["ADX", "BB"]
        assert strategy.weights == {"ADX": 0.5, "BB": 0.5}
        assert strategy.direction == {"ADX": "long", "BB": "neutral"}
    
    def test_get_valid_factors(self):
        """测试获取有效因子"""
        strategy = FactorStrategy(
            name="test",
            factors=["ADX", "BB", "DIF"],
            weights={"ADX": 0.5, "BB": 0.3, "DIF": 0.2},
            direction={"ADX": "long", "BB": "neutral", "DIF": "short"}
        )
        
        valid = strategy.get_valid_factors()
        assert "ADX" in valid
        assert "DIF" in valid
        assert "BB" not in valid
    
    def test_to_dict(self):
        """测试序列化"""
        strategy = FactorStrategy(
            name="test",
            factors=["ADX"],
            weights={"ADX": 1.0},
            direction={"ADX": "long"},
            score_config=ScoreConfig(threshold=0.7)
        )
        
        d = strategy.to_dict()
        
        assert d['name'] == "test"
        assert d['factors'] == ["ADX"]
        assert d['weights'] == {"ADX": 1.0}
        assert d['direction'] == {"ADX": "long"}
        assert d['score_config']['threshold'] == 0.7
    
    def test_from_dict(self):
        """测试反序列化"""
        d = {
            'name': 'test2',
            'factors': ['RSI', 'MACD'],
            'weights': {'RSI': 0.6, 'MACD': 0.4},
            'direction': {'RSI': 'long', 'MACD': 'short'},
            'score_config': {'threshold': 0.5, 'min_active_factors': 1}
        }
        
        strategy = FactorStrategy.from_dict(d)
        
        assert strategy.name == "test2"
        assert len(strategy.factors) == 2
        assert strategy.score_config.threshold == 0.5


class TestBacktestConfig:
    """回测配置测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = BacktestConfig()
        
        assert config.stop_loss == -0.05
        assert config.stop_profit == 0.10
        assert config.hold_days == 5
        assert config.max_positions == 2
        assert config.commission == 0.0003
        assert config.slippage == 0.001
    
    def test_custom_values(self):
        """测试自定义值"""
        config = BacktestConfig(
            stop_loss=-0.03,
            stop_profit=0.08,
            hold_days=10,
            max_positions=3
        )
        
        assert config.stop_loss == -0.03
        assert config.stop_profit == 0.08
        assert config.hold_days == 10
        assert config.max_positions == 3


class TestDataConfig:
    """数据配置测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = DataConfig()
        
        assert config.train_start == "2024-11-01"
        assert config.train_end == "2025-06-30"
        assert config.test_start == "2025-07-01"
        assert config.test_end == "2025-12-31"
    
    def test_custom_values(self):
        """测试自定义值"""
        config = DataConfig(
            train_start="2023-01-01",
            test_start="2026-01-01"
        )
        
        assert config.train_start == "2023-01-01"
        assert config.test_start == "2026-01-01"


class TestExperimentConfig:
    """实验配置测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = ExperimentConfig(name="test")
        
        assert config.id == 0
        assert config.name == "test"
        assert config.version == "v0.1.0"
        assert isinstance(config.factor_strategy, FactorStrategy)
        assert isinstance(config.backtest, BacktestConfig)
        assert isinstance(config.data, DataConfig)
    
    def test_to_dict(self):
        """测试序列化"""
        config = ExperimentConfig(
            id=1,
            name="test",
            factor_strategy=FactorStrategy(
                name="test",
                factors=["ADX"],
                weights={"ADX": 1.0},
                direction={"ADX": "long"}
            ),
            backtest=BacktestConfig(stop_loss=-0.03),
            data=DataConfig()
        )
        
        d = config.to_dict()
        
        assert d['id'] == 1
        assert d['name'] == "test"
        assert d['factor_strategy']['weights'] == {"ADX": 1.0}
        assert d['backtest']['stop_loss'] == -0.03
    
    def test_from_dict(self):
        """测试反序列化"""
        d = {
            'id': 5,
            'name': 'exp5',
            'factor_strategy': {
                'name': 'ADX优先',
                'factors': ['ADX', 'BB'],
                'weights': {'ADX': 0.5, 'BB': 0.5},
                'direction': {'ADX': 'long', 'BB': 'long'}
            },
            'backtest': {
                'stop_loss': -0.02,
                'stop_profit': 0.05
            },
            'data': {}
        }
        
        config = ExperimentConfig.from_dict(d)
        
        assert config.id == 5
        assert config.name == "exp5"
        assert config.factor_strategy.weights == {'ADX': 0.5, 'BB': 0.5}
        assert config.backtest.stop_loss == -0.02


if __name__ == "__main__":
    pytest.main([__file__, "-v"])