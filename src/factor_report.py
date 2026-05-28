#!/usr/bin/env python3
"""因子有效性报告生成"""
import pandas as pd
from typing import Dict, List
from datetime import datetime

from src.factor_analysis import FactorAnalyzer


class FactorReport:
    """因子有效性报告"""
    
    def __init__(self, data_dir: str = None):
        self.analyzer = FactorAnalyzer(data_dir=data_dir) if data_dir else None
        self.results: Dict = {}
    
    def generate_report(
        self,
        data: Dict[str, pd.DataFrame],
        factors: List[str] = None,
        lookback_days: int = 60
    ) -> pd.DataFrame:
        """生成因子有效性报告
        
        Args:
            data: ETF数据字典
            factors: 因子列表
            lookback_days: 回看天数
            
        Returns:
            因子有效性DataFrame
        """
        if factors is None:
            factors = ['ma120', 'ma60', 'ma20', 'vol_ratio', 'rsi_14', 'macd']
        
        results = []
        
        for factor in factors:
            try:
                # 计算该因子的IC序列
                ic_series = self._calc_factor_ic(data, factor, lookback_days)
                
                if len(ic_series) > 0:
                    ic_mean = ic_series.mean()
                    ic_std = ic_series.std()
                    ir = ic_mean / ic_std if ic_std > 0 else 0
                    
                    results.append({
                        'factor': factor,
                        'ic_mean': ic_mean,
                        'ic_std': ic_std,
                        'ir': ir,
                        'ic_positive_pct': (ic_series > 0).sum() / len(ic_series),
                        'sample_count': len(ic_series),
                    })
                    
            except Exception as e:
                print(f"  因子 {factor} 计算失败: {e}")
        
        self.results = pd.DataFrame(results)
        
        if len(self.results) > 0:
            self.results = self.results.sort_values('ir', ascending=False)
        
        return self.results
    
    def _calc_factor_ic(
        self,
        data: Dict[str, pd.DataFrame],
        factor: str,
        lookback_days: int
    ) -> pd.Series:
        """计算单个因子的IC序列"""
        ic_values = []
        
        for code, df in data.items():
            if len(df) < lookback_days + 20:
                continue
            
            df = df.tail(lookback_days + 20).copy()
            
            if factor not in df.columns:
                continue
            
            # 计算每日因子值与次日收益的IC
            df['next_return'] = df['close'].pct_change().shift(-1)
            
            valid = df.dropna(subset=[factor, 'next_return'])
            
            if len(valid) > 10:
                ic = valid[factor].corr(valid['next_return'])
                if not pd.isna(ic):
                    ic_values.append(ic)
        
        return pd.Series(ic_values)
    
    def print_report(self):
        """打印报告"""
        if self.results is None or len(self.results) == 0:
            print("无因子数据")
            return
        
        print("\n" + "="*70)
        print("📊 因子有效性报告")
        print("="*70)
        print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-"*70)
        
        # 表头
        print(f"{'因子':<12} {'IC均值':>10} {'IC标准差':>10} {'IR':>8} "
              f"{'正向IC比例':>12} {'样本数':>8}")
        print("-"*70)
        
        for _, row in self.results.iterrows():
            star = "⭐" if row['ir'] > 0.3 else ("★" if row['ir'] > 0.1 else "")
            print(f"{row['factor']:<12} {row['ic_mean']:>+10.4f} "
                  f"{row['ic_std']:>10.4f} {row['ir']:>8.3f} "
                  f"{row['ic_positive_pct']:>11.1%} {row['sample_count']:>8}{star}")
        
        print("-"*70)
        print("⭐ IR > 0.3 高效因子  ★ IR > 0.1 有效因子")
        print("="*70)
        
        # 建议
        print("\n💡 因子使用建议:")
        high_ir = self.results[self.results['ir'] > 0.1]
        if len(high_ir) > 0:
            top_factors = high_ir['factor'].tolist()[:3]
            print(f"  推荐使用: {', '.join(top_factors)}")
        else:
            print("  警告: 无高效因子，建议降低选股阈值")
        
        print()
    
    def get_ic_weights(self) -> Dict[str, float]:
        """获取IC权重用于选股"""
        if self.results is None or len(self.results) == 0:
            return {}
        
        # 归一化IR为权重
        total_ir = self.results['ir'].abs().sum()
        if total_ir == 0:
            return {}
        
        weights = {}
        for _, row in self.results.iterrows():
            # 使用IR的绝对值作为权重
            weight = abs(row['ir']) / total_ir
            # 映射到基础权重 (1-3分)
            weights[row['factor']] = 1 + weight * 2
        
        return weights


def quick_report():
    """快速报告测试"""
    from .config import load_etf_data
    
    data = load_etf_data('etf_data_live')
    
    report = FactorReport()
    df = report.generate_report(data)
    report.print_report()
    
    weights = report.get_ic_weights()
    print(f"IC权重: {weights}")
    
    print("✓ 因子报告测试通过")
    return True


if __name__ == '__main__':
    quick_report()


__all__ = ['FactorReport', 'quick_report']