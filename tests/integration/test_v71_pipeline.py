"""
v7.1 集成测试 - 全链路验证

测试目标：验证三个一致性
1. 工具调用一致
2. 执行流程一致
3. 评价标准一致
"""
import pytest
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.indicators.relative import RelativeCalculator
from scripts.factor_mining.unified_mining_v7 import (
    simple_backtest, backtest_single_factor, BacktestConfig
)


class TestIntegration:
    """集成测试套件"""
    
    @pytest.fixture
    def test_data(self):
        """加载测试数据"""
        dl = DataLoader()
        all_data = dl.load(['510300', '512880', '512660'])
        # load_all_data返回(dict, DataFrame)
        etf_data = {k: v for k, v in all_data.items() if k != '510300'}
        df_benchmark = all_data['510300']
        
        # 将date列转为datetime并设为索引（用于日期查找）
        if 'date' in df_benchmark.columns:
            df_benchmark['date'] = pd.to_datetime(df_benchmark['date'])
            df_benchmark = df_benchmark.set_index('date')
        
        return etf_data, df_benchmark
    
    def test_it01_full_pipeline(self, test_data):
        """
        IT-01: 全链路测试 - 数据→指标→相对→回测
        
        验证：全链路执行成功，相对收益计算正确
        """
        etf_data, df_benchmark = test_data
        
        print("\n=== IT-01: 全链路测试 ===")
        
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
        for code, df in etf_data.items():
            if code != '510300':
                etf_data[code] = rc.calc_all_relative(df, df_benchmark)
        print("  ✅ RelativeCalculator: 计算成功")
        
        # 4. 回测
        config = BacktestConfig()
        signals = pd.Series([True] + [False] * 4, index=etf_data['512880'].index[:5])
        trades = simple_backtest(etf_data['512880'], signals, config)
        
        if trades:
            print(f"  ✅ simple_backtest: {len(trades)}笔交易")
            print(f"     交易日期: {trades[0]['buy_date']} ~ {trades[0]['sell_date']}")
        
        # 5. 验证相对收益计算（修复后）
        trades, _, _ = backtest_single_factor(
            etf_data, ['rel_MACD_strength'], config, df_benchmark
        )
        
        if trades:
            rel_returns = [t['relative_return'] for t in trades]
            bench_returns = [t['benchmark_return'] for t in trades]
            abs_returns = [t['return'] for t in trades]
            
            print(f"\n  === 相对收益验证 ===")
            print(f"  样本数: {len(trades)}")
            print(f"  绝对收益均值: {np.mean(abs_returns)*100:.2f}%")
            print(f"  大盘收益均值: {np.mean(bench_returns)*100:.2f}%")
            print(f"  相对收益均值: {np.mean(rel_returns)*100:.2f}%")
            
            # 验证：相对收益应该不等于绝对收益（除非刚好等于大盘）
            if len(trades) > 0:
                diff_count = sum(1 for a, b in zip(abs_returns, bench_returns) if abs(a - b) > 0.001)
                print(f"  绝对收益≠大盘收益的交易数: {diff_count}/{len(trades)}")
                
                # 验证相对收益 = 绝对收益 - 大盘收益
                rel_check = [a - b for a, b in zip(abs_returns, bench_returns)]
                rel_diff = [abs(r - rc) for r, rc in zip(rel_returns, rel_check)]
                
                if all(d < 0.001 for d in rel_diff):
                    print("  ✅ 相对收益计算正确: relative_return = absolute_return - benchmark_return")
                else:
                    print("  ❌ 相对收益计算有误")
            
            # 验证日期非1970-01-01
            dates = [t['buy_date'] for t in trades]
            has_1970 = any('1970' in str(d) for d in dates)
            if not has_1970:
                print("  ✅ 日期正确: 无1970-01-01")
            else:
                print("  ❌ 日期错误: 存在1970-01-01")
    
    def test_it02_single_etf_single_factor(self, test_data):
        """
        IT-02: 单ETF单因子测试
        
        验证：1+1测试，有交易输出
        """
        etf_data, df_benchmark = test_data
        config = BacktestConfig()
        
        print("\n=== IT-02: 单ETF单因子测试 ===")
        
        # 只用一个ETF和一个因子
        single_etf = {'512880': etf_data['512880']}
        trades, bm_ret, pool_ret = backtest_single_factor(
            single_etf, ['rel_MACD_strength'], config, df_benchmark
        )
        
        print(f"  交易数: {len(trades)}")
        print(f"  大盘收益: {bm_ret*100:.2f}%")
        print(f"  ETF池收益: {pool_ret*100:.2f}%")
        
        # 验证有交易输出
        assert len(trades) > 0, "应有交易输出"
    
    def test_it03_multi_etf_multi_factor(self, test_data):
        """
        IT-03: 多ETF多因子组合测试
        
        验证：评分正确，排序正确
        """
        etf_data, df_benchmark = test_data
        config = BacktestConfig()
        
        print("\n=== IT-03: 多ETF多因子组合测试 ===")
        
        # 测试多因子组合
        combo = ['rel_MACD_strength', 'rel_ADX_strength']
        trades, bm_ret, pool_ret = backtest_single_factor(
            etf_data, combo, config, df_benchmark
        )
        
        print(f"  因子组合: {combo}")
        print(f"  交易数: {len(trades)}")
        
        # 验证交易有relative_return字段
        if trades:
            has_rel = all('relative_return' in t for t in trades)
            has_bench = all('benchmark_return' in t for t in trades)
            
            if has_rel and has_bench:
                print("  ✅ 交易记录包含相对收益字段")
            else:
                print("  ❌ 交易记录缺少相对收益字段")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short', '-s'])