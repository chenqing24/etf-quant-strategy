# ETF量化策略方案详解

## 一、方案对比总览

| 指标 | Exp36 (激进型) | Exp48 (稳健型) |
|------|---------------|---------------|
| **定位** | 高收益 | 高夏普 |
| 训练期收益 | 574.8% | 303.2% |
| 测试期收益 | **1544.6%** | 839.7% |
| 训练期夏普 | 3.44 | 4.37 |
| 测试期夏普 | 6.58 | **8.46** |
| 交易次数 | 1048/730 | 576/404 |
| 胜率 | 34.4% | **36.4%** |
| 最大回撤 | 19.5% | **16.9%** |

---

## 二、策略配置详情

### 2.1 Exp36: 持仓3天+阈值0.8 (激进型)

#### 因子配置
| 因子 | 权重 | 方向 | IC | IR |
|------|------|------|-----|-----|
| ADX | 50% | long | 0.1219 | 1.28 |
| BB_percent | 20% | long | 0.0228 | 0.29 |
| SAR_trend | 15% | long | 0.0219 | 0.38 |
| OBV_diff | 15% | short | -0.0281 | -0.40 |

#### 交易规则
```
选股信号 = 0.5×ADX分数 + 0.2×BB分数 + 0.15×SAR分数 + 0.15×OBV分数
信号阈值 = 0.8
持仓周期 = 3天
止损线   = -5%
止盈线   = +10%
```

---

### 2.2 Exp48: 均衡权重 (稳健型)

#### 因子配置
| 因子 | 权重 | 方向 | IC | IR |
|------|------|------|-----|-----|
| ADX | 25% | long | 0.1219 | 1.28 |
| BB_percent | 25% | long | 0.0228 | 0.29 |
| SAR_trend | 25% | long | 0.0219 | 0.38 |
| OBV_diff | 25% | short | -0.0281 | -0.40 |

#### 交易规则
```
选股信号 = 0.25×ADX分数 + 0.25×BB分数 + 0.25×SAR分数 + 0.25×OBV分数
信号阈值 = 0.8
持仓周期 = 3天
止损线   = -5%
止盈线   = +10%
```

---

## 三、完整交易流程

### 3.1 第一步: 数据采集

```python
# 采集33只ETF的历史数据
etf_codes = ['159823', '159825', '159915', '159931', ...]  # 共33只

for code in etf_codes:
    df = fetcher.fetch(code, start_date='2023-01-01')
    db.save(code, df)

# 计算技术指标
for code in etf_codes:
    df = db.load(code)
    df = calculator.calculate_all(df)
    db.save_indicators(code, df)
```

**采集结果**: 33只ETF × 800天历史数据

---

### 3.2 第二步: 因子计算

```python
# 计算各因子值
df['ADX'] = calculate_adx(df)           # 趋势强度
df['BB_percent'] = calculate_bb(df)    # 布林带位置
df['SAR_trend'] = calculate_sar(df)    # 抛物线转向
df['OBV_diff'] = calculate_obv(df)     # 能量潮变化
```

**因子方向**:
- ADX, BB, SAR: 越高越买入 (long)
- OBV_diff: 越低越买入 (short)

---

### 3.3 第三步: 选股评分

```python
# Exp36评分公式
def score_exp36(row):
    adx_score = normalize(row['ADX'], direction='long') * 0.5
    bb_score = normalize(row['BB_percent'], direction='long') * 0.2
    sar_score = normalize(row['SAR_trend'], direction='long') * 0.15
    obv_score = normalize(row['OBV_diff'], direction='short') * 0.15
    return adx_score + bb_score + sar_score + obv_score

# Exp48评分公式
def score_exp48(row):
    adx_score = normalize(row['ADX'], direction='long') * 0.25
    bb_score = normalize(row['BB_percent'], direction='long') * 0.25
    sar_score = normalize(row['SAR_trend'], direction='long') * 0.25
    obv_score = normalize(row['OBV_diff'], direction='short') * 0.25
    return adx_score + bb_score + sar_score + obv_score

# 归一化函数
def normalize(value, direction='long'):
    if direction == 'long':
        return min(value / threshold, 1.0)
    else:
        return min((1 - value) / threshold, 1.0)
```

---

### 3.4 第四步: 信号生成

```python
# 每个交易日结束时
for date in trading_dates:
    signals = []
    
    for code in etf_codes:
        df = db.load(code, date=date)
        score = score_exp36(df.iloc[-1])  # Exp36
        
        if score >= 0.8:  # 阈值
            signals.append({'code': code, 'score': score, 'date': date})
    
    # 按分数排序，选Top1
    signals.sort(key=lambda x: x['score'], reverse=True)
    if signals:
        top = signals[0]
        execute_buy(top['code'], top['date'], top['score'])
```

---

### 3.5 第五步: 执行交易

```python
# 买入
def execute_buy(code, date, score):
    price = db.get_price(code, date)
    shares = 100  # 固定份额
    amount = price * shares
    
    trade = {
        'code': code,
        'action': 'buy',
        'date': date,
        'price': price,
        'shares': shares,
        'score': score,
        'entry_price': price
    }
    db.save_trade(trade)
    
    # 持仓3天
    for i in range(1, 4):
        check_exit(code, date + i, trade)

# 检查是否触发退出
def check_exit(code, date, trade):
    price = db.get_price(code, date)
    ret = (price - trade['entry_price']) / trade['entry_price']
    
    if ret <= -0.05:  # 止损
        execute_sell(code, date, 'stop_loss', ret)
    elif ret >= 0.10:  # 止盈
        execute_sell(code, date, 'stop_profit', ret)
    elif date == trade['exit_date']:  # 到期
        execute_sell(code, date, 'expire', ret)

# 卖出
def execute_sell(code, date, reason, pnl_pct):
    price = db.get_price(code, date)
    
    trade = {
        'code': code,
        'action': 'sell',
        'date': date,
        'price': price,
        'pnl_pct': pnl_pct,
        'reason': reason
    }
    db.save_trade(trade)
```

---

## 四、交易记录样本

### 4.1 Exp36 交易样本 (2023年1月-3月)

| 交易日期 | ETF代码 | 操作 | 价格 | 分数/收益 | 原因 |
|---------|---------|------|------|----------|------|
| 2023-01-09 | 159823 | **买入** | 0.730 | 0.80 | 信号触发 |
| 2023-01-10 | 159823 | 卖出 | 0.734 | +0.55% | 到期 |
| 2023-01-18 | 159823 | **买入** | 0.729 | 0.81 | 信号触发 |
| 2023-01-19 | 159823 | 卖出 | 0.736 | +0.96% | 到期 |
| 2023-02-03 | 159952 | **买入** | 1.498 | 0.80 | 信号触发 |
| 2023-02-06 | 159823 | **买入** | 0.719 | 0.85 | 信号触发 |
| 2023-02-06 | 159952 | 卖出 | 1.493 | -0.33% | 到期 |
| 2023-02-07 | 159823 | 卖出 | 0.726 | +0.97% | 到期 |
| 2023-02-09 | 159997 | **买入** | 0.929 | 0.80 | 信号触发 |
| 2023-02-10 | 159997 | 卖出 | 0.962 | +3.55% | 到期 |
| 2023-02-13 | 159823 | **买入** | 0.702 | 0.81 | 信号触发 |
| 2023-02-14 | 159823 | 卖出 | 0.713 | +1.57% | 到期 |
| 2023-02-15 | 512880 | **买入** | 0.930 | 0.88 | 信号触发 |
| 2023-02-16 | 512880 | 卖出 | 0.926 | -0.43% | 到期 |
| 2023-02-17 | 159997 | **买入** | 0.934 | 0.92 | 信号触发 |
| 2023-02-17 | 159823 | **买入** | 0.714 | 0.85 | 信号触发 |
| 2023-02-20 | 159997 | 卖出 | 0.951 | +1.82% | 到期 |
| 2023-02-21 | 159823 | 卖出 | 0.707 | -0.98% | 到期 |

**特征分析**:
- 持仓期2-3天
- 止盈止损触发较少
- 多数交易因"到期"结束

---

### 4.2 Exp48 交易样本 (2023年2月-3月)

| 交易日期 | ETF代码 | 操作 | 价格 | 分数/收益 | 原因 |
|---------|---------|------|------|----------|------|
| 2023-02-15 | 159825 | **买入** | 0.885 | 0.88 | 信号触发 |
| 2023-02-16 | 159995 | **买入** | 1.074 | 0.81 | 信号触发 |
| 2023-02-16 | 159825 | 卖出 | 0.875 | -1.13% | 到期 |
| 2023-02-17 | 159997 | **买入** | 0.934 | 0.90 | 信号触发 |
| 2023-02-17 | 159995 | 卖出 | 1.047 | -2.51% | 到期 |
| 2023-02-21 | 159823 | **买入** | 0.707 | 0.90 | 信号触发 |
| 2023-02-22 | 159823 | 卖出 | 0.700 | -0.99% | 到期 |
| 2023-02-24 | 159952 | **买入** | 1.427 | 0.91 | 信号触发 |
| 2023-02-24 | 516160 | **买入** | 3.274 | 0.90 | 信号触发 |
| 2023-02-27 | 159952 | 卖出 | 1.416 | -0.77% | 到期 |
| 2023-03-02 | 159823 | **买入** | 0.684 | 0.93 | 信号触发 |
| 2023-03-02 | 159823 | 卖出 | 0.703 | +2.78% | 到期 |

**特征分析**:
- 可同时持仓2只ETF
- 均衡权重使分数更分散
- 交易频率较低

---

## 五、绩效对比

### 5.1 收益曲线

```
Exp36 (激进型):
Train: ████████████████████████████████████████████████████████ 574.8%
Test:  ████████████████████████████████████████████████████████████████████████████████████████████████ 1544.6%

Exp48 (稳健型):
Train: ████████████████████████████████████████████████ 303.2%
Test:  ████████████████████████████████████████████████████████████████████████████████ 839.7%
```

### 5.2 风险指标

| 指标 | Exp36 | Exp48 | 对比 |
|------|-------|-------|------|
| 最大回撤 | 19.5% | 16.9% | Exp48更优 |
| 夏普比率 | 6.58 | 8.46 | Exp48更优 |
| 胜率 | 34.4% | 36.4% | Exp48更优 |
| 盈亏比 | 1.48 | 1.52 | Exp48更优 |
| 日均交易 | 1.4笔 | 0.8笔 | Exp36更频繁 |

---

## 六、推荐结论

### 6.1 场景选择

| 使用场景 | 推荐方案 | 理由 |
|---------|---------|------|
| 追求高收益 | **Exp36** | 测试期收益1544.6% |
| 追求稳健 | **Exp48** | 夏普8.46，回撤16.9% |
| 实盘交易 | **Exp48** | 胜率36.4%，风险可控 |
| 教学展示 | Exp36 | 数据更震撼 |

### 6.2 最终推荐: Exp48

**推荐理由**:
1. ✅ 夏普比率8.46，风险调整后收益最优
2. ✅ 最大回撤16.9%，心理压力小
3. ✅ 胜率36.4%，每3笔交易赢1笔
4. ✅ 滚动验证收益比稳定(均值1.54)

**风险提示**:
⚠️ 滚动验证标准差0.66，显示策略对市场环境敏感
⚠️ 测试期收益异常高(839.7%)，实盘可能无法复制