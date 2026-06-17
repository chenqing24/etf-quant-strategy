# SOP-13: ETF 池单一数据源（DB 化）标准操作流程

> 版本: v1.0 | 创建: 2026-06-17 | 适用范围: etf_strategy 仓

---

## 一、目标

**把 ETF 池从"散落在 .txt / .py 硬编码"统一到 etf.db.etf_names 表的 pool_role 字段**。

解决三个反复出现的问题：
1. **池文件 vs 实际推荐脱节**（动态池 15 只，但 report_generator 从全库 72 只选股）
2. **参考标的混进 trade 候选**（510300/159919 沪深300ETF 出现在买入建议里）
3. **LLM 腐化征兆**——靠 LLM 记忆"哪些 ETF 是参考"会腐化（L019 教训），必须机制层强制

---

## 二、核心原则

| # | 原则 | 引用 |
|---|---|---|
| 1 | **DB 是 single source of truth** | SOUL 规则 15 |
| 2 | **默认 deny**（tradable=0, pool_role='unclassified'）| L019 教训 |
| 3 | **不删数据，只标角色**（soft delete）| SOUL 规则 21 |
| 4 | **机制层强制 > LLM 自觉** | L025 教训 |
| 5 | **测试驱动**：先写 test，再改代码 | SOP-12 经验 |
| 6 | **先调研再实现**：先查 git log + 现有代码 | SOUL 规则 11 |

---

## 三、Schema 设计（已存在，不需要新增表）

`etf_names` 表的关键字段：

```sql
-- 已在 schema/migrations/003_add_tradable_pool_role.sql（2026-06-03）
ALTER TABLE etf_names ADD COLUMN tradable INTEGER DEFAULT 0;
ALTER TABLE etf_names ADD COLUMN pool_role TEXT DEFAULT 'unclassified';
CREATE INDEX idx_etf_names_pool_role ON etf_names(pool_role);
CREATE INDEX idx_etf_names_tradable ON etf_names(tradable);
```

| 字段 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `tradable` | INTEGER | 0 | 0=不可交易, 1=可交易（候选池成员）|
| `pool_role` | TEXT | 'unclassified' | core / reference / excluded / unclassified |

**角色定义**：
- `core` = 当前 trade 候选池（动态池 15 只 + 兜底池里的真候选）
- `reference` = 不可交易，但保留数据用于研究/对照（如 510300/159919 沪深300ETF）
- `excluded` = 主动排除（如国债 511010、QDII 513100）
- `unclassified` = 未标注（默认状态，**不可进入 trade 流程**）

---

## 四、标准执行流程（5 个 Phase）

### Phase 1：备份 + 事实核查（必须）

```bash
# 1.1 备份 etf.db
mkdir -p backups/etf_db_$(date +%Y%m%d_%H%M%S)
cp etf_data_live/etf.db backups/etf_db_$(date +%Y%m%d_%H%M%S)/etf.db.original
# 验证
sqlite3 etf_data_live/etf.db "PRAGMA integrity_check;"

# 1.2 记录当前 schema
sqlite3 etf_data_live/etf.db ".schema etf_names" > backups/etf_db_$(date +%Y%m%d_%H%M%S)/etf_names.schema.before.txt

# 1.3 跑 init_database.py --dry-run（如果支持）
python3 scripts/init_database.py --dry-run 2>&1 | tee backups/etf_db_$(date +%Y%m%d_%H%M%S)/init_dry_run.log

# 1.4 核对：当前是否有 tradable / pool_role 字段
sqlite3 etf_data_live/etf.db "PRAGMA table_info(etf_names);" | grep -E "tradable|pool_role"
```

**验收**：
- [ ] 备份文件存在
- [ ] `PRAGMA integrity_check` 返回 `ok`
- [ ] 已记录"迁移前 vs 迁移后"字段差异

### Phase 2：执行 migration

```bash
# 2.1 跑 init_database.py（按 SOUL/AGENTS 数据库管理规范）
python3 scripts/init_database.py 2>&1 | tee backups/etf_db_$(date +%Y%m%d_%H%M%S)/init_run.log

# 2.2 跑 migrate_pool_roles.py（标 15 core + 40 reference + 兜底池 excluded）
python3 scripts/migrate_pool_roles.py 2>&1 | tee backups/etf_db_$(date +%Y%m%d_%H%M%S)/migrate_run.log

# 2.3 验证
sqlite3 etf_data_live/etf.db "SELECT pool_role, COUNT(*) FROM etf_names GROUP BY pool_role;"
```

**验收**：
- [ ] `pool_role='core'` ≥ 15
- [ ] `pool_role='reference'` ≥ 40（含所有 40 只沪深300ETF）
- [ ] `pool_role='unclassified'` = 总数 - core - reference - excluded
- [ ] 没有 `tradable=1 AND pool_role='reference'` 的矛盾数据

### Phase 3：写测试（TDD，先于改代码）

**测试文件**：`tests/unit/test_pool_db_sot.py`

| # | 测试名 | 验证内容 |
|---|---|---|
| 1 | `test_core_pool_size_is_15` | `list_codes('core')` 返回 15 只 |
| 2 | `test_csi300_excluded_from_core` | 510300/159919/510310 都不在 core 池 |
| 3 | `test_loader_returns_no_300etf` | `ETFListLoader.load()` 0 只沪深300 |
| 4 | `test_reference_pool_keeps_300etf` | 510300/159919 在 reference 池（数据不删）|
| 5 | `test_dry_run_no_data_change` | migration 跑前 vs 跑后数据量一致 |

**先写测试**（pytest 必然失败，因为代码还没改）→ 再改代码 → 再跑测试（通过）。

### Phase 4：改代码（按测试驱动）

**4.1 `src/data/etf_pool_loader.py`**
- 移除 `FALLBACK_ETF_CODES` 常量（US-085 已删，确认下）
- `load()` 内部用 `ETFRepository.list_codes('core')` 替换原 `top500_target_pool.txt` 读取

**4.2 `src/analysis/report_generator.py`**
- `analyze_market()` 改用 `ETFRepository.list_codes('core')` 限制选股范围
- 关键修复：`for code, df in self.data.items()` → `for code in self.core_codes:` 然后查 `self.data[code]`

**4.3 `src/data/fetcher.py` 预热阶段**
- 仍用 `ETFListLoader`（已改为读 DB）→ 行为不变

### Phase 5：重跑 + 验证 + 提交

```bash
# 5.1 跑 daily
python -m src.cli.decision -m daily 2>&1 | tee backups/etf_db_$(date +%Y%m%d_%H%M%S)/daily_after.log

# 5.2 跑 eval
python -m src.cli.decision -m eval 2>&1 | tee backups/etf_db_$(date +%Y%m%d_%H%M%S)/eval_after.log

# 5.3 验证报告里没有 159919/510300
grep -E "159919|510300" etf_reports/report_$(date +%Y%m%d).txt && echo "❌ 失败：300ETF 仍出现" || echo "✅ 通过：300ETF 已剔除"

# 5.4 跑全部 pytest
python -m pytest tests/unit/ -v 2>&1 | tee backups/etf_db_$(date +%Y%m%d_%H%M%S)/pytest_after.log

# 5.5 Git 提交（小步）
git add schema/ scripts/ src/data/ src/analysis/ tests/unit/test_pool_db_sot.py docs/SOP_13_ETF_POOL_DB_SOT.md docs/ETF_POOL_MANAGEMENT.md
git commit -m "fix(etf_pool): 执行 migration 落地 pool_role + report_generator 限制 core 池"
```

**验收**：
- [ ] daily/eval 报告里 159919/510300 不再出现
- [ ] pytest 全过
- [ ] Git 1 步提交
- [ ] docs/ETF_POOL_MANAGEMENT.md 更新到 v2.0（DB 主版本）

---

## 五、回归测试（必须，防退化）

| # | 测试 | 验证 |
|---|---|---|
| 1 | 跑 C11（5 因子 + max_hold=99999）| alpha 不退化 |
| 2 | 跑 C21-1（BOLL+MA60 入场过滤）| alpha ≈ +52.96% 不退化 |
| 3 | 跑 daily/eval 5 次 | 报告稳定可重复 |

**判定标准**：alpha 退化 > 5% 立即停，回滚到 Phase 1 备份。

---

## 六、Lessons 沉淀（按 SOUL 规则）

完成后必须写：
- **L228**："LLM 腐化征兆 8 维度自检"（hallucination + 假设未验证 + 文档脱节 3 维触发）
- **L229**："DB 单一数据源迁移 = 跑脚本，不是新增表"
- **L230**："SOP-13 池 DB 化流程"（本文档）

---

## 七、相关 commit 历史

| Commit | 用途 |
|---|---|
| `b7bbcad` | feat(us001): ETF 池改为数据库单一数据源（**设计阶段**）|
| `b452ad5` | feat(us002): etf_names 表加 tradable + pool_role 字段（**migration 写了**）|
| `ae0fc5f` | feat(us-002): 完成核心池数据库化（**核心池修成 15 只**）|
| `4a35a51` | fix(etf_pool): 修正核心池为 15 只股票 ETF（**US-085**）|
| `20ed1dc` | fix(us-089): 修正 510300 为 reference 池 |
| `59e0815` | fix(us-095): migrate_pool_roles.py 修正 515050 误标 |
| **TODO** | 跑 migration 在当前 etf.db 落地 |

---

## 八、风险与缓解

| 风险 | 缓解 |
|---|---|
| migration 跑错丢数据 | Phase 1 强制备份 + dry-run |
| core 池标的误排除 | Phase 3 写"ETFListLoader 包含关键 13 只"测试 |
| 报告生成器改完性能下降 | Phase 5 跑 daily 多次验证时长 |
| 兜底池逻辑未触发 | Phase 4.1 验证 FALLBACK 已删 |
| 已沉淀的 C11-C21 alpha 退化 | Phase 5 跑回归 C11/C21-1 |

---

**本 SOP 触发条件**：
- ✅ 用户报告"300ETF 进 trade 候选"等池污染问题
- ✅ 新增 ETF 需要标角色
- ✅ 池文件 / 兜底池与 DB 不一致
- ✅ 任何 trade 推荐与核心池不符

**不适用于**：
- ❌ 短期的临时数据探索
- ❌ 一次性回测脚本（用 FALLBACK 即可）
