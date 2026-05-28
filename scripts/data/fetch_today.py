#!/usr/bin/env python3
"""实时行情采集 - 今日数据获取"""
import requests
import pandas as pd
import json
import os

# 腾讯实时行情API
codes = [
    'sh515050', 'sh515880', 'sh512580', 'sh510180',  # 报告TOP4
    'sz159577', 'sz159995', 'sz159981', 'sz159915',  # 报告TOP5,9,10 + 创业板
    'sh515000', 'sh516050', 'sh513100', 'sz159805',   # 报告TOP6,7,8 + 传媒
    'sh510300', 'sh510500', 'sz159919', 'sh512010',   # 沪深300, 500, 创业板, 医药
    'sz159901', 'sz159938', 'sh512660', 'sh512760',   # 纳指, 芯片设备, 军工, 芯片
    'sh516160', 'sh513500', 'sz159628', 'sh512500',   # 医疗, 纳指, 5G, 中证1000
]

url = f"https://qt.gtimg.cn/q={','.join(codes)}"

try:
    resp = requests.get(url, timeout=10)
    resp.encoding = 'gbk'
    lines = resp.text.strip().split('\n')
    
    today_data = {}
    for line in lines:
        parts = line.split('~')
        if len(parts) > 32:
            code_raw = parts[2]
            name = parts[1]
            price = float(parts[3])
            yclose = float(parts[4])
            today_pct = float(parts[32])
            
            today_data[code_raw] = {
                'name': name,
                'price': price,
                'yclose': yclose,
                'pct': today_pct,
                'date': pd.Timestamp.now().strftime('%Y-%m-%d'),
            }
    
    print(f"获取到 {len(today_data)} 只ETF的今日实时数据:")
    for code, d in sorted(today_data.items(), key=lambda x: -x[1]['pct']):
        print(f"  {code} {d['name'][:6]}: {d['price']} ({d['pct']:+.2f}%)")
    
    # 保存
    out_path = 'etf_data_live/today_realtime.json'
    with open(out_path, 'w') as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到 {out_path}")
    
except Exception as e:
    print(f"获取失败: {e}")