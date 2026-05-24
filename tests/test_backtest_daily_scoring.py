#!/usr/bin/env python3
"""回测引擎重构测试 - 每日评分版"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import pandas as pd
import numpy as np
from src.backtest import run_backtest
from src.config import StrategyConfig
from src.indicator import Indicator


def create_test_data(n_days=100, code='000001', start_price=1.0):
    """创建测试用ETF数据"""
    dates = pd.date_range('2024-01-01', periods=n_days, freq='D')
    np.random.seed(42)
    
    # 上涨趋势
    trend = np.linspace(0, 0.3, n_days)
    noise = np.random.randn(n_days) * 0.02
    
    data = {
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': start_price * (1 + trend + noise),
        'high': start_price * (1 + trend + noise + 0.01),
        'low': start_price * (1 + trend + noise - 0.01),
        'close': start_price * (1 + trend + noise),
        'volume': np.random.randint(1000000, 5000000, n_days),
    }
    df = pd.DataFrame(data)
    return {code: df}


class TestDailyScoringBacktest(unittest.TestCase):
    """每日评分回测测试"""
    
    def test_daily_scoring_triggers_sell(self):
        """测试评分下降时触发卖出"""
        # 创建测试数据
        data = create_test_data(100, '000001')
        data = Indicator.calculate_all(data)
        
        config = StrategyConfig(
            hold_count=1,
            weights=(1.0,),
            score_threshold=6,
            rebalance_days=30,
            stop_loss=-0.05,
            stop_gain=0.08,
        )
        
        result = run_backtest(
            data=data,
            config=config,
            test_start='2024-01-01',
            test_end='2024-04-10',
            market_filter=None,
        )
        
        # 应该有交易记录
        self.assertGreater(result['trades'], 0)
    
    def test_rebalance_cycle(self):
        """测试调仓周期"""
        data = create_test_data(200, '000001')
        data = Indicator.calculate_all(data)
        
        config = StrategyConfig(
            hold_count=1,
            weights=(1.0,),
            score_threshold=6,
            rebalance_days=10,  # 10天调仓
        )
        
        result = run_backtest(
            data=data,
            config=config,
            test_start='2024-01-01',
            test_end='2024-06-30',
        )
        
        # 调仓周期内应该有足够交易
        self.assertGreaterEqual(result['trades'], 1)


class TestBacktestWithMultipleETF(unittest.TestCase):
    """多ETF回测"""
    
    def test_multiple_etf_selection(self):
        """测试多ETF选择"""
        data = {}
        for i, code in enumerate(['000001', '000002', '000003']):
            df = create_test_data(100, code, start_price=1.0 + i*0.1)
            data.update(df)
        
        data = Indicator.calculate_all(data)
        
        config = StrategyConfig(
            hold_count=2,
            weights=(0.6, 0.4),
            score_threshold=6,
        )
        
        result = run_backtest(
            data=data,
            config=config,
            test_start='2024-01-01',
            test_end='2024-04-10',
        )
        
        # 应该有交易记录(trades可能是int或list)
        trades = result.get('trades', 0)
        if isinstance(trades, int):
            self.assertGreaterEqual(trades, 1)
        else:
            buy_trades = [t for t in trades if t.get('action') == 'buy']
            self.assertGreaterEqual(len(buy_trades), 1)


class TestBacktestEdgeCases(unittest.TestCase):
    """边界情况测试"""
    
    def test_no_data(self):
        """测试无数据"""
        result = run_backtest(
            data={},
            config=StrategyConfig(),
            test_start='2024-01-01',
            test_end='2024-04-10',
        )
        
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['trades'], 0)
    
    def test_short_period(self):
        """测试短周期"""
        data = create_test_data(5)  # 只有5天数据
        data = Indicator.calculate_all(data)
        
        result = run_backtest(
            data=data,
            config=StrategyConfig(),
            test_start='2024-01-01',
            test_end='2024-01-10',
        )
        
        # 短期可能没有交易
        self.assertIn('return', result)


class TestCompareOldVsNew(unittest.TestCase):
    """新旧回测对比"""
    
    def test_old_logic_available(self):
        """测试旧版逻辑仍可用"""
        from src.selector import Selector
        
        selector = Selector()
        # 旧版评分
        self.assertTrue(hasattr(selector, 'evaluate_legacy'))
        
        # 验证旧版没有RSI扣分
        df = pd.DataFrame({
            'date': ['2024-01-01'],
            'close': [1.0],
            'ma20': [0.9],
            'ma60': [0.85],
            'ma120': [0.8],
            'vol_ratio': [2.0],
            'rsi_14': [85.0],  # 超买
        })
        
        score_old = selector.evaluate_legacy(df, '2024-01-01')[0]
        score_new = selector.evaluate(df, '2024-01-01')[0]
        
        # 新版分数应该更低(有RSI扣分)
        self.assertLess(score_new, score_old)


if __name__ == '__main__':
    unittest.main(verbosity=2)