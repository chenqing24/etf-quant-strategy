#!/usr/bin/env python3
"""
ETF池筛选 - 流动性Top500版本
筛选流程：
1. 流动性筛选：按成交额排序，取Top500
2. 类型排除：排除货币基金、债券基金、QDII海外、商品ETF
3. 主题筛选：仅保留宽基指数+行业ETF
4. 去重：同主题保留规模最大的
"""
import sqlite3
import json
import requests

DB_PATH = "etf_data_live/etf.db"
AKTOOLS_URL = "http://127.0.0.1:8080"

# ========== 数据获取 ==========

def get_all_etf_spot():
    """获取全市场ETF实时行情"""
    print("📡 获取全市场ETF实时行情...")
    r = requests.get(f"{AKTOOLS_URL}/api/public/fund_etf_spot_em", timeout=60)
    data = r.json()
    print(f"  共 {len(data)} 条\n")
    return {etf['代码']: etf for etf in data}

def get_etf_names():
    """获取数据库中的ETF名称"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT code, name, aum FROM etf_names")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {'name': row[1], 'aum': row[2]} for row in rows}

# ========== 筛选逻辑 ==========

def classify_etf(code, name, amount):
    """分类ETF并判断是否适合量化策略"""
    # 排除关键词
    exclude_keywords = {
        '货币基金': ['货币', '添益', '日利', '现金', '理财'],
        '债券基金': ['债券', '企债', '国债', '政债', '地方债', '公司债'],
        'QDII海外': ['纳指', '标普', '恒生', '日经', '德国', '法国', '东南亚', '越南', '印度'],
        '商品ETF': ['黄金', '白银'],
    }
    
    for category, keywords in exclude_keywords.items():
        for kw in keywords:
            if kw in name:
                return {'category': category, 'suitable': False, 'theme': category}
    
    # 主题分类
    theme = ""
    
    # 宽基
    if any(kw in name for kw in ['沪深300', '中证500', '中证1000', '上证50', '上证180', '上证指数']):
        theme = '宽基-大盘'
    elif any(kw in name for kw in ['创业板', '科创50', '科创100', '创50', '创100', '创成长']):
        theme = '宽基-创业板/科创'
    # 行业
    elif any(kw in name for kw in ['芯片', '半导体', '集成电路']):
        theme = '行业-芯片半导体'
    elif any(kw in name for kw in ['医疗', '医药', '生物']):
        theme = '行业-医疗医药'
    elif any(kw in name for kw in ['光伏', '新能源', '能源']):
        theme = '行业-新能源'
    elif any(kw in name for kw in ['消费', '白酒']):
        theme = '行业-消费'
    elif any(kw in name for kw in ['券商', '证券']):
        theme = '行业-券商'
    elif any(kw in name for kw in ['银行']):
        theme = '行业-银行'
    elif any(kw in name for kw in ['通信', '5G']):
        theme = '行业-通信'
    elif any(kw in name for kw in ['军工']):
        theme = '行业-军工'
    elif any(kw in name for kw in ['人工智能', 'AI']):
        theme = '行业-人工智能'
    elif any(kw in name for kw in ['房地产', '地产']):
        theme = '行业-房地产'
    elif any(kw in name for kw in ['农业', '养殖', '畜牧']):
        theme = '行业-农业'
    elif any(kw in name for kw in ['化工']):
        theme = '行业-化工'
    elif any(kw in name for kw in ['有色', '稀土', '矿业']):
        theme = '行业-有色'
    elif any(kw in name for kw in ['教育']):
        theme = '行业-教育'
    elif any(kw in name for kw in ['传媒', '游戏']):
        theme = '行业-传媒游戏'
    elif any(kw in name for kw in ['港股通', '香港']):
        theme = '行业-港股'
    else:
        theme = '其他'
    
    return {'category': '宽基/行业' if theme.startswith('宽基') or theme.startswith('行业') else '其他', 
            'suitable': theme.startswith('宽基') or theme.startswith('行业'),
            'theme': theme}

def main():
    print("=" * 80)
    print("📊 ETF池筛选 - 流动性Top500版本")
    print("=" * 80)
    
    # Step 1: 获取全市场ETF
    all_etf = get_all_etf_spot()
    etf_names_db = get_etf_names()
    
    # 按成交额排序
    sorted_etf = sorted(all_etf.values(), key=lambda x: x.get('成交额', 0) or 0, reverse=True)
    
    # Step 2: 取Top500
    top500 = sorted_etf[:500]
    print(f"📈 Step 1: 流动性Top500")
    print(f"  成交额范围: {top500[-1].get('成交额', 0)/1e8:.2f}亿 ~ {top500[0].get('成交额', 0)/1e8:.2f}亿")
    
    # Step 3: 分类
    results = []
    for etf in top500:
        code = etf.get('代码', '')
        name = etf.get('名称', '')
        amount = etf.get('成交额', 0) or 0
        
        info = etf_names_db.get(code, {'name': name, 'aum': 0})
        classification = classify_etf(code, info['name'], amount)
        
        results.append({
            'code': code,
            'name': info['name'],
            'amount': amount,  # 成交额
            'aum': info['aum'],  # 规模
            'category': classification['category'],
            'theme': classification['theme'],
            'suitable': classification['suitable']
        })
    
    # Step 4: 统计
    print(f"\n📈 Step 2: 类型分类统计")
    
    categories = {}
    for r in results:
        cat = r['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)
    
    for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
        suitable = sum(1 for i in items if i['suitable'])
        print(f"  {cat}: {len(items)}只 ({suitable}✅ / {len(items)-suitable}❌)")
    
    # Step 5: 仅保留宽基+行业ETF
    broad_sector = [r for r in results if r['suitable']]
    print(f"\n📈 Step 3: 仅保留宽基+行业ETF")
    print(f"  宽基+行业ETF: {len(broad_sector)}只")
    
    # Step 6: 按主题分组
    themes = {}
    for r in broad_sector:
        theme = r['theme']
        if theme not in themes:
            themes[theme] = []
        themes[theme].append(r)
    
    print(f"\n📈 Step 4: 主题分组统计")
    for theme, items in sorted(themes.items(), key=lambda x: -len(x[1])):
        print(f"  {theme}: {len(items)}只")
    
    # Step 7: 去重（同主题保留规模最大的）
    final_pool = []
    duplicates = []
    
    print(f"\n📈 Step 5: 去重（同主题保留规模最大）")
    
    for theme, items in sorted(themes.items(), key=lambda x: -len(x[1])):
        # 按AUM排序，优先保留规模大的
        # 注意：AUM可能是None或0，需要处理
        sorted_items = sorted(items, key=lambda x: x.get('aum') or 0, reverse=True)
        
        keep = sorted_items[0]
        print(f"  【{theme}】{len(items)}只 → 保留 {keep['code']}: {keep['name']} (AUM: {keep.get('aum') or 0:.0f})")
        final_pool.append(keep)
        
        for item in sorted_items[1:]:
            duplicates.append(item)
            print(f"    ❌ 排除: {item['code']}: {item['name']}")
    
    # 输出结果
    print("\n" + "=" * 80)
    print("📋 最终结果")
    print("=" * 80)
    print(f"  原始ETF池: 1486只")
    print(f"  流动性Top500: 500只")
    print(f"  宽基+行业ETF: {len(broad_sector)}只")
    print(f"  去重后（最终）: {len(final_pool)}只")
    print(f"  排除重复: {len(duplicates)}只")
    
    print("\n【最终ETF池】")
    print(f"{'代码':<10} {'名称':<25} {'主题':<20} {'规模(亿)'}")
    print("-" * 70)
    
    for r in sorted(final_pool, key=lambda x: x['theme']):
        aum = r.get('aum') or 0
        aum_str = f"{aum/1e8:.2f}" if aum else "N/A"
        print(f"{r['code']:<10} {r['name'][:22]:<25} {r['theme']:<20} {aum_str}")
    
    # 保存结果
    final_codes = [r['code'] for r in final_pool]
    
    with open('etf_data_live/top500_etf_pool.txt', 'w') as f:
        f.write("# ETF池 - 流动性Top500筛选结果\n")
        f.write(f"# 筛选标准：排除货币基金、债券基金、QDII海外、商品ETF\n")
        f.write(f"# 仅保留宽基指数+行业ETF，同主题去重\n")
        f.write(f"# 总数: {len(final_codes)}只\n\n")
        f.write("ETF_POOL = [\n")
        for code in final_codes:
            f.write(f"    '{code}',\n")
        f.write("]\n")
    
    # 保存详细JSON
    result_json = {
        'total_etf': len(all_etf),
        'top500_count': 500,
        'broad_sector_count': len(broad_sector),
        'final_count': len(final_pool),
        'duplicates_count': len(duplicates),
        'final_pool': [{'code': r['code'], 'name': r['name'], 'theme': r['theme'], 'aum': r.get('aum') or 0} for r in final_pool],
        'duplicates': [{'code': r['code'], 'name': r['name'], 'theme': r['theme']} for r in duplicates],
        'themes': {theme: [r['code'] for r in items] for theme, items in themes.items()}
    }
    
    with open('etf_data_live/top500_etf_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存:")
    print(f"   - etf_data_live/top500_etf_pool.txt")
    print(f"   - etf_data_live/top500_etf_analysis.json")
    
    return final_pool

if __name__ == "__main__":
    main()