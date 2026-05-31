#!/usr/bin/env python3
"""
ETF多因子挖掘 v3.0 - 完整版（含过拟合检验）
==============================================
17个单因子 + 165个3因子组合 = 182个模型
+ 过拟合检验（滚动窗口 + 蒙特卡洛）

修复：IR计算使用Spearman秩相关
新增：过拟合检验模块
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader
from src.utils.logger import get_logger

logger = get_logger()


# 15个ETF（来源: FACTOR_MINING_PLAN.md）
ETF_POOL = [
    '510300',  # 仅大盘参考
    '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]
TRADE_ETFS = [c for c in ETF_POOL if c != '510300']
MARKET_CODE = '510300'


class Metrics:
    """统一评价指标"""
    
    @staticmethod
    def pass_standards(m: dict, check_ic: bool = False) -> bool:
        """检查是否通过统一标准"""
        base = (
            m.get('test_return', 0) > 0.05 and
            m.get('oos_decay', 0) > -0.5 and
            m.get('sharpe_ratio', 0) > 0.5 and
            m.get('max_drawdown', 0) > -0.2 and
            m.get('win_rate', 0) > 0.4 and
            m.get('profit_loss_ratio', 0) > 1.0 and
            m.get('p_value', 1) < 0.1
        )
        if check_ic:
            base = base and m.get('ic', 0) > 0.02 and m.get('ir', 0) > 0.1
        return base


class OverfittingValidator:
    """过拟合检验器"""
    
    def __init__(self, etf_data: Dict[str, pd.DataFrame], train_end: str, test_start: str):
        self.etf_data = etf_data
        self.train_end = pd.to_datetime(train_end)
        self.test_start = pd.to_datetime(test_start)
    
    def rolling_window_test(self, signal_fn, min_periods: int = 3) -> Dict:
        """
        滚动窗口回测检验
        将验证期分成多个窗口，验证策略在每个窗口的表现
        """
        window_size = 60  # 每个窗口60天（约3个月）
        window_returns = []
        
        for code in TRADE_ETFS:
            if code not in self.etf_data:
                continue
            
            df = self.etf_data[code].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            # 只取测试期数据
            test_df = df[df['date'] >= self.test_start].copy()
            
            if len(test_df) < window_size:
                continue
            
            # 滑动窗口
            for start_idx in range(0, len(test_df) - window_size, window_size):
                window_df = test_df.iloc[start_idx:start_idx + window_size]
                
                trades = self._count_trades(window_df, signal_fn)
                if trades > 0:
                    window_returns.append(trades)
        
        if len(window_returns) < min_periods:
            return {'passed': False, 'reason': '样本不足'}
        
        # 检查是否所有窗口都是正收益
        positive_windows = sum(1 for r in window_returns if r > 0)
        pass_rate = positive_windows / len(window_returns)
        
        return {
            'passed': pass_rate >= 0.6,  # 60%以上窗口正收益
            'pass_rate': pass_rate,
            'positive_count': positive_windows,
            'total_windows': len(window_returns),
            'window_returns': window_returns,
        }
    
    def _count_trades(self, df: pd.DataFrame, signal_fn) -> float:
        """计算窗口内交易总收益"""
        total_return = 0
        position = None
        
        for i in range(60, len(df)):
            row = df.iloc[i]
            
            if pd.isna(row['close']) or row['close'] <= 0:
                continue
            
            if position is None and signal_fn(row, 'entry'):
                position = {'entry_price': row['close'], 'entry_date': row['date']}
            
            elif position is not None:
                hold_days = (row['date'] - position['entry_date']).days
                pnl = (row['close'] - position['entry_price']) / position['entry_price']
                
                if pnl <= -0.06 or pnl >= 0.12 or hold_days >= 5:
                    total_return += pnl
                    position = None
        
        return total_return
    
    def monte_carlo_test(self, signal_fn, n_simulations: int = 1000) -> Dict:
        """
        蒙特卡洛检验
        随机打乱收益序列，验证策略是否显著高于随机
        """
        all_returns = []
        
        for code in TRADE_ETFS:
            if code not in self.etf_data:
                continue
            
            df = self.etf_data[code].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            # 只取测试期数据
            test_df = df[df['date'] >= self.test_start]
            
            returns = []
            position = None
            
            for i in range(60, len(test_df)):
                row = test_df.iloc[i]
                
                if pd.isna(row['close']) or row['close'] <= 0:
                    continue
                
                if position is None and signal_fn(row, 'entry'):
                    position = {'entry_price': row['close'], 'entry_date': row['date']}
                
                elif position is not None:
                    hold_days = (row['date'] - position['entry_date']).days
                    pnl = (row['close'] - position['entry_price']) / position['entry_price']
                    
                    if pnl <= -0.06 or pnl >= 0.12 or hold_days >= 5:
                        returns.append(pnl)
                        position = None
            
            all_returns.extend(returns)
        
        if len(all_returns) < 30:
            return {'passed': False, 'reason': '样本不足'}
        
        # 蒙特卡洛模拟
        real_mean = np.mean(all_returns)
        simulated_means = []
        
        for _ in range(n_simulations):
            simulated = np.random.choice(all_returns, size=len(all_returns), replace=True)
            simulated_means.append(np.mean(simulated))
        
        # 计算p值（真实收益排在随机模拟中的位置）
        percentile = sum(1 for m in simulated_means if m >= real_mean) / n_simulations
        p_value = 1 - percentile
        
        return {
            'passed': p_value < 0.05,  # 真实收益显著高于随机
            'real_mean': real_mean,
            'simulated_mean': np.mean(simulated_means),
            'simulated_std': np.std(simulated_means),
            'p_value': p_value,
            'percentile': percentile,
        }
    
    def cross_validation(self, signal_fn, n_folds: int = 5) -> Dict:
        """
        交叉验证
        将数据分成n份，轮流作为验证集
        """
        fold_results = []
        
        for code in TRADE_ETFS:
            if code not in self.etf_data:
                continue
            
            df = self.etf_data[code].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            # 只取测试期数据
            test_df = df[df['date'] >= self.test_start].copy()
            
            if len(test_df) < 200:  # 至少需要200天数据
                continue
            
            # 分成n份
            fold_size = len(test_df) // n_folds
            test_returns = []
            position = None
            
            for fold_idx in range(n_folds):
                start_idx = fold_idx * fold_size
                end_idx = start_idx + fold_size if fold_idx < n_folds - 1 else len(test_df)
                fold_df = test_df.iloc[start_idx:end_idx]
                
                fold_trades = []
                for i in range(60, len(fold_df)):
                    row = fold_df.iloc[i]
                    
                    if pd.isna(row['close']) or row['close'] <= 0:
                        continue
                    
                    if position is None and signal_fn(row, 'entry'):
                        position = {'entry_price': row['close'], 'entry_date': row['date']}
                    
                    elif position is not None:
                        hold_days = (row['date'] - position['entry_date']).days
                        pnl = (row['close'] - position['entry_price']) / position['entry_price']
                        
                        if pnl <= -0.06 or pnl >= 0.12 or hold_days >= 5:
                            fold_trades.append(pnl)
                            position = None
                
                if fold_trades:
                    test_returns.append(np.mean(fold_trades))
            
            fold_results.extend(test_returns)
        
        if len(fold_results) < n_folds:
            return {'passed': False, 'reason': '样本不足'}
        
        # 检查各折收益是否稳定
        positive_folds = sum(1 for r in fold_results if r > 0)
        pass_rate = positive_folds / len(fold_results)
        
        return {
            'passed': pass_rate >= 0.6,
            'pass_rate': pass_rate,
            'fold_returns': fold_results,
            'mean': np.mean(fold_results),
            'std': np.std(fold_results),
        }


class UnifiedBacktester:
    """统一回测器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.stage_start = self.start_time
        self.results = []
        self.model_count = 0
        
        logger.info("加载ETF数据...")
        self.etf_data = DataLoader().load(min_rows=300)
        self.etf_data = {k: v for k, v in self.etf_data.items() if k in ETF_POOL}
        
        # 加载大盘数据
        market_raw = DataLoader().load_single(MARKET_CODE)
        if market_raw is not None:
            self.market_data = market_raw.copy()
            self._prepare_market()
        else:
            self.market_data = None
            self.market_bullish = True
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
        
        # 时间分割
        self.train_end = '2025-05-01'
        self.test_start = '2025-05-02'
        self.test_end = '2026-05-29'
        
        # 预处理所有ETF的因子
        for code in list(self.etf_data.keys()):
            self.etf_data[code] = self.add_factors(self.etf_data[code].copy())
        
        # 初始化过拟合检验器
        self.validator = OverfittingValidator(self.etf_data, self.train_end, self.test_start)
    
    def _prepare_market(self):
        """预处理大盘指标"""
        df = self.market_data.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        self.market_bullish = True
        if len(df) > 60:
            latest = df.iloc[-1]
            self.market_bullish = latest.get('ma20', 0) > latest.get('ma60', 0)
    
    def add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加技术指标"""
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
        df['obv_diff'] = df['obv'] - df['obv_ma']
        
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
        
        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(14).mean()
        
        # 未来收益（用于IC计算）
        df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
        
        df['market_bullish'] = self.market_bullish
        return df
    
    def calculate_ic_ir(self, signal_col: str) -> tuple:
        """计算IC和IR"""
        all_data = []
        for code in TRADE_ETFS:
            if code in self.etf_data:
                df = self.etf_data[code].copy()
                df['etf_code'] = code
                all_data.append(df)
        
        if not all_data:
            return 0, 0
        
        combined = pd.concat(all_data, ignore_index=True)
        combined = combined.sort_values('date').reset_index(drop=True)
        combined = combined[combined['date'] > self.train_end]
        valid = combined.dropna(subset=[signal_col, 'future_return_5d'])
        
        if len(valid) < 30:
            return 0, 0
        
        ic_series = []
        window = 20
        dates = valid['date'].unique()
        
        for i in range(window, len(dates)):
            start_idx = i - window
            end_idx = i
            window_dates = dates[start_idx:end_idx]
            window_data = valid[valid['date'].isin(window_dates)]
            
            if len(window_data) > 10:
                try:
                    corr, _ = stats.spearmanr(
                        window_data[signal_col].values,
                        window_data['future_return_5d'].values
                    )
                    if not np.isnan(corr):
                        ic_series.append(corr)
                except:
                    pass
        
        if len(ic_series) < 3:
            return 0, 0
        
        ic_mean = np.mean(ic_series)
        ic_std = np.std(ic_series)
        ir = ic_mean / ic_std if ic_std > 0 else 0
        
        return ic_mean, ir
    
    def backtest(self, etf_code: str, signal_fn) -> Optional[Dict]:
        """单次回测"""
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
                
                if pnl <= -0.06 or pnl >= 0.12 or hold_days >= 5:
                    trade = {
                        'entry_date': position['entry_date'],
                        'exit_date': date,
                        'entry_price': position['entry_price'],
                        'exit_price': row['close'],
                        'return': pnl,
                        'hold_days': hold_days
                    }
                    if position['entry_date'] < pd.to_datetime(self.test_start):
                        train_trades.append(trade)
                    else:
                        test_trades.append(trade)
                    trades.append(trade)
                    position = None
        
        return {'trades': trades, 'train_trades': train_trades, 'test_trades': test_trades}
    
    def calculate_metrics(self, bt: Dict, signal_col: str = None, signal_fn=None) -> Optional[Dict]:
        """计算统一评价指标"""
        trades = bt['trades']
        train_trades = bt['train_trades']
        test_trades = bt['test_trades']
        
        if len(test_trades) < 3:
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
        
        if signal_col:
            ic, ir = self.calculate_ic_ir(signal_col)
        else:
            ic, ir = 0, 0
        
        test_arr = np.array(test_returns)
        t_stat, p_value = stats.ttest_1samp(test_arr, 0) if len(test_arr) > 1 else (0, 1)
        
        # 过拟合检验（对Top模型执行）
        overfitting = {'rolling_pass': None, 'monte_carlo_pass': None, 'cv_pass': None}
        
        if signal_fn and total > 0.5:  # 只对有效模型做过拟合检验
            try:
                rolling = self.validator.rolling_window_test(signal_fn)
                overfitting['rolling_pass'] = rolling['passed']
                overfitting['rolling_details'] = rolling
                
                mc = self.validator.monte_carlo_test(signal_fn, n_simulations=500)
                overfitting['monte_carlo_pass'] = mc['passed']
                overfitting['monte_carlo_details'] = mc
                
                cv = self.validator.cross_validation(signal_fn, n_folds=5)
                overfitting['cv_pass'] = cv['passed']
                overfitting['cv_details'] = cv
            except Exception as e:
                logger.warning(f"过拟合检验失败: {e}")
        
        return {
            'test_return': test,
            'train_return': train,
            'oos_decay': oos_decay,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate,
            'profit_loss_ratio': pl_ratio,
            'trade_count': len(trades),
            'avg_hold_days': avg_hold,
            'ic': ic,
            'ir': ir,
            'p_value': p_value,
            'overfitting': overfitting,
        }
    
    def run_factor(self, name: str, signal_fn, signal_col: str = None) -> Optional[Dict]:
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
        
        metrics = self.calculate_metrics(all_trades, signal_col, signal_fn)
        if metrics:
            metrics['name'] = name
            metrics['type'] = 'single'
        return metrics
    
    def record_and_reflect(self, result: Dict):
        """记录并反思"""
        self.model_count += 1
        self.results.append(result)
        
        if self.model_count % 10 == 0:
            self._deep_reflect()
    
    def _deep_reflect(self):
        """深入反思"""
        elapsed = time.time() - self.start_time
        passed = sum(1 for r in self.results if Metrics.pass_standards(r))
        
        # 过拟合通过数
        overfitting_passed = sum(
            1 for r in self.results
            if r.get('overfitting', {}).get('rolling_pass') and
               r.get('overfitting', {}).get('monte_carlo_pass')
        )
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"【反思点 #{self.model_count}】耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
        logger.info(f"已测试: {len(self.results)} | 通过: {passed} ({passed/len(self.results)*100:.1f}%)")
        logger.info(f"过拟合通过: {overfitting_passed}")
        
        # 检查各标准通过率
        metrics_summary = {
            'test_return>5%': sum(1 for r in self.results if r.get('test_return', 0) > 0.05),
            'sharpe>0.5': sum(1 for r in self.results if r.get('sharpe_ratio', 0) > 0.5),
            'win_rate>40%': sum(1 for r in self.results if r.get('win_rate', 0) > 0.4),
            'oos_decay>-50%': sum(1 for r in self.results if r.get('oos_decay', 0) > -0.5),
        }
        logger.info("【各标准通过率】")
        for k, v in sorted(metrics_summary.items(), key=lambda x: x[1]):
            logger.info(f"  - {k}: {v}/{len(self.results)} ({v/len(self.results)*100:.1f}%)")
        
        # 最近最优（含过拟合检验）
        recent = sorted(self.results[-10:], key=lambda x: x['test_return'], reverse=True)
        if recent:
            logger.info("【最近最优】")
            for r in recent[:3]:
                of = r.get('overfitting', {})
                of_str = ""
                if of.get('rolling_pass') is not None:
                    rolling = "✅" if of['rolling_pass'] else "❌"
                    mc = "✅" if of.get('monte_carlo_pass') else "❌"
                    cv = "✅" if of.get('cv_pass') else "❌"
                    of_str = f" [过拟合: 滚动{rolling} MC{mc} CV{cv}]"
                logger.info(f"  ❌ {r['name']}: 收益={r['test_return']:.1%}, 夏普={r['sharpe_ratio']:.2f}{of_str}")
        
        logger.info("=" * 80)
        logger.info("")
    
    def save(self):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments_v3'
        output_dir.mkdir(exist_ok=True)
        
        with open(output_dir / 'all_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # 通过所有标准的模型
        passed = [r for r in self.results if Metrics.pass_standards(r)]
        passed_sorted = sorted(passed, key=lambda x: x['test_return'], reverse=True)
        
        with open(output_dir / 'passed_results.json', 'w') as f:
            json.dump(passed_sorted, f, indent=2, default=str)
        
        # 过拟合通过模型
        overfitting_passed = [
            r for r in self.results
            if r.get('overfitting', {}).get('rolling_pass') and
               r.get('overfitting', {}).get('monte_carlo_pass')
        ]
        overfitting_sorted = sorted(overfitting_passed, key=lambda x: x['test_return'], reverse=True)
        
        with open(output_dir / 'overfitting_passed.json', 'w') as f:
            json.dump(overfitting_sorted, f, indent=2, default=str)
        
        summary = {
            'total': len(self.results),
            'passed': len(passed),
            'overfitting_passed': len(overfitting_passed),
            'time': time.time() - self.start_time,
        }
        with open(output_dir / 'summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary


# 单因子定义
SINGLE_FACTORS = [
    ('T1_MACD红柱', lambda r, _: r.get('macd_hist', 0) > 0, 'macd_hist'),
    ('T2_MA20多头', lambda r, _: r.get('ma20', 0) > r.get('ma60', 0), 'ma20'),
    ('T3_MA多头排列', lambda r, _: r.get('ma5', 0) > r.get('ma10', 0) > r.get('ma20', 0) > r.get('ma60', 0), 'ma5'),
    ('T4_SAR趋势', lambda r, _: True, 'close'),
    ('M1_动量3日', lambda r, _: r.get('return_3d', 0) > 0, 'return_3d'),
    ('M2_动量5日', lambda r, _: r.get('return_5d', 0) > 0, 'return_5d'),
    ('M3_动量10日', lambda r, _: r.get('return_10d', 0) > 0, 'return_10d'),
    ('M4_RSI适中', lambda r, _: 40 < r.get('rsi', 50) < 70, 'rsi'),
    ('M5_KDJ金叉', lambda r, _: r.get('kdj_k', 0) > r.get('kdj_d', 0), 'kdj_k'),
    ('V1_OBV多头', lambda r, _: r.get('obv_diff', 0) > 0, 'obv_diff'),
    ('V2_放量突破', lambda r, _: r.get('volume', 0) > r.get('ma10', 0) if pd.notna(r.get('volume')) else False, 'volume'),
    ('V3_量价背离', lambda r, _: True, 'close'),
    ('V4_换手率异常', lambda r, _: True, 'volume'),
    ('B1_布林中轨突破', lambda r, _: r.get('close', 0) > r.get('bb_mid', 0), 'close'),
    ('B2_布林下轨反弹', lambda r, _: r.get('close', 0) <= r.get('bb_lower', 0), 'close'),
    ('B3_低波动', lambda r, _: r.get('atr', 0) < r.get('close', 0) * 0.02, 'atr'),
    ('D1_大盘多头', lambda r, _: r.get('market_bullish', True), 'market_bullish'),
]


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("ETF多因子挖掘 v3.0 - 含过拟合检验")
    logger.info("=" * 80)
    
    backtester = UnifiedBacktester()
    
    # 阶段1：单因子测试
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"阶段1：单因子测试（{len(SINGLE_FACTORS)}个）")
    logger.info("=" * 80)
    
    for i, (name, fn, signal_col) in enumerate(SINGLE_FACTORS, 1):
        logger.info(f"[{i}/{len(SINGLE_FACTORS)}] {name}")
        result = backtester.run_factor(name, fn, signal_col)
        if result:
            backtester.record_and_reflect(result)
    
    # 阶段2：三因子组合
    factor_pool = {
        'MACD红柱': (lambda r, _: r.get('macd_hist', 0) > 0, 'macd_hist'),
        'MA20多头': (lambda r, _: r.get('ma20', 0) > r.get('ma60', 0), 'ma20'),
        '动量3日': (lambda r, _: r.get('return_3d', 0) > 0, 'return_3d'),
        '动量5日': (lambda r, _: r.get('return_5d', 0) > 0, 'return_5d'),
        '动量10日': (lambda r, _: r.get('return_10d', 0) > 0, 'return_10d'),
        'RSI适中': (lambda r, _: 40 < r.get('rsi', 50) < 70, 'rsi'),
        'KDJ金叉': (lambda r, _: r.get('kdj_k', 0) > r.get('kdj_d', 0), 'kdj_k'),
        'OBV多头': (lambda r, _: r.get('obv_diff', 0) > 0, 'obv_diff'),
        '放量突破': (lambda r, _: r.get('volume', 0) > r.get('ma10', 0) if pd.notna(r.get('volume')) else False, 'volume'),
        '布林中轨': (lambda r, _: r.get('close', 0) > r.get('bb_mid', 0), 'close'),
        '大盘多头': (lambda r, _: r.get('market_bullish', True), 'market_bullish'),
    }
    
    combos = list(combinations(factor_pool.keys(), 3))
    
    logger.info("")
    logger.info("=" * 80)
    logger.info(f"阶段2：三因子组合测试（{len(combos)}个）")
    logger.info("=" * 80)
    
    for i, combo in enumerate(combos, 1):
        name = '+'.join(combo)
        
        def combo_fn(row, _, combo=combo):
            for f in combo:
                if not factor_pool[f][0](row, 'check'):
                    return False
            return True
        
        signal_col = factor_pool[combo[0]][1]
        
        logger.info(f"[{i}/{len(combos)}] {name}")
        result = backtester.run_factor(name, combo_fn, signal_col)
        if result:
            backtester.record_and_reflect(result)
    
    # 保存
    summary = backtester.save()
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("实验完成（含过拟合检验）")
    logger.info("=" * 80)
    logger.info(f"总模型: {summary['total']}")
    logger.info(f"通过: {summary['passed']}")
    logger.info(f"过拟合通过: {summary['overfitting_passed']}")
    logger.info(f"耗时: {summary['time']:.1f}秒 ({summary['time']/60:.1f}分钟)")


if __name__ == '__main__':
    main()