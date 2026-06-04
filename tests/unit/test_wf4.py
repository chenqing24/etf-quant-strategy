#!/usr/bin/env python3
"""
wf4.py 单元测试套件

测试覆盖：
1. 4折日期切分正确性
2. 指标计算（Sharpe/胜率/盈亏比）
3. JSON输出格式
4. 边界情况处理
"""
import sys
import json
import unittest
import pytest
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# US-016: wf4.py 已重写，旧 API (WalkForward4Fold/WF4Fold/WF4Result) 移除
# 旧测试需要重写以测新 API (WFFoldResult, run_wf_backtest, validate_4fold)
# 见 docs/V9_BACKLOG.md US-016-task-002
pytestmark = pytest.mark.skip(
    reason="US-016: wf4.py 重写后旧 API 不存在，需重写测试 (ticket: US-016-task-002, deadline: 2026-06-11)"
)

# 以下 import 已废弃，保留用于重写时的参考
# from scripts.validators.wf4 import (
#     WalkForward4Fold, WF4Fold, WF4Result
# )


# ============================================================
# 测试数据生成器
# ============================================================

def generate_test_data(
    start_date: str = '2023-01-01',
    periods: int = 900,
    trend: str = 'up',
    volatility: float = 0.02
) -> pd.DataFrame:
    """生成测试数据
    
    periods=900 约覆盖到2026-08（≈900个交易日）
    """
    dates = pd.date_range(start=start_date, periods=periods, freq='B')
    
    if trend == 'up':
        base = 100
        drift = 0.001
    elif trend == 'down':
        base = 100
        drift = -0.001
    else:  # flat
        base = 100
        drift = 0.0
    
    np.random.seed(42)
    returns = np.random.normal(drift, volatility, periods)
    prices = base * np.cumprod(1 + returns)
    
    df = pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'code': 'TESTETF',
        'open': prices * 0.99,
        'high': prices * 1.02,
        'low': prices * 0.98,
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, periods)
    })
    
    return df


# ============================================================
# 测试用例
# ============================================================

class TestSplitFolds(unittest.TestCase):
    """测试4折日期切分"""
    
    def setUp(self):
        """生成测试数据（2023-01到2026-08，共约900天，覆盖全部4折）
        
        数据范围需要覆盖到 2026-06-02（约892个交易日）
        """
        self.df = generate_test_data(
            start_date='2023-01-01',
            periods=900,
            trend='up'
        )
        self.wf4 = WalkForward4Fold()
    
    def test_fold_count(self):
        """验证生成4折"""
        folds = self.wf4._split_folds(self.df)
        self.assertEqual(len(folds), 4, f"期望4折，实际{len(folds)}折")
    
    def test_fold_dates_match_design(self):
        """验证折的日期与设计文档一致
        
        设计文档：
        Fold 1: IS[2023-09-26 ~ 2024-12-31] → OOS[2025-01-01 ~ 2025-06-30]
        Fold 2: IS[2023-09-26 ~ 2025-06-30] → OOS[2025-07-01 ~ 2025-12-31]
        Fold 3: IS[2023-09-26 ~ 2025-12-31] → OOS[2026-01-01 ~ 2026-03-31]
        Fold 4: IS[2023-09-26 ~ 2026-03-31] → OOS[2026-04-01 ~ 2026-06-02]
        """
        folds = self.wf4._split_folds(self.df)
        
        expected = [
            (1, '2023-09-26', '2024-12-31', '2025-01-01', '2025-06-30'),
            (2, '2023-09-26', '2025-06-30', '2025-07-01', '2025-12-31'),
            (3, '2023-09-26', '2025-12-31', '2026-01-01', '2026-03-31'),
            (4, '2023-09-26', '2026-03-31', '2026-04-01', '2026-06-02'),
        ]
        
        for i, (fold_idx, train_start, train_end, test_start, test_end) in enumerate(expected):
            with self.subTest(i=i):
                self.assertEqual(folds[i]['fold_idx'], fold_idx)
                self.assertEqual(folds[i]['train_start'], train_start)
                self.assertEqual(folds[i]['train_end'], train_end)
                self.assertEqual(folds[i]['test_start'], test_start)
                self.assertEqual(folds[i]['test_end'], test_end)
    
    def test_oos_sequential(self):
        """验证OOS期顺序（时间上递增）"""
        folds = self.wf4._split_folds(self.df)
        
        # 设计文档的OOS期是递增的：
        # Fold 1 OOS: 2025-01 ~ 2025-06 (最早)
        # Fold 2 OOS: 2025-07 ~ 2025-12
        # Fold 3 OOS: 2026-01 ~ 2026-03
        # Fold 4 OOS: 2026-04 ~ 2026-06 (最晚)
        
        for i in range(1, len(folds)):
            prev_oos_end = folds[i-1]['test_end']
            curr_oos_end = folds[i]['test_end']
            prev_date = datetime.strptime(prev_oos_end, '%Y-%m-%d')
            curr_date = datetime.strptime(curr_oos_end, '%Y-%m-%d')
            self.assertLess(prev_date, curr_date,
                f"Fold{i} OOS结束{prev_oos_end} 应早于 Fold{i+1} OOS结束{curr_oos_end}")


class TestComputeMetrics(unittest.TestCase):
    """测试指标计算"""
    
    def setUp(self):
        self.wf4 = WalkForward4Fold()
        self.config = type('Config', (), {})()
    
    def test_sharpe_calculation(self):
        """验证Sharpe计算"""
        # 上涨趋势数据
        df = generate_test_data(trend='up', volatility=0.015)
        
        metrics = self.wf4._compute_metrics(df, self.config)
        
        self.assertIn('sharpe', metrics)
        self.assertIsInstance(metrics['sharpe'], float)
        # 上涨趋势应该有正Sharpe
        self.assertGreater(metrics['sharpe'], 0, "上涨趋势Sharpe应>0")
    
    def test_win_rate_calculation(self):
        """验证胜率计算"""
        df = generate_test_data(trend='up')
        
        metrics = self.wf4._compute_metrics(df, self.config)
        
        self.assertIn('win_rate', metrics)
        self.assertGreaterEqual(metrics['win_rate'], 0)
        self.assertLessEqual(metrics['win_rate'], 1)
    
    def test_profit_loss_ratio(self):
        """验证盈亏比计算"""
        df = generate_test_data(trend='up')
        
        metrics = self.wf4._compute_metrics(df, self.config)
        
        self.assertIn('profit_loss_ratio', metrics)
        self.assertIn('profit_x_win', metrics)
        # 盈亏比应为正数
        self.assertGreater(metrics['profit_loss_ratio'], 0)
    
    def test_no_trades(self):
        """验证无交易时返回0"""
        # 数据太短，无法生成信号
        df = generate_test_data(periods=20)
        
        metrics = self.wf4._compute_metrics(df, self.config)
        
        self.assertEqual(metrics['sharpe'], 0)
        self.assertEqual(metrics['win_rate'], 0)
    
    def test_all_wins(self):
        """验证全胜时盈亏比处理（avg_loss=0的特殊情况）"""
        # 单边上涨数据，全胜
        df = generate_test_data(trend='up', volatility=0.005)
        
        metrics = self.wf4._compute_metrics(df, self.config)
        
        # 盈亏比应该是 avg_win（因为 avg_loss=0）
        self.assertGreater(metrics['profit_loss_ratio'], 0)


class TestWF4Result(unittest.TestCase):
    """测试WF4Result数据类"""
    
    def test_wf4_fold_to_dict(self):
        """验证WF4Fold序列化"""
        fold = WF4Fold(
            fold=1,
            is_range='2023-09 ~ 2024-12',
            oos_range='2025-01 ~ 2025-06',
            sharpe=1.234,
            win_rate=0.5,
            profit_loss_ratio=2.0,
            profit_x_win=1.0,
            pass_=True,
            reason='通过'
        )
        
        d = fold.to_dict()
        
        self.assertEqual(d['fold'], 1)
        self.assertEqual(d['sharpe'], 1.234)
        self.assertEqual(d['win_rate'], 50.0)  # 转为百分比
        self.assertEqual(d['pass'], True)
    
    def test_wf4_result_to_dict(self):
        """验证WF4Result序列化"""
        result = WF4Result(
            etf_code='515050',
            data_range='2023-09-26 ~ 2026-06-02',
            n_folds=4,
            n_passed=2,
            pass_rate=0.5,
            avg_sharpe=0.8,
            avg_win_rate=0.45,
            avg_profit_loss_ratio=1.5,
            avg_profit_x_win=0.675,
            overall_pass=False,
            confidence='LOW',
            folds=[]
        )
        
        d = result.to_dict()
        
        self.assertEqual(d['etf_code'], '515050')
        self.assertEqual(d['pass_rate'], 50.0)  # 转为百分比
        self.assertEqual(d['overall_pass'], False)
        self.assertEqual(d['confidence'], 'LOW')


class TestConfidenceLevel(unittest.TestCase):
    """测试置信度计算"""
    
    def test_high_confidence(self):
        """验证4/4通过=高置信度"""
        result = WF4Result(
            etf_code='TEST',
            data_range='2023-09-26 ~ 2026-06-02',
            n_folds=4,
            n_passed=4,
            pass_rate=1.0,
            avg_sharpe=1.0,
            avg_win_rate=0.5,
            avg_profit_loss_ratio=2.0,
            avg_profit_x_win=1.0,
            overall_pass=True,
            confidence='HIGH',
            folds=[]
        )
        
        self.assertEqual(result.confidence, 'HIGH')
    
    def test_low_confidence(self):
        """验证2/4通过=低置信度"""
        result = WF4Result(
            etf_code='TEST',
            data_range='2023-09-26 ~ 2026-06-02',
            n_folds=4,
            n_passed=2,
            pass_rate=0.5,
            avg_sharpe=0.5,
            avg_win_rate=0.4,
            avg_profit_loss_ratio=1.2,
            avg_profit_x_win=0.48,
            overall_pass=False,
            confidence='LOW',
            folds=[]
        )
        
        self.assertEqual(result.confidence, 'LOW')


class TestPassCriteria(unittest.TestCase):
    """测试通过标准"""
    
    def setUp(self):
        self.wf4 = WalkForward4Fold()
    
    def test_min_sharpe_threshold(self):
        """验证Sharpe阈值"""
        self.assertEqual(self.wf4.MIN_SHARPE, 0.5)
    
    def test_min_win_rate_threshold(self):
        """验证胜率阈值"""
        self.assertEqual(self.wf4.MIN_WIN_RATE, 0.4)  # 40%
    
    def test_min_profit_x_win_threshold(self):
        """验证盈亏比×胜率阈值"""
        self.assertEqual(self.wf4.MIN_PROFIT_X_WIN, 1.0)


# ============================================================
# 运行测试
# ============================================================

if __name__ == '__main__':
    # 运行所有测试
    unittest.main(verbosity=2)