#!/usr/bin/env python
import json
import numpy as np
from collections import defaultdict

with open('data/experiments/fishbody_v3.json', 'r') as f:
    data = json.load(f)

results = data['results']

config_results = defaultdict(list)
for r in results:
    config_results[r['config']].append(r)

config_ranking = []
for cfg, cfg_results in config_results.items():
    total_ret = sum(r['stats']['total_return'] for r in cfg_results)
    config_ranking.append((cfg, total_ret, cfg_results))

config_ranking.sort(key=lambda x: x[1], reverse=True)
top3 = config_ranking[:3]

ETF_NAMES = {
    'sh510300': '沪深300',
    'sh510500': '中证500',
    'sh159915': '创业板',
    'sh159806': '新能源',
    'sh512760': '医疗',
    'sh515050': '5G',
    'sh511010': '纳指',
}

FACTORS = ['BULLISH_ALIGN', 'MACD_SIGNAL', 'FISHBODY_OK', 'RSI_OK', 'TREND_OK']

output = []

for rank, (cfg, total_ret, cfg_results) in enumerate(top3, 1):
    params = cfg_results[0]['params']
    
    output.append("")
    output.append("="*80)
    output.append("## 第{}名: {}".format(rank, cfg))
    output.append("**配置**: 止损{}%, 止盈{}%, 持仓{}天".format(
        int(params['stop_loss']*100),
        int(params['stop_profit']*100),
        params['max_hold_days']
    ))
    output.append("")
    
    output.append("### 因子IC详情 (5因子)")
    output.append("")
    
    factor_names = []
    for f in FACTORS:
        name = f.replace('_OK', '').replace('_ALIGN', '').replace('_SIGNAL', '')
        factor_names.append(name)
    
    output.append("| ETF | " + " | ".join(factor_names) + " | 平均IC |")
    output.append("|------|" + "|".join(["-" * 10 for _ in FACTORS]) + "|---------|")
    
    for r in cfg_results:
        ic = r['stats'].get('ic_results', {})
        etf = ETF_NAMES.get(r['code'], r['code'].replace('sh', ''))
        
        row = [etf]
        ic_vals = []
        for f in FACTORS:
            val = float(ic.get(f, 0))
            row.append("{:.4f}".format(val))
            ic_vals.append(val)
        avg_ic = np.mean(ic_vals)
        row.append("{:.4f}".format(avg_ic))
        output.append("| " + " | ".join(row) + " |")
    
    avg_row = ["**平均**"]
    for f in FACTORS:
        vals = [float(r['stats'].get('ic_results', {}).get(f, 0)) for r in cfg_results]
        avg_row.append("**{:.4f}**".format(np.mean(vals)))
    vals = []
    for r in cfg_results:
        ic_vals = [float(r['stats'].get('ic_results', {}).get(f, 0)) for f in FACTORS]
        vals.append(np.mean(ic_vals))
    avg_row.append("**{:.4f}**".format(np.mean(vals)))
    output.append("| " + " | ".join(avg_row) + " |")
    
    output.append("")
    output.append("**因子有效统计** (IC>0):")
    for f in FACTORS:
        valid = sum(1 for r in cfg_results if float(r['stats'].get('ic_results', {}).get(f, 0)) > 0)
        total = len(cfg_results)
        ratio = valid / total * 100
        status = "YES" if ratio > 50 else "PARTIAL" if ratio > 0 else "NO"
        output.append("- {} {}: {}/{} ({:.0f}%)".format(status, f, valid, total, ratio))

print("\n".join(output))