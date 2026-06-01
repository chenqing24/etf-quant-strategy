#!/usr/bin/env python3
"""
检查回测数据问题

用途：
    - 检查 ETF 数据质量
    - 计算技术指标（MACD 等）
    - 诊断数据问题

被谁调用：
    - 无（独立工具，一次性使用）
    - 数据调试时手动运行

功能说明：
    - 加载 ETF 池数据
    - 计算 MACD 指标
    - 检查数据范围和行数

使用方式：
    python scripts/check_data.py

依赖：
    - src.data.etf_pool_loader (ETFListLoader)
    - src.data.loader (DataLoader)

注意事项：
    - 已豁免 pre-commit 检查（一次性分析工具）
    - 用于数据调试，不执行交易
    - 可以修改 code 变量检查不同 ETF
"""
import sys
sys.path.insert(0, 'src')
import pandas as pd
from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader

loader = ETFListLoader()
etf_pool = loader.load()
etf_data = DataLoader().load(etf_pool)

code = '515050'
df = etf_data[code].copy()
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)

print(f'ETF: {code}')
print(f'数据范围: {df["date"].min()} ~ {df["date"].max()}')
print(f'总行数: {len(df)}')

# 计算MACD
ema12 = df['close'].ewm(span=12).mean()
ema26 = df['close'].ewm(span=26).mean()
df['dif'] = ema12 - ema26
df['dea'] = df['dif'].ewm(span=9).mean()
df['macd_hist'] = (df['dif'] - df['dea']) * 2

signal_count = (df['macd_hist'] > 0).sum()
print(f'MACD红柱信号数: {signal_count}/{len(df)}')
print(f'信号比例: {signal_count/len(df)*100:.1f}%')

# 检查收益率
df['return_1d'] = df['close'].pct_change()
print(f'\n收益率统计:')
print(df['return_1d'].describe())

# 假设每次MACD红柱都买入，收益累计
df['signal'] = df['macd_hist'] > 0
df['position'] = df['signal'].shift(1)
df['trade_return'] = df['return_1d'] * df['position']
print(f'\n按信号买入的收益:')
print(f'总收益: {(1 + df["trade_return"].fillna(0)).prod() - 1:.2%}')
print(f'正收益天数: {(df["trade_return"] > 0).sum()}')
print(f'负收益天数: {(df["trade_return"] < 0).sum()}')