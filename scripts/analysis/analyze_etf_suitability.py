#!/usr/bin/env python3
"""分析ETF池中哪些ETF不适合量化策略"""
import sqlite3
import json
from datetime import datetime

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

def get_etf_info(db_path):
    """获取ETF基本信息"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有ETF信息
    cursor.execute("SELECT code, name, exchange, aum FROM etf_names")
    rows = cursor.fetchall()
    
    conn.close()
    
    return {row[0]: {'code': row[0], 'name': row[1], 'exchange': row[2], 'aum': row[3]} for row in rows}

def get_etf_daily_stats(db_path, etf_codes):
    """获取每只ETF的日线统计信息"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    results = {}
    
    for code in etf_codes:
        cursor.execute("""
            SELECT 
                COUNT(*) as cnt,
                MIN(date) as min_date,
                MAX(date) as max_date,
                AVG(close) as avg_close,
                MAX(high) as max_high,
                MIN(low) as min_low,
                AVG(volume) as avg_volume
            FROM daily 
            WHERE code = ?
        """, (code,))
        
        row = cursor.fetchone()
        if row and row[0] > 0:
            results[code] = {
                'count': row[0],
                'min_date': row[1],
                'max_date': row[2],
                'avg_close': row[3] or 0,
                'max_high': row[4] or 0,
                'min_low': row[5] or 0,
                'avg_volume': row[6] or 0,
                # 计算波动率（最高价/最低价）
                'volatility_ratio': (row[4] or 0) / (row[5] or 1) if row[5] and row[5] > 0 else 0
            }
        else:
            results[code] = {
                'count': 0,
                'min_date': None,
                'max_date': None,
                'avg_close': 0,
                'max_high': 0,
                'min_low': 0,
                'avg_volume': 0,
                'volatility_ratio': 0
            }
    
    conn.close()
    return results

def analyze_suitability(code, info, stats):
    """分析ETF是否适合量化策略"""
    reasons = []
    score = 100  # 满分100
    
    # 1. 没有历史数据
    if stats['count'] == 0:
        reasons.append("❌ 无历史数据")
        score -= 100
        return {'suitable': False, 'score': 0, 'reasons': reasons}
    
    # 2. 数据太少（<100条）
    if stats['count'] < 100:
        reasons.append(f"⚠️ 数据太少({stats['count']}条)，训练期不足")
        score -= 30
    
    # 3. 数据时间太短（<2年）
    if stats['min_date']:
        try:
            min_dt = datetime.strptime(stats['min_date'], '%Y-%m-%d')
            days = (datetime.now() - min_dt).days
            if days < 365:
                reasons.append(f"⚠️ 历史太短({days}天)，不足1年")
                score -= 20
            elif days < 730:
                reasons.append(f"⚠️ 历史较短({days}天)，不足2年")
                score -= 10
        except:
            pass
    
    # 4. 波动率异常（太低或太高）
    if stats['volatility_ratio'] > 0:
        if stats['volatility_ratio'] < 1.1:
            reasons.append(f"⚠️ 波动率极低({stats['volatility_ratio']:.2f})，不适合择时")
            score -= 15
        elif stats['volatility_ratio'] > 10:
            reasons.append(f"⚠️ 波动率异常高({stats['volatility_ratio']:.2f})，风险极大")
            score -= 15
    
    # 5. 平均成交量太低
    if stats['avg_volume'] < 100000:
        reasons.append(f"⚠️ 成交量偏低({stats['avg_volume']:.0f})，流动性差")
        score -= 10
    
    # 6. 平均价格太低（货币基金等）
    if info and stats['avg_close'] < 1:
        reasons.append(f"⚠️ 价格异常低({stats['avg_close']:.4f})，可能为货币基金")
        score -= 10
    
    suitable = score >= 60
    status = "✅ 适合" if suitable else "❌ 不适合"
    
    return {
        'suitable': suitable,
        'score': score,
        'reasons': reasons if reasons else ["✅ 数据质量良好"]
    }

def main():
    print("=" * 80)
    print("📊 ETF策略适用性分析")
    print("=" * 80)
    
    # 获取ETF信息
    etf_info = get_etf_info(DB_PATH)
    
    # 获取日线统计
    print("\n📡 获取日线数据统计...")
    daily_stats = get_etf_daily_stats(DB_PATH, ETF_POOL)
    print(f"  已分析 {len(daily_stats)} 只ETF\n")
    
    # 分析每只ETF
    suitable_list = []
    unsuitable_list = []
    
    for code in ETF_POOL:
        info = etf_info.get(code)
        stats = daily_stats.get(code, {})
        
        result = analyze_suitability(code, info, stats)
        
        item = {
            'code': code,
            'name': info['name'] if info else '未知',
            'exchange': info['exchange'] if info else '未知',
            'daily_count': stats.get('count', 0),
            'min_date': stats.get('min_date'),
            'max_date': stats.get('max_date'),
            'score': result['score'],
            'suitable': result['suitable'],
            'reasons': result['reasons']
        }
        
        if result['suitable']:
            suitable_list.append(item)
        else:
            unsuitable_list.append(item)
    
    # 输出不适合的ETF
    print("=" * 80)
    print(f"🚫 不适合量化策略的ETF ({len(unsuitable_list)}只)")
    print("=" * 80)
    print(f"{'代码':<10} {'名称':<20} {'数据条数':<10} {'评分':<8} {'原因'}")
    print("-" * 80)
    
    for item in sorted(unsuitable_list, key=lambda x: x['score']):
        reasons_str = ', '.join(item['reasons'])
        print(f"{item['code']:<10} {item['name']:<20} {item['daily_count']:<10} {item['score']:<8} {reasons_str[:40]}")
    
    # 输出适合的ETF
    print("\n" + "=" * 80)
    print(f"✅ 适合量化策略的ETF ({len(suitable_list)}只)")
    print("=" * 80)
    print(f"{'代码':<10} {'名称':<25} {'数据条数':<10} {'历史范围':<25} {'评分':<8}")
    print("-" * 80)
    
    for item in sorted(suitable_list, key=lambda x: -x['score']):
        date_range = f"{item['min_date']} ~ {item['max_date']}" if item['min_date'] else "无数据"
        print(f"{item['code']:<10} {item['name']:<25} {item['daily_count']:<10} {date_range:<25} {item['score']:<8}")
    
    # 统计
    print("\n" + "=" * 80)
    print("📈 统计摘要")
    print("=" * 80)
    print(f"  ETF池总数: {len(ETF_POOL)}")
    print(f"  ✅ 适合: {len(suitable_list)} ({len(suitable_list)/len(ETF_POOL)*100:.1f}%)")
    print(f"  ❌ 不适合: {len(unsuitable_list)} ({len(unsuitable_list)/len(ETF_POOL)*100:.1f}%)")
    
    # 按原因分类
    print("\n  不适合原因分布:")
    reason_counts = {}
    for item in unsuitable_list:
        for reason in item['reasons']:
            # 提取主要原因
            main_reason = reason.split('(')[0].strip()
            reason_counts[main_reason] = reason_counts.get(main_reason, 0) + 1
    
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        print(f"    - {reason}: {count}只")
    
    # 保存结果
    result = {
        'total': len(ETF_POOL),
        'suitable': len(suitable_list),
        'unsuitable': len(unsuitable_list),
        'suitable_list': [item['code'] for item in suitable_list],
        'unsuitable_list': [item['code'] for item in unsuitable_list],
        'details': suitable_list + unsuitable_list
    }
    
    with open('etf_data_live/etf_suitability_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存: etf_data_live/etf_suitability_analysis.json")
    
    return suitable_list, unsuitable_list

if __name__ == "__main__":
    main()