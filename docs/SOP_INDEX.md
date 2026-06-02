# SOP文档索引

> 版本: 1.0 | 创建: 2026-05-31

---

## 一、SOP总览

| # | 文档 | 用途 | 触发场景 |
|---|------|------|----------|
| **SOP-01** | [数据挖掘标准流程](./SOP_01_DATA_MINING.md) | 因子挖掘完整流程 | 启动新因子研究 |
| **SOP-02** | [重构与修复开发流程](./SOP_02_REFACTOR_DEV.md) | 问题发现→修复→验证 | 发现bug或需要重构 |
| **SOP-03** | [实验执行标准流程](./SOP_03_EXPERIMENT.md) | 实验设计→执行→分析 | 批量因子/组合测试 |
| **SOP-04** | [数据源接入与验证标准流程](./SOP_04_DATA_SOURCE.md) | 接入新数据源 | 新API/数据源验证 |
| **SOP-05** | [双模式决策标准流程](./SOP_05_DUAL_MODE.md) | v9双模式决策 | 每日检查/趋势/震荡市 |
| **SOP-06** | [用户手动交易记录](./SOP_06_MANUAL_TRADE.md) | 手动记录买卖 | 用户手动交易后 |

---

## 二、快速查阅

### 场景 → SOP 对照

| 场景 | 推荐SOP |
|------|---------|
| 我要开始一个新因子挖掘任务 | [SOP-01: 数据挖掘](./SOP_01_DATA_MINING.md) |
| 发现回测有问题（如89.5%连续买入） | [SOP-02: 重构与修复](./SOP_02_REFACTOR_DEV.md) |
| 我要跑100个组合的实验 | [SOP-03: 实验执行](./SOP_03_EXPERIMENT.md) |
| 我要接入一个新数据源 | [SOP-04: 数据源接入](./SOP_04_DATA_SOURCE.md) |
| 我要验证数据质量 | [SOP-01 Step 1](./SOP_01_DATA_MINING.md#step-1-数据准备-门槛检查) |
| 我要分析因子IC/IR | [SOP-01 Step 3](./SOP_01_DATA_MINING.md#step-3-ic计算) |
| 我要回测验证策略 | [SOP-01 Step 6](./SOP_01_DATA_MINING.md#step-6-回测验证-⚠️-核心检查点) |
| 我手动买卖了ETF，需要记录 | [SOP-06: 手动交易记录](./SOP_06_MANUAL_TRADE.md) |
| 每日ETF检查/双模式决策 | [SOP-05: 双模式决策](./SOP_05_DUAL_MODE.md) |

---

## 三、关键检查点速查

### SOP-01: 数据挖掘

```
[ ] Step 1 通过: 多源数据差异 < 0.5%
[ ] Step 3 通过: IC均值 > 0.02, IR > 0.3
[ ] Step 6 通过: 盈利期望 > 1.0, 最大回撤 < 20%
```

### SOP-02: 重构与修复

```
[ ] 持仓管理机制 已设计
[ ] 交易执行模型 已设计
[ ] 止盈止损顺序 已设计
[ ] min/max持仓天数 已设计
[ ] 测试覆盖率 ≥80%
[ ] 回归测试通过
[ ] 数据库变更检查（schema/*.sql + init_database.py）
[ ] 工具更新同步检查（TOOLS.md, INDEX.md, CHECK_REPORT.md）
```

### SOP-03: 实验执行

```
[ ] ETF股票池定义完整（14只+1只参考）
[ ] 时间分割正确（训练期/验证期）
[ ] 因子池定义清晰
[ ] 数据质量检查（交易日完整性 + 新鲜度）
[ ] 每10个模型停下反思
[ ] IC/IR分析完成
[ ] 过拟合检验完成（使用新验证器）
    - WalkForwardEngine (min_windows=6)
    - MonteCarloEngine
    - CrossEtfValidator (min_test=5)
    - ComprehensiveValidator (threshold=0.6)
[ ] 实验笔记已归档
```

### SOP-04: 数据源接入

```
[ ] 多源交叉验证 差异 < 0.5%
[ ] 字段类型验证 OHLCV顺序正确
[ ] 限速规则 已遵守
[ ] 文档已更新 DATA_SOURCE_REFERENCE.md
[ ] 小批量测试通过（3-5只ETF）
```

---

## 四、交付物清单

### SOP-01: 数据挖掘

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

### SOP-03: 实验执行

| 文件 | 内容 | 位置 |
|------|------|------|
| `single_factor_results.json` | 单因子测试结果 | data/experiments/ |
| `combo_results.json` | 组合测试结果 | data/experiments/ |
| `top10.json` | Top10模型 | data/experiments/ |
| `overfitting_report.json` | 过拟合检验 | data/experiments/ |
| `experiment_YYYYMMDD.md` | 实验笔记 | memory/ |

---

## 五、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-05-31 | 初始版本，4个SOP |
| 1.1 | 2026-06-02 | 增加 SOP-05 双模式决策、SOP-06 手动交易记录 |

---

*SOP索引版本: 1.0 | 创建: 2026-05-31*
*相关文档: SOUL.md（行为规则）, AGENTS.md（工作流指南）*