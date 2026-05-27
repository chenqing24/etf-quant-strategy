"""
因子挖掘实验2: ADX优先配置

目标: ADX是IC最高的因子，给予更高权重
日期: 2026-05-27
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import Database
from src.indicators.wrapper import IndicatorCalculator, calculate_returns
from src.analysis.experiment_logger import get_logger
from src.analysis.ic_calculator import calculate_ic
import pandas as pd
import numpy as np


def run_experiment_2():
    """实验2: ADX优先配置"""
    
    print("=" * 70)
    print("🔬 因子挖掘实验 #2: ADX优先配置")
    print("=" * 70)
    
    db = Database()
    calculator = IndicatorCalculator()
    logger = get_logger()
    
    stock_info = db.query("SELECT code FROM stock_info")
    codes = [row['code'] for row in stock_info if row['code'] not in ['behavior_log', 'etf_performance', 'etf_positions', 'etf_trades', 'realtime_cache', 'test_code']]
    print(f"\n数据范围: {len(codes)} 个ETF")
    
    # 实验配置
    FACTORS = ['ADX', 'BB_percent', 'SAR_trend', 'RSI_5', 'K', 'DIF', 'OBV_diff', 'DMA']
    
    # 计算IC
    all_ic_results = {f: [] for f in FACTORS}
    
    for code in codes:
        df = db.query_df(
            "SELECT date, open, high, low, close, volume FROM daily_price WHERE code = ? ORDER BY date",
            (code,)
        )
        if df.empty or len(df) < 60:
            continue
        
        df = calculator.calculate_all(df)
        df = calculate_returns(df)
        
        for factor in FACTORS:
            if factor in df.columns:
                ic = calculate_ic(df[factor], df['return_5d'], method='pearson')
                if not np.isnan(ic):
                    all_ic_results[factor].append(ic)
    
    # IC汇总
    ic_summary = {}
    for factor, ic_list in all_ic_results.items():
        if ic_list:
            ic_summary[factor] = np.mean(ic_list)
    
    # 因子方向 (基于IC)
    factor_direction = {
        'ADX': 'long',         # ADX高 → 强趋势 → 做多
        'BB_percent': 'long',   # BB低 → 接近下轨 → 做多
        'SAR_trend': 'long',    # SAR上升 → 趋势向上
        'RSI_5': 'neutral',     # 中性
        'K': 'neutral',         # 中性
        'DIF': 'short',         # DIF高 → MACD超买 → 做空
        'OBV_diff': 'short',   # OBV差值为负 → 量能不足 → 做空
        'DMA': 'neutral'        # 中性
    }
    
    # 有效因子
    effective_factors = [f for f, d in factor_direction.items() if d != 'neutral']
    
    # ADX加权配置
    weights = {}
    for f in effective_factors:
        if f == 'ADX':
            weights[f] = 0.4  # ADX权重提高到40%
        elif f == 'BB_percent':
            weights[f] = 0.3  # BB权重30%
        elif f == 'SAR_trend':
            weights[f] = 0.3  # SAR权重30%
        else:
            weights[f] = 0
    
    print("\n📊 IC结果:", {f: f"{ic:.4f}" for f, ic in ic_summary.items()})
    print("\n⚖️ 权重配置 (ADX优先):")
    for f, w in weights.items():
        print(f"  {f:<12} {w:>6.1%}")
    
    # 记录实验
    exp_id = logger.log_experiment(
        name="Exp2: ADX优先",
        description="ADX因子权重40%，验证强趋势因子效果",
        factors=FACTORS,
        ic_results=ic_summary,
        factor_direction=factor_direction,
        weights=weights,
        tags=['adx', 'trend-following']
    )
    
    print(f"\n✅ 实验 #{exp_id} 已记录")
    
    if logger.should_review():
        print("\n" + logger.review_round(logger._get_current_round()))
        logger.mark_reviewed()
    
    return {'exp_id': exp_id, 'weights': weights}


if __name__ == "__main__":
    run_experiment_2()