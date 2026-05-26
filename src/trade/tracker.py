#!/usr/bin/env python3
"""交易追踪与记录"""
import csv
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class TradeRecord:
    """交易记录"""
    date: str           # 交易日期
    code: str           # ETF代码
    name: str           # ETF名称
    action: str         # buy/sell
    price: float        # 成交价格
    quantity: int       # 数量
    amount: float       # 金额
    reason: str         # 交易原因
    expected_return: float = 0    # 预期收益
    actual_pnl: float = 0         # 实际盈亏
    note: str = ""                # 备注

    # ── US-005 增强字段 ──────────────────────────────────────────
    realtime_price: float = 0.0   # 实时价格（买入时快照）
    price_deviation: float = 0.0  # 偏差率 (%)
    rsi_14: float = 0.0           # RSI(14) 值
    day_change_pct: float = 0.0  # 当日涨跌幅 (%)
    score: int = 0               # 策略评分
    # ─────────────────────────────────────────────────────────────


@dataclass
class Position:
    """持仓"""
    code: str
    name: str
    entry_date: str
    entry_price: float
    quantity: int
    current_price: float = 0
    pnl_pct: float = 0
    hold_days: int = 0


class TradeTracker:
    """交易追踪器"""
    
    def __init__(self, data_dir: str = '.'):
        self.data_dir = data_dir
        self.trades_file = os.path.join(data_dir, 'etf_trades.json')
        self.positions_file = os.path.join(data_dir, 'etf_positions.json')
        self.performance_file = os.path.join(data_dir, 'etf_performance.json')
        
        self._ensure_files()
    
    def _ensure_files(self):
        """初始化文件"""
        for f in [self.trades_file, self.positions_file, self.performance_file]:
            if not os.path.exists(f):
                with open(f, 'w') as fp:
                    json.dump({
                        'trades': [],
                        'positions': [],
                        'performance': {
                            'initial_capital': 20000,
                            'current_capital': 20000,
                            'total_pnl': 0,
                            'total_trades': 0,
                            'win_rate': 0,
                        }
                    }, fp, indent=2)
    
    def load_trades(self) -> List[TradeRecord]:
        """加载交易记录"""
        with open(self.trades_file, 'r') as f:
            data = json.load(f)
            return [TradeRecord(**t) for t in data.get('trades', [])]
    
    def save_trade(self, trade: TradeRecord):
        """保存交易记录"""
        with open(self.trades_file, 'r') as f:
            data = json.load(f)
        
        data['trades'].append(asdict(trade))
        
        with open(self.trades_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_positions(self) -> List[Position]:
        """加载当前持仓"""
        with open(self.positions_file, 'r') as f:
            data = json.load(f)
            return [Position(**p) for p in data.get('positions', [])]
    
    def save_positions(self, positions: List[Position]):
        """保存持仓"""
        with open(self.positions_file, 'w') as f:
            json.dump({
                'positions': [asdict(p) for p in positions],
            }, f, indent=2, ensure_ascii=False)
    
    # ── US-005: 实时数据获取 ────────────────────────────────────
    
    def _fetch_realtime_data(self, code: str) -> Dict:
        """
        获取ETF实时数据（价格、涨跌幅、RSI）
        
        优先使用热数据管理器(DataFacade)，降级使用腾讯API直调。
        
        Returns:
            {'price': float, 'change_pct': float, 'rsi_14': float,
             'price_deviation': float, 'data_source': str}
        """
        # 策略1: 使用 DataFacade 热数据层
        try:
            from src.data.manager import DataFacade
            facade = DataFacade(self.data_dir)
            merged = facade.get_merged_data(code)
            
            if merged.get('price') and merged['price'] > 0:
                change_pct = merged.get('change_pct', 0.0)
                return {
                    'price': merged['price'],
                    'change_pct': change_pct,
                    'rsi_14': merged.get('rsi_14', 50.0),
                    'price_deviation': 0.0,   # 热数据无信号价，无法计算偏差
                    'data_source': 'hot_data',
                }
        except Exception:
            pass
        
        # 策略2: DataFacade（统一入口）
        return self._fetch_tencent_realtime(code)
    
    def _fetch_tencent_realtime(self, code: str) -> Dict:
        """通过DataFacade获取实时数据"""
        from src.data.facade import DataFacade
        facade = DataFacade(self.data_dir)
        
        # 处理code前缀
        if code.startswith(('sh', 'sz')):
            prefix = code
        elif code.isdigit():
            prefix = f'sh{code}' if code.startswith(('5', '1', '11')) else f'sz{code}'
        else:
            prefix = code
        
        result = facade.get_realtime([prefix])
        data = result.get(prefix, {})
        
        if data:
            return {
                'price': data.get('price', 0),
                'change_pct': data.get('change_pct', 0),
                'rsi_14': self._calc_rsi_14(code),
                'price_deviation': 0.0,
                'data_source': 'facade_sina',
            }
        
        return {'price': 0, 'change_pct': 0, 'rsi_14': 50.0, 'price_deviation': 0.0, 'data_source': 'fallback'}
    
    def _calc_rsi_14(self, code: str) -> float:
        """计算RSI(14) from cold CSV data"""
        try:
            from src.data.manager import ColdDataManager
            cold = ColdDataManager(self.data_dir)
            records = cold.get(code)
            
            if not records or len(records) < 15:
                return 50.0
            
            # 取最近14个收盘价计算RSI
            closes = [float(r['close']) for r in records[-15:]]
            
            gains, losses = [], []
            for i in range(1, len(closes)):
                delta = closes[i] - closes[i-1]
                gains.append(max(delta, 0))
                losses.append(max(-delta, 0))
            
            avg_gain = sum(gains[-14:]) / 14 if gains else 0
            avg_loss = sum(losses[-14:]) / 14 if losses else 0
            
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return round(100 - 100 / (1 + rs), 2)
        except Exception:
            return 50.0
    
    # ─────────────────────────────────────────────────────────────
    
    def record_buy(self, code: str, name: str, price: float, 
                   quantity: int, reason: str = "",
                   signal_price: float = 0.0,
                   score: int = 0) -> TradeRecord:
        """
        记录买入（US-005: 自动填充实时数据）
        
        Args:
            code:           ETF代码
            name:           ETF名称
            price:          成交价格
            quantity:       数量
            reason:         交易原因
            signal_price:   信号发出时的价格（用于计算偏差率）
            score:          策略评分（可选）
        """
        # ── 自动获取实时快照 ──
        rt = self._fetch_realtime_data(code)
        realtime_price = rt.get('price', price)
        day_change_pct = rt.get('change_pct', 0.0)
        rsi_14 = rt.get('rsi_14', 50.0)
        data_source = rt.get('data_source', 'unknown')
        
        # 偏差率: (实时价 - 信号价) / 信号价 * 100
        if signal_price > 0 and realtime_price > 0:
            price_deviation = (realtime_price - signal_price) / signal_price * 100
        else:
            price_deviation = 0.0
        
        # 评分默认填充
        final_score = score
        
        amount = price * quantity
        
        trade = TradeRecord(
            date=datetime.now().strftime('%Y-%m-%d'),
            code=code,
            name=name,
            action='buy',
            price=price,
            quantity=quantity,
            amount=amount,
            reason=reason,
            # US-005 增强字段
            realtime_price=realtime_price,
            price_deviation=price_deviation,
            rsi_14=rsi_14,
            day_change_pct=day_change_pct,
            score=final_score,
        )
        
        self.save_trade(trade)
        
        # 更新持仓
        positions = self.load_positions()
        positions.append(Position(
            code=code,
            name=name,
            entry_date=trade.date,
            entry_price=price,
            quantity=quantity,
            current_price=price,
            pnl_pct=0,
            hold_days=0,
        ))
        self.save_positions(positions)
        
        return trade
    
    def record_sell(self, code: str, price: float, actual_pnl: float = 0,
                     signal_price: float = 0.0, score: int = 0) -> Optional[TradeRecord]:
        """
        记录卖出（US-005: 填充实时快照字段，sell端留0）
        
        Args:
            code:           ETF代码
            price:          成交价格
            actual_pnl:     实际盈亏
            signal_price:   信号价（sell时未使用，留0）
            score:          评分（sell时未使用，留0）
        """
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)
        
        if pos:
            trade = TradeRecord(
                date=datetime.now().strftime('%Y-%m-%d'),
                code=code,
                name=pos.name,
                action='sell',
                price=price,
                quantity=pos.quantity,
                amount=price * pos.quantity,
                reason='卖出',
                actual_pnl=actual_pnl,
                # US-005: sell时无法提供有效实时快照，填0
                realtime_price=price,
                price_deviation=0.0,
                rsi_14=0.0,
                day_change_pct=0.0,
                score=0,
            )
            self.save_trade(trade)
            
            # 移除持仓
            positions = [p for p in positions if p.code != code]
            self.save_positions(positions)
            
            return trade
        return None
    
    # ── US-005: 查询接口 ─────────────────────────────────────────
    
    def query_trades(self,
                     date: Optional[str] = None,
                     code: Optional[str] = None,
                     action: Optional[str] = None) -> List[TradeRecord]:
        """
        查询交易记录
        
        Args:
            date:   交易日期，格式 YYYY-MM-DD（支持模糊，如 "2026-05"）
            code:   ETF代码（支持模糊匹配）
            action: 行为类型 'buy' / 'sell'
            
        Returns:
            符合条件的 TradeRecord 列表
        """
        trades = self.load_trades()
        results = trades
        
        if date:
            # 支持完整日期或年月
            if len(date) == 10:
                results = [t for t in results if t.date == date]
            elif len(date) == 7:
                results = [t for t in results if t.date.startswith(date)]
            elif len(date) == 4:
                results = [t for t in results if t.date.startswith(date)]
        
        if code:
            code_upper = code.upper()
            results = [t for t in results if code_upper in t.code.upper()]
        
        if action:
            results = [t for t in results if t.action == action]
        
        return results
    
    def export_csv(self, filepath: str) -> int:
        """
        导出交易记录为CSV
        
        Args:
            filepath:  输出文件路径
            
        Returns:
            导出的记录数
        """
        trades = self.load_trades()
        
        # 定义CSV字段（含US-005新字段）
        fieldnames = [
            'date', 'code', 'name', 'action',
            'price', 'quantity', 'amount', 'reason',
            'expected_return', 'actual_pnl', 'note',
            # US-005 增强字段
            'realtime_price', 'price_deviation',
            'rsi_14', 'day_change_pct', 'score',
        ]
        
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trades:
                writer.writerow(asdict(t))
        
        return len(trades)
    
    # ─────────────────────────────────────────────────────────────
    
    def update_position_price(self, code: str, current_price: float):
        """更新持仓价格"""
        positions = self.load_positions()
        
        for p in positions:
            if p.code == code:
                p.current_price = current_price
                p.pnl_pct = (current_price - p.entry_price) / p.entry_price * 100
                p.hold_days = (datetime.now() - datetime.strptime(p.entry_date, '%Y-%m-%d')).days
        
        self.save_positions(positions)
        return positions
    
    def get_holdings(self) -> List[Position]:
        """获取当前持仓"""
        return self.load_positions()
    
    def check_stop_loss(self, code: str, threshold: float = -5) -> bool:
        """检查是否触发止损"""
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)
        
        if pos and pos.pnl_pct <= threshold:
            return True
        return False
    
    def check_take_profit(self, code: str, threshold: float = 8) -> bool:
        """检查是否触发止盈"""
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)
        
        if pos and pos.pnl_pct >= threshold:
            return True
        return False
    
    def need_rebalance(self, max_hold_days: int = 10) -> bool:
        """检查是否需要调仓"""
        positions = self.load_positions()
        
        for p in positions:
            if p.hold_days >= max_hold_days:
                return True
        return False
    
    def get_performance_summary(self) -> Dict:
        """获取绩效汇总"""
        if os.path.exists(self.performance_file):
            with open(self.performance_file, 'r') as f:
                data = json.load(f)
                return data.get('performance', {})
        return {
            'initial_capital': 20000,
            'current_capital': 20000,
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
        }
    
    def update_performance(self, capital: float, pnl: float, 
                           total_trades: int, win_rate: float):
        """更新绩效"""
        with open(self.performance_file, 'r') as f:
            data = json.load(f)
        
        data['performance'].update({
            'current_capital': capital,
            'total_pnl': pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
        with open(self.performance_file, 'w') as f:
            json.dump(data, f, indent=2)
