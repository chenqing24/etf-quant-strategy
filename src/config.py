#!/usr/bin/env python3
"""配置层"""
from dataclasses import dataclass, field
from typing import Tuple

@dataclass
class StrategyConfig:
    """ETF量化策略配置"""
    
    # 训练期
    train_start: str = '2022-01-01'
    train_end: str = '2024-12-31'
    
    # 选股
    score_threshold: int = 6
    
    # 持仓
    hold_count: int = 2
    weights: Tuple[float, float] = (0.5, 0.5)
    
    # 调仓
    rebalance_days: int = 10
    
    # 风控
    stop_loss: float = -0.10
    stop_gain: float = 0.15
    max_hold_days: int = 15
    
    # 市场过滤
    market_ma: int = 60
    
    # 手续费
    fee_rate: float = 0.0003
    
    # 排除代码
    exclude_codes: set = field(default_factory=lambda: {
        '159825', '159902', '159915', '159928', '159952',  # 港股通
        '513360', '515050', '513080',  # 红利/养老
        '512880', '512170', '512200',  # 证券
    })


def run_strategy(test_start: str, test_end: str, 
                 rebalance_days: int = 10,
                 score_threshold: int = 6,
                 weights: Tuple[float, float] = (0.5, 0.5)):
    """便捷入口：运行完整策略"""
    from .data_loader import DataLoader
    from .indicator import Indicator
    from .selector import Selector
    from .market_filter import MarketFilter
    from .backtest import run_backtest
    from pathlib import Path
    
    # 加载数据
    data_dir = Path(__file__).parent.parent / 'data' / 'etf_data_50'
    loader = DataLoader()
    data = loader.load(str(data_dir) if data_dir.exists() else 'etf_data_50')
    
    # 配置
    config = StrategyConfig(
        rebalance_days=rebalance_days,
        score_threshold=score_threshold,
        weights=weights,
    )
    
    # 选ETF
    selector = Selector()
    selected = selector.select_etfs(data, config)
    
    # 计算指标
    data = Indicator.calculate_all({code: df for code, df in data.items() if code in selected})
    
    # 市场过滤
    if '510300' in data:
        market_filter = MarketFilter(data['510300'], config.market_ma)
    else:
        market_filter = None
    
    # 回测
    result = run_backtest(data, config, test_start, test_end, market_filter)
    
    return result


__all__ = ['StrategyConfig', 'run_strategy']