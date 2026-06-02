#!/usr/bin/env python3
"""检测合成数据 - 检查时间间隔是否正常"""
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

def check_date_gaps(df, name):
    """检查日期间隔是否正常（应该是工作日，即1-3天）"""
    gaps = []
    for i in range(1, min(len(df), 50)):
        d1 = datetime.strptime(df.iloc[i-1]['date'], '%Y-%m-%d')
        d2 = datetime.strptime(df.iloc[i]['date'], '%Y-%m-%d')
        gap = (d2 - d1).days
        if gap > 7:  # 超过7天视为异常
            gaps.append((df.iloc[i-1]['date'], df.iloc[i]['date'], gap))
    return gaps

conn = sqlite3.connect('etf_data_live/etf.db')

print('=' * 70)
print('真实数据 510300 日期检查')
print('=' * 70)
df_real = pd.read_sql('SELECT * FROM daily WHERE code="510300" ORDER BY date', conn)
gaps = check_date_gaps(df_real, '510300')
print(f'异常间隔（>7天）数量: {len(gaps)}')
if gaps[:5]:
    for g in gaps[:5]:
        print(f'  {g[0]} -> {g[1]}: {g[2]}天')

print()
print('=' * 70)
print('合成数据 159611 日期检查')
print('=' * 70)
df_fake = pd.read_csv('../etf_data_50/159611.csv')
gaps = check_date_gaps(df_fake, '159611')
print(f'异常间隔（>7天）数量: {len(gaps)}')
if gaps[:5]:
    for g in gaps[:5]:
        print(f'  {g[0]} -> {g[1]}: {g[2]}天')

conn.close()

# 检查2022年4月的数据是否真实存在
print()
print('=' * 70)
print('验证：2022年4月159611的真实行情')
print('=' * 70)
print('真实情况下，ETF 159611在2022年4月是否存在？')
print('需要从历史数据源验证...')