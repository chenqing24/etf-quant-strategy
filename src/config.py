#!/usr/bin/env python3
"""配置层"""
from dataclasses import dataclass, field
from typing import Tuple, Set, Optional

@dataclass
class StrategyConfig:
    """ETF量化策略配置 - 所有参数可配置，无硬编码"""
    
    # ===== 数据配置 =====
    data_dir: str = 'etf_data_50'          # 数据目录
    market_code: str = '510300'             # 市场基准代码（沪深300）
    
    # ===== 训练期配置 =====
    train_start: str = '2022-01-01'         # 训练开始日期
    train_end: str = '2024-12-31'           # 训练结束日期
    
    # ===== 选股配置 =====
    score_threshold: int = 6                # 选股分数门槛
    top_n: int = 30                         # 选出的ETF数量
    
    # ===== 持仓配置 =====
    hold_count: int = 2                     # 持仓数量
    weights: Tuple[float, float] = (0.5, 0.5)  # 仓位权重
    
    # ===== 调仓配置 =====
    rebalance_days: int = 10                # 调仓周期(天)
    
    # ===== 风控配置 =====
    stop_loss: float = -0.10                # 止损比例
    stop_gain: float = 0.15                 # 固定止盈比例
    max_hold_days: int = 15                 # 最大持仓天数
    
    # ===== 移动止盈配置 =====
    enable_trailing_stop: bool = False      # 是否启用移动止盈
    trailing_threshold: float = 0.10        # 启动移动止盈的盈利门槛 (10%)
    trailing_stop: float = 0.08             # 移动止盈回撤比例 (8%)
    
    # ===== 市场过滤配置 =====
    market_ma: int = 60                     # 市场均线周期
    enable_market_filter: bool = True       # 是否启用市场过滤
    
    # ===== 交易成本 =====
    fee_rate: float = 0.0003                # 手续费率
    
    # ===== ETF排除规则 =====
    exclude_codes: Set[str] = field(default_factory=lambda: {
        '159825', '159902', '159915', '159928', '159952',  # 港股通
        '513360', '515050', '513080',  # 红利/养老
        '512880', '512170', '512200',  # 证券
    })


def run_strategy(
    test_start: str,
    test_end: str,
    # 选股参数
    score_threshold: int = 6,
    top_n: int = 30,
    # 持仓参数
    hold_count: int = 2,
    weights: Tuple[float, float] = (0.5, 0.5),
    # 调仓参数
    rebalance_days: int = 10,
    # 风控参数
    stop_loss: float = -0.10,
    stop_gain: float = 0.15,
    max_hold_days: int = 15,
    # 移动止盈参数
    enable_trailing_stop: bool = False,
    trailing_threshold: float = 0.10,
    trailing_stop: float = 0.08,
    # 市场过滤
    market_ma: int = 60,
    enable_market_filter: bool = True,
    # 数据配置
    data_dir: str = 'etf_data_50',
    market_code: str = '510300',
    train_start: str = '2022-01-01',
    train_end: str = '2024-12-31',
    exclude_codes: Optional[Set[str]] = None,
):
    """便捷入口：运行完整策略
    
    所有参数均可传入，无硬编码
    """
    from .data_loader import DataLoader
    from .indicator import Indicator
    from .selector import Selector
    from .market_filter import MarketFilter
    from .backtest import run_backtest
    from pathlib import Path
    
    # 配置 - 使用默认配置对象
    default_config = StrategyConfig()
    config = StrategyConfig(
        data_dir=data_dir,
        market_code=market_code,
        train_start=train_start,
        train_end=train_end,
        score_threshold=score_threshold,
        top_n=top_n,
        hold_count=hold_count,
        weights=weights,
        rebalance_days=rebalance_days,
        stop_loss=stop_loss,
        stop_gain=stop_gain,
        max_hold_days=max_hold_days,
        enable_trailing_stop=enable_trailing_stop,
        trailing_threshold=trailing_threshold,
        trailing_stop=trailing_stop,
        market_ma=market_ma,
        enable_market_filter=enable_market_filter,
        # 用户未指定时使用默认排除码
        exclude_codes=exclude_codes if exclude_codes is not None else default_config.exclude_codes,
    )
    
    # 加载数据
    loader = DataLoader()
    
    # 支持绝对路径和相对路径
    dd = Path(data_dir)
    if not dd.exists():
        dd = Path.cwd() / data_dir
    data = loader.load(str(dd))
    
    if not data:
        raise ValueError(f"无法加载数据: {data_dir}")
    
    # 选ETF - Top N可配置
    selector = Selector()
    selected = selector.select_etfs(data, config)
    
    # 计算指标
    etf_data = {code: df for code, df in data.items() if code in selected}
    etf_data = Indicator.calculate_all(etf_data)
    
    # 市场过滤 - 使用配置的市场代码
    market_filter = None
    if enable_market_filter and market_code in etf_data:
        market_filter = MarketFilter(etf_data[market_code], config.market_ma)
    
    # 回测
    result = run_backtest(etf_data, config, test_start, test_end, market_filter)
    
    return result


__all__ = ['StrategyConfig', 'run_strategy']