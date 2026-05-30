#!/usr/bin/env python3
"""
ETF多因子挖掘框架 v1.0
=====================
支持：
1. 15只ETF批量回测
2. 多因子IC/IR分析
3. 训练/测试分割
4. 过拟合检验
5. 大盘过滤（510300）
"""
import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from itertools import product

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
    ic_std: float = 0.0
    ir: float = 0.0
    p_value: float = 1.0
    t_stat: float = 0.0
    sample_count: int = 0
    
    # 回测指标
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    avg_hold_days: float = 0.0
    
    # 过拟合检验
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
    
    @staticmethod
    def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        direction = np.where(close > close.shift(), 1, -1)
        return (direction * volume).cumsum()
    
    @staticmethod
    def calc_cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
        tp = (high + low + close) / 3
        sma = tp.rolling(n).mean()
        mad = (tp - sma).abs().rolling(n).mean()
        return (tp - sma) / (0.015 * mad + 1e-10)


class FactorMiner:
    """因子挖掘器"""
    
    # 时间范围
    START_DATE = '2021-05-01'
    END_DATE = '2026-05-29'
    TRAIN_END = '2024-05-01'
    
    # 数据分割点
    TRAIN_START = '2021-05-01'
    TRAIN_END = '2024-05-01'
    TEST_START = '2024-05-01'
    TEST_END = '2026-05-29'
    
    def __init__(self):
        self.pool_loader = ETFListLoader()
        self.data_loader = DataLoader()
        self.factor_calc = FactorCalculator()
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.market_data: Optional[pd.DataFrame] = None  # 510300
        
        # 实验结果
        self.results: List[FactorMetrics] = []
        
    def load_data(self):
        """加载数据"""
        logger.info("加载ETF数据...")
        
        # 加载15只ETF
        codes = self.pool_loader.load()
        self.etf_data = self.data_loader.load(min_rows=300)
        
        # 过滤时间范围，转换日期格式
        for code in list(self.etf_data.keys()):
            df = self.etf_data[code]
            df = df[(df['date'] >= self.START_DATE) & (df['date'] <= self.END_DATE)]
            if len(df) < 100:
                del self.etf_data[code]
                continue
            df = df.sort_values('date').reset_index(drop=True)
            # 转换日期
            df['date'] = pd.to_datetime(df['date'])
            self.etf_data[code] = df
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
        
        # 加载510300大盘数据
        if '510300' in self.etf_data:
            self.market_data = self.etf_data['510300'].copy()
    
    def add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """为DataFrame添加所有因子"""
        df = df.copy()
        
        # 均线
        for n in [5, 10, 20, 60, 120]:
            df[f'ma{n}'] = self.factor_calc.calc_ma(df['close'], n)
        
        # RSI
        df['rsi6'] = self.factor_calc.calc_rsi(df['close'], 6)
        df['rsi14'] = self.factor_calc.calc_rsi(df['close'], 14)
        
        # MACD
        df['dif'], df['dea'], df['macd_hist'] = self.factor_calc.calc_macd(df['close'])
        
        # KDJ
        df['k'], df['d'], df['j'] = self.factor_calc.calc_kdj(df['high'], df['low'], df['close'])
        
        # 布林带
        df['boll_upper'], df['boll_mid'], df['boll_lower'] = self.factor_calc.calc_boll(df['close'])
        
        # ATR
        df['atr'] = self.factor_calc.calc_atr(df['high'], df['low'], df['close'])
        
        # OBV
        df['obv'] = self.factor_calc.calc_obv(df['close'], df['volume'])
        
        # CCI
        df['cci'] = self.factor_calc.calc_cci(df['high'], df['low'], df['close'])
        
        # 成交量均线
        df['vol_ma20'] = self.factor_calc.calc_ma(df['volume'], 20)
        df['vol_ratio'] = df['volume'] / df['vol_ma20'].replace(0, np.nan)
        
        # 未来收益（用于IC计算）
        for n in [1, 5, 10, 20]:
            df[f'return_{n}d'] = df['close'].pct_change(n).shift(-n)
        
        return df
    
    def is_market_bullish(self) -> bool:
        """判断大盘是否多头"""
        if self.market_data is None:
            return True
        
        df = self.market_data
        latest = df.iloc[-1]
        
        # 大盘趋势条件：收盘>MA20>MA60，且MA20>MA60
        return (
            latest['close'] > latest['ma20'] and
            latest['close'] > latest['ma60'] and
            latest['ma20'] > latest['ma60']
        )
    
    def calc_ic(self, factor_values: np.ndarray, returns: np.ndarray) -> Tuple[float, float, float, float]:
        """计算IC、IR、p值、t统计量"""
        # 去除NaN
        mask = ~(np.isnan(factor_values) | np.isnan(returns))
        f = factor_values[mask]
        r = returns[mask]
        
        if len(f) < 20:
            return 0.0, 0.0, 1.0, 0.0
        
        # Pearson相关系数
        if np.std(f) < 1e-10 or np.std(r) < 1e-10:
            return 0.0, 0.0, 1.0, 0.0
        
        ic = np.corrcoef(f, r)[0, 1]
        if np.isnan(ic):
            return 0.0, 0.0, 1.0, 0.0
        
        # 滚动IC计算IR
        window = min(20, len(f) // 2)
        rolling_ic = []
        for i in range(window, len(f)):
            ic_i = np.corrcoef(f[i-window:i], r[i-window:i])[0, 1]
            if not np.isnan(ic_i):
                rolling_ic.append(ic_i)
        
        if len(rolling_ic) < 5:
            ir = 0.0
        else:
            ic_mean = np.mean(rolling_ic)
            ic_std = np.std(rolling_ic)
            ir = ic_mean / (ic_std + 1e-10)
        
        # t统计量
        t_stat = ic * np.sqrt(len(f) - 2) / np.sqrt(1 - ic**2 + 1e-10)
        
        # p值（近似）
        from scipy import stats
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), len(f) - 2))
        
        return ic, ir, p_value, t_stat
    
    def backtest_single(
        self,
        df: pd.DataFrame,
        entry_condition: str,
        exit_conditions: List[str],
        stop_loss: float = -0.05,
        stop_profit: float = 0.10,
        max_hold_days: int = 10
    ) -> FactorMetrics:
        """单次回测"""
        metrics = FactorMetrics(factor_name=entry_condition)
        
        trades = []
        position = None
        entry_date = None
        entry_price = None
        
        train_df = df[df['date'] < self.TRAIN_END]
        test_df = df[df['date'] >= self.TEST_START]
        
        def check_condition(row, condition):
            """检查条件"""
            try:
                return bool(eval(condition, {'np': np}, row.to_dict()))
            except:
                return False
        
        # 训练集回测
        for _, row in train_df.iterrows():
            if position is None:
                # 检查买入条件
                if check_condition(row, entry_condition):
                    position = 'long'
                    entry_date = row['date']
                    entry_price = row['close']
            else:
                # 检查卖出条件
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                
                should_sell = False
                reason = ""
                
                # 止损/止盈/到期
                if pnl <= stop_loss:
                    should_sell = True
                    reason = "止损"
                elif pnl >= stop_profit:
                    should_sell = True
                    reason = "止盈"
                elif hold_days >= max_hold_days:
                    should_sell = True
                    reason = "到期"
                # 检查其他退出条件
                for cond in exit_conditions:
                    if check_condition(row, cond):
                        should_sell = True
                        reason = cond
                        break
                
                if should_sell:
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
        
        # 测试集回测
        for _, row in test_df.iterrows():
            if position is None:
                if check_condition(row, entry_condition):
                    position = 'long'
                    entry_date = row['date']
                    entry_price = row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                
                should_sell = False
                reason = ""
                
                if pnl <= stop_loss:
                    should_sell = True
                    reason = "止损"
                elif pnl >= stop_profit:
                    should_sell = True
                    reason = "止盈"
                elif hold_days >= max_hold_days:
                    should_sell = True
                    reason = "到期"
                
                if should_sell:
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
        if trades:
            train_trades = [t for t in trades if t['period'] == 'train']
            test_trades = [t for t in trades if t['period'] == 'test']
            
            if train_trades:
                metrics.train_return = sum(t['pnl'] for t in train_trades)
            if test_trades:
                metrics.test_return = sum(t['pnl'] for t in test_trades)
            
            metrics.oos_decay = (metrics.train_return - metrics.test_return) / abs(metrics.train_return) if metrics.train_return != 0 else 0
            
            metrics.trade_count = len(trades)
            metrics.win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades)
            metrics.avg_hold_days = np.mean([t['hold_days'] for t in trades])
            
            # 简化计算（假设平均持仓）
            if metrics.avg_hold_days > 0:
                annual_return = metrics.test_return / (metrics.avg_hold_days / 252)
                metrics.annual_return = annual_return
        
        return metrics
    
    def run_single_factor(self, factor_name: str, condition: str) -> FactorMetrics:
        """运行单个因子测试"""
        metrics_list = []
        
        # 只测试15只目标ETF池中的ETF
        target_codes = set(self.pool_loader.load())
        
        for code, df in self.etf_data.items():
            if code not in target_codes:
                continue
                
            df = self.add_factors(df)
            metrics = self.backtest_single(df, condition, [])
            metrics.factor_name = f"{factor_name}_{code}"
            metrics_list.append(metrics)
        
        # 合并结果
        avg_metrics = FactorMetrics(factor_name=factor_name)
        if metrics_list:
            avg_metrics.ic_mean = np.mean([m.ic_mean for m in metrics_list])
            avg_metrics.ir = np.mean([m.ir for m in metrics_list])
            avg_metrics.total_return = np.sum([m.total_return for m in metrics_list])
            avg_metrics.trade_count = sum(m.trade_count for m in metrics_list)
            avg_metrics.train_return = np.mean([m.train_return for m in metrics_list])
            avg_metrics.test_return = np.mean([m.test_return for m in metrics_list])
            avg_metrics.oos_decay = np.mean([m.oos_decay for m in metrics_list])
        
        return avg_metrics
    
    def run_round(self, run_id: int) -> List[FactorMetrics]:
        """运行单次回测"""
        logger.info(f"执行回测 #{run_id}")
        
        # 测试不同因子组合
        results = []
        
        # 趋势因子测试
        test_conditions = [
            ("MA20多头", "close > ma20"),
            ("MA60多头", "close > ma60"),
            ("MA120多头", "close > ma120"),
            ("MA多头排列", "(close > ma20) & (ma20 > ma60) & (ma60 > ma120)"),
            ("MACD红柱", "macd_hist > 0"),
            ("MACD金叉", "(dif > dea) & (dif.shift(1) <= dea.shift(1))"),
            ("RSI适中", "(rsi14 > 30) & (rsi14 < 70)"),
            ("RSI超卖", "rsi14 < 30"),
            ("KDJ金叉", "(k > d) & (k.shift(1) <= d.shift(1))"),
            ("CCI突破", "cci > 100"),
            ("布林突破", "close > boll_upper"),
            ("放量", "vol_ratio > 1.5"),
        ]
        
        for name, cond in test_conditions:
            metrics = self.run_single_factor(name, cond)
            metrics.factor_name = f"run{run_id}_{name}"
            results.append(metrics)
        
        return results
    
    def run_full_round(self, round_id: int) -> List[FactorMetrics]:
        """运行完整一轮（10次回测）"""
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
            'start_date': self.START_DATE,
            'end_date': self.END_DATE,
            'train_period': f"{self.TRAIN_START} ~ {self.TRAIN_END}",
            'test_period': f"{self.TEST_START} ~ {self.TEST_END}",
            'results': [r.to_dict() for r in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("ETF多因子挖掘框架 v1.0")
    logger.info("=" * 60)
    
    miner = FactorMiner()
    miner.load_data()
    
    # 运行测试
    results = miner.run_full_round(1)
    
    # 保存结果
    miner.save_results(results, 1)
    
    # 打印汇总
    logger.info("=" * 60)
    logger.info("结果汇总")
    logger.info("=" * 60)
    
    # 按夏普排序
    sorted_results = sorted(results, key=lambda x: x.sharpe_ratio, reverse=True)
    
    for r in sorted_results[:10]:
        logger.info(f"{r.factor_name}: 夏普={r.sharpe_ratio:.2f}, 交易={r.trade_count}, 样本外衰减={r.oos_decay:.1%}")


if __name__ == '__main__':
    main()