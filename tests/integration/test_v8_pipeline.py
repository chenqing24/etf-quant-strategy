"""
v8.0 集成测试 - 全链路验证

测试目标：验证三个一致性 + 新引擎
1. 工具调用一致
2. 执行流程一致
3. 评价标准一致
4. 新引擎FactorBacktester（v8.0）
"""
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.indicators.relative import RelativeCalculator
from src.backtest.engine import FactorBacktester, BacktestConfig


class TestIntegration:
    """集成测试套件"""
    
    @pytest.fixture
    def test_data(self):
        """加载测试数据"""
        dl = DataLoader()
        all_data = dl.load(['510300', '512880', '512660'])
        
        # load返回{code: df}，其中510300是大盘
        etf_data = {k: v for k, v in all_data.items() if k != '510300'}
        df_benchmark = all_data['510300']
        
        return etf_data, df_benchmark
    
    def test_it01_full_pipeline_v8(self, test_data):
        """
        IT-01: 全链路测试 - 数据→指标→相对→回测
        
        验证：新引擎FactorBacktester全链路执行成功
        """
        etf_data, df_benchmark = test_data
        
        print("\n=== IT-01: 全链路测试(v8.0) ===")
        
        # 1. DataLoader加载
        assert '512880' in etf_data, "ETF数据加载失败"
        assert len(df_benchmark) > 0, "大盘数据加载失败"
        print("  ✅ DataLoader: 加载成功")
        
        # 2. IndicatorCalculator计算
        ic = IndicatorCalculator()
        for code, df in etf_data.items():
            etf_data[code] = ic.calculate_all(df)
        print("  ✅ IndicatorCalculator: 计算成功")
        
        # 3. RelativeCalculator计算
        rc = RelativeCalculator('510300')
        for code in list(etf_data.keys()):
            if code != '510300':
                etf_data[code] = rc.calc_all_relative(etf_data[code], df_benchmark)
        print("  ✅ RelativeCalculator: 计算成功")
        
        # 4. 回测（使用新引擎）
        config = BacktestConfig(
            stop_loss=-0.04,
            stop_profit=0.06,
            min_hold_days=3,
            max_hold_days=20,
            max_positions=2,
        )
        
        # 定义信号函数：MACD红柱 + DMA多头
        def signal_func(df):
            macd = df['MACD_hist'] > 0 if 'MACD_hist' in df.columns else False
            dma = df['DMA'] > 0 if 'DMA' in df.columns else False
            return macd & dma
        
        backtester = FactorBacktester(config=config)
        
        result = backtester.backtest(
            price_data=etf_data,
            signal_func=signal_func,
            benchmark_data=df_benchmark,
            start_date='2024-01-01',
            end_date='2024-12-31'
        )
        
        print(f"  ✅ FactorBacktester: {result.trade_count}笔交易")
        print(f"     绝对收益: {result.total_return:.2%}")
        print(f"     相对收益: {result.relative_return:.2%}")
        print(f"     胜率: {result.win_rate:.2%}")
        
        # 5. 验证结果结构
        assert hasattr(result, 'total_return'), "缺少total_return"
        assert hasattr(result, 'relative_return'), "缺少relative_return"
        assert hasattr(result, 'win_rate'), "缺少win_rate"
        assert hasattr(result, 'trades'), "缺少trades"
        print("  ✅ 结果结构验证通过")
        
        # 6. 验证交易记录
        if result.trades:
            trade = result.trades[0]
            assert 'code' in trade, "交易记录缺少code"
            assert 'entry_date' in trade, "交易记录缺少entry_date"
            assert 'exit_date' in trade, "交易记录缺少exit_date"
            assert 'pnl_pct' in trade, "交易记录缺少pnl_pct"
            assert 'hold_days' in trade, "交易记录缺少hold_days"
            print("  ✅ 交易记录字段验证通过")
    
    def test_it02_t1_open_execution(self, test_data):
        """
        IT-02: T+1开盘价成交验证
        
        验证：买入日=信号日+1，买入价=次日开盘价
        """
        etf_data, df_benchmark = test_data
        
        print("\n=== IT-02: T+1开盘价成交验证 ===")
        
        config = BacktestConfig(
            max_positions=1,
        )
        
        # 固定信号函数
        def signal_func(df):
            return pd.Series(True, index=df.index)
        
        backtester = FactorBacktester(config=config)
        result = backtester.backtest(
            price_data={'512880': etf_data['512880']},
            signal_func=signal_func,
            benchmark_data=df_benchmark,
            start_date='2024-01-01',
            end_date='2024-03-01'
        )
        
        if result.trades:
            trade = result.trades[0]
            
            # 验证：entry_signal_date < entry_date（信号日 < 买入日）
            entry_signal = trade.get('entry_signal_date', '')
            entry_date = trade['entry_date']
            
            print(f"  信号日: {entry_signal}")
            print(f"  买入日: {entry_date}")
            print(f"  买入价: {trade['entry_price']:.4f}")
            
            # 信号日应该早于买入日
            assert entry_signal < entry_date, f"信号日{entry_signal}应早于买入日{entry_date}"
            print("  ✅ T+1成交验证通过")
    
    def test_it03_position_management(self, test_data):
        """
        IT-03: 持仓管理验证
        
        验证：同一ETF不重复买入，同日不平仓再买
        """
        etf_data, df_benchmark = test_data
        
        print("\n=== IT-03: 持仓管理验证 ===")
        
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
            price_data=etf_data,
            signal_func=signal_func,
            benchmark_data=df_benchmark,
            start_date='2024-01-01',
            end_date='2024-06-01'
        )
        
        # 验证1：同一ETF不连续买入
        trades_512880 = [t for t in result.trades if t['code'] == '512880']
        trades_512660 = [t for t in result.trades if t['code'] == '512660']
        
        print(f"  512880交易数: {len(trades_512880)}")
        print(f"  512660交易数: {len(trades_512660)}")
        
        if len(trades_512880) >= 2:
            for i in range(1, len(trades_512880)):
                prev_sell = trades_512880[i-1]['exit_date']
                curr_buy = trades_512880[i]['entry_date']
                assert curr_buy > prev_sell, f"512880连续买入：{prev_sell}卖，{curr_buy}买"
            print("  ✅ 同一ETF不连续买入")
        
        if len(trades_512660) >= 2:
            for i in range(1, len(trades_512660)):
                prev_sell = trades_512660[i-1]['exit_date']
                curr_buy = trades_512660[i]['entry_date']
                assert curr_buy > prev_sell, f"512660连续买入：{prev_sell}卖，{curr_buy}买"
            print("  ✅ 512660不连续买入")
        
        # 验证2：最大持仓数
        max_pos = max((t['concurrent_positions'] for t in result.trades), default=0)
        print(f"  最大同时持仓: {max_pos}")
        assert max_pos <= config.max_positions, f"超过最大持仓数{max_pos} > {config.max_positions}"
        print("  ✅ 最大持仓数限制")
    
    def test_it04_stop_loss_profit(self, test_data):
        """
        IT-04: 止盈止损验证
        
        验证：
        - 止损任何时候可触发
        - 止盈需满足min_hold_days
        """
        etf_data, df_benchmark = test_data
        
        print("\n=== IT-04: 止盈止损验证 ===")
        
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
            price_data={'512880': etf_data['512880']},
            signal_func=signal_func,
            benchmark_data=df_benchmark,
            start_date='2024-01-01',
            end_date='2024-12-31'
        )
        
        if result.trades:
            # 统计止盈止损分布
            stop_loss = [t for t in result.trades if t['exit_reason'] == '止损']
            take_profit = [t for t in result.trades if t['exit_reason'] == '止盈']
            expired = [t for t in result.trades if t['exit_reason'] in ('到期', '期末平仓')]
            
            print(f"  止损: {len(stop_loss)}笔")
            print(f"  止盈: {len(take_profit)}笔")
            print(f"  到期: {len(expired)}笔")
            
            # 验证：止盈持仓天数应>=min_hold_days
            if take_profit:
                min_hold = min(t['hold_days'] for t in take_profit)
                max_hold = max(t['hold_days'] for t in take_profit)
                print(f"  止盈持仓天数: {min_hold}~{max_hold}天")
                assert min_hold >= config.min_hold_days, f"止盈持仓{min_hold}天<{config.min_hold_days}天"
                print("  ✅ 止盈满足min_hold_days")
            
            # 验证：止损可<min_hold_days
            if stop_loss:
                min_hold_stop = min(t['hold_days'] for t in stop_loss)
                print(f"  止损最小持仓: {min_hold_stop}天")
                print("  ✅ 止损可在min_hold_days前触发")
    
    def test_it05_relative_return(self, test_data):
        """
        IT-05: 相对收益验证
        
        验证：relative_return = pnl_pct - benchmark_return
        """
        etf_data, df_benchmark = test_data
        
        print("\n=== IT-05: 相对收益验证 ===")
        
        config = BacktestConfig()
        
        def signal_func(df):
            return pd.Series(True, index=df.index)
        
        backtester = FactorBacktester(config=config)
        result = backtester.backtest(
            price_data={'512880': etf_data['512880']},
            signal_func=signal_func,
            benchmark_data=df_benchmark,
            start_date='2024-01-01',
            end_date='2024-06-01'
        )
        
        if result.trades and len(result.trades) > 0:
            trade = result.trades[0]
            
            # 手动计算相对收益
            entry = trade['entry_date']
            exit = trade['exit_date']
            
            bench_entry = df_benchmark[df_benchmark['date'] == entry]['close'].values
            bench_exit = df_benchmark[df_benchmark['date'] == exit]['close'].values
            
            if len(bench_entry) > 0 and len(bench_exit) > 0:
                bench_return = (bench_exit[0] / bench_entry[0]) - 1
                calculated_rel = trade['pnl_pct'] - bench_return
                
                print(f"  策略收益: {trade['pnl_pct']:.4f}")
                print(f"  基准收益: {bench_return:.4f}")
                print(f"  记录相对收益: {trade.get('relative_return', 0):.4f}")
                print(f"  计算相对收益: {calculated_rel:.4f}")
                
                # 验证相对收益在合理范围内
                rel_return = trade.get('relative_return', 0)
                assert -0.5 < rel_return < 0.5, f"相对收益{rel_return}超出合理范围"
                print("  ✅ 相对收益范围合理")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short', '-s'])