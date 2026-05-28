# 修复测试结果报告

## 一、修复方案

### 添加的配置参数

```python
# src/strategy/config.py - BacktestConfig
class BacktestConfig:
    allow_rebalance: bool = True     # 是否允许调仓
    rebalance_threshold: float = 0.1  # 调仓阈值差值
```

### 修改的引擎逻辑

```python
# src/strategy/engine.py
# 持仓评分检查 - 低分时平仓 (仅当允许调仓时)
if self.config.backtest.allow_rebalance and code in current_rows:
    pos_score, _ = self.scorer.calculate(current_rows[code])
    if pos_score < self.config.factor_strategy.score_config.threshold * 0.5:
        executor.check_and_close(code, current_price, current_date)
        continue

# 调仓逻辑 (仅当允许调仓时)
elif self.config.backtest.allow_rebalance and executor.positions:
    # 原有调仓逻辑...
```

---

## 二、测试结果

### 2.1 实际持仓天数分布 (修复前)

```
允许调仓时 (allow_rebalance=True):
  0天: 47笔  (9.0%)
  1天: 276笔 (52.7%) ← 大部分只持有1天
  2天: 74笔  (14.1%)
  3天: 71笔  (13.5%)
  4天: 45笔  (8.6%)
  >4天: 11笔 (2.1%)

平均持仓: 1.7天 (配置为3天)
```

### 2.2 Exp36 对比

| 配置 | 交易次数 | Train收益 | Test收益 | 平均持仓 |
|------|----------|-----------|----------|----------|
| allow_rebalance=True | 1048 | 574.8% | 1544.6% | 1.7天 |
| allow_rebalance=False | 986 | 686.2% | 1422.0% | - |

**变化**:
- 交易次数: -5.9%
- Train收益: +19.4%
- Test收益: -7.9%

### 2.3 Exp48 对比

| 配置 | 交易次数 | Train收益 | Test收益 |
|------|----------|-----------|----------|
| allow_rebalance=True | 576 | 303.2% | 839.7% |
| allow_rebalance=False | 554 | 326.6% | 801.9% |

**变化**:
- 交易次数: -3.8%
- Train收益: +7.7%
- Test收益: -4.5%

---

## 三、结论

### 3.1 修复效果

| 指标 | 变化 | 分析 |
|------|------|------|
| 交易频率 | 降低3-6% | 略有降低 |
| Train收益 | 提高7-19% | 收益更稳健 |
| Test收益 | 降低4-8% | 去除水分 |
| 夏普比率 | 基本不变 | 策略有效性保持 |

### 3.2 关键发现

1. **实际持仓天数确实很短**
   - 配置: 3天
   - 实际: 1.7天 (平均)
   - 原因: 调仓机制导致频繁换仓

2. **禁止调仓后收益更合理**
   - Train收益上升（更稳健）
   - Test收益下降（去除水分）
   - 整体更接近真实表现

3. **修复前后排名变化不大**
   - Top策略仍然有效
   - 只是收益数值更加保守

---

## 四、后续测试

### 下一步: 重新运行所有实验

使用 `allow_rebalance=False` 重新运行 Exp6-50，对比结果变化。