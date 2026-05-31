#!/usr/bin/env python3
"""
ETF多因子挖掘框架 v6.0
=====================
改进点（基于第5轮实验）：
1. 锁定MACD+动量3最优策略
2. 测试不同动量周期（1日、5日）
3. 测试更严格的MA过滤
4. 滚动窗口验证
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
    """因子挖掘器 v6.0"""
    
    START_DATE = '2021-05-01'
    END_DATE = '2026-05-29'
    TRAIN_END = '2024-05-01'
    TEST_START = '2024-05-01'
    
    def __init__(self):
        self.pool_loader = ETFListLoader()
        self.data_loader = DataLoader()
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.market_data: Optional[pd.DataFrame] = None
        self.results: List[FactorMetrics] = []
        
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
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi14'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['dif'] = ema12 - ema26
        df['dea'] = df['dif'].ewm(span=9).mean()
        df['macd_hist'] = (df['dif'] - df['dea']) * 2
        
        # 成交量
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20'].replace(0, np.nan)
        
        # 动量（多个周期）
        for n in [1, 3, 5, 10]:
            df[f'return_{n}d'] = df['close'].pct_change(n)
        
        return df
    
    def is_market_bullish_v1(self, date: pd.Timestamp) -> bool:
        """大盘过滤V1：收盘>MA20>MA60"""
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
    
    def backtest(
        self,
        df: pd.DataFrame,
        entry_condition: str,
        stop_loss: float = -0.06,
        stop_profit: float = 0.12,
        max_hold_days: int = 5
    ) -> FactorMetrics:
        """回测"""
        metrics = FactorMetrics()
        
        train_df = df[df['date'] < self.TRAIN_END]
        test_df = df[df['date'] >= self.TEST_START]
        
        def check_condition(row, date):
            try:
                return bool(eval(entry_condition, {'np': np}, row.to_dict())) and self.is_market_bullish_v1(date)
            except:
                return False
        
        # 训练集交易
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
        
        # 测试集交易
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
        
        # 计算指标
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
                       stop_loss: float = -0.06,
                       stop_profit: float = 0.12,
                       max_hold_days: int = 5) -> FactorMetrics:
        """运行实验"""
        target_codes = set(self.pool_loader.load())
        
        all_metrics = []
        for code, df in self.etf_data.items():
            if code not in target_codes:
                continue
            
            df = self._add_factors(df)
            m = self.backtest(df, condition, stop_loss, stop_profit, max_hold_days)
            all_metrics.append(m)
        
        # 合并结果
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
    
    def run_round_6(self) -> List[FactorMetrics]:
        """第6轮：动量周期测试 + MA过滤"""
        logger.info("=" * 60)
        logger.info("第6轮：动量周期测试 + MA过滤")
        logger.info("=" * 60)
        
        results = []
        
        # 测试不同动量周期
        momentum_tests = [
            ("MACD+动量1", "(macd_hist > 0) & (return_1d > 0)"),
            ("MACD+动量3", "(macd_hist > 0) & (return_3d > 0)"),
            ("MACD+动量5", "(macd_hist > 0) & (return_5d > 0)"),
            ("MACD+动量10", "(macd_hist > 0) & (return_10d > 0)"),
        ]
        
        # 参数
        stop_losses = [-0.05, -0.06]
        stop_profits = [0.10, 0.12]
        max_holds = [5]
        
        total = len(momentum_tests) * len(stop_losses) * len(stop_profits)
        run_count = 0
        
        for name, cond in momentum_tests:
            for sl in stop_losses:
                for sp in stop_profits:
                    full_name = f"{name}_SL{abs(sl)*100:.0f}_SP{int(sp*100)}"
                    m = self.run_experiment(full_name, cond, sl, sp, 5)
                    results.append(m)
                    run_count += 1
                    if run_count % 5 == 0:
                        logger.info(f"已完成 {run_count}/{total}")
                    time.sleep(0.01)
        
        # 测试MA过滤
        ma_filter_tests = [
            ("MACD+动量3+MA20过滤", "(macd_hist > 0) & (return_3d > 0) & (close > ma20)"),
            ("MACD+动量3+MA60过滤", "(macd_hist > 0) & (return_3d > 0) & (close > ma60)"),
            ("MACD+动量3+MA多头过滤", "(macd_hist > 0) & (return_3d > 0) & (ma20 > ma60)"),
            ("MACD+动量3+完全多头", "(macd_hist > 0) & (return_3d > 0) & (close > ma20) & (ma20 > ma60)"),
        ]
        
        for name, cond in ma_filter_tests:
            for sl in [-0.06]:
                for sp in [0.12]:
                    full_name = f"{name}_SL{abs(sl)*100:.0f}_SP{int(sp*100)}"
                    m = self.run_experiment(full_name, cond, sl, sp, 5)
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
    
    results = miner.run_round_6()
    miner.save_results(results, 6)
    
    # 汇总输出
    print("\n" + "=" * 140)
    print("第6轮实验结果（动量周期测试 + MA过滤）")
    print("=" * 140)
    
    # 去重
    seen = set()
    unique = []
    for r in results:
        if r.factor_name not in seen:
            seen.add(r.factor_name)
            unique.append(r)
    
    unique.sort(key=lambda x: x.test_return, reverse=True)
    
    print(f"\n{'因子名称':<40} {'测试收益':<10} {'训练收益':<10} {'样本外衰减':<10} {'交易次数':<8} {'胜率':<8}")
    print("-" * 140)
    
    for r in unique:
        print(f"{r.factor_name:<40} {r.test_return:<10.2%} {r.train_return:<10.2%} {r.oos_decay:<10.2%} {r.trade_count:>8} {r.win_rate:>8.1%}")
    
    # 最稳定策略
    print("\n" + "=" * 140)
    print("最稳定策略（样本外衰减<20%）：")
    print("-" * 140)
    
    stable = [r for r in unique if abs(r.oos_decay) < 0.2]
    for r in stable:
        print(f"{r.factor_name:<40} 测试={r.test_return:>8.2%} 训练={r.train_return:>8.2%} 衰减={r.oos_decay:>8.2%}")


if __name__ == '__main__':
    main()