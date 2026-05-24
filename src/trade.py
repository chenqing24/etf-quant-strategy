#!/usr/bin/env python3
"""交易执行逻辑"""
import pandas as pd
from typing import Dict, List, Tuple, Optional

from .config import StrategyConfig
from .selector import Selector
from .market_filter import MarketFilter


class TradeExecutor:
    """交易执行器"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.selector = Selector()
        self.holdings: Dict[str, dict] = {}
        self.equity = 1.0
        self.trades: List[dict] = []
        
        # 冷却期控制
        self.cooldown_days = 0  # 市场转强立即入场
        self.last_market_filter_trigger = -999
        self.was_bearish_prev = False
    
    def reset(self):
        """重置状态"""
        self.holdings = {}
        self.equity = 1.0
        self.trades = []
        self.last_market_filter_trigger = -999
        self.was_bearish_prev = False
    
    def process_day(self, date: str, date_idx: int, all_dates: List[str],
                    data: Dict[str, pd.DataFrame], 
                    market_filter: Optional[MarketFilter],
                    holding_dates: set) -> bool:
        """处理单日交易
        
        Returns:
            是否成功处理
        """
        # 检查市场状态
        market_ok = not market_filter or market_filter.is_bullish(date)
        
        # === 止损/止盈/超时检查 ===
        self._check_stop_loss_take_profit(date, date_idx, data)
        
        # === 市场过滤清仓 ===
        if market_filter and not market_ok:
            self._handle_market_filter(date, date_idx, data, holding_dates)
            # 记录市场状态
            self.was_bearish_prev = True
            return True
        
        # === 检测市场转强时刻 ===
        market_turned_bullish = self.was_bearish_prev and market_ok
        
        # === 重新入场 (市场转强 或 冷却期结束) ===
        can_reenter = (market_turned_bullish or 
                      (market_ok and (date_idx - self.last_market_filter_trigger) >= self.cooldown_days))
        
        if not self.holdings and can_reenter:
            self._try_reenter(date, date_idx, data, market_ok)
        
        # === 调仓 (仅在市场上涨时) ===
        if market_ok and date_idx % self.config.rebalance_days == 0:
            self._rebalance(date, date_idx, data)
        
        # 记录市场状态
        self.was_bearish_prev = not market_ok
        
        return True
    
    def _check_stop_loss_take_profit(self, date: str, date_idx: int, 
                                      data: Dict[str, pd.DataFrame]):
        """止损止盈检查"""
        to_close = []
        
        for code, pos in list(self.holdings.items()):
            row = data[code][data[code]['date'] == date]
            if len(row) == 0:
                continue
            
            current_price = row.iloc[0]['close']
            pnl = (current_price - pos['cost']) / pos['cost']
            hold_days = date_idx - pos['entry_idx']
            
            if pnl <= self.config.stop_loss:
                to_close.append((code, '止损', pnl, current_price, hold_days))
            elif pnl >= self.config.stop_gain:
                to_close.append((code, '止盈', pnl, current_price, hold_days))
            elif hold_days >= self.config.max_hold_days:
                to_close.append((code, '超时', pnl, current_price, hold_days))
        
        for code, reason, pnl, price, hold_days in to_close:
            self._close_position(code, date, pnl, reason, hold_days)
    
    def _handle_market_filter(self, date: str, date_idx: int,
                              data: Dict[str, pd.DataFrame], holding_dates: set):
        """市场过滤清仓"""
        self.last_market_filter_trigger = date_idx
        
        for code in list(self.holdings.keys()):
            row = data[code][data[code]['date'] == date]
            if len(row) > 0:
                price = row.iloc[0]['close']
                pnl = (price - self.holdings[code]['cost']) / self.holdings[code]['cost']
                hold_days = date_idx - self.holdings[code]['entry_idx']
                self._close_position(code, date, pnl, '市场过滤', hold_days)
    
    def _try_reenter(self, date: str, date_idx: int,
                     data: Dict[str, pd.DataFrame], market_ok: bool):
        """尝试重新入场"""
        # 需要市场上涨
        if not market_ok:
            return
        
        candidates = []
        for code, df in data.items():
            s, _ = self.selector.score(df, date)
            if s >= self.config.score_threshold:
                row = df[df['date'] == date]
                if len(row) > 0:
                    candidates.append((code, s, row.iloc[0]['close']))
        
        if len(candidates) >= self.config.hold_count:
            candidates.sort(key=lambda x: -x[1])
            for i, (code, s, price) in enumerate(candidates[:self.config.hold_count]):
                w = self.config.weights[i] if i < len(self.config.weights) else 0.5
                shares = (self.equity * w) / price
                self.holdings[code] = {
                    'cost': price,
                    'entry_idx': date_idx,
                    'entry_date': date,
                    'shares': shares
                }
                self.trades.append({
                    'date': date, 'code': code, 'action': 'buy', 'score': s,
                    'reason': '市场转强' if self.was_bearish_prev else '正常买入'
                })
    
    def _rebalance(self, date: str, date_idx: int, data: Dict[str, pd.DataFrame]):
        """调仓"""
        candidates = []
        for code, df in data.items():
            s, _ = self.selector.score(df, date)
            if s >= self.config.score_threshold:
                row = df[df['date'] == date]
                if len(row) > 0:
                    candidates.append((code, s, row.iloc[0]['close']))
        
        if len(candidates) >= self.config.hold_count:
            candidates.sort(key=lambda x: -x[1])
            top_codes = {c[0] for c in candidates[:self.config.hold_count]}
            
            # 卖出不在Top的
            for code in list(self.holdings.keys()):
                if code not in top_codes:
                    row = data[code][data[code]['date'] == date]
                    if len(row) > 0:
                        price = row.iloc[0]['close']
                        pnl = (price - self.holdings[code]['cost']) / self.holdings[code]['cost']
                        hold_days = date_idx - self.holdings[code]['entry_idx']
                        self._close_position(code, date, pnl, '调出', hold_days)
            
            # 买入Top
            for i, (code, s, price) in enumerate(candidates[:self.config.hold_count]):
                if code not in self.holdings:
                    w = self.config.weights[i] if i < len(self.config.weights) else 0.5
                    shares = (self.equity * w) / price
                    self.holdings[code] = {
                        'cost': price,
                        'entry_idx': date_idx,
                        'entry_date': date,
                        'shares': shares
                    }
                    self.trades.append({'date': date, 'code': code, 'action': 'buy', 'score': s})
    
    def _close_position(self, code: str, date: str, pnl: float, reason: str, hold_days: int):
        """平仓"""
        if code in self.holdings:
            self.equity *= (1 + pnl) * (1 - self.config.fee_rate)
            self.trades.append({
                'date': date,
                'code': code,
                'action': 'sell',
                'pnl': pnl,
                'reason': reason,
                'hold_days': hold_days,
            })
            del self.holdings[code]
    
    def get_equity(self, date: str, data: Dict[str, pd.DataFrame]) -> float:
        """获取当前净值"""
        if self.holdings:
            return sum(
                pos['shares'] * data[code][data[code]['date'] == date].iloc[0]['close']
                for code, pos in self.holdings.items()
                if len(data[code][data[code]['date'] == date]) > 0
            )
        return self.equity
    
    def get_sells(self) -> List[dict]:
        """获取所有卖出交易"""
        return [t for t in self.trades if t['action'] == 'sell' and 'pnl' in t]


__all__ = ['TradeExecutor']