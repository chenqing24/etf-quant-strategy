#!/usr/bin/env python3
"""合并流动性Top60与现有ETF池，生成无重复的新列表"""
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
    existing = get_existing_etf(DB_PATH)
    daily_counts = get_daily_count(DB_PATH)
    
    print("=" * 80)
    print("📊 ETF池合并分析（去重版）")
    print("=" * 80)
    
    # 分析
    top60_in_db = [c for c in TOP60_CODES if c in existing]
    top60_not_in_db = [c for c in TOP60_CODES if c not in existing]
    
    print(f"\n📈 流动性Top60:")
    print(f"  - 数据库已有: {len(top60_in_db)} 只")
    print(f"  - 数据库无记录: {len(top60_not_in_db)} 只")
    
    print(f"\n📦 现有数据库:")
    print(f"  - 总ETF数: {len(existing)} 只")
    
    # 构建无重复的合并列表
    merged = []  # 最终列表（去重）
    seen = set()  # 已添加的代码
    
    # 1. Top60 排在前面
    print("\n" + "=" * 80)
    print("📋 新ETF池列表（Top60优先，无重复）")
    print("=" * 80)
    print(f"{'排名':<4} {'代码':<10} {'名称':<25} {'日线数据':<8}")
    print("-" * 60)
    
    rank = 1
    for code in sorted(TOP60_CODES):
        if code in seen:
            continue
        seen.add(code)
        
        name = existing[code]['name'] if code in existing else '未知'
        daily = daily_counts.get(code, 0)
        
        merged.append({'rank': rank, 'code': code, 'name': name, 'daily': daily})
        print(f"{rank:<4} {code:<10} {name:<25} {daily:<8}")
        rank += 1
    
    # 2. 补充数据库中有历史数据但不在Top60的ETF
    existing_with_data = sorted(
        [c for c in existing if c not in seen and daily_counts.get(c, 0) > 100],
        key=lambda x: daily_counts.get(x, 0),
        reverse=True
    )[:40]  # 最多补充40只
    
    for code in existing_with_data:
        if code in seen:
            continue
        seen.add(code)
        
        name = existing[code]['name']
        daily = daily_counts.get(code, 0)
        
        merged.append({'rank': rank, 'code': code, 'name': name, 'daily': daily})
        print(f"{rank:<4} {code:<10} {name:<25} {daily:<8}")
        rank += 1
    
    print("-" * 60)
    print(f"✅ 总计: {len(merged)} 只ETF（无重复）")
    
    # 验证无重复
    codes_only = [item['code'] for item in merged]
    unique_codes = set(codes_only)
    if len(codes_only) != len(unique_codes):
        print(f"\n❌ 警告：仍有 {len(codes_only) - len(unique_codes)} 个重复！")
    else:
        print(f"✅ 验证通过：无重复代码")
    
    # 统计
    top60_count = len([c for c in codes_only if c in TOP60_CODES])
    db_count = len(codes_only) - top60_count
    
    print(f"\n📊 统计:")
    print(f"  - Top60贡献: {top60_count} 只")
    print(f"  - 数据库补充: {db_count} 只")
    
    # 保存到文件
    with open('etf_data_live/merged_etf_pool.txt', 'w', encoding='utf-8') as f:
        f.write("# 合并后的ETF池（流动性Top60 + 数据库）\n")
        f.write(f"# 总数: {len(merged)} | Top60: {top60_count} | 数据库: {db_count}\n")
        f.write("# 去重验证: ✅ 无重复\n\n")
        f.write("ETF_POOL = [\n")
        for item in merged:
            f.write(f"    '{item['code']}',  # {item['name']}\n")
        f.write("]\n")
    
    print(f"\n✅ 已保存: etf_data_live/merged_etf_pool.txt")
    
    # 输出代码列表（简洁版）
    print("\n" + "=" * 80)
    print("📝 代码列表（可复制）")
    print("=" * 80)
    for i in range(0, len(codes_only), 10):
        chunk = codes_only[i:i+10]
        print("    '" + "', '".join(chunk) + "',")
    
    return merged

if __name__ == "__main__":
    main()