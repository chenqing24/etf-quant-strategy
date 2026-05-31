#!/usr/bin/env python3
"""
ETF多因子挖掘 v7.0 - 完整评价体系版
====================================
【三个一致性】
1. 工具调用一致：DataLoader + IndicatorCalculator + RelativeCalculator + FactorBacktester
2. 执行流程一致：单因子测试 → 组合测试 → 过拟合验证 → 完整评价
3. 评价标准一致：43个指标 + 8大维度 + 硬性门槛

【核心改进（相对v6.0）】
- 大盘因子量化：引入相对收益率、相对MACD、相对强弱等8个相对指标
- 完整评价体系：43个指标覆盖8大维度
- 相对收益基准：相对于大盘和ETF池的超额收益
"""
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from itertools import combinations
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.indicators.relative import RelativeCalculator, FACTORS_V7
from src.evaluation.metrics_v7 import (
    calc_all_metrics, calc_comprehensive_score,
    METRICS, DIMENSIONS, HARD_REJECT
)
from src.utils.logger import get_logger

logger = get_logger()


# ============================================================
# v7.0专用回测配置（不依赖外部版本）
# ============================================================

@dataclass
class SimpleBacktestConfig:
    """v7.0专用回测配置"""
    stop_loss: float = -0.04      # 止损4%
    stop_profit: float = 0.06     # 止盈6%
    min_hold_days: int = 3        # 最小持仓3天
    max_hold_days: int = 20       # 最大持仓20天
    commission_rate: float = 0.0003   # 佣金0.03%
    slippage_rate: float = 0.0002     # 滑点0.02%

    def to_dict(self) -> dict:
        return {
            'stop_loss': self.stop_loss,
            'stop_profit': self.stop_profit,
            'min_hold_days': self.min_hold_days,
            'max_hold_days': self.max_hold_days,
            'commission_rate': self.commission_rate,
            'slippage_rate': self.slippage_rate,
        }


# 别名，方便使用
BacktestConfig = SimpleBacktestConfig


# ============================================================
# 配置
# ============================================================

# ETF池（15只）
ETF_POOL = [
    '510300',  # 大盘参考
    '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]
TRADE_ETFS = [c for c in ETF_POOL if c != '510300']
BENCHMARK_CODE = '510300'

# ETF专用参数
TAKE_PROFIT = 0.06   # 止盈6%
STOP_LOSS = 0.04     # 止损4%
MIN_HOLD_DAYS = 3    # 最小持仓3天
MAX_HOLD_DAYS = 20   # 最大持仓20天

# 过拟合检验参数
ROLLING_WINDOW_DAYS = 180  # 滚动窗口大小
ROLLING_STEP_DAYS = 60     # 滚动步长
MONTE_CARLO_N = 500        # 蒙特卡洛次数

# 成本参数
COMMISSION_RATE = 0.0003    # 佣金0.03%
SLIPPAGE_RATE = 0.0002     # 滑点0.02%


# ============================================================
# 数据加载（三个一致性之一：工具调用一致）
# ============================================================

def load_all_data(etf_codes: List[str], benchmark_code: str = '510300') -> Dict[str, pd.DataFrame]:
    """
    加载所有ETF数据，并计算相对大盘的指标
    
    【三个一致性：工具调用一致】
    使用标准化工具链：
    - DataLoader → 加载原始数据
    - IndicatorCalculator → 计算技术指标
    - RelativeCalculator → 计算相对指标
    """
    loader = DataLoader()
    ind_calc = IndicatorCalculator()
    rel_calc = RelativeCalculator(benchmark_code)
    
    logger.info(f"加载大盘数据: {benchmark_code}")
    df_benchmark = loader.load_etf_data(benchmark_code)
    df_benchmark = ind_calc.calculate(df_benchmark)
    
    logger.info(f"计算大盘技术指标完成，{len(df_benchmark)}行")
    
    etf_data = {}
    for code in etf_codes:
        if code == benchmark_code:
            continue
            
        logger.info(f"加载ETF数据: {code}")
        df_etf = loader.load_etf_data(code)
        df_etf = ind_calc.calculate(df_etf)
        
        # 计算相对指标
        df_etf = rel_calc.calc_all_relative(df_etf, df_benchmark)
        
        etf_data[code] = df_etf
        logger.info(f"  → ETF {code} 加载完成，{len(df_etf)}行，{len(df_etf.columns)}列")
    
    return etf_data, df_benchmark


def calc_benchmark_metrics(df_benchmark: pd.DataFrame) -> dict:
    """计算大盘基准指标"""
    if len(df_benchmark) < 20:
        return {'benchmark_return': 0, 'etf_pool_return': 0}
    
    start_price = df_benchmark['close'].iloc[0]
    end_price = df_benchmark['close'].iloc[-1]
    benchmark_return = (end_price / start_price) - 1
    
    return {
        'benchmark_return': benchmark_return,
        'trade_days': len(df_benchmark),
    }


# ============================================================
# 因子信号生成
# ============================================================

def check_factor_signal(df: pd.DataFrame, factor_def: dict) -> pd.Series:
    """
    检查因子信号
    
    Args:
        df: ETF数据（含技术指标和相对指标）
        factor_def: 因子定义
    
    Returns:
        信号Series（True/False）
    """
    col = factor_def['col']
    op = factor_def['op']
    
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    
    if op == 'gt':
        return df[col] > factor_def.get('threshold', 0)
    elif op == 'lt':
        return df[col] < factor_def.get('threshold', 0)
    elif op == 'eq':
        return df[col] == factor_def.get('threshold', 0)
    elif op == 'gte':
        return df[col] >= factor_def.get('threshold', 0)
    elif op == 'lte':
        return df[col] <= factor_def.get('threshold', 0)
    elif op == 'between':
        return (df[col] >= factor_def.get('low', 0)) & (df[col] <= factor_def.get('high', 999))
    elif op == 'gt_ref':
        ref_col = factor_def.get('ref', '')
        if ref_col in df.columns:
            return df[col] > df[ref_col]
        return pd.Series(False, index=df.index)
    elif op == 'gt_ratio':
        ref_col = factor_def.get('ref', '')
        ratio = factor_def.get('ratio', 1.2)
        if ref_col in df.columns:
            return df[col] > df[ref_col] * ratio
        return pd.Series(False, index=df.index)
    
    return pd.Series(False, index=df.index)


def combine_signals(df: pd.DataFrame, factor_names: List[str], factor_defs: dict) -> pd.Series:
    """
    组合多个因子信号（AND逻辑）
    """
    combined = pd.Series(True, index=df.index)
    
    for name in factor_names:
        if name not in factor_defs:
            continue
        signal = check_factor_signal(df, factor_defs[name])
        combined = combined & signal
    
    return combined


# ============================================================
# 回测引擎
# ============================================================

def backtest_single_factor(
    etf_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
    config: BacktestConfig
) -> Tuple[List[dict], float, float]:
    """
    回测单个因子组合
    
    Returns:
        (trades, benchmark_return, etf_pool_return)
    """
    backtester = FactorBacktester(config)
    
    all_trades = []
    benchmark_return = 0
    etf_pool_return = 0
    
    for code, df in etf_data.items():
        signal = combine_signals(df, factor_names, FACTORS_V7)
        
        result = backtester.backtest(df, signal)
        trades = result.trades
        
        # 计算相对收益
        for trade in trades:
            trade['etf_code'] = code
            trade['relative_return'] = trade['return'] - trade.get('market_return', 0)
        
        all_trades.extend(trades)
    
    # 计算大盘收益
    if all_trades:
        benchmark_return = all_trades[0].get('market_return', 0)
        etf_pool_return = np.mean([t['return'] for t in all_trades])
    
    return all_trades, benchmark_return, etf_pool_return


# ============================================================
# 过拟合检验（三个一致性之一：执行流程一致）
# ============================================================

@dataclass
class OverfittingResult:
    """过拟合检验结果"""
    rolling_pass_rate: float = 0
    rolling_windows: List[Dict] = field(default_factory=list)
    monte_carlo_pvalue: float = 1
    monte_carlo_sim_returns: List[float] = field(default_factory=list)
    cross_val_pass_rate: float = 0
    cross_val_windows: List[Dict] = field(default_factory=list)
    return_decay_rate: float = 0


def rolling_window_test(
    etf_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
    config: BacktestConfig,
    window_days: int = ROLLING_WINDOW_DAYS,
    step_days: int = ROLLING_STEP_DAYS
) -> OverfittingResult:
    """滚动窗口过拟合检验"""
    result = OverfittingResult()
    
    # 获取公共日期范围
    all_dates = None
    for code, df in etf_data.items():
        if all_dates is None:
            all_dates = set(df.index)
        else:
            all_dates &= set(df.index)
    all_dates = sorted(list(all_dates))
    
    if len(all_dates) < window_days:
        return result
    
    # 滚动窗口
    start_idx = 0
    window_returns = []
    
    while start_idx + window_days <= len(all_dates):
        end_idx = start_idx + window_days
        window_dates = all_dates[start_idx:end_idx]
        
        # 截取窗口数据
        window_data = {}
        for code, df in etf_data.items():
            window_df = df.loc[df.index.isin(window_dates)].copy()
            if len(window_df) > 0:
                window_data[code] = window_df
        
        if len(window_data) >= 5:
            trades, bm_ret, _ = backtest_single_factor(window_data, factor_names, config)
            if trades:
                window_return = sum(t['return'] for t in trades)
                window_returns.append({
                    'start_date': window_dates[0],
                    'end_date': window_dates[-1],
                    'return': window_return,
                    'trade_count': len(trades)
                })
        
        start_idx += step_days
    
    if window_returns:
        result.rolling_pass_rate = sum(1 for r in window_returns if r['return'] > 0) / len(window_returns)
        result.rolling_windows = window_returns
    
    return result


def monte_carlo_test(
    etf_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
    config: BacktestConfig,
    n_simulations: int = MONTE_CARLO_N
) -> OverfittingResult:
    """蒙特卡洛过拟合检验"""
    result = OverfittingResult()
    
    # 获取所有交易收益
    all_trades, _, _ = backtest_single_factor(etf_data, factor_names, config)
    
    if not all_trades or len(all_trades) < 10:
        return result
    
    returns = [t['return'] for t in all_trades]
    observed_mean = np.mean(returns)
    
    # 模拟
    sim_returns = []
    np.random.seed(42)
    for _ in range(n_simulations):
        sim_sample = np.random.choice(returns, size=len(returns), replace=True)
        sim_returns.append(np.mean(sim_sample))
    
    result.monte_carlo_sim_returns = sim_returns
    
    # p值：模拟均值大于观测均值的比例
    p_value = sum(1 for r in sim_returns if r >= observed_mean) / n_simulations
    result.monte_carlo_pvalue = p_value
    
    return result


def cross_validation_test(
    etf_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
    config: BacktestConfig,
    n_folds: int = 3
) -> OverfittingResult:
    """交叉验证过拟合检验"""
    result = OverfittingResult()
    
    # 获取公共日期范围
    all_dates = None
    for code, df in etf_data.items():
        if all_dates is None:
            all_dates = set(df.index)
        else:
            all_dates &= set(df.index)
    all_dates = sorted(list(all_dates))
    
    if len(all_dates) < 100:
        return result
    
    # 分成n个时期
    fold_size = len(all_dates) // n_folds
    cv_results = []
    
    for fold in range(n_folds):
        val_start = fold * fold_size
        val_end = val_start + fold_size
        
        val_dates = all_dates[val_start:val_end]
        
        # 验证期
        val_data = {}
        for code, df in etf_data.items():
            val_df = df.loc[df.index.isin(val_dates)].copy()
            if len(val_df) > 0:
                val_data[code] = val_df
        
        if len(val_data) >= 5:
            trades, _, _ = backtest_single_factor(val_data, factor_names, config)
            if trades:
                cv_return = sum(t['return'] for t in trades)
                cv_results.append({
                    'fold': fold,
                    'return': cv_return,
                    'trade_count': len(trades)
                })
    
    if cv_results:
        result.cross_val_pass_rate = sum(1 for r in cv_results if r['return'] > 0) / len(cv_results)
        result.cross_val_windows = cv_results
    
    return result


# ============================================================
# 完整评价（三个一致性之一：评价标准一致）
# ============================================================

def evaluate_model(
    trades: List[dict],
    benchmark_return: float,
    etf_pool_return: float,
    trade_days: int,
    overfit_result: OverfittingResult
) -> dict:
    """
    完整评价模型
    
    【三个一致性：评价标准一致】
    使用43个指标、8大维度、硬性门槛
    """
    # 1. 计算所有43个指标
    rolling_results = overfit_result.rolling_windows
    monte_carlo_pvalue = overfit_result.monte_carlo_pvalue
    crossval_results = overfit_result.cross_val_windows
    
    metrics = calc_all_metrics(
        trades=trades,
        benchmark_return=benchmark_return,
        etf_pool_return=etf_pool_return,
        trade_days=trade_days,
        rolling_results=rolling_results,
        monte_carlo_pvalue=monte_carlo_pvalue,
        crossval_results=crossval_results,
        commission_rate=COMMISSION_RATE,
        slippage_rate=SLIPPAGE_RATE
    )
    
    # 2. 综合评分
    score_result = calc_comprehensive_score(metrics)
    
    # 3. 组装结果
    return {
        'trades': trades,
        'metrics': metrics,
        'score': score_result,
        'overfitting': {
            'rolling_pass_rate': overfit_result.rolling_pass_rate,
            'monte_carlo_pvalue': overfit_result.monte_carlo_pvalue,
            'cross_val_pass_rate': overfit_result.cross_val_pass_rate,
            'return_decay_rate': overfit_result.return_decay_rate,
        }
    }


# ============================================================
# 主流程（三个一致性之一：执行流程一致）
# ============================================================

def run_experiment(
    etf_data: Dict[str, pd.DataFrame],
    df_benchmark: pd.DataFrame,
    output_dir: Path
):
    """
    执行v7.0因子挖掘实验
    
    【三个一致性：执行流程一致】
    Phase 1: 单因子测试
    Phase 2: 组合因子测试
    Phase 3: 过拟合验证
    Phase 4: 完整评价
    """
    logger.info("=" * 60)
    logger.info("ETF多因子挖掘 v7.0 - 完整评价体系版")
    logger.info("=" * 60)
    
    # 计算基准
    bm_metrics = calc_benchmark_metrics(df_benchmark)
    logger.info(f"大盘基准收益: {bm_metrics['benchmark_return']*100:.2f}%")
    
    config = BacktestConfig(
        initial_capital=100000,
        take_profit=TAKE_PROFIT,
        stop_loss=STOP_LOSS,
        min_hold_days=MIN_HOLD_DAYS,
        max_hold_days=MAX_HOLD_DAYS,
        commission_rate=COMMISSION_RATE,
        slippage_rate=SLIPPAGE_RATE
    )
    
    # ----- Phase 1: 单因子测试 -----
    logger.info("\n" + "=" * 60)
    logger.info("Phase 1: 单因子测试")
    logger.info("=" * 60)
    
    single_factor_results = []
    
    for name, defn in FACTORS_V7.items():
        logger.info(f"\n测试单因子: {name}")
        
        trades, bm_ret, pool_ret = backtest_single_factor(etf_data, [name], config)
        
        if not trades:
            logger.info(f"  → 无交易，跳过")
            continue
        
        # 过拟合验证
        overfit = rolling_window_test(etf_data, [name], config)
        overfit2 = monte_carlo_test(etf_data, [name], config)
        overfit3 = cross_validation_test(etf_data, [name], config)
        
        # 完整评价
        result = evaluate_model(
            trades, bm_ret, pool_ret,
            bm_metrics['trade_days'],
            overfit
        )
        
        # 合并过拟合结果
        result['overfitting']['monte_carlo_pvalue'] = overfit2.monte_carlo_pvalue
        result['overfitting']['cross_val_pass_rate'] = overfit3.cross_val_pass_rate
        
        single_factor_results.append({
            'factors': [name],
            'factor_count': 1,
            'result': result
        })
        
        score = result['score']['total_score']
        grade = result['score']['grade']
        logger.info(f"  → 总分: {score}, 等级: {grade}")
    
    # ----- Phase 2: 组合因子测试 -----
    logger.info("\n" + "=" * 60)
    logger.info("Phase 2: 组合因子测试")
    logger.info("=" * 60)
    
    combination_results = []
    factor_names = list(FACTORS_V7.keys())
    
    # 只测试2-4因子组合
    for n_factors in [2, 3, 4]:
        logger.info(f"\n测试{n_factors}因子组合...")
        
        count = 0
        for combo in combinations(factor_names, n_factors):
            count += 1
            
            if count % 100 == 0:
                logger.info(f"  已测试 {count} 个组合...")
            
            combo_list = list(combo)
            trades, bm_ret, pool_ret = backtest_single_factor(etf_data, combo_list, config)
            
            if not trades or len(trades) < 20:
                continue
            
            # 快速过拟合检查（只做滚动窗口）
            overfit = rolling_window_test(etf_data, combo_list, config)
            if overfit.rolling_pass_rate < 0.5:
                continue
            
            # 完整评价
            result = evaluate_model(
                trades, bm_ret, pool_ret,
                bm_metrics['trade_days'],
                overfit
            )
            
            combination_results.append({
                'factors': combo_list,
                'factor_count': n_factors,
                'result': result
            })
        
        logger.info(f"  {n_factors}因子组合测试完成: {count}个")
    
    # ----- Phase 3: 汇总结果 -----
    all_results = single_factor_results + combination_results
    
    logger.info("\n" + "=" * 60)
    logger.info("Phase 3: 结果汇总")
    logger.info("=" * 60)
    
    # 按评分排序
    all_results.sort(key=lambda x: x['result']['score']['total_score'], reverse=True)
    
    # 统计
    total_models = len(all_results)
    score_dist = {'S': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
    
    for r in all_results:
        grade = r['result']['score']['grade']
        score_dist[grade] += 1
    
    logger.info(f"总模型数: {total_models}")
    logger.info(f"评分分布: {score_dist}")
    
    # ----- Phase 4: 输出报告 -----
    report = {
        'version': 'v7.0',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'config': {
            'etf_pool': ETF_POOL,
            'trade_etfs': TRADE_ETFS,
            'take_profit': TAKE_PROFIT,
            'stop_loss': STOP_LOSS,
            'min_hold_days': MIN_HOLD_DAYS,
            'max_hold_days': MAX_HOLD_DAYS,
            'benchmark_code': BENCHMARK_CODE,
            'rolling_window_days': ROLLING_WINDOW_DAYS,
            'monte_carlo_n': MONTE_CARLO_N,
        },
        'benchmark_metrics': bm_metrics,
        'total_models': total_models,
        'score_distribution': score_dist,
        'factor_definitions': {k: v for k, v in FACTORS_V7.items()},
        'results': all_results,
        'dimensions': DIMENSIONS,
        'metrics': METRICS,
    }
    
    # 保存结果
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'full_results.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    
    # 保存Top模型
    top_models = []
    for r in all_results[:20]:
        top_models.append({
            'factors': r['factors'],
            'factor_count': r['factor_count'],
            'total_score': r['result']['score']['total_score'],
            'grade': r['result']['score']['grade'],
            'dimensions': {k: v['normalized'] for k, v in r['result']['score']['dimension_scores'].items()},
            'key_metrics': {
                'absolute_return': r['result']['metrics'].get('absolute_return'),
                'relative_return': r['result']['metrics'].get('relative_return'),
                'max_drawdown': r['result']['metrics'].get('max_drawdown'),
                'sharpe_absolute': r['result']['metrics'].get('sharpe_absolute'),
                'win_rate': r['result']['metrics'].get('win_rate'),
            },
            'overfitting': r['result']['overfitting'],
            'passed_checklist': r['result']['score']['passed_checklist'],
            'failed_checklist': r['result']['score']['failed_checklist'],
        })
    
    with open(output_dir / 'top_models.json', 'w', encoding='utf-8') as f:
        json.dump(top_models, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n结果已保存到: {output_dir}")
    
    return all_results


# ============================================================
# 入口
# ============================================================

def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ETF多因子挖掘 v7.0')
    parser.add_argument('--output', default='data/experiments_v7', help='输出目录')
    parser.add_argument('--codes', nargs='+', default=None, help='ETF代码列表')
    args = parser.parse_args()
    
    output_dir = Path(args.output) if args.output.startswith('/') else PROJECT_ROOT / args.output
    
    logger.info("开始加载数据...")
    etf_data, df_benchmark = load_all_data(TRADE_ETFS if not args.codes else args.codes)
    
    logger.info(f"\n数据加载完成:")
    logger.info(f"  交易ETF数: {len(etf_data)}")
    logger.info(f"  大盘数据: {len(df_benchmark)}行")
    
    results = run_experiment(etf_data, df_benchmark, output_dir)
    
    logger.info("\n" + "=" * 60)
    logger.info("实验完成!")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
