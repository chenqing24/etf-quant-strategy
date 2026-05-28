#!/usr/bin/env python3
"""对比真实数据和合成数据"""
import pandas as pd
import sqlite3

print('=' * 70)
print('真实数据示例（etf.db中的510300）')
print('=' * 70)
conn = sqlite3.connect('etf_data_live/etf.db')
df_real = pd.read_sql('SELECT * FROM daily WHERE code="510300" ORDER BY date', conn)
print(df_real[['date','close','volume']].head(20).to_string(index=False))
conn.close()

print()
print('=' * 70)
print('合成数据示例（159611.csv - 1000行整）')
print('=' * 70)
df_fake = pd.read_csv('../etf_data_50/159611.csv')
print(df_fake[['date','close','volume']].head(20).to_string(index=False))