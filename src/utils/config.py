#!/usr/bin/env python3
"""配置层"""
from dataclasses import dataclass, field
from typing import Tuple, Set, Optional

# ===== 数据目录常量 =====
DATA_DIR = 'etf_data_live'  # 标准数据目录，所有模块应使用此常量

@dataclass
class StrategyConfig:
    """ETF量化策略配置 - 所有参数可配置，无硬编码"""
    
    # ===== 数据配置 =====
    data_dir: str = 'etf_data_live'          # 数据目录
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
    
    # ===== 行业配置 =====
    enable_industry_limit: bool = False    # 是否启用行业限制
    max_industry_ratio: float = 0.4        # 单行业最大比例 (40%)
    
    # ===== 市场过滤配置 =====
    market_ma: int = 60                     # 市场均线周期
    enable_market_filter: bool = True       # 是否启用市场过滤
    
    # ===== 交易成本配置 =====
    enable_slippage: bool = False           # 是否启用滑点模拟
    slippage_rate: float = 0.001            # 滑点比例 (千分之一)
    
    # ===== 交易成本 =====
    fee_rate: float = 0.0003                # 手续费率
    
    # ===== ETF排除规则 =====
    # 7因子模型基于技术动量，以下ETF不适用：
    # - 红利ETF：走势与基本面/分红高度相关
    # - 低波动/价值ETF：策略驱动，非市场动量
    # - 港股/海外ETF：受汇率、境外市场影响
    # - 证券/金融ETF：强周期，与市场相关性特殊
    exclude_codes: Set[str] = field(default_factory=lambda: {
        # 港股/境外 (汇率+境外市场)
        '159825', '159902', '159915', '159928', '159952', '159997',  # 港股通
        '159920', '159867',  # 恒生ETF
        '513360', '513050',  # 港股ETF
        
        # 红利/分红策略 (510880 红利ETF, 513500 中证红利)
        '510880', '159825', '513880', '512590', '515460', '513500',
        
        # 低波动/价值策略
        '159916', '159934',  # 黄金/低波
        
        # 强周期证券 (波动规律不同)
        '512880', '512170', '512200', '512690', '159815',
        
        # 债券ETF (与股票走势不同)
        '511010', '511880', '511990', '511220', '511210',
        
        # 商品ETF (受商品价格主导)
        '518880', '518800', '159912',
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
    # 交易成本
    enable_slippage: bool = False,
    slippage_rate: float = 0.001,
    # 数据配置
    data_dir: str = 'etf_data_live',
    market_code: str = '510300',
    train_start: str = '2022-01-01',
    train_end: str = '2024-12-31',
    exclude_codes: Optional[Set[str]] = None,
):
    """便捷入口：运行完整策略
    
    所有参数均可传入，无硬编码
    """
    from src.data.loader import DataLoader
    from src.analysis.indicator import Indicator
    from src.core.selector import Selector
    from src.core.market_filter import MarketFilter
    from src.core.backtest import run_backtest
    from pathlib import Path
    
    # 简版模式：设置DataLoader标志
    _simple_mode = getattr(Selector, '_simple_mode', False)
    
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
        enable_slippage=enable_slippage,
        slippage_rate=slippage_rate,
        # 用户未指定时使用默认排除码
        exclude_codes=exclude_codes if exclude_codes is not None else default_config.exclude_codes,
    )
    
    # 加载数据
    loader = DataLoader()
    if _simple_mode:
        loader._simple_mode = True
    
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