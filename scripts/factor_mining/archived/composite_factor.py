#!/usr/bin/env python3
"""
复合因子组合优化
基于已验证的MACD红柱+动量3策略，测试添加其他因子的效果
"""
import sys
import json
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


class CompositeFactorMiner:
    """复合因子组合优化"""
    
    START_DATE = '2021-05-01'
    END_DATE = '2026-05-29'
    TRAIN_END = '2024-05-01'
    TEST_START = '2024-05-01'
    
    # 原始MACD红柱策略绩效（基准）
    BASE_TEST_RETURN = 0.0901
    BASE_TRAIN_RETURN = 0.0950
    BASE_OOS_DECAY = -0.0507  # -5.07%
    
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
        """添加所有因子"""
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
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi14'] = 100 - (100 / (1 + rs))
        
        # 成交量
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20'].replace(0, np.nan)
        
        # OBV
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).cumsum()
        df['obv_ma10'] = df['obv'].rolling(10).mean()
        df['obv_signal'] = (df['obv'] > df['obv_ma10']).astype(int)
        
        # 布林带
        df['boll_mid'] = df['close'].rolling(20).mean()
        df['boll_std'] = df['close'].rolling(20).std()
        df['boll_lower'] = df['boll_mid'] - 2 * df['boll_std']
        
        # 波动率
        df['hv20'] = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        df['hv20_pct'] = df['hv20'].rolling(60).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) >= 20 else 0.5, raw=False
        )
        
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
        
        train_trades, test_trades = [], []
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
        """运行所有复合因子测试"""
        logger.info("=" * 60)
        logger.info("复合因子组合优化")
        logger.info("=" * 60)
        
        logger.info(f"\n基准策略（MACD红柱+动量3）：")
        logger.info(f"  测试收益: {self.BASE_TEST_RETURN:.2%}")
        logger.info(f"  训练收益: {self.BASE_TRAIN_RETURN:.2%}")
        logger.info(f"  样本外衰减: {self.BASE_OOS_DECAY:.2%}")
        
        results = []
        
        # 基础条件
        base = "(macd_hist > 0) & (return_3d > 0)"
        
        # 复合因子组合
        conditions = [
            # 添加放量
            (f"MACD+动量+放量1.5", f"{base} & (vol_ratio > 1.5)"),
            (f"MACD+动量+OBV多头", f"{base} & (obv_signal == 1)"),
            (f"MACD+动量+OBV上升", f"{base} & (obv > obv_ma10)"),
            
            # 添加波动率
            (f"MACD+动量+低波动", f"{base} & (hv20_pct < 0.25)"),
            (f"MACD+动量+布林下轨", f"{base} & (close < boll_lower)"),
            
            # 添加RSI
            (f"MACD+动量+RSI适中", f"{base} & (rsi14 > 40) & (rsi14 < 70)"),
            (f"MACD+动量+RSI偏强", f"{base} & (rsi14 > 50) & (rsi14 < 80)"),
            
            # 多重组合
            (f"MACD+动量+OBV+放量", f"{base} & (obv_signal == 1) & (vol_ratio > 1.3)"),
            (f"MACD+动量+OBV+低波动", f"{base} & (obv_signal == 1) & (hv20_pct < 0.25)"),
            (f"MACD+动量+放量+RSI", f"{base} & (vol_ratio > 1.3) & (rsi14 > 40) & (rsi14 < 70)"),
            
            # 全组合
            (f"全因子组合", f"{base} & (obv_signal == 1) & (vol_ratio > 1.3) & (hv20_pct < 0.25) & (rsi14 > 40) & (rsi14 < 70)"),
        ]
        
        for name, cond in conditions:
            m = self.run_experiment(name, cond)
            results.append(m)
            
            # 与基准对比
            diff = m.test_return - self.BASE_TEST_RETURN
            status = "✅ 超越" if diff > 0 else "❌ 未超越"
            
            logger.info(f"{name}: 测试={m.test_return:.2%} 训练={m.train_return:.2%} 衰减={m.oos_decay:.2%} | {status} (差{diff:+.2%})")
        
        return results
    
    def save_results(self, results: List[FactorMetrics]):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / 'composite_factors.json'
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'base_strategy': {
                'name': 'MACD红柱+动量3',
                'test_return': self.BASE_TEST_RETURN,
                'train_return': self.BASE_TRAIN_RETURN,
                'oos_decay': self.BASE_OOS_DECAY
            },
            'results': [r.to_dict() for r in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    miner = CompositeFactorMiner()
    miner.load_data()
    
    results = miner.run_all()
    miner.save_results(results)
    
    # 汇总
    print("\n" + "=" * 80)
    print("复合因子实验结果")
    print("=" * 80)
    
    # 超越基准的策略
    better = [r for r in results if r.test_return > miner.BASE_TEST_RETURN and abs(r.oos_decay) < 0.30]
    better.sort(key=lambda x: x.test_return, reverse=True)
    
    print(f"\n超越基准的复合因子（测试收益>{miner.BASE_TEST_RETURN:.2%}）：{len(better)}个")
    print("-" * 80)
    
    if better:
        print(f"{'因子名称':<30} {'测试收益':<10} {'训练收益':<10} {'样本外衰减':<12}")
        print("-" * 80)
        for r in better:
            print(f"{r.factor_name:<30} {r.test_return:<10.2%} {r.train_return:<10.2%} {r.oos_decay:<12.2%}")
        
        print(f"\n🏆 推荐使用: {better[0].factor_name}")
        print(f"   测试收益: {better[0].test_return:.2%} (基准: {miner.BASE_TEST_RETURN:.2%})")
        print(f"   提升: {better[0].test_return - miner.BASE_TEST_RETURN:+.2%}")
    else:
        print("无复合因子超越基准，建议继续使用原始MACD红柱+动量3策略")


if __name__ == '__main__':
    main()