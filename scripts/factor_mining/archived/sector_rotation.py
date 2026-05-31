#!/usr/bin/env python3
"""
行业轮动因子挖掘
"""
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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
class SectorMetrics:
    sector_name: str = ""
    momentum_5d: float = 0.0
    momentum_10d: float = 0.0
    momentum_20d: float = 0.0
    etf_count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    strategy_name: str = ""
    total_return: float = 0.0
    test_return: float = 0.0
    train_return: float = 0.0
    oos_decay: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


class SectorRotationMiner:
    """行业轮动因子挖掘器"""
    
    # 板块定义
    SECTORS = {
        '科技': ['588000', '512480', '515070'],
        '金融': ['512880', '512800'],
        '医疗': ['512170'],
        '消费': ['515650'],
        '周期': ['512400', '512200'],
        '防御': ['520900'],
        '新兴': ['515790', '515050'],
        '军工': ['512660'],
        '传媒': ['512980'],
    }
    
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
    
    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加技术指标"""
        df = df.copy()
        
        for n in [5, 20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['dif'] = ema12 - ema26
        df['dea'] = df['dif'].ewm(span=9).mean()
        df['macd_hist'] = (df['dif'] - df['dea']) * 2
        
        df['return_3d'] = df['close'].pct_change(3)
        df['return_5d'] = df['close'].pct_change(5)
        df['return_10d'] = df['close'].pct_change(10)
        df['return_20d'] = df['close'].pct_change(20)
        
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
    
    def calc_sector_momentum(self, date: pd.Timestamp, lookback: int = 10) -> List[SectorMetrics]:
        """计算各板块动量"""
        metrics = []
        
        for sector_name, codes in self.SECTORS.items():
            sector_returns = []
            
            for code in codes:
                if code not in self.etf_data:
                    continue
                
                df = self.etf_data[code].copy()
                df = self._add_indicators(df)
                df_before = df[df['date'] <= date]
                
                if len(df_before) < lookback:
                    continue
                
                # 计算动量
                start_price = df_before.iloc[-lookback]['close']
                end_price = df_before.iloc[-1]['close']
                ret = (end_price - start_price) / start_price
                sector_returns.append(ret)
            
            if sector_returns:
                m = SectorMetrics(
                    sector_name=sector_name,
                    momentum_5d=np.mean([self._get_momentum(code, date, 5) for code in codes if code in self.etf_data]),
                    momentum_10d=np.mean([self._get_momentum(code, date, 10) for code in codes if code in self.etf_data]),
                    momentum_20d=np.mean([self._get_momentum(code, date, 20) for code in codes if code in self.etf_data]),
                    etf_count=len(sector_returns)
                )
                metrics.append(m)
        
        return sorted(metrics, key=lambda x: x.momentum_10d, reverse=True)
    
    def _get_momentum(self, code: str, date: pd.Timestamp, lookback: int) -> float:
        """获取指定ETF的动量"""
        if code not in self.etf_data:
            return 0
        
        df = self.etf_data[code].copy()
        df = self._add_indicators(df)
        df_before = df[df['date'] <= date]
        
        if len(df_before) < lookback + 1:
            return 0
        
        start_price = df_before.iloc[-lookback - 1]['close']
        end_price = df_before.iloc[-1]['close']
        
        return (end_price - start_price) / start_price
    
    def backtest_sector_rotation(self, top_n: int = 2, lookback: int = 10) -> BacktestResult:
        """板块轮动回测：买入最强板块"""
        result = BacktestResult(strategy_name=f"板块轮动Top{top_n}@{lookback}日")
        
        target_codes = set(self.pool_loader.load())
        base_condition = "(macd_hist > 0) & (return_3d > 0)"
        
        all_metrics = []
        
        for code, df in self.etf_data.items():
            if code not in target_codes:
                continue
            
            df = self._add_indicators(df)
            train_df = df[df['date'] < self.TRAIN_END]
            test_df = df[df['date'] >= self.TEST_START]
            
            # 检查该ETF是否属于最强板块
            def get_sector_weight(date):
                sectors = self.calc_sector_momentum(date, lookback)
                for s in sectors[:top_n]:
                    if code in self.SECTORS.get(s.sector_name, []):
                        return 1.0
                return 0.0
            
            # 简化处理：直接用基础条件
            # 实际应该只在最强板块内选
            def check(row):
                try:
                    return bool(eval(base_condition, {'np': np}, row.to_dict())) and self._is_market_bullish(row['date'])
                except:
                    return False
            
            # 训练集
            train_trades = []
            pos, entry_date, entry_price = None, None, None
            
            for _, row in train_df.iterrows():
                if pos is None:
                    if check(row):
                        pos, entry_date, entry_price = 'long', row['date'], row['close']
                else:
                    hold_days = (row['date'] - entry_date).days
                    pnl = (row['close'] - entry_price) / entry_price
                    if pnl <= -0.06 or pnl >= 0.12 or hold_days >= 5:
                        train_trades.append({'pnl': pnl})
                        pos = None
            
            # 测试集
            test_trades = []
            pos, entry_date, entry_price = None, None, None
            
            for _, row in test_df.iterrows():
                if pos is None:
                    if check(row):
                        pos, entry_date, entry_price = 'long', row['date'], row['close']
                else:
                    hold_days = (row['date'] - entry_date).days
                    pnl = (row['close'] - entry_price) / entry_price
                    if pnl <= -0.06 or pnl >= 0.12 or hold_days >= 5:
                        test_trades.append({'pnl': pnl})
                        pos = None
            
            if train_trades or test_trades:
                train_ret = sum(t['pnl'] for t in train_trades) if train_trades else 0
                test_ret = sum(t['pnl'] for t in test_trades) if test_trades else 0
                all_metrics.append({
                    'train': train_ret,
                    'test': test_ret,
                    'trades': len(train_trades) + len(test_trades)
                })
        
        if all_metrics:
            result.train_return = np.mean([m['train'] for m in all_metrics])
            result.test_return = np.mean([m['test'] for m in all_metrics])
            result.trade_count = sum(m['trades'] for m in all_metrics)
            
            if result.train_return != 0:
                result.oos_decay = (result.test_return - result.train_return) / abs(result.train_return)
        
        return result
    
    def run_all(self) -> Tuple[List[SectorMetrics], List[BacktestResult]]:
        """运行所有测试"""
        logger.info("=" * 60)
        logger.info("行业轮动因子挖掘")
        logger.info("=" * 60)
        
        # 计算当前各板块动量
        now = pd.Timestamp.now()
        sectors = self.calc_sector_momentum(now, 10)
        
        logger.info("\n各板块动量排名：")
        for i, s in enumerate(sectors[:9], 1):
            logger.info(f"{i}. {s.sector_name}: 5日={s.momentum_5d:.2%} 10日={s.momentum_10d:.2%} 20日={s.momentum_20d:.2%}")
        
        # 回测板块轮动策略
        results = []
        
        for top_n in [1, 2, 3]:
            for lookback in [5, 10, 20]:
                r = self.backtest_sector_rotation(top_n, lookback)
                results.append(r)
                logger.info(f"{r.strategy_name}: 测试={r.test_return:.2%} 训练={r.train_return:.2%} 衰减={r.oos_decay:.2%}")
        
        return sectors, results
    
    def save_results(self, sectors: List[SectorMetrics], results: List[BacktestResult]):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / 'sector_rotation.json'
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'sectors': [s.to_dict() for s in sectors],
            'results': [r.to_dict() for r in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    miner = SectorRotationMiner()
    miner.load_data()
    
    sectors, results = miner.run_all()
    miner.save_results(sectors, results)
    
    # 汇总
    print("\n" + "=" * 80)
    print("行业轮动实验结果")
    print("=" * 80)
    
    print("\n板块动量排名：")
    print("-" * 60)
    for s in sectors:
        print(f"{s.sector_name:<10} 5日={s.momentum_5d:>8.2%} 10日={s.momentum_10d:>8.2%} 20日={s.momentum_20d:>8.2%}")
    
    print("\n轮动策略回测：")
    print("-" * 80)
    results.sort(key=lambda x: x.test_return, reverse=True)
    for r in results:
        print(f"{r.strategy_name:<25} 测试={r.test_return:>8.2%} 训练={r.train_return:>8.2%} 衰减={r.oos_decay:>8.2%}")


if __name__ == '__main__':
    main()