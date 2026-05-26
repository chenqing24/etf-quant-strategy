# ETF量化系统 - 文档索引

> 快速查找需要的文档

## 文档分类

### 📚 架构设计

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) | **系统总览**（全局视图+术语表） | ⭐⭐⭐ |
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | 系统完整架构 | ⭐⭐⭐ |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 热冷数据分离架构 | ⭐⭐ |
| [EXECUTION_LAYER.md](./EXECUTION_LAYER.md) | 执行层架构（交易流程） | ⭐⭐ |
| [MONITORING.md](./MONITORING.md) | 监控层架构（告警规则） | ⭐⭐ |

### 📐 接口规范

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [INTERFACE_CONTRACT.md](./INTERFACE_CONTRACT.md) | **模块接口契约** | ⭐⭐⭐ |
| [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) | **字段定义+错误码** | ⭐⭐⭐ |
| [LOG_SPEC.md](./LOG_SPEC.md) | 日志规范 | ⭐⭐ |
| [OUTPUT_FORMAT.md](./OUTPUT_FORMAT.md) | 输出格式规范 | ⭐⭐ |

### 📋 业务规则

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [SELECTION_RULES.md](./SELECTION_RULES.md) | 7因子选股规则 | ⭐⭐⭐ |
| [POSITION_MANAGEMENT.md](./POSITION_MANAGEMENT.md) | 持仓管理规则 | ⭐⭐ |
| [PRD.md](./PRD.md) | 产品需求文档 | ⭐⭐ |

### 📖 使用说明

| 文档 | 说明 | 优先级 |
|------|------|--------|
| [USAGE.md](./USAGE.md) | 使用说明 | ⭐⭐⭐ |
| [CRON_SETUP.md](./CRON_SETUP.md) | 定时任务配置 | ⭐⭐ |
| [NOTIFICATION_ARCHITECTURE.md](./NOTIFICATION_ARCHITECTURE.md) | 通知架构 | ⭐⭐ |

### 📝 开发记录

| 文档 | 说明 |
|------|------|
| [DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md) | 开发日志 |
| [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) | 开发计划 |
| [BUILD_REVIEW.md](./BUILD_REVIEW.md) | 复盘总结 |
| [TASK_TRACKING.md](./TASK_TRACKING.md) | 任务跟踪 |
| [ETF_SKILL_PLAN.md](./ETF_SKILL_PLAN.md) | 技能规划 |

---

## 按职责查找

### 👋 我是新用户
1. [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) - 快速了解系统
2. [USAGE.md](./USAGE.md) - 开始使用

### 🔧 我要修改代码
1. [INTERFACE_CONTRACT.md](./INTERFACE_CONTRACT.md) - 看接口定义
2. [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) - 看字段含义
3. [LOG_SPEC.md](./LOG_SPEC.md) - 看日志规范

### 📊 我要理解策略
1. [SELECTION_RULES.md](./SELECTION_RULES.md) - 看选股规则
2. [POSITION_MANAGEMENT.md](./POSITION_MANAGEMENT.md) - 看持仓规则
3. [PRD.md](./PRD.md) - 看需求背景

### 🏗️ 我要新增模块
1. [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) - 看模块关系
2. [INTERFACE_CONTRACT.md](./INTERFACE_CONTRACT.md) - 定义接口
3. [EXECUTION_LAYER.md](./EXECUTION_LAYER.md) - 参考架构模式

### 📈 我要监控策略
1. [MONITORING.md](./MONITORING.md) - 看监控指标
2. [PERFORMANCE_METRICS.md](./PERFORMANCE_METRICS.md) - 看性能定义

---

## 文档状态

| 状态 | 含义 |
|------|------|
| ✅ 完整 | 文档内容完整，可直接使用 |
| ⚠️ 待完善 | 有内容但需补充细节 |
| ⏳ 待实现 | 仅有框架，内容待填充 |

---

## 贡献指南

### 新增文档
1. 在对应分类下添加文档
2. 更新本文档索引
3. 遵循命名规范：`MODULE_NAME.md`

### 更新文档
1. 在文档末尾添加修订历史
2. 更新本文档的"最后更新"时间
3. Git提交时标注修改范围

---

**最后更新**: 2026-05-26