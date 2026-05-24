#!/usr/bin/env python3
"""指标计算"""
import numpy as np
from typing import List, Dict


def calculate_metrics(
    equity: float,
    equity_history: List[float],
    trades: List[dict],
    all_dates: List[str],
    holding_dates: set,
) -> Dict:
    """计算完整回测指标
    
    Args:
        equity: 最终净值
        equity_history: 净值曲线
        trades: 交易记录
        all_dates: 所有交易日
        holding_dates: 有持仓的日期集合
    """
    # ========== 收益率 ==========
    total_return = (equity - 1) * 100
    
    # 年化收益率
    trading_days = len(all_dates)
    years = trading_days / 252
    annual_return = ((equity ** (1/years)) - 1) * 100 if years > 0 else 0
    
    # ========== 最大回撤 ==========
    equity_arr = np.array(equity_history)
    equity_arr = np.maximum(equity_arr, 0.01)
    peak = np.maximum.accumulate(equity_arr)
    dd = (equity_arr - peak) / peak
    max_dd = dd.min() * 100
    
    # ========== 风险调整指标 ==========
    # 卡玛比率 = 年化收益 / 最大回撤
    calmar = abs(annual_return / max_dd) if max_dd != 0 else 0
    
    # 夏普比率
    daily_returns = np.diff(equity_arr) / equity_arr[:-1]
    daily_returns = daily_returns[np.isfinite(daily_returns)]
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (annual_return / 100) / (daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0
    
    # ========== 交易统计 ==========
    sells = [t for t in trades if t['action'] == 'sell' and 'pnl' in t]
    wins = [t['pnl'] for t in sells if t['pnl'] > 0]
    losses = [t['pnl'] for t in sells if t['pnl'] <= 0]
    
    win_rate = len(wins) / len(sells) * 100 if sells else 0
    
    # 盈亏比
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    # 平均持仓天数
    hold_days_list = [t.get('hold_days', 0) for t in sells]
    avg_hold_days = np.mean(hold_days_list) if hold_days_list else 0
    
    # 最大单笔
    max_profit = max(wins) if wins else 0
    max_loss = min(losses) if losses else 0
    
    # 持仓天数占比
    trade_days_ratio = len(holding_dates) / len(all_dates) * 100 if all_dates else 0
    
    return {
        # 收益
        'return': round(total_return, 1),
        'annual_return': round(annual_return, 1),
        # 风险
        'drawdown': round(max_dd, 1),
        'calmar': round(calmar, 2),
        'sharpe': round(sharpe, 2),
        # 交易
        'winrate': round(win_rate, 1),
        'profit_loss_ratio': round(profit_loss_ratio, 2),
        'trades': len(sells),
        'avg_hold_days': round(avg_hold_days, 1),
        'max_profit': round(max_profit * 100, 2),
        'max_loss': round(max_loss * 100, 2),
        'trade_days_ratio': round(trade_days_ratio, 1),
        # 曲线
        'equity_curve': equity_history,
    }


def print_metrics(m: Dict) -> None:
    """打印指标"""
    print(f"\n{'='*60}")
    print(f"回测结果")
    print(f"{'='*60}")
    
    print(f"\n【收益指标】")
    print(f"  总收益率:     {m['return']:+.1f}%")
    print(f"  年化收益率:   {m['annual_return']:+.1f}%")
    
    print(f"\n【风险指标】")
    print(f"  最大回撤:     {m['drawdown']:.1f}%")
    print(f"  卡玛比率:     {m['calmar']:.2f}")
    print(f"  夏普比率:     {m['sharpe']:.2f}")
    
    print(f"\n【交易指标】")
    print(f"  交易次数:     {m['trades']}")
    print(f"  胜率:         {m['winrate']:.1f}%")
    print(f"  盈亏比:       {m['profit_loss_ratio']:.2f}")
    print(f"  平均持仓天数: {m['avg_hold_days']:.1f}天")
    print(f"  最大单笔盈利: {m['max_profit']:+.2f}%")
    print(f"  最大单笔亏损: {m['max_loss']:.2f}%")
    print(f"  持仓天数占比: {m['trade_days_ratio']:.1f}%")


__all__ = ['calculate_metrics', 'print_metrics']