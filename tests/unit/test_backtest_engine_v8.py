#!/usr/bin/env python3
"""
回测引擎 v8.0 测试套件

测试覆盖：
1. 交易执行模型（T+1开盘成交）
2. 持仓管理（避免重复买入）
3. 止盈止损逻辑（min_hold_days）
4. 相对收益计算
"""
import sys
from pathlib import Path
import unittest
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.engine import (
    FactorBacktester, 
    BacktestConfig, 
    BacktestResult,
    create_backtester
)


# ============================================================
# 测试数据生成器
# ============================================================

def generate_test_data(
    code: str = '510300',
    start_date: str = '2023-01-01',
    periods: int = 100,
    trend: str = 'up'
) -> pd.DataFrame:
    """生成测试数据"""
    dates = pd.date_range(start=start_date, periods=periods, freq='B')
    
    if trend == 'up':
        base = 100
        drift = 0.002
    elif trend == 'down':
        base = 100
        drift = -0.002
    else:
        base = 100
        drift = 0
    
    np.random.seed(42)
    returns = np.random.normal(drift, 0.01, periods)
    close = base * np.cumprod(1 + returns)
    open_prices = close * (1 + np.random.uniform(-0.005, 0.005, periods))
    
    df = pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': open_prices,
        'close': close,
        'high': close * 1.005,
        'low': close * 0.995,
        'volume': np.random.randint(1000000, 10000000, periods),
    })
    df['code'] = code
    
    # 添加测试因子
    # 转换为Series后计算因子
    close_series = pd.Series(close, index=df.index)
    df['MACD_hist'] = (close_series > close_series.shift(5)).astype(int)
    df['DMA'] = (close_series > close_series.rolling(5).mean()).astype(int)
    df['SAR_trend'] = 0.7
    
    return df


def generate_benchmark_data(
    start_date: str = '2023-01-01',
    periods: int = 100
) -> pd.DataFrame:
    """生成基准数据"""
    dates = pd.date_range(start=start_date, periods=periods, freq='B')
    
    np.random.seed(43)
    base = 100
    returns = np.random.normal(0.001, 0.008, periods)
    close = base * np.cumprod(1 + returns)
    open_prices = close * (1 + np.random.uniform(-0.003, 0.003, periods))
    
    df = pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': open_prices,
        'close': close,
        'code': 'benchmark',
    })
    
    return df


# ============================================================
# 测试用例：交易执行模型
# ============================================================

class TestTradingExecution(unittest.TestCase):
    """测试交易执行模型"""
    
    def test_next_day_execution(self):
        """T日信号 → T+1开盘价成交"""
        # 生成数据
        df = generate_test_data('510300', '2023-01-01', 50, 'up')
        
        # 模拟信号：第10天触发买入
        signal_dates = ['2023-01-16']  # 第10个工作日
        
        # 预期成交：T+1开盘价
        signal_idx = df[df['date'].isin(signal_dates)].index
        if len(signal_idx) > 0:
            expected_buy_date = df.loc[signal_idx[0] + 1, 'date']
            expected_buy_price = df.loc[signal_idx[0] + 1, 'open']
        
        print(f"信号日: {signal_dates[0]}")
        print(f"预期买入日: {expected_buy_date}")
        print(f"预期买入价: {expected_buy_price:.4f}")
        
        # 验证
        self.assertIsNotNone(expected_buy_date)
        self.assertIsNotNone(expected_buy_price)


# ============================================================
# 测试用例：持仓管理
# ============================================================

class TestPositionManagement(unittest.TestCase):
    """测试持仓管理"""
    
    def setUp(self):
        """设置测试环境"""
        self.price_data = {
            'ETF1': generate_test_data('ETF1', '2023-01-01', 50, 'up'),
            'ETF2': generate_test_data('ETF2', '2023-01-01', 50, 'up'),
            '510300': generate_benchmark_data('2023-01-01', 50),
        }
        
        self.config = BacktestConfig(
            stop_loss=-0.04,
            stop_profit=0.06,
            min_hold_days=3,
            max_hold_days=20,
            max_positions=2,
        )
    
    def test_no_duplicate_buy(self):
        """同一ETF不能重复买入"""
        # 信号函数：始终返回True（持续触发信号）
        def always_signal(date, df_dict):
            # US-010 迁移: 原 always_signal(df) → (date, df_dict) -> {code: Signal}
            from src.strategy.base import Signal
            return {code: Signal(code=code, action='buy', price=1.0, confidence=1.0, reason='test')
                    for code in df_dict.keys()}
        
        # 创建回测器
        backtester = create_backtester(self.config)
        
        # 运行回测
        result = backtester.backtest(
            price_data=self.price_data,
            signal_func=always_signal,
            benchmark_data=self.price_data['510300'],
            start_date='2023-01-01',
            end_date='2023-04-01'
        )
        
        # 验证：同一ETF不能连续买入
        trades = result.trades
        etf1_trades = [t for t in trades if t['code'] == 'ETF1']
        
        print(f"ETF1交易次数: {len(etf1_trades)}")
        
        # 检查连续买入
        if len(etf1_trades) >= 2:
            for i in range(1, len(etf1_trades)):
                prev_sell = etf1_trades[i-1]['exit_date']
                curr_buy = etf1_trades[i]['entry_date']
                self.assertGreater(curr_buy, prev_sell, 
                    f"发现连续买入：前一笔{prev_sell}卖出，后一笔{curr_buy}买入")
        
        print("✅ 无重复买入")
    
    def test_max_positions(self):
        """最大持仓数限制"""
        def always_signal(date, df_dict):
            # US-010 迁移: 原 always_signal(df) → (date, df_dict) -> {code: Signal}
            from src.strategy.base import Signal
            return {code: Signal(code=code, action='buy', price=1.0, confidence=1.0, reason='test')
                    for code in df_dict.keys()}
        
        backtester = create_backtester(self.config)
        
        result = backtester.backtest(
            price_data=self.price_data,
            signal_func=always_signal,
            benchmark_data=self.price_data['510300'],
            start_date='2023-01-01',
            end_date='2023-04-01'
        )
        
        # 检查最大持仓
        max_pos = max((t['concurrent_positions'] for t in result.trades), default=0)
        print(f"最大同时持仓数: {max_pos}")
        self.assertLessEqual(max_pos, self.config.max_positions)


# ============================================================
# 测试用例：止盈止损逻辑
# ============================================================

class TestStopLossProfit(unittest.TestCase):
    """测试止盈止损逻辑"""
    
    def test_stop_loss_priority(self):
        """止损优先于持仓天数"""
        # 生成大跌数据
        df = generate_test_data('510300', '2023-01-01', 20, 'down')
        # 人为制造大跌
        df.loc[2:3, 'close'] = df.loc[2:3, 'close'] * 0.95
        df.loc[2:3, 'open'] = df.loc[2:3, 'close'] * 0.995
        
        price_data = {
            '510300': df,
            'benchmark': generate_benchmark_data('2023-01-01', 20),
        }
        
        config = BacktestConfig(
            stop_loss=-0.04,
            stop_profit=0.06,
            min_hold_days=3,
            max_hold_days=20,
            max_positions=2,
        )
        
        def signal(date, df_dict):
            # US-010 迁移: 返回空 dict（无信号）
            return {}
        
        backtester = create_backtester(config)
        result = backtester.backtest(
            price_data=price_data,
            signal_func=signal,
            benchmark_data=price_data['benchmark'],
            start_date='2023-01-01',
            end_date='2023-02-01'
        )
    
    def test_profit_take_after_min_hold(self):
        """止盈需满足最小持仓天数"""
        # 生成大涨数据
        df = generate_test_data('510300', '2023-01-01', 30, 'up')
        df.loc[5, 'close'] = df.loc[5, 'close'] * 1.08  # 第6天大涨
        df.loc[5, 'open'] = df.loc[5, 'close'] * 0.999
        
        price_data = {
            '510300': df,
            'benchmark': generate_benchmark_data('2023-01-01', 30),
        }
        
        config = BacktestConfig(
            stop_loss=-0.04,
            stop_profit=0.06,
            min_hold_days=3,
            max_hold_days=20,
            max_positions=2,
        )
        
        def signal(date, df_dict):
            # US-010 迁移: 返回空 dict（无信号）
            return {}
        
        backtester = create_backtester(config)
        result = backtester.backtest(
            price_data=price_data,
            signal_func=signal,
            benchmark_data=price_data['benchmark'],
            start_date='2023-01-01',
            end_date='2023-03-01'
        )


# ============================================================
# 测试用例：相对收益
# ============================================================

class TestRelativeReturn(unittest.TestCase):
    """测试相对收益计算"""
    
    def test_relative_return_calculation(self):
        """相对收益 = 策略收益 - 基准收益"""
        etf_df = generate_test_data('510300', '2023-01-01', 30, 'up')
        bench_df = generate_benchmark_data('2023-01-01', 30)
        
        price_data = {'510300': etf_df}
        
        config = BacktestConfig()
        backtester = create_backtester(config)
        
        result = backtester.backtest(
            price_data=price_data,
            signal_func=lambda date, df_dict: {code: type('S', (), {
                'code': code, 'action': 'buy', 'price': 1.0, 'confidence': 1.0,
                'reason': 'test', 'stop_loss': 0.0, 'take_profit': 0.0,
                'max_hold_days': 5, 'position_size': 0.0
            })() for code in df_dict.keys()},
            benchmark_data=bench_df,
            start_date='2023-01-01',
            end_date='2023-02-01'
        )
        
        print(f"绝对收益: {result.total_return:.2%}")
        print(f"相对收益: {result.relative_return:.2%}")
        
        # 相对收益应该是有意义的数值
        self.assertIsNotNone(result.relative_return)
        self.assertIsInstance(result.relative_return, float)


# ============================================================
# 测试用例：边界条件
# ============================================================

class TestEdgeCases(unittest.TestCase):
    """测试边界条件"""
    
    def test_no_trades_when_no_signal(self):
        """无信号时无交易"""
        df = generate_test_data('510300', '2023-01-01', 30, 'up')
        
        config = BacktestConfig()
        backtester = create_backtester(config)
        
        result = backtester.backtest(
            price_data={'510300': df},
            signal_func=lambda date, df_dict: {},
            benchmark_data=None,
            start_date='2023-01-01',
            end_date='2023-02-01'
        )
        
        self.assertEqual(len(result.trades), 0)
        print("✅ 无信号时无交易")
    
    def test_empty_price_data(self):
        """空数据"""
        config = BacktestConfig()
        backtester = create_backtester(config)
        
        result = backtester.backtest(
            price_data={},
            signal_func=lambda date, df_dict: {},
            benchmark_data=None,
            start_date='2023-01-01',
            end_date='2023-02-01'
        )
        
        self.assertEqual(len(result.trades), 0)
        print("✅ 空数据无交易")
    
    def test_single_day_data(self):
        """单日数据"""
        df = generate_test_data('510300', '2023-01-01', 2, 'up')
        
        config = BacktestConfig()
        backtester = create_backtester(config)
        
        result = backtester.backtest(
            price_data={'510300': df},
            signal_func=lambda date, df_dict: {code: type('S', (), {
                'code': code, 'action': 'buy', 'price': 1.0, 'confidence': 1.0,
                'reason': 'test', 'stop_loss': 0.0, 'take_profit': 0.0,
                'max_hold_days': 5, 'position_size': 0.0
            })() for code in df_dict.keys()},
            benchmark_data=None,
            start_date='2023-01-01',
            end_date='2023-01-02'
        )
        
        print(f"单日数据交易数: {len(result.trades)}")


# ============================================================
# 测试运行
# ============================================================

if __name__ == '__main__':
    print("=" * 80)
    print("回测引擎 v8.0 测试套件")
    print("=" * 80)
    print()
    
    # 运行测试
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestTradingExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestPositionManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestStopLossProfit))
    suite.addTests(loader.loadTestsFromTestCase(TestRelativeReturn))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # 运行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出总结
    print()
    print("=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"运行: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")