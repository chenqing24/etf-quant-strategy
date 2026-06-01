#!/usr/bin/env python3
"""ETF筛选 - 仅保留宽基指数 + 行业ETF"""
import json

# 读取分析结果
with open('etf_data_live/etf_selection_analysis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 只保留宽基指数和行业ETF
allowed_categories = ['宽基指数', '行业ETF']

# 重新筛选
final_codes = []
exclude_list = []
categories_summary = {}

for detail in data['details']:
    cat = detail['category']
    
    if cat not in categories_summary:
        categories_summary[cat] = {'total': 0, 'kept': 0, 'codes': []}
    
    categories_summary[cat]['total'] += 1
    categories_summary[cat]['codes'].append(detail['code'])
    
    if cat in allowed_categories:
        final_codes.append(detail['code'])
        categories_summary[cat]['kept'] += 1
    else:
        exclude_list.append(detail['code'])

print("=" * 70)
print("📊 ETF筛选结果（仅保留宽基指数 + 行业ETF）")
print("=" * 70)

print("\n【分类统计】")
for cat, info in categories_summary.items():
    status = "✅ 保留" if cat in allowed_categories else "❌ 排除"
    print(f"  {cat}: {info['total']}只 ({info['kept']}保留 / {info['total']-info['kept']}排除) {status}")

print(f"\n【最终结果】")
print(f"  原始ETF池: {data['total']}只")
print(f"  保留（宽基+行业）: {len(final_codes)}只")
print(f"  排除（其他）: {len(exclude_list)}只")

print(f"\n【排除的类别】")
excluded_by_cat = {}
for code in exclude_list:
    for detail in data['details']:
        if detail['code'] == code:
            cat = detail['category']
            if cat not in excluded_by_cat:
                excluded_by_cat[cat] = []
            excluded_by_cat[cat].append(code)
            break

for cat, codes in excluded_by_cat.items():
    print(f"  {cat}: {len(codes)}只")
    print(f"    {', '.join(codes[:10])}")

print(f"\n【保留的ETF代码】({len(final_codes)}只)")
for i in range(0, len(final_codes), 15):
    print("  " + ", ".join(final_codes[i:i+15]))

# 保存结果
with open('etf_data_live/final_etf_pool.txt', 'w') as f:
    f.write("# 最终ETF池（仅宽基指数 + 行业ETF）\n")
    f.write(f"# 筛选标准：排除货币基金、债券基金、QDII海外、商品ETF\n")
    f.write(f"# 总数: {len(final_codes)}只\n\n")
    f.write("ETF_POOL = [\n")
    for code in final_codes:
        f.write(f"    '{code}',\n")
    f.write("]\n")

print(f"\n✅ 已保存: etf_data_live/final_etf_pool.txt")