#!/usr/bin/env python3
"""
量价因子挖掘
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
    
    def to_dict(self) -> dict:
        return asdict(self)


class VolumePriceMiner:
    """量价因子挖掘器"""
    
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
        """添加量价因子"""
        df = df.copy()
        
        # MA
        for n in [5, 20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['dif'] = ema12 - ema26
        df['dea'] = df['dif'].ewm(span=9).mean()
        df['macd_hist'] = (df['dif'] - df['dea']) * 2
        
        # 动量
        df['return_3d'] = df['close'].pct_change(3)
        
        # OBV
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).cumsum()
        df['obv_ma10'] = df['obv'].rolling(10).mean()
        df['obv_signal'] = df['obv'] > df['obv_ma10']
        
        # 成交量
        df['vol_ma5'] = df['volume'].rolling(5).mean()
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20'].replace(0, np.nan)
        df['vol_ratio_5'] = df['volume'] / df['vol_ma5'].replace(0, np.nan)
        
        # VR（成交量变异率）
        df['vr'] = df['volume'].rolling(26).apply(
            lambda x: x[x > 0].sum() / (x[x == 0].count() + 1), raw=False
        ) * 100 / (df['volume'].rolling(26).sum() + 1)
        
        # 量价背离：价格创N日新高但OBV下降
        df['high_n'] = df['high'].rolling(10).max()
        df['price_new_high'] = df['high'] >= df['high_n']
        df['obv_diff'] = df['obv'].diff(5)
        df['divergence'] = df['price_new_high'] & (df['obv_diff'] < 0)
        
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
    
    def backtest(self, df: pd.DataFrame, condition: str,
                 stop_loss: float, stop_profit: float, max_hold: int) -> FactorMetrics:
        """回测"""
        metrics = FactorMetrics()
        
        df = self._add_factors(df)
        train_df = df[df['date'] < self.TRAIN_END]
        test_df = df[df['date'] >= self.TEST_START]
        
        def check(row, date):
            try:
                return bool(eval(condition, {'np': np}, row.to_dict())) and self._is_market_bullish(date)
            except:
                return False
        
        # 训练集
        train_trades = []
        pos, entry_date, entry_price = None, None, None
        
        for _, row in train_df.iterrows():
            if pos is None:
                if check(row, row['date']):
                    pos, entry_date, entry_price = 'long', row['date'], row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold:
                    train_trades.append({'pnl': pnl})
                    pos = None
        
        # 测试集
        test_trades = []
        pos, entry_date, entry_price = None, None, None
        
        for _, row in test_df.iterrows():
            if pos is None:
                if check(row, row['date']):
                    pos, entry_date, entry_price = 'long', row['date'], row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold:
                    test_trades.append({'pnl': pnl})
                    pos = None
        
        if train_trades:
            metrics.train_return = sum(t['pnl'] for t in train_trades)
        if test_trades:
            metrics.test_return = sum(t['pnl'] for t in test_trades)
        if train_trades or test_trades:
            all_trades = train_trades + test_trades
            metrics.trade_count = len(all_trades)
            metrics.win_rate = len([t for t in all_trades if t['pnl'] > 0]) / len(all_trades)
        
        if metrics.train_return != 0:
            metrics.oos_decay = (metrics.test_return - metrics.train_return) / abs(metrics.train_return)
        
        return metrics
    
    def run_experiment(self, name: str, condition: str) -> FactorMetrics:
        """运行实验"""
        target_codes = set(self.pool_loader.load())
        
        all_metrics = []
        for code, df in self.etf_data.items():
            if code not in target_codes:
                continue
            m = self.backtest(df, condition, -0.06, 0.12, 5)
            all_metrics.append(m)
        
        result = FactorMetrics(factor_name=name)
        if all_metrics:
            result.test_return = np.mean([m.test_return for m in all_metrics])
            result.train_return = np.mean([m.train_return for m in all_metrics])
            result.trade_count = sum(m.trade_count for m in all_metrics)
            result.win_rate = np.mean([m.win_rate for m in all_metrics if m.trade_count > 0])
            
            if result.train_return != 0:
                result.oos_decay = (result.test_return - result.train_return) / abs(result.train_return)
        
        return result
    
    def run_all(self) -> List[FactorMetrics]:
        """运行所有量价因子测试"""
        logger.info("=" * 60)
        logger.info("量价因子挖掘")
        logger.info("=" * 60)
        
        results = []
        
        # 基础条件（MACD+动量+大盘）
        base = "(macd_hist > 0) & (return_3d > 0)"
        
        # 量价因子组合
        conditions = [
            # 放量系列
            (f"放量1.5倍+MACD+动量", f"{base} & (vol_ratio > 1.5)"),
            (f"放量2倍+MACD+动量", f"{base} & (vol_ratio > 2.0)"),
            (f"放量3倍+MACD+动量", f"{base} & (vol_ratio > 3.0)"),
            (f"放量5日1.5倍+MACD", f"(macd_hist > 0) & (vol_ratio_5 > 1.5)"),
            
            # OBV系列
            (f"OBV多头+MACD+动量", f"{base} & obv_signal"),
            (f"OBV上升+MACD", "(macd_hist > 0) & (obv_diff > 0)"),
            
            # VR系列
            (f"VR放量+MACD+动量", f"{base} & (vol_ratio > 1.2)"),
            
            # 缩量系列
            (f"缩量+MACD+动量", f"{base} & (vol_ratio < 0.5)"),
            
            # 量价背离
            (f"背离反转+MACD+动量", f"{base} & divergence"),
            
            # 单独量价因子
            (f"OBV多头", "obv_signal"),
            (f"放量1.5倍", "vol_ratio > 1.5"),
        ]
        
        for name, cond in conditions:
            m = self.run_experiment(name, cond)
            results.append(m)
            logger.info(f"{name}: 测试={m.test_return:.2%} 训练={m.train_return:.2%} 衰减={m.oos_decay:.2%}")
            time.sleep(0.01)
        
        return results
    
    def save_results(self, results: List[FactorMetrics]):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / 'volume_price_factors.json'
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'results': [r.to_dict() for r in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    miner = VolumePriceMiner()
    miner.load_data()
    
    results = miner.run_all()
    miner.save_results(results)
    
    # 汇总
    print("\n" + "=" * 80)
    print("量价因子实验结果")
    print("=" * 80)
    
    # 有效因子（测试收益>5% 且 |样本外衰减|<30%）
    effective = [r for r in results if r.test_return > 0.05 and abs(r.oos_decay) < 0.30]
    effective.sort(key=lambda x: x.test_return, reverse=True)
    
    print(f"\n有效量价因子（测试收益>5% 且 |样本外衰减|<30%）：{len(effective)}个")
    print("-" * 80)
    print(f"{'因子名称':<30} {'测试收益':<10} {'训练收益':<10} {'样本外衰减':<12} {'交易次数':<8}")
    print("-" * 80)
    
    for r in effective:
        print(f"{r.factor_name:<30} {r.test_return:<10.2%} {r.train_return:<10.2%} {r.oos_decay:<12.2%} {r.trade_count:>8}")


if __name__ == '__main__':
    main()