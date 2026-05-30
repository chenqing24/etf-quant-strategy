#!/usr/bin/env python3
"""
补充目标ETF缺失的历史行情数据
标准流程：
1. 数据采集（通过数据源获取）
2. 数据验证（格式校验）
3. 写入数据库（通过DataWriter）
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

# 添加项目路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.writer import DataWriter
from src.data.exceptions import DataValidationError

# 缺失数据的ETF
MISSING_ETFS = ['588000', '512480', '512400', '515070', '520900', '515650']


def get_prefix(code: str) -> str:
    """获取交易所前缀"""
    if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')):
        return 'sh'
    return 'sz'


def get_etf_names():
    """获取ETF名称 - 从etf_names表直接查询"""
    import sqlite3
    import os
    
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'etf_data_live',
        'etf.db'
    )
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT code, name FROM etf_names WHERE code IN ({})'.format(
        ','.join(['?' for _ in MISSING_ETFS])
    ), MISSING_ETFS)
    rows = cursor.fetchall()
    conn.close()
    
    return {row[0]: row[1] for row in rows}


def fetch_historical_from_tencent(code: str, days: int = 2000) -> list:
    """
    从腾讯API获取历史K线数据
    
    Returns:
        list: [date, open, close, high, low, volume] 格式的数据列表
    """
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


def records_to_dataframe(records: list) -> pd.DataFrame:
    """
    将腾讯API数据转换为DataFrame
    
    腾讯API格式: [date, open, close, high, low, volume]
    DataFrame格式: [date, open, high, low, close, volume]
    """
    if not records:
        return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    
    data = []
    for item in records:
        try:
            # 腾讯数据顺序: [date, open, close, high, low, volume]
            row = {
                'date': item[0],
                'open': float(item[1]) if item[1] else 0,
                'close': float(item[2]) if item[2] else 0,
                'high': float(item[3]) if item[3] else 0,
                'low': float(item[4]) if item[4] else 0,
                'volume': int(float(item[5])) if item[5] else 0,
            }
            data.append(row)
        except (IndexError, ValueError):
            continue
    
    df = pd.DataFrame(data)
    
    # 确保列顺序正确
    if not df.empty:
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    
    return df


def main():
    print("=" * 70)
    print("📥 补充目标ETF缺失的历史行情数据（标准流程）")
    print("=" * 70)
    print("流程：数据采集 → 格式转换 → DataWriter写入")
    print()
    
    # 初始化统一数据写入器
    writer = DataWriter()
    
    # 获取ETF名称
    name_map = get_etf_names()
    
    total_new = 0
    total_failed = 0
    
    for code in MISSING_ETFS:
        name = name_map.get(code, 'N/A')
        print(f"\n📊 {code} - {name}")
        
        # Step 1: 数据采集
        print(f"  [1/3] 采集数据...")
        records = fetch_historical_from_tencent(code, days=2000)
        
        if not records:
            print(f"  ❌ 获取失败")
            total_failed += 1
            continue
        
        print(f"  ✅ 获取到 {len(records)} 条原始数据")
        
        # Step 2: 格式转换
        print(f"  [2/3] 格式转换...")
        df = records_to_dataframe(records)
        
        if df.empty:
            print(f"  ❌ 转换失败")
            total_failed += 1
            continue
        
        print(f"  ✅ 转换为 DataFrame: {len(df)} 条")
        
        # Step 3: DataWriter写入
        print(f"  [3/3] 写入数据库...")
        try:
            count = writer.write_daily(code, df)
            print(f"  ✅ 新增 {count} 条数据")
            total_new += count
        except DataValidationError as e:
            print(f"  ❌ 写入失败: {e}")
            total_failed += 1
            continue
        
        time.sleep(2)  # 限速
    
    print("\n" + "=" * 70)
    print("📋 执行结果")
    print("=" * 70)
    print(f"  ✅ 新增记录: {total_new} 条")
    print(f"  ❌ 失败: {total_failed} 只ETF")
    print("=" * 70)


if __name__ == "__main__":
    main()