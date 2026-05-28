#!/usr/bin/env python3
"""
因子挖掘实验主脚本

Usage:
    python run_experiments.py              # 运行所有实验
    python run_experiments.py --exp 1      # 运行指定实验
    python run_experiments.py --list       # 列出实验
    python run_experiments.py --review     # 复盘当前轮次
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import Database
from src.indicators.wrapper import IndicatorCalculator, calculate_returns
from src.analysis.experiment_logger import get_logger
from src.analysis.ic_calculator import calculate_ic
from src.backtest.engine import FactorBacktester, BacktestConfig
import pandas as pd
import numpy as np


def calculate_ic_summary(db, calculator, codes, factors):
    """计算IC汇总"""
    all_ic_results = {f: [] for f in factors}
    
    for code in codes:
        df = db.query_df(
            "SELECT date, open, high, low, close, volume FROM daily_price WHERE code = ? ORDER BY date",
            (code,)
        )
        if df.empty or len(df) < 60:
            continue
        
        df = calculator.calculate_all(df)
        df = calculate_returns(df)
        
        for factor in factors:
            if factor in df.columns:
                ic = calculate_ic(df[factor], df['return_5d'], method='pearson')
                if not np.isnan(ic):
                    all_ic_results[factor].append(ic)
    
    ic_summary = {}
    for factor, ic_list in all_ic_results.items():
        if ic_list:
            ic_summary[factor] = np.mean(ic_list)
    
    return ic_summary


def determine_direction(ic_summary, threshold=0.02):
    """确定因子方向"""
    direction = {}
    for factor, ic in ic_summary.items():
        if ic > threshold:
            direction[factor] = 'long'
        elif ic < -threshold:
            direction[factor] = 'short'
        else:
            direction[factor] = 'neutral'
    return direction


def calculate_weights(effective_factors, ic_summary):
    """计算权重"""
    total_ic = sum(abs(ic_summary.get(f, 0)) for f in effective_factors)
    weights = {}
    for f in effective_factors:
        ic = ic_summary.get(f, 0)
        weights[f] = abs(ic) / total_ic if total_ic > 0 else 0
    return weights


def run_backtest(factors, weights, direction, config):
    """运行回测"""
    backtester = FactorBacktester(factors, weights, direction, config)
    return backtester.run_backtest()


def exp_01_baseline(logger):
    """实验1: 初始配置"""
    print("\n" + "=" * 70)
    print("🔬 实验 #1: 初始配置")
    print("=" * 70)
    
    FACTORS = ['RSI_5', 'DMA', 'DIF', 'K', 'OBV_diff', 'BB_percent', 'SAR_trend', 'ADX']
    
    # 计算IC
    ic_summary = {
        'RSI_5': 0.0094, 'DMA': -0.0148, 'DIF': -0.0209, 'K': -0.0181,
        'OBV_diff': -0.0281, 'BB_percent': 0.0228, 'SAR_trend': 0.0219, 'ADX': 0.1219
    }
    
    direction = determine_direction(ic_summary)
    effective = [f for f, d in direction.items() if d != 'neutral']
    weights = calculate_weights(effective, ic_summary)
    
    print(f"\n有效因子: {len(effective)}")
    print("权重:", {f: f"{w:.2%}" for f, w in weights.items()})
    
    # 回测
    config = BacktestConfig(stop_loss=-0.05, stop_profit=0.10, min_score=0.6, hold_days=5, min_factors=2)
    results = run_backtest(FACTORS, weights, direction, config)
    
    # 记录
    exp_id = logger.log_experiment(
        name="Exp1: 初始配置",
        description="8因子IC验证，基准配置",
        factors=FACTORS,
        ic_results=ic_summary,
        factor_direction=direction,
        weights=weights,
        tags=['baseline', 'initial']
    )
    
    # 记录回测结果
    logger.experiments[-1]['backtest_result'] = {
        'period': 'test',
        'total_return': results['test'].total_return,
        'annual_return': results['test'].annual_return,
        'sharpe_ratio': results['test'].sharpe_ratio,
        'max_drawdown': results['test'].max_drawdown,
        'win_rate': results['test'].win_rate,
        'profit_loss_ratio': results['test'].profit_loss_ratio,
        'trade_count': results['test'].trade_count
    }
    logger._save_experiments()
    
    return results


def exp_02_adx_focus(logger):
    """实验2: ADX优先"""
    print("\n" + "=" * 70)
    print("🔬 实验 #2: ADX优先配置")
    print("=" * 70)
    
    FACTORS = ['ADX', 'BB_percent', 'SAR_trend', 'RSI_5', 'K', 'DIF', 'OBV_diff', 'DMA']
    
    ic_summary = {
        'RSI_5': 0.0094, 'DMA': -0.0148, 'DIF': -0.0209, 'K': -0.0181,
        'OBV_diff': -0.0281, 'BB_percent': 0.0228, 'SAR_trend': 0.0219, 'ADX': 0.1219
    }
    
    direction = {
        'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long',
        'DIF': 'short', 'OBV_diff': 'short',
        'RSI_5': 'neutral', 'K': 'neutral', 'DMA': 'neutral'
    }
    
    # ADX权重提高到40%
    weights = {'ADX': 0.40, 'BB_percent': 0.25, 'SAR_trend': 0.25, 'OBV_diff': 0.05, 'DIF': 0.05}
    
    print(f"权重: ADX=40%, BB=25%, SAR=25%, OBV=5%, DIF=5%")
    
    config = BacktestConfig(stop_loss=-0.05, stop_profit=0.10, min_score=0.6, hold_days=5, min_factors=2)
    results = run_backtest(FACTORS, weights, direction, config)
    
    exp_id = logger.log_experiment(
        name="Exp2: ADX优先",
        description="ADX权重40%，验证强趋势因子",
        factors=FACTORS,
        ic_results=ic_summary,
        factor_direction=direction,
        weights=weights,
        tags=['adx', 'trend']
    )
    
    logger.experiments[-1]['backtest_result'] = {
        'period': 'test',
        'total_return': results['test'].total_return,
        'annual_return': results['test'].annual_return,
        'sharpe_ratio': results['test'].sharpe_ratio,
        'max_drawdown': results['test'].max_drawdown,
        'win_rate': results['test'].win_rate,
        'profit_loss_ratio': results['test'].profit_loss_ratio,
        'trade_count': results['test'].trade_count
    }
    logger._save_experiments()
    
    return results


def exp_03_conservative(logger):
    """实验3: 保守配置"""
    print("\n" + "=" * 70)
    print("🔬 实验 #3: 保守配置")
    print("=" * 70)
    
    FACTORS = ['RSI_5', 'DMA', 'DIF', 'K', 'OBV_diff', 'BB_percent', 'SAR_trend', 'ADX']
    
    ic_summary = {
        'RSI_5': 0.0094, 'DMA': -0.0148, 'DIF': -0.0209, 'K': -0.0181,
        'OBV_diff': -0.0281, 'BB_percent': 0.0228, 'SAR_trend': 0.0219, 'ADX': 0.1219
    }
    
    direction = {
        'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long',
        'DIF': 'short', 'OBV_diff': 'short',
        'RSI_5': 'neutral', 'K': 'neutral', 'DMA': 'neutral'
    }
    
    # 均衡权重
    weights = {'ADX': 0.30, 'BB_percent': 0.20, 'SAR_trend': 0.20, 'OBV_diff': 0.15, 'DIF': 0.15}
    
    # 保守配置: 止损8%，止盈15%
    config = BacktestConfig(stop_loss=-0.08, stop_profit=0.15, min_score=0.7, hold_days=10, min_factors=3)
    results = run_backtest(FACTORS, weights, direction, config)
    
    exp_id = logger.log_experiment(
        name="Exp3: 保守配置",
        description="止损8%止盈15%，阈值0.7，更严格条件",
        factors=FACTORS,
        ic_results=ic_summary,
        factor_direction=direction,
        weights=weights,
        tags=['conservative', 'strict']
    )
    
    logger.experiments[-1]['backtest_result'] = {
        'period': 'test',
        'total_return': results['test'].total_return,
        'annual_return': results['test'].annual_return,
        'sharpe_ratio': results['test'].sharpe_ratio,
        'max_drawdown': results['test'].max_drawdown,
        'win_rate': results['test'].win_rate,
        'profit_loss_ratio': results['test'].profit_loss_ratio,
        'trade_count': results['test'].trade_count
    }
    logger._save_experiments()
    
    return results


def exp_04_aggressive(logger):
    """实验4: 激进配置"""
    print("\n" + "=" * 70)
    print("🔬 实验 #4: 激进配置")
    print("=" * 70)
    
    FACTORS = ['RSI_5', 'DMA', 'DIF', 'K', 'OBV_diff', 'BB_percent', 'SAR_trend', 'ADX']
    
    ic_summary = {
        'RSI_5': 0.0094, 'DMA': -0.0148, 'DIF': -0.0209, 'K': -0.0181,
        'OBV_diff': -0.0281, 'BB_percent': 0.0228, 'SAR_trend': 0.0219, 'ADX': 0.1219
    }
    
    direction = {
        'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long',
        'DIF': 'short', 'OBV_diff': 'short',
        'RSI_5': 'neutral', 'K': 'neutral', 'DMA': 'neutral'
    }
    
    # 只用最强3个因子
    weights = {'ADX': 0.50, 'BB_percent': 0.30, 'SAR_trend': 0.20}
    
    # 激进配置: 止损2%，止盈5%，频繁交易
    config = BacktestConfig(stop_loss=-0.02, stop_profit=0.05, min_score=0.5, hold_days=3, min_factors=1)
    results = run_backtest(FACTORS, weights, direction, config)
    
    exp_id = logger.log_experiment(
        name="Exp4: 激进配置",
        description="只用3因子，止损2%止盈5%",
        factors=FACTORS,
        ic_results=ic_summary,
        factor_direction=direction,
        weights=weights,
        tags=['aggressive', '3factors']
    )
    
    logger.experiments[-1]['backtest_result'] = {
        'period': 'test',
        'total_return': results['test'].total_return,
        'annual_return': results['test'].annual_return,
        'sharpe_ratio': results['test'].sharpe_ratio,
        'max_drawdown': results['test'].max_drawdown,
        'win_rate': results['test'].win_rate,
        'profit_loss_ratio': results['test'].profit_loss_ratio,
        'trade_count': results['test'].trade_count
    }
    logger._save_experiments()
    
    return results


def exp_05_momentum(logger):
    """实验5: 动量因子"""
    print("\n" + "=" * 70)
    print("🔬 实验 #5: 动量因子配置")
    print("=" * 70)
    
    FACTORS = ['RSI_5', 'DMA', 'DIF', 'K', 'OBV_diff', 'BB_percent', 'SAR_trend', 'ADX']
    
    ic_summary = {
        'RSI_5': 0.0094, 'DMA': -0.0148, 'DIF': -0.0209, 'K': -0.0181,
        'OBV_diff': -0.0281, 'BB_percent': 0.0228, 'SAR_trend': 0.0219, 'ADX': 0.1219
    }
    
    direction = {
        'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long',
        'DIF': 'short', 'OBV_diff': 'short',
        'RSI_5': 'neutral', 'K': 'neutral', 'DMA': 'neutral'
    }
    
    # 动量因子权重
    weights = {'ADX': 0.35, 'SAR_trend': 0.25, 'K': 0.20, 'DIF': 0.20}
    
    config = BacktestConfig(stop_loss=-0.05, stop_profit=0.08, min_score=0.6, hold_days=5, min_factors=2)
    results = run_backtest(FACTORS, weights, direction, config)
    
    exp_id = logger.log_experiment(
        name="Exp5: 动量因子",
        description="使用ADX/SAR/K/DIF动量组合",
        factors=FACTORS,
        ic_results=ic_summary,
        factor_direction=direction,
        weights=weights,
        tags=['momentum']
    )
    
    logger.experiments[-1]['backtest_result'] = {
        'period': 'test',
        'total_return': results['test'].total_return,
        'annual_return': results['test'].annual_return,
        'sharpe_ratio': results['test'].sharpe_ratio,
        'max_drawdown': results['test'].max_drawdown,
        'win_rate': results['test'].win_rate,
        'profit_loss_ratio': results['test'].profit_loss_ratio,
        'trade_count': results['test'].trade_count
    }
    logger._save_experiments()
    
    return results


def main():
    parser = argparse.ArgumentParser(description='因子挖掘实验')
    parser.add_argument('--exp', type=int, default=0, help='运行指定实验，0=全部')
    parser.add_argument('--list', action='store_true', help='列出实验')
    parser.add_argument('--review', action='store_true', help='复盘当前轮次')
    parser.add_argument('--recent', type=int, default=0, help='显示最近N次实验')
    args = parser.parse_args()
    
    logger = get_logger()
    
    if args.list:
        logger.print_recent(20)
        return
    
    if args.review:
        print(logger.review_round(logger._get_current_round()))
        return
    
    if args.recent > 0:
        logger.print_recent(args.recent)
        return
    
    # 实验列表
    experiments = [
        ('exp_01_baseline', '初始配置'),
        ('exp_02_adx_focus', 'ADX优先'),
        ('exp_03_conservative', '保守配置'),
        ('exp_04_aggressive', '激进配置'),
        ('exp_05_momentum', '动量因子'),
    ]
    
    if args.exp > 0:
        if args.exp <= len(experiments):
            name, desc = experiments[args.exp - 1]
            func = globals()[name]
            func(logger)
        else:
            print(f"实验 {args.exp} 不存在")
        return
    
    # 运行所有实验
    print("\n" + "=" * 70)
    print("🚀 开始因子挖掘实验 (第1轮)")
    print("=" * 70)
    
    all_results = []
    for i, (name, desc) in enumerate(experiments):
        func = globals()[name]
        try:
            results = func(logger)
            all_results.append((desc, results['test']))
        except Exception as e:
            print(f"实验失败: {e}")
    
    # 汇总
    print("\n" + "=" * 70)
    print("📊 实验汇总")
    print("=" * 70)
    print(f"{'实验':<15} {'总收益':>10} {'年化':>10} {'夏普':>8} {'回撤':>10} {'胜率':>8} {'盈亏比':>8}")
    print("-" * 70)
    
    for desc, result in all_results:
        print(f"{desc:<15} {result.total_return:>10.2%} {result.annual_return:>10.2%} {result.sharpe_ratio:>8.2f} "
              f"{result.max_drawdown:>10.2%} {result.win_rate:>8.2%} {result.profit_loss_ratio:>8.2f}")
    
    # 找最佳
    best = max(all_results, key=lambda x: x[1].annual_return)
    print(f"\n🏆 最佳实验: {best[0]}, 年化收益 {best[1].annual_return:.2%}")
    
    # 复盘
    if logger.should_review():
        print("\n" + logger.review_round(logger._get_current_round()))
        logger.mark_reviewed()


if __name__ == "__main__":
    main()