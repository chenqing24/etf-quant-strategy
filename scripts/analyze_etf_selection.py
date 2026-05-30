#!/usr/bin/env python3
"""ETF筛选标准分析 - 基于业界最佳实践 v2.0"""
import sqlite3
import json

DB_PATH = "etf_data_live/etf.db"

# 合并后的ETF池（100只）
ETF_POOL = [
    '159131', '159206', '159217', '159316', '159326', '159338', '159352', '159361', '159363',
    '159509', '159516', '159529', '159530', '159558', '159567', '159570', '159611', '159740',
    '159792', '159845', '159870', '159915', '159941', '159949', '159967', '159995', '510050',
    '510300', '510310', '510500', '511880', '511990', '512000', '512050', '512100', '512400',
    '512480', '512690', '512760', '512800', '512880', '513050', '513080', '513100', '513120',
    '513130', '513180', '513310', '513330', '513360', '513580', '513090', '513010', '513360',
    '515000', '515050', '515790', '516050', '516110', '516120', '516160', '518880', '520500',
    '562500', '563360', '588000', '588080', '588170', '588200', '588220', '588290', '159801',
    '159806', '159808', '159825', '159857', '159867', '159902', '159919', '159920', '159928',
    '159934', '159952', '159981', '159997', '510010', '510030', '510100', '510150', '510180',
    '510210', '510660', '510880', '510900', '512010', '512170', '512200', '512500', '512580',
    '512660', '512980'
]

def get_etf_data(code):
    """获取ETF详细信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, exchange, aum FROM etf_names WHERE code = ?", (code,))
    row = cursor.fetchone()
    info = {'code': code, 'name': row[0] if row else '未知', 'exchange': row[1] if row else '未知', 'aum': row[2] if row else 0}
    
    cursor.execute("""
        SELECT COUNT(*) as cnt, MIN(date) as min_date, MAX(date) as max_date, 
               AVG(close) as avg_price, SUM(volume) as total_volume
        FROM daily WHERE code = ?
    """, (code,))
    row = cursor.fetchone()
    
    info['daily_count'] = row[0] or 0
    info['min_date'] = row[1]
    info['max_date'] = row[2]
    info['avg_price'] = row[3] or 0
    info['total_volume'] = row[4] or 0
    
    conn.close()
    return info

def classify_etf(info):
    """基于名称和特征分类ETF
    
    排除标准（基于业界最佳实践）：
    1. 货币基金 - 波动极低，价格约100元
    2. 债券基金 - 趋势不明显，收益稳定
    """
    name = info['name']
    avg_price = info['avg_price']
    
    category = ""
    suitable = True
    exclude_reasons = []
    
    # ========== 排除判断（严格标准）==========
    
    # 1. 货币基金
    if any(kw in name for kw in ['货币', '添益', '日利', '现金', '理财']):
        category = "货币基金"
        suitable = False
        exclude_reasons.append("货币基金波动极低，不适合趋势策略")
    
    # 2. 债券基金
    elif any(kw in name for kw in ['债券', '企债', '国债', '政债', '地方债', '公司债']):
        category = "债券基金"
        suitable = False
        exclude_reasons.append("债券收益稳定，趋势不明显")
    
    # 3. 纯债ETF（价格接近100）
    elif avg_price > 99 and avg_price < 101:
        category = "纯债ETF"
        suitable = False
        exclude_reasons.append("价格接近100元，可能是纯债ETF")
    
    # ========== 可选排除（参考标准）==========
    
    # 4. QDII海外
    elif any(kw in name for kw in ['纳指', '标普', '恒生', '日经', '德国', '法国', '东南亚', '越南', '印度']):
        category = "QDII海外"
        suitable = True  # 可考虑，但有时区差异
        exclude_reasons.append("海外ETF有时区差异，数据可能不连续")
    
    # 5. 黄金/商品
    elif any(kw in name for kw in ['黄金', '白银']):
        category = "商品ETF"
        suitable = True  # 可考虑，波动大
        exclude_reasons.append("受宏观影响大，趋势难以预测")
    
    # 6. 宽基指数
    elif any(kw in name for kw in ['沪深300', '中证500', '中证1000', '创业板', '上证50', '科创50']):
        category = "宽基指数"
        suitable = True
        exclude_reasons.append("")  # 无需排除
    
    # 7. 行业ETF
    elif any(kw in name for kw in ['芯片', '半导体', '医疗', '医药', '新能源', '光伏', '白酒', '消费', '券商', '银行']):
        category = "行业ETF"
        suitable = True
        exclude_reasons.append("")
    
    # 8. 其他
    else:
        category = "其他"
        suitable = True
        exclude_reasons.append("")
    
    return {'category': category, 'suitable': suitable, 'exclude_reasons': exclude_reasons}

def main():
    print("=" * 80)
    print("📊 ETF筛选标准分析 v2.0 - 基于业界最佳实践")
    print("=" * 80)
    
    results = []
    
    for code in ETF_POOL:
        info = get_etf_data(code)
        classification = classify_etf(info)
        info.update(classification)
        results.append(info)
    
    # 统计
    categories = {}
    unsuitable = []
    suitable = []
    
    for r in results:
        cat = r['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)
        
        if r['suitable']:
            suitable.append(r)
        else:
            unsuitable.append(r)
    
    # ========== 输出 ==========
    
    print("\n" + "=" * 80)
    print("📋 ETF分类统计")
    print("=" * 80)
    
    for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
        unsuitable_cnt = sum(1 for i in items if not i['suitable'])
        print(f"\n【{cat}】{len(items)}只 ({len(items)-unsuitable_cnt}✅ / {unsuitable_cnt}❌)")
        
        for item in items:
            status = "✅" if item['suitable'] else "❌"
            reason = item['exclude_reasons'][0] if item['exclude_reasons'] else ""
            print(f"  {status} {item['code']}: {item['name'][:25]} {reason}")
    
    # ========== 排除的ETF ==========
    
    print("\n" + "=" * 80)
    print("🚫 不适合量化策略的ETF（必须排除）")
    print("=" * 80)
    print(f"\n{'代码':<10} {'名称':<25} {'类别':<12} {'原因'}")
    print("-" * 80)
    
    for r in unsuitable:
        print(f"{r['code']:<10} {r['name'][:22]:<25} {r['category']:<12} {r['exclude_reasons'][0]}")
    
    # ========== 建议保留的ETF ==========
    
    print("\n" + "=" * 80)
    print("✅ 建议保留的ETF")
    print("=" * 80)
    
    for cat in ['宽基指数', '行业ETF', 'QDII海外', '商品ETF', '其他']:
        items = [r for r in suitable if r['category'] == cat]
        if items:
            print(f"\n【{cat}】{len(items)}只:")
            codes = [r['code'] for r in items]
            for i in range(0, len(codes), 15):
                print("  " + ", ".join(codes[i:i+15]))
    
    # ========== 最终统计 ==========
    
    print("\n" + "=" * 80)
    print("📈 最终统计")
    print("=" * 80)
    print(f"  ETF池总数: {len(ETF_POOL)}")
    print(f"  建议保留: {len(suitable)} ({len(suitable)/len(ETF_POOL)*100:.1f}%)")
    print(f"  建议排除: {len(unsuitable)} ({len(unsuitable)/len(ETF_POOL)*100:.1f}%)")
    
    # 排除的代码
    exclude_codes = [r['code'] for r in unsuitable]
    print(f"\n排除的代码 ({len(exclude_codes)}只):")
    print("  " + ", ".join(exclude_codes))
    
    # 保存结果
    final_codes = [r['code'] for r in suitable]
    
    result = {
        'total': len(ETF_POOL),
        'suitable': len(suitable),
        'unsuitable': len(unsuitable),
        'exclude_codes': exclude_codes,
        'final_codes': final_codes,
        'categories': {k: [r['code'] for r in v] for k, v in categories.items()},
        'details': results
    }
    
    with open('etf_data_live/etf_selection_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 保存最终代码列表
    with open('etf_data_live/final_etf_pool.txt', 'w') as f:
        f.write(f"# 最终ETF池（适合量化策略）\n")
        f.write(f"# 筛选标准：排除货币基金、债券基金\n")
        f.write(f"# 总数: {len(final_codes)}只\n")
        f.write(f"# 排除: {len(exclude_codes)}只\n\n")
        f.write("ETF_POOL = [\n")
        for code in final_codes:
            f.write(f"    '{code}',\n")
        f.write("]\n")
    
    print(f"\n✅ 已保存:")
    print(f"   - etf_data_live/etf_selection_analysis.json")
    print(f"   - etf_data_live/final_etf_pool.txt")

if __name__ == "__main__":
    main()