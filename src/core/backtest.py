#!/usr/bin/env python3
"""回测引擎 - 支持每日评分和调仓周期"""
import pandas as pd
from typing import Dict, Optional, List, Tuple

from src.utils.config import StrategyConfig
from src.core.selector import Selector
from src.core.market_filter import MarketFilter
from src.core.position import TradeExecutor
from src.analysis.metrics import calculate_metrics
from src.trade.cost import apply_trading_cost


def run_backtest(
    data: Dict[str, pd.DataFrame],
    config: StrategyConfig,
    test_start: str,
    test_end: str,
    market_filter: Optional[MarketFilter] = None,
    allow_oversold: bool = True,
) -> Dict:
    """运行回测 - 每日评分版
    
    特点：
    1. 每日重新评分持仓ETF
    2. 评分低于阈值时触发卖出/调仓
    3. 按调仓周期重新选择标的
    
    Args:
        data: ETF数据（已计算指标）
        config: 策略配置
        test_start: 测试开始日期
        test_end: 测试结束日期
        market_filter: 市场过滤器
        allow_oversold: 是否允许RSI超卖时买入（True=混合策略，False=纯趋势策略）
        
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
    
    # 初始化
    executor = TradeExecutor(config)
    selector = Selector()
    equity_history = [1.0]
    holding_dates = set()
    
    # 调仓计数器
    days_since_rebalance = 0
    
    # 首次买入
    first_date = all_dates[0]
    market_ok = not market_filter or market_filter.is_bullish(first_date)
    
    if market_ok:
        _select_and_buy(executor, selector, data, config, first_date, allow_oversold)
        if executor.holdings:
            holding_dates.add(first_date)
    
    # 主循环
    for date_idx, date in enumerate(all_dates):
        days_since_rebalance += 1
        
        # 1. 每日评分检查 - 检查持仓ETF是否需要卖出
        if executor.holdings:
            holdings_to_close = []
            for code, pos in executor.holdings.items():
                if code not in data:
                    continue
                    
                score, _ = selector.evaluate(data[code], date)
                
                # 评分低于阈值，触发卖出
                if score < config.score_threshold:
                    holdings_to_close.append(code)
                    executor.trades.append({
                        'date': date,
                        'code': code,
                        'action': 'sell',
                        'score': score,
                        'reason': f'评分下降({score}<{config.score_threshold})'
                    })
            
            # 执行卖出
            for code in holdings_to_close:
                _close_position(executor, data, code, date, config)
        
        # 2. 调仓周期检查 - 定期重新选择
        should_rebalance = (
            days_since_rebalance >= config.rebalance_days and
            len(executor.holdings) < config.hold_count
        )
        
        if should_rebalance:
            # 重新选择并买入
            _select_and_buy(executor, selector, data, config, date, allow_oversold)
            days_since_rebalance = 0
        
        # 3. 更新权益
        _update_equity(executor, data, date)
        equity_history.append(executor.equity)
        
        if executor.holdings:
            holding_dates.add(date)
    
    # 最终结算
    _final_settlement(executor, data, all_dates[-1])
    
    # 计算指标
    metrics = calculate_metrics(
        equity=executor.equity,
        equity_history=equity_history,
        trades=executor.trades,
        all_dates=all_dates,
        holding_dates=holding_dates,
    )
    
    return metrics


def _select_and_buy(
    executor: TradeExecutor,
    selector: Selector,
    data: Dict[str, pd.DataFrame],
    config: StrategyConfig,
    date: str,
    allow_oversold: bool = True,
) -> None:
    """选择ETF并买入
    
    Args:
        allow_oversold: 是否允许RSI超卖时买入（True=混合策略，False=纯趋势策略）
    """
    if len(executor.holdings) >= config.hold_count:
        return
    
    # 获取候选ETF
    candidates = []
    exclude_codes = config.exclude_codes or set()
    exclude_codes.update(executor.holdings.keys())  # 排除已持仓
    
    for code, df in data.items():
        if code in exclude_codes:
            continue
        if len(df[df['date'] == date]) == 0:
            continue
            
        score, _ = selector.evaluate(df, date)
        if score >= config.score_threshold:
            row = df[df['date'] == date].iloc[0]
            rsi = row['rsi_14']
            
            # 纯趋势策略：RSI<30 不买入
            if not allow_oversold and rsi < 30:
                continue
            
            candidates.append((code, score, row['close']))
    
    # 排序并买入
    candidates.sort(key=lambda x: -x[1])
    slots_available = config.hold_count - len(executor.holdings)
    
    for i, (code, score, price) in enumerate(candidates[:slots_available]):
        # 应用滑点
        if config.enable_slippage:
            w = config.weights[i] if i < len(config.weights) else 0.5
            trade_value = executor.equity * w
            price = apply_trading_cost(price, trade_value, side='buy')
        
        w = config.weights[i] if i < len(config.weights) else 0.5
        shares = (executor.equity * w) / price
        
        executor.holdings[code] = {
            'cost': price,
            'entry_idx': 0,
            'entry_date': date,
            'shares': shares
        }
        executor.trades.append({
            'date': date,
            'code': code,
            'action': 'buy',
            'score': score
        })


def _close_position(
    executor: TradeExecutor,
    data: Dict[str, pd.DataFrame],
    code: str,
    date: str,
    config: StrategyConfig
) -> None:
    """平仓"""
    if code not in executor.holdings:
        return
    
    pos = executor.holdings[code]
    df = data.get(code)
    if df is None or len(df[df['date'] == date]) == 0:
        del executor.holdings[code]
        return
    
    price = df[df['date'] == date].iloc[0]['close']
    
    # 应用滑点(卖出时价格更低)
    if config.enable_slippage:
        trade_value = pos['shares'] * price
        price = apply_trading_cost(price, trade_value, side='sell')
    
    # 计算收益
    cost = pos['cost']
    pnl = (price - cost) / cost
    
    # 更新权益
    executor.equity *= (1 + pnl * (pos['shares'] * cost / executor.equity))
    
    # 记录卖出
    executor.trades.append({
        'date': date,
        'code': code,
        'action': 'sell',
        'price': price,
        'cost': cost,
        'pnl': pnl,
        'hold_days': (pd.to_datetime(date) - pd.to_datetime(pos['entry_date'])).days
    })
    
    del executor.holdings[code]


def _update_equity(
    executor: TradeExecutor,
    data: Dict[str, pd.DataFrame],
    date: str
) -> None:
    """更新组合权益"""
    total_value = executor.equity
    
    # 不更新权益，只记录持仓状态
    # 实际权益在卖出时计算


def _final_settlement(
    executor: TradeExecutor,
    data: Dict[str, pd.DataFrame],
    final_date: str
) -> None:
    """最终结算"""
    if not executor.holdings:
        return
    
    # 清空所有持仓，计算最终收益
    codes_to_close = list(executor.holdings.keys())
    for code in codes_to_close:
        _close_position(executor, data, code, final_date, StrategyConfig())


def _empty_result() -> Dict:
    return {
        'return': 0, 'annual_return': 0, 'drawdown': 0,
        'calmar': 0, 'sharpe': 0, 'winrate': 0, 'profit_loss_ratio': 0,
        'trades': 0, 'avg_hold_days': 0, 'max_profit': 0, 'max_loss': 0,
        'trade_days_ratio': 0, 'equity_curve': []
    }


__all__ = ['run_backtest']