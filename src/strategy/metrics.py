"""
绩效指标计算

计算回测绩效指标
"""
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime
import pandas as pd
import numpy as np


@dataclass
class BacktestResult:
    """回测结果"""
    config_id: int = 0
    period: str = "test"
    total_return: float = 0.0       # 总收益
    annual_return: float = 0.0     # 年化收益
    sharpe_ratio: float = 0.0      # 夏普比率
    max_drawdown: float = 0.0      # 最大回撤
    max_drawdown_days: int = 0     # 最大回撤天数
    win_rate: float = 0.0           # 胜率
    profit_loss_ratio: float = 0.0  # 盈亏比
    avg_profit: float = 0.0         # 平均盈利
    avg_loss: float = 0.0           # 平均亏损
    trade_count: int = 0           # 交易次数
    trades: List[Dict] = None       # 交易列表
    
    def __post_init__(self):
        if self.trades is None:
            self.trades = []
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'config_id': self.config_id,
            'period': self.period,
            'total_return': self.total_return,
            'annual_return': self.annual_return,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_days': self.max_drawdown_days,
            'win_rate': self.win_rate,
            'profit_loss_ratio': self.profit_loss_ratio,
            'avg_profit': self.avg_profit,
            'avg_loss': self.avg_loss,
            'trade_count': self.trade_count
        }


class MetricsCalculator:
    """绩效指标计算器"""
    
    @staticmethod
    def calculate(
        trades: List[Dict], 
        start_date: str, 
        end_date: str,
        config_id: int = 0,
        period: str = "test"
    ) -> BacktestResult:
        """
        计算绩效指标
        
        Args:
            trades: 交易列表
            start_date: 开始日期
            end_date: 结束日期
            config_id: 配置ID
            period: 周期名称
            
        Returns:
            回测结果
        """
        if not trades:
            return BacktestResult(
                config_id=config_id,
                period=period,
                total_return=0,
                annual_return=0,
                sharpe_ratio=0,
                max_drawdown=0,
                max_drawdown_days=0,
                win_rate=0,
                profit_loss_ratio=0,
                avg_profit=0,
                avg_loss=0,
                trade_count=0,
                trades=[]
            )
        
        # 创建DataFrame
        df = pd.DataFrame(trades)
        df = df.sort_values('exit_date')
        
        # 累计收益
        cumulative = (1 + df['pnl_pct']).cumprod()
        total_return = cumulative.iloc[-1] - 1 if len(cumulative) > 0 else 0
        
        # 年化收益
        try:
            days = (datetime.strptime(end_date, '%Y-%m-%d') - 
                    datetime.strptime(start_date, '%Y-%m-%d')).days
        except:
            days = 365
        years = max(days / 365, 0.01)
        annual_return = (1 + total_return) ** (1 / years) - 1
        
        # 夏普比率
        if df['pnl_pct'].std() > 1e-10:
            sharpe = df['pnl_pct'].mean() / df['pnl_pct'].std() * np.sqrt(252)
        else:
            sharpe = 0
        
        # 最大回撤
        peak = cumulative.expanding().max()
        drawdown = (cumulative - peak) / peak
        max_drawdown = abs(drawdown.min()) if drawdown.min() < 0 else 0
        
        # 最大回撤天数
        max_dd_days = 0
        dd_start = None
        for i, val in enumerate(drawdown):
            if val == 0:
                if dd_start is not None:
                    max_dd_days = max(max_dd_days, i - dd_start)
                dd_start = i
        
        # 胜率
        wins = df[df['pnl_pct'] > 0]
        win_rate = len(wins) / len(df) if len(df) > 0 else 0
        avg_profit = wins['pnl_pct'].mean() if len(wins) > 0 else 0
        
        # 盈亏比
        losses = df[df['pnl_pct'] < 0]
        avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else 0
        
        return BacktestResult(
            config_id=config_id,
            period=period,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            max_drawdown_days=max_dd_days,
            win_rate=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            trade_count=len(trades),
            trades=trades
        )