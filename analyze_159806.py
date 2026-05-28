import pandas as pd

# 加载数据
df = pd.read_csv('etf_data_live/sh159806.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').tail(20).reset_index(drop=True)

print('='*70)
print('📊 159806 新能源车 最近20日技术指标分析')
print('='*70)

# 计算各指标
df['MA5'] = df['close'].rolling(5).mean()
df['MA10'] = df['close'].rolling(10).mean()
df['EMA12'] = df['close'].ewm(span=12).mean()
df['EMA26'] = df['close'].ewm(span=26).mean()
df['DIF'] = df['EMA12'] - df['EMA26']
df['DEA'] = df['DIF'].ewm(span=9).mean()
df['MACD'] = (df['DIF'] - df['DEA']) * 2
df['DMA_diff'] = df['DIF'] - df['DEA']

obv_change = df['close'].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
df['OBV'] = (obv_change * df['volume']).cumsum()

delta = df['close'].diff()
gain = delta.apply(lambda x: x if x > 0 else 0)
loss = delta.apply(lambda x: -x if x < 0 else 0)
avg_gain = gain.rolling(14).mean()
avg_loss = loss.rolling(14).mean()
rs = avg_gain / avg_loss
df['RSI14'] = 100 - (100 / (1 + rs))

print()
print('【最新5日数据】')
print('-'*70)
for i in range(-5, 0):
    row = df.iloc[i]
    date = row['date'].strftime('%m-%d')
    close = row['close']
    macd = '▼' if row['MACD'] < 0 else '▲'
    dma = '▼' if row['DMA_diff'] < 0 else '▲'
    print(f"{date} 收:{close:.3f} | MACD:{macd}{row['MACD']:.5f} | DMA:{dma}{row['DMA_diff']:.5f} | OBV:{row['OBV']:,.0f} | RSI14:{row['RSI14']:.1f}")

print()
print('='*70)
print('📌 矛盾分析')
print('='*70)

latest = df.iloc[-1]
high = df['close'].max()
low = df['close'].min()

print()
print('【核心矛盾】')
print('-'*70)
print('用户观察: DMA向下 MACD向下 OBV流出 价格下跌')
print('系统推荐: 买入 159806')
print()
print('矛盾原因分析:')
print('1. 7因子模型使用【短期技术指标】(ADX/RSI/BB_percent)')
print('   - 短期指标对中长期趋势不敏感')
print('   - 下跌趋势中也有反弹机会')
print()
print('2. 选股逻辑是【动量反转】而非【趋势跟踪】')
print('   - 下跌到超卖区域 -> 可能反弹 -> 买入信号')
print('   - 但用户理解为趋势跟踪 -> 应该等待底部确认')
print()
print('3. 因子权重问题')
print('   - 当前权重: ADX=0.4, BB_percent=0.3, SAR_trend=0.2, OBV_diff=0.1')
print('   - ADX高权重可能放大短期波动影响')
print()
print('4. 缺少【趋势确认】过滤条件')
print('   - 没有要求DMA/MACD都向上才买入')
print('   - 只看短期超跌，可能买在半山腰')
print()
print('='*70)
print('📌 结论')
print('='*70)
print('- 矛盾是设计理念差异: 动量反转 vs 趋势确认')
print('- 建议: 增加趋势过滤条件，避免在下降趋势中抄底')
print('- 可以在P0-1/P0-2基础上增加P1: 趋势确认模块')