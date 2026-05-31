#!/usr/bin/env python3
"""
ETF多因子挖掘框架 v2.0
=====================
改进点（基于第1轮实验）：
1. 加入510300大盘过滤（必须在大盘MA多头时才能买入）
2. 调整止损/止盈参数
3. 放宽金叉条件
4. 测试多条件组合
"""
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class FactorMetrics:
    """因子评价指标"""
    factor_name: str
    ic_mean: float = 0.0
    ir: float = 0.0
    p_value: float = 1.0
    
    # 回测指标
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    avg_hold_days: float = 0.0
    
    # 训练/测试
    train_return: float = 0.0
    test_return: float = 0.0
    oos_decay: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


class FactorCalculator:
    """因子计算器"""
    
    @staticmethod
    def calc_ma(series: pd.Series, n: int) -> pd.Series:
        return series.rolling(n).mean()
    
    @staticmethod
    def calc_rsi(series: pd.Series, n: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(n).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = series.ewm(span=fast).mean()
        ema_slow = series.ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        hist = (dif - dea) * 2
        return dif, dea, hist
    
    @staticmethod
    def calc_boll(series: pd.Series, n: int = 20, k: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        mid = series.rolling(n).mean()
        std = series.rolling(n).std()
        upper = mid + k * std
        lower = mid - k * std
        return upper, mid, lower
    
    @staticmethod
    def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(n).mean()
    
    @staticmethod
    def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3) -> Tuple[pd.Series, pd.Series, pd.Series]:
        lowest_low = low.rolling(n).min()
        highest_high = high.rolling(n).max()
        rsv = (close - lowest_low) / (highest_high - lowest_low + 1e-10) * 100
        K = rsv.ewm(com=m1-1).mean()
        D = K.ewm(com=m2-1).mean()
        J = 3 * K - 2 * D
        return K, D, J


class FactorMiner:
    """因子挖掘器 v2.0（带大盘过滤）"""
    
    START_DATE = '2021-05-01'
    END_DATE = '2026-05-29'
    TRAIN_END = '2024-05-01'
    TEST_START = '2024-05-01'
    
    def __init__(self, use_market_filter: bool = True):
        self.pool_loader = ETFListLoader()
        self.data_loader = DataLoader()
        self.factor_calc = FactorCalculator()
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.market_data: Optional[pd.DataFrame] = None
        self.use_market_filter = use_market_filter  # 是否使用大盘过滤
        self.results: List[FactorMetrics] = []
        
    def load_data(self):
        """加载数据"""
        logger.info("加载ETF数据...")
        
        codes = self.pool_loader.load()
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
        
        # 加载510300大盘数据
        if '510300' in self.etf_data:
            self.market_data = self.etf_data['510300'].copy()
            self.market_data = self.add_factors(self.market_data)
    
    def add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加因子"""
        df = df.copy()
        
        for n in [5, 10, 20, 60, 120]:
            df[f'ma{n}'] = self.factor_calc.calc_ma(df['close'], n)
        
        df['rsi6'] = self.factor_calc.calc_rsi(df['close'], 6)
        df['rsi14'] = self.factor_calc.calc_rsi(df['close'], 14)
        
        df['dif'], df['dea'], df['macd_hist'] = self.factor_calc.calc_macd(df['close'])
        
        df['k'], df['d'], df['j'] = self.factor_calc.calc_kdj(df['high'], df['low'], df['close'])
        
        df['boll_upper'], df['boll_mid'], df['boll_lower'] = self.factor_calc.calc_boll(df['close'])
        
        df['atr'] = self.factor_calc.calc_atr(df['high'], df['low'], df['close'])
        
        df['vol_ma20'] = self.factor_calc.calc_ma(df['volume'], 20)
        df['vol_ratio'] = df['volume'] / df['vol_ma20'].replace(0, np.nan)
        
        # 动量因子
        for n in [1, 5, 10, 20]:
            df[f'return_{n}d'] = df['close'].pct_change(n)
        
        # 均线多头排列
        df['ma_arrange'] = ((df['ma5'] > df['ma10']) & 
                           (df['ma10'] > df['ma20']) & 
                           (df['ma20'] > df['ma60'])).astype(int)
        
        return df
    
    def is_market_bullish(self, date: pd.Timestamp) -> bool:
        """判断大盘在指定日期是否多头"""
        if not self.use_market_filter or self.market_data is None:
            return True
        
        df = self.market_data
        df_before = df[df['date'] <= date]
        
        if len(df_before) < 5:
            return True
        
        latest = df_before.iloc[-1]
        
        # 大盘趋势：收盘>MA20>MA60
        return (
            latest['close'] > latest['ma20'] and
            latest['close'] > latest['ma60'] and
            latest['ma20'] > latest['ma60']
        )
    
    def backtest(
        self,
        df: pd.DataFrame,
        entry_condition: str,
        stop_loss: float = -0.05,
        stop_profit: float = 0.08,
        max_hold_days: int = 7,
        require_market_bull: bool = True
    ) -> FactorMetrics:
        """回测"""
        metrics = FactorMetrics(factor_name=entry_condition)
        
        trades = []
        position = None
        entry_date = None
        entry_price = None
        
        train_df = df[df['date'] < self.TRAIN_END]
        test_df = df[df['date'] >= self.TEST_START]
        
        def check_condition(row, condition, market_date):
            """检查条件，包含大盘过滤"""
            try:
                result = bool(eval(condition, {'np': np}, row.to_dict()))
                if result and require_market_bull:
                    result = result and self.is_market_bullish(market_date)
                return result
            except:
                return False
        
        # 训练集
        for _, row in train_df.iterrows():
            if position is None:
                if check_condition(row, entry_condition, row['date']):
                    position = 'long'
                    entry_date = row['date']
                    entry_price = row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold_days:
                    reason = "止损" if pnl <= stop_loss else ("止盈" if pnl >= stop_profit else "到期")
                    trades.append({
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'exit_date': row['date'],
                        'exit_price': row['close'],
                        'pnl': pnl,
                        'hold_days': hold_days,
                        'reason': reason,
                        'period': 'train'
                    })
                    position = None
        
        # 测试集
        for _, row in test_df.iterrows():
            if position is None:
                if check_condition(row, entry_condition, row['date']):
                    position = 'long'
                    entry_date = row['date']
                    entry_price = row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold_days:
                    reason = "止损" if pnl <= stop_loss else ("止盈" if pnl >= stop_profit else "到期")
                    trades.append({
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'exit_date': row['date'],
                        'exit_price': row['close'],
                        'pnl': pnl,
                        'hold_days': hold_days,
                        'reason': reason,
                        'period': 'test'
                    })
                    position = None
        
        # 计算指标
        train_trades = [t for t in trades if t['period'] == 'train']
        test_trades = [t for t in trades if t['period'] == 'test']
        
        if train_trades:
            metrics.train_return = sum(t['pnl'] for t in train_trades)
        if test_trades:
            metrics.test_return = sum(t['pnl'] for t in test_trades)
        
        if trades:
            metrics.trade_count = len(trades)
            metrics.win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades)
            metrics.avg_hold_days = np.mean([t['hold_days'] for t in trades])
            
            if metrics.avg_hold_days > 0 and metrics.test_return != 0:
                metrics.annual_return = metrics.test_return / (metrics.avg_hold_days / 252)
        
        if metrics.train_return != 0:
            metrics.oos_decay = (metrics.test_return - metrics.train_return) / abs(metrics.train_return)
        
        return metrics
    
    def run_single_factor(self, factor_name: str, condition: str) -> FactorMetrics:
        """测试单个因子"""
        metrics_list = []
        target_codes = set(self.pool_loader.load())
        
        for code, df in self.etf_data.items():
            if code not in target_codes:
                continue
            
            df = self.add_factors(df)
            metrics = self.backtest(df, condition)
            metrics_list.append(metrics)
        
        avg_metrics = FactorMetrics(factor_name=factor_name)
        if metrics_list:
            avg_metrics.test_return = np.mean([m.test_return for m in metrics_list])
            avg_metrics.train_return = np.mean([m.train_return for m in metrics_list])
            avg_metrics.trade_count = sum(m.trade_count for m in metrics_list)
            avg_metrics.win_rate = np.mean([m.win_rate for m in metrics_list])
            avg_metrics.avg_hold_days = np.mean([m.avg_hold_days for m in metrics_list])
            
            if avg_metrics.train_return != 0:
                avg_metrics.oos_decay = (avg_metrics.test_return - avg_metrics.train_return) / abs(avg_metrics.train_return)
        
        return avg_metrics
    
    def run_round(self, run_id: int) -> List[FactorMetrics]:
        """运行10次回测"""
        logger.info(f"执行回测 #{run_id}")
        
        # 第2轮测试的因子（加入大盘过滤 + 调整参数）
        test_conditions = [
            # 趋势因子
            ("MA20多头+大盘", "close > ma20"),
            ("MA60多头+大盘", "close > ma60"),
            ("MA120多头+大盘", "close > ma120"),
            ("均线多头排列+大盘", "(close > ma20) & (ma20 > ma60) & (ma60 > ma120)"),
            
            # MACD
            ("MACD红柱+大盘", "macd_hist > 0"),
            
            # RSI
            ("RSI超卖+大盘", "rsi14 < 30"),
            ("RSI适中+大盘", "(rsi14 > 40) & (rsi14 < 70)"),
            
            # 动量
            ("动量5日+大盘", "return_5d > 0.02"),
            ("动量10日+大盘", "return_10d > 0.05"),
            
            # 量价
            ("放量+大盘", "vol_ratio > 1.5"),
            
            # 布林带
            ("布林下轨+大盘", "close < boll_lower"),
            
            # 复合条件
            ("MA60+RSI适中+大盘", "(close > ma60) & (rsi14 > 40) & (rsi14 < 70)"),
            ("放量+MA多头+大盘", "(vol_ratio > 1.3) & (close > ma20)"),
        ]
        
        results = []
        for name, cond in test_conditions:
            metrics = self.run_single_factor(name, cond)
            metrics.factor_name = f"run{run_id}_{name}"
            results.append(metrics)
            time.sleep(0.1)
        
        return results
    
    def run_full_round(self, round_id: int) -> List[FactorMetrics]:
        """运行完整一轮"""
        all_results = []
        
        for i in range(10):
            results = self.run_round(i + 1)
            all_results.extend(results)
        
        return all_results
    
    def save_results(self, results: List[FactorMetrics], round_id: int):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f'round{round_id}.json'
        
        data = {
            'round_id': round_id,
            'timestamp': datetime.now().isoformat(),
            'market_filter': self.use_market_filter,
            'start_date': self.START_DATE,
            'end_date': self.END_DATE,
            'train_period': f"2021-05-01 ~ 2024-05-01",
            'test_period': f"2024-05-01 ~ 2026-05-29",
            'stop_loss': -0.05,
            'stop_profit': 0.08,
            'max_hold_days': 7,
            'results': [r.to_dict() for r in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    logger.info("=" * 60)
    logger.info("ETF多因子挖掘框架 v2.0（带大盘过滤）")
    logger.info("=" * 60)
    
    miner = FactorMiner(use_market_filter=True)
    miner.load_data()
    
    results = miner.run_full_round(2)
    miner.save_results(results, 2)
    
    # 打印汇总
    logger.info("=" * 60)
    logger.info("第2轮结果汇总")
    logger.info("=" * 60)
    
    sorted_results = sorted(results, key=lambda x: x.test_return, reverse=True)
    
    print(f"{'因子名称':<25} {'测试收益':<10} {'训练收益':<10} {'样本外衰减':<10} {'交易次数':<8} {'胜率':<8}")
    print('-' * 80)
    for r in sorted_results[:15]:
        name = r.factor_name.replace('run2_', '')
        print(f"{name:<25} {r.test_return:<10.2%} {r.train_return:<10.2%} {r.oos_decay:<10.2%} {r.trade_count:>8} {r.win_rate:>8.1%}")


if __name__ == '__main__':
    main()