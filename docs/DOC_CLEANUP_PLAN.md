# 文档清理建议报告

> 创建: 2026-05-31 | 分析: 99个文档

---

## 一、文档统计

| 类别 | 数量 | 占比 |
|------|-----:|-----:|
| 架构文档 | 7个 | 7% |
| 实验报告 | 14个 | 14% |
| 计划文档 | 11个 | 11% |
| SOP文档 | 5个 | 5% |
| 其他 | 62个 | 63% |
| **总计** | **99个** | 100% |

---

## 二、重复/可合并文档清单

### 2.1 架构类（7个 → 建议3个）

| 文档 | 大小 | 行数 | 建议 | 理由 |
|------|-----:|-----:|:----:|------|
| `ARCHITECTURE.md` | 14KB | 351 | ⚠️ 合并 | 内容被其他文档覆盖 |
| `ARCHITECTURE_SIMPLE.md` | 4KB | 221 | 🔴 废弃 | 被ARCHITECTURE.md包含 |
| `ARCHITECTURE_DESIGN.md` | 17KB | 552 | ✅ 保留 | 基础设计文档 |
| `ARCHITECTURE_DESIGN_V3.md` | 30KB | 1030 | ✅ 保留 | **最佳实践版**，完整设计 |
| `ARCHITECTURE_IMPROVEMENT.md` | 13KB | 412 | ⚠️ 合并 | 可整合到V3 |
| `ARCHITECTURE_FULL.md` | 19KB | 367 | ✅ 保留 | 完整架构图+模块说明 |
| `ARCHITECTURE_MINDMAP.md` | 18KB | 281 | ✅ 保留 | 思维导图形式，易读 |

**建议操作**：
- `ARCHITECTURE_DESIGN_V3.md` → 保留（最新最完整）
- `ARCHITECTURE_FULL.md` → 保留（架构图）
- `ARCHITECTURE_MINDMAP.md` → 保留（快速查阅）
- 其他4个 → 移动到 `archive/` 目录

---

### 2.2 挖掘计划类（4个 → 建议2个）

| 文档 | 大小 | 行数 | 建议 | 理由 |
|------|-----:|-----:|:----:|------|
| `8FACTOR_MINING_PLAN.md` | 11KB | - | 🔴 废弃 | 内容已整合到v2 |
| `FACTOR_MINING_PLAN_v2.md` | 21KB | - | ✅ 保留 | **完整方案v2** |
| `MINING_PLAN_V6.md` | 9KB | - | 🔴 废弃 | 内容已整合到SOP |
| `SOP_01_DATA_MINING.md` | 8KB | - | ✅ 保留 | **标准化流程** |

**建议操作**：
- `FACTOR_MINING_PLAN_v2.md` → 保留（历史版本存档）
- `SOP_01_DATA_MINING.md` → 保留（SOP版本）
- `8FACTOR_MINING_PLAN.md` → 移动到 `archive/`
- `MINING_PLAN_V6.md` → 移动到 `archive/`

---

### 2.3 实验报告类（14个 → 建议保留5个）

| 文档 | 大小 | 建议 | 理由 |
|------|-----:|:----:|------|
| `EXPERIMENT_REPORT_V2.md` | 7KB | ⚠️ 合并 | V2基础版 |
| `EXPERIMENT_REPORT_V2_FINAL.md` | 8KB | ⚠️ 合并 | V2最终版，与V2合并 |
| `EXPERIMENT_REPORT_V3.md` | 7KB | ✅ 保留 | 独立实验 |
| `EXPERIMENT_REPORT_V5.md` | 5KB | ⚠️ 合并 | 内容较少 |
| `EXPERIMENT_REPORT_V6.md` | 8KB | ⚠️ 合并 | 内容较少 |
| `EXPERIMENT_REPORT_V7.md` | 5KB | ✅ 保留 | **最近版本**，需保留 |
| `FISH_BODY_EXPERIMENT_REPORT.md` | 5KB | ✅ 保留 | 独立实验 |
| `FISH_BODY_V2_REPORT.md` | 1KB | 🔴 废弃 | 内容过少 |
| `FISH_BODY_V3_REPORT.md` | 1KB | ⚠️ 合并 | 合并到V3_PLAN |
| `FISH_BODY_V3_PLAN.md` | 7KB | ✅ 保留 | 完整计划 |
| `TOP3_COMPLETE_REPORT.md` | 7KB | ⚠️ 合并 | 重复内容 |
| `TOP3_DIMENSION_REPORT.md` | 7KB | ⚠️ 合并 | 重复内容 |
| `TOP3_FULL_DIMENSION_REPORT.md` | 13KB | ✅ 保留 | 最完整 |
| `TOP3_TRADE_DETAIL_REPORT.md` | 9KB | ✅ 保留 | 交易明细 |
| `TOP3_FULL_TABLE.md` | 10KB | ✅ 保留 | 完整表格 |

**建议操作**：
- 每个实验保留 **1个最终版报告**
- 中间版本移动到 `archive/experiment_reports/`
- TOP3系列保留 `TOP3_FULL_DIMENSION_REPORT.md` + `TOP3_TRADE_DETAIL_REPORT.md`

---

### 2.4 计划文档类（11个 → 建议保留5个）

| 文档 | 大小 | 建议 | 理由 |
|------|-----:|:----:|------|
| `8FACTOR_MINING_PLAN.md` | 11KB | 🔴 废弃 | 已整合 |
| `CLEANUP_PLAN.md` | 4KB | ✅ 保留 | 清理计划 |
| `DEVELOPMENT_PLAN.md` | 5KB | ✅ 保留 | 开发计划 |
| `ETF_SKILL_PLAN.md` | 8KB | ✅ 保留 | Skill计划 |
| `EXECUTION_PLAN_V2.md` | 9KB | ✅ 保留 | 执行计划（已整合到SOP） |
| `FISH_BODY_V3_PLAN.md` | 7KB | ✅ 保留 | 鱼身计划 |
| `IMPROVEMENT_PLAN.md` | 6KB | ⚠️ 合并 | 改进计划 |
| `MINING_PLAN_V6.md` | 9KB | 🔴 废弃 | 已整合 |
| `STRATEGY_IMPROVEMENT_PLAN.md` | 5KB | ⚠️ 合并 | 合并到IMPROVEMENT_PLAN |
| `TODAY_PLAN.md` | 3KB | ✅ 保留 | 今日计划模板 |
| `FACTOR_MINING_PLAN_v2.md` | 21KB | ✅ 保留 | 完整方案 |

---

## 三、合并建议汇总

### 3.1 立即删除（可恢复）

| 路径 | 理由 |
|------|------|
| `ARCHITECTURE_SIMPLE.md` | 被ARCHITECTURE.md包含 |
| `FISH_BODY_V2_REPORT.md` | 内容过少（26行） |
| `8FACTOR_MINING_PLAN.md` | 已整合到v2 |
| `MINING_PLAN_V6.md` | 已整合到SOP |

### 3.2 移动到 archive/（保留历史）

| 来源 | 数量 | 说明 |
|------|-----:|------|
| ARCHITECTURE系列 | 4个 | 旧版本设计 |
| EXPERIMENT_REPORT系列 | 5个 | 中间版本 |
| TOP3系列 | 3个 | 精简后保留1个 |
| MINING_PLAN系列 | 2个 | 旧版本计划 |

### 3.3 精简后目标

| 类别 | 当前 | 目标 | 减少 |
|------|-----:|-----:|-----:|
| 架构文档 | 7个 | 3个 | -57% |
| 实验报告 | 14个 | 8个 | -43% |
| 计划文档 | 11个 | 7个 | -36% |
| **总计** | **99个** | **~50个** | **-50%** |

---

## 四、执行计划

### Phase 1: 立即清理（5分钟）

```bash
# 1. 删除明显重复的文档
rm docs/ARCHITECTURE_SIMPLE.md
rm docs/FISH_BODY_V2_REPORT.md

# 2. 创建archive目录
mkdir -p docs/archive/architecture
mkdir -p docs/archive/experiment_reports
mkdir -p docs/archive/plans

# 3. 移动旧版本到archive
mv docs/ARCHITECTURE.md docs/archive/architecture/
mv docs/ARCHITECTURE_IMPROVEMENT.md docs/archive/architecture/
mv docs/8FACTOR_MINING_PLAN.md docs/archive/plans/
mv docs/MINING_PLAN_V6.md docs/archive/plans/
```

### Phase 2: 合并实验报告（10分钟）

```bash
# 合并V2系列
cat docs/EXPERIMENT_REPORT_V2.md docs/EXPERIMENT_REPORT_V2_FINAL.md > docs/archive/experiment_reports/V2_combined.md

# 合并TOP3系列（保留最完整的）
mv docs/TOP3_COMPLETE_REPORT.md docs/archive/experiment_reports/
mv docs/TOP3_DIMENSION_REPORT.md docs/archive/experiment_reports/
```

### Phase 3: 更新索引（5分钟）

```bash
# 更新INDEX.md，添加archive说明
# 更新SOP_INDEX.md，清理指向已删除文档的链接
```

---

## 五、保留文档清单（建议）

| 类别 | 保留文档 | 说明 |
|------|----------|------|
| **架构** | `ARCHITECTURE_DESIGN_V3.md` | 完整设计文档 |
| | `ARCHITECTURE_FULL.md` | 架构图+模块说明 |
| | `ARCHITECTURE_MINDMAP.md` | 思维导图 |
| **SOP** | `SOP_01~04_DATA_*.md` | 标准化流程 |
| | `SOP_INDEX.md` | SOP索引 |
| **数据** | `DATA_SOURCE_REFERENCE.md` | 数据源文档 |
| | `DATA_DICTIONARY.md` | 数据字典 |
| **实验** | `EXPERIMENT_REPORT_V7.md` | 最近实验 |
| | `FISH_BODY_V3_PLAN.md` | 鱼身计划 |
| | `TOP3_FULL_DIMENSION_REPORT.md` | Top3报告 |
| **计划** | `FACTOR_MINING_PLAN_v2.md` | 挖掘方案v2 |
| | `DEVELOPMENT_PLAN.md` | 开发计划 |

---

## 六、验证命令

```bash
# 清理后验证文档数量
find docs -name "*.md" | wc -l
# 目标: < 70个

# 验证关键文档存在
ls docs/SOP_INDEX.md
ls docs/SOP_01_DATA_MINING.md
ls docs/ARCHITECTURE_DESIGN_V3.md
ls docs/ARCHITECTURE_FULL.md
```

---

*报告创建: 2026-05-31*