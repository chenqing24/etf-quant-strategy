# ETF 池管理规范 v2.0

> 版本: v2.0 | 创建: 2026-05-30 (v1.0) / 2026-06-17 (v2.0)
> 适用: etf_strategy 仓
> 关联: SOP-13 (ETF 池 DB 化)

---

## ⚠️ v2.0 重要变更（2026-06-17）

**v1.0 已被废弃**——v1.0 错误地把 .txt 文件作为"配置主输入"。

**v2.0 设计原则**：
- ✅ **DB 是 single source of truth**（etf_names.pool_role 字段）
- ✅ `.txt` 文件仅作**导出产物**（人看用）
- ✅ **机制层强制 > LLM 自觉**（L225 教训）

**v1.0 → v2.0 关键修复**：
1. `etf_names` 表加 `tradable` + `pool_role` 字段（migration 003）
2. `ETFListLoader.load()` 优先从 DB 读取
3. `report_generator.analyze_market` 限定 CORE 池
4. 所有 40 只沪深300 ETF 标 reference（不删数据）
5. CORE 池 = 动态池 14 只（510300 已剔除）

---

## 一、核心概念

### ETF 池 4 种角色

| 角色 | 含义 | 默认 | 数量 |
|------|------|------|------|
| `core` | trade 候选池 | tradable=1 | **14**（动态池 - 510300）|
| `reference` | 不可交易，保留数据用于研究/对照 | tradable=0 | **40**（所有 300ETF）|
| `excluded` | 主动排除（港股/红利/证券等）| tradable=0 | **19** |
| `unclassified` | 未标注（默认状态，**不可进 trade**）| tradable=0 | **1413** |

### 完整流程

```
etf.db.etf_names.pool_role='core'  ←  DB 单一真相源
       │
       ├──→ ETFListLoader.load()     (预热/选股/分析)
       ├──→ ETFRepository.list_codes()  (其他业务)
       └──→ scripts/export_pool_to_txt.py  (导出 .txt)
                  │
                  ▼
etf_data_live/top500_target_pool.txt  ←  导出产物（人看用）
```

---

## 二、Schema 设计

### 2.1 etf_names 表新增字段（migration 003）

```sql
-- schema/migrations/003_add_tradable_pool_role.sql
ALTER TABLE etf_names ADD COLUMN tradable INTEGER DEFAULT 0;
ALTER TABLE etf_names ADD COLUMN pool_role TEXT DEFAULT 'unclassified';

CREATE INDEX idx_etf_names_pool_role ON etf_names(pool_role);
CREATE INDEX idx_etf_names_tradable ON etf_names(tradable);
```

### 2.2 字段语义

| 字段 | 类型 | 默认 | 取值 | 含义 |
|------|------|------|------|------|
| `tradable` | INTEGER | 0 | 0 / 1 | 是否可交易（候选池成员）|
| `pool_role` | TEXT | 'unclassified' | core / reference / excluded / unclassified | 池角色 |

**默认值采用"保守策略"**（L019 教训）：新加字段后所有 ETF 默认"未分类、不可交易"，必须显式标注才进 trade 流程。

---

## 三、CORE 池定义

### 3.1 当前 14 只 CORE 池

```
588000   科创50ETF华夏
512480   半导体ETF国联安
512880   证券ETF国泰
512170   医疗ETF华宝
520900   港股通红利ETF广发
515790   光伏ETF华泰柏瑞
515050   通信ETF华夏
512400   有色金属ETF南方
512660   军工ETF国泰
515070   人工智能ETF华夏
512800   银行ETF华宝
512980   传媒ETF广发
512200   房地产ETF南方
515650   消费50ETF富国
```

**筛选标准**（写在 `top500_target_pool.txt` 注释里）：
```
# 成交额>=10亿 + 规模>=10亿
# 排除：货币/债券/QDII/商品
# 仅保留：宽基+行业ETF，同主题去重
# 510300 已剔除（沪深300 ETF 全部为 reference 池）
```

### 3.2 EXCLUDED 池（19 只）

```
# 港股通ETF
159825, 159902, 159915, 159928, 159952

# 红利/养老
513360, 513080

# 证券/金融
512880, 512170, 512200

# 兜底池里的非 CORE（US-088 修正后从 CORE 移出）
159801, 159806, 159857, 159867, 159995, 159997,
510050, 510500, 512760, 515000, 516050, 516160
```

### 3.3 REFERENCE 池（40 只）

**所有沪深300 ETF 全部 reference**（含 510300/159919/510310/510330 等 40 只）：

| 序号 | 代码 | 名称 | 备注 |
|------|------|------|------|
| 1 | 510300 | 沪深300ETF华泰柏瑞 | 主指（流动性最大）|
| 2 | 510310 | 沪深300ETF易方达 | |
| 3 | 510320 | 沪深300ETF中金 | |
| 4 | 510330 | 沪深300ETF华夏 | |
| 5 | 510350 | 沪深300ETF工银 | |
| 6-40 | ... | 其他 35 只 | 510360/510370/510380/510390/512530/515130/.../159919 |

**数据保留**：所有 reference ETF 的历史 K 线**不删**（用于回测研究/对照基准）

---

## 四、加载机制

### 4.1 ETFListLoader（兼容层）

```python
from src.data.etf_pool_loader import ETFListLoader

loader = ETFListLoader()
codes = loader.load()  # 14 只 CORE 池（不含 300ETF）
```

**load() 优先级**（v2.0）：

1. **DB 池**（`etf_names.pool_role='core'`）—— 单一真相源
2. **池文件**（`top500_target_pool.txt`）—— 仅作导出产物/兜底
3. **硬编码**（`FALLBACK_ETF_CODES`）—— 兜底兜底（已弃用）

### 4.2 ETFRepository（推荐）

```python
from src.data.etf_pool_repository import ETFRepository

repo = ETFRepository()
core_codes = repo.list_codes('core')           # 14 只
reference_codes = repo.list_codes('reference') # 40 只
excluded_codes = repo.list_codes('excluded')   # 19 只
```

**Repository 模式**（from Evans《DDD》）：封装 SQL 访问，调用方无需关心表名/字段名。

### 4.3 数据契约

| 字段 | 类型 | 约束 |
|------|------|------|
| 输出 `codes` | list | 6 位纯数字代码 |
| `with_prefix` | list | 腾讯格式（sh/sz 前缀）|
| 重复 | - | 不允许（自动去重）|

---

## 五、迁移流程（SOP-13 5 Phase）

### Phase 1：备份 + 事实核查

```bash
mkdir -p backups/etf_db_$(date +%Y%m%d_%H%M%S)
cp etf_data_live/etf.db backups/etf_db_xxx/etf.db.original
sqlite3 etf_data_live/etf.db "PRAGMA integrity_check;"
# 期望：ok
```

### Phase 2：跑 migration

```bash
python3 scripts/migrate_pool_roles.py
# 自动备份 + 跑 003 migration + 标 core/reference/excluded
```

### Phase 3：写测试（TDD）

测试文件：`tests/unit/test_pool_csi300_filter.py`

```python
def test_core_pool_size_is_14(repo):
    """CORE 池大小 = 14"""
    assert len(repo.list_codes('core')) == 14

def test_csi300_excluded_from_core(repo):
    """所有沪深300 ETF 都不在 CORE"""
    core = set(repo.list_codes('core'))
    for code in CSI300_CODES:
        assert code not in core
```

### Phase 4：改代码

- `src/data/etf_pool_loader.py`：`load()` 优先读 DB
- `src/analysis/report_generator.py`：`analyze_market` 限定 CORE 池

### Phase 5：重跑 + 验证 + 提交

```bash
python -m src.cli.decision -m eval --force
# 期望：预热池 = 14，只 ETF，推荐 ≠ 159919/510300
grep -E "510300|159919" etf_reports/report_$(date +%Y%m%d).txt
# 期望：无输出
git commit -m "fix(etf_pool): SOP-13 执行 003 migration + 限定 CORE 池（14 只）"
```

---

## 六、导出脚本（DB → .txt）

### scripts/export_pool_to_txt.py

```python
#!/usr/bin/env python3
"""DB → top500_target_pool.txt 导出脚本"""
from src.data.etf_pool_repository import ETFRepository
from pathlib import Path

OUT_FILE = Path('etf_data_live/top500_target_pool.txt')

def main():
    repo = ETFRepository()
    core = repo.list_codes('core')

    # 写头部注释
    content = f'''# ETF 池（DB 导出）
# 导出时间: {datetime.now()}
# CORE 池: {len(core)} 只

ETF_POOL = [
'''
    for code in core:
        name = repo.get_name(code) or ''
        content += f"    '{code}',  # {name}\n"
    content += ']\n'

    OUT_FILE.write_text(content, encoding='utf-8')
    print(f'✅ 导出 {len(core)} 只到 {OUT_FILE}')

if __name__ == '__main__':
    main()
```

---

## 七、测试覆盖

| 测试类 | 测试数 | 验证内容 |
|--------|:---:|----------|
| `TestCorePool` | 4 | 池大小、CSI300 排除、reference 保留、跟动态池一致 |
| `TestETFListLoader` | 2 | 无 300ETF、返回 14 只 |
| `TestReferencePool` | 2 | 全 40 只 CSI300、数量 ≥ 40 |
| `TestExcludedPool` | 2 | 510300/510310 不在 core、CORE ∩ EXCLUDED = ∅ |

**总计 10 个测试，回归通过率 100%**（commit `c3bcf38`）

---

## 八、风险与缓解

| 风险 | 缓解 |
|------|------|
| Migration 跑错丢数据 | Phase 1 强制备份 + integrity_check |
| CORE 池标的误排除 | Phase 3 写"ETFListLoader 包含 14 只"测试 |
| 报告生成器改完性能下降 | Phase 5 跑 daily 多次验证时长 |
| LLM 腐化导致 .txt 又被当输入 | 文档显式说明"DB 主输入，.txt 导出产物" |
| 旧 SOP 与新 SOP 混淆 | 旧 SOP 标记 DEPRECATED |

---

## 九、相关文档

| 文档 | 用途 |
|------|------|
| `SOP_13_ETF_POOL_DB_SOT.md` | 池 DB 化标准操作流程 |
| `L228_300ETF进trade候选_...md` | 教训沉淀（跨仓）|
| `etf_pool_repository.py` | Repository 实现 |
| `etf_pool_loader.py` | 兼容层 Loader |
| `migrate_pool_roles.py` | Migration 脚本 |

---

## 十、变更日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-05-30 | 初版（错误地把 .txt 作为主输入）|
| **v2.0** | **2026-06-17** | **DB 单一真相源重构（SOP-13 落地）** |

**v1.0 → v2.0 关键变更**：
- ❌ `.txt` 从"主输入"降级为"导出产物"
- ✅ `etf_names.pool_role` 字段落地
- ✅ 510300 等 40 只 300ETF 全部 reference
- ✅ `ETFListLoader` 改读 DB
- ✅ `report_generator` 限定 CORE 池
- ✅ 测试 10 个新增（L020 教训：docstring 说明新行为）
