#!/usr/bin/env python3
"""
评分入口统一 - 单元测试
运行: python tests/test_selector_evaluate.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import pandas as pd
import numpy as np
from src.selector import Selector
from src.indicator import Indicator


def create_sample_etf_data(days=180):
    """生成测试用ETF数据"""
    dates = pd.date_range('2024-01-01', periods=days, freq='D')
    np.random.seed(42)
    
    # 构造上涨趋势数据
    close_prices = 1.0 + np.linspace(0, 0.3, days) + np.random.randn(days) * 0.02
    
    data = {
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': close_prices - 0.01,
        'high': close_prices + 0.02,
        'low': close_prices - 0.02,
        'close': close_prices,
        'volume': 1000000 + np.random.rand(days) * 500000,
    }
    df = pd.DataFrame(data)
    return df


class TestSelectorEvaluate(unittest.TestCase):
    """Selector.evaluate() 统一入口测试"""
    
    def setUp(self):
        """测试前准备"""
        self.df = create_sample_etf_data()
        self.df = Indicator.calculate(self.df)
        self.selector = Selector()
        self.latest_date = self.df['date'].iloc[-1]
    
    def test_evaluate_returns_tuple(self):
        """测试evaluate返回正确格式"""
        result = self.selector.evaluate(self.df, self.latest_date)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], int)
        self.assertIsInstance(result[1], list)
    
    def test_evaluate_same_as_score_with_ic(self):
        """测试evaluate与score_with_ic结果一致"""
        result_evaluate = self.selector.evaluate(self.df, self.latest_date)
        result_original = self.selector.score_with_ic(self.df, self.latest_date)
        self.assertEqual(result_evaluate, result_original)
    
    def test_evaluate_with_rsi_penalty(self):
        """测试RSI超买扣分 (>80)"""
        # 设置RSI为85（超买）
        self.df.loc[self.df['date'] == self.latest_date, 'rsi_14'] = 85.0
        
        score, reasons = self.selector.evaluate(self.df, self.latest_date)
        
        # 应该有严重超买警告
        self.assertIn('RSI⚠️⚠️', reasons)
        # 由于超买扣2分，分数应该降低
        print(f"RSI=85 时评分: {score}, 理由: {reasons}")
    
    def test_evaluate_with_rsi_warning(self):
        """测试RSI警告 (<80 但 >70)"""
        # 设置RSI为75（警告）
        self.df.loc[self.df['date'] == self.latest_date, 'rsi_14'] = 75.0
        
        score, reasons = self.selector.evaluate(self.df, self.latest_date)
        
        # 应该有警告但不扣分
        self.assertIn('RSI⚠️', reasons)
        # 不应该有严重警告
        self.assertNotIn('RSI⚠️⚠️', reasons)
        print(f"RSI=75 时评分: {score}, 理由: {reasons}")
    
    def test_evaluate_with_rsi_normal(self):
        """测试RSI正常加分 (<70)"""
        # 设置RSI为50（正常）
        self.df.loc[self.df['date'] == self.latest_date, 'rsi_14'] = 50.0
        
        score, reasons = self.selector.evaluate(self.df, self.latest_date)
        
        # 应该有RSI加分标记
        self.assertIn('RSI', reasons)
        # 不应该有警告
        self.assertNotIn('⚠️', reasons)
        print(f"RSI=50 时评分: {score}, 理由: {reasons}")


class TestSelectorEvaluateLegacy(unittest.TestCase):
    """Selector.evaluate_legacy() 旧版评分测试"""
    
    def setUp(self):
        """测试前准备"""
        self.df = create_sample_etf_data()
        self.df = Indicator.calculate(self.df)
        self.selector = Selector()
        self.latest_date = self.df['date'].iloc[-1]
    
    def test_legacy_no_rsi_penalty(self):
        """测试旧版评分无RSI扣分"""
        self.df.loc[self.df['date'] == self.latest_date, 'rsi_14'] = 85.0
        
        score, reasons = self.selector.evaluate_legacy(self.df, self.latest_date)
        
        # 旧版评分不应该有RSI相关标记
        self.assertNotIn('RSI', reasons)
    
    def test_legacy_always_passes_rsi(self):
        """测试旧版评分RSI条件更宽松"""
        # 设置RSI为85
        self.df.loc[self.df['date'] == self.latest_date, 'rsi_14'] = 85.0
        
        score_new = self.selector.evaluate(self.df, self.latest_date)[0]
        score_old = self.selector.evaluate_legacy(self.df, self.latest_date)[0]
        
        # 新版（RSI>80扣分）应该比旧版低
        self.assertLess(score_new, score_old,
                       f"新评分({score_new})应该小于旧版({score_old})")
        print(f"新旧评分对比: 新={score_new}, 旧={score_old}")


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
        
        # 测试多个日期
        for date in df['date'].iloc[-5:]:
            score, reasons = selector.evaluate(df, date)
            self.assertIsInstance(score, int)
            self.assertGreaterEqual(score, 0)
            self.assertIsInstance(reasons, list)
        
        print(f"完整评分流程测试通过: 测试了5个日期")


if __name__ == '__main__':
    print("=" * 60)
    print("评分入口统一 - 单元测试")
    print("=" * 60)
    unittest.main(verbosity=2)