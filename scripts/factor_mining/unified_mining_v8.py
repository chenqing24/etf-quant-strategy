#!/usr/bin/env python3
"""
ETF多因子挖掘 v8.0 - 统一回测引擎版
====================================

【三个一致性】
1. 工具调用一致：DataLoader + IndicatorCalculator + RelativeCalculator + FactorBacktester
2. 执行流程一致：单因子测试 → 组合测试 → 过拟合验证 → 完整评价
3. 评价标准一致：8个核心指标

【v8.0核心改进】
- 唯一回测引擎：FactorBacktester (src/backtest/engine.py)
- T+1开盘价成交：避免look-ahead bias
- 持仓管理：closed_today防止重复买入
- min_hold_days：止盈需满足最小持仓
- 相对收益：计算与大盘的相对收益
"""
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
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
from src.backtest.engine import FactorBacktester, BacktestConfig as EngineConfig
from src.utils.logger import get_logger
logger = get_logger()


# ============================================================
# 因子定义（来自v7）
# ============================================================

# 因子定义
FACTOR_DEFINITIONS = FACTORS_V7

# 因子方向
FACTOR_DIRECTIONS = {
    'MACD红柱': 'long',
    'DMA多头': 'long',
    'SAR趋势': 'long',
    'ADX趋势': 'long',
    '布林突破': 'long',
    'RSI超卖': 'long',
    '资金流入': 'long',
    '相对强弱': 'long',
}


# ============================================================
# 信号组合
# ============================================================

def check_factor_signal(df: pd.DataFrame, factor_def: dict) -> pd.Series:
    """检查单因子信号"""
    col = factor_def.get('col', '')
    op = factor_def.get('op', '')
    threshold = factor_def.get('threshold', 0)
    ref = factor_def.get('ref', None)
    
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    
    if op == 'gt':
        return df[col] > threshold
    elif op == 'lt':
        return df[col] < threshold
    elif op == 'eq':
        return df[col] == threshold
    elif op == 'gte':
        return df[col] >= threshold
    elif op == 'lte':
        return df[col] <= threshold
    elif op == 'ref_gt':
        if ref and ref in df.columns:
            return df[col] > df[ref]
    elif op == 'ref_lt':
        if ref and ref in df.columns:
            return df[col] < df[ref]
    
    return pd.Series(False, index=df.index)


def combine_signals(df: pd.DataFrame, factor_names: List[str], factor_defs: dict) -> pd.Series:
    """组合多个因子信号（AND逻辑）"""
    combined = pd.Series(True, index=df.index)
    
    for name in factor_names:
        if name not in factor_defs:
            continue
        signal = check_factor_signal(df, factor_defs[name])
        combined = combined & signal
    
    return combined


# ============================================================
# 回测执行
# ============================================================

def backtest_factor_combo(
    price_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
    factor_defs: dict,
    config: EngineConfig,
    benchmark_data: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> Tuple[Dict, List[Dict]]:
    """
    回测因子组合
    
    Args:
        price_data: ETF数据
        factor_names: 因子列表
        factor_defs: 因子定义
        config: 回测配置
        benchmark_data: 大盘数据
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        (metrics, trades)
    """
    # 定义信号函数
    def signal_func(df: pd.DataFrame) -> pd.Series:
        return combine_signals(df, factor_names, factor_defs)
    
    # 创建回测器
    backtester = FactorBacktester(config=config)
    
    # 执行回测
    result = backtester.backtest(
        price_data=price_data,
        signal_func=signal_func,
        benchmark_data=benchmark_data,
        start_date=start_date,
        end_date=end_date,
    )
    
    # 转换为字典
    metrics = {
        'total_return': result.total_return,
        'relative_return': result.relative_return,
        'annual_return': result.annual_return,
        'max_drawdown': result.max_drawdown,
        'daily_volatility': result.daily_volatility,
        'sharpe_relative': result.sharpe_relative,
        'calmar_ratio': result.calmar_ratio,
        'win_rate': result.win_rate,
        'trade_count': result.trade_count,
        'annual_trades': result.annual_trades,
        'profit_loss_ratio': result.profit_loss_ratio,
        'avg_profit': result.avg_profit,
        'avg_loss': result.avg_loss,
    }
    
    return metrics, result.trades


# ============================================================
# 组合测试
# ============================================================

def test_factor_combinations(
    etf_data: Dict[str, pd.DataFrame],
    benchmark_data: pd.DataFrame,
    factor_defs: dict,
    min_factors: int = 2,
    max_factors: int = 4,
    start_date: str = None,
    end_date: str = None,
    max_combos: int = 100,
) -> List[Dict]:
    """测试因子组合"""
    
    # 筛选有数据的因子
    available_factors = []
    sample_df = list(etf_data.values())[0]
    for name, defn in factor_defs.items():
        col = defn.get('col', '')
        if col in sample_df.columns:
            available_factors.append(name)
    
    print(f"可用因子: {len(available_factors)}")
    
    # 生成组合
    combos = []
    for n in range(min_factors, max_factors + 1):
        for combo in combinations(available_factors, n):
            combos.append(list(combo))
    
    print(f"待测试组合: {len(combos)}")
    
    if len(combos) > max_combos:
        combos = combos[:max_combos]
        print(f"限制为前{max_combos}个组合")
    
    # 回测配置
    config = EngineConfig(
        stop_loss=-0.04,
        stop_profit=0.06,
        min_hold_days=3,
        max_hold_days=20,
        max_positions=2,
    )
    
    # 执行回测
    results = []
    for i, factors in enumerate(combos):
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(combos)}")
        
        try:
            metrics, trades = backtest_factor_combo(
                price_data=etf_data,
                factor_names=factors,
                factor_defs=factor_defs,
                config=config,
                benchmark_data=benchmark_data,
                start_date=start_date,
                end_date=end_date,
            )
            
            # 计算综合评分
            score = calc_combo_score(metrics)
            
            results.append({
                'factors': factors,
                'metrics': metrics,
                'score': score,
                'trade_count': metrics['trade_count'],
            })
        except Exception as e:
            print(f"  组合{factors}回测失败: {e}")
    
    # 按评分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return results


def calc_combo_score(metrics: Dict) -> float:
    """计算组合评分"""
    score = 0.0
    
    # 相对收益（最重要）
    rel_ret = metrics.get('relative_return', 0)
    score += rel_ret * 100 * 2  # 权重2
    
    # 夏普比率
    sharpe = metrics.get('sharpe_relative', 0)
    score += sharpe * 10
    
    # 胜率
    win_rate = metrics.get('win_rate', 0)
    score += win_rate * 30
    
    # 最大回撤（负分）
    mdd = metrics.get('max_drawdown', 0)
    score -= mdd * 50
    
    # 交易数惩罚
    trade_count = metrics.get('trade_count', 0)
    if trade_count < 10:
        score -= 20
    
    return score


# ============================================================
# 数据加载
# ============================================================

def load_all_data(etf_codes: List[str]) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
    """加载所有数据"""
    dl = DataLoader()
    
    # 加载ETF数据
    all_data = dl.load(etf_codes)
    
    # 分离大盘和ETF
    benchmark_data = all_data.get('510300')
    if benchmark_data is None:
        benchmark_data = all_data[list(all_data.keys())[0]]
    
    etf_data = {k: v for k, v in all_data.items() if k != '510300'}
    
    # 计算指标
    ic = IndicatorCalculator()
    for code in etf_data:
        etf_data[code] = ic.calculate_all(etf_data[code])
    
    # 计算相对指标
    if benchmark_data is not None:
        rc = RelativeCalculator('510300')
        for code in etf_data:
            etf_data[code] = rc.calc_all_relative(etf_data[code], benchmark_data)
    
    return etf_data, benchmark_data


# ============================================================
# 主函数
# ============================================================

def main():
    """主函数"""
    print("=" * 80)
    print("ETF多因子挖掘 v8.0")
    print("=" * 80)
    print()
    
    # 配置
    ETF_CODES = ['510300', '512880']  # 减少ETF数量加快测试
    START_DATE = '2024-01-01'
    END_DATE = '2024-03-31'  # 缩短测试周期
    
    # 加载数据
    print("加载数据...")
    etf_data, benchmark_data = load_all_data(ETF_CODES)
    print(f"ETF数量: {len(etf_data)}")
    print()
    
    # 测试因子组合
    print("开始测试因子组合...")
    start_time = time.time()
    
    results = test_factor_combinations(
        etf_data=etf_data,
        benchmark_data=benchmark_data,
        factor_defs=FACTOR_DEFINITIONS,
        min_factors=2,
        max_factors=4,
        start_date=START_DATE,
        end_date=END_DATE,
        max_combos=10,  # 限制数量（小规模测试）
    )
    
    elapsed = time.time() - start_time
    print(f"\n完成！用时 {elapsed:.1f}秒")
    print()
    
    # 输出Top10
    print("=" * 80)
    print("Top10 因子组合")
    print("=" * 80)
    
    for i, result in enumerate(results[:10], 1):
        print(f"\n#{i}: {' + '.join(result['factors'])}")
        print(f"   评分: {result['score']:.2f}")
        print(f"   交易数: {result['trade_count']}")
        m = result['metrics']
        print(f"   相对收益: {m['relative_return']:.2%}")
        print(f"   胜率: {m['win_rate']:.2%}")
        print(f"   夏普: {m['sharpe_relative']:.2f}")
        print(f"   最大回撤: {m['max_drawdown']:.2%}")
    
    # 保存结果
    output_dir = Path('data/experiments_v8')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'results.json', 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果已保存: {output_dir / 'results.json'}")


if __name__ == '__main__':
    main()