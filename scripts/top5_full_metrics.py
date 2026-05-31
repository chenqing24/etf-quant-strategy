#!/usr/bin/env python3
"""Top5模型完整指标计算"""
import sys
import json
from pathlib import Path
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader
from src.strategy.macd_strategy import MACDStrategy
from src.utils.logger import get_logger

logger = get_logger()


def parse_params(name: str) -> dict:
    """从名称解析参数"""
    params = {
        'macd_filter': 'MACD' in name or '红柱' in name,
        'momentum_days': 0,
        'stop_loss': 0.06,
        'take_profit': 0.12,
        'max_hold_days': 5,
        'market_filter': '510300' if '大盘' in name or 'MH' in name else None,
        'market_ma_short': 20 if 'MA' in name else 20,
        'market_ma_long': 60,
    }
    
    # 解析止损
    if 'SL' in name:
        import re
        match = re.search(r'SL(\d+)', name)
        if match:
            params['stop_loss'] = int(match.group(1)) / 100
    
    # 解析止盈
    if 'SP' in name:
        match = re.search(r'SP(\d+)', name)
        if match:
            params['take_profit'] = int(match.group(1)) / 100
    
    # 解析持仓
    if 'MH' in name:
        match = re.search(r'MH(\d+)', name)
        if match:
            params['max_hold_days'] = int(match.group(1))
    
    # 解析动量
    if '动量' in name or '动量' in name:
        match = re.search(r'动量(\d+)', name)
        if match:
            params['momentum_days'] = int(match.group(1))
    
    return params


def calculate_metrics(trades: list, returns: list, benchmark_returns: list) -> dict:
    """计算完整评价指标"""
    if not trades or len(returns) < 10:
        return None
    
    returns = np.array(returns)
    benchmark_returns = np.array(benchmark_returns)
    
    # 核心收益
    total_return = (1 + returns).prod() - 1
    annual_return = (1 + total_return) ** (252 / len(returns)) - 1 if len(returns) > 0 else 0
    
    # 风险
    excess_returns = returns - benchmark_returns
    sharpe_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(252) if excess_returns.std() > 0 else 0
    
    # 最大回撤
    cumret = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumret)
    drawdown = (cumret - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # 交易效率
    trade_returns = [t['return'] for t in trades if 'return' in t]
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    win_rate = len(wins) / len(trade_returns) if trade_returns else 0
    profit_loss_ratio = abs(np.mean(wins)) / abs(np.mean(losses)) if losses and wins else 0
    avg_hold_days = np.mean([t.get('hold_days', 5) for t in trades]) if trades else 5
    
    # IC/IR
    ic = np.corrcoef(returns[:-1], returns[1:])[0, 1] if len(returns) > 1 else 0
    
    # 统计显著性
    t_stat, p_value = stats.ttest_1samp(returns, 0)
    confidence = (1 - p_value) * 100 if p_value else 0
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'profit_loss_ratio': profit_loss_ratio,
        'trade_count': len(trades),
        'avg_hold_days': avg_hold_days,
        'ic': abs(ic) if not np.isnan(ic) else 0,
        'ir': abs(ic) if not np.isnan(ic) else 0,
        't_statistic': t_stat,
        'p_value': p_value,
        'confidence': confidence,
    }


def run_single_backtest(etf_data: dict, params: dict) -> dict:
    """单次回测"""
    strat = MACDStrategy()
    strat.etf_data = etf_data
    
    # 使用默认策略参数
    stop_loss = params.get('stop_loss', 0.06)
    take_profit = params.get('take_profit', 0.12)
    max_hold_days = params.get('max_hold_days', 5)
    
    results = strat.backtest(
        etf_data,
        start_date='2021-05-01',
        end_date='2026-05-29'
    )
    
    return results


def main():
    # 加载实验结果
    all_results = []
    for f in sorted(Path('data/experiments').glob('round*.json')):
        with open(f) as fp:
            data = json.load(fp)
            if isinstance(data, dict) and 'results' in data:
                all_results.extend(data['results'])
    
    # 去重
    seen = set()
    unique = []
    for r in all_results:
        name = r['factor_name']
        if name not in seen and r.get('test_return', 0) != 0:
            seen.add(name)
            unique.append(r)
    
    # 按测试收益排序，取Top20
    sorted_results = sorted(unique, key=lambda x: x.get('test_return', 0), reverse=True)
    candidates = sorted_results[:20]
    
    # 加载ETF数据
    logger.info("加载ETF数据...")
    loader = ETFListLoader()
    etf_pool = loader.load()
    etf_data = DataLoader().load(etf_pool)
    logger.info(f"加载了 {len(etf_data)} 只ETF数据")
    
    # 对每个候选模型计算完整指标
    top5_with_full_metrics = []
    
    for r in candidates:
        params = parse_params(r['factor_name'])
        metrics = run_single_backtest(etf_data, params)
        
        if metrics and metrics.get('trade_count', 0) > 0:
            top5_with_full_metrics.append({
                'name': r['factor_name'],
                'original': r,
                'metrics': metrics['metrics']
            })
        
        if len(top5_with_full_metrics) >= 5:
            break
    
    # 输出结果
    print('=' * 130)
    print('🏆 Top 5 模型完整指标对比')
    print('=' * 130)
    print(f"{'排名':<4} {'模型名称':<35} {'测试收益':>8} {'年化':>8} {'夏普':>6} {'回撤':>8} {'胜率':>6} {'盈亏比':>7} {'交易数':>6} {'持仓':>5} {'IC':>6} {'IR':>6} {'p值':>8}")
    print('-' * 130)
    
    for i, item in enumerate(top5_with_full_metrics, 1):
        m = item['metrics']
        name = item['name'][:33]
        print(f"{i:<4} {name:<35} {m['total_return']:>7.1%} {m['annual_return']:>7.1%} {m['sharpe_ratio']:>6.2f} {m['max_drawdown']:>8.1%} {m['win_rate']:>6.1%} {m['profit_loss_ratio']:>7.2f} {m['trade_count']:>6d} {m['avg_hold_days']:>5.1f} {m['ic']:>6.3f} {m['ir']:>6.2f} {m['p_value']:>8.4f}")
    
    print()
    print('【指标说明】')
    print('-' * 130)
    print('''
一、核心收益指标
  测试收益   回测期收益，越高越好
  年化       年化收益率
  夏普比率   (Rp-Rf)/σp，>0.5为佳，衡量风险调整收益

二、交易效率指标
  回撤       最大亏损幅度，>-15%为佳
  胜率       盈利交易占比，>40%为佳
  盈亏比     平均盈利/平均亏损，>1.2为佳
  交易数     总交易次数
  持仓       平均持仓天数

三、稳定性指标
  IC         Information Coefficient，>0.03为佳，衡量因子预测力
  IR         Information Ratio，>0.5为佳，衡量因子稳定性

四、统计显著性
  p值        <0.05为显著，<0.01为高度显著
''')


if __name__ == '__main__':
    main()