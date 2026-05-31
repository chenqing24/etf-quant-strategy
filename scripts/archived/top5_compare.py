#!/usr/bin/env python3
"""Top 5 模型完整指标对比"""
import json
from pathlib import Path

# 加载所有轮次
all_results = []
for f in sorted(Path('data/experiments').glob('round*.json')):
    with open(f) as fp:
        data = json.load(fp)
        if isinstance(data, dict) and 'results' in data:
            all_results.extend(data['results'])

# 去重
seen = set()
unique = []
for r in all_results:
    name = r['factor_name']
    if name not in seen and r.get('test_return', 0) != 0:
        seen.add(name)
        unique.append(r)

# 筛选有效模型（测试收益>3%，|衰减|<100%）
valid = [r for r in unique if r.get('test_return', 0) > 0.03 and abs(r.get('oos_decay', 999)) < 1.0]
sorted_results = sorted(valid, key=lambda x: x.get('test_return', 0), reverse=True)
top5 = sorted_results[:5]

print('=' * 100)
print('🏆 Top 5 模型完整指标对比')
print('=' * 100)
print(f"{'排名':<4} {'模型名称':<35} {'测试收益':>8} {'夏普':>6} {'胜率':>6} {'最大回撤':>9} {'IC':>6} {'IR':>6} {'p值':>7}")
print('-' * 100)

for i, r in enumerate(top5, 1):
    name = r['factor_name'][:33]
    print(f"{i:<4} {name:<35} {r['test_return']:>7.1%} {r.get('sharpe_ratio', 0):>6.2f} {r.get('win_rate', 0):>6.1%} {r.get('max_drawdown', 0):>9.1%} {r.get('ic', 0):>6.3f} {r.get('ir', 0):>6.2f} {r.get('p_value', 1):>7.4f}")

print()
print('=' * 100)
print('📊 完整评价指标体系说明')
print('=' * 100)
print("""
┌─────────────────────────────────────────────────────────────────────────────┐
│  一、核心收益指标                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  测试收益   回测期(2026-05)收益率，越高越好                                      │
│  夏普比率   (Rp-Rf)/σp，衡量风险调整收益，>0.5为佳，>1.0为优秀                   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  二、交易效率指标                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  胜率       盈利交易占比，>40%为佳，>50%为优秀                                    │
│  最大回撤   最大亏损幅度，>-15%需关注，>-20%为高风险                             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  三、稳定性指标                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  IC         Information Coefficient，>0.03为佳                                │
│             因子与收益相关性，衡量因子预测力                                      │
│  IR         Information Ratio，>0.5为佳，>1.0为优秀                           │
│             IC均值/IC标准差，衡量因子稳定性                                      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  四、统计显著性                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  p值        <0.05为统计显著，<0.01为高度显著                                    │
│             p<0.05说明策略收益非随机                                           │
└─────────────────────────────────────────────────────────────────────────────┘
""")