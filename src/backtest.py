#!/usr/bin/env python3
"""回测引擎"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import sys

from .config import StrategyConfig
from .selector import Selector
from .market_filter import MarketFilter


class BacktestResult:
    """回测结果"""
    
    def __init__(self):
        self.return_pct: float = 0.0      # 总收益率(%)
        self.drawdown_pct: float = 0.0    # 最大回撤(%)
        self.winrate: float = 0.0         # 胜率(%)
        self.trade_count: int = 0         # 交易次数
        self.equity_curve: List[float] = []  # 净值曲线
    
    def to_dict(self) -> Dict:
        return {
            'return': self.return_pct,
            'drawdown': self.drawdown_pct,
            'winrate': self.winrate,
            'trades': self.trade_count,
            'equity_curve': self.equity_curve,
        }
    
    def __repr__(self):
        return (f"BacktestResult(return={self.return_pct:+.1f}%, "
                f"drawdown={self.drawdown_pct:.1f}%, "
                f"winrate={self.winrate:.1f}%, "
                f"trades={self.trade_count})")


def run_backtest(
    data: Dict[str, pd.DataFrame],
    config: StrategyConfig,
    test_start: str,
    test_end: str,
    market_filter: Optional[MarketFilter] = None,
) -> Dict:
    """运行回测
    
    Args:
        data: ETF数据（已计算指标）
        config: 策略配置
        test_start: 测试开始日期
        test_end: 测试结束日期
        market_filter: 市场过滤器（可选）
        
    Returns:
        回测结果字典:
        {
            'return': 总收益率(%),
            'drawdown': 最大回撤(%),
            'winrate': 胜率(%),
            'trades': 交易次数,
            'equity_curve': [净值...]
        }
    """
    
    # 获取所有交易日
    all_dates = sorted(set(
        d for df in data.values() 
        for d in df['date'] 
        if test_start <= d <= test_end
    ))
    
    if len(all_dates) < 10:
        print("警告: 测试期交易日太少")
        return {'return': 0, 'drawdown': 0, 'winrate': 0, 'trades': 0, 'equity_curve': []}
    
    # 初始化
    selector = Selector()
    holdings: Dict[str, dict] = {}  # {code: {'cost': float, 'entry_idx': int, 'shares': float}}
    equity = 1.0
    trades: List[dict] = []
    equity_history: List[float] = [1.0]
    
    # 首次买入
    first_date = all_dates[0]
    candidates = []
    for code, df in data.items():
        s, _ = selector.score(df, first_date)
        if s >= config.score_threshold:
            row = df[df['date'] == first_date]
            if len(row) > 0:
                candidates.append((code, s, row.iloc[0]['close']))
    
    if len(candidates) >= config.hold_count:
        candidates.sort(key=lambda x: -x[1])
        for i, (code, s, price) in enumerate(candidates[:config.hold_count]):
            w = config.weights[i] if i < len(config.weights) else 0.5
            shares = (equity * w) / price
            holdings[code] = {'cost': price, 'entry_idx': 0, 'shares': shares}
            trades.append({'date': first_date, 'code': code, 'action': 'buy', 'score': s})
    
    # 主循环
    for date_idx, date in enumerate(all_dates):
        # 记录当前净值 (现金 + 持仓)
        if holdings:
            portfolio_value = sum(
                pos['shares'] * data[code][data[code]['date'] == date].iloc[0]['close']
                for code, pos in holdings.items()
                if len(data[code][data[code]['date'] == date]) > 0
            )
        else:
            portfolio_value = equity
        equity_history.append(portfolio_value)
        
        # 止损/止盈/超时检查
        to_close = []
        for code, pos in list(holdings.items()):
            row = data[code][data[code]['date'] == date]
            if len(row) == 0:
                continue
            
            current_price = row.iloc[0]['close']
            pnl = (current_price - pos['cost']) / pos['cost']
            
            if pnl <= config.stop_loss:
                to_close.append((code, '止损', pnl, current_price))
            elif pnl >= config.stop_gain:
                to_close.append((code, '止盈', pnl, current_price))
            elif date_idx - pos['entry_idx'] >= config.max_hold_days:
                to_close.append((code, '超时', pnl, current_price))
        
        # 执行卖出
        for code, reason, pnl, price in to_close:
            if code in holdings:
                equity *= (1 + pnl) * (1 - config.fee_rate)
                trades.append({
                    'date': date, 
                    'code': code, 
                    'action': 'sell', 
                    'pnl': pnl, 
                    'reason': reason
                })
                del holdings[code]
                equity_history.append(equity)
        
        # 市场过滤清仓
        if market_filter and not market_filter.is_bullish(date):
            for code in list(holdings.keys()):
                row = data[code][data[code]['date'] == date]
                if len(row) > 0:
                    price = row.iloc[0]['close']
                    pnl = (price - holdings[code]['cost']) / holdings[code]['cost']
                    equity *= (1 + pnl) * (1 - config.fee_rate)
                    trades.append({
                        'date': date, 
                        'code': code, 
                        'action': 'sell', 
                        'pnl': pnl, 
                        'reason': '市场过滤'
                    })
                    del holdings[code]
                    equity_history.append(equity)
            continue
        
        # 调仓
        if date_idx % config.rebalance_days == 0:
            candidates = []
            for code, df in data.items():
                s, _ = selector.score(df, date)
                if s >= config.score_threshold:
                    row = df[df['date'] == date]
                    if len(row) > 0:
                        candidates.append((code, s, row.iloc[0]['close']))
            
            if len(candidates) >= config.hold_count:
                candidates.sort(key=lambda x: -x[1])
                top_codes = {c[0] for c in candidates[:config.hold_count]}
                
                # 卖出不在Top的
                for code in list(holdings.keys()):
                    if code not in top_codes:
                        row = data[code][data[code]['date'] == date]
                        if len(row) > 0:
                            price = row.iloc[0]['close']
                            pnl = (price - holdings[code]['cost']) / holdings[code]['cost']
                            equity *= (1 + pnl) * (1 - config.fee_rate)
                            trades.append({
                                'date': date, 
                                'code': code, 
                                'action': 'sell', 
                                'pnl': pnl, 
                                'reason': '调出'
                            })
                            del holdings[code]
                            equity_history.append(equity)
                
                # 买入Top
                for i, (code, s, price) in enumerate(candidates[:config.hold_count]):
                    if code not in holdings:
                        w = config.weights[i] if i < len(config.weights) else 0.5
                        shares = (equity * w) / price
                        holdings[code] = {'cost': price, 'entry_idx': date_idx, 'shares': shares}
                        trades.append({'date': date, 'code': code, 'action': 'buy', 'score': s})
    
    # 最终结算
    final_date = all_dates[-1]
    if holdings:
        final_pv = sum(
            pos['shares'] * data[code][data[code]['date'] == final_date].iloc[0]['close']
            for code, pos in holdings.items()
            if len(data[code][data[code]['date'] == final_date]) > 0
        )
    else:
        final_pv = equity
    
    equity = final_pv
    
    # 计算指标
    total_return = (equity - 1) * 100
    
    # 最大回撤
    equity_arr = np.array(equity_history)
    equity_arr = np.maximum(equity_arr, 0.01)  # 防止除零
    peak = np.maximum.accumulate(equity_arr)
    dd = (equity_arr - peak) / peak
    max_dd = dd.min() * 100
    
    # 胜率
    sells = [t for t in trades if t['action'] == 'sell' and 'pnl' in t]
    wins = sum(1 for t in sells if t['pnl'] > 0)
    win_rate = wins / len(sells) * 100 if sells else 0
    
    return {
        'return': round(total_return, 1),
        'drawdown': round(max_dd, 1),
        'winrate': round(win_rate, 1),
        'trades': len(sells),
        'equity_curve': equity_history
    }


__all__ = ['run_backtest', 'BacktestResult']