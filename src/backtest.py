#!/usr/bin/env python3
"""回测引擎 - 完整指标版本"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import math

from .config import StrategyConfig
from .selector import Selector
from .market_filter import MarketFilter


class BacktestResult:
    """回测结果"""
    
    def __init__(self):
        self.return_pct: float = 0.0       # 总收益率(%)
        self.annual_return: float = 0.0    # 年化收益率(%)
        self.drawdown_pct: float = 0.0     # 最大回撤(%)
        self.calmar: float = 0.0           # 卡玛比率
        self.sharpe: float = 0.0           # 夏普比率
        self.winrate: float = 0.0          # 胜率(%)
        self.profit_loss_ratio: float = 0.0  # 盈亏比
        self.trade_count: int = 0          # 交易次数
        self.avg_hold_days: float = 0.0    # 平均持仓天数
        self.max_profit: float = 0.0       # 最大单笔盈利(%)
        self.max_loss: float = 0.0         # 最大单笔亏损(%)
        self.trade_days_ratio: float = 0.0  # 持仓天数占比(%)
        self.equity_curve: List[float] = []  # 净值曲线
    
    def to_dict(self) -> Dict:
        return {
            'return': self.return_pct,
            'annual_return': self.annual_return,
            'drawdown': self.drawdown_pct,
            'calmar': round(self.calmar, 2),
            'sharpe': round(self.sharpe, 2),
            'winrate': self.winrate,
            'profit_loss_ratio': round(self.profit_loss_ratio, 2),
            'trades': self.trade_count,
            'avg_hold_days': round(self.avg_hold_days, 1),
            'max_profit': round(self.max_profit * 100, 2),
            'max_loss': round(self.max_loss * 100, 2),
            'trade_days_ratio': round(self.trade_days_ratio, 1),
            'equity_curve': self.equity_curve,
        }
    
    def __repr__(self):
        return (f"BacktestResult(\n"
                f"  收益率: {self.return_pct:+.1f}%\n"
                f"  年化收益: {self.annual_return:+.1f}%\n"
                f"  最大回撤: {self.drawdown_pct:.1f}%\n"
                f"  卡玛比率: {self.calmar:.2f}\n"
                f"  夏普比率: {self.sharpe:.2f}\n"
                f"  胜率: {self.winrate:.1f}%\n"
                f"  盈亏比: {self.profit_loss_ratio:.2f}\n"
                f"  交易次数: {self.trade_count}\n"
                f"  平均持仓: {self.avg_hold_days:.1f}天\n"
                f"  最大单笔盈利: {self.max_profit*100:+.2f}%\n"
                f"  最大单笔亏损: {self.max_loss*100:.2f}%\n"
                f"  持仓天数占比: {self.trade_days_ratio:.1f}%\n"
                f")")


def run_backtest(
    data: Dict[str, pd.DataFrame],
    config: StrategyConfig,
    test_start: str,
    test_end: str,
    market_filter: Optional[MarketFilter] = None,
) -> Dict:
    """运行回测 - 完整指标版"""
    
    # 获取所有交易日
    all_dates = sorted(set(
        d for df in data.values() 
        for d in df['date'] 
        if test_start <= d <= test_end
    ))
    
    if len(all_dates) < 10:
        return _empty_result()
    
    # 初始化
    selector = Selector()
    holdings: Dict[str, dict] = {}  # {code: {'cost': float, 'entry_idx': int, 'shares': float, 'entry_date': str}}
    equity = 1.0
    trades: List[dict] = []
    equity_history: List[float] = [1.0]
    
    # 持仓日期记录
    holding_dates = set()  # 记录有持仓的日期
    
    # 首次买入 - 需要等待市场上涨 (修复bug:不可以在市场下跌时买入)
    # 策略: 等第一次市场上涨+满足选股条件再买入
    first_buy_done = False  # 标记是否完成首次买入
    
    # 冷却期: 市场过滤后等待N天再入场 (防止反复被割)
    cooldown_days = 5  # 冷却5天
    last_market_filter_trigger = -999  # 上次市场过滤触发的日期索引
    
    # 主循环
    for date_idx, date in enumerate(all_dates):
        
        # 记录当前净值 (现金 + 持仓)
        if holdings:
            portfolio_value = sum(
                pos['shares'] * data[code][data[code]['date'] == date].iloc[0]['close']
                for code, pos in holdings.items()
                if len(data[code][data[code]['date'] == date]) > 0
            )
            holding_dates.add(date)
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
            
            # 记录持仓天数
            entry_date = pos['entry_date']
            hold_days = date_idx - pos['entry_idx']
            
            if pnl <= config.stop_loss:
                to_close.append((code, '止损', pnl, current_price, hold_days))
            elif pnl >= config.stop_gain:
                to_close.append((code, '止盈', pnl, current_price, hold_days))
            elif date_idx - pos['entry_idx'] >= config.max_hold_days:
                to_close.append((code, '超时', pnl, current_price, hold_days))
        
        # 执行卖出
        for code, reason, pnl, price, hold_days in to_close:
            if code in holdings:
                equity *= (1 + pnl) * (1 - config.fee_rate)
                trades.append({
                    'date': date, 
                    'code': code, 
                    'action': 'sell', 
                    'pnl': pnl, 
                    'reason': reason,
                    'hold_days': hold_days,
                })
                del holdings[code]
                equity_history.append(equity)
        
        # 市场过滤清仓
        if market_filter and not market_filter.is_bullish(date):
            # 触发冷却期
            last_market_filter_trigger = date_idx
            
            for code in list(holdings.keys()):
                row = data[code][data[code]['date'] == date]
                if len(row) > 0:
                    price = row.iloc[0]['close']
                    pnl = (price - holdings[code]['cost']) / holdings[code]['cost']
                    hold_days = date_idx - holdings[code]['entry_idx']
                    equity *= (1 + pnl) * (1 - config.fee_rate)
                    trades.append({
                        'date': date, 
                        'code': code, 
                        'action': 'sell', 
                        'pnl': pnl, 
                        'reason': '市场过滤',
                        'hold_days': hold_days,
                    })
                    del holdings[code]
                    equity_history.append(equity)
            # 不再continue！允许同一天或第二天重新入场
            
            # 如果没有持仓，尝试重新入场（但要等冷却期 + 市场上涨）
            market_ok = not market_filter or market_filter.is_bullish(date)
            if not holdings and market_ok and (date_idx - last_market_filter_trigger) >= cooldown_days:
                candidates = []
                for code, df in data.items():
                    s, _ = selector.score(df, date)
                    if s >= config.score_threshold:
                        row = df[df['date'] == date]
                        if len(row) > 0:
                            candidates.append((code, s, row.iloc[0]['close']))
                
                if len(candidates) >= config.hold_count:
                    candidates.sort(key=lambda x: -x[1])
                    for i, (code, s, price) in enumerate(candidates[:config.hold_count]):
                        w = config.weights[i] if i < len(config.weights) else 0.5
                        shares = (equity * w) / price
                        holdings[code] = {
                            'cost': price, 
                            'entry_idx': date_idx,
                            'entry_date': date,
                            'shares': shares
                        }
                        trades.append({'date': date, 'code': code, 'action': 'buy', 'score': s, 'from': 'reentry'})
                        holding_dates.add(date)
        
        # 调仓 - 只有在市场上涨时才调仓
        market_ok = not market_filter or market_filter.is_bullish(date)
        if market_ok and date_idx % config.rebalance_days == 0:
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
                            hold_days = date_idx - holdings[code]['entry_idx']
                            equity *= (1 + pnl) * (1 - config.fee_rate)
                            trades.append({
                                'date': date, 
                                'code': code, 
                                'action': 'sell', 
                                'pnl': pnl, 
                                'reason': '调出',
                                'hold_days': hold_days,
                            })
                            del holdings[code]
                            equity_history.append(equity)
                
                # 买入Top
                for i, (code, s, price) in enumerate(candidates[:config.hold_count]):
                    if code not in holdings:
                        w = config.weights[i] if i < len(config.weights) else 0.5
                        shares = (equity * w) / price
                        holdings[code] = {
                            'cost': price, 
                            'entry_idx': date_idx,
                            'entry_date': date,
                            'shares': shares
                        }
                        trades.append({'date': date, 'code': code, 'action': 'buy', 'score': s})
                        holding_dates.add(date)
    
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
    
    # ==================== 计算完整指标 ====================
    
    total_return = (equity - 1) * 100
    
    # 年化收益率 (考虑实际交易日)
    trading_days = len(all_dates)
    years = trading_days / 252  # 年化
    annual_return = ((equity ** (1/years)) - 1) * 100 if years > 0 else 0
    
    # 最大回撤
    equity_arr = np.array(equity_history)
    equity_arr = np.maximum(equity_arr, 0.01)
    peak = np.maximum.accumulate(equity_arr)
    dd = (equity_arr - peak) / peak
    max_dd = dd.min() * 100
    
    # 卡玛比率 = 年化收益 / 最大回撤
    calmar = abs(annual_return / max_dd) if max_dd != 0 else 0
    
    # 夏普比率 = (年化收益 - 无风险利率) / 年化波动率
    # 简化版: 年化收益 / 年化波动率
    daily_returns = np.diff(equity_arr) / equity_arr[:-1]
    daily_returns = daily_returns[np.isfinite(daily_returns)]
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe = (annual_return / 100) / (daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0
    
    # 胜率 & 盈亏比
    sells = [t for t in trades if t['action'] == 'sell' and 'pnl' in t]
    wins = [t['pnl'] for t in sells if t['pnl'] > 0]
    losses = [t['pnl'] for t in sells if t['pnl'] <= 0]
    
    win_rate = len(wins) / len(sells) * 100 if sells else 0
    
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    # 最大单笔
    max_profit = max(wins) if wins else 0
    max_loss = min(losses) if losses else 0
    
    # 平均持仓天数
    hold_days_list = [t.get('hold_days', 0) for t in sells]
    avg_hold_days = np.mean(hold_days_list) if hold_days_list else 0
    
    # 持仓天数占比
    trade_days_ratio = len(holding_dates) / len(all_dates) * 100 if all_dates else 0
    
    return {
        # 收益指标
        'return': round(total_return, 1),
        'annual_return': round(annual_return, 1),
        # 风险指标
        'drawdown': round(max_dd, 1),
        'calmar': round(calmar, 2),
        'sharpe': round(sharpe, 2),
        # 交易指标
        'winrate': round(win_rate, 1),
        'profit_loss_ratio': round(profit_loss_ratio, 2),
        'trades': len(sells),
        'avg_hold_days': round(avg_hold_days, 1),
        'max_profit': round(max_profit * 100, 2),
        'max_loss': round(max_loss * 100, 2),
        'trade_days_ratio': round(trade_days_ratio, 1),
        # 净值曲线
        'equity_curve': equity_history,
    }


def _empty_result() -> Dict:
    return {
        'return': 0, 'annual_return': 0, 'drawdown': 0,
        'calmar': 0, 'sharpe': 0, 'winrate': 0, 'profit_loss_ratio': 0,
        'trades': 0, 'avg_hold_days': 0, 'max_profit': 0, 'max_loss': 0,
        'trade_days_ratio': 0, 'equity_curve': []
    }


__all__ = ['run_backtest', 'BacktestResult']