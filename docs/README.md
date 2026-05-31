# ETF量化系统 - 文档索引

> 快速查找需要的文档 | 更新: 2026-05-31

---

## 📁 文档目录结构

```
docs/
├── ⭐ 核心文档（必须阅读）
│   ├── INDEX.md              # 场景索引（工具定位）
│   ├── TOOLS.md              # 工具清单
│   └── SOP_INDEX.md          # SOP文档索引
├── 📐 架构设计
│   ├── ARCHITECTURE_DESIGN_V3.md  # 完整设计文档（推荐）
│   ├── ARCHITECTURE_FULL.md       # 架构图+模块说明
│   └── ARCHITECTURE_MINDMAP.md    # 思维导图
├── 📊 SOP标准流程
│   ├── SOP_01_DATA_MINING.md      # 数据挖掘流程
│   ├── SOP_02_REFACTOR_DEV.md     # 重构修复流程
│   ├── SOP_03_EXPERIMENT.md        # 实验执行流程
│   └── SOP_04_DATA_SOURCE.md      # 数据源接入流程
├── 📖 业务规则
│   ├── SELECTION_RULES.md    # 选股规则
│   ├── POSITION_MANAGEMENT.md  # 持仓管理
│   └── BACKTEST_SPEC.md      # 回测规范
└── archive/                  # 历史文档（可忽略）
    ├── architecture/         # 旧版架构文档
    ├── experiment_reports/    # 旧版实验报告
    ├── plans/                # 旧版计划文档
    └── top3/                 # 旧版TOP3报告
```

---

## 文档分类索引

### 📚 架构设计

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [ARCHITECTURE_DESIGN_V3.md](./ARCHITECTURE_DESIGN_V3.md) | **完整设计文档**（推荐） | ⭐⭐⭐ |
| [ARCHITECTURE_FULL.md](./ARCHITECTURE_FULL.md) | 架构图+模块说明 | ⭐⭐⭐ |
| [ARCHITECTURE_MINDMAP.md](./ARCHITECTURE_MINDMAP.md) | 思维导图（快速浏览） | ⭐⭐ |
| [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) | 系统总览+术语表 | ⭐⭐ |
| [EXECUTION_LAYER.md](./EXECUTION_LAYER.md) | 执行层架构 | ⭐⭐ |

### 📐 接口规范

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [INTERFACE_CONTRACT.md](./INTERFACE_CONTRACT.md) | 模块接口契约 | ⭐⭐⭐ |
| [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) | 字段定义+错误码 | ⭐⭐⭐ |
| [LOG_SPEC.md](./LOG_SPEC.md) | 日志规范 | ⭐⭐ |

### 📋 业务规则

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [SELECTION_RULES.md](./SELECTION_RULES.md) | 7因子选股规则 | ⭐⭐⭐ |
| [POSITION_MANAGEMENT.md](./POSITION_MANAGEMENT.md) | 持仓管理规则 | ⭐⭐ |
| [PRD.md](./PRD.md) | 产品需求文档 | ⭐⭐ |
| [BACKTEST_SPEC.md](./BACKTEST_SPEC.md) | 回测规范 | ⭐⭐ |

### 📖 SOP标准流程

| 文档 | 说明 | 用途 |
|------|------|------|
| [SOP_01_DATA_MINING.md](./SOP_01_DATA_MINING.md) | 数据挖掘8步流程 | 因子研究 |
| [SOP_02_REFACTOR_DEV.md](./SOP_02_REFACTOR_DEV.md) | 重构与修复流程 | 问题修复 |
| [SOP_03_EXPERIMENT.md](./SOP_03_EXPERIMENT.md) | 实验执行流程 | 批量测试 |
| [SOP_04_DATA_SOURCE.md](./SOP_04_DATA_SOURCE.md) | 数据源接入流程 | 新API验证 |

### 📊 数据相关

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [DATA_SOURCE_REFERENCE.md](./DATA_SOURCE_REFERENCE.md) | **数据源完整文档** | ⭐⭐⭐ |
| [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) | 字段定义 | ⭐⭐ |
| [DATA_LAYER.md](./DATA_LAYER.md) | 数据层架构 | ⭐⭐ |

### 📝 开发记录

| 文档 | 说明 |
|------|------|
| [DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md) | 开发日志 |
| [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) | 开发计划 |
| [BUILD_REVIEW.md](./BUILD_REVIEW.md) | 复盘总结 |
| [DOC_CLEANUP_PLAN.md](./DOC_CLEANUP_PLAN.md) | 文档清理记录 |

---

## 按职责查找

### 👋 我是新用户
1. [INDEX.md](./INDEX.md) - 快速定位工具
2. [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) - 了解系统
3. [TOOLS.md](./TOOLS.md) - 查看可用工具

### 🔧 我要修改代码
1. [INTERFACE_CONTRACT.md](./INTERFACE_CONTRACT.md) - 看接口定义
2. [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) - 看字段含义

### 📊 我要理解策略
1. [SELECTION_RULES.md](./SELECTION_RULES.md) - 看选股规则
2. [POSITION_MANAGEMENT.md](./POSITION_MANAGEMENT.md) - 看持仓规则

### 🔧 我要处理数据
1. [DATA_SOURCE_REFERENCE.md](./DATA_SOURCE_REFERENCE.md) - 看数据源
2. [SOP_04_DATA_SOURCE.md](./SOP_04_DATA_SOURCE.md) - 接入新数据源
3. [TOOLS.md](./TOOLS.md) - 找工具

### 📈 我要跑实验
1. [SOP_03_EXPERIMENT.md](./SOP_03_EXPERIMENT.md) - 实验执行流程
2. [SOP_01_DATA_MINING.md](./SOP_01_DATA_MINING.md) - 因子挖掘流程

### 🏗️ 我要新增模块
1. [ARCHITECTURE_DESIGN_V3.md](./ARCHITECTURE_DESIGN_V3.md) - 看架构设计
2. [INTERFACE_CONTRACT.md](./INTERFACE_CONTRACT.md) - 定义接口

---

## 历史文档（archive/）

旧版本文档已移动到 `archive/` 目录，如有需要可查阅：

| 目录 | 内容 |
|------|------|
| `archive/architecture/` | 旧版架构文档（V1/V2） |
| `archive/experiment_reports/` | 旧版实验报告 |
| `archive/plans/` | 旧版计划文档 |
| `archive/top3/` | 旧版TOP3报告 |

---

**最后更新**: 2026-05-31