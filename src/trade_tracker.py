#!/usr/bin/env python3
"""交易追踪与记录"""
import json
import os
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
                'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, f, indent=2)
    
    def record_buy(self, code: str, name: str, price: float, 
                   quantity: int, reason: str = "") -> TradeRecord:
        """记录买入"""
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
    
    def record_sell(self, code: str, price: float, actual_pnl: float = 0):
        """记录卖出"""
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
            )
            self.save_trade(trade)
            
            # 移除持仓
            positions = [p for p in positions if p.code != code]
            self.save_positions(positions)
            
            return trade
        return None
    
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
    
    def get_performance_summary(self) -> Dict:
        """获取绩效汇总"""
        with open(self.performance_file, 'r') as f:
            return json.load(f)
    
    def update_performance(self, pnl: float):
        """更新绩效"""
        with open(self.performance_file, 'r') as f:
            perf = json.load(f)
        
        perf['total_pnl'] += pnl
        perf['current_capital'] = perf['initial_capital'] * (1 + perf['total_pnl'] / 100)
        perf['total_trades'] += 1
        
        # 计算胜率
        trades = self.load_trades()
        sell_trades = [t for t in trades if t.action == 'sell' and t.actual_pnl != 0]
        if sell_trades:
            wins = sum(1 for t in sell_trades if t.actual_pnl > 0)
            perf['win_rate'] = wins / len(sell_trades) * 100
        
        with open(self.performance_file, 'w') as f:
            json.dump(perf, f, indent=2)
        
        return perf
    
    def need_rebalance(self, rebalance_days: int = 10) -> bool:
        """判断是否需要调仓"""
        positions = self.load_positions()
        
        if not positions:
            return True  # 空仓需要买入
        
        # 检查是否持仓超期
        for p in positions:
            hold_days = (datetime.now() - datetime.strptime(p.entry_date, '%Y-%m-%d')).days
            if hold_days >= rebalance_days:
                return True
        
        return False
    
    def print_status(self):
        """打印当前状态"""
        positions = self.load_positions()
        perf = self.get_performance_summary()
        
        print("\n" + "="*50)
        print("📊 当前持仓状态")
        print("="*50)
        
        if positions:
            for p in positions:
                print(f"  {p.code} {p.name}")
                print(f"    买入: {p.entry_price} × {p.quantity}股")
                print(f"    当前: {p.current_price} (盈亏: {p.pnl_pct:+.1f}%)")
                print(f"    持有: {p.hold_days}天")
        else:
            print("  (空仓)")
        
        print(f"\n总资产: {perf['current_capital']:,.0f}元")
        print(f"累计盈亏: {perf['total_pnl']:+.1f}%")
        print(f"交易次数: {perf['total_trades']}")
        print(f"胜率: {perf['win_rate']:.1f}%")
        print("="*50)


def test_tracker():
    """测试"""
    tracker = TradeTracker('.')
    
    # 模拟记录买入
    tracker.record_buy('516050', '科创成长', 1.384, 13000, '首推')
    
    # 模拟更新价格
    tracker.update_position_price('516050', 1.42)
    
    # 打印状态
    tracker.print_status()
    
    print("✓ 交易追踪测试通过")


if __name__ == '__main__':
    test_tracker()


__all__ = ['TradeTracker', 'TradeRecord', 'Position', 'test_tracker']