#!/usr/bin/env python3
"""评分入口统一测试 - 使用unittest"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import pandas as pd
import numpy as np
from src.selector import Selector
from src.indicator import Indicator


def create_sample_etf_data():
    """生成测试用ETF数据"""
    dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    np.random.seed(42)
    
    data = {
        'date': dates,
        'open': 1.0 + np.random.randn(len(dates)) * 0.02,
        'high': 1.05 + np.random.randn(len(dates)) * 0.02,
        'low': 0.95 + np.random.randn(len(dates)) * 0.02,
        'close': 1.0 + np.cumsum(np.random.randn(len(dates)) * 0.01),
        'volume': 1000000 + np.random.randn(len(dates)) * 100000,
    }
    df = pd.DataFrame(data)
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    return df


class TestSelectorEvaluate(unittest.TestCase):
    """Selector.evaluate() 统一入口测试"""
    
    def test_evaluate_returns_tuple(self):
        """测试evaluate返回正确格式"""
        df = create_sample_etf_data()
        df = Indicator.calculate(df)
        selector = Selector()
        latest_date = df['date'].iloc[-1]
        
        result = selector.evaluate(df, latest_date)
        
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], int)
        self.assertIsInstance(result[1], list)
    
    def test_evaluate_same_as_score_with_ic(self):
        """测试evaluate与score_with_ic结果一致"""
        df = create_sample_etf_data()
        df = Indicator.calculate(df)
        selector = Selector()
        latest_date = df['date'].iloc[-1]
        
        result_evaluate = selector.evaluate(df, latest_date)
        result_original = selector.score_with_ic(df, latest_date)
        
        self.assertEqual(result_evaluate, result_original)
    
    def test_evaluate_with_rsi_penalty(self):
        """测试RSI超买扣分"""
        df = create_sample_etf_data()
        df = Indicator.calculate(df)
        selector = Selector()
        
        latest_date = df['date'].iloc[-1]
        df.loc[df['date'] == latest_date, 'rsi_14'] = 85.0
        
        score, reasons = selector.evaluate(df, latest_date)
        
        self.assertIn('RSI⚠️⚠️', reasons)
    
    def test_evaluate_with_rsi_normal(self):
        """测试RSI正常加分"""
        df = create_sample_etf_data()
        df = Indicator.calculate(df)
        selector = Selector()
        
        latest_date = df['date'].iloc[-1]
        df.loc[df['date'] == latest_date, 'rsi_14'] = 50.0
        
        score, reasons = selector.evaluate(df, latest_date)
        
        self.assertIn('RSI', reasons)


class TestSelectorEvaluateLegacy(unittest.TestCase):
    """Selector.evaluate_legacy() 旧版评分测试"""
    
    def test_legacy_no_rsi_penalty(self):
        """测试旧版评分无RSI扣分"""
        df = create_sample_etf_data()
        df = Indicator.calculate(df)
        selector = Selector()
        
        latest_date = df['date'].iloc[-1]
        df.loc[df['date'] == latest_date, 'rsi_14'] = 85.0
        
        score, reasons = selector.evaluate_legacy(df, latest_date)
        
        self.assertNotIn('RSI', reasons)
    
    def test_legacy_different_from_new(self):
        """测试新旧版评分差异"""
        df = create_sample_etf_data()
        df = Indicator.calculate(df)
        selector = Selector()
        
        latest_date = df['date'].iloc[-1]
        df.loc[df['date'] == latest_date, 'rsi_14'] = 85.0
        
        score_new = selector.evaluate(df, latest_date)[0]
        score_old = selector.evaluate_legacy(df, latest_date)[0]
        
        self.assertLess(score_new, score_old)


class TestCallSites(unittest.TestCase):
    """验证所有调用点已更新"""
    
    def test_backtest_uses_evaluate(self):
        """测试backtest.py使用evaluate"""
        with open('src/backtest.py', 'r') as f:
            content = f.read()
        
        self.assertIn('selector.evaluate', content)
        self.assertNotIn('selector.score(df,', content)
        self.assertNotIn('selector.score_with_ic(df,', content)
    
    def test_report_generator_uses_evaluate(self):
        """测试report_generator.py使用evaluate"""
        with open('src/report_generator.py', 'r') as f:
            content = f.read()
        
        self.assertIn('selector.evaluate', content)
        self.assertNotIn('selector.score(df,', content)
    
    def test_etf_pool_updater_uses_evaluate(self):
        """测试etf_pool_updater.py使用evaluate"""
        with open('src/etf_pool_updater.py', 'r') as f:
            content = f.read()
        
        self.assertIn('selector.evaluate', content)
        self.assertNotIn('selector.score(df,', content)
    
    def test_trade_uses_evaluate(self):
        """测试trade.py使用evaluate"""
        with open('src/trade.py', 'r') as f:
            content = f.read()
        
        self.assertIn('selector.evaluate', content)
        self.assertNotIn('self.selector.score(df,', content)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_evaluation_flow(self):
        """测试完整评分流程"""
        df = create_sample_etf_data()
        df = Indicator.calculate(df)
        selector = Selector()
        
        for date in df['date'].iloc[-5:]:
            score, reasons = selector.evaluate(df, date)
            self.assertIsInstance(score, int)
            self.assertGreaterEqual(score, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)