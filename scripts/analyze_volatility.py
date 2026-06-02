#!/usr/bin/env python3
"""分析价格波动特征 - 区分真实数据和合成数据"""
import pandas as pd
import sqlite3
import numpy as np

conn = sqlite3.connect('etf_data_live/etf.db')

print('=' * 70)
print('价格波动统计对比')
print('=' * 70)

# 真实数据
df_real = pd.read_sql('SELECT * FROM daily WHERE code="510300" ORDER BY date', conn)
real_volatility = df_real['close'].std() / df_real['close'].mean() * 100
real_range = (df_real['close'].max() - df_real['close'].min()) / df_real['close'].mean() * 100
real_change_std = df_real['close'].pct_change().std() * 100
print(f'510300(真实):')
print(f'  价格波动率(std/mean): {real_volatility:.2f}%')
print(f'  价格振幅(max-min)/mean): {real_range:.2f}%')
print(f'  日涨跌标准差: {real_change_std:.3f}%')

print()
df_fake = pd.read_csv('../etf_data_50/159611.csv')
fake_volatility = df_fake['close'].std() / df_fake['close'].mean() * 100
fake_range = (df_fake['close'].max() - df_fake['close'].min()) / df_fake['close'].mean() * 100
fake_change_std = df_fake['close'].pct_change().std() * 100
print(f'159611(合成):')
print(f'  价格波动率(std/mean): {fake_volatility:.2f}%')
print(f'  价格振幅(max-min)/mean): {fake_range:.2f}%')
print(f'  日涨跌标准差: {fake_change_std:.3f}%')

conn.close()

# 检查是否有重复价格
print()
print('=' * 70)
print('检查价格重复率')
print('=' * 70)
real_dup = (df_real['close'].diff() == 0).sum() / len(df_real) * 100
fake_dup = (df_fake['close'].diff() == 0).sum() / len(df_fake) * 100
print(f'510300(真实): 连续相同价格比例 {real_dup:.2f}%')
print(f'159611(合成): 连续相同价格比例 {fake_dup:.2f}%')