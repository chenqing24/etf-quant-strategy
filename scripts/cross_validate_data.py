#!/usr/bin/env python3
"""
数据源交叉验证脚本
对比腾讯API、新浪API、老CSV的数据一致性
"""
import requests
import json
import csv
import sqlite3
from datetime import datetime

def get_tencent_data(code: str, days: int = 100) -> dict:
    """从腾讯API获取数据"""
    prefix = 'sz' if code.startswith('1') else 'sh'
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={prefix}{code},day,,,{days},qfq'
    try:
        resp = requests.get(url, timeout=10)
        text = resp.text.replace('kline_dayqfq=', '', 1)
        data = json.loads(text)
        key = prefix + code
        if key in data['data']:
            days_data = data['data'][key].get('qfqday') or data['data'][key].get('day', [])
            # [date, open, close, high, low, volume]
            return {d[0]: {'open': d[1], 'close': d[2], 'high': d[3], 'low': d[4], 'volume': d[5]} for d in days_data}
    except Exception as e:
        print(f"腾讯API错误: {e}")
    return {}

def get_sina_data(code: str, scale: int = 240) -> dict:
    """从新浪API获取数据（scale=240约1年）"""
    prefix = 'sh' if code.startswith('5') else 'sz'
    url = f'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={prefix}{code}&scale={scale}'
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        # [day, open, close, high, low, volume, amount]
        return {d['day']: {'open': d['open'], 'close': d['close'], 'high': d['high'], 'low': d['low'], 'volume': d['volume']} for d in data}
    except Exception as e:
        print(f"新浪API错误: {e}")
    return {}

def get_db_data(code: str) -> dict:
    """从SQLite获取数据"""
    conn = sqlite3.connect('etf_data_live/etf.db')
    cur = conn.cursor()
    cur.execute(f'SELECT date, open, high, low, close, volume FROM daily WHERE code="{code}" ORDER BY date')
    result = {r[0]: {'open': r[1], 'high': r[2], 'low': r[3], 'close': r[4], 'volume': r[5]} for r in cur.fetchall()}
    conn.close()
    return result

def get_csv_data(code: str) -> dict:
    """从etf_data_50获取CSV数据"""
    path = f'../etf_data_50/{code}.csv'
    try:
        with open(path) as f:
            reader = csv.DictReader(f)
            return {r['date']: r for r in reader}
    except FileNotFoundError:
        return {}

def compare_data(code: str, date: str):
    """对比同一日期各数据源"""
    print(f'\n{"="*70}')
    print(f'ETF: {code}, 日期: {date}')
    print(f'{"="*70}')
    
    tencent = get_tencent_data(code, 2000)
    sina = get_sina_data(code, 240)
    db = get_db_data(code)
    csv_data = get_csv_data(code)
    
    sources = {
        '腾讯API': tencent.get(date),
        '新浪API': sina.get(date),
        'etf.db': db.get(date),
        'etf_data_50': csv_data.get(date)
    }
    
    print(f'\n{"数据源":<15} {"close":>10} {"high":>10} {"low":>10}')
    print('-' * 50)
    for name, data in sources.items():
        if data:
            c = data.get('close', data.get('Close', ''))
            h = data.get('high', data.get('High', ''))
            l = data.get('low', data.get('Low', ''))
            print(f'{name:<15} {str(c):>10} {str(h):>10} {str(l):>10}')
        else:
            print(f'{name:<15} {"无数据":>10}')
    
    return sources

if __name__ == '__main__':
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else '510300'
    date = sys.argv[2] if len(sys.argv) > 2 else None
    
    compare_data(code, date)