#!/usr/bin/env python3
"""数据源接口测试脚本"""
import requests
import baostock as bs

print("=" * 60)
print("ETF量化系统 - 数据源接口测试")
print("=" * 60)

# 1. 腾讯实时行情
print("\n【1】腾讯实时行情 - qt.gtimg.cn")
url = "https://qt.gtimg.cn/q=sz159919,sh510300"
r = requests.get(url, timeout=10)
for line in r.text.strip().split('\n'):
    code = line.split('~')[0].split('_')[-1]
    parts = line.split('"')[1].split('~')
    name = parts[1] if len(parts) > 1 else 'unknown'
    price = parts[3] if len(parts) > 3 else 'N/A'
    change = parts[32] if len(parts) > 32 else 'N/A'
    print(f"  {code} {name}: {price} ({change}%)")

# 2. 新浪小时线
print("\n【2】新浪小时线 - quotes.sina.cn (scale=30)")
url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sz159919&scale=30&ma=no&datalen=3"
r = requests.get(url, timeout=10)
data = r.json()
print(f"  最新3条小时线:")
for k in data[:3]:
    print(f"  {k['day']}: 开{k['open']} 高{k['high']} 低{k['low']} 收{k['close']} 量{k['volume']}")

# 3. 天天基金ETF基本信息
print("\n【3】天天基金基本信息 - fundgz.1234567.com.cn")
url = "https://fundgz.1234567.com.cn/js/159919.js?rt=1748601600"
r = requests.get(url, timeout=10)
print(f"  {r.text}")

# 4. 东方财富基金历史
print("\n【4】东方财富基金历史 - api.fund.eastmoney.com")
url = "https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode=159919&pageIndex=1&pageSize=3"
r = requests.get(url, timeout=10)
text = r.text.strip()[7:-1]  # 去掉jQuery()
import json
data = json.loads(text)
print(f"  总记录数: {data['TotalCount']}")
for item in data['Data']['LSJZList'][:3]:
    print(f"  {item['FSRQ']}: 净值{item['DWJZ']} 累计{item['LJJZ']} 涨幅{item['JZZZL']}%")

# 5. BaoStock ETF日线
print("\n【5】BaoStock ETF日线")
bs.login()
rs = bs.query_history_k_data_plus('sz.159919',
    'date,open,high,low,close,volume',
    start_date='2026-05-25', end_date='2026-05-30', frequency='d')
print(f"  字段: {rs.fields}")
while rs.error_code == '0' and rs.next():
    print(f"  {rs.get_row_data()}")
bs.logout()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)