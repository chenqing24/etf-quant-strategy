#!/usr/bin/env python
"""检查159806评分详情"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from src.core.selector import Selector
from src.analysis.indicator import Indicator

# 加载数据
df = pd.read_csv('etf_data_live/sh159806.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)

# 计算指标
indicator = Indicator()
df = indicator.calculate(df)

# 最新日期
latest_date = df['date'].max().strftime('%Y-%m-%d')
print("最新日期:", latest_date)

# 评分
selector = Selector()
score, reasons = selector.evaluate(df, latest_date)

print()
print("="*70)
print("159806 评分详情")
print("="*70)
print("总分:", score)
print("理由:", reasons)

# 检查各因子
row = df[df['date'] == latest_date].iloc[0]

print()
print("【各因子检查】")
print("1. 站上MA120:", row['close'] > row['ma120'] if not pd.isna(row.get('ma120')) else "N/A")
print("2. MA60向上:", end=" ")
recent = df[df['date'] <= latest_date].tail(5)
if len(recent) >= 5 and not pd.isna(recent['ma60'].iloc[-1]) and not pd.isna(recent['ma60'].iloc[0]):
    ma60_up = recent['ma60'].iloc[-1] > recent['ma60'].iloc[0]
    print(ma60_up)
else:
    print("N/A")

print("3. 站上MA60:", row['close'] > row['ma60'] if not pd.isna(row.get('ma60')) else "N/A")
print("4. 站上MA20:", row['close'] > row['ma20'] if not pd.isna(row.get('ma20')) else "N/A")
print("5. 放量:", row.get('vol_ratio', 0))
print("6. RSI:", row.get('rsi_14', 'N/A'))

# RSI超卖检查
if not pd.isna(row.get('rsi_14')) and row['rsi_14'] < 30:
    print()
    print("⚠️ RSI超卖检查")
    ma20_up = False
    if len(recent) >= 5 and not pd.isna(recent['ma20'].iloc[-1]) and not pd.isna(recent['ma20'].iloc[0]):
        ma20_up = recent['ma20'].iloc[-1] > recent['ma20'].iloc[0]
    print("  MA20向上:", ma20_up)
    print("  RSI超卖需要MA20向上确认才能得分")
    print("  结论:", "✅ RSI得分有效" if ma20_up else "❌ RSI不得分(防止接飞刀)")

print()
print("="*70)
print("问题总结")
print("="*70)
print("159806得分:", score)
print("RSI:", row.get('rsi_14'))
print()
print("【为什么系统推荐了159806?】")
print("  系统有7个因子评分，RSI只是其中之一")
print("  即使RSI不得分，其他因子可能已经够6分")
print()
print("【鱼身理论的批评】")
print("  鱼身理论认为：RSI超卖时，趋势必须向上才能买入")
print("  当前系统在RSI超卖时不加分，但没有强制排除")
print("  导致：在下降趋势中仍然推荐了RSI超卖的ETF")