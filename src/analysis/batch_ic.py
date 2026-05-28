"""
批量IC计算脚本

计算66只ETF的8个核心因子IC值
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from tqdm import tqdm

from src.data.database import Database
from src.data.data_importer import DataImporter
from src.indicators.wrapper import IndicatorCalculator, calculate_returns
from src.analysis.ic_calculator import calculate_ic, calculate_ir, CORE_FACTORS


class BatchICCalculator:
    """批量IC计算器"""
    
    def __init__(self, db: Database = None):
        """
        初始化
        
        Args:
            db: 数据库实例
        """
        self.db = db or Database()
        self.calculator = IndicatorCalculator()
        self.results = []
    
    def load_etf_data(self, code: str) -> Optional[pd.DataFrame]:
        """
        加载单个ETF数据
        
        Args:
            code: ETF代码
            
        Returns:
            DataFrame
        """
        df = self.db.query_df(
            "SELECT date, open, high, low, close, volume FROM daily_price WHERE code = ? ORDER BY date",
            (code,)
        )
        
        if df.empty:
            return None
        
        return df
    
    def calculate_factor_ic(
        self,
        df: pd.DataFrame,
        factor_col: str,
        return_period: int = 5
    ) -> Dict:
        """
        计算单个因子的IC
        
        Args:
            df: 因子数据
            factor_col: 因子列名
            return_period: 收益周期
            
        Returns:
            IC结果字典
        """
        if factor_col not in df.columns:
            return None
        
        factor = df[factor_col]
        return_col = f'return_{return_period}d'
        
        if return_col not in df.columns:
            return None
        
        returns = df[return_col]
        
        ic = calculate_ic(factor, returns, method='pearson')
        
        return {
            'factor': factor_col,
            'ic': ic,
            'sample_count': factor.notna().sum()
        }
    
    def calculate_all_factors_ic(
        self,
        df: pd.DataFrame,
        return_period: int = 5
    ) -> List[Dict]:
        """
        计算所有因子的IC
        
        Args:
            df: DataFrame
            return_period: 收益周期
            
        Returns:
            IC结果列表
        """
        # 计算因子
        df = self.calculator.calculate_all(df)
        df = calculate_returns(df)
        
        results = []
        
        # 计算各因子IC
        factor_cols = [
            'RSI_5', 'DMA', 'DIF', 'K', 'OBV_diff',
            'BB_percent', 'SAR_trend', 'ADX'
        ]
        
        for factor_col in factor_cols:
            if factor_col in df.columns:
                ic_result = self.calculate_factor_ic(df, factor_col, return_period)
                if ic_result:
                    results.append(ic_result)
        
        return results
    
    def calculate_single_etf(
        self,
        code: str,
        return_period: int = 5
    ) -> Dict:
        """
        计算单个ETF的所有因子IC
        
        Args:
            code: ETF代码
            return_period: 收益周期
            
        Returns:
            结果字典
        """
        df = self.load_etf_data(code)
        if df is None:
            return {'code': code, 'success': False, 'reason': '无数据'}
        
        try:
            ic_results = self.calculate_all_factors_ic(df, return_period)
            return {
                'code': code,
                'success': True,
                'ic_results': ic_results,
                'data_count': len(df)
            }
        except Exception as e:
            return {
                'code': code,
                'success': False,
                'reason': str(e)
            }
    
    def batch_calculate(
        self,
        codes: List[str],
        return_period: int = 5,
        show_progress: bool = True
    ) -> pd.DataFrame:
        """
        批量计算多个ETF的IC
        
        Args:
            codes: ETF代码列表
            return_period: 收益周期
            show_progress: 显示进度条
            
        Returns:
            IC结果DataFrame
        """
        all_results = []
        success_count = 0
        
        iterator = tqdm(codes, desc="计算IC") if show_progress else codes
        
        for code in iterator:
            result = self.calculate_single_etf(code, return_period)
            
            if result['success']:
                success_count += 1
                for ic_result in result['ic_results']:
                    all_results.append({
                        'code': code,
                        'factor': ic_result['factor'],
                        'ic': ic_result['ic'],
                        'sample_count': ic_result['sample_count'],
                        'return_period': return_period,
                        'data_count': result['data_count']
                    })
            else:
                print(f"{code}: {result.get('reason', '未知错误')}")
        
        df = pd.DataFrame(all_results)
        
        print(f"\n计算完成: {success_count}/{len(codes)} 成功")
        
        return df
    
    def aggregate_ic(self, ic_df: pd.DataFrame) -> pd.DataFrame:
        """
        汇总IC结果
        
        Args:
            ic_df: IC计算结果
            
        Returns:
            汇总后的IC统计
        """
        if ic_df.empty:
            return pd.DataFrame()
        
        # 按因子分组统计
        agg = ic_df.groupby('factor').agg({
            'ic': ['mean', 'std', 'count'],
            'sample_count': 'sum'
        }).reset_index()
        
        agg.columns = ['factor', 'ic_mean', 'ic_std', 'etf_count', 'total_samples']
        
        # 计算IR
        agg['ir'] = agg['ic_mean'] / agg['ic_std']
        
        # 判断方向
        agg['direction'] = agg['ic_mean'].apply(
            lambda x: 'long' if x > 0.02 else ('short' if x < -0.02 else 'neutral')
        )
        
        # 排序
        agg = agg.sort_values('ic_mean', ascending=False)
        
        return agg
    
    def save_to_database(self, ic_df: pd.DataFrame, start_date: str, end_date: str):
        """
        保存IC结果到数据库
        
        Args:
            ic_df: IC结果
            start_date: 起始日期
            end_date: 结束日期
        """
        for _, row in ic_df.iterrows():
            data = {
                'factor_name': row['factor'],
                'code': row['code'],
                'period': row['return_period'],
                'ic_mean': row['ic'],
                'sample_count': row['sample_count'],
                'start_date': start_date,
                'end_date': end_date,
                'created_at': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            self.db.insert_or_update(
                'ic_results',
                data,
                ['factor_name', 'code', 'period', 'start_date', 'end_date']
            )
    
    def print_summary(self, agg_df: pd.DataFrame):
        """
        打印汇总结果
        
        Args:
            agg_df: 汇总DataFrame
        """
        print("\n" + "=" * 70)
        print("8因子IC汇总结果")
        print("=" * 70)
        
        print(f"\n{'因子':<15} {'IC均值':>10} {'IC标准差':>10} {'IR':>8} {'方向':>10} {'样本数':>10}")
        print("-" * 70)
        
        for _, row in agg_df.iterrows():
            direction_symbol = '📈' if row['direction'] == 'long' else ('📉' if row['direction'] == 'short' else '➡️')
            print(f"{row['factor']:<15} {row['ic_mean']:>10.4f} {row['ic_std']:>10.4f} {row['ir']:>8.4f} {row['direction']:>6} {direction_symbol} {row['total_samples']:>10}")
        
        # 有效因子
        valid_factors = agg_df[abs(agg_df['ic_mean']) > 0.02]
        print(f"\n有效因子 (|IC| > 0.02): {len(valid_factors)}/{len(agg_df)}")
        print(f"正向因子: {len(agg_df[agg_df['direction'] == 'long'])}")
        print(f"反向因子: {len(agg_df[agg_df['direction'] == 'short'])}")


def run_batch_ic(
    db_path: str = "data/etf_factors.db",
    return_period: int = 5
):
    """
    运行批量IC计算
    
    Args:
        db_path: 数据库路径
        return_period: 收益周期
    """
    print("=" * 70)
    print("ETF 8因子批量IC计算")
    print("=" * 70)
    
    # 初始化
    db = Database(db_path)
    calculator = BatchICCalculator(db)
    
    # 获取所有ETF代码
    stock_info = db.query("SELECT code FROM stock_info")
    codes = [row['code'] for row in stock_info]
    print(f"\n发现 {len(codes)} 个ETF")
    
    if len(codes) == 0:
        print("数据库中没有ETF数据，请先导入数据")
        return
    
    # 批量计算
    ic_df = calculator.batch_calculate(codes, return_period)
    
    if ic_df.empty:
        print("IC计算结果为空")
        return
    
    # 汇总
    agg_df = calculator.aggregate_ic(ic_df)
    
    # 打印结果
    calculator.print_summary(agg_df)
    
    # 保存到数据库
    ic_df['start_date'] = '2020-01-01'
    ic_df['end_date'] = '2026-05-27'
    
    # 保存汇总结果
    summary_path = Path("data/ic_summary.csv")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    agg_df.to_csv(summary_path, index=False)
    print(f"\n汇总结果已保存到: {summary_path}")
    
    return agg_df


if __name__ == "__main__":
    run_batch_ic()