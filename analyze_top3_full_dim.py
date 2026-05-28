#!/usr/bin/env python
"""
Top3模型完整9维度指标详表
"""
import json
import numpy as np
from collections import defaultdict

with open('data/experiments/fishbody_v3.json', 'r') as f:
    data = json.load(f)

results = data['results']

# 按配置分组
config_results = defaultdict(list)
for r in results:
    config_results[r['config']].append(r)

# 按总收益排序Top3
config_ranking = []
for cfg, cfg_results in config_results.items():
    total_ret = sum(r['stats']['total_return'] for r in cfg_results)
    config_ranking.append((cfg, total_ret, cfg_results))

config_ranking.sort(key=lambda x: x[1], reverse=True)
top3 = config_ranking[:3]

# 9维度定义
DIMENSIONS = [
    ('D1', '总收益', '%'),
    ('D2', '年化收益', '%'),
    ('D3', '夏普比率', ''),
    ('D4', '最大回撤', '%'),
    ('D5', '胜率', '%'),
    ('D6', '盈亏比', ''),
    ('D7', '交易次数', '次'),
    ('D8', 'IC均值', ''),
    ('D9', '因子方向一致', '%'),
]

def get_value(stats, dim_id):
    if dim_id == 'D1': return stats.get('total_return', 0)
    if dim_id == 'D2': return stats.get('annual_return', 0)
    if dim_id == 'D3': return stats.get('sharpe_ratio', 0)
    if dim_id == 'D4': return stats.get('max_drawdown', 0)
    if dim_id == 'D5': return stats.get('win_rate', 0)
    if dim_id == 'D6': return stats.get('profit_loss_ratio', 0)
    if dim_id == 'D7': return stats.get('trade_count', 0)
    return 0

# IC因子
FACTORS = ['BULLISH_ALIGN', 'MACD_SIGNAL', 'FISHBODY_OK', 'RSI_OK', 'TREND_OK']

# ETF中文名
ETF_NAMES = {
    'sh510300': '沪深300',
    'sh510500': '中证500',
    'sh159915': '创业板',
    'sh159806': '新能源',
    'sh512760': '医疗',
    'sh515050': '5G',
    'sh511010': '纳指',
}

output = []
output.append("# 📊 Top3 模型完整9维度指标详表")
output.append("")
output.append("## 一、9维度定义")
output.append("")
output.append("| 维度 | 指标名称 | 单位 | 说明 |")
output.append("|------|----------|------|------|")
output.append("| D1 | 总收益 | % | 最终收益百分比 |")
output.append("| D2 | 年化收益 | % | 平均年化收益 |")
output.append("| D3 | 夏普比率 | - | 风险调整收益 |")
output.append("| D4 | 最大回撤 | % | 历史最大亏损 |")
output.append("| D5 | 胜率 | % | 盈利交易占比 |")
output.append("| D6 | 盈亏比 | - | 平均盈利/平均亏损 |")
output.append("| D7 | 交易次数 | 次 | 总交易数 |")
output.append("| D8 | IC均值 | - | 因子预测能力 |")
output.append("| D9 | 因子方向一致 | % | 方向符合预期 |")
output.append("")

for rank, (cfg, total_ret, cfg_results) in enumerate(top3, 1):
    params = cfg_results[0]['params']
    
    output.append("")
    output.append("="*80)
    output.append(f"## 二、{'🥇' if rank==1 else '🥈' if rank==2 else '🥉'} 第{rank}名: {cfg}")
    output.append(f"**配置**: 止损{int(params['stop_loss']*100)}%, 止盈{int(params['stop_profit']*100)}%, 持仓{params['max_hold_days']}天")
    output.append(f"**总收益**: {total_ret:.1f}%")
    output.append("")
    
    # 表1: 每个ETF的9维度指标
    output.append("### 2." + str(rank) + " 完整9维度数据 (按ETF)")
    output.append("")
    output.append("| ETF | " + " | ".join([d[1] for d in DIMENSIONS]) + " |")
    output.append("|------|" + "|".join(["-" * 10 for _ in DIMENSIONS]) + "|")
    
    for r in cfg_results:
        stats = r['stats']
        etf = ETF_NAMES.get(r['code'], r['code'].replace('sh', ''))
        
        row = [etf]
        for dim_id, _, unit in DIMENSIONS:
            val = get_value(stats, dim_id)
            if unit == '%':
                row.append(f"{val:.2f}%")
            else:
                row.append(f"{val:.4f}")
        output.append("| " + " | ".join(row) + " |")
    
    # 平均行
    avg_row = ["**平均**"]
    for dim_id, _, unit in DIMENSIONS:
        vals = [get_value(r['stats'], dim_id) for r in cfg_results]
        avg = np.mean(vals)
        if unit == '%':
            avg_row.append(f"**{avg:.2f}%**")
        else:
            avg_row.append(f"**{avg:.4f}**")
    output.append("| " + " | ".join(avg_row) + " |")
    
    output.append("")
    
    # 表2: 极值统计
    output.append("### 2." + str(rank+3) + " 极值统计")
    output.append("")
    output.append("| 维度 | 最小值 ETF | 最小值 | 最大值 ETF | 最大值 | 均值 | 标准差 |")
    output.append("|------|-----------|--------|-----------|--------|------|--------|")
    
    for dim_id, dim_name, unit in DIMENSIONS:
        vals = [(get_value(r['stats'], dim_id), r['code']) for r in cfg_results]
        min_val, min_etf = min(vals, key=lambda x: x[0])
        max_val, max_etf = max(vals, key=lambda x: x[0])
        mean_val = np.mean([v[0] for v in vals])
        std_val = np.std([v[0] for v in vals])
        
        min_etf_name = ETF_NAMES.get(min_etf, min_etf.replace('sh', ''))
        max_etf_name = ETF_NAMES.get(max_etf, max_etf.replace('sh', ''))
        
        if unit == '%':
            output.append(f"| {dim_name} | {min_etf_name} | {min_val:.2f}% | {max_etf_name} | {max_val:.2f}% | {mean_val:.2f}% | {std_val:.2f} |")
        else:
            output.append(f"| {dim_name} | {min_etf_name} | {min_val:.4f} | {max_etf_name} | {max_val:.4f} | {mean_val:.4f} | {std_val:.4f} |")
    
    output.append("")
    
    # 表3: IC因子详细
    output.append("### 2." + str(rank+6) + " 因子IC详情")
    output.append("")
    output.append("| ETF | " + " | ".join([f.replace('_OK', '').replace('ALIGN', '') for f in FACTORS]) + " |")
    output.append("|------|" + "|".join(["-" * 8 for _ in FACTORS]) + "|")
    
    ic_valid_count = defaultdict(int)
    for r in cfg_results:
        ic = r['stats'].get('ic_results', {})
        etf = ETF_NAMES.get(r['code'], r['code'].replace('sh', ''))
        
        row = [etf]
        for f in FACTORS:
            val = ic.get(f, 0)
            row.append(f"{val:.4f}")
            if val > 0:
                ic_valid_count[f] += 1
        output.append("| " + " | ".join(row) + " |")
    
    output.append("")
    output.append("**因子有效统计** (IC>0的ETF数):")
    for f in FACTORS:
        count = ic_valid_count[f]
        total = len(cfg_results)
        ratio = count / total * 100
        status = "✅" if ratio > 50 else "⚠️" if ratio > 0 else "❌"
        output.append(f"- {status} {f}: {count}/{total} ({ratio:.0f}%)")
    output.append("")

# 三、Top3横向对比
output.append("")
output.append("="*80)
output.append("## 三、Top3 横向对比")
output.append("")
output.append("### 3.1 各维度排名")
output.append("")
output.append("| 维度 | Cfg4 | Cfg5 | Cfg2 | 最优 |")
output.append("|------|------|------|------|------|")

# 计算Top3各维度均值
cfg_means = {}
for cfg, total_ret, cfg_results in top3:
    means = {}
    for dim_id, _, unit in DIMENSIONS:
        vals = [get_value(r['stats'], dim_id) for r in cfg_results]
        means[dim_id] = np.mean(vals)
    cfg_means[cfg] = means

for dim_id, dim_name, unit in DIMENSIONS:
    vals = [(cfg_means[cfg][dim_id], cfg) for cfg, _, _ in top3]
    if dim_id in ['D4']:  # 回撤越小越好
        best = min(vals, key=lambda x: x[0])
        vals_sorted = sorted(vals, key=lambda x: x[0])
    else:
        best = max(vals, key=lambda x: x[0])
        vals_sorted = sorted(vals, key=lambda x: x[0], reverse=True)
    
    row = [dim_name]
    for cfg, _, _ in top3:
        val = cfg_means[cfg][dim_id]
        if unit == '%':
            row.append(f"{val:.2f}%")
        else:
            row.append(f"{val:.4f}")
    
    best_cfg = best[1]
    row.append(best_cfg)
    output.append("| " + " | ".join(row) + " |")

output.append("")
output.append("### 3.2 全部数据汇总表")
output.append("")
output.append("| 配置 | ETF | " + " | ".join([d[1] for d in DIMENSIONS]) + " |")
output.append("|------|------|" + "|".join(["-" * 10 for _ in DIMENSIONS]) + "|")

for cfg, total_ret, cfg_results in top3:
    for r in cfg_results:
        stats = r['stats']
        etf = ETF_NAMES.get(r['code'], r['code'].replace('sh', ''))
        
        row = [cfg, etf]
        for dim_id, _, unit in DIMENSIONS:
            val = get_value(stats, dim_id)
            if unit == '%':
                row.append(f"{val:.2f}%")
            else:
                row.append(f"{val:.4f}")
        output.append("| " + " | ".join(row) + " |")

# 四、综合评分
output.append("")
output.append("="*80)
output.append("## 四、综合评分 (9维度加权)")
output.append("")

# 计算综合得分
weights = {'D1': 0.20, 'D2': 0.15, 'D3': 0.15, 'D4': 0.15, 'D5': 0.10, 'D6': 0.10, 'D7': 0.05, 'D8': 0.05, 'D9': 0.05}

output.append("权重: " + ", ".join([f"D{i+1}={weights['D'+str(i+1)]*100:.0f}%" for i in range(9)]))
output.append("")
output.append("| 配置 | " + " | ".join([d[1] for d in DIMENSIONS]) + " | 综合得分 |")
output.append("|------|" + "|".join(["-" * 10 for _ in DIMENSIONS]) + "|----------|")

scores = {}
for cfg, total_ret, cfg_results in top3:
    row = [cfg]
    weighted_sum = 0
    
    for dim_id, _, unit in DIMENSIONS:
        vals = [get_value(r['stats'], dim_id) for r in cfg_results]
        cfg_avg = np.mean(vals)
        
        # 标准化到0-100
        all_vals = [get_value(r['stats'], dim_id) for r in results if r['config'] in cfg_means]
        min_v, max_v = min(all_vals), max(all_vals)
        if max_v > min_v:
            norm = (cfg_avg - min_v) / (max_v - min_v) * 100
        else:
            norm = 50
        
        if unit == '%':
            row.append(f"{cfg_avg:.2f}%")
        else:
            row.append(f"{cfg_avg:.4f}")
        
        weighted_sum += norm * weights[dim_id]
    
    scores[cfg] = weighted_sum
    row.append(f"**{weighted_sum:.1f}**")
    output.append("| " + " | ".join(row) + " |")

output.append("")
output.append("**综合评分排名**: " + ", ".join([f"{cfg}({score:.1f}分)" for cfg, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)]))

# 打印输出
print("\n".join(output))

# 保存文件
with open('docs/TOP3_FULL_DIMENSION_REPORT.md', 'w') as f:
    f.write("\n".join(output))