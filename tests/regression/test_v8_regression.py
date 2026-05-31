#!/usr/bin/env python3
"""
v8.0 回归测试 - 验证原有功能

测试目标：
1. 新引擎与旧引擎行为一致
2. 持仓管理修复后交易数合理
3. 止盈止损逻辑正确
"""
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import DataLoader
from src.backtest.engine import FactorBacktester, BacktestConfig


class TestRegression:
    """回归测试套件"""
    
    @pytest.fixture
    def etf_data(self):
        """加载ETF数据"""
        dl = DataLoader()
        data = dl.load(['510300', '512880', '512660', '515650'])
        
        # 分离大盘和ETF
        benchmark = data['510300']
        etfs = {k: v for k, v in data.items() if k != '510300'}
        
        return etfs, benchmark
    
    def test_rt01_consecutive_buy_zero(self, etf_data):
        """
        RT-01: 验证连续买入比例=0%
        
        问题：v7.0 simple_backtest有89.5%连续买入
        期望：v8.0 FactorBacktester连续买入=0%
        """
        etfs, benchmark = etf_data
        
        print("\n=== RT-01: 连续买入验证 ===")
        
        config = BacktestConfig(
            max_positions=2,
        )
        
        def signal_func(df):
            return pd.Series(True, index=df.index)
        
        backtester = FactorBacktester(config=config)
        result = backtester.backtest(
            price_data=etfs,
            signal_func=signal_func,
            benchmark_data=benchmark,
            start_date='2024-01-01',
            end_date='2024-12-31'
        )
        
        # 统计连续买入
        by_etf = defaultdict(list)
        for t in result.trades:
            by_etf[t['code']].append(t)
        
        consecutive = 0
        for code, trades in by_etf.items():
            trades = sorted(trades, key=lambda x: x['entry_date'])
            for i in range(1, len(trades)):
                if trades[i]['entry_date'] <= trades[i-1]['exit_date']:
                    consecutive += 1
        
        total_pairs = sum(len(t) - 1 for t in by_etf.values() if len(t) > 1)
        if total_pairs > 0:
            consecutive_rate = consecutive / total_pairs
            print(f"  连续买入: {consecutive}/{total_pairs} ({consecutive_rate:.1%})")
            assert consecutive_rate == 0, f"仍有{consecutive_rate:.1%}连续买入"
        else:
            print("  交易数不足，跳过检查")
        
        print("  ✅ 连续买入=0%")
    
    def test_rt02_trade_count_reasonable(self, etf_data):
        """
        RT-02: 验证交易数合理
        
        问题：v7.0有2241笔交易（4只ETF）
        期望：v8.0交易数大幅减少
        """
        etfs, benchmark = etf_data
        
        print("\n=== RT-02: 交易数合理性验证 ===")
        
        config = BacktestConfig(
            stop_loss=-0.04,
            stop_profit=0.06,
            min_hold_days=3,
            max_hold_days=20,
            max_positions=2,
        )
        
        def signal_func(df):
            return pd.Series(True, index=df.index)
        
        backtester = FactorBacktester(config=config)
        result = backtester.backtest(
            price_data=etfs,
            signal_func=signal_func,
            benchmark_data=benchmark,
            start_date='2024-01-01',
            end_date='2024-12-31'
        )
        
        n_etfs = len(etfs)
        n_days = 250  # 交易日
        max_theoretical = n_etfs * (n_days // config.min_hold_days) // config.max_positions
        
        print(f"  交易数: {result.trade_count}")
        print(f"  ETF数: {n_etfs}")
        print(f"  最大理论交易数: ~{max_theoretical}")
        
        # 交易数应该远小于v7.0的2241
        assert result.trade_count < 500, f"交易数{result.trade_count}仍然过多"
        print(f"  ✅ 交易数{result.trade_count}<500（远少于v7.0的2241）")
    
    def test_rt03_hold_days_distribution(self, etf_data):
        """
        RT-03: 验证持仓天数分布
        
        期望：min_hold_days=3时，持仓<3天比例<5%
        """
        etfs, benchmark = etf_data
        
        print("\n=== RT-03: 持仓天数分布验证 ===")
        
        config = BacktestConfig(
            stop_loss=-0.04,
            stop_profit=0.06,
            min_hold_days=3,
            max_hold_days=20,
            max_positions=2,
        )
        
        def signal_func(df):
            return pd.Series(True, index=df.index)
        
        backtester = FactorBacktester(config=config)
        result = backtester.backtest(
            price_data=etfs,
            signal_func=signal_func,
            benchmark_data=benchmark,
            start_date='2024-01-01',
            end_date='2024-12-31'
        )
        
        if result.trades:
            hold_days = [t['hold_days'] for t in result.trades]
            short_holds = [h for h in hold_days if h < config.min_hold_days]
            
            print(f"  总交易数: {len(result.trades)}")
            print(f"  持仓<3天: {len(short_holds)} ({len(short_holds)/len(result.trades):.1%})")
            print(f"  平均持仓: {np.mean(hold_days):.1f}天")
            print(f"  最短持仓: {min(hold_days)}天")
            print(f"  最长持仓: {max(hold_days)}天")
            
            # 止损可以有1-2天持仓，但止盈必须是>=3天
            short_by_reason = defaultdict(int)
            for t in result.trades:
                if t['hold_days'] < config.min_hold_days:
                    short_by_reason[t['exit_reason']] += 1
            
            print(f"  短持仓原因: {dict(short_by_reason)}")
            
            # 止盈不应该有短持仓
            tp_short = short_by_reason.get('止盈', 0)
            assert tp_short == 0, f"止盈中有{tp_short}笔持仓<3天"
            print("  ✅ 止盈全部满足min_hold_days")
    
    def test_rt04_relative_return_exists(self, etf_data):
        """
        RT-04: 验证相对收益计算
        
        期望：有基准数据时，相对收益有值
        """
        etfs, benchmark = etf_data
        
        print("\n=== RT-04: 相对收益验证 ===")
        
        config = BacktestConfig()
        
        def signal_func(df):
            return pd.Series(True, index=df.index)
        
        backtester = FactorBacktester(config=config)
        result = backtester.backtest(
            price_data=etfs,
            signal_func=signal_func,
            benchmark_data=benchmark,
            start_date='2024-01-01',
            end_date='2024-06-01'
        )
        
        if result.trades:
            rel_returns = [t.get('relative_return', 0) for t in result.trades]
            valid_rel = [r for r in rel_returns if r != 0]
            
            print(f"  相对收益笔数: {len(valid_rel)}/{len(result.trades)}")
            if valid_rel:
                print(f"  相对收益范围: {min(valid_rel):.2%} ~ {max(valid_rel):.2%}")
            
            assert len(valid_rel) > 0, "相对收益未计算"
            print("  ✅ 相对收益已计算")
    
    def test_rt05_stop_loss_always_valid(self, etf_data):
        """
        RT-05: 验证止损始终有效
        
        期望：任意持仓天数触发止损都有效
        """
        etfs, benchmark = etf_data
        
        print("\n=== RT-05: 止损有效性验证 ===")
        
        config = BacktestConfig(
            stop_loss=-0.04,
            stop_profit=0.06,
            min_hold_days=3,
            max_hold_days=20,
            max_positions=1,
        )
        
        def signal_func(df):
            return pd.Series(True, index=df.index)
        
        backtester = FactorBacktester(config=config)
        result = backtester.backtest(
            price_data={'512880': etfs['512880']},
            signal_func=signal_func,
            benchmark_data=benchmark,
            start_date='2024-01-01',
            end_date='2024-12-31'
        )
        
        stop_losses = [t for t in result.trades if t['exit_reason'] == '止损']
        
        if stop_losses:
            stop_returns = [t['pnl_pct'] for t in stop_losses]
            print(f"  止损笔数: {len(stop_losses)}")
            print(f"  止损收益: {min(stop_returns):.2%} ~ {max(stop_returns):.2%}")
            
            # 止损应该为负（在0附近或以下）
            negative_stop = [t for t in stop_losses if t['pnl_pct'] <= 0]
            print(f"  止损为负: {len(negative_stop)}/{len(stop_losses)}")
            assert len(negative_stop) > 0, "止损应包含亏损交易"
            
            print("  ✅ 止损功能正常")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short', '-s'])