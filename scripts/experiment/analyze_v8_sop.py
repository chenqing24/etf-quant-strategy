#!/usr/bin/env python3
"""
v8_sop 实验结果分析脚本

用途：
    - 分析 v8_sop 实验结果
    - 生成 ETF 分布统计
    - 分析因子出现频率

被谁调用：
    - 无（独立工具，手动执行）
    - 实验复盘时使用

功能说明：
    - 读取 data/experiments_v8_sop/results_sop.json
    - 统计核心通过模型的 ETF 分布
    - 分析因子出现频率

使用方式：
    python scripts/experiment/analyze_v8_sop.py

依赖：
    - json

注意事项：
    - 已豁免 pre-commit 检查（分析脚本）
    - 仅用于数据分析，不执行交易
"""

with open('data/experiments_v8_sop/results_sop.json') as f:
    data = json.load(f)

combo = data['combinations']
single = data['single_factor']

print("=" * 60)
print("v8_sop 深度复盘分析")
print("=" * 60)

# 1. ETF分布分析
etf_dist = {}
for r in combo:
    if r.get('pass_core', False):
        etf = r['etf_code']
        etf_dist[etf] = etf_dist.get(etf, 0) + 1

print("\n【1. 核心通过模型的ETF分布】")
for etf, count in sorted(etf_dist.items(), key=lambda x: -x[1]):
    print(f"  {etf}: {count}个")

# 2. 因子出现频率
factor_count = {}
for r in combo:
    if r.get('pass_core', False):
        for f in r['factors']:
            factor_count[f] = factor_count.get(f, 0) + 1

print("\n【2. 核心通过模型中各因子出现频率】")
for f, count in sorted(factor_count.items(), key=lambda x: -x[1]):
    print(f"  {f}: {count}次")

# 3. 2因子vs3因子对比
two_factor = [r for r in combo if len(r['factors']) == 2 and r.get('pass_core', False)]
three_factor = [r for r in combo if len(r['factors']) == 3 and r.get('pass_core', False)]
two_total = sum(1 for r in combo if len(r['factors']) == 2)
three_total = sum(1 for r in combo if len(r['factors']) == 3)
print(f"\n【3. 2因子 vs 3因子通过率】")
print(f"  2因子: {len(two_factor)}/{two_total} = {len(two_factor)/two_total*100:.1f}%")
print(f"  3因子: {len(three_factor)}/{three_total} = {len(three_factor)/three_total*100:.1f}%")

# 4. 单因子IC分布
print("\n【4. 单因子IC排名】")
for f, d in sorted(single.items(), key=lambda x: -abs(x[1]['ic_mean'])):
    status = "✅" if abs(d['ic_mean']) > 0.02 else "⚠️" if abs(d['ic_mean']) > 0.01 else "❌"
    print(f"  {status} {f}: IC={d['ic_mean']:.4f}, IR={d['ir']:.2f}")

# 5. 收益分布
passed_returns = [r['total_return']*100 for r in combo if r.get('pass_core', False)]
if passed_returns:
    print(f"\n【5. 核心通过模型收益分布】")
    print(f"  最高: {max(passed_returns):.1f}%")
    print(f"  最低: {min(passed_returns):.1f}%")
    print(f"  平均: {sum(passed_returns)/len(passed_returns):.1f}%")

# 6. 交易次数分布
trade_counts = [r['trade_count'] for r in combo if r.get('pass_core', False)]
if trade_counts:
    print(f"\n【6. 核心通过模型交易次数分布】")
    print(f"  最多: {max(trade_counts)}次")
    print(f"  最少: {min(trade_counts)}次")
    print(f"  平均: {sum(trade_counts)/len(trade_counts):.1f}次")

# 7. 过拟合检验详情
print("\n【7. 过拟合检验结果】")
if data.get('top_models'):
    top = data['top_models'][:5]
    for r in top:
        rolling = r.get('overfit_rolling', 0)
        mc_pval = r.get('overfit_mc_pvalue', 1)
        cv = r.get('overfit_cv', 0)
        print(f"  {r['factors']}")
        print(f"    滚动:{rolling:.2f} MC_p:{mc_pval:.3f} CV:{cv:.2f}")