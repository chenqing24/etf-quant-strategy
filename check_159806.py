#!/usr/bin/env python
"""159806 技术指标分析"""
import pandas as pd
import numpy as np

df = pd.read_csv('etf_data_live/sh159806.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)

for period in [5, 10, 20, 60, 120]:
    df['MA'+str(period)] = df['close'].rolling(period).mean()

df['EMA12'] = df['close'].ewm(span=12).mean()
df['EMA26'] = df['close'].ewm(span=26).mean()
df['DIF'] = df['EMA12'] - df['EMA26']
df['DEA'] = df['DIF'].ewm(span=9).mean()
df['MACD'] = df['DIF'] - df['DEA']
df['MACD_SIGNAL'] = (df['MACD'] > 0).astype(int)

delta = df['close'].diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)
avg_gain = gain.rolling(14).mean()
avg_loss = loss.rolling(14).mean()
df['RSI'] = 100 - (100 / (1 + avg_gain / (avg_loss + 0.001)))

df['high_distance'] = (df['close'] - df['low'].rolling(60).min()) / \
                     (df['high'].rolling(60).max() - df['low'].rolling(60).min() + 0.001) * 100
df['FISHBODY_OK'] = ((df['high_distance'] >= 30) & (df['high_distance'] <= 85)).astype(int)

df['BULLISH_ALIGN'] = ((df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])).astype(int)

df['trend_5'] = np.where(df['close'] > df['MA5'], 1, -1)
df['trend_10'] = np.where(df['MA10'] > df['MA10'].shift(5), 1, -1)
df['trend_20'] = np.where(df['MA20'] > df['MA20'].shift(10), 1, -1)
df['trend_consistency'] = (df['trend_5'] + df['trend_10'] + df['trend_20']) / 3
df['TREND_OK'] = (df['trend_consistency'] > 0).astype(int)

latest = df.iloc[-1]

print("="*70)
print("159806 技术指标分析")
print("="*70)
print("日期:", latest['date'].strftime('%Y-%m-%d'))
print("价格:", latest['close'])
print()
print("【均线】")
print("  MA5:", latest['MA5'], "  MA10:", latest['MA10'], "  MA20:", latest['MA20'])
print("  多头排列:", "YES" if latest['BULLISH_ALIGN'] else "NO")
print()
print("【MACD】", "正值" if latest['MACD_SIGNAL'] else "负值")
print("  DIF:", latest['DIF'])
print()
print("【RSI】", latest['RSI'])
print()
print("【鱼身因子】")
signal_count = latest['BULLISH_ALIGN'] + latest['MACD_SIGNAL'] + latest['FISHBODY_OK'] + int(25 <= latest['RSI'] <= 65) + latest['TREND_OK']
print("  满足条件:", signal_count, "/5")
print("  多头排列:", latest['BULLISH_ALIGN'])
print("  MACD正:", latest['MACD_SIGNAL'])
print("  鱼身位置:", latest['FISHBODY_OK'], "(距离", latest['high_distance'], "%)")
print("  RSI适中:", "YES" if 25 <= latest['RSI'] <= 65 else "NO")
print("  趋势一致:", latest['TREND_OK'])

print()
print("="*70)
print("问题诊断")
print("="*70)

if latest['MA5'] < latest['MA10']:
    print("❌ MA5 < MA10 (空头排列)")
if latest['MACD_SIGNAL'] == 0:
    print("❌ MACD为负")
if latest['RSI'] < 30:
    print("⚠️ RSI超卖:", latest['RSI'])
if not latest['FISHBODY_OK']:
    print("❌ 鱼身位置不在30-85%区间")
if not latest['TREND_OK']:
    print("❌ 趋势不一致")

print()
print("【结论】")
print("鱼身信号:", signal_count, "/5")
if signal_count >= 4:
    print("✅ 可买入")
elif signal_count >= 3:
    print("⚠️ 谨慎买入")
else:
    print("❌ 不满足买入条件")
    print()
    print("【系统为何推荐买入?】")
    print("  系统使用RSI<30作为买入信号")
    print("  但鱼身理论认为: RSI超卖 + 趋势向下 = 可能是鱼尾")
    print("  应该等趋势确认后再买入")