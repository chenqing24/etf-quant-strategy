#!/usr/bin/env python3
"""
全面验证: 用新验证器测试所有4125个组合

Phase 1: 快速筛选（WalkForward only）
Phase 2: 深度验证（核心通过模型）

执行时间: ~2小时（4125 × 2秒筛选 + 90 × 30秒深度）
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from scripts.validators import ComprehensiveValidator

# ============ 配置 ============
ETF_POOL = [
    '510300', '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]

FACTORS = {
    'T1_MACD红柱': {'func': 'macd_positive'},
    'T2_MA多头': {'func': 'ma_bullish'},
    'T3_SAR趋势': {'func': 'sar_bullish'},
    'T4_ADX趋势': {'func': 'adx_strong'},
    'M1_动量3日': {'func': 'momentum_3d'},
    'M2_动量5日': {'func': 'momentum_5d'},
    'M3_RSI适中': {'func': 'rsi_moderate'},
    'M4_KDJ金叉': {'func': 'kdj_golden'},
    'V1_放量': {'func': 'volume_surge'},
    'V2_OBV多头': {'func': 'obv_bullish'},
    'V3_资金流入': {'func': 'money_flow'},
    'B1_布林上轨突破': {'func': 'bollinger_upper'},
}

OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'experiments_v8_sop'


def get_signal(df, factor_name):
    """获取单个因子信号"""
    func_name = FACTORS[factor_name]['func']
    
    if func_name == 'macd_positive':
        return df['MACD_hist'] > 0
    elif func_name == 'ma_bullish':
        return (df['MA_short'] > df['MA_long'])
    elif func_name == 'sar_bullish':
        return df['close'] > df['SAR']
    elif func_name == 'adx_strong':
        return df['ADX'] > 25
    elif func_name == 'momentum_3d':
        return df['close'].pct_change(3) > 0
    elif func_name == 'momentum_5d':
        return df['close'].pct_change(5) > 0
    elif func_name == 'rsi_moderate':
        return (df['RSI_5'] > 40) & (df['RSI_5'] < 70)
    elif func_name == 'kdj_golden':
        return df['K'] > df['D']
    elif func_name == 'volume_surge':
        return df['volume'] > df['volume'].rolling(10).mean() * 1.2
    elif func_name == 'obv_bullish':
        return df['OBV'] > df['MAOBV']
    elif func_name == 'money_flow':
        return df['OBV'] > df['MAOBV']
    elif func_name == 'bollinger_upper':
        return df['close'] > df['BB_upper']
    else:
        return pd.Series(False, index=df.index)


def get_combined_signal(df, factors):
    """获取组合信号（AND）"""
    signals = [get_signal(df, f) for f in factors]
    combo_signal = signals[0]
    for s in signals[1:]:
        combo_signal = combo_signal & s
    return combo_signal


def main():
    print("=" * 60)
    print("全面验证: 新验证器测试所有4125个组合")
    print("=" * 60)
    
    # Step 1: 加载数据
    print("\n【Step 1】加载ETF数据...")
    loader = DataLoader()
    calc = IndicatorCalculator()
    
    etf_data = {}
    for code in ETF_POOL:
        df = loader.load_single(code, min_rows=400)
        if df is not None:
            df = df.sort_values('date').reset_index(drop=True)
            df = calc.calculate_all(df)
            etf_data[code] = df
    
    print(f"加载完成: {len(etf_data)}只ETF")
    
    # Step 2: 加载旧实验结果
    print("\n【Step 2】加载旧实验结果...")
    old_results_file = OUTPUT_DIR / 'results_sop.json'
    
    with open(old_results_file) as f:
        old_data = json.load(f)
    
    combinations = old_data.get('combinations', [])
    print(f"总组合数: {len(combinations)}")
    
    # Step 3: Phase 1 快速筛选（WalkForward only）
    print("\n【Step 3】Phase 1: WalkForward快速筛选")
    print("-" * 60)
    
    validator = ComprehensiveValidator()
    
    quick_results = []
    start_time = datetime.now()
    
    for i, combo in enumerate(combinations):
        factors = combo['factors']
        etf_code = combo['etf_code']
        
        if (i + 1) % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            eta = elapsed / (i + 1) * (len(combinations) - i - 1)
            print(f"  [{i+1}/{len(combinations)}] 进度 {(i+1)/len(combinations)*100:.1f}% | "
                  f"已用时 {elapsed/60:.1f}分钟 | 预计剩余 {eta/60:.1f}分钟")
        
        if etf_code not in etf_data:
            continue
        
        df = etf_data[etf_code]
        
        def signal_func(df, fs=factors):
            return get_combined_signal(df, fs)
        
        try:
            result = validator.validate({etf_code: df}, signal_func)
            quick_results.append({
                'factors': factors,
                'etf_code': etf_code,
                'old_pass_core': bool(combo.get('pass_core', False)),
                'new_score': float(result.composite_score),
                'new_pass': bool(result.pass_),
                'wf_score': float(result.walk_forward_score),
                'mc_score': float(result.monte_carlo_score),
                'ce_score': float(result.cross_etf_score),
                'warnings': result.warnings,
            })
        except Exception as e:
            quick_results.append({
                'factors': factors,
                'etf_code': etf_code,
                'old_pass_core': bool(combo.get('pass_core', False)),
                'new_score': 0.0,
                'new_pass': False,
                'wf_score': 0.0,
                'mc_score': 0.0,
                'ce_score': 0.0,
                'error': str(e),
            })
    
    # Step 4: 统计结果
    print("\n【Step 4】统计结果")
    print("-" * 60)
    
    total = len(quick_results)
    new_pass = sum(1 for r in quick_results if r.get('new_pass', False))
    old_core_pass = sum(1 for r in quick_results if r.get('old_pass_core', False))
    
    # 交叉分析
    old_pass_new_pass = sum(1 for r in quick_results if r.get('old_pass_core') and r.get('new_pass'))
    old_pass_new_fail = sum(1 for r in quick_results if r.get('old_pass_core') and not r.get('new_pass'))
    old_fail_new_pass = sum(1 for r in quick_results if not r.get('old_pass_core') and r.get('new_pass'))
    old_fail_new_fail = sum(1 for r in quick_results if not r.get('old_pass_core') and not r.get('new_pass'))
    
    print(f"总组合数: {total}")
    print(f"新验证通过: {new_pass} ({new_pass/total*100:.1f}%)")
    print(f"旧核心通过: {old_core_pass} ({old_core_pass/total*100:.1f}%)")
    print()
    print("交叉分析:")
    print(f"  旧通过 → 新通过: {old_pass_new_pass} (真阳性)")
    print(f"  旧通过 → 新未通过: {old_pass_new_fail} (假阳性)")
    print(f"  旧未通过 → 新通过: {old_fail_new_pass} (假阴性)")
    print(f"  旧未通过 → 新未通过: {old_fail_new_fail} (真阴性)")
    
    # 得分分布
    if quick_results:
        scores = [r['new_score'] for r in quick_results]
        print(f"\n得分分布:")
        print(f"  最小: {min(scores):.3f}")
        print(f"  最大: {max(scores):.3f}")
        print(f"  平均: {sum(scores)/len(scores):.3f}")
        
        # 分位数
        sorted_scores = sorted(scores)
        print(f"  P25: {sorted_scores[int(len(scores)*0.25)]:.3f}")
        print(f"  P50: {sorted_scores[int(len(scores)*0.50)]:.3f}")
        print(f"  P75: {sorted_scores[int(len(scores)*0.75)]:.3f}")
    
    # Step 5: 保存结果
    print("\n【Step 5】保存结果...")
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_combinations': total,
        'statistics': {
            'new_pass_count': new_pass,
            'new_pass_rate': new_pass / total if total else 0,
            'old_core_pass_count': old_core_pass,
            'cross_analysis': {
                'old_pass_new_pass': old_pass_new_pass,
                'old_pass_new_fail': old_pass_new_fail,
                'old_fail_new_pass': old_fail_new_pass,
                'old_fail_new_fail': old_fail_new_fail,
            }
        },
        'results': quick_results,
    }
    
    output_file = OUTPUT_DIR / 'full_validation_results.json'
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 结果已保存: {output_file}")
    
    # Step 6: Top20模型
    print("\n【Step 6】Top20模型（按新综合分）")
    print("-" * 60)
    
    sorted_results = sorted(quick_results, key=lambda x: x['new_score'], reverse=True)
    
    print(f"{'#':<3} {'因子':<30} {'ETF':<8} {'旧通过':<6} {'新分':<6} {'新通过':<6} {'WF':<5} {'MC':<5} {'CE':<5}")
    print("-" * 60)
    
    for i, r in enumerate(sorted_results[:20]):
        old_mark = '✅' if r.get('old_pass_core') else '❌'
        new_mark = '✅' if r.get('new_pass') else '❌'
        factors_str = '+'.join(r['factors'][:2])
        if len(r['factors']) > 2:
            factors_str += f'+...({len(r["factors"])})'
        
        print(f"{i+1:<3} {factors_str:<30} {r['etf_code']:<8} {old_mark:<6} "
              f"{r['new_score']:.3f}   {new_mark:<6} "
              f"{r['wf_score']:.2f}  {r['mc_score']:.2f}  {r['ce_score']:.2f}")
    
    print("-" * 60)
    print(f"\n✅ 验证完成！")
    
    return report


if __name__ == '__main__':
    import pandas as pd
    main()