#!/usr/bin/env python3
"""
ETF量化策略 - 主入口

Usage:
    python main.py
    
    # 自定义参数
    python main.py --rebalance 10 --score 6
    python main.py --rebalance 10 --score 6 --market-code 510300
    python main.py --train-start 2023-01-01 --train-end 2024-12-31
    
    # 自定义排除ETF
    python main.py --exclude 159825,513360
"""
import argparse
import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import StrategyConfig, run_strategy


def parse_args():
    parser = argparse.ArgumentParser(description='ETF量化策略回测')
    
    # 数据配置
    parser.add_argument('--data-dir', default='../etf_data_50', help='数据目录')
    parser.add_argument('--market-code', default='510300', help='市场基准代码(默认沪深300)')
    
    # 训练期
    parser.add_argument('--train-start', default='2022-01-01', help='训练开始日期')
    parser.add_argument('--train-end', default='2024-12-31', help='训练结束日期')
    
    # 测试期
    parser.add_argument('--test-start', default='2025-05-06', help='测试开始日期')
    parser.add_argument('--test-end', default='2026-05-22', help='测试结束日期')
    
    # 选股
    parser.add_argument('--top-n', type=int, default=30, help='选出的ETF数量')
    parser.add_argument('--score', type=int, default=6, help='分数门槛')
    parser.add_argument('--exclude', default='', help='排除的ETF代码,逗号分隔')
    
    # 持仓
    parser.add_argument('--hold-count', type=int, default=2, help='持仓数量')
    parser.add_argument('--weights', default='50,50', help='仓位权重,如: 50,50')
    
    # 调仓
    parser.add_argument('--rebalance', type=int, default=10, help='调仓周期(天)')
    
    # 风控
    parser.add_argument('--stop-loss', type=float, default=-0.10, help='止损比例,如: -0.10')
    parser.add_argument('--stop-gain', type=float, default=0.15, help='止盈比例,如: 0.15')
    parser.add_argument('--max-hold-days', type=int, default=15, help='最大持仓天数')
    
    # 市场过滤
    parser.add_argument('--market-ma', type=int, default=60, help='市场均线周期')
    parser.add_argument('--no-market-filter', action='store_true', help='禁用市场过滤')
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # 解析权重
    weights = tuple(int(w)/100 for w in args.weights.split(','))
    
    # 解析排除代码
    exclude_codes = set(args.exclude.split(',')) if args.exclude else None
    
    # 运行策略
    try:
        result = run_strategy(
            test_start=args.test_start,
            test_end=args.test_end,
            
            # 数据
            data_dir=args.data_dir,
            market_code=args.market_code,
            
            # 训练期
            train_start=args.train_start,
            train_end=args.train_end,
            
            # 选股
            top_n=args.top_n,
            score_threshold=args.score,
            exclude_codes=exclude_codes,
            
            # 持仓
            hold_count=args.hold_count,
            weights=weights,
            
            # 调仓
            rebalance_days=args.rebalance,
            
            # 风控
            stop_loss=args.stop_loss,
            stop_gain=args.stop_gain,
            max_hold_days=args.max_hold_days,
            
            # 市场过滤
            market_ma=args.market_ma,
            enable_market_filter=not args.no_market_filter,
        )
        
        # 输出结果
        print(f"\n{'='*60}")
        print(f"参数配置:")
        print(f"  训练期: {args.train_start} ~ {args.train_end}")
        print(f"  测试期: {args.test_start} ~ {args.test_end}")
        print(f"  ETF数量: {args.top_n}, 持仓: {args.hold_count}只")
        print(f"  调仓周期: {args.rebalance}天, 分数门槛: >={args.score}")
        print(f"  市场过滤: {'启用(MA' + str(args.market_ma) + ')' if not args.no_market_filter else '禁用'}")
        print('='*60)
        
        print(f"\n{'='*60}")
        print(f"回测结果:")
        print(f"{'='*60}")
        
        # 收益指标
        print(f"\n【收益指标】")
        print(f"  总收益率:     {result['return']:+.1f}%")
        print(f"  年化收益率:   {result['annual_return']:+.1f}%")
        
        # 风险指标
        print(f"\n【风险指标】")
        print(f"  最大回撤:     {result['drawdown']:.1f}%")
        print(f"  卡玛比率:     {result['calmar']:.2f}")
        print(f"  夏普比率:     {result['sharpe']:.2f}")
        
        # 交易指标
        print(f"\n【交易指标】")
        print(f"  交易次数:     {result['trades']}")
        print(f"  胜率:         {result['winrate']:.1f}%")
        print(f"  盈亏比:       {result['profit_loss_ratio']:.2f}")
        print(f"  平均持仓天数: {result['avg_hold_days']:.1f}天")
        print(f"  最大单笔盈利: {result['max_profit']:+.2f}%")
        print(f"  最大单笔亏损: {result['max_loss']:.2f}%")
        print(f"  持仓天数占比: {result['trade_days_ratio']:.1f}%")
        
        return result
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()