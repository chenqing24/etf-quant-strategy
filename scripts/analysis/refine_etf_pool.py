#!/usr/bin/env python3
"""ETF池分析 - 基于名称排除货币基金"""
import sqlite3

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

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 获取ETF信息
results = []
for code in ETF_POOL:
    cursor.execute("SELECT name FROM etf_names WHERE code = ?", (code,))
    row = cursor.fetchone()
    name = row[0] if row else '未知'
    
    cursor.execute("""
        SELECT AVG(close) as avg_price, COUNT(*) as cnt 
        FROM daily WHERE code = ?
    """, (code,))
    row = cursor.fetchone()
    
    results.append({
        'code': code,
        'name': name,
        'avg_price': row[0] or 0,
        'daily_count': row[1] or 0
    })

conn.close()

# 分类 - 基于名称排除货币基金
EXCLUDE_KEYWORDS = ['货币', '添益', '日利', '现金', '理财']

unsuitable = []
suitable = []

for r in results:
    is_money_fund = False
    exclude_reason = ""
    
    # 检查名称是否包含排除关键词
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in r['name']:
            is_money_fund = True
            exclude_reason = f"货币基金(含'{keyword}')"
            break
    
    # 检查平均价格（货币基金通常接近100）
    if not is_money_fund and r['avg_price'] > 99.5 and r['avg_price'] < 100.5:
        # 价格接近100，更可能是货币基金
        if r['daily_count'] > 0:
            is_money_fund = True
            exclude_reason = "价格约100元，可能为货币基金"
    
    if is_money_fund:
        r['reason'] = exclude_reason
        unsuitable.append(r)
    else:
        r['reason'] = ""
        suitable.append(r)

# 输出
print("=" * 70)
print("📊 ETF池分析结果（基于策略因子挖掘经验）")
print("=" * 70)

print(f"\n🚫 不适合的ETF ({len(unsuitable)}只):")
if unsuitable:
    for r in unsuitable:
        print(f"   {r['code']}: {r['name']} - {r['reason']}")
else:
    print("   无")

print(f"\n✅ 适合的ETF ({len(suitable)}只):")
print("   包括：股票型、债券型、商品型（黄金）、跨境ETF、QDII等")

# 输出最终代码
print("\n" + "=" * 70)
print("📋 最终ETF池代码列表")
print("=" * 70)
final_codes = [r['code'] for r in suitable]
print(f"共 {len(final_codes)} 只\n")

for i in range(0, len(final_codes), 15):
    chunk = final_codes[i:i+15]
    print("    " + ", ".join(chunk))

# 保存
with open('etf_data_live/final_etf_pool.txt', 'w') as f:
    f.write(f"# 最终ETF池（适合量化策略）\n")
    f.write(f"# 总数: {len(final_codes)}只\n")
    if unsuitable:
        f.write(f"# 排除: {len(unsuitable)}只货币基金\n")
        for r in unsuitable:
            f.write(f"#   - {r['code']}: {r['name']} ({r['reason']})\n")
    f.write("\nETF_POOL = [\n")
    for code in final_codes:
        f.write(f"    '{code}',\n")
    f.write("]\n")

print(f"\n✅ 已保存: etf_data_live/final_etf_pool.txt")
print(f"\n📈 统计:")
print(f"   - ETF池总数: {len(ETF_POOL)}")
print(f"   - 货币基金: {len(unsuitable)}只（排除）")
print(f"   - 有效ETF: {len(suitable)}只（保留）")