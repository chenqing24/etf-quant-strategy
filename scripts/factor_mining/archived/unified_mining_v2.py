#!/usr/bin/env python3
"""
ETF多因子挖掘 v2.0 - 修正版
==========================
修复了IR计算错误：
- IC: 使用滚动窗口计算因子信号与未来收益的秩相关系数
- IR = IC均值 / IC标准差
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
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


class UnifiedMetrics:
    """统一评价指标"""
    
    @staticmethod
    def pass_standards(m: dict) -> bool:
        """检查是否通过统一标准"""
        return (
            m.get('test_return', 0) > 0.05 and
            m.get('oos_decay', 0) > -0.5 and
            m.get('sharpe_ratio', 0) > 0.5 and
            m.get('max_drawdown', 0) > -0.2 and
            m.get('win_rate', 0) > 0.4 and
            m.get('profit_loss_ratio', 0) > 1.0 and
            m.get('ic', 0) > 0.02 and
            m.get('ir', 0) > 0.1 and  # 放宽到0.1，因为样本量有限
            m.get('p_value', 1) < 0.1
        )


class UnifiedBacktester:
    """统一回测器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.stage_start = self.start_time
        self.results = []
        self.model_count = 0
        self.factor_cache = {}  # 缓存因子值
        
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
            self.market_bullish = True  # 默认值
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
        
        # 预处理所有ETF的因子（在market_bullish初始化之后）
        for code in list(self.etf_data.keys()):
            self.etf_data[code] = self.add_factors(self.etf_data[code].copy())
        
        # 时间分割
        self.train_end = '2025-05-01'
        self.test_start = '2025-05-02'
        self.test_end = '2026-05-29'
    
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
        """
        计算IC和IR（修正版）
        - IC: 使用滚动窗口计算因子信号与未来收益的秩相关系数
        - IR = IC均值 / IC标准差
        """
        # 合并所有ETF的数据
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
        
        # 只取测试期的数据
        combined = combined[combined['date'] > self.train_end]
        
        # 去除缺失值
        valid = combined.dropna(subset=[signal_col, 'future_return_5d'])
        
        if len(valid) < 30:
            return 0, 0
        
        # 计算IC（秩相关系数）
        ic_series = []
        window = 20  # 滚动窗口大小
        dates = valid['date'].unique()
        
        for i in range(window, len(dates)):
            start_idx = i - window
            end_idx = i
            window_dates = dates[start_idx:end_idx]
            
            window_data = valid[valid['date'].isin(window_dates)]
            
            if len(window_data) > 10:
                # Spearman秩相关系数
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
        
        # IR = IC均值 / IC标准差
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
            
            # 入场
            if position is None and signal_fn(row, 'entry'):
                position = {
                    'entry_date': date,
                    'entry_price': row['close'],
                }
            
            # 持仓
            elif position is not None:
                hold_days = (date - position['entry_date']).days
                pnl = (row['close'] - position['entry_price']) / position['entry_price']
                
                # 止损-6%, 止盈+12%, 超时5天
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
    
    def calculate_metrics(self, bt: Dict, signal_col: str = None) -> Optional[Dict]:
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
        
        # 最大回撤
        cumret = np.cumprod(1 + arr)
        running_max = np.maximum.accumulate(cumret)
        dd = (cumret - running_max) / running_max
        max_dd = dd.min() if len(dd) > 0 else 0
        
        wins = [r for r in all_returns if r > 0]
        losses = [r for r in all_returns if r < 0]
        win_rate = len(wins) / len(all_returns) if all_returns else 0
        pl_ratio = abs(np.mean(wins)) / abs(np.mean(losses)) if wins and losses else 0
        avg_hold = np.mean([t['hold_days'] for t in trades]) if trades else 0
        
        # IC/IR（修正版）
        if signal_col:
            ic, ir = self.calculate_ic_ir(signal_col)
        else:
            ic, ir = 0, 0
        
        # 显著性
        test_arr = np.array(test_returns)
        t_stat, p_value = stats.ttest_1samp(test_arr, 0) if len(test_arr) > 1 else (0, 1)
        
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
        
        metrics = self.calculate_metrics(all_trades, signal_col)
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
        passed = sum(1 for r in self.results if UnifiedMetrics.pass_standards(r))
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"【反思点 #{self.model_count}】耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
        logger.info(f"已测试: {len(self.results)} | 通过: {passed} ({passed/len(self.results)*100:.1f}%)")
        
        # 问题1: 为什么通过率低？
        if passed == 0:
            # 检查哪个标准最严格
            metrics_summary = {
                'test_return>5%': sum(1 for r in self.results if r.get('test_return', 0) > 0.05),
                'sharpe>0.5': sum(1 for r in self.results if r.get('sharpe_ratio', 0) > 0.5),
                'ir>0.1': sum(1 for r in self.results if r.get('ir', 0) > 0.1),
                'p_value<0.1': sum(1 for r in self.results if r.get('p_value', 1) < 0.1),
            }
            logger.info("【问题分析】通过率0%，检查各标准:")
            for k, v in sorted(metrics_summary.items(), key=lambda x: x[1]):
                logger.info(f"  - {k}: {v}/{len(self.results)} 通过 ({v/len(self.results)*100:.1f}%)")
        
        # 问题2: 最近最优的共同特征
        recent = sorted(self.results[-10:], key=lambda x: x['test_return'], reverse=True)
        if recent:
            logger.info("【最近最优】")
            for r in recent[:3]:
                pass_str = "✅" if UnifiedMetrics.pass_standards(r) else "❌"
                logger.info(f"  {pass_str} {r['name']}:")
                logger.info(f"       收益={r['test_return']:.1%}, 衰减={r['oos_decay']:.1%}, 夏普={r['sharpe_ratio']:.2f}, IR={r['ir']:.3f}")
        
        # 问题3: 异常现象
        negative_decay = [r for r in self.results if r.get('oos_decay', 0) < -0.3]
        if negative_decay:
            logger.info(f"【异常现象】{len(negative_decay)}个模型衰减为负（验证期>训练期）")
        
        logger.info("=" * 80)
        logger.info("")
    
    def save(self):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments_v2'
        output_dir.mkdir(exist_ok=True)
        
        with open(output_dir / 'all_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        passed = [r for r in self.results if UnifiedMetrics.pass_standards(r)]
        passed_sorted = sorted(passed, key=lambda x: x['test_return'], reverse=True)
        
        with open(output_dir / 'top10.json', 'w') as f:
            json.dump(passed_sorted[:10], f, indent=2, default=str)
        
        summary = {
            'total': len(self.results),
            'passed': len(passed),
            'time': time.time() - self.start_time,
        }
        with open(output_dir / 'summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary


# 单因子定义（包含signal_col用于IC计算）
SINGLE_FACTORS = [
    ('T1_MACD红柱', lambda r, _: r.get('macd_hist', 0) > 0, 'macd_hist'),
    ('T2_MA20多头', lambda r, _: r.get('ma20', 0) > r.get('ma60', 0), 'ma20'),
    ('T3_MA多头排列', lambda r, _: r.get('ma5', 0) > r.get('ma10', 0) > r.get('ma20', 0) > r.get('ma60', 0), 'ma5'),
    ('T4_SAR趋势', lambda r, _: True, 'close'),  # 简化
    ('M1_动量3日', lambda r, _: r.get('return_3d', 0) > 0, 'return_3d'),
    ('M2_动量5日', lambda r, _: r.get('return_5d', 0) > 0, 'return_5d'),
    ('M3_动量10日', lambda r, _: r.get('return_10d', 0) > 0, 'return_10d'),
    ('M4_RSI适中', lambda r, _: 40 < r.get('rsi', 50) < 70, 'rsi'),
    ('M5_KDJ金叉', lambda r, _: r.get('kdj_k', 0) > r.get('kdj_d', 0), 'kdj_k'),
    ('V1_OBV多头', lambda r, _: r.get('obv_diff', 0) > 0, 'obv_diff'),
    ('V2_放量突破', lambda r, _: r.get('volume', 0) > r.get('ma10', 0) if pd.notna(r.get('volume')) else False, 'volume'),
    ('V3_量价背离', lambda r, _: True, 'close'),  # 简化
    ('V4_换手率异常', lambda r, _: True, 'volume'),  # 简化
    ('B1_布林中轨突破', lambda r, _: r.get('close', 0) > r.get('bb_mid', 0), 'close'),
    ('B2_布林下轨反弹', lambda r, _: r.get('close', 0) <= r.get('bb_lower', 0), 'close'),
    ('B3_低波动', lambda r, _: r.get('atr', 0) < r.get('close', 0) * 0.02, 'atr'),
    ('D1_大盘多头', lambda r, _: r.get('market_bullish', True), 'market_bullish'),
]


def main():
    """主函数"""
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
    
    # 阶段2：三因子组合（165个 = C(11,3)）
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
        
        # 使用第一个因子的signal_col（简化）
        signal_col = factor_pool[combo[0]][1]
        
        logger.info(f"[{i}/{len(combos)}] {name}")
        result = backtester.run_factor(name, combo_fn, signal_col)
        if result:
            backtester.record_and_reflect(result)
    
    # 保存
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