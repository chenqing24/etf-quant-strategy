#!/usr/bin/env python3
"""
ETF多因子挖掘 v6.0 - 标准化工具版
==================================
使用标准化工具链：
- DataLoader → 数据加载
- IndicatorCalculator → 指标计算
- FactorBacktester → 回测引擎

ETF专用参数：止盈6%，止损4%，持仓3-20天
"""
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.backtest.engine import FactorBacktester, BacktestConfig, BacktestResult
from src.utils.logger import get_logger

logger = get_logger()


# ETF池（15只）
ETF_POOL = [
    '510300',  # 大盘参考
    '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]
TRADE_ETFS = [c for c in ETF_POOL if c != '510300']

# ETF专用参数
TAKE_PROFIT = 0.06   # 止盈6%
STOP_LOSS = 0.04     # 止损4%
MIN_HOLD_DAYS = 3    # 最小持仓3天
MAX_HOLD_DAYS = 20   # 最大持仓20天


# 13个因子定义
FACTORS = {
    # 趋势因子
    'MACD红柱': {'col': 'MACD_hist', 'op': 'gt', 'threshold': 0},
    'MA多头排列': {'col': 'MA5', 'op': 'gt_both', 'refs': ['MA20', 'MA60']},
    '布林上轨突破': {'col': 'close', 'op': 'gt', 'ref': 'BB_upper'},
    'SAR趋势': {'col': 'SAR', 'op': 'lt', 'ref': 'close'},
    '大盘多头': {'col': 'market_bullish', 'op': 'eq', 'threshold': True},
    'ADX趋势': {'col': 'ADX', 'op': 'gt', 'threshold': 25},
    # 动量因子
    '动量3日': {'col': 'return_3d', 'op': 'gt', 'threshold': 0},
    '动量5日': {'col': 'return_5d', 'op': 'gt', 'threshold': 0},
    'RSI适中': {'col': 'RSI_10', 'op': 'between', 'low': 40, 'high': 70},
    'KDJ金叉': {'col': 'K', 'op': 'gt', 'ref': 'D'},
    # 量能因子
    'OBV多头': {'col': 'OBV', 'op': 'gt', 'ref': 'OBV_MA'},
    '放量': {'col': 'volume', 'op': 'gt_ratio', 'ref': 'volume_MA10', 'ratio': 1.2},
    '资金流入': {'col': 'OBV', 'op': 'gt', 'ref': 'OBV_MA'},
}


class UnifiedPipeline:
    """标准化挖掘流程"""
    
    def __init__(self):
        self.start_time = time.time()
        self.results = []
        
        logger.info("=" * 80)
        logger.info("ETF多因子挖掘 v6.0 - 标准化工具版")
        logger.info(f"参数：止盈+{TAKE_PROFIT*100:.0f}%，止损-{STOP_LOSS*100:.0f}%，持仓{MIN_HOLD_DAYS}-{MAX_HOLD_DAYS}天")
        logger.info("=" * 80)
        
        # Step 1: 使用DataLoader加载数据
        logger.info("\n[Step 1] 加载数据...")
        self.loader = DataLoader()
        self.raw_data = self.loader.load(min_rows=300)
        self.raw_data = {k: v for k, v in self.raw_data.items() if k in ETF_POOL}
        logger.info(f"  加载了 {len(self.raw_data)} 只ETF数据")
        
        # Step 2: 使用IndicatorCalculator计算指标
        logger.info("\n[Step 2] 计算指标...")
        self.calculator = IndicatorCalculator()
        self.price_data = {}
        
        # 获取大盘数据（用于市场过滤）
        market_raw = self.loader.load_single('510300')
        market_bullish = True
        if market_raw is not None:
            mdf = market_raw.copy()
            mdf['date'] = pd.to_datetime(mdf['date'])
            mdf = mdf.sort_values('date').reset_index(drop=True)
            for n in [5, 10, 20, 60]:
                mdf[f'ma{n}'] = mdf['close'].rolling(n).mean()
            if len(mdf) > 60:
                latest = mdf.iloc[-1]
                market_bullish = latest.get('ma20', 0) > latest.get('ma60', 0)
        
        for code in self.raw_data:
            df = self.raw_data[code].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            df = self.calculator.calculate_all(df)
            df = self._calculate_custom_factors(df)
            df['market_bullish'] = market_bullish
            self.price_data[code] = df
        
        logger.info(f"  指标计算完成")
        
        # 时间分割
        self.train_end = '2025-05-01'
        self.test_start = '2025-05-02'
    
    def _calculate_custom_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算自定义因子"""
        df = df.copy()
        
        # 移动平均线
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        # 收益率
        for n in [3, 5, 10]:
            df[f'return_{n}d'] = df['close'].pct_change(n)
        
        # 布林带
        df['BB_mid'] = df['close'].rolling(20).mean()
        df['BB_std'] = df['close'].rolling(20).std()
        df['BB_upper'] = df['BB_mid'] + 2 * df['BB_std']
        df['BB_lower'] = df['BB_mid'] - 2 * df['BB_std']
        
        # MACD直方图
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['DIF'] = ema12 - ema26
        df['DEA'] = df['DIF'].ewm(span=9).mean()
        df['MACD_hist'] = (df['DIF'] - df['DEA']) * 2
        
        # OBV
        df['OBV'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        df['OBV_MA'] = df['OBV'].rolling(10).mean()
        
        # 成交量均线
        df['volume_MA10'] = df['volume'].rolling(10).mean()
        
        # 简化SAR（用最近5日最低价）
        df['SAR'] = df['low'].rolling(5).min()
        
        # ADX（简化）
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1)))
        )
        df['ATR'] = df['tr'].rolling(14).mean()
        df['ADX'] = (df['ATR'] / df['close'] * 100).fillna(0)
        
        return df
    
    def _create_signal_fn(self, factor_names: List[str]):
        """根据因子列表创建信号函数"""
        def signal_fn(row: pd.Series) -> bool:
            for fname in factor_names:
                if fname not in FACTORS:
                    continue
                
                config = FACTORS[fname]
                col = config['col']
                op = config['op']
                
                if col not in row.index:
                    return False
                
                val = row.get(col)
                if pd.isna(val):
                    return False
                
                if op == 'gt':
                    if not (val > config.get('threshold', 0)):
                        return False
                elif op == 'lt':
                    if not (val < row.get(config['ref'], float('inf'))):
                        return False
                elif op == 'gt_both':
                    if not (val > row.get(config['refs'][0], 0) and row.get(config['refs'][1], 0) > 0):
                        return False
                elif op == 'between':
                    if not (config['low'] < val < config['high']):
                        return False
                elif op == 'gt_ratio':
                    ref_val = row.get(config['ref'], 0)
                    if not (ref_val > 0 and val > ref_val * config['ratio']):
                        return False
                elif op == 'eq':
                    if not (val == config['threshold']):
                        return False
                elif op == 'gt_ref':
                    if not (val > row.get(config['ref'], 0)):
                        return False
            
            return True
        
        return signal_fn
    
    def backtest_factor(self, name: str, factor_names: List[str]) -> Optional[Dict]:
        """回测单个因子或组合"""
        signal_fn = self._create_signal_fn(factor_names)
        
        all_trades = []
        train_trades = []
        test_trades = []
        
        for code in TRADE_ETFS:
            if code not in self.price_data:
                continue
            
            df = self.price_data[code].copy()
            df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
            
            position = None
            
            for i in range(60, len(df)):
                row = df.iloc[i]
                date_str = row['date_str']
                
                if pd.isna(row['close']) or row['close'] <= 0:
                    continue
                
                # 入场
                if position is None and signal_fn(row):
                    position = {'entry_date': date_str, 'entry_price': row['close']}
                
                # 持仓
                elif position is not None:
                    hold_days = (row['date'] - pd.to_datetime(position['entry_date'])).days
                    pnl = (row['close'] - position['entry_price']) / position['entry_price']
                    
                    exit_condition = (
                        pnl <= -STOP_LOSS or 
                        pnl >= TAKE_PROFIT or 
                        hold_days >= MAX_HOLD_DAYS
                    )
                    min_hold_condition = hold_days >= MIN_HOLD_DAYS
                    
                    if exit_condition and min_hold_condition:
                        reason = '止损' if pnl <= -STOP_LOSS else ('止盈' if pnl >= TAKE_PROFIT else '超时')
                        
                        trade = {
                            'code': code,
                            'entry_date': position['entry_date'],
                            'exit_date': date_str,
                            'return': pnl,
                            'hold_days': hold_days,
                            'exit_reason': reason
                        }
                        
                        if position['entry_date'] < self.test_start:
                            train_trades.append(trade)
                        else:
                            test_trades.append(trade)
                        all_trades.append(trade)
                        position = None
        
        if len(test_trades) < 3:
            return None
        
        return self._calculate_metrics(name, factor_names, all_trades, train_trades, test_trades)
    
    def _calculate_metrics(self, name: str, factor_names: List[str], 
                          all_trades: List, train_trades: List, test_trades: List) -> Dict:
        """计算评价指标"""
        all_returns = [t['return'] for t in all_trades]
        train_returns = [t['return'] for t in train_trades]
        test_returns = [t['return'] for t in test_trades]
        
        total = sum(all_returns)
        train = sum(train_returns)
        test = sum(test_returns)
        oos_decay = (test - train) / abs(train) if train != 0 else 0
        
        arr = np.array(all_returns)
        sharpe = arr.mean() / arr.std() * np.sqrt(252) if arr.std() > 0 else 0
        
        cumret = np.cumprod(1 + arr)
        running_max = np.maximum.accumulate(cumret)
        dd = (cumret - running_max) / running_max
        max_dd = dd.min() if len(dd) > 0 else 0
        
        wins = [r for r in all_returns if r > 0]
        losses = [r for r in all_returns if r < 0]
        win_rate = len(wins) / len(all_returns) if all_returns else 0
        pl_ratio = abs(np.mean(wins)) / abs(np.mean(losses)) if wins and losses else 0
        avg_hold = np.mean([t['hold_days'] for t in all_trades]) if all_trades else 0
        mean_return = np.mean(all_returns)
        
        # 退出原因统计
        exit_reasons = {}
        for t in all_trades:
            reason = t.get('exit_reason', 'unknown')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        from scipy import stats
        test_arr = np.array(test_returns)
        _, p_value = stats.ttest_1samp(test_arr, 0) if len(test_arr) > 1 else (0, 1)
        
        return {
            'name': name,
            'factors': factor_names,
            'test_return': test,
            'train_return': train,
            'oos_decay': oos_decay,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate,
            'profit_loss_ratio': pl_ratio,
            'trade_count': len(all_trades),
            'avg_hold_days': avg_hold,
            'mean_return': mean_return,
            'p_value': p_value,
            'exit_reasons': exit_reasons,
        }
    
    def _pass_standards(self, m: dict) -> bool:
        """ETF通过标准"""
        return (
            m.get('test_return', 0) > 0 and
            m.get('mean_return', 0) > 0.005 and
            m.get('sharpe_ratio', 0) > 0.3 and
            m.get('win_rate', 0) > 0.45 and
            m.get('max_drawdown', 0) > -0.15
        )
    
    def run(self):
        """执行挖掘"""
        from itertools import combinations
        
        # 单因子测试
        logger.info(f"\n[Step 3] 单因子测试（{len(FACTORS)}个）")
        for i, fname in enumerate(FACTORS.keys(), 1):
            logger.info(f"  [{i}/{len(FACTORS)}] {fname}")
            result = self.backtest_factor(fname, [fname])
            if result:
                self.results.append(result)
                self._log_progress()
        
        # 组合测试
        factor_list = list(FACTORS.keys())
        combos = list(combinations(factor_list, 3))
        
        logger.info(f"\n[Step 4] 组合测试（{len(combos)}个）")
        for i, combo in enumerate(combos, 1):
            name = '+'.join(combo)
            logger.info(f"  [{i}/{len(combos)}] {name}")
            result = self.backtest_factor(name, list(combo))
            if result:
                self.results.append(result)
                self._log_progress()
        
        # 保存
        self._save()
        
        elapsed = time.time() - self.start_time
        passed = sum(1 for r in self.results if self._pass_standards(r))
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("实验完成")
        logger.info("=" * 80)
        logger.info(f"总模型: {len(self.results)}")
        logger.info(f"通过: {passed} ({passed/len(self.results)*100:.1f}%)")
        logger.info(f"耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
    
    def _log_progress(self):
        """记录进度"""
        if len(self.results) % 20 == 0:
            passed = sum(1 for r in self.results if self._pass_standards(r))
            elapsed = time.time() - self.start_time
            logger.info(f"    进度: {len(self.results)}个 | 通过: {passed} | 耗时: {elapsed:.0f}秒")
    
    def _save(self):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments_v6'
        output_dir.mkdir(exist_ok=True)
        
        with open(output_dir / 'all_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        passed = [r for r in self.results if self._pass_standards(r)]
        passed_sorted = sorted(passed, key=lambda x: x['mean_return'], reverse=True)
        
        with open(output_dir / 'passed_results.json', 'w') as f:
            json.dump(passed_sorted, f, indent=2, default=str)
        
        summary = {
            'total': len(self.results),
            'passed': len(passed),
            'time': time.time() - self.start_time,
            'params': {
                'take_profit': TAKE_PROFIT,
                'stop_loss': STOP_LOSS,
                'min_hold_days': MIN_HOLD_DAYS,
                'max_hold_days': MAX_HOLD_DAYS,
            }
        }
        with open(output_dir / 'summary.json', 'w') as f:
            json.dump(summary, f, indent=2)


def main():
    pipeline = UnifiedPipeline()
    pipeline.run()


if __name__ == '__main__':
    main()