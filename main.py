#!/usr/bin/env python3
"""
ETF量化策略 - 主入口

Usage:
    python main.py                           # 默认参数
    python main.py --rebalance 10            # 调仓周期10天
    python main.py --score 6 --rebalance 10  # 自定义参数
"""
import argparse
import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import StrategyConfig
from src.data_loader import DataLoader
from src.indicator import Indicator
from src.selector import Selector
from src.market_filter import MarketFilter
from src.backtest import run_backtest


def main():
    parser = argparse.ArgumentParser(description='ETF量化策略回测')
    parser.add_argument('--test-start', default='2025-05-06', help='测试开始日期')
    parser.add_argument('--test-end', default='2026-05-22', help='测试结束日期')
    parser.add_argument('--rebalance', type=int, default=10, help='调仓周期(天)')
    parser.add_argument('--score', type=int, default=6, help='分数门槛')
    parser.add_argument('--weights', default='50,50', help='仓位权重，如: 50,50')
    parser.add_argument('--data-dir', default='../etf_data_50', help='数据目录')
    
    args = parser.parse_args()
    
    # 解析权重
    weights = tuple(int(w)/100 for w in args.weights.split(','))
    
    # 配置
    config = StrategyConfig(
        rebalance_days=args.rebalance,
        score_threshold=args.score,
        weights=weights,
    )
    
    # 加载数据
    loader = DataLoader()
    data = loader.load(args.data_dir)
    
    if not data:
        print("错误: 无法加载数据")
        sys.exit(1)
    
    # 选ETF
    selector = Selector()
    selected = selector.select_etfs(data, config)
    
    # 计算指标
    etf_data = {code: df for code, df in data.items() if code in selected}
    etf_data = Indicator.calculate_all(etf_data)
    
    # 市场过滤
    if '510300' in etf_data:
        market_filter = MarketFilter(etf_data['510300'], config.market_ma)
    else:
        print("警告: 找不到沪深300数据，跳过市场过滤")
        market_filter = None
    
    # 回测
    print(f"\n{'='*60}")
    print(f"参数: 调仓{args.rebalance}天, 分数>={args.score}, 权重{weights}")
    print(f"测试期: {args.test_start} ~ {args.test_end}")
    print('='*60)
    
    result = run_backtest(etf_data, config, args.test_start, args.test_end, market_filter)
    
    # 输出结果
    print(f"\n回测结果:")
    print(f"  收益率:  {result['return']:+.1f}%")
    print(f"  最大回撤: {result['drawdown']:.1f}%")
    print(f"  胜率:    {result['winrate']:.1f}%")
    print(f"  交易次数: {result['trades']}")
    
    return result


if __name__ == '__main__':
    main()