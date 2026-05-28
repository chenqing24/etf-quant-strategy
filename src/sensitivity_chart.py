#!/usr/bin/env python3
"""敏感性图表可视化"""
import pandas as pd
from typing import Dict, List
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class SensitivityChart:
    """参数敏感性图表"""
    
    def __init__(self, output_dir: str = 'results'):
        self.output_dir = output_dir
    
    def plot_single_param(
        self,
        results: pd.DataFrame,
        param_name: str,
        metric: str = 'sharpe',
        save_path: str = None
    ):
        """绘制单参数敏感性图"""
        if param_name not in results.columns:
            print(f"警告: 参数 {param_name} 不在结果中")
            return
        
        # 排序
        df = results[[param_name, metric]].dropna().sort_values(param_name)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.plot(df[param_name], df[metric], 'o-', linewidth=2, markersize=8)
        ax.set_xlabel(param_name, fontsize=12)
        ax.set_ylabel(metric, fontsize=12)
        ax.set_title(f'{param_name} vs {metric}', fontsize=14)
        ax.grid(True, alpha=0.3)
        
        # 标记最优点
        best_idx = df[metric].idxmax()
        best_val = df.loc[best_idx, param_name]
        best_metric = df.loc[best_idx, metric]
        ax.scatter([best_val], [best_metric], color='red', s=200, zorder=5, 
                   label=f'Best: {param_name}={best_val}, {metric}={best_metric:.2f}')
        ax.legend()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {save_path}")
        
        plt.close()
        return fig
    
    def plot_heatmap(
        self,
        results: pd.DataFrame,
        param1: str,
        param2: str,
        metric: str = 'sharpe',
        save_path: str = None
    ):
        """绘制双参数热力图"""
        pivot = results.pivot_table(
            index=param1, 
            columns=param2, 
            values=metric,
            aggfunc='mean'
        )
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        im = ax.imshow(pivot.values, cmap='RdYlGn', aspect='auto')
        
        # 设置刻度标签
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_yticks(range(len(pivot.index)))
        ax.set_xticklabels([f'{c:.2f}' for c in pivot.columns])
        ax.set_yticklabels([f'{r:.2f}' for r in pivot.index])
        
        ax.set_xlabel(param2, fontsize=12)
        ax.set_ylabel(param1, fontsize=12)
        ax.set_title(f'{metric} Heatmap: {param1} vs {param2}', fontsize=14)
        
        # 颜色条
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label(metric, fontsize=12)
        
        # 在每个格子上标注数值
        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                val = pivot.values[i, j]
                if not pd.isna(val):
                    color = 'white' if val < pivot.values.mean() else 'black'
                    ax.text(j, i, f'{val:.2f}', ha='center', va='center', 
                            color=color, fontsize=9)
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"热力图已保存: {save_path}")
        
        plt.close()
        return fig
    
    def plot_equity_curve_comparison(
        self,
        results_dict: Dict[str, Dict],
        save_path: str = None
    ):
        """绘制多策略收益曲线对比
        
        results_dict: {'策略名': {'dates': [...], 'equity': [...]}}
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        
        for name, data in results_dict.items():
            if 'dates' in data and 'equity' in data:
                ax.plot(data['dates'], data['equity'], label=name, linewidth=1.5)
        
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Equity', fontsize=12)
        ax.set_title('Equity Curve Comparison', fontsize=14)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"收益曲线对比图已保存: {save_path}")
        
        plt.close()
        return fig


def test_charts():
    """测试图表生成"""
    import numpy as np
    
    # 模拟数据
    np.random.seed(42)
    results = pd.DataFrame({
        'rebalance_days': [5, 10, 15, 20, 5, 10, 15, 20],
        'stop_loss': [-0.08, -0.08, -0.08, -0.08, -0.10, -0.10, -0.10, -0.10],
        'return': np.random.uniform(-10, 30, 8),
        'sharpe': np.random.uniform(-0.5, 2.0, 8),
        'drawdown': np.random.uniform(-30, -5, 8),
    })
    
    chart = SensitivityChart()
    
    # 测试单参数图
    chart.plot_single_param(results, 'rebalance_days', 'sharpe')
    
    # 测试热力图
    chart.plot_heatmap(results, 'rebalance_days', 'stop_loss', 'return')
    
    print("✓ 图表生成测试通过")
    return True


if __name__ == '__main__':
    test_charts()


__all__ = ['SensitivityChart', 'test_charts']