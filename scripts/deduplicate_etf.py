#!/usr/bin/env python3
"""ETF去重分析 - 识别性质和特征高度相似的ETF"""
import sqlite3
import json

DB_PATH = "etf_data_live/etf.db"

# 最终ETF池（37只）
ETF_POOL = [
    '159363', '159516', '159558', '159845', '159915', '159949', '159967', '159995',
    '510050', '510300', '510310', '510500', '512000', '512100', '512480', '512760',
    '512800', '513310', '515790', '516160', '588000', '588080', '588170', '588200',
    '588290', '159801', '159806', '159857', '159919', '159928', '159952', '510100',
    '510150', '510660', '512010', '512170', '512500'
]

def get_etf_info(code):
    """获取ETF详细信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, aum FROM etf_names WHERE code = ?", (code,))
    row = cursor.fetchone()
    info = {
        'code': code,
        'name': row[0] if row else '未知',
        'aum': row[1] if row else 0  # 规模
    }
    
    # 获取日线数据用于计算相关性
    cursor.execute("""
        SELECT date, close FROM daily WHERE code = ? ORDER BY date
    """, (code,))
    rows = cursor.fetchall()
    info['prices'] = {row[0]: row[1] for row in rows}
    info['count'] = len(rows)
    
    # 计算年化收益率和波动率
    if len(rows) >= 30:
        prices = [row[1] for row in rows]
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        if returns:
            import statistics
            info['avg_return'] = sum(returns) / len(returns) * 252  # 年化
            info['volatility'] = statistics.stdev(returns) * (252 ** 0.5) if len(returns) > 1 else 0
        else:
            info['avg_return'] = 0
            info['volatility'] = 0
    else:
        info['avg_return'] = 0
        info['volatility'] = 0
    
    conn.close()
    return info

def calculate_correlation(etf1, etf2):
    """计算两只ETF的价格相关性"""
    # 找出共同的日期
    common_dates = set(etf1['prices'].keys()) & set(etf2['prices'].keys())
    
    if len(common_dates) < 30:
        return None  # 数据不足
    
    prices1 = [etf1['prices'][d] for d in sorted(common_dates)]
    prices2 = [etf2['prices'][d] for d in sorted(common_dates)]
    
    # 计算收益率
    returns1 = [(prices1[i] - prices1[i-1]) / prices1[i-1] for i in range(1, len(prices1))]
    returns2 = [(prices2[i] - prices2[i-1]) / prices2[i-1] for i in range(1, len(prices2))]
    
    if len(returns1) < 30:
        return None
    
    # 计算相关系数
    import statistics
    mean1 = sum(returns1) / len(returns1)
    mean2 = sum(returns2) / len(returns2)
    
    cov = sum((r1 - mean1) * (r2 - mean2) for r1, r2 in zip(returns1, returns2)) / len(returns1)
    std1 = statistics.stdev(returns1) if len(returns1) > 1 else 1
    std2 = statistics.stdev(returns2) if len(returns2) > 1 else 1
    
    if std1 == 0 or std2 == 0:
        return None
    
    return cov / (std1 * std2)

def classify_etf_by_theme(info):
    """根据名称分类ETF主题"""
    name = info['name']
    
    # 宽基
    if any(kw in name for kw in ['沪深300', '中证500', '中证1000', '上证50', '上证180', '上证指数']):
        return '宽基-大盘'
    if any(kw in name for kw in ['创业板', '科创50', '科创100', '创50', '创100', '创成长']):
        return '宽基-创业板/科创'
    
    # 行业
    if any(kw in name for kw in ['芯片', '半导体', '集成电路']):
        return '行业-芯片半导体'
    if any(kw in name for kw in ['医疗', '医药', '生物']):
        return '行业-医疗医药'
    if any(kw in name for kw in ['光伏', '新能源', '能源']):
        return '行业-新能源'
    if any(kw in name for kw in ['消费', '白酒']):
        return '行业-消费'
    if any(kw in name for kw in ['券商', '证券']):
        return '行业-券商'
    if any(kw in name for kw in ['银行']):
        return '行业-银行'
    if any(kw in name for kw in ['通信', '5G']):
        return '行业-通信'
    if any(kw in name for kw in ['军工']):
        return '行业-军工'
    if any(kw in name for kw in ['人工智能', 'AI']):
        return '行业-人工智能'
    
    return '其他'

def main():
    print("=" * 80)
    print("📊 ETF去重分析 - 识别高度相似的ETF")
    print("=" * 80)
    
    # 获取所有ETF信息
    print("\n📡 获取ETF数据...")
    all_etfs = {}
    for code in ETF_POOL:
        info = get_etf_info(code)
        info['theme'] = classify_etf_by_theme(info)
        all_etfs[code] = info
        print(f"  {code}: {info['name'][:20]} ({info['theme']})")
    
    # 按主题分组
    themes = {}
    for code, info in all_etfs.items():
        theme = info['theme']
        if theme not in themes:
            themes[theme] = []
        themes[theme].append(code)
    
    print("\n" + "=" * 80)
    print("📋 按主题分类")
    print("=" * 80)
    
    duplicates = []  # 重复的ETF
    keep_one = []    # 每个主题保留一只
    
    for theme, codes in sorted(themes.items(), key=lambda x: -len(x[1])):
        if len(codes) == 1:
            print(f"\n【{theme}】1只 → 保留")
            print(f"  ✅ {codes[0]}: {all_etfs[codes[0]]['name']}")
            keep_one.append(codes[0])
        else:
            print(f"\n【{theme}】{len(codes)}只 → 需要去重")
            
            # 按规模排序，优先保留规模大的
            sorted_codes = sorted(codes, key=lambda c: all_etfs[c].get('aum', 0) or 0, reverse=True)
            
            # 保留最大的一只
            keep_code = sorted_codes[0]
            print(f"  ✅ 保留（规模最大）: {keep_code}: {all_etfs[keep_code]['name']} (AUM: {all_etfs[keep_code].get('aum', 0)})")
            keep_one.append(keep_code)
            
            # 标记其他为重复
            for code in sorted_codes[1:]:
                aum = all_etfs[code].get('aum', 0)
                cnt = all_etfs[code]['count']
                print(f"  ❌ 排除: {code}: {all_etfs[code]['name']} (AUM: {aum}, 数据: {cnt}条)")
                duplicates.append({
                    'code': code,
                    'name': all_etfs[code]['name'],
                    'theme': theme,
                    'aum': aum,
                    'reason': f'与{keep_code}重复'
                })
    
    # 输出结果
    print("\n" + "=" * 80)
    print("📈 去重统计")
    print("=" * 80)
    print(f"  原始ETF池: {len(ETF_POOL)}只")
    print(f"  保留: {len(keep_one)}只")
    print(f"  排除（重复）: {len(duplicates)}只")
    
    print("\n" + "=" * 80)
    print("📋 最终ETF池（去重后）")
    print("=" * 80)
    
    # 按主题分组输出
    final_pool = []
    for code in keep_one:
        info = all_etfs[code]
        theme = info['theme']
        print(f"  {code}: {info['name'][:25]} [{theme}]")
        final_pool.append(code)
    
    print(f"\n共 {len(final_pool)} 只ETF")
    
    # 保存结果
    with open('etf_data_live/deduplicated_etf_pool.txt', 'w') as f:
        f.write("# 去重后的ETF池（宽基指数 + 行业ETF）\n")
        f.write(f"# 筛选标准：\n")
        f.write(f"#   1. 排除货币基金、债券基金、QDII海外、商品ETF\n")
        f.write(f"#   2. 同一主题保留规模最大的一只\n")
        f.write(f"# 总数: {len(final_pool)}只\n\n")
        f.write("ETF_POOL = [\n")
        for code in final_pool:
            f.write(f"    '{code}',\n")
        f.write("]\n")
    
    print(f"\n✅ 已保存: etf_data_live/deduplicated_etf_pool.txt")
    
    # 输出排除的列表
    if duplicates:
        print("\n" + "=" * 80)
        print("🚫 排除的重复ETF")
        print("=" * 80)
        for d in duplicates:
            print(f"  {d['code']}: {d['name']} ({d['reason']})")

if __name__ == "__main__":
    main()