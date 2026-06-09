```yaml
---
file: SOP_01_DATA_MINING.md
purpose: 因子挖掘完整流程（业务理解→数据准备→IC计算→方向确认→权重→回测验证→参数优化）
used_by:
  - 所有因子研究任务
  - US-024 v9 维护
status: active
last_review: 2026-06-08
review_interval: weekly
---
```

# SOP-01: 数据挖掘标准流程

> 来源: FACTOR_MINING_PLAN_v2.md / 8FACTOR_MINING_PLAN.md
> 版本: 1.1 | 创建: 2026-05-31 | 升级: 2026-06-06 (US-024 后)

**v1.1 变更**：
- ➕ **Step 0** 业务理解（CRISP-DM 第 1 阶段）— 防 fomo 决策
- ➕ **Step 5.0** 因子相关性检查 — 防伪分散
- 🔧 **Step 6** 验收加交易成本（引用 BacktestConfig 默认 0.1% 单边）
- 🔧 **Step 7** 引用 WalkForwardEngine（min_windows=6）

---

## 一、流程概览

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 0: 业务理解     → Step 1: 数据准备     → Step 2: 因子计算  │
│  2问：目标+失败标准  ⚠️门槛     多源验证完成       实现核心指标     │
└─────────────────────────────────────────────────────────────────┘
            ↓                   ↓                   ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: IC计算       → Step 4: 方向判断     → Step 5: 权重确定  │
│  IC均值+IR            IC正/负决定用法         Step 5.0: 相关性检查 │
│                                               防止伪分散         │
└─────────────────────────────────────────────────────────────────┘
            ↓                   ↓                   ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 6: 回测验证     → Step 7: 参数调优     → Step 8: 上线监控  │
│  扣交易成本 0.1%     引用 WalkForward         监控因子IC漂移     │
│  ⚠️ 核心检查点       min_windows=6                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、Step-by-Step 详细操作

### Step 0: 业务理解 ⚠️ 必填门槛

**目标**: 挖因子前必须有"市场假说"约束，防止"为 IC 而 IC"和 fomo 决策

**参考来源**：
- CRISP-DM 1.0 第 1 阶段 Business Understanding（IBM, 1996）
- Lean Startup Hypothesis-Driven Development（Ries, 2011）

**必填 2 问**（不填不让进 Step 1）：

| 问 | 模板 | 示例 |
|---|------|------|
| **问 1（目标）** | "识别 [标的] 在 [时段] 的 [模式]" | 识别通信 ETF 在 5 日内的超跌反弹 |
| **问 2（失败）** | "当 [条件] 时，因子失效" | 熊市 IC < 0 持续 60 天时暂停使用 |

**模板**：[docs/sop01_step0_template.md](./sop01_step0_template.md)

**验证**（v1.1 内嵌）：
- 走 1 遍完整挖新因子流程
- 决策犹豫时长 < 2 小时
- 2 问都填了（无跳过）

---

### Step 1: 数据准备 ⚠️ 门槛检查

**目标**: 确保数据准确，建立数据验证机制

**必须验证项**:
| 检查项 | 方法 | 通过标准 |
|--------|------|----------|
| 多源交叉验证 | 腾讯API vs BaoStock | 同日期收盘价差异 < 0.5% |
| 字段类型验证 | 确认OHLCV顺序 | 100%正确 |
| 异常值检测 | 价格=0, 成交量<0 | 无异常 |
| 日期连续性 | 节假日处理 | 标记或补齐 |

**交付物**: `data_quality_report.md`
```
data_quality_report.md
├── 数据源对比表
├── 异常记录清单
└── 验证结论
```

**门槛**: 数据质量不达标 → 停止 → 修复 → 重新验证

---

### Step 2: 候选因子

**目标**: 系统列出所有可挖掘因子方向

**候选因子分类**:
| 类别 | 因子 | 理论逻辑 |
|------|------|----------|
| **趋势类** | MA5/20/60, SAR, ADX | 趋势方向确认 |
| **动量类** | RSI, MACD, KDJ, 动量(N日) | 超买超卖/趋势延续 |
| **量能类** | OBV, MAOBV, 量比 | 资金流向 |
| **波动类** | 布林带, ATR, 波动率 | 突破信号/风险指标 |
| **超买超卖** | CCI, WR | 反转信号 |

**因子去重规则**:
| 重复类型 | 处理方式 |
|----------|----------|
| 信息重复 | 合并/保留信息量最大的 |
| 数学包含 | 只保留基础因子 |
| 逻辑等价 | 保留更通用的 |

**最终因子数**: 建议 8-10 个核心因子

---

### Step 3: IC计算

**目标**: 量化每个因子的预测能力

**计算公式**:
```python
IC = Correlation(因子值, 未来收益)
IR = IC_mean / IC_std
```

**判定标准**:
| 指标 | 标准 | 说明 |
|------|------|------|
| IC均值 | > 0.02 | 有效 |
| IR | > 0.3 | 稳定 |
| 样本量 | > 100 | 统计显著 |

**IC解释**:
```
IC > 0 → 因子值越大，收益越高（正向）
IC < 0 → 因子值越大，收益越低（反转/舍弃）
|IC| < 0.02 → 因子无效（舍弃）
```

**交付物**: `factor_ic_report.md`
```
factor_ic_report.md
├── 各因子IC/IR汇总表
├── IC时序图（判断稳定性）
└── 有效因子清单
```

---

### Step 4: 方向判断

**决策规则**:
```python
if IC > 0:
    direction = "long"  # 因子值越大越好
elif IC < 0 and 反转理论支持:
    direction = "short" # 反转使用
else:
    direction = "drop"  # 舍弃
```

**交付物**: `factor_direction.md`

---

### Step 5.0: 因子相关性检查 ⚠️ 必跑（防伪分散）

**目标**: 防止多个因子高相关导致"伪分散"（看似分散其实集中）

**参考来源**：
- López de Prado《Advances in Financial Machine Learning》Ch.4（多重检验）
- Chincarini《Quantitative Equity Portfolio Management》Ch.5

**执行步骤**：
1. 收集所有候选因子的时间序列值
2. 算 `corr(factors).abs()`
3. 找 |corr| > 0.7 的高相关对
4. 处理方式：
   - 合并：取主成分 / 取平均
   - 剔除：保留 IC 更高的那个

**工具**：[scripts/sop01_factor_correlation.py](../../scripts/sop01_factor_correlation.py)

**交付物**: `factor_correlation_report.md`
```
factor_correlation_report.md
├── 相关系数矩阵
├── 高相关对清单（|corr| > 0.7）
└── 处理决策（合并/剔除 + 理由）
```

**验证**（v1.1 内嵌）：
- 用 v9 mission 已有 5-8 因子跑一遍
- 评分 = 发现数 × 2（0 发现 = 0 分，1 发现 = 2 分）
- 0 发现时仍接受（"防御性价值"，对未来挖新因子有用）

---

### Step 5: 权重确定

**权重公式**:
```python
weight_i = |IC_i| / sum(|IC|)
```

**约束**:
- 单因子权重上限: 30%
- 最低权重: 5%
- 总权重: 100%

**前置条件**: Step 5.0 相关性检查已完成，高相关对已处理

**交付物**: `factor_weights.md`

---

### Step 6: 回测验证 ⚠️ 核心检查点

**测试时段**:
| 测试类型 | 区间 | 说明 |
|----------|------|------|
| 近1年 | 最近1年 | 最近验证 |
| 近2年 | 最近2年 | 中期验证 |
| 近3年 | 最近3年 | 长期验证 |
| 熊市 | 2022-06~2023-12 | 极端行情 |

**v1.1 关键修订**: 验收必须扣交易成本（v1.0 漏了）

**成本模型**（引用 `src.backtest.engine.BacktestConfig` 默认值）：
```python
from src.backtest.engine import BacktestConfig
config = BacktestConfig()
# 默认：commission_rate=0.0003 (万3) + slippage_rate=0.0002 (万2)
# 单边 0.05% (万5) / 双边 0.1% (万10)
```

**参考来源**：
- López de Prado《Advances in Financial Machine Learning》Ch.16（合成数据回测）
- Ernest Chan《Quantitative Trading》Ch.4（盈利期望公式）

**验收指标**（必须同时满足）:
| 指标 | 目标值 | 门槛 | v1.1 状态 |
|------|--------|:----:|:---:|
| 总收益 | > 0 | ✅ | 保留 |
| **净收益**（=总收益-总成本） | **> 0** | ✅ | ➕ 新增 |
| **净夏普**（扣成本） | **> 0.5** | ⭐ | ➕ 新增 |
| 最大回撤 | < -20% | ⚠️ | 保留 |
| 胜率 | > 40% | ⭐ | 保留 |
| 净盈利期望 | > 1.0 | ✅ | 改（净）|

**公式**:
- `总成本 = 换手率 × cost_per_side × 2`（双边）
- `净收益 = 总收益 - 总成本`
- `净夏普 = (收益均值 - 无风险) / 收益波动率`（扣成本后）
- `盈利期望 = 盈亏比 × 胜率`

**验证**（v1.1 内嵌）：
- v9 mission 已知 5-10 个"通过"实验，用 BacktestConfig 默认值重跑
- 评分 = (1 - 扣成本后通过率) × 100
- 通过率 < 80% 表明成本对策略有实质影响

**交付物**: `backtest_report.md`
```
backtest_report.md
├── 各时段回测结果（扣成本前后对比）
├── 关键指标对比
├── 总成本占收益比例
└── 是否通过验收
```

---

### Step 7: 参数调优

**v1.1 关键修订**: 强制跑 WalkForward 验证（v1.0 只是"建议"）

**调优参数**:
| 参数 | 候选范围 | 当前值 |
|------|----------|--------|
| RSI超卖阈值 | 20~40 | 30 |
| ADX趋势阈值 | 20~30 | 25 |
| 分数门槛 | 4~10 | 6 |

**调优方法**（三选一）:
- 网格搜索（穷举验证）
- 遗传算法（高效搜索）
- Bayesian Optimization

**强制验证（不通过 → 回到 Step 6）**:
- 必须跑 `scripts.validators.walk_forward.WalkForwardEngine`
- 默认配置：`min_windows=6, transaction_cost=0.002 (双边0.2%)`

**不通过标准**:
- OOS IC < 0.01 持续 3 个窗口
- 或 OOS 收益 < IS 收益 50%

**参考来源**：
- López de Prado《Advances in Financial Machine Learning》Ch.11（回测的危险）

**验证**（v1.1 内嵌）：
- 取 v9 一个关键参数跑 WalkForward
- 评分 = OOS/IS 收益比 × 100
- OOS/IS > 50% 表明参数稳健

**交付物**: `parameter_optimization.md`
```
parameter_optimization.md
├── 调优方法 + 参数搜索空间
├── WalkForward 验证结果（每窗口 OOS 收益）
├── OOS/IS 比
└── 是否通过验证
```

---

### Step 8: 上线监控

**监控指标**:
| 指标 | 告警阈值 | 处理 |
|------|----------|------|
| IC漂移 | IC < 0.01 持续30天 | 降低权重 |
| IR衰减 | IR < 0.2 持续60天 | 考虑剔除 |
| 收益反转 | 单季度亏损 > 15% | 临时关闭 |

**监控频率**:
- 每日: IC滚动计算
- 每周: IC均值回顾
- 每月: 因子有效性报告

**交付物**: `monitoring_config.md`

---

## 三、交付物清单

| # | 文档 | 触发时机 |
|---|------|----------|
| 1 | `data_quality_report.md` | Step 1 完成 |
| 2 | `candidate_factors.md` | Step 2 完成 |
| 3 | `factor_ic_report.md` | Step 3 完成 |
| 4 | `factor_direction.md` | Step 4 完成 |
| 5 | `factor_weights.md` | Step 5 完成 |
| 6 | `backtest_report.md` | Step 6 完成 |
| 7 | `parameter_optimization.md` | Step 7 完成 |
| 8 | `monitoring_config.md` | Step 8 完成 |

---

## 四、时间参考

| 阶段 | 任务 | 工时 |
|------|------|:----:|
| **Day 1** | Step 1-2: 数据验证 + 候选因子 | 6h |
| **Day 2** | Step 3: IC计算 | 4h |
| **Day 3** | Step 4-5: 方向判断 + 权重确定 | 3h |
| **Day 4** | Step 6: 回测验证（第1轮） | 4h |
| **Day 5** | Step 6: 回测验证（第2轮）+ 收敛分析 | 4h |
| **Day 6** | Step 7: 参数调优 | 3h |
| **Day 7** | Step 8: 监控配置 + 文档整理 | 2h |

**参考工期**: 7天

---

## 五、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| IC为负无法解释 | 中 | 中 | 设计"反转使用"逻辑 |
| 样本量不足 | 低 | 高 | 扩大ETF池或延长回测期 |
| 过拟合 | 中 | 高 | 留出样本外验证期 |
| 市场结构变化 | 高 | 中 | 动态监控+定期复盘 |

---

## 六、关键检查点（v1.1）

```
[ ] Step 0 必填: 2 问（目标 + 失败标准）都填了
[ ] Step 1 通过: 多源数据差异 < 0.5%
[ ] Step 3 通过: IC均值 > 0.02, IR > 0.3
[ ] Step 5.0 通过: 因子相关性 |corr| < 0.7（高相关对已处理）
[ ] Step 6 通过: 净收益 > 0, 净夏普 > 0.5, 最大回撤 < 20%
[ ] Step 7 通过: WalkForward(min_windows=6) OOS/IS > 50%
```

**任一步骤不通过 → 停止 → 分析原因 → 修复 → 重新验证**

---

## 七、v1.1 实施清单（US-024 后）

实施 SOP-01 v1.1 升级时必须完成：

| 任务 | 位置 | 状态 |
|------|------|:----:|
| Step 0 业务理解 2 问 | 文档 + 模板 | ✅ 文档完成 |
| Step 5.0 因子相关性检查 | 文档 + 工具 | ✅ 文档完成 |
| Step 6 验收扣交易成本 | 文档（引用 BacktestConfig）| ✅ 文档完成 |
| Step 7 强制 WalkForward | 文档（引用 WalkForwardEngine）| ✅ 文档完成 |
| Step 0 模板 | docs/sop01_step0_template.md | ⏸ 待写 |
| 相关性检查工具 | scripts/sop01_factor_correlation.py | ⏸ 待写 |
| 验证（v9 5-8 因子跑相关性）| Phase 5 | ⏸ 待跑 |

---

*SOP版本: 1.1 | 创建: 2026-05-31 | 升级: 2026-06-06*
*来源: FACTOR_MINING_PLAN_v2.md + 8FACTOR_MINING_PLAN.md + CRISP-DM + López de Prado*