#!/usr/bin/env python3
"""列出本次挖掘计划探索的所有方向"""
import json
from pathlib import Path

print('=' * 70)
print('ETF多因子挖掘探索方向汇总')
print('=' * 70)

sections = [
    ('【一、趋势因子】', [
        '1. MACD趋势（红柱/金叉/死叉）',
        '2. MA多头排列（MA5/10/20/60/120）',
        '3. SAR趋势跟随',
        '轮次: Round 1-2'
    ]),
    ('【二、动量因子】', [
        '1. 动量指标（3日/5日/10日）',
        '2. RSI超卖/超买',
        '3. KDJ金叉/死叉',
        '4. CCI突破',
        '轮次: Round 2-3'
    ]),
    ('【三、量价因子】', [
        '1. OBV趋势',
        '2. 放量/缩量突破',
        '3. 量价背离',
        '4. 换手率异常',
        '文件: volume_price_factor.py'
    ]),
    ('【四、波动率因子】', [
        '1. 布林带突破（上下轨/中轨）',
        '2. ATR止损',
        '3. 波动率聚类',
        '文件: volatility_factor.py'
    ]),
    ('【五、行业轮动因子】', [
        '1. 行业强弱排序',
        '2. 行业动量',
        '3. 行业轮动信号',
        '文件: sector_rotation.py'
    ]),
    ('【六、大盘趋势过滤】', [
        '1. 510300 MA20 > MA60 多头',
        '2. 510300 MA空头时禁止买入',
        '贯穿: Round 2-10'
    ]),
    ('【七、复合因子组合】', [
        '1. IC加权因子权重',
        '2. 多因子打分模型',
        '文件: composite_factor.py'
    ]),
    ('【八、风控参数优化】', [
        '1. 止损参数（-3% ~ -8%）',
        '2. 止盈参数（+5% ~ +20%）',
        '3. 最大持仓天数（3~10天）',
        '轮次: Round 4-10'
    ]),
    ('【九、过拟合检验】', [
        '1. 滚动窗口验证',
        '2. 蒙特卡洛随机化检验',
        '3. 参数敏感性分析',
        '文件: overfitting_test_v2.py'
    ]),
]

for title, items in sections:
    print()
    print(title)
    for item in items:
        print(f'  {item}')

print()
print('=' * 70)
print('实验规模')
print('=' * 70)
total = 0
for f in sorted(Path('data/experiments').glob('round*.json')):
    with open(f) as fp:
        data = json.load(fp)
    count = len(data.get('results', [])) if isinstance(data, dict) else len(data)
    print(f'{f.name:20} {count:>5} 组实验')
    total += count

print('-' * 70)
print(f'{"总计":<20} {total:>5} 组实验')