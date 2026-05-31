# 问题修复计划 v1.0

> 版本: 1.0 | 创建: 2026-06-01 | 流程: SOP-02完整执行

---

## 一、问题清单

| ID | 问题 | 严重性 | 状态 | 优先级 |
|----|------|:------:|------|:------:|
| Q-001 | 交叉验证逻辑异常 | P0 | 🔴待修复 | P0 |
| Q-002 | MC检验逻辑问题 | P0 | 🔴待修复 | P0 |
| Q-003 | 策略设计过于简单 | P1 | 🟡待优化 | P1 |
| Q-004 | ETF集中分布 | P1 | 🟡待优化 | P1 |
| Q-005 | 验证期太短 | P2 | 🟡计划中 | P2 |

---

## 二、SOP-02执行计划

### Phase 1: 问题发现 ✅

- [x] 问题清单已创建：`docs/ISSUES.md`
- [x] 严重性分类完成（P0×2, P1×2, P2×1）
- [x] 参考方案已调研（QuantConnect, sklearn, Zipline）

### Phase 2: 根因分析 🔄

**Q-001: 交叉验证逻辑异常**

| 层级 | 分析 |
|------|------|
| **现象** | CV通过率100%，而滚动<50%、MC=1.0 |
| **直接原因** | CV实现使用了重叠窗口或错误的标准 |
| **根因** | 没有实现walk-forward验证，使用了固定时间段分割 |
| **代码位置** | `experiment_v8_sop.py::cross_validation_test()` |

**当前实现问题**：
```python
# 问题1: 时间段重叠
periods = [
    ('2023-06-01', '2024-12-31'),  # 18个月
    ('2024-01-01', '2024-12-31'),  # 12个月，与上面重叠6个月
    ('2025-01-01', '2025-12-31'),  # 12个月，与上面重叠
]

# 问题2: 只看收益>0，未考虑其他指标
pass': result.total_return > 0
```

**Q-002: 蒙特卡洛检验逻辑问题**

| 层级 | 分析 |
|------|------|
| **现象** | MC p-value=1.0，随机信号优于真实因子 |
| **直接原因** | 随机信号只是打乱收益顺序，没有生成真正的随机买入点 |
| **根因** | 检验逻辑有误：应该比较"随机买入点 vs 真实买入点"的收益，不是打乱已有收益 |
| **代码位置** | `experiment_v8_sop.py::monte_carlo_test()` |

**当前实现问题**：
```python
# 问题: 只是打乱已有收益顺序
shuffled = np.random.permutation(returns)  # 这不是真正的随机信号！
random_means.append(np.mean(shuffled))
```

**正确做法**：应该随机生成买入信号位置，再计算收益

### Phase 3: 方案设计 🟡 进行中

**Q-001修复方案**

| 设计项 | 内容 |
|--------|------|
| **输入** | ETF数据、因子列表 |
| **输出** | Walk-Forward验证结果（通过率） |
| **核心逻辑** | 非重叠窗口 + 多指标评估 |
| **窗口设计** | 训练6个月 → 测试3个月 → 滚动 |

```python
def walk_forward_validation(df, factors, train_months=6, test_months=3):
    """
    Walk-Forward验证:
    1. 使用前N月训练
    2. 在接下来M月测试
    3. 滚动到下一个窗口
    """
    results = []
    
    # 计算窗口边界
    dates = df['date'].values
    train_size = int(train_months * 21)  # 每月约21个交易日
    test_size = int(test_months * 21)
    step = test_size  # 非重叠
    
    for start in range(0, len(dates) - train_size - test_size, step):
        train_end = start + train_size
        test_end = train_end + test_size
        
        train_df = df.iloc[start:train_end]
        test_df = df.iloc[train_end:test_end]
        
        # 训练期优化
        train_signal = get_signal(train_df, factors)
        train_result = backtest(train_df, train_signal)
        
        # 测试期验证
        test_signal = get_signal(test_df, factors)
        test_result = backtest(test_df, test_signal)
        
        results.append({
            'train_return': train_result.total_return,
            'test_return': test_result.total_return,
            'train_vs_test_decay': (test_result.total_return - train_result.total_return) / train_result.total_return
        })
    
    # 多指标评估
    pass_count = sum(1 for r in results 
                     if r['test_return'] > 0 
                     and abs(r['train_vs_test_decay']) < 0.5)  # 样本外衰减<50%
    
    return pass_count / len(results)
```

**Q-002修复方案**

| 设计项 | 内容 |
|--------|------|
| **输入** | 真实信号、真实收益 |
| **输出** | MC p-value + z-score |
| **核心逻辑** | 生成独立随机买入信号，再比较收益 |

```python
def monte_carlo_test_improved(df, factors, n_simulations=1000, signal_p=None):
    """
    改进的蒙特卡洛检验:
    1. 获取真实信号和收益
    2. 生成n个随机买入信号（独立于真实信号）
    3. 比较真实策略与随机策略的性能
    """
    real_signal = get_signal(df, factors)
    real_returns = calculate_returns(df, real_signal)
    
    # 估计真实信号的信号率（用于生成等比例随机信号）
    if signal_p is None:
        signal_p = real_signal.mean()
    
    random_means = []
    for _ in range(n_simulations):
        # 生成独立的随机信号（与真实信号长度相同）
        random_signal = pd.Series(
            np.random.random(len(df)) < signal_p,
            index=df.index
        )
        
        # 计算随机策略收益
        random_returns = calculate_returns(df, random_signal)
        random_means.append(np.mean(random_returns))
    
    # 计算p_value: 随机收益 >= 真实收益的比例
    real_mean = np.mean(real_returns)
    p_value = np.mean([1 if m >= real_mean else 0 for m in random_means])
    
    return {
        'p_value': p_value,
        'real_mean': real_mean,
        'random_mean': np.mean(random_means),
        'random_std': np.std(random_means),
        'z_score': (real_mean - np.mean(random_means)) / np.std(random_means) if np.std(random_means) > 0 else 0
    }
```

---

## 三、Phase 4-6: 开发执行

待Phase 3设计确认后执行。

| Phase | 内容 | 预计工时 |
|-------|------|:--------:|
| Phase 4 | 实现walk_forward_validation + monte_carlo_test_improved | 2小时 |
| Phase 5 | 单元测试 + 回归测试 | 1小时 |
| Phase 6 | 验证旧实验结果 + 交付 | 1小时 |

---

## 四、验收标准

### Q-001验收

| 标准 | 检查方法 |
|------|----------|
| 非重叠窗口 | 检查窗口边界不重叠 |
| 多指标评估 | 同时检查收益、衰减、夏普 |
| 通过率合理 | 不应=100%，应有失败案例 |

### Q-002验收

| 标准 | 检查方法 |
|------|----------|
| p-value<0.05 | 至少部分策略显著 |
| p-value≠1.0 | 随机信号不应100%优于真实 |
| z-score合理 | z-score应在合理范围 |

### 回归验收

| 标准 | 检查方法 |
|------|----------|
| 旧实验可重跑 | experiment_v8_sop.py可正常运行 |
| 结果一致 | 相同参数产生相同结果 |

---

## 五、相关文档

| 文档 | 用途 |
|------|------|
| `docs/ISSUES.md` | 问题清单 |
| `docs/SOP_02_REFACTOR_DEV.md` | SOP-02流程 |
| `docs/SOP_03_EXPERIMENT.md` | SOP-03实验流程 |
| `scripts/experiment_v8_sop.py` | 待修复代码 |

---

*计划版本: 1.0 | 创建: 2026-06-01*