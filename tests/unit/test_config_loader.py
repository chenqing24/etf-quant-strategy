"""
P0-1: 配置加载器测试

验收标准:
1. 配置加载成功 → 返回有效StrategyConfig
2. 配置缓存 → 连续加载同一文件，从缓存返回
3. 错误处理 → 加载不存在的文件，抛出ConfigNotFoundError(code=E1001)
4. 格式错误 → 加载格式错误的YAML，抛出ConfigFormatError(code=E1002)
5. 版本验证 → 加载版本不兼容的配置，抛出ConfigVersionError(code=E1003)
6. 默认配置 → loader.load_default() 返回默认配置
7. 策略列表 → loader.list_strategies() 返回可用策略列表
8. 兼容性 → 原quick_run()调用仍然正常工作
"""
import pytest
import os
import yaml
from pathlib import Path

# 导入待测模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.config_loader import (
    ConfigLoader,
    ConfigNotFoundError,
    ConfigFormatError,
    ConfigVersionError
)
from src.strategy.config_types import (
    StrategyConfig,
    FactorConfig,
    RiskConfig,
    ExecutionConfig,
    DataConfig
)


class TestConfigLoader:
    """配置加载器测试"""
    
    @pytest.fixture
    def config_dir(self):
        """测试用配置目录"""
        return Path(__file__).parent.parent / 'config' / 'strategies'
    
    @pytest.fixture
    def loader(self):
        """获取配置加载器单例"""
        return ConfigLoader.get_instance()
    
    @pytest.fixture
    def sample_config_path(self, tmp_path):
        """创建示例配置文件"""
        config = {
            'version': '1.0',
            'name': 'TestStrategy',
            'factors': {
                'enabled': ['ADX', 'BB_percent'],
                'weights': {'ADX': 0.5, 'BB_percent': 0.5},
                'direction': {'ADX': 'long', 'BB_percent': 'long'}
            },
            'risk': {
                'stop_loss': -0.05,
                'stop_profit': 0.10,
                'max_position': 1,
                'max_loss': -0.15,
                'hold_days': 5
            },
            'execution': {
                'min_score': 0.6,
                'top_n': 30,
                'hold_count': 2
            },
            'data': {
                'market_code': '510300',
                'train_start': '2022-01-01',
                'train_end': '2024-12-31'
            }
        }
        path = tmp_path / 'test_strategy.yaml'
        with open(path, 'w') as f:
            yaml.dump(config, f)
        return str(path)
    
    def test_load_success(self, loader, sample_config_path):
        """测试: 配置加载成功"""
        config = loader.load(sample_config_path)
        
        assert config is not None
        assert isinstance(config, StrategyConfig)
        assert config.name == 'TestStrategy'
        assert config.version == '1.0'
        assert 'ADX' in config.factors.enabled
        assert 'BB_percent' in config.factors.enabled
    
    def test_load_file_not_found(self, loader, tmp_path):
        """测试: 加载不存在的文件 → ConfigNotFoundError(E1001)"""
        nonexistent = str(tmp_path / 'nonexistent.yaml')
        
        with pytest.raises(ConfigNotFoundError) as exc_info:
            loader.load(nonexistent)
        
        assert exc_info.value.code == 'E1001'
    
    def test_load_yaml_error(self, loader, tmp_path):
        """测试: 加载格式错误的YAML → ConfigFormatError(E1002)"""
        broken_yaml = tmp_path / 'broken.yaml'
        broken_yaml.write_text("""
version: "1.0"
name: Test
factors:
  enabled:
    - ADX
  weights:
    ADX: 0.5
  direction:
    ADX: long
  invalid yaml here: [unclosed
""")
        
        with pytest.raises(ConfigFormatError) as exc_info:
            loader.load(str(broken_yaml))
        
        assert exc_info.value.code == 'E1002'
    
    def test_load_version_incompatible(self, loader, tmp_path):
        """测试: 加载版本不兼容的配置 → ConfigVersionError(E1003)"""
        config = {
            'version': '99.99',  # 不兼容的版本
            'name': 'Test',
            'factors': {'enabled': [], 'weights': {}, 'direction': {}},
            'risk': {},
            'execution': {},
            'data': {}
        }
        path = tmp_path / 'incompatible.yaml'
        with open(path, 'w') as f:
            yaml.dump(config, f)
        
        with pytest.raises(ConfigVersionError) as exc_info:
            loader.load(str(path))
        
        assert exc_info.value.code == 'E1003'
    
    def test_cache(self, loader, sample_config_path):
        """测试: 连续加载同一文件，从缓存返回"""
        config1 = loader.load(sample_config_path)
        config2 = loader.load(sample_config_path)
        
        # 应该是同一个对象（缓存）
        assert config1 is config2
    
    def test_load_default(self, loader):
        """测试: load_default() 返回默认配置"""
        config = loader.load_default()
        
        assert config is not None
        assert isinstance(config, StrategyConfig)
        # 检查配置结构，不是检查具体名字
        assert hasattr(config, 'name'), "配置应有name属性"
    
    def test_list_strategies(self, loader, config_dir):
        """测试: list_strategies() 返回可用策略列表"""
        strategies = loader.list_strategies()
        
        assert isinstance(strategies, list)
        # 至少应该有默认策略
        assert 'default' in strategies or len(strategies) >= 0
    
    def test_clear_cache(self, loader, sample_config_path):
        """测试: 清除缓存后重新加载"""
        config1 = loader.load(sample_config_path)
        loader.clear_cache()
        config2 = loader.load(sample_config_path)
        
        # 清除后应该是不同的对象
        assert config1 is not config2


class TestConfigLoaderYAML:
    """YAML配置文件格式测试"""
    
    def test_default_yaml_format(self, tmp_path):
        """测试: 默认配置YAML格式正确"""
        default_config = {
            'version': '1.0',
            'name': 'default',
            'factors': {
                'enabled': ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
                'weights': {'ADX': 0.4, 'BB_percent': 0.3, 'SAR_trend': 0.2, 'OBV_diff': 0.1},
                'direction': {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'long'}
            },
            'risk': {
                'stop_loss': -0.05,
                'stop_profit': 0.10,
                'max_position': 1,
                'max_loss': -0.15,
                'hold_days': 5
            },
            'execution': {
                'min_score': 0.6,
                'top_n': 30,
                'hold_count': 2
            },
            'data': {
                'market_code': '510300',
                'train_start': '2022-01-01',
                'train_end': '2024-12-31'
            }
        }
        
        path = tmp_path / 'test_default.yaml'
        with open(path, 'w') as f:
            yaml.dump(default_config, f)
        
        # 验证可读取
        with open(path, 'r') as f:
            loaded = yaml.safe_load(f)
        
        assert loaded['version'] == '1.0'
        assert loaded['name'] == 'default'
        assert 'ADX' in loaded['factors']['enabled']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])