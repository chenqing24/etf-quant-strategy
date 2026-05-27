"""
持仓执行器

负责:
- 开仓/平仓管理
- 止盈止损检查
- 权益计算
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
from src.strategy.config import BacktestConfig


@dataclass
class Position:
    """持仓"""
    code: str
    entry_price: float
    entry_date: str
    entry_score: float
    shares: float
    hold_days: int = 0


class PositionExecutor:
    """持仓执行器"""
    
    def __init__(self, config: BacktestConfig):
        """
        初始化
        
        Args:
            config: 回测配置
        """
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.trades: List[Dict] = []
        self.equity = 1.0  # 初始权益
    
    def can_open(self) -> bool:
        """是否可以开仓"""
        return len(self.positions) < self.config.max_positions
    
    def open_position(
        self, 
        code: str, 
        price: float, 
        date: str, 
        score: float
    ) -> bool:
        """
        开仓
        
        Args:
            code: ETF代码
            price: 买入价格
            date: 买入日期
            score: 买入分数
            
        Returns:
            是否成功
        """
        if not self.can_open():
            return False
        
        if price <= 0:
            return False
        
        # 计算买入数量
        # 每次开仓使用等权资金
        position_value = self.equity / max(1, self.config.max_positions - len(self.positions))
        shares = position_value / price
        shares = max(1, int(shares))  # 至少1股
        
        if shares <= 0:
            return False
        
        # 记录持仓
        self.positions[code] = Position(
            code=code,
            entry_price=price,
            entry_date=date,
            entry_score=score,
            shares=shares
        )
        
        # 记录交易
        self.trades.append({
            'code': code,
            'action': 'buy',
            'date': date,
            'price': price,
            'shares': shares,
            'score': score
        })
        
        return True
    
    def check_and_close(
        self, 
        code: str, 
        current_price: float, 
        date: str
    ) -> Optional[Dict]:
        """
        检查是否需要平仓
        
        Args:
            code: ETF代码
            current_price: 当前价格
            date: 当前日期
            
        Returns:
            平仓交易记录，如果不需要平仓则返回None
        """
        if code not in self.positions:
            return None
        
        pos = self.positions[code]
        pos.hold_days += 1
        
        pnl_pct = (current_price - pos.entry_price) / pos.entry_price
        
        # 止盈止损检查
        if pnl_pct <= self.config.stop_loss:
            return self._close_position(pos, current_price, date, '止损')
        
        if pnl_pct >= self.config.stop_profit:
            return self._close_position(pos, current_price, date, '止盈')
        
        if pos.hold_days >= self.config.hold_days:
            return self._close_position(pos, current_price, date, '到期')
        
        return None
    
    def _close_position(
        self, 
        pos: Position, 
        exit_price: float, 
        date: str, 
        reason: str
    ) -> Dict:
        """
        平仓
        
        Args:
            pos: 持仓
            exit_price: 卖出价格
            date: 卖出日期
            reason: 平仓原因
            
        Returns:
            平仓交易记录
        """
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        
        trade = {
            'code': pos.code,
            'entry_date': pos.entry_date,
            'exit_date': date,
            'entry_price': pos.entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'hold_days': pos.hold_days,
            'exit_reason': reason,
            'entry_score': pos.entry_score
        }
        
        # 记录卖出交易
        self.trades.append({
            'code': pos.code,
            'action': 'sell',
            'date': date,
            'price': exit_price,
            'pnl_pct': pnl_pct,
            'reason': reason,
            'exit_reason': reason
        })
        
        # 更新权益
        self.equity *= (1 + pnl_pct)
        
        # 删除持仓
        del self.positions[pos.code]
        
        return trade
    
    def close_all(
        self, 
        current_prices: Dict[str, float], 
        date: str
    ):
        """
        期末平仓
        
        Args:
            current_prices: 当前价格字典
            date: 平仓日期
        """
        for code, pos in list(self.positions.items()):
            price = current_prices.get(code, pos.entry_price)
            self._close_position(pos, price, date, '期末平仓')
    
    def get_position_count(self) -> int:
        """获取持仓数量"""
        return len(self.positions)
    
    def has_position(self, code: str) -> bool:
        """是否持有该ETF"""
        return code in self.positions
    
    def reset(self):
        """重置执行器"""
        self.positions = {}
        self.trades = []
        self.equity = 1.0