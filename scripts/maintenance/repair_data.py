#!/usr/bin/env python3
"""
数据修复脚本 - 从腾讯API重新获取并正确存储数据
"""
import sys
sys.path.insert(0, '.')

import sqlite3
import time
import requests
import json
from pathlib import Path

DB_PATH = 'etf_data_live/etf.db'

# 缺失的33只ETF
MISSING_ETFS = [
    '159338', '159611', '159808', '159902', '159927', '159981',
    '510010', '510030', '510100', '510150', '510180', '510210',
    '510660', '510880', '510900', '512580', '512690', '512800',
    '512980', '513050', '513080', '513120', '513330', '513360',
    '513500', '513580', '515220', '515790', '515880', '515980',
    '516110', '516120', '518600'
]

# 需要重新采集的ETF（已有但数据错误）
REPAIR_ETFS = [
    '510300', '510500', '159919', '159915', '512880', '512170', '512200',
    '159928', '159825', '512010', '512500', '159952', '159997', '159995',
    '512760', '159801', '159823', '515050', '159857', '516160', '159806',
    '159942', '510050', '512660', '159920', '159867', '518880', '159934',
    '511010', '516050', '159577', '515000', '513100'
]

def fetch_from_tencent(code: str, days: int = 2000) -> list:
    """从腾讯API获取数据（正确解析字段顺序）"""
    prefix = 'sz' if code.startswith('1') else 'sh'
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={prefix}{code},day,,,{days},qfq'
    
    try:
        resp = requests.get(url, timeout=10)
        text = resp.text.replace('kline_dayqfq=', '', 1)
        data = json.loads(text)
        
        key = prefix + code
        if key not in data.get('data', {}):
            return []
        
        days_data = data['data'][key].get('qfqday') or data['data'][key].get('day', [])
        
        # ⚠️ 正确解析：腾讯API顺序是 [date, open, close, high, low, volume]
        result = []
        for item in days_data:
            result.append({
                'date': item[0],
                'open': float(item[1]),
                'close': float(item[2]),
                'high': float(item[3]),
                'low': float(item[4]),
                'volume': float(item[5])
            })
        
        return result
        
    except Exception as e:
        print(f"  ⚠️ {code}: {e}")
        return []

def validate_data(data: list) -> bool:
    """验证数据的high/low/close关系"""
    for d in data:
        if d['high'] < d['close'] or d['high'] < d['open']:
            return False
        if d['low'] > d['close'] or d['low'] > d['open']:
            return False
    return True

def repair_db(codes: list, dry_run: bool = False):
    """修复数据库中的ETF数据"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    total = len(codes)
    success = 0
    failed = []
    
    for i, code in enumerate(codes, 1):
        print(f"[{i}/{total}] 修复 {code}...", end=' ')
        
        # 从腾讯API获取数据
        data = fetch_from_tencent(code, days=2000)
        
        if not data:
            print("❌ 获取失败")
            failed.append((code, '获取失败'))
            continue
        
        # 验证数据
        if not validate_data(data):
            print("❌ 数据验证失败")
            failed.append((code, '数据验证失败'))
            continue
        
        if dry_run:
            print(f"✅ (dry-run) {len(data)}行")
            continue
        
        # 删除旧数据
        cur.execute('DELETE FROM daily WHERE code=?', (code,))
        
        # 插入新数据
        for d in data:
            cur.execute(
                'INSERT INTO daily (code, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (code, d['date'], d['open'], d['high'], d['low'], d['close'], int(d['volume']))
            )
        
        conn.commit()
        print(f"✅ {len(data)}行")
        success += 1
        
        # 限流
        time.sleep(0.3)
    
    conn.close()
    
    print()
    print("=" * 60)
    print(f"修复完成: {success}/{total} 成功")
    if failed:
        print("失败:")
        for code, reason in failed:
            print(f"  {code}: {reason}")
    
    return success, failed

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='数据修复脚本')
    parser.add_argument('--dry-run', action='store_true', help='只测试不写入')
    parser.add_argument('--missing', action='store_true', help='只修复缺失的33只')
    parser.add_argument('--repair', action='store_true', help='只修复已有但错误的33只')
    
    args = parser.parse_args()
    
    if args.missing:
        codes = MISSING_ETFS
        print(f"将修复 {len(codes)} 只缺失ETF")
    elif args.repair:
        codes = REPAIR_ETFS
        print(f"将重新采集 {len(codes)} 只ETF")
    else:
        codes = MISSING_ETFS + REPAIR_ETFS
        print(f"将修复全部 {len(codes)} 只ETF")
    
    print()
    success, failed = repair_db(codes, dry_run=args.dry_run)
    
    if not args.dry_run and success > 0:
        print()
        # 验证结果
        conn = sqlite3.connect(DB_PATH)
        total_rows = conn.execute('SELECT COUNT(*) FROM daily').fetchone()[0]
        total_codes = conn.execute('SELECT COUNT(DISTINCT code) FROM daily').fetchone()[0]
        conn.close()
        print(f"数据库现状: {total_rows}行, {total_codes}只ETF")