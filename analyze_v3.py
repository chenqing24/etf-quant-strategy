#!/usr/bin/env python
import json

with open('data/experiments/fishbody_v3.json', 'r') as f:
    data = json.load(f)

results = data['results']

print('='*80)
print('全部42个实验结果明细')
print('='*80)

# 按配置分组
configs = {}
for r in results:
    cfg = r['config']
    if cfg not in configs:
        configs[cfg] = []
    configs[cfg].append(r)

for cfg in sorted(configs.keys()):
    cfg_results = configs[cfg]
    cfg_info = cfg_results[0]['params']
    
    print()
    print('='*60)
    print(cfg + ' 止损' + str(int(cfg_info['stop_loss']*100)) + '% 止盈' + str(int(cfg_info['stop_profit']*100)) + '% 持仓' + str(cfg_info['max_hold_days']) + '天')
    print('='*60)
    
    total_ret = sum(r['stats']['total_return'] for r in cfg_results)
    avg_ret = total_ret / len(cfg_results)
    total_trades = sum(r['trade_count'] for r in cfg_results)
    
    print('总收益: %.1f%% 平均收益: %.1f%% 总交易: %d次' % (total_ret, avg_ret, total_trades))
    print()
    print('  ETF             收益      胜率    交易    IC均值      未来函数')
    print('  ' + '-'*60)
    
    ic_sum = 0
    for r in cfg_results:
        ic = r['stats']['ic_results']
        avg_ic = sum(float(v) for v in ic.values()) / len(ic) if ic else 0
        ic_sum += avg_ic
        
        la = 'YES' if r['validation']['no_look_ahead'] else 'NO'
        print('  %-14s %7.1f%%   %5.1f%%   %4d   %8.4f   %s' % (r['code'], r['stats']['total_return'], r['stats']['win_rate'], r['trade_count'], avg_ic, la))
    
    print('  IC均值: %.4f' % (ic_sum/len(cfg_results),))