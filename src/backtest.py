#!/usr/bin/env python3
"""回测引擎 - 使用拆分后的模块"""
import pandas as pd
from typing import Dict, Optional

from .config import StrategyConfig
from .selector import Selector
from .market_filter import MarketFilter
from .trade import TradeExecutor
from .metrics import calculate_metrics
from .trading_cost import apply_trading_cost


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
        market_filter: 市场过滤器
        
    Returns:
        回测结果字典
    """
    # 获取所有交易日
    all_dates = sorted(set(
        d for df in data.values() 
        for d in df['date'] 
        if test_start <= d <= test_end
    ))
    
    if len(all_dates) < 10:
        return _empty_result()
    
    # 初始化交易执行器
    executor = TradeExecutor(config)
    selector = Selector()
    
    # 初始化
    equity_history = [1.0]
    holding_dates = set()
    
    # 首次买入 - 等待市场上涨
    first_date = all_dates[0]
    market_ok = not market_filter or market_filter.is_bullish(first_date)
    
    if market_ok:
        candidates = []
        exclude_codes = config.exclude_codes or set()
        for code, df in data.items():
            if code in exclude_codes:
                continue
            s, _ = selector.evaluate(df, first_date)
            if s >= config.score_threshold:
                row = df[df['date'] == first_date]
                if len(row) > 0:
                    candidates.append((code, s, row.iloc[0]['close']))
        
        if len(candidates) >= config.hold_count:
            candidates.sort(key=lambda x: -x[1])
            for i, (code, s, price) in enumerate(candidates[:config.hold_count]):
                # 应用滑点 (买入时价格更高)
                if config.enable_slippage:
                    trade_value = executor.equity * (config.weights[i] if i < len(config.weights) else 0.5)
                    price = apply_trading_cost(price, trade_value, side='buy')
                
                w = config.weights[i] if i < len(config.weights) else 0.5
                shares = (executor.equity * w) / price
                executor.holdings[code] = {
                    'cost': price,
                    'entry_idx': 0,
                    'entry_date': first_date,
                    'shares': shares
                }
                executor.trades.append({
                    'date': first_date, 
                    'code': code, 
                    'action': 'buy', 
                    'score': s
                })
                holding_dates.add(first_date)
    
    # 主循环
    for date_idx, date in enumerate(all_dates):
        # 处理当日交易
        executor.process_day(date, date_idx, all_dates, data, market_filter, holding_dates)
        
        # 记录净值
        equity_value = executor.get_equity(date, data)
        equity_history.append(equity_value)
        
        # 记录持仓日
        if executor.holdings:
            holding_dates.add(date)
    
    # 最终结算
    final_date = all_dates[-1]
    if executor.holdings:
        final_pv = sum(
            pos['shares'] * data[code][data[code]['date'] == final_date].iloc[0]['close']
            for code, pos in executor.holdings.items()
            if len(data[code][data[code]['date'] == final_date]) > 0
        )
        executor.equity = final_pv
    
    # 计算指标
    metrics = calculate_metrics(
        equity=executor.equity,
        equity_history=equity_history,
        trades=executor.trades,
        all_dates=all_dates,
        holding_dates=holding_dates,
    )
    
    return metrics


def _empty_result() -> Dict:
    return {
        'return': 0, 'annual_return': 0, 'drawdown': 0,
        'calmar': 0, 'sharpe': 0, 'winrate': 0, 'profit_loss_ratio': 0,
        'trades': 0, 'avg_hold_days': 0, 'max_profit': 0, 'max_loss': 0,
        'trade_days_ratio': 0, 'equity_curve': []
    }


__all__ = ['run_backtest']