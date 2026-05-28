#!/usr/bin/env python3
"""交叉验证 - 多时间窗口滚动验证"""
import pandas as pd
from typing import List, Dict, Tuple
from dataclasses import dataclass

from src.utils.config import run_strategy
from pathlib import Path


@dataclass
class ValidationWindow:
    """验证窗口"""
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    name: str


class CrossValidator:
    """交叉验证器"""
    
    def __init__(self, data_dir: str = 'etf_data_live'):
        self.data_dir = data_dir
        self.results: List[Dict] = []
    
    def get_default_windows(self) -> List[ValidationWindow]:
        """获取默认验证窗口"""
        return [
            # 基准窗口
            ValidationWindow(
                train_start='2022-01-01',
                train_end='2024-12-31',
                test_start='2025-01-01',
                test_end='2026-05-22',
                name='基准 (2022-2024选→2025测)'
            ),
            # 短训练期
            ValidationWindow(
                train_start='2023-01-01',
                train_end='2024-12-31',
                test_start='2025-01-01',
                test_end='2025-12-31',
                name='2023-2024选→2025测'
            ),
            # 极短训练期
            ValidationWindow(
                train_start='2024-01-01',
                train_end='2024-12-31',
                test_start='2025-01-01',
                test_end='2025-06-30',
                name='2024选→2025上半年'
            ),
        ]
    
    def run_single_window(
        self, 
        window: ValidationWindow,
        **kwargs
    ) -> Dict:
        """运行单个验证窗口"""
        result = run_strategy(
            test_start=window.test_start,
            test_end=window.test_end,
            data_dir=self.data_dir,
            train_start=window.train_start,
            train_end=window.train_end,
            **kwargs
        )
        
        return {
            'name': window.name,
            'train_period': f"{window.train_start}~{window.train_end}",
            'test_period': f"{window.test_start}~{window.test_end}",
            'return': result.get('return', 0),
            'drawdown': result.get('drawdown', 0),
            'sharpe': result.get('sharpe', 0),
            'winrate': result.get('winrate', 0),
            'trades': result.get('trades', 0),
        }
    
    def run_cross_validation(
        self,
        windows: List[ValidationWindow] = None,
        **kwargs
    ) -> List[Dict]:
        """运行交叉验证"""
        if windows is None:
            windows = self.get_default_windows()
        
        self.results = []
        
        for window in windows:
            print(f"处理: {window.name}")
            result = self.run_single_window(window, **kwargs)
            self.results.append(result)
        
        return self.results
    
    def analyze_stability(self) -> Dict:
        """分析结果稳定性"""
        if not self.results:
            return {}
        
        returns = [r['return'] for r in self.results]
        drawdowns = [r['drawdown'] for r in self.results]
        sharpes = [r['sharpe'] for r in self.results]
        
        return {
            'return_mean': sum(returns) / len(returns),
            'return_min': min(returns),
            'return_max': max(returns),
            'return_std': pd.Series(returns).std(),
            'drawdown_mean': sum(drawdowns) / len(drawdowns),
            'sharpe_mean': sum(sharpes) / len(sharpes),
            'positive_count': sum(1 for r in returns if r > 0),
            'total_count': len(returns),
        }
    
    def print_report(self):
        """打印验证报告"""
        print("\n" + "="*70)
        print("交叉验证报告")
        print("="*70)
        
        headers = ['窗口', '训练期', '测试期', '收益', '回撤', '夏普', '胜率', '交易数']
        print(f"\n{headers[0]:<30} {headers[1]:<12} {headers[2]:<12} {headers[3]:>8} {headers[4]:>8} {headers[5]:>6} {headers[6]:>6} {headers[7]:>6}")
        print("-"*90)
        
        for r in self.results:
            print(f"{r['name']:<30} {r['train_period']:<12} {r['test_period']:<12} {r['return']:>+7.1f}% {r['drawdown']:>7.1f}% {r['sharpe']:>6.2f} {r['winrate']:>5.1f}% {r['trades']:>6}")
        
        # 稳定性分析
        stability = self.analyze_stability()
        print("\n" + "-"*70)
        print(f"平均收益: {stability.get('return_mean', 0):+.1f}%  (范围: {stability.get('return_min', 0):+.1f}% ~ {stability.get('return_max', 0):+.1f}%)")
        print(f"平均回撤: {stability.get('drawdown_mean', 0):.1f}%")
        print(f"平均夏普: {stability.get('sharpe_mean', 0):.2f}")
        print(f"正收益窗口: {stability.get('positive_count', 0)}/{stability.get('total_count', 0)}")
        print("="*70)
        
        return stability


def test_cross_validation():
    """测试交叉验证"""
    validator = CrossValidator(data_dir='etf_data_live')
    
    # 使用短窗口快速测试
    windows = [
        ValidationWindow(
            train_start='2024-01-01',
            train_end='2024-12-31',
            test_start='2025-01-01',
            test_end='2025-03-31',
            name='测试'
        ),
    ]
    
    results = validator.run_cross_validation(
        windows=windows,
        rebalance_days=5,
    )
    
    assert len(results) == 1
    assert 'return' in results[0]
    assert 'drawdown' in results[0]
    
    print("✓ 交叉验证测试通过")
    
    return True


if __name__ == '__main__':
    test_cross_validation()


__all__ = ['CrossValidator', 'ValidationWindow', 'test_cross_validation']