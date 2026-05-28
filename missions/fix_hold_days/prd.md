# 修复方案: 持仓时间问题

## 问题描述

当前回测存在持仓时间与配置不符的问题：
- **配置**: 持仓3天
- **实际**: 平均1.4天
- **原因**: 调仓机制导致频繁换仓

### 调仓触发条件

1. **持仓评分检查** (engine.py:186-190)
   - 持仓评分低于阈值一半时平仓

2. **调仓逻辑** (engine.py:221-234)
   - 新信号分数 > 持仓分数 + 0.1 时换仓

---

## 修复方案

### 方案A: 添加配置项控制调仓行为

```python
# BacktestConfig 新增字段
class BacktestConfig:
    def __init__(
        self,
        stop_loss=-0.05,
        stop_profit=0.1,
        hold_days=5,
        max_positions=2,
        commission=0.0003,
        slippage=0.001,
        allow_rebalance=False,  # 新增：是否允许调仓
        rebalance_threshold=0.1,  # 新增：调仓阈值
    ):
```

### 方案B: 修改引擎逻辑

```python
# 持仓评分检查
if allow_rebalance and code in current_rows:
    pos_score, _ = self.scorer.calculate(current_rows[code])
    if pos_score < self.config.factor_strategy.score_config.threshold * 0.5:
        executor.check_and_close(code, current_price, current_date)
        continue

# 调仓逻辑
if allow_rebalance and executor.positions:
    # ... 原有调仓逻辑
```

---

## 验收标准

1. ✅ 修复后平均持仓时间 = 配置的hold_days
2. ✅ 调仓频率显著降低
3. ✅ 所有原有测试通过
4. ✅ 回测结果与修正前对比，收益合理下降

---

## 影响评估

| 指标 | 修正前 | 修正后(预期) |
|------|--------|-------------|
| 平均持仓 | 1.4天 | 3天 |
| 年交易次数 | ~250次 | ~80次 |
| 年度交易成本 | ~130% | ~42% |
| 回测收益 | 1544.6% | ~500-800% |