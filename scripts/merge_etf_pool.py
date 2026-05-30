#!/usr/bin/env python3
"""合并流动性Top60与现有ETF池，生成新ETF列表"""
import sqlite3
import json

DB_PATH = "etf_data_live/etf.db"

# 流动性Top60 ETF代码
TOP60_CODES = {
    '511880', '511990', '513090', '588000', '513120', '588200', '159915',
    '513310', '513130', '515880', '512100', '563360', '513180', '159338',
    '159361', '159570', '159949', '159792', '159352', '518880', '510300',
    '588080', '159516', '513330', '512880', '510500', '588170', '159206',
    '512480', '513050', '159131', '512050', '159941', '159845', '159217',
    '510050', '510310', '512690', '159740', '159567', '513010', '159363',
    '520500', '159529', '159995', '159967', '159326', '159611', '159530',
    '512000', '562500', '159316', '515050', '159509', '513100', '159870',
    '588220', '512400', '159558', '588290'
}

def get_existing_etf(db_path):
    """获取数据库中已存在的ETF"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT code, name, exchange, aum FROM etf_names ORDER BY code")
    rows = cursor.fetchall()
    
    conn.close()
    
    return {row[0]: {'code': row[0], 'name': row[1], 'exchange': row[2], 'aum': row[3]} for row in rows}

def get_daily_count(db_path):
    """获取每只ETF的日线数据条数"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT code, COUNT(*) as cnt FROM daily GROUP BY code ORDER BY cnt DESC")
    rows = cursor.fetchall()
    
    conn.close()
    
    return {row[0]: row[1] for row in rows}

def main():
    # 获取现有ETF
    existing = get_existing_etf(DB_PATH)
    daily_counts = get_daily_count(DB_PATH)
    
    print("=" * 80)
    print("📊 ETF池合并分析")
    print("=" * 80)
    
    # 分析Top60与现有的关系
    in_both = []      # 既在Top60又在数据库中
    only_top60 = []    # 只在Top60中
    only_existing = [] # 只在数据库中
    
    for code in TOP60_CODES:
        if code in existing:
            in_both.append(code)
        else:
            only_top60.append(code)
    
    # 统计有日线数据的
    in_both_with_data = [c for c in in_both if daily_counts.get(c, 0) > 0]
    only_top60_with_data = [c for c in only_top60 if daily_counts.get(c, 0) > 0]
    
    print(f"\n📈 流动性Top60分析:")
    print(f"  - 与现有数据库重叠: {len(in_both)} 只")
    print(f"    - 其中有日线数据: {len(in_both_with_data)} 只")
    print(f"  - 新增（数据库无记录）: {len(only_top60)} 只")
    print(f"    - 其中有日线数据: {len(only_top60_with_data)} 只")
    
    print(f"\n📦 现有数据库:")
    print(f"  - 总ETF数: {len(existing)} 只")
    print(f"  - 有日线数据: {sum(1 for c in existing if daily_counts.get(c, 0) > 0)} 只")
    
    # 合并Top60 + 有数据的现有ETF
    merged_codes = set(in_both) | set(only_top60) | {c for c in existing if daily_counts.get(c, 0) > 100}
    
    print(f"\n🆕 合并后ETF池:")
    print(f"  - 总数: {len(merged_codes)} 只")
    
    # 生成新列表
    print("\n" + "=" * 80)
    print("📋 新ETF池列表（按流动性排序）")
    print("=" * 80)
    print(f"{'排名':<4} {'代码':<10} {'名称':<25} {'来源':<12} {'日线数据':<10}")
    print("-" * 80)
    
    # 按Top60优先，再按数据库顺序
    ranked_list = []
    
    # Top60排在前面
    for code in TOP60_CODES:
        if code in existing:
            etf = existing[code]
            ranked_list.append({
                'rank': len(ranked_list) + 1,
                'code': code,
                'name': etf['name'],
                'source': 'Top60+DB',
                'daily_count': daily_counts.get(code, 0)
            })
        else:
            ranked_list.append({
                'rank': len(ranked_list) + 1,
                'code': code,
                'name': '新增ETF',
                'source': 'Top60新增',
                'daily_count': 0
            })
    
    # 补充数据库中其他有数据的ETF
    existing_codes_sorted = sorted(
        [c for c in existing if c not in TOP60_CODES and daily_counts.get(c, 0) > 100],
        key=lambda x: daily_counts.get(x, 0),
        reverse=True
    )[:40]  # 最多补充40只
    
    for code in existing_codes_sorted:
        etf = existing[code]
        ranked_list.append({
            'rank': len(ranked_list) + 1,
            'code': code,
            'name': etf['name'],
            'source': 'DB补充',
            'daily_count': daily_counts.get(code, 0)
        })
    
    # 输出
    for item in ranked_list:
        print(f"{item['rank']:<4} {item['code']:<10} {item['name']:<25} {item['source']:<12} {item['daily_count']:<10}")
    
    print("-" * 80)
    print(f"总计: {len(ranked_list)} 只ETF")
    
    # 生成代码列表（用于配置文件）
    all_codes = [item['code'] for item in ranked_list]
    
    print("\n" + "=" * 80)
    print("📝 ETF代码列表（可直接复制到配置）")
    print("=" * 80)
    
    # 按每行10个分组
    for i in range(0, len(all_codes), 10):
        chunk = all_codes[i:i+10]
        print("    '" + "', '".join(chunk) + "',")
    
    # 保存到文件
    output = {
        'total': len(ranked_list),
        'from_top60': len(TOP60_CODES),
        'from_existing': len(existing_codes_sorted),
        'etf_list': ranked_list,
        'codes': all_codes
    }
    
    with open('etf_data_live/merged_etf_pool.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存到: etf_data_live/merged_etf_pool.json")
    
    # 保存为Python列表格式
    with open('etf_data_live/merged_etf_pool.txt', 'w', encoding='utf-8') as f:
        f.write("# 合并后的ETF池（流动性Top60 + 数据库）\n")
        f.write(f"# 总数: {len(all_codes)}\n\n")
        f.write("ETF_POOL = [\n")
        for code in all_codes:
            f.write(f"    '{code}',\n")
        f.write("]\n")
    
    print(f"✅ 已保存到: etf_data_live/merged_etf_pool.txt")
    
    return ranked_list

if __name__ == "__main__":
    main()