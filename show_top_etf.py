#!/usr/bin/env python3
"""显示流动性最高的ETF（前60名）"""
import requests

# 获取全市场ETF实时行情
print("📡 获取 ETF 实时行情...")
r = requests.get("http://127.0.0.1:8080/api/public/fund_etf_spot_em", timeout=60)
data = r.json()
print(f"  共 {len(data)} 条\n")

# 按成交额排序，取前60
sorted_data = sorted(data, key=lambda x: x.get('成交额', 0) or 0, reverse=True)[:60]

# 格式化输出
print("=" * 90)
print(f"{'排名':<4} {'代码':<10} {'名称':<22} {'最新价':<10} {'涨跌幅':<10} {'成交额(亿)':<12} {'换手率':<8}")
print("=" * 90)

total_amount = 0
for i, etf in enumerate(sorted_data, 1):
    code = etf.get('代码', '')
    name = etf.get('名称', '')[:20]
    price = etf.get('最新价', 0)
    change_pct = etf.get('涨跌幅', 0)
    amount = etf.get('成交额', 0) or 0
    turnover = etf.get('换手率', 0) or 0
    amount_yi = amount / 1e8  # 转换为亿
    
    total_amount += amount
    
    # 涨跌幅颜色（文本表示）
    if change_pct > 0:
        pct_str = f"+{change_pct:.2f}%"
    elif change_pct < 0:
        pct_str = f"{change_pct:.2f}%"
    else:
        pct_str = "0.00%"
    
    print(f"{i:<4} {code:<10} {name:<22} {price:<10.4f} {pct_str:<10} {amount_yi:<12.2f} {turnover:<8.2f}%")

print("=" * 90)
print(f"\n📊 前60名ETF成交额合计: {total_amount/1e8:.2f} 亿元")
print(f"   占全市场 {total_amount/sum(e.get('成交额',0) for e in data)*100:.1f}%")