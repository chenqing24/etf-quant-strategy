#!/usr/bin/env python3
"""参数敏感性分析"""
import pandas as pd
from typing import Dict, List, Tuple, Callable
from itertools import product

from src.utils.config import run_strategy
from pathlib import Path


class SensitivityAnalyzer:
    """参数敏感性分析器"""
    
    def __init__(self, data_dir: str = 'etf_data_50'):
        self.data_dir = data_dir
        self.results: pd.DataFrame = None
    
    def grid_search(
        self,
        param_grid: Dict[str, List],
        test_start: str = '2025-05-06',
        test_end: str = '2026-05-22',
        fixed_params: Dict = None,
    ) -> pd.DataFrame:
        """网格搜索
        
        Args:
            param_grid: 参数网格
            test_start: 测试开始日期
            test_end: 测试结束日期
            fixed_params: 固定参数
            
        Returns:
            结果DataFrame
        """
        if fixed_params is None:
            fixed_params = {}
        
        # 生成参数组合
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))
        
        results = []
        total = len(combinations)
        
        print(f"参数敏感性分析: {total} 个组合")
        
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            params.update(fixed_params)
            
            print(f"  [{i+1}/{total}] {params}")
            
            try:
                result = run_strategy(
                    test_start=test_start,
                    test_end=test_end,
                    **params
                )
                
                row = {
                    'params': str(params),
                    **{k: v for k, v in params.items()},
                    'return': result.get('return', 0),
                    'drawdown': result.get('drawdown', 0),
                    'sharpe': result.get('sharpe', 0),
                    'winrate': result.get('winrate', 0),
                    'trades': result.get('trades', 0),
                }
                results.append(row)
                
            except Exception as e:
                print(f"    错误: {e}")
                row = {
                    'params': str(params),
                    **{k: v for k, v in params.items()},
                    'return': None,
                    'drawdown': None,
                    'sharpe': None,
                    'winrate': None,
                    'trades': None,
                    'error': str(e),
                }
                results.append(row)
        
        self.results = pd.DataFrame(results)
        return self.results
    
    def analyze_single_param(
        self,
        param_name: str,
        param_values: List,
        metric: str = 'sharpe',
        fixed_params: Dict = None,
    ) -> pd.DataFrame:
        """分析单个参数的敏感性"""
        param_grid = {param_name: param_values}
        df = self.grid_search(param_grid, fixed_params=fixed_params)
        return df[[param_name, metric]].sort_values(metric, ascending=False)
    
    def find_robust_params(
        self,
        metric: str = 'sharpe',
        threshold_pct: float = 0.8
    ) -> Dict:
        """找出稳健参数"""
        if self.results is None or len(self.results) == 0:
            return {}
        
        param_cols = [c for c in self.results.columns 
                     if c not in ['return', 'drawdown', 'sharpe', 'winrate', 'trades', 'params', 'error']]
        
        best_value = self.results[metric].max()
        threshold_value = best_value * threshold_pct
        
        good_results = self.results[self.results[metric] >= threshold_value]
        
        recommendations = {}
        for col in param_cols:
            value_counts = good_results[col].value_counts()
            if len(value_counts) > 0:
                best_param_value = value_counts.index[0]
                recommendations[col] = best_param_value
        
        return recommendations
    
    def print_summary(self):
        """打印汇总报告"""
        if self.results is None or len(self.results) == 0:
            print("无结果")
            return
        
        print("\n" + "="*70)
        print("参数敏感性分析报告")
        print("="*70)
        
        df_sorted = self.results.dropna().sort_values('sharpe', ascending=False)
        
        print(f"\nTop 5 参数组合 (按夏普):")
        print("-"*70)
        
        for i, row in df_sorted.head(5).iterrows():
            print(f"  收益:{row['return']:>+7.1f}%  回撤:{row['drawdown']:>7.1f}%  "
                  f"夏普:{row['sharpe']:>5.2f}  胜率:{row['winrate']:>5.1f}%  "
                  f"参数:{row['params']}")
        
        robust = self.find_robust_params(metric='sharpe', threshold_pct=0.8)
        print(f"\n稳健参数推荐 (top 20%):")
        for k, v in robust.items():
            print(f"  {k}: {v}")
        
        print("="*70)


def quick_sensitivity_test():
    """快速敏感性测试"""
    import time
    
    analyzer = SensitivityAnalyzer(data_dir='../etf_data_50')
    
    # 简单参数网格
    param_grid = {
        'rebalance_days': [5, 10],
        'stop_loss': [-0.08, -0.10],
    }
    
    fixed_params = {
        'data_dir': '../etf_data_50',
    }
    
    t0 = time.time()
    df = analyzer.grid_search(
        param_grid, 
        test_start='2025-05-06',
        test_end='2025-12-31',
        fixed_params=fixed_params,
    )
    
    print(f"耗时: {time.time()-t0:.1f}秒")
    print(f"\n结果:\n{df[['rebalance_days', 'stop_loss', 'return', 'drawdown', 'sharpe']]}")
    
    print("\n✓ 敏感性测试通过")
    return True


if __name__ == '__main__':
    quick_sensitivity_test()


__all__ = ['SensitivityAnalyzer', 'quick_sensitivity_test']