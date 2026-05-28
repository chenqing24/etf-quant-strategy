"""
因子挖掘实验1: 初始配置

目标: 验证8因子IC结果，建立基准
日期: 2026-05-27
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import Database
from src.indicators.wrapper import IndicatorCalculator, calculate_returns
from src.analysis.experiment_logger import get_logger
from src.analysis.ic_calculator import calculate_ic, calculate_ir
import pandas as pd
import numpy as np


def run_experiment_1():
    """实验1: 初始因子配置"""
    
    print("=" * 70)
    print("🔬 因子挖掘实验 #1: 初始配置")
    print("=" * 70)
    
    db = Database()
    calculator = IndicatorCalculator()
    logger = get_logger()
    
    # 获取所有ETF代码
    stock_info = db.query("SELECT code FROM stock_info")
    codes = [row['code'] for row in stock_info if row['code'] not in ['behavior_log', 'etf_performance', 'etf_positions', 'etf_trades', 'realtime_cache', 'test_code']]
    print(f"\n数据范围: {len(codes)} 个ETF")
    
    # 因子列表
    FACTORS = ['RSI_5', 'DMA', 'DIF', 'K', 'OBV_diff', 'BB_percent', 'SAR_trend', 'ADX']
    
    # 计算每个因子的IC
    all_ic_results = {f: [] for f in FACTORS}
    
    for code in codes:
        # 加载数据
        df = db.query_df(
            "SELECT date, open, high, low, close, volume FROM daily_price WHERE code = ? ORDER BY date",
            (code,)
        )
        if df.empty or len(df) < 60:
            continue
        
        # 计算指标
        df = calculator.calculate_all(df)
        df = calculate_returns(df)
        
        # 计算5日收益IC
        for factor in FACTORS:
            if factor in df.columns:
                ic = calculate_ic(df[factor], df['return_5d'], method='pearson')
                if not np.isnan(ic):
                    all_ic_results[factor].append(ic)
    
    # 汇总IC
    ic_summary = {}
    for factor, ic_list in all_ic_results.items():
        if ic_list:
            ic_mean = np.mean(ic_list)
            ic_std = np.std(ic_list)
            ir = ic_mean / ic_std if ic_std > 0 else 0
            ic_summary[factor] = ic_mean
    
    print("\n📊 IC汇总:")
    for f, ic in sorted(ic_summary.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"  {f:<12} IC={ic:>8.4f}")
    
    # 确定因子方向
    factor_direction = {}
    for factor, ic in ic_summary.items():
        if ic > 0.02:
            factor_direction[factor] = 'long'
        elif ic < -0.02:
            factor_direction[factor] = 'short'
        else:
            factor_direction[factor] = 'neutral'
    
    print("\n📍 因子方向:")
    for f, direction in factor_direction.items():
        icon = "📈" if direction == 'long' else ("📉" if direction == 'short' else "➡️")
        print(f"  {icon} {f}: {direction}")
    
    # 有效因子
    effective_factors = [f for f, d in factor_direction.items() if d != 'neutral']
    print(f"\n有效因子: {len(effective_factors)}/{len(FACTORS)}")
    
    # 计算权重 (使用IC绝对值归一化)
    total_ic = sum(abs(ic_summary.get(f, 0)) for f in effective_factors)
    weights = {}
    for f in effective_factors:
        ic = ic_summary.get(f, 0)
        weights[f] = abs(ic) / total_ic if total_ic > 0 else 0
    
    print("\n⚖️ 因子权重:")
    for f, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        print(f"  {f:<12} {w:>6.2%}")
    
    # 记录实验
    exp_id = logger.log_experiment(
        name="Exp1: 初始配置",
        description="8因子初始IC验证，基准实验",
        factors=FACTORS,
        ic_results=ic_summary,
        factor_direction=factor_direction,
        weights=weights,
        tags=['initial', 'baseline']
    )
    
    print(f"\n✅ 实验 #{exp_id} 已记录")
    
    # 检查是否需要复盘
    if logger.should_review():
        print("\n" + logger.review_round(logger._get_current_round()))
        logger.mark_reviewed()
    
    return {
        'exp_id': exp_id,
        'ic_results': ic_summary,
        'factor_direction': factor_direction,
        'weights': weights,
        'effective_factors': effective_factors
    }


if __name__ == "__main__":
    run_experiment_1()