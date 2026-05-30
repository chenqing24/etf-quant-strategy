#!/usr/bin/env python3
"""
补充目标ETF缺失的历史行情数据 - 腾讯API v2
"""
import json
import sqlite3
import time
import requests

DB_PATH = "etf_data_live/etf.db"

# 缺失数据的ETF
MISSING_ETFS = ['588000', '512480', '512400', '515070', '520900', '515650']

def get_prefix(code: str) -> str:
    """获取交易所前缀"""
    if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')):
        return 'sh'
    return 'sz'

def get_etf_names():
    """获取ETF名称"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT code, name FROM etf_names')
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def get_existing_dates(code):
    """获取已存在的日期范围"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT MIN(date), MAX(date), COUNT(*) FROM daily WHERE code=?', (code,))
    result = cursor.fetchone()
    conn.close()
    return result

def fetch_historical_from_tencent(code: str, days: int = 2000) -> list:
    """从腾讯API获取历史K线数据"""
    prefix = get_prefix(code)
    full_code = f"{prefix}{code}"
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {
        '_var': 'kline_dayqfq',
        'param': f'{full_code},day,,,{days},qfq'
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        text = r.text.replace('kline_dayqfq=', '', 1)
        data = json.loads(text)
        
        etf_data = data.get('data', {}).get(full_code, {})
        
        # 优先取复权数据
        for field in ['qfqday', 'day']:
            records = etf_data.get(field)
            if records:
                return records
        
        return []
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return []

def save_to_db(code, records):
    """保存数据到数据库"""
    if not records:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    count = 0
    for item in records:
        # 腾讯API数组顺序: [date, open, close, high, low, volume]
        try:
            date = item[0]
            open_price = float(item[1]) if item[1] else 0
            close_price = float(item[2]) if item[2] else 0
            high_price = float(item[3]) if item[3] else 0
            low_price = float(item[4]) if item[4] else 0
            volume = int(float(item[5])) if item[5] else 0
            
            # 检查是否已存在
            cursor.execute('SELECT COUNT(*) FROM daily WHERE code=? AND date=?', (code, date))
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO daily (code, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (code, date, open_price, high_price, low_price, close_price, volume))
                count += 1
        except Exception as e:
            print(f"  ⚠️ 解析错误: {e}")
            continue
    
    conn.commit()
    conn.close()
    return count

def main():
    print("=" * 70)
    print("📥 补充目标ETF缺失的历史行情数据")
    print("=" * 70)
    
    name_map = get_etf_names()
    
    total_new = 0
    
    for code in MISSING_ETFS:
        name = name_map.get(code, 'N/A')
        print(f"\n📊 {code} - {name}")
        
        # 检查现有数据
        existing = get_existing_dates(code)
        if existing[2] and existing[2] > 0:
            print(f"  已有数据: {existing[0]} ~ {existing[1]} ({existing[2]}条)")
            continue
        
        print(f"  无历史数据，正在获取...")
        
        # 获取历史数据（2000天约8年）
        records = fetch_historical_from_tencent(code, days=2000)
        
        if records and len(records) > 0:
            print(f"  获取到 {len(records)} 条原始数据")
            
            # 保存到数据库
            count = save_to_db(code, records)
            print(f"  ✅ 新增 {count} 条数据")
            total_new += count
            
            # 验证
            new_range = get_existing_dates(code)
            if new_range[2]:
                print(f"  📅 日期范围: {new_range[0]} ~ {new_range[1]} ({new_range[2]}条)")
            else:
                print(f"  ⚠️ 数据验证失败")
        else:
            print(f"  ❌ 获取失败（可能ETF代码不正确或已退市）")
        
        time.sleep(2)  # 限速
    
    print("\n" + "=" * 70)
    print(f"✅ 数据补充完成，共新增 {total_new} 条数据")
    print("=" * 70)

if __name__ == "__main__":
    main()