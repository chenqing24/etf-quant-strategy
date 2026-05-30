#!/usr/bin/env python3
"""
ETF多因子挖掘框架 v7.0
=====================
第7-10轮：快速参数优化
"""
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class FactorMetrics:
    factor_name: str = ""
    test_return: float = 0.0
    train_return: float = 0.0
    oos_decay: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    avg_hold_days: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


class FactorMiner:
    """因子挖掘器 v7.0"""
    
    START_DATE = '2021-05-01'
    END_DATE = '2026-05-29'
    TRAIN_END = '2024-05-01'
    TEST_START = '2024-05-01'
    
    def __init__(self):
        self.pool_loader = ETFListLoader()
        self.data_loader = DataLoader()
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.market_data: Optional[pd.DataFrame] = None
        
    def load_data(self):
        """加载数据"""
        logger.info("加载ETF数据...")
        
        self.etf_data = self.data_loader.load(min_rows=300)
        
        for code in list(self.etf_data.keys()):
            df = self.etf_data[code]
            df = df[(df['date'] >= self.START_DATE) & (df['date'] <= self.END_DATE)]
            if len(df) < 100:
                del self.etf_data[code]
                continue
            df = df.sort_values('date').reset_index(drop=True)
            df['date'] = pd.to_datetime(df['date'])
            self.etf_data[code] = df
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
        
        if '510300' in self.etf_data:
            self.market_data = self.etf_data['510300'].copy()
            self.market_data = self._add_factors(self.market_data)
    
    def _add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加技术指标"""
        df = df.copy()
        
        # MA
        for n in [5, 10, 20, 60, 120]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['dif'] = ema12 - ema26
        df['dea'] = df['dif'].ewm(span=9).mean()
        df['macd_hist'] = (df['dif'] - df['dea']) * 2
        
        # 动量
        for n in [3, 10]:
            df[f'return_{n}d'] = df['close'].pct_change(n)
        
        return df
    
    def is_market_bullish_v1(self, date: pd.Timestamp) -> bool:
        """大盘过滤：收盘>MA20>MA60"""
        if self.market_data is None:
            return True
        
        df_before = self.market_data[self.market_data['date'] <= date]
        if len(df_before) < 5:
            return True
        
        latest = df_before.iloc[-1]
        return (
            latest['close'] > latest['ma20'] and
            latest['close'] > latest['ma60'] and
            latest['ma20'] > latest['ma60']
        )
    
    def backtest(self, df: pd.DataFrame, entry_condition: str,
                 stop_loss: float, stop_profit: float, max_hold_days: int) -> FactorMetrics:
        """回测"""
        metrics = FactorMetrics()
        
        train_df = df[df['date'] < self.TRAIN_END]
        test_df = df[df['date'] >= self.TEST_START]
        
        def check_condition(row, date):
            try:
                return bool(eval(entry_condition, {'np': np}, row.to_dict())) and self.is_market_bullish_v1(date)
            except:
                return False
        
        # 训练集
        train_trades = []
        position, entry_date, entry_price = None, None, None
        
        for _, row in train_df.iterrows():
            if position is None:
                if check_condition(row, row['date']):
                    position, entry_date, entry_price = 'long', row['date'], row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold_days:
                    train_trades.append({'pnl': pnl, 'hold_days': hold_days})
                    position = None
        
        # 测试集
        test_trades = []
        position, entry_date, entry_price = None, None, None
        
        for _, row in test_df.iterrows():
            if position is None:
                if check_condition(row, row['date']):
                    position, entry_date, entry_price = 'long', row['date'], row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold_days:
                    test_trades.append({'pnl': pnl, 'hold_days': hold_days})
                    position = None
        
        if train_trades:
            metrics.train_return = sum(t['pnl'] for t in train_trades)
        if test_trades:
            metrics.test_return = sum(t['pnl'] for t in test_trades)
        if train_trades or test_trades:
            all_trades = train_trades + test_trades
            metrics.trade_count = len(all_trades)
            metrics.win_rate = len([t for t in all_trades if t['pnl'] > 0]) / len(all_trades)
            metrics.avg_hold_days = np.mean([t['hold_days'] for t in all_trades])
        
        if metrics.train_return != 0:
            metrics.oos_decay = (metrics.test_return - metrics.train_return) / abs(metrics.train_return)
        
        return metrics
    
    def run_experiment(self, name: str, condition: str, 
                       stop_loss: float, stop_profit: float, max_hold_days: int) -> FactorMetrics:
        """运行实验"""
        target_codes = set(self.pool_loader.load())
        
        all_metrics = []
        for code, df in self.etf_data.items():
            if code not in target_codes:
                continue
            
            df = self._add_factors(df)
            m = self.backtest(df, condition, stop_loss, stop_profit, max_hold_days)
            all_metrics.append(m)
        
        result = FactorMetrics(factor_name=name)
        if all_metrics:
            result.test_return = np.mean([m.test_return for m in all_metrics])
            result.train_return = np.mean([m.train_return for m in all_metrics])
            result.trade_count = sum(m.trade_count for m in all_metrics)
            result.win_rate = np.mean([m.win_rate for m in all_metrics if m.trade_count > 0]) if any(m.trade_count > 0 for m in all_metrics) else 0
            result.avg_hold_days = np.mean([m.avg_hold_days for m in all_metrics if m.trade_count > 0]) if any(m.trade_count > 0 for m in all_metrics) else 0
            
            if result.train_return != 0:
                result.oos_decay = (result.test_return - result.train_return) / abs(result.train_return)
        
        return result
    
    def run_rounds_7_10(self) -> List[FactorMetrics]:
        """第7-10轮：快速参数优化"""
        logger.info("=" * 60)
        logger.info("第7-10轮：快速参数优化")
        logger.info("=" * 60)
        
        results = []
        base_condition = "(macd_hist > 0) & (return_3d > 0)"
        
        # 参数网格
        stop_losses = [-0.05, -0.06, -0.07, -0.08]
        stop_profits = [0.10, 0.12, 0.14, 0.16]
        max_holds = [4, 5, 6]
        
        # 第7轮
        logger.info("执行第7轮...")
        for sl in stop_losses[:2]:
            for sp in stop_profits[:2]:
                for mh in max_holds[:2]:
                    name = f"R7_MACD_SL{abs(sl)*100:.0f}_SP{int(sp*100)}_MH{mh}"
                    m = self.run_experiment(name, base_condition, sl, sp, mh)
                    results.append(m)
                    time.sleep(0.01)
        
        # 第8轮
        logger.info("执行第8轮...")
        for sl in stop_losses[2:]:
            for sp in stop_profits[:2]:
                for mh in max_holds[:2]:
                    name = f"R8_MACD_SL{abs(sl)*100:.0f}_SP{int(sp*100)}_MH{mh}"
                    m = self.run_experiment(name, base_condition, sl, sp, mh)
                    results.append(m)
                    time.sleep(0.01)
        
        # 第9轮
        logger.info("执行第9轮...")
        for sl in stop_losses[:2]:
            for sp in stop_profits[2:]:
                for mh in max_holds[:2]:
                    name = f"R9_MACD_SL{abs(sl)*100:.0f}_SP{int(sp*100)}_MH{mh}"
                    m = self.run_experiment(name, base_condition, sl, sp, mh)
                    results.append(m)
                    time.sleep(0.01)
        
        # 第10轮
        logger.info("执行第10轮...")
        for sl in stop_losses[:2]:
            for sp in stop_profits[:2]:
                for mh in max_holds[2:]:
                    name = f"R10_MACD_SL{abs(sl)*100:.0f}_SP{int(sp*100)}_MH{mh}"
                    m = self.run_experiment(name, base_condition, sl, sp, mh)
                    results.append(m)
                    time.sleep(0.01)
        
        return results
    
    def save_results(self, results: List[FactorMetrics], round_id: int):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f'round{round_id}.json'
        
        data = {
            'round_id': round_id,
            'timestamp': datetime.now().isoformat(),
            'start_date': self.START_DATE,
            'end_date': self.END_DATE,
            'train_period': "2021-05-01 ~ 2024-05-01",
            'test_period': "2024-05-01 ~ 2026-05-29",
            'results': [r.to_dict() for r in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    miner = FactorMiner()
    miner.load_data()
    
    # 第7-10轮
    for round_id in [7, 8, 9, 10]:
        logger.info(f"\n{'='*60}")
        logger.info(f"开始第{round_id}轮")
        logger.info(f"{'='*60}")
        
        results = miner.run_rounds_7_10()
        miner.save_results(results, round_id)
        
        # 打印本轮Top3
        sorted_results = sorted(results, key=lambda x: abs(x.oos_decay))  # 按稳定性排序
        print(f"\n第{round_id}轮 Top3 稳定策略：")
        for r in sorted_results[:3]:
            print(f"  {r.factor_name}: 测试={r.test_return:.2%} 训练={r.train_return:.2%} 衰减={r.oos_decay:.2%}")
        
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print("第7-10轮实验完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()