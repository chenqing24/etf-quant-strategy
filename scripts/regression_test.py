#!/usr/bin/env python3
"""
回归测试: 用新验证器重跑v8_sop实验

功能：
1. 加载v8_sop实验数据
2. 用新验证器验证核心通过模型
3. 对比新旧结果
4. 生成对比报告
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.loader import DataLoader
from scripts.validators import ComprehensiveValidator


# ETF池（与v8_sop一致）
ETF_POOL = [
    '510300', '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]

# 因子定义（与v8_sop一致）
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


def get_signal(df, factor_name):
    """获取信号函数"""
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
    """获取组合信号"""
    signals = [get_signal(df, f) for f in factors]
    combo_signal = signals[0]
    for s in signals[1:]:
        combo_signal = combo_signal & s
    return combo_signal


def main():
    print("=" * 60)
    print("回归测试: 新验证器 vs 旧验证器")
    print("=" * 60)
    
    # Step 1: 加载数据
    print("\n【Step 1】加载数据")
    loader = DataLoader()
    etf_data = {}
    
    for code in ETF_POOL:
        df = loader.load_single(code, min_rows=400)
        if df is not None:
            df = df.sort_values('date').reset_index(drop=True)
            etf_data[code] = df
    
    print(f"加载完成: {len(etf_data)}只ETF")
    
    # Step 2: 加载旧实验结果
    print("\n【Step 2】加载旧实验结果")
    old_results_file = Path(__file__).parent.parent / 'data' / 'experiments_v8_sop' / 'results_sop.json'
    
    if old_results_file.exists():
        with open(old_results_file) as f:
            old_data = json.load(f)
        
        old_top_models = old_data.get('top_models', [])[:5]
        print(f"旧Top5模型: {len(old_top_models)}个")
    else:
        print("旧结果文件不存在，跳过")
        old_top_models = []
    
    # Step 3: 用新验证器验证
    print("\n【Step 3】用新验证器验证")
    validator = ComprehensiveValidator()
    
    new_results = []
    
    for i, model in enumerate(old_top_models):
        factors = model['factors']
        etf_code = model['etf_code']
        
        print(f"\n  [{i+1}/{len(old_top_models)}] {factors}")
        print(f"    ETF: {etf_code}")
        
        if etf_code not in etf_data:
            print(f"    ⚠️ 数据不存在，跳过")
            continue
        
        df = etf_data[etf_code]
        
        # 创建信号函数
        def signal_func(df, fs=factors):
            return get_combined_signal(df, fs)
        
        # 验证
        try:
            result = validator.validate({etf_code: df}, signal_func)
            new_results.append({
                'factors': factors,
                'etf_code': etf_code,
                'old_pass': bool(model.get('pass_core', False)),
                'new_score': float(result.composite_score),
                'new_pass': bool(result.pass_),
                'wf_score': float(result.walk_forward_score),
                'mc_score': float(result.monte_carlo_score),
                'ce_score': float(result.cross_etf_score)
            })
            
            print(f"    综合分: {result.composite_score:.3f}")
            print(f"    通过: {result.pass_}")
            print(f"    WF: {result.walk_forward_score:.2f}, MC: {result.monte_carlo_score:.2f}, CE: {result.cross_etf_score:.2f}")
            
        except Exception as e:
            print(f"    ❌ 验证失败: {e}")
    
    # Step 4: 生成对比报告
    print("\n" + "=" * 60)
    print("对比报告")
    print("=" * 60)
    
    print("\n| # | 因子组合 | ETF | 旧通过 | 新综合分 | 新通过 | WF | MC | CE |")
    print("|---|----------|-----|:------:|:--------:|:------:|:--:|:--:|:--:|")
    
    for i, r in enumerate(new_results):
        print(f"| {i+1} | {r['factors'][0][:10]}... | {r['etf_code']} | {'✅' if r['old_pass'] else '❌'} | {r['new_score']:.2f} | {'✅' if r['new_pass'] else '❌'} | {r['wf_score']:.2f} | {r['mc_score']:.2f} | {r['ce_score']:.2f} |")
    
    # 统计
    old_pass_count = sum(1 for r in new_results if r['old_pass'])
    new_pass_count = sum(1 for r in new_results if r['new_pass'])
    
    print(f"\n**统计对比**")
    print(f"- 旧验证通过: {old_pass_count}/{len(new_results)}")
    print(f"- 新验证通过: {new_pass_count}/{len(new_results)}")
    
    if new_results:
        avg_new_score = sum(r['new_score'] for r in new_results) / len(new_results)
        avg_wf = sum(r['wf_score'] for r in new_results) / len(new_results)
        avg_mc = sum(r['mc_score'] for r in new_results) / len(new_results)
        avg_ce = sum(r['ce_score'] for r in new_results) / len(new_results)
        
        print(f"- 平均综合分: {avg_new_score:.3f}")
        print(f"- 平均WF: {avg_wf:.3f}")
        print(f"- 平均MC: {avg_mc:.3f}")
        print(f"- 平均CE: {avg_ce:.3f}")
    
    # 保存结果
    output_file = Path(__file__).parent.parent / 'data' / 'experiments_v8_sop' / 'regression_results.json'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'old_results_count': len(old_top_models),
        'tested_count': len(new_results),
        'old_pass_count': old_pass_count,
        'new_pass_count': new_pass_count,
        'new_results': [
            {
                'factors': r['factors'],
                'etf_code': r['etf_code'],
                'old_pass': r['old_pass'],
                'new_score': float(r['new_score']),
                'new_pass': r['new_pass'],
                'wf_score': float(r['wf_score']),
                'mc_score': float(r['mc_score']),
                'ce_score': float(r['ce_score'])
            }
            for r in new_results
        ],
        'averages': {
            'composite_score': float(avg_new_score) if new_results else 0,
            'wf_score': float(avg_wf) if new_results else 0,
            'mc_score': float(avg_mc) if new_results else 0,
            'ce_score': float(avg_ce) if new_results else 0
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 结果已保存: {output_file}")
    
    return report


if __name__ == '__main__':
    import pandas as pd
    main()