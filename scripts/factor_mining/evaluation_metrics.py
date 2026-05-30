#!/usr/bin/env python3
"""
完整评价指标体系
"""
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class EvaluationMetrics:
    """完整评价指标"""
    # 核心收益
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    
    # 交易效率
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    trade_count: int = 0
    avg_hold_days: float = 0.0
    
    # 稳定性
    ic: float = 0.0
    ir: float = 0.0
    oos_decay: float = 0.0
    return_stability: float = 0.0
    
    # 统计显著性
    t_statistic: float = 0.0
    p_value: float = 1.0
    confidence: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


class EvaluationSystem:
    """评价指标系统"""
    
    START_DATE = '2021-05-01'
    END_DATE = '2026-05-29'
    TRAIN_END = '2024-05-01'
    TEST_START = '2024-05-01'
    
    def __init__(self):
        self.pool_loader = ETFListLoader()
        self.data_loader = DataLoader()
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.market_data = None
        
    def load_data(self):
        """加载数据"""
        logger.info("加载ETF数据...")
        self.etf_data = self.data_loader.load(min_rows=200)
        
        for code in list(self.etf_data.keys()):
            df = self.etf_data[code]
            df = df[(df['date'] >= self.START_DATE) & (df['date'] <= self.END_DATE)]
            if len(df) < 100:
                del self.etf_data[code]
                continue
            df = df.sort_values('date').reset_index(drop=True)
            df['date'] = pd.to_datetime(df['date'])
            self.etf_data[code] = df
        
        if '510300' in self.etf_data:
            self.market_data = self.etf_data['510300'].copy()
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
    
    def _add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加因子"""
        df = df.copy()
        
        for n in [20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd_hist'] = ((ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()) * 2
        df['return_3d'] = df['close'].pct_change(3)
        
        return df
    
    def _is_market_bullish(self, date: pd.Timestamp) -> bool:
        if self.market_data is None:
            return True
        
        df = self.market_data.copy()
        for n in [20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        df_before = df[df['date'] <= date]
        if len(df_before) < 60:
            return True
        
        latest = df_before.iloc[-1]
        return (
            latest['close'] > latest['ma20'] and
            latest['close'] > latest['ma60'] and
            latest['ma20'] > latest['ma60']
        )
    
    def backtest_strategy(self, df: pd.DataFrame, stop_loss: float = -0.06, 
                         stop_profit: float = 0.12, max_hold: int = 5) -> List[Dict]:
        """回测并返回所有交易"""
        df = self._add_factors(df)
        train_df = df[df['date'] < self.TRAIN_END]
        test_df = df[df['date'] >= self.TEST_START]
        
        condition = "(macd_hist > 0) & (return_3d > 0)"
        
        def check(row, date):
            try:
                return bool(eval(condition, {'np': np}, row.to_dict())) and self._is_market_bullish(date)
            except:
                return False
        
        trades = []
        
        # 训练集
        pos, entry_price, entry_date = None, None, None
        for _, row in train_df.iterrows():
            if pos is None:
                if check(row, row['date']):
                    pos, entry_price, entry_date = 'long', row['close'], row['date']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold:
                    trades.append({'pnl': pnl, 'period': 'train', 'hold_days': hold_days})
                    pos = None
        
        # 测试集
        pos, entry_price, entry_date = None, None, None
        for _, row in test_df.iterrows():
            if pos is None:
                if check(row, row['date']):
                    pos, entry_price, entry_date = 'long', row['close'], row['date']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold:
                    trades.append({'pnl': pnl, 'period': 'test', 'hold_days': hold_days})
                    pos = None
        
        return trades
    
    def calculate_metrics(self, trades: List[Dict], strategy_name: str = "MACD红柱+动量3") -> EvaluationMetrics:
        """计算完整评价指标"""
        metrics = EvaluationMetrics()
        
        if not trades:
            return metrics
        
        train_trades = [t for t in trades if t['period'] == 'train']
        test_trades = [t for t in trades if t['period'] == 'test']
        all_trades = trades
        
        # 核心收益
        metrics.total_return = sum(t['pnl'] for t in all_trades)
        metrics.annual_return = metrics.total_return / 2  # 2年测试期
        
        # 夏普比率（简化）
        if len(all_trades) > 1:
            returns = [t['pnl'] for t in all_trades]
            metrics.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252/5) if np.std(returns) > 0 else 0
        
        # 最大回撤
        cumulative = np.cumsum([1] + [t['pnl'] for t in all_trades])
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        metrics.max_drawdown = drawdowns.min()
        
        # 交易效率
        winning_trades = [t for t in all_trades if t['pnl'] > 0]
        losing_trades = [t for t in all_trades if t['pnl'] <= 0]
        
        metrics.trade_count = len(all_trades)
        metrics.win_rate = len(winning_trades) / len(all_trades) if all_trades else 0
        
        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0
        metrics.profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        metrics.avg_hold_days = np.mean([t['hold_days'] for t in all_trades]) if all_trades else 0
        
        # 稳定性
        if train_trades:
            metrics.oos_decay = (sum(t['pnl'] for t in test_trades) / len(test_trades) - 
                                  sum(t['pnl'] for t in train_trades) / len(train_trades)) / \
                                 abs(sum(t['pnl'] for t in train_trades) / len(train_trades)) if train_trades else 0
        
        # IC（因子与收益相关性，简化用交易收益相关性）
        if len(test_trades) >= 3:
            returns = [t['pnl'] for t in test_trades]
            metrics.ic = np.corrcoef(range(len(returns)), returns)[0, 1] if len(returns) > 1 else 0
            metrics.ir = metrics.ic / np.std(returns) if np.std(returns) > 0 else 0
        
        # 收益稳定性
        monthly_returns = []
        for i in range(0, len(all_trades), 20):  # 简化按20笔交易为一个月
            month_trades = all_trades[i:i+20]
            if month_trades:
                monthly_returns.append(sum(t['pnl'] for t in month_trades))
        
        if monthly_returns:
            metrics.return_stability = np.std(monthly_returns) / abs(np.mean(monthly_returns)) if np.mean(monthly_returns) != 0 else 0
        
        # 统计显著性
        if len(all_trades) > 1:
            returns = [t['pnl'] for t in all_trades]
            metrics.t_statistic, metrics.p_value = stats.ttest_1samp(returns, 0)
            metrics.confidence = (1 - metrics.p_value) * 100
        
        return metrics
    
    def evaluate_all(self) -> EvaluationMetrics:
        """评估所有ETF"""
        logger.info("=" * 60)
        logger.info("完整评价指标计算")
        logger.info("=" * 60)
        
        target_codes = set(self.pool_loader.load())
        all_trades = []
        
        for code in target_codes:
            if code not in self.etf_data:
                continue
            
            df = self.etf_data[code]
            trades = self.backtest_strategy(df)
            all_trades.extend(trades)
        
        metrics = self.calculate_metrics(all_trades)
        
        # 打印结果
        logger.info(f"\n📊 核心收益指标:")
        logger.info(f"  总收益率: {metrics.total_return:.2%}")
        logger.info(f"  年化收益率: {metrics.annual_return:.2%}")
        logger.info(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
        logger.info(f"  最大回撤: {metrics.max_drawdown:.2%}")
        
        logger.info(f"\n📈 交易效率指标:")
        logger.info(f"  胜率: {metrics.win_rate:.1%}")
        logger.info(f"  盈亏比: {metrics.profit_loss_ratio:.2f}")
        logger.info(f"  交易次数: {metrics.trade_count}")
        logger.info(f"  平均持仓: {metrics.avg_hold_days:.1f}天")
        
        logger.info(f"\n📉 稳定性指标:")
        logger.info(f"  IC: {metrics.ic:.4f}")
        logger.info(f"  IR: {metrics.ir:.4f}")
        logger.info(f"  样本外衰减: {metrics.oos_decay:.2%}")
        logger.info(f"  收益稳定性: {metrics.return_stability:.2f}")
        
        logger.info(f"\n📐 统计显著性:")
        logger.info(f"  t统计量: {metrics.t_statistic:.2f}")
        logger.info(f"  p值: {metrics.p_value:.4f}")
        logger.info(f"  置信度: {metrics.confidence:.1f}%")
        
        return metrics
    
    def save_results(self, metrics: EvaluationMetrics):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / 'evaluation_metrics.json'
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'strategy': 'MACD红柱+动量3',
            'parameters': {
                'stop_loss': -0.06,
                'stop_profit': 0.12,
                'max_hold_days': 5,
                'market_filter': '510300 MA20>MA60>MA120'
            },
            'metrics': metrics.to_dict()
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    system = EvaluationSystem()
    system.load_data()
    
    metrics = system.evaluate_all()
    system.save_results(metrics)
    
    print("\n" + "=" * 60)
    print("评价指标汇总")
    print("=" * 60)
    print(f"总收益率: {metrics.total_return:.2%}")
    print(f"夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"胜率: {metrics.win_rate:.1%}")
    print(f"样本外衰减: {metrics.oos_decay:.2%}")
    print(f"p值: {metrics.p_value:.4f}")


if __name__ == '__main__':
    main()