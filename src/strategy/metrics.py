"""
绩效指标计算

计算回测绩效指标
"""
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
import numpy as np


@dataclass
class BacktestResult:
    """回测结果"""
    experiment_id: int = 0
    period: str = "test"
    start_date: str = ""
    end_date: str = ""
    total_return: float = 0.0       # 总收益
    annual_return: float = 0.0     # 年化收益
    sharpe_ratio: float = 0.0      # 夏普比率
    max_drawdown: float = 0.0      # 最大回撤
    max_drawdown_days: int = 0     # 最大回撤天数
    trade_count: int = 0           # 交易次数
    win_rate: float = 0.0           # 胜率
    avg_win: float = 0.0           # 平均盈利
    avg_loss: float = 0.0          # 平均亏损
    profit_loss_ratio: float = 0.0  # 盈亏比
    trade_list: List[Dict] = None  # 交易列表
    
    def __post_init__(self):
        if self.trade_list is None:
            self.trade_list = []
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        result = asdict(self)
        return result
    
    @property
    def win_count(self) -> int:
        return int(self.win_rate * self.trade_count) if self.trade_count > 0 else 0
    
    @property
    def loss_count(self) -> int:
        return self.trade_count - self.win_count


class MetricsCalculator:
    """绩效指标计算器"""
    
    @staticmethod
    def calculate(
        trades: List[Dict], 
        start_date: str, 
        end_date: str,
        experiment_id: int = 0,
        period: str = "test"
    ) -> BacktestResult:
        """
        计算绩效指标
        
        Args:
            trades: 交易列表
            start_date: 开始日期
            end_date: 结束日期
            experiment_id: 实验ID
            period: 周期名称
            
        Returns:
            回测结果
        """
        if not trades or len(trades) == 0:
            return BacktestResult(
                experiment_id=experiment_id,
                period=period,
                start_date=start_date,
                end_date=end_date,
                total_return=0.0,
                annual_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_days=0,
                trade_count=0,
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_loss_ratio=0.0,
                trade_list=[]
            )
        
        df = pd.DataFrame(trades)
        
        # 确保有exit_date字段
        if 'exit_date' not in df.columns:
            df['exit_date'] = df.get('date', end_date)
        
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
        win_count = len(wins)
        win_rate = win_count / len(df) if len(df) > 0 else 0
        avg_win = wins['pnl_pct'].mean() if win_count > 0 else 0
        
        # 盈亏比
        losses = df[df['pnl_pct'] < 0]
        avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        return BacktestResult(
            experiment_id=experiment_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            max_drawdown_days=max_dd_days,
            trade_count=len(trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_loss_ratio=profit_loss_ratio,
            trade_list=trades
        )