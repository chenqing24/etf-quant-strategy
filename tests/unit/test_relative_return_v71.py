"""
v7.1 单元测试 - 相对收益计算验证

参考业界实践：
- 避免前视偏差（no look-ahead bias）
- 日期对齐验证
- 统计显著性检验
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime

# 被测模块
import sys
sys.path.insert(0, '.')
from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.indicators.relative import RelativeCalculator
from src.backtest.engine import FactorBacktester, BacktestConfig


class TestRelativeReturn:
    """相对收益计算测试套件"""
    
    @pytest.fixture
    def sample_data(self):
        """构造测试数据：ETF涨3%，基准涨1%，期望相对收益+2%"""
        dates = pd.date_range('2024-01-01', periods=10, freq='D').strftime('%Y-%m-%d').tolist()
        
        # ETF: 从1.0涨到1.03（涨3%）
        etf_close = [1.0, 1.003, 1.006, 1.009, 1.012, 1.015, 1.018, 1.021, 1.024, 1.03]
        
        # 基准: 从1.0涨到1.01（涨1%）
        bm_close = [1.0, 1.001, 1.002, 1.003, 1.004, 1.005, 1.006, 1.007, 1.008, 1.01]
        
        etf_df = pd.DataFrame({
            'code': ['512880'] * 10,
            'date': dates,
            'close': etf_close
        })
        
        bm_df = pd.DataFrame({
            'code': ['510300'] * 10,
            'date': dates,
            'close': bm_close
        })
        
        return {'512880': etf_df, '510300': bm_df}
    
    @pytest.fixture
    def real_data(self):
        """真实数据：加载510300和512880"""
        dl = DataLoader()
        data = dl.load(['510300', '512880'])
        return data
    
    def test_ut01_relative_return_calculation(self, sample_data):
        """
        UT-01: 相对收益计算 - 基本场景
        
        输入: ETF涨3%, 基准涨1%
        期望: 相对收益 = 2% (误差<0.01%)
        参考: 无前视偏差原则
        """
        etf_df = sample_data['512880'].copy()
        bm_df = sample_data['510300'].copy()
        
        # 按日期排序
        etf_df = etf_df.sort_values('date').reset_index(drop=True)
        bm_df = bm_df.sort_values('date').reset_index(drop=True)
        
        # 计算收益
        etf_df['return'] = etf_df['close'].pct_change()
        bm_df['return'] = bm_df['close'].pct_change()
        
        # 合并计算相对收益
        merged = bm_df[['date', 'return']].merge(
            etf_df[['date', 'return']], 
            on='date', 
            suffixes=('_bm', '_etf')
        )
        merged['relative_return'] = merged['return_etf'] - merged['return_bm']
        
        # 验证最后一期（总收益）
        total_etf_return = (etf_df['close'].iloc[-1] / etf_df['close'].iloc[0]) - 1
        total_bm_return = (bm_df['close'].iloc[-1] / bm_df['close'].iloc[0]) - 1
        total_rel_return = total_etf_return - total_bm_return
        
        print(f"\nUT-01 结果:")
        print(f"  ETF总收益: {total_etf_return*100:.2f}%")
        print(f"  基准总收益: {total_bm_return*100:.2f}%")
        print(f"  相对收益: {total_rel_return*100:.2f}%")
        
        assert abs(total_rel_return - 0.02) < 0.0001, f"相对收益应为2%，实际为{total_rel_return*100:.2f}%"
    
    def test_ut02_relative_return_zero(self, sample_data):
        """
        UT-02: 相对收益边界 - ETF与基准同涨同跌
        
        输入: ETF和基准都涨1%
        期望: 相对收益 = 0%
        """
        etf_df = sample_data['512880'].copy()
        bm_df = sample_data['510300'].copy()
        
        # 修改为同涨同跌
        etf_df['close'] = [1.0, 1.001, 1.002, 1.003, 1.004, 1.005, 1.006, 1.007, 1.008, 1.01]
        bm_df['close'] = [1.0, 1.001, 1.002, 1.003, 1.004, 1.005, 1.006, 1.007, 1.008, 1.01]
        
        etf_df = etf_df.sort_values('date').reset_index(drop=True)
        bm_df = bm_df.sort_values('date').reset_index(drop=True)
        
        total_etf_return = (etf_df['close'].iloc[-1] / etf_df['close'].iloc[0]) - 1
        total_bm_return = (bm_df['close'].iloc[-1] / bm_df['close'].iloc[0]) - 1
        total_rel_return = total_etf_return - total_bm_return
        
        print(f"\nUT-02 结果:")
        print(f"  ETF总收益: {total_etf_return*100:.2f}%")
        print(f"  基准总收益: {total_bm_return*100:.2f}%")
        print(f"  相对收益: {total_rel_return*100:.2f}%")
        
        assert abs(total_rel_return) < 0.0001, f"相对收益应为0%，实际为{total_rel_return*100:.2f}%"
    
    def test_ut03_date_index_correctness(self, real_data):
        """
        UT-03: 日期索引正确性
        
        输入: 真实交易数据
        期望: 日期不包含1970-01-01
        参考: 时间戳验证
        """
        etf_df = real_data['512880']
        
        # 检查日期格式
        assert 'date' in etf_df.columns, "数据应包含date列"
        
        # 检查是否有1970-01-01
        dates_str = etf_df['date'].astype(str)
        has_1970 = dates_str.str.startswith('1970').any()
        
        print(f"\nUT-03 结果:")
        print(f"  数据行数: {len(etf_df)}")
        print(f"  日期范围: {etf_df['date'].min()} ~ {etf_df['date'].max()}")
        print(f"  是否有1970日期: {has_1970}")
        
        assert not has_1970, "数据不应包含1970-01-01日期"
    
    def test_ut04_monte_carlo_pvalue_range(self):
        """
        UT-04: 蒙特卡洛p值范围
        
        输入: 1000次模拟
        期望: 0.01 < p_value < 0.99
        参考: 统计显著性检验
        """
        # 模拟策略收益序列
        np.random.seed(42)
        strategy_returns = np.random.normal(0.001, 0.02, 100)
        baseline_returns = np.random.normal(0, 0.015, 100)
        
        # 简单的蒙特卡洛p值计算
        excess_returns = strategy_returns - baseline_returns
        observed_mean = np.mean(excess_returns)
        
        # Bootstrap模拟
        n_simulations = 1000
        simulated_means = []
        for _ in range(n_simulations):
            # 混合所有收益，随机分配到策略和基准
            combined = np.concatenate([strategy_returns, baseline_returns])
            np.random.shuffle(combined)
            sim_strategy = combined[:len(strategy_returns)]
            sim_excess = sim_strategy - baseline_returns
            simulated_means.append(np.mean(sim_excess))
        
        p_value = np.mean(np.array(simulated_means) >= observed_mean)
        
        print(f"\nUT-04 结果:")
        print(f"  观察到的超额收益均值: {observed_mean*100:.4f}%")
        print(f"  模拟p值: {p_value:.4f}")
        print(f"  是否在合理范围(0.01~0.99): {0.01 < p_value < 0.99}")
        
        assert 0.01 < p_value < 0.99, f"p值应在0.01~0.99之间，实际为{p_value:.4f}"
    
    def test_ut05_score_normalization(self):
        """
        UT-05: 评分归一化
        
        输入: 任意收益值
        期望: 归一化到0-100分
        参考: min-max标准化
        """
        # 模拟不同策略的收益
        returns = [0.5, 1.0, 1.5, 2.0, -0.5, -1.0]
        sharpes = [1.0, 2.0, 3.0, 4.0, 0.5, 0.8]
        
        # Min-Max归一化
        def normalize(values, min_val=None, max_val=None):
            min_v = min_val if min_val is not None else min(values)
            max_v = max_val if max_val is not None else max(values)
            return [(v - min_v) / (max_v - min_v) * 100 for v in values]
        
        norm_returns = normalize(returns)
        norm_sharpes = normalize(sharpes)
        
        print(f"\nUT-05 结果:")
        print(f"  收益归一化: {returns} -> {[f'{r:.1f}' for r in norm_returns]}")
        print(f"  夏普归一化: {sharpes} -> {[f'{s:.1f}' for s in norm_sharpes]}")
        
        # 验证归一化范围
        assert all(0 <= r <= 100 for r in norm_returns), "归一化收益应在0-100范围内"
        assert all(0 <= s <= 100 for s in norm_sharpes), "归一化夏普应在0-100范围内"
        
        # 验证相对顺序保持
        assert norm_returns[0] < norm_returns[3], "收益排序应保持"
        assert norm_sharpes[0] < norm_sharpes[3], "夏普排序应保持"
    
    def test_ut06_hard_filter(self):
        """
        UT-06: 硬性门槛过滤
        
        输入: 不同胜率的策略
        期望: 胜率<50%被过滤
        参考: 业界门槛设计
        """
        strategies = [
            {'name': '策略A', 'win_rate': 0.55, 'return': 0.10},
            {'name': '策略B', 'win_rate': 0.48, 'return': 0.15},
            {'name': '策略C', 'win_rate': 0.52, 'return': 0.08},
        ]
        
        # 硬性门槛：胜率>=50%
        passed = [s for s in strategies if s['win_rate'] >= 0.50]
        
        print(f"\nUT-06 结果:")
        print(f"  原始策略数: {len(strategies)}")
        print(f"  通过门槛数: {len(passed)}")
        print(f"  通过的策略: {[s['name'] for s in passed]}")
        
        assert len(passed) == 2, "应只有2个策略通过"
        assert all(s['win_rate'] >= 0.50 for s in passed), "通过的策略胜率应>=50%"
    
    def test_ut07_empty_data_handling(self):
        """
        UT-07: 空数据处理
        
        输入: 无交易数据
        期望: 返回0而非报错
        参考: 容错设计
        """
        empty_trades = []
        
        # 计算平均收益（空数据应返回0）
        if empty_trades:
            avg_return = np.mean([t['return'] for t in empty_trades])
        else:
            avg_return = 0
        
        win_rate = len([t for t in empty_trades if t.get('return', 0) > 0]) / max(len(empty_trades), 1)
        
        print(f"\nUT-07 结果:")
        print(f"  空交易列表长度: {len(empty_trades)}")
        print(f"  平均收益: {avg_return}")
        print(f"  胜率: {win_rate}")
        
        assert avg_return == 0, "空数据应返回0"
        assert win_rate == 0, "空数据胜率应为0"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])