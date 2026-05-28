"""
策略深度复盘：只吃鱼身原则
从第一性原理出发，多维度分析现有策略问题
"""
import pandas as pd
import numpy as np

print("="*70)
print("🐟 策略深度复盘：只吃鱼身原则")
print("="*70)

# ===== 第一维度：趋势阶段识别 =====
print()
print("="*70)
print("📊 第一维度：趋势阶段识别")
print("="*70)

df = pd.read_csv('etf_data_live/sh159806.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date')

# 计算指标
df['MA20'] = df['close'].rolling(20).mean()
df['MA60'] = df['close'].rolling(60).mean()

# 计算当前在近期高低点的位置
recent = df.tail(60).copy()
current_price = recent['close'].iloc[-1]
recent_high = recent['high'].max()
recent_low = recent['low'].min()

if recent_high > recent_low:
    position_ratio = (current_price - recent_low) / (recent_high - recent_low) * 100
else:
    position_ratio = 50

print(f"当前价格: {current_price:.3f}")
print(f"60日最高: {recent_high:.3f}")
print(f"60日最低: {recent_low:.3f}")
print(f"当前位置: {position_ratio:.1f}% (0%=低点, 100%=高点)")

print()
print("【趋势阶段判断】")
if position_ratio < 20:
    phase = "接近底部 (可能是鱼尾末端)"
    quality = "❌ 不宜买入"
elif position_ratio < 40:
    phase = "中下位置 (可能是鱼身起点)"
    quality = "✅ 可以考虑"
elif position_ratio < 60:
    phase = "中间位置 (鱼身中部)"
    quality = "✅ 最佳买入区间"
elif position_ratio < 80:
    phase = "中上位置 (鱼身末端)"
    quality = "⚠️ 谨慎买入"
else:
    phase = "接近顶部 (鱼尾)"
    quality = "❌ 不宜买入"

print(f"  阶段: {phase}")
print(f"  建议: {quality}")

# ===== 第二维度：多周期趋势一致性 =====
print()
print("="*70)
print("📊 第二维度：多周期趋势一致性")
print("="*70)

# 计算各周期均线
ma5 = df['close'].rolling(5).mean()
ma10 = df['close'].rolling(10).mean()
ma20 = df['close'].rolling(20).mean()

# 计算EMA和MACD
df['EMA12'] = df['close'].ewm(span=12).mean()
df['EMA26'] = df['close'].ewm(span=26).mean()
df['DIF'] = df['EMA12'] - df['EMA26']
df['DEA'] = df['DIF'].ewm(span=9).mean()
df['MACD'] = df['DIF'] - df['DEA']

# 获取最近数据
latest = df.iloc[-1]
ma5_val = ma5.iloc[-1]
ma10_val = ma10.iloc[-1]
ma20_val = ma20.iloc[-1]

print(f"短期(MA5): {latest['close']:.3f} {'>' if latest['close'] > ma5_val else '<'} {ma5_val:.3f}")
print(f"中期(MA10): {ma10_val:.3f} {'↑' if ma10_val > ma10.iloc[-5] else '↓'}")
print(f"长期(MA20): {ma20_val:.3f} {'↑' if ma20_val > ma20.iloc[-10] else '↓'}")

# 多周期趋势
short = 1 if latest['close'] > ma5_val else -1
mid = 1 if ma10_val > ma10.iloc[-5] else -1
long = 1 if ma20_val > ma20.iloc[-10] else -1

print()
print("【趋势一致性评分】")
trend_score = (short + mid + long) / 3  # -1到1之间
if trend_score > 0.5:
    print(f"  综合评分: {trend_score:.2f} (满1) = 多周期向上 = 鱼身概率高")
elif trend_score < -0.5:
    print(f"  综合评分: {trend_score:.2f} (满1) = 多周期向下 = 鱼尾概率高")
else:
    print(f"  综合评分: {trend_score:.2f} (满1) = 方向不明")

# ===== 第三维度：动量指标 =====
print()
print("="*70)
print("📊 第三维度：动量指标分析")
print("="*70)

print(f"MACD柱: {latest['MACD']:.5f} {'▲' if latest['MACD'] > 0 else '▼'}")
print(f"DIF: {latest['DIF']:.5f}")
print(f"DEA: {latest['DEA']:.5f}")

# 计算RSI
delta = df['close'].diff()
gain = delta.apply(lambda x: x if x > 0 else 0)
loss = delta.apply(lambda x: -x if x < 0 else 0)
avg_gain = gain.rolling(14).mean()
avg_loss = loss.rolling(14).mean()
rs = avg_gain / avg_loss
df['RSI14'] = 100 - (100 / (1 + rs))

latest_rsi = df['RSI14'].iloc[-1]
print(f"RSI14: {latest_rsi:.1f} ({'超卖' if latest_rsi < 30 else '超买' if latest_rsi > 70 else '中性'})")

# ===== 第四维度：成交量验证 =====
print()
print("="*70)
print("📊 第四维度：成交量验证")
print("="*70)

vol_ma5 = df['volume'].rolling(5).mean().iloc[-1]
vol_now = latest['volume']
vol_ratio = vol_now / vol_ma5 if vol_ma5 > 0 else 1

print(f"5日均量: {vol_ma5:,.0f}")
print(f"今日量: {vol_now:,.0f}")
print(f"量比: {vol_ratio:.2f}x")

if vol_ratio > 1.5:
    vol_verdict = "放量: 有资金关注"
elif vol_ratio > 0.8:
    vol_verdict = "正常量"
else:
    vol_verdict = "缩量: 观望情绪"

print(f"  结论: {vol_verdict}")

# ===== 第五维度：大盘环境 =====
print()
print("="*70)
print("📊 第五维度：大盘环境")
print("="*70)

try:
    df_300 = pd.read_csv('etf_data_live/sh510300.csv')
    df_300['date'] = pd.to_datetime(df_300['date'])
    df_300 = df_300.sort_values('date')
    
    ma5_300 = df_300['close'].rolling(5).mean().iloc[-1]
    ma20_300 = df_300['close'].rolling(20).mean().iloc[-1]
    close_300 = df_300['close'].iloc[-1]
    
    print(f"沪深300: {close_300:.3f}")
    print(f"MA5: {ma5_300:.3f}, MA20: {ma20_300:.3f}")
    
    if close_300 > ma5_300 > ma20_300:
        market = "强势上涨"
        market_score = 1
    elif close_300 > ma20_300:
        market = "震荡偏强"
        market_score = 0.5
    elif close_300 < ma5_300 < ma20_300:
        market = "弱势下跌"
        market_score = -1
    else:
        market = "震荡偏弱"
        market_score = -0.5
    
    print(f"  大盘: {market}")
except Exception as e:
    print(f"  大盘数据不可用: {e}")
    market_score = 0

# ===== 综合评分 =====
print()
print("="*70)
print("📊 综合评分：159806买入决策")
print("="*70)

# 计算各维度分数
position_score = 1 if 40 <= position_ratio <= 60 else 0.5 if 20 <= position_ratio <= 80 else 0
trend_score_adj = (trend_score + 1) / 2  # 转换为0-1
rsi_score = 1 if 30 <= latest_rsi <= 50 else 0.5 if latest_rsi < 30 else 0.3
vol_score = 1 if 1 <= vol_ratio <= 2 else 0.7 if vol_ratio > 0.5 else 0.4

# MACD方向评分
macd_score = 1 if latest['MACD'] > 0 else 0.3  # MACD向上=1，向下=0.3

total_score = (
    position_score * 0.25 +   # 位置25%
    trend_score_adj * 0.25 +   # 趋势25%
    macd_score * 0.15 +        # MACD方向15%
    rsi_score * 0.15 +        # RSI15%
    vol_score * 0.10 +        # 成交量10%
    (market_score + 1) / 2 * 0.10  # 大盘10%
)

print()
print("【各维度权重得分】")
print(f"  趋势位置 (25%): {position_score:.1f} - {'鱼身区间' if position_score > 0.5 else '非最佳位置'}")
print(f"  多周期趋势 (25%): {trend_score_adj:.1f} - {'向上' if trend_score_adj > 0.5 else '向下'}")
print(f"  MACD方向 (15%): {macd_score:.1f} - {'向上' if macd_score > 0.5 else '向下'}")
print(f"  RSI指标 (15%): {rsi_score:.1f} - {'合理' if rsi_score > 0.5 else '超买/超卖'}")
print(f"  成交量 (10%): {vol_score:.1f} - {vol_verdict}")
print(f"  大盘环境 (10%): {(market_score + 1) / 2:.1f} - {market}")
print()
print(f"  综合得分: {total_score:.2f} / 1.00")

print()
print("【最终建议】")
if total_score > 0.7:
    print("  ✅ 强烈建议买入")
elif total_score > 0.5:
    print("  ⚠️ 可以考虑买入")
elif total_score > 0.3:
    print("  ❌ 暂不买入，等待信号")
else:
    print("  ❌ 不建议买入")

print()
print("="*70)
print("📌 问题诊断")
print("="*70)
print()
print("【当前策略问题】")
print("  1. 缺少趋势位置判断 → 可能在鱼尾买入")
print("  2. 缺少多周期确认 → 可能在下跌中抄底")
print("  3. RSI超卖信号过于敏感 → 可能误判反弹时机")
print("  4. 缺少大盘过滤 → 系统性风险未考虑")
print()
print("【159806具体问题】")
print(f"  - 当前位置: {position_ratio:.1f}% (偏高)")
print(f"  - 趋势方向: {'向下' if trend_score < 0 else '向上'}")
print(f"  - MACD: {'向下' if latest['MACD'] < 0 else '向上'}")
print(f"  - RSI: {latest_rsi:.1f} (超卖但可能继续跌)")
print()
print("="*70)