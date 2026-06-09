"""config 包 - 配置模块

包含：
- etf_pools: ETF 池配置（新版本）
- legacy: 旧版配置（已废弃，保留向后兼容）
"""
from src.config.etf_pools import ETF_POOLS, get_all_codes, get_codes_by_pool
from src.config.legacy import StrategyConfig, run_strategy

# 向后兼容别名
ETF_POOL = get_all_codes()
CORE_POOL = get_codes_by_pool('core')
EXTENDED_POOL = get_codes_by_pool('extended')

__all__ = ['ETF_POOLS', 'ETF_POOL', 'CORE_POOL', 'EXTENDED_POOL', 'StrategyConfig', 'run_strategy', 'get_all_codes', 'get_codes_by_pool']