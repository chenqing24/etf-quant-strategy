"""重新测试Exp36和Exp48，比较允许调仓 vs 禁止调仓的效果"""
import sys
sys.path.insert(0, '.')

from src.strategy.store import quick_run, ExperimentStore
from src.strategy.config import ExperimentConfig, FactorStrategy, BacktestConfig, DataConfig, ScoreConfig
from src.data.database import Database
from src.indicators.wrapper import IndicatorCalculator, calculate_returns
from datetime import datetime
from collections import Counter
import json


def test_exp36_with_rebalance():
    """Exp36 允许调仓 (原配置)"""
    print("=" * 70)
    print("Exp36: 允许调仓 (原配置)")
    print("=" * 70)
    
    r = quick_run(
        name='Exp36: 允许调仓',
        factors=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
        weights={'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15},
        direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'},
        stop_loss=-0.05, stop_profit=0.10, threshold=0.8, hold_days=3,
        allow_rebalance=True
    )
    
    avg_hold = _calc_avg_hold_days(r['train'].trade_list)
    
    print(f"Train: {r['train'].total_return:.1%} 夏普={r['train'].sharpe_ratio:.2f} 交易={r['train'].trade_count} 平均持仓={avg_hold:.1f}天")
    print(f"Test:  {r['test'].total_return:.1%} 夏普={r['test'].sharpe_ratio:.2f} 交易={r['test'].trade_count}")
    
    return r


def test_exp36_without_rebalance():
    """Exp36 禁止调仓 (修复后配置)"""
    print("\n" + "=" * 70)
    print("Exp36: 禁止调仓 (修复后)")
    print("=" * 70)
    
    r = quick_run(
        name='Exp36: 禁止调仓',
        factors=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
        weights={'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15},
        direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'},
        stop_loss=-0.05, stop_profit=0.10, threshold=0.8, hold_days=3,
        allow_rebalance=False  # 禁止调仓
    )
    
    avg_hold = _calc_avg_hold_days(r['train'].trade_list)
    
    print(f"Train: {r['train'].total_return:.1%} 夏普={r['train'].sharpe_ratio:.2f} 交易={r['train'].trade_count} 平均持仓={avg_hold:.1f}天")
    print(f"Test:  {r['test'].total_return:.1%} 夏普={r['test'].sharpe_ratio:.2f} 交易={r['test'].trade_count}")
    
    return r


def test_exp48_with_rebalance():
    """Exp48 允许调仓 (原配置)"""
    print("\n" + "=" * 70)
    print("Exp48: 允许调仓 (原配置)")
    print("=" * 70)
    
    r = quick_run(
        name='Exp48: 允许调仓',
        factors=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
        weights={'ADX': 0.25, 'BB_percent': 0.25, 'SAR_trend': 0.25, 'OBV_diff': 0.25},
        direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'},
        stop_loss=-0.05, stop_profit=0.10, threshold=0.8, hold_days=3,
        allow_rebalance=True
    )
    
    avg_hold = _calc_avg_hold_days(r['train'].trade_list)
    
    print(f"Train: {r['train'].total_return:.1%} 夏普={r['train'].sharpe_ratio:.2f} 交易={r['train'].trade_count} 平均持仓={avg_hold:.1f}天")
    print(f"Test:  {r['test'].total_return:.1%} 夏普={r['test'].sharpe_ratio:.2f} 交易={r['test'].trade_count}")
    
    return r


def test_exp48_without_rebalance():
    """Exp48 禁止调仓 (修复后配置)"""
    print("\n" + "=" * 70)
    print("Exp48: 禁止调仓 (修复后)")
    print("=" * 70)
    
    r = quick_run(
        name='Exp48: 禁止调仓',
        factors=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
        weights={'ADX': 0.25, 'BB_percent': 0.25, 'SAR_trend': 0.25, 'OBV_diff': 0.25},
        direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'},
        stop_loss=-0.05, stop_profit=0.10, threshold=0.8, hold_days=3,
        allow_rebalance=False  # 禁止调仓
    )
    
    avg_hold = _calc_avg_hold_days(r['train'].trade_list)
    
    print(f"Train: {r['train'].total_return:.1%} 夏普={r['train'].sharpe_ratio:.2f} 交易={r['train'].trade_count} 平均持仓={avg_hold:.1f}天")
    print(f"Test:  {r['test'].total_return:.1%} 夏普={r['test'].sharpe_ratio:.2f} 交易={r['test'].trade_count}")
    
    return r


def _calc_avg_hold_days(trades):
    """计算平均持仓天数"""
    sell_trades = [t for t in trades if t.get('action') == 'sell']
    if not sell_trades:
        return 0
    
    hold_days = []
    for sell in sell_trades:
        code = sell.get('code')
        buy_trade = None
        for t in trades:
            if t.get('code') == code and t.get('action') == 'buy':
                buy_trade = t
                break
        if buy_trade:
            buy_date = datetime.strptime(buy_trade['date'][:10], '%Y-%m-%d')
            sell_date = datetime.strptime(sell['date'][:10], '%Y-%m-%d')
            days = (sell_date - buy_date).days
            hold_days.append(days)
    
    return sum(hold_days) / len(hold_days) if hold_days else 0


def compare_results(r1, r2, name1, name2):
    """比较两组结果"""
    print("\n" + "=" * 70)
    print(f"对比: {name1} vs {name2}")
    print("=" * 70)
    
    print(f"{'指标':<20} {'Train变化':<20} {'Test变化':<20}")
    print("-" * 60)
    print(f"{'收益':<20} {r1['train'].total_return:.1%} → {r2['train'].total_return:.1%} ({r2['train'].total_return/r1['train'].total_return-1:.1%})  {r1['test'].total_return:.1%} → {r2['test'].total_return:.1%} ({r2['test'].total_return/r1['test'].total_return-1:.1%})")
    print(f"{'夏普':<20} {r1['train'].sharpe_ratio:.2f} → {r2['train'].sharpe_ratio:.2f}  {r1['test'].sharpe_ratio:.2f} → {r2['test'].sharpe_ratio:.2f}")
    print(f"{'交易次数':<20} {r1['train'].trade_count} → {r2['train'].trade_count}  {r1['test'].trade_count} → {r2['test'].trade_count}")


if __name__ == '__main__':
    print("测试修复效果: 允许调仓 vs 禁止调仓")
    print("=" * 70)
    
    # Exp36
    r36_with = test_exp36_with_rebalance()
    r36_without = test_exp36_without_rebalance()
    compare_results(r36_with, r36_without, "允许调仓", "禁止调仓")
    
    # Exp48
    r48_with = test_exp48_with_rebalance()
    r48_without = test_exp48_without_rebalance()
    compare_results(r48_with, r48_without, "允许调仓", "禁止调仓")
    
    # 保存结果
    results = {
        'exp36_with': {'train': r36_with['train'].to_dict(), 'test': r36_with['test'].to_dict()},
        'exp36_without': {'train': r36_without['train'].to_dict(), 'test': r36_without['test'].to_dict()},
        'exp48_with': {'train': r48_with['train'].to_dict(), 'test': r48_with['test'].to_dict()},
        'exp48_without': {'train': r48_without['train'].to_dict(), 'test': r48_without['test'].to_dict()},
    }
    
    with open('data/experiments/rebalance_comparison.json', 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 70)
    print("✅ 测试完成，结果已保存")
    print("=" * 70)