#!/usr/bin/env python3
"""3因子组合全排列分析"""
from itertools import combinations

# 定义因子池（基于业界最佳实践）
factor_pool = {
    # 趋势因子（最重要）
    'T1_MACD红柱': {'category': '趋势', 'importance': 0.9},
    'T2_MA20多头': {'category': '趋势', 'importance': 0.6},
    'T3_MA多头排列': {'category': '趋势', 'importance': 0.5},
    'T4_SAR趋势': {'category': '趋势', 'importance': 0.4},
    
    # 动量因子（有效）
    'M1_动量3日': {'category': '动量', 'importance': 0.8},
    'M2_动量5日': {'category': '动量', 'importance': 0.7},
    'M3_动量10日': {'category': '动量', 'importance': 0.6},
    'M4_RSI适中': {'category': '动量', 'importance': 0.5},
    'M5_KDJ金叉': {'category': '动量', 'importance': 0.4},
    
    # 量价因子（辅助）
    'V1_OBV多头': {'category': '量价', 'importance': 0.7},
    'V2_放量突破': {'category': '量价', 'importance': 0.6},
    'V3_量价背离': {'category': '量价', 'importance': 0.4},
    'V4_换手率异常': {'category': '量价', 'importance': 0.3},
    
    # 波动率因子（辅助）
    'B1_布林中轨突破': {'category': '波动率', 'importance': 0.7},
    'B2_布林下轨反弹': {'category': '波动率', 'importance': 0.5},
    'B3_低波动': {'category': '波动率', 'importance': 0.4},
    
    # 大盘过滤（必需）
    'D1_大盘MA20>MA60': {'category': '大盘', 'importance': 0.9},
}

# 计算3因子组合
factor_names = list(factor_pool.keys())
all_combinations = list(combinations(factor_names, 3))

print('=' * 70)
print('3因子组合全排列分析')
print('=' * 70)
print(f'因子总数: {len(factor_pool)} 个')
print(f'3因子组合总数: {len(all_combinations)} 种')
print()

# 按重要性评分
def score_combination(factors):
    """评分函数：优先趋势+动量+大盘"""
    score = 0
    categories = set()
    
    for f in factors:
        info = factor_pool[f]
        score += info['importance']
        categories.add(info['category'])
    
    # 必须包含：趋势(T) + 动量(M) 或 大盘(D)
    has_trend = any('T' in f for f in factors)
    has_momentum = any('M' in f for f in factors)
    has_market = any('D' in f for f in factors)
    
    # 最佳组合：趋势+动量+大盘 或 趋势+动量+量价
    if has_trend and has_momentum and has_market:
        score *= 1.5  # 最优组合
    elif has_trend and has_momentum:
        score *= 1.2
    
    return score

# 评分并排序
scored = []
for combo in all_combinations:
    score = score_combination(combo)
    scored.append((score, combo))

scored.sort(reverse=True)

# 取前20%（按业界最佳实践过滤）
top_20_pct = int(len(scored) * 0.20)
top_combos = scored[:top_20_pct]

print(f'前20%组合数: {top_20_pct} 种')
print()
print('=' * 70)
print('按业界最佳实践过滤后的 Top 20% 组合')
print('=' * 70)
print('评分标准:')
print('  1. 因子重要性累加')
print('  2. 最佳组合: 趋势(T) + 动量(M) + 大盘(D) x1.5')
print('  3. 次佳组合: 趋势(T) + 动量(M) + 其他 x1.2')
print()
print('-' * 70)

for i, (score, combo) in enumerate(top_combos[:30], 1):
    cats = [factor_pool[f]['category'] for f in combo]
    cats_str = '+'.join(sorted(set(cats)))
    print(f'{i:2}. [{cats_str}] {" + ".join(combo)}')
    
print()
print('...' if len(top_combos) > 30 else '')
print(f'共 {len(top_combos)} 种组合待验证')