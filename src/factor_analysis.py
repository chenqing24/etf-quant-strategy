#!/usr/bin/env python3
"""因子有效性分析 - IC/IR计算"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


class FactorAnalysis:
    """因子有效性分析器"""
    
    @staticmethod
    def calculate_ic(factor_values: np.ndarray, forward_returns: np.ndarray) -> float:
        """计算因子IC值 (Information Coefficient)
        
        Args:
            factor_values: 因子值序列
            forward_returns: 未来收益序列
            
        Returns:
            IC值 (-1 ~ 1)
        """
        # 去除NaN
        if len(factor_values) != len(forward_returns):
            return 0.0
            
        mask = ~(np.isnan(factor_values) | np.isnan(forward_returns))
        f = factor_values[mask]
        r = forward_returns[mask]
        
        if len(f) < 5:  # 样本太少
            return 0.0
            
        # Pearson相关系数 (手动计算)
        if np.std(f) == 0 or np.std(r) == 0:
            return 0.0
        ic = np.corrcoef(f, r)[0, 1]
        return ic if not np.isnan(ic) else 0.0
    
    @staticmethod
    def calculate_rolling_ic(
        factor_series: pd.Series,
        return_series: pd.Series,
        window: int = 20
    ) -> pd.Series:
        """计算滚动IC
        
        Args:
            factor_series: 因子序列
            return_series: 收益序列
            window: 滚动窗口
            
        Returns:
            滚动IC序列
        """
        rolling_ic = pd.Series(index=factor_series.index, dtype=float)
        
        for i in range(window, len(factor_series)):
            factor_window = factor_series.iloc[i-window:i].values
            
            # 未来收益 (shift -1 表示当日持仓次日收益)
            return_window = return_series.iloc[i-window+1:i+1].values
            
            ic = FactorAnalysis.calculate_ic(factor_window, return_window)
            rolling_ic.iloc[i] = ic
        
        return rolling_ic.dropna()
    
    @staticmethod
    def calculate_ir(rolling_ic: pd.Series) -> Tuple[float, float, float]:
        """计算信息比 (Information Ratio)
        
        Args:
            rolling_ic: 滚动IC序列
            
        Returns:
            (IC均值, IC标准差, IR)
        """
        ic_mean = rolling_ic.mean()
        ic_std = rolling_ic.std()
        
        if ic_std == 0 or np.isnan(ic_std):
            return ic_mean, ic_std, 0.0
            
        ir = ic_mean / ic_std
        return ic_mean, ic_std, ir
    
    @staticmethod
    def analyze_factor有效性(
        df: pd.DataFrame,
        factor_name: str,
        return_col: str = 'return',
        window: int = 20
    ) -> Dict:
        """分析单个因子的有效性
        
        Args:
            df: 包含因子和收益的数据
            factor_name: 因子列名
            return_col: 收益列名
            window: 滚动窗口
            
        Returns:
            分析结果字典
        """
        factor = df[factor_name].dropna()
        returns = df[return_col].dropna()
        
        # 对齐索引
        common_idx = factor.index.intersection(returns.index)
        factor = factor.loc[common_idx]
        returns = returns.loc[common_idx]
        
        # 计算滚动IC
        rolling_ic = FactorAnalysis.calculate_rolling_ic(factor, returns, window)
        
        if len(rolling_ic) == 0:
            return {
                'factor': factor_name,
                'ic_mean': 0.0,
                'ic_std': 0.0,
                'ir': 0.0,
                'ic_positive_ratio': 0.0,
            }
        
        # IC统计
        ic_mean, ic_std, ir = FactorAnalysis.calculate_ir(rolling_ic)
        
        # IC为正的比例
        ic_positive_ratio = (rolling_ic > 0).mean()
        
        return {
            'factor': factor_name,
            'ic_mean': round(ic_mean, 4),
            'ic_std': round(ic_std, 4),
            'ir': round(ir, 4),
            'ic_positive_ratio': round(ic_positive_ratio, 4),
            'rolling_ic': rolling_ic,
        }
    
    @staticmethod
    def analyze_all_factors(
        data: Dict[str, pd.DataFrame],
        date: str,
        forward_days: int = 5
    ) -> pd.DataFrame:
        """分析所有因子的有效性
        
        Args:
            data: ETF数据字典
            date: 分析日期
            forward_days: 向前计算收益的天数
            
        Returns:
            因子有效性报告DataFrame
        """
        results = []
        
        # 收集某一天所有ETF的因子值和未来收益
        factor_data = []
        
        for code, df in data.items():
            row = df[df['date'] == date]
            if len(row) == 0:
                continue
            row = row.iloc[0]
            
            # 获取未来收益
            idx = df[df['date'] == date].index[0]
            if idx + forward_days < len(df):
                future_price = df.iloc[idx + forward_days]['close']
                current_price = df.iloc[idx]['close']
                future_return = (future_price - current_price) / current_price
            else:
                continue
            
            factor_data.append({
                'code': code,
                'ma120_signal': 1 if row.get('close', 0) > row.get('ma120', 0) else 0,
                'ma60_up_signal': 1 if row.get('ma60_up', False) else 0,
                'ma60_signal': 1 if row.get('close', 0) > row.get('ma60', 0) else 0,
                'ma20_signal': 1 if row.get('close', 0) > row.get('ma20', 0) else 0,
                'vol_signal': 1 if row.get('vol_ratio', 0) > 1.5 else 0,
                'rsi_signal': 1 if row.get('rsi_14', 100) < 70 else 0,
                'macd_signal': 1 if row.get('macd', 0) > 0 else 0,
                'future_return': future_return,
            })
        
        if len(factor_data) < 10:
            return pd.DataFrame()
        
        df_analysis = pd.DataFrame(factor_data)
        factor_cols = ['ma120_signal', 'ma60_up_signal', 'ma60_signal', 
                       'ma20_signal', 'vol_signal', 'rsi_signal', 'macd_signal']
        
        for col in factor_cols:
            # 将信号(0/1)转为因子值
            ic = FactorAnalysis.calculate_ic(
                df_analysis[col].values,
                df_analysis['future_return'].values
            )
            results.append({
                'factor': col,
                'ic_mean': round(ic, 4),
                'description': FactorAnalysis.get_factor_description(col),
            })
        
        return pd.DataFrame(results).sort_values('ic_mean', ascending=False)
    
    @staticmethod
    def get_factor_description(factor: str) -> str:
        """获取因子描述"""
        descriptions = {
            'ma120_signal': '站上MA120 (+3分)',
            'ma60_up_signal': 'MA60向上 (+2分)',
            'ma60_signal': '站上MA60 (+2分)',
            'ma20_signal': '站上MA20 (+1分)',
            'vol_signal': '放量 (+2分)',
            'rsi_signal': 'RSI健康 (+1分)',
            'macd_signal': 'MACD金叉 (+1分)',
        }
        return descriptions.get(factor, factor)


def test_factor_analysis():
    """测试因子分析"""
    # 创建测试数据
    np.random.seed(42)
    n = 100
    
    df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=n),
        'factor1': np.random.randn(n),
        'return': np.random.randn(n) * 0.02,  # 与factor1相关
    })
    
    # 让factor1和return正相关
    df['return'] = df['factor1'] * 0.05 + np.random.randn(n) * 0.01
    
    # 测试IC计算
    ic = FactorAnalysis.calculate_ic(df['factor1'].values, df['return'].values)
    assert abs(ic) > 0, "IC应该显著"
    print(f"✓ IC计算测试通过: IC={ic:.4f}")
    
    # 测试滚动IC
    rolling_ic = FactorAnalysis.calculate_rolling_ic(df['factor1'], df['return'], window=20)
    assert len(rolling_ic) > 0, "应有滚动IC"
    print(f"✓ 滚动IC计算测试通过: 均值={rolling_ic.mean():.4f}")
    
    # 测试IR计算
    ic_mean, ic_std, ir = FactorAnalysis.calculate_ir(rolling_ic)
    assert ir != 0, "IR应该非零"
    print(f"✓ IR计算测试通过: IR={ir:.4f}")
    
    return True


if __name__ == '__main__':
    test_factor_analysis()
    print("\n✓ 因子分析模块测试通过!")


__all__ = ['FactorAnalysis']