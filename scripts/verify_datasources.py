#!/usr/bin/env python3
"""测试并整理数据源接口文档"""
import requests
import json

print("=" * 70)
print("ETF量化系统 - 数据源接口实际测试 + 网上参考")
print("=" * 70)

# 1. 腾讯实时行情
print("\n【1】腾讯实时行情 - qt.gtimg.cn")
print("-" * 50)
url = "https://qt.gtimg.cn/q=sz159919"
r = requests.get(url, timeout=10)
r.encoding = 'gbk'
parts = r.text.split('"')[1].split('~')
print(f"字段总数: {len(parts)}")
print("\n实测字段:")
fields = {
    0: "市场状态",
    1: "ETF名称",
    2: "代码",
    3: "当前价格",
    4: "昨收价",
    5: "今日最高",
    6: "成交量(股)",
    7: "外盘量",
    8: "内盘量",
    9: "现价",
    30: "数据时间",
    31: "涨跌额",
    32: "涨跌幅%",
    33: "52周最高",
    34: "52周最低",
    38: "成交量(万手)",
    44: "52周最高(另一个)",
    45: "52周最低(另一个)",
    57: "估算规模亿",
    61: "类型",
    62: "规模亿(ETF)",
    63: "估算溢价率%",
    74: "52周涨跌%",
    82: "货币单位",
}
for idx, name in fields.items():
    val = parts[idx] if idx < len(parts) else ""
    print(f"  [{idx:2d}] {name}: {val}")

# 2. 新浪小时线
print("\n【2】新浪小时线 - quotes.sina.cn")
print("-" * 50)
url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sz159919&scale=30&ma=no&datalen=3"
r = requests.get(url, timeout=10)
data = r.json()
print(f"返回格式: JSON数组")
print(f"示例数据:")
for k in data[:2]:
    print(f"  {k}")

# 3. 天天基金
print("\n【3】天天基金基本信息 - fundgz.1234567.com.cn")
print("-" * 50)
url = "https://fundgz.1234567.com.cn/js/159919.js?rt=1748601600"
r = requests.get(url, timeout=10)
print(f"返回格式: JSONP")
print(f"原始返回: {r.text}")
# 解析
import re
m = re.search(r'\((\{.*\})\)', r.text)
if m:
    data = json.loads(m.group(1))
    print(f"\n解析后字段:")
    for k, v in data.items():
        print(f"  {k}: {v}")

# 4. 东方财富基金历史
print("\n【4】东方财富基金历史净值 - api.fund.eastmoney.com")
print("-" * 50)
url = "https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode=159919&pageIndex=1&pageSize=5"
headers = {'Referer': 'https://fund.eastmoney.com/'}
r = requests.get(url, headers=headers, timeout=10)
text = r.text.strip()
if text.startswith('jQuery'):
    text = text[7:-1]
try:
    data = json.loads(text)
    print(f"总记录数: {data.get('TotalCount', 0)}")
    if data.get('Data', {}).get('LSJZList'):
        print(f"\n字段说明:")
        for item in data['Data']['LSJZList'][:2]:
            print(f"  {item}")
except:
    print(f"请求结果: {text[:200]}")

# 5. BaoStock
print("\n【5】BaoStock ETF日线")
print("-" * 50)
import baostock as bs
bs.login()
rs = bs.query_history_k_data_plus(
    'sz.159919',
    'date,open,high,low,close,volume,pchapter,pe,pcf',
    start_date='2026-05-25', end_date='2026-05-30', frequency='d'
)
print(f"字段列表: {rs.fields}")
while rs.error_code == '0' and rs.next():
    print(f"  {rs.get_row_data()}")
bs.logout()

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)