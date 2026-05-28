"""
配置加载器

功能:
- 从YAML文件加载策略配置
- 配置缓存（避免重复读取）
- 版本验证
- 错误处理

错误码:
- E1001: 配置文件不存在
- E1002: 配置文件格式错误
- E1003: 配置版本不兼容
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
import yaml

from .config_types import (
    StrategyConfig,
    FactorConfig,
    RiskConfig,
    ExecutionConfig,
    DataConfig,
    SUPPORTED_VERSIONS
)


# ===== 错误类 =====
class ConfigError(Exception):
    """配置错误基类"""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigNotFoundError(ConfigError):
    """配置文件不存在 (E1001)"""
    def __init__(self, path: str):
        super().__init__(
            f"配置文件不存在: {path}",
            "E1001"
        )


class ConfigFormatError(ConfigError):
    """配置文件格式错误 (E1002)"""
    def __init__(self, path: str, reason: str):
        super().__init__(
            f"配置文件格式错误: {path}, 原因: {reason}",
            "E1002"
        )


class ConfigVersionError(ConfigError):
    """配置版本不兼容 (E1003)"""
    def __init__(self, version: str, supported: str):
        super().__init__(
            f"配置版本 {version} 不支持, 支持版本: {supported}",
            "E1003"
        )


# ===== 配置加载器 =====
class ConfigLoader:
    """
    策略配置加载器
    
    特性:
    - 单例模式: 全局只有一个实例
    - 配置缓存: 避免重复读取文件
    - 版本验证: 确保配置兼容
    - 默认配置: 支持加载默认配置
    
    用法:
        loader = ConfigLoader.get_instance()
        config = loader.load("config/strategies/exp50.yaml")
        strategies = loader.list_strategies()
    """
    
    _instance: Optional['ConfigLoader'] = None
    _cache: Dict[str, StrategyConfig] = {}
    
    def __init__(self):
        """初始化配置加载器"""
        self.strategy_dir = Path('config/strategies')
        self.default_config_path = self.strategy_dir / 'default.yaml'
    
    @classmethod
    def get_instance(cls) -> 'ConfigLoader':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def clear_cache(cls):
        """清除配置缓存"""
        cls._cache.clear()
    
    def load(self, path: str) -> StrategyConfig:
        """
        加载配置文件
        
        Args:
            path: 配置文件路径 (可以是相对路径或绝对路径)
            
        Returns:
            StrategyConfig: 策略配置对象
            
        Raises:
            ConfigNotFoundError: 配置文件不存在 (E1001)
            ConfigFormatError: 配置文件格式错误 (E1002)
            ConfigVersionError: 配置版本不兼容 (E1003)
            
        用法:
            config = loader.load("config/strategies/exp50.yaml")
        """
        # 检查缓存
        if path in self._cache:
            return self._cache[path]
        
        # 解析路径
        config_path = self._resolve_path(path)
        
        # 检查文件存在
        if not config_path.exists():
            raise ConfigNotFoundError(path)
        
        # 加载YAML
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigFormatError(path, str(e))
        except Exception as e:
            raise ConfigFormatError(path, str(e))
        
        # 验证版本
        version = data.get('version', '1.0')
        if version not in SUPPORTED_VERSIONS:
            raise ConfigVersionError(version, ', '.join(SUPPORTED_VERSIONS))
        
        # 构建配置对象
        config = self._build_config(data)
        
        # 缓存
        self._cache[path] = config
        
        return config
    
    def load_default(self) -> StrategyConfig:
        """
        加载默认配置
        
        Returns:
            StrategyConfig: 默认配置
            
        Raises:
            ConfigNotFoundError: 默认配置文件不存在
        """
        default_path = str(self.default_config_path)
        
        # 如果默认配置存在，尝试加载
        if self.default_config_path.exists():
            return self.load(default_path)
        
        # 否则返回内存中的默认配置
        return StrategyConfig(
            version='1.0',
            name='default',
            factors=FactorConfig(
                enabled=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
                weights={'ADX': 0.4, 'BB_percent': 0.3, 'SAR_trend': 0.2, 'OBV_diff': 0.1},
                direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'long'}
            ),
            risk=RiskConfig(
                stop_loss=-0.05,
                stop_profit=0.10,
                max_position=1,
                max_loss=-0.15,
                hold_days=5
            ),
            execution=ExecutionConfig(
                min_score=0.6,
                top_n=30,
                hold_count=2
            ),
            data=DataConfig(
                market_code='510300',
                train_start='2022-01-01',
                train_end='2024-12-31'
            )
        )
    
    @staticmethod
    def list_strategies() -> List[str]:
        """
        列出所有可用策略
        
        Returns:
            List[str]: 策略名称列表
            
        用法:
            strategies = ConfigLoader.list_strategies()
            # ['exp50', 'exp36', 'default']
        """
        strategy_dir = Path('config/strategies')
        if not strategy_dir.exists():
            return []
        
        strategies = []
        for f in strategy_dir.glob('*.yaml'):
            strategies.append(f.stem)
        
        return sorted(strategies)
    
    def _resolve_path(self, path: str) -> Path:
        """解析配置路径"""
        p = Path(path)
        
        # 如果是绝对路径，直接返回
        if p.is_absolute():
            return p
        
        # 如果是相对路径，尝试多种方式
        # 1. 相对于当前工作目录
        cwd_path = Path.cwd() / p
        if cwd_path.exists():
            return cwd_path
        
        # 2. 相对于项目根目录 (etf_strategy/)
        project_root = Path(__file__).parent.parent.parent
        project_path = project_root / p
        if project_path.exists():
            return project_path
        
        # 3. 返回原始路径（会在调用处报错）
        return p
    
    def _build_config(self, data: dict) -> StrategyConfig:
        """从字典数据构建配置对象"""
        return StrategyConfig.from_dict(data)
    
    def create_sample_configs(self):
        """创建示例配置文件（用于初始化）"""
        self.strategy_dir.mkdir(parents=True, exist_ok=True)
        
        default_config = {
            'version': '1.0',
            'name': 'default',
            'factors': {
                'enabled': ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
                'weights': {
                    'ADX': 0.4,
                    'BB_percent': 0.3,
                    'SAR_trend': 0.2,
                    'OBV_diff': 0.1
                },
                'direction': {
                    'ADX': 'long',
                    'BB_percent': 'long',
                    'SAR_trend': 'long',
                    'OBV_diff': 'long'
                }
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
        
        default_path = self.strategy_dir / 'default.yaml'
        if not default_path.exists():
            with open(default_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)


# ===== 便捷函数 =====
def load_strategy(path: str) -> StrategyConfig:
    """便捷函数: 加载策略配置"""
    return ConfigLoader.get_instance().load(path)


def load_default_strategy() -> StrategyConfig:
    """便捷函数: 加载默认策略配置"""
    return ConfigLoader.get_instance().load_default()


def list_available_strategies() -> List[str]:
    """便捷函数: 列出可用策略"""
    return ConfigLoader.list_strategies()