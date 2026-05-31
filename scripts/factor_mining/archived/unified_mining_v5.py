#!/usr/bin/env python3
"""
ETF多因子挖掘 v5.0 - ETF专用参数版
==================================
ETF特性：波动小，止盈5-8%，止损3-5%，单笔目标0.5%

13个单因子 + 286个3因子组合 = 299个模型
"""
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import DataLoader
from src.utils.logger import get_logger

logger = get_logger()


# 15个ETF
ETF_POOL = [
    '510300',  # 大盘参考
    '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]
TRADE_ETFS = [c for c in ETF_POOL if c != '510300']
MARKET_CODE = '510300'


# ETF专用参数（v5.0修正）
TAKE_PROFIT = 0.06   # 止盈6%
STOP_LOSS = 0.04      # 止损4%
MIN_HOLD_DAYS = 3     # 最小持仓3天
MAX_HOLD_DAYS = 20    # 最大持仓20天（强制调仓）


class UnifiedBacktester:
    """ETF回测器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.results = []
        self.model_count = 0
        
        logger.info("加载ETF数据...")
        self.etf_data = DataLoader().load(min_rows=300)
        self.etf_data = {k: v for k, v in self.etf_data.items() if k in ETF_POOL}
        
        # 预处理
        market_raw = DataLoader().load_single(MARKET_CODE)
        if market_raw is not None:
            self.market_data = market_raw.copy()
            self._prepare_market()
        else:
            self.market_data = None
            self.market_bullish = True
        
        for code in list(self.etf_data.keys()):
            self.etf_data[code] = self._add_factors(self.etf_data[code].copy())
        
        self.train_end = '2025-05-01'
        self.test_start = '2025-05-02'
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
        logger.info(f"ETF参数：止盈+{TAKE_PROFIT*100:.0f}%，止损-{STOP_LOSS*100:.0f}%，持仓{MIN_HOLD_DAYS}-{MAX_HOLD_DAYS}天")
    
    def _prepare_market(self):
        df = self.market_data.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        self.market_bullish = True
        if len(df) > 60:
            latest = df.iloc[-1]
            self.market_bullish = latest.get('ma20', 0) > latest.get('ma60', 0)
    
    def _add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['dif'] = ema12 - ema26
        df['dea'] = df['dif'].ewm(span=9).mean()
        df['macd_hist'] = (df['dif'] - df['dea']) * 2
        
        # 动量
        for n in [3, 5, 10]:
            df[f'return_{n}d'] = df['close'].pct_change(n)
        
        # OBV
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        df['obv_ma'] = df['obv'].rolling(10).mean()
        
        # 布林带
        df['bb_mid'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + gain / loss.replace(0, 0.001)))
        
        # KDJ
        low14 = df['low'].rolling(14).min()
        high14 = df['high'].rolling(14).max()
        df['kdj_k'] = 100 * (df['close'] - low14) / (high14 - low14)
        df['kdj_d'] = df['kdj_k'].rolling(3).mean()
        
        # SAR（简化版）
        df['sar'] = df['close'].rolling(5).min()
        df['sar_trend'] = df['close'] > df['sar']
        
        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1)))
        )
        df['atr'] = df['tr'].rolling(14).mean()
        
        # ADX（简化版）
        df['adx'] = df['atr'] / df['close'] * 100
        
        df['market_bullish'] = self.market_bullish
        return df
    
    def backtest(self, etf_code: str, signal_fn) -> Optional[Dict]:
        """ETF回测：止盈6%，止损4%，持仓3-20天"""
        if etf_code not in self.etf_data:
            return None
        
        df = self.etf_data[etf_code].copy()
        trades = []
        train_trades = []
        test_trades = []
        position = None
        
        for i in range(60, len(df)):
            row = df.iloc[i]
            date = row['date']
            
            if pd.isna(row['close']) or row['close'] <= 0:
                continue
            
            if position is None and signal_fn(row, 'entry'):
                position = {'entry_date': date, 'entry_price': row['close']}
            
            elif position is not None:
                hold_days = (date - position['entry_date']).days
                pnl = (row['close'] - position['entry_price']) / position['entry_price']
                
                # ETF专用：止盈6%，止损4%，持仓3-20天
                exit_condition = (
                    pnl <= -STOP_LOSS or 
                    pnl >= TAKE_PROFIT or 
                    hold_days >= MAX_HOLD_DAYS
                )
                min_hold_condition = hold_days >= MIN_HOLD_DAYS
                
                if exit_condition and min_hold_condition:
                    trade = {
                        'entry_date': position['entry_date'],
                        'exit_date': date,
                        'return': pnl,
                        'hold_days': hold_days,
                        'exit_reason': 'stop_loss' if pnl <= -STOP_LOSS else 
                                       'take_profit' if pnl >= TAKE_PROFIT else 
                                       'timeout'
                    }
                    if position['entry_date'] < pd.to_datetime(self.test_start):
                        train_trades.append(trade)
                    else:
                        test_trades.append(trade)
                    trades.append(trade)
                    position = None
        
        return {'trades': trades, 'train_trades': train_trades, 'test_trades': test_trades}
    
    def run_factor(self, name: str, signal_fn) -> Optional[Dict]:
        """测试因子"""
        all_trades = {'trades': [], 'train_trades': [], 'test_trades': []}
        
        for code in TRADE_ETFS:
            bt = self.backtest(code, signal_fn)
            if bt and bt['trades']:
                all_trades['trades'].extend(bt['trades'])
                all_trades['train_trades'].extend(bt['train_trades'])
                all_trades['test_trades'].extend(bt['test_trades'])
        
        if not all_trades['trades']:
            return None
        
        return self._calculate_metrics(all_trades, name)
    
    def _calculate_metrics(self, bt: Dict, name: str) -> Dict:
        """计算评价指标"""
        trades = bt['trades']
        train_trades = bt['train_trades']
        test_trades = bt['test_trades']
        
        if len(test_trades) < 5:
            return None
        
        all_returns = [t['return'] for t in trades]
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
        avg_hold = np.mean([t['hold_days'] for t in trades]) if trades else 0
        
        # 关键指标
        mean_return = np.mean(all_returns)
        
        # 退出原因统计
        exit_reasons = {}
        for t in trades:
            reason = t.get('exit_reason', 'unknown')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        test_arr = np.array(test_returns)
        t_stat, p_value = stats.ttest_1samp(test_arr, 0) if len(test_arr) > 1 else (0, 1)
        
        return {
            'name': name,
            'test_return': test,
            'train_return': train,
            'oos_decay': oos_decay,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate,
            'profit_loss_ratio': pl_ratio,
            'trade_count': len(trades),
            'avg_hold_days': avg_hold,
            'mean_return': mean_return,
            'p_value': p_value,
            'exit_reasons': exit_reasons,
        }
    
    def _pass_standards(self, m: dict) -> bool:
        """ETF通过标准（务实）"""
        return (
            m.get('test_return', 0) > 0 and           # 正收益
            m.get('mean_return', 0) > 0.005 and      # 单笔>0.5%
            m.get('sharpe_ratio', 0) > 0.3 and        # 夏普>0.3
            m.get('win_rate', 0) > 0.45 and           # 胜率>45%
            m.get('max_drawdown', 0) > -0.15 and      # 最大回撤>-15%
            m.get('avg_hold_days', 0) >= 3           # 持仓≥3天
        )
    
    def record_and_reflect(self, result: Dict):
        """记录并反思"""
        self.model_count += 1
        self.results.append(result)
        
        if self.model_count % 20 == 0:
            self._deep_reflect()
    
    def _deep_reflect(self):
        """深入反思"""
        elapsed = time.time() - self.start_time
        passed = sum(1 for r in self.results if self._pass_standards(r))
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"【反思点 #{self.model_count}】耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
        logger.info(f"已测试: {len(self.results)} | 通过: {passed} ({passed/len(self.results)*100:.1f}%)")
        
        # 按单笔收益排序
        sorted_recent = sorted(self.results[-20:], key=lambda x: x['mean_return'], reverse=True)
        
        if sorted_recent:
            logger.info("【最近最优（按单笔收益）】")
            for r in sorted_recent[:3]:
                logger.info(f"  {r['name']}: 单笔={r['mean_return']:.2%}, 总收益={r['test_return']:.1%}, 均持仓={r['avg_hold_days']:.1f}天")
        
        logger.info("=" * 80)
        logger.info("")
    
    def save(self):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments_v5'
        output_dir.mkdir(exist_ok=True)
        
        with open(output_dir / 'all_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        passed = [r for r in self.results if self._pass_standards(r)]
        passed_sorted = sorted(passed, key=lambda x: x['test_return'], reverse=True)
        
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
        
        return summary


# 13个单因子
SINGLE_FACTORS = [
    ('T1_MACD红柱', lambda r, _: r.get('macd_hist', 0) > 0),
    ('T2_MA多头排列', lambda r, _: r.get('ma5', 0) > r.get('ma20', 0) > r.get('ma60', 0)),
    ('T3_布林上轨突破', lambda r, _: r.get('close', 0) > r.get('bb_upper', 0) if pd.notna(r.get('bb_upper')) else False),
    ('T4_SAR趋势', lambda r, _: r.get('sar_trend', True)),
    ('T5_大盘多头', lambda r, _: r.get('market_bullish', True)),
    ('T6_ADX趋势', lambda r, _: r.get('adx', 0) > 10 if pd.notna(r.get('adx')) else False),
    ('M1_动量3日', lambda r, _: r.get('return_3d', 0) > 0),
    ('M2_动量5日', lambda r, _: r.get('return_5d', 0) > 0),
    ('M3_RSI适中', lambda r, _: 40 < r.get('rsi', 50) < 70),
    ('M4_KDJ金叉', lambda r, _: r.get('kdj_k', 0) > r.get('kdj_d', 0)),
    ('V1_OBV多头', lambda r, _: r.get('obv', 0) > r.get('obv_ma', 0) if pd.notna(r.get('obv_ma')) else False),
    ('V2_放量', lambda r, _: r.get('volume', 0) > r.get('ma10', 0) * 1.2 if pd.notna(r.get('volume')) and pd.notna(r.get('ma10')) else False),
    ('V3_资金流入', lambda r, _: r.get('obv', 0) > r.get('obv_ma', 0)),
]


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("ETF多因子挖掘 v5.0 - ETF专用参数版")
    logger.info(f"参数：止盈+{TAKE_PROFIT*100:.0f}%，止损-{STOP_LOSS*100:.0f}%，持仓{MIN_HOLD_DAYS}-{MAX_HOLD_DAYS}天")
    logger.info("=" * 80)
    
    backtester = UnifiedBacktester()
    
    # 阶段1：单因子测试
    logger.info(f"\n阶段1：单因子测试（{len(SINGLE_FACTORS)}个）")
    for i, (name, fn) in enumerate(SINGLE_FACTORS, 1):
        logger.info(f"[{i}/{len(SINGLE_FACTORS)}] {name}")
        result = backtester.run_factor(name, fn)
        if result:
            backtester.record_and_reflect(result)
    
    # 阶段2：三因子组合
    factor_pool = {
        'MACD红柱': lambda r, _: r.get('macd_hist', 0) > 0,
        'MA多头排列': lambda r, _: r.get('ma5', 0) > r.get('ma20', 0) > r.get('ma60', 0),
        '布林上轨突破': lambda r, _: r.get('close', 0) > r.get('bb_upper', 0) if pd.notna(r.get('bb_upper')) else False,
        'SAR趋势': lambda r, _: r.get('sar_trend', True),
        '大盘多头': lambda r, _: r.get('market_bullish', True),
        'ADX趋势': lambda r, _: r.get('adx', 0) > 10 if pd.notna(r.get('adx')) else False,
        '动量3日': lambda r, _: r.get('return_3d', 0) > 0,
        '动量5日': lambda r, _: r.get('return_5d', 0) > 0,
        'RSI适中': lambda r, _: 40 < r.get('rsi', 50) < 70,
        'KDJ金叉': lambda r, _: r.get('kdj_k', 0) > r.get('kdj_d', 0),
        'OBV多头': lambda r, _: r.get('obv', 0) > r.get('obv_ma', 0),
        '放量': lambda r, _: r.get('volume', 0) > r.get('ma10', 0) * 1.2 if pd.notna(r.get('volume')) and pd.notna(r.get('ma10')) else False,
        '资金流入': lambda r, _: r.get('obv', 0) > r.get('obv_ma', 0),
    }
    
    combos = list(combinations(factor_pool.keys(), 3))
    
    logger.info(f"\n阶段2：三因子组合测试（{len(combos)}个）")
    for i, combo in enumerate(combos, 1):
        name = '+'.join(combo)
        
        def combo_fn(row, _, combo=combo):
            for f in combo:
                if not factor_pool[f](row, 'check'):
                    return False
            return True
        
        logger.info(f"[{i}/{len(combos)}] {name}")
        result = backtester.run_factor(name, combo_fn)
        if result:
            backtester.record_and_reflect(result)
    
    summary = backtester.save()
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("实验完成")
    logger.info("=" * 80)
    logger.info(f"总模型: {summary['total']}")
    logger.info(f"通过: {summary['passed']}")
    logger.info(f"耗时: {summary['time']:.1f}秒 ({summary['time']/60:.1f}分钟)")


if __name__ == '__main__':
    main()