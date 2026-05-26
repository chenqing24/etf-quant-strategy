# 今日开发计划 - 2026-05-27

## 问题背景

**数据质量严重问题**：通过交叉验证发现数据采集模块存在字段顺序错误。

### 已确认的问题

| 问题 | 位置 | 影响 |
|------|------|------|
| 腾讯API字段解析错误 | fetcher.py | high/low/close错位 |
| CSV格式与腾讯API不一致 | CSV文件 | 无法直接迁移 |
| migrate脚本字段映射错误 | migrate_csv_to_sqlite.py | etf.db数据错误 |
| 历史数据不可信 | etf.db | 全部33只ETF |

### 腾讯API字段顺序（实测）

```
索引:   [0]     [1]     [2]      [3]      [4]      [5]
       date    open    close    high     low     volume
值例:  "date"  "open"  "close"  "high"   "low"   "volume"
```

### 当前错误的解析方式

```python
# fetcher.py 当前代码（错误！）
date, open_p, high, low, close, volume = item
# 实际解析为: close=item[2], high=item[3], low=item[4]
# 但代码期望: high=item[2], low=item[3], close=item[4]
```

---

## 修复任务

### T-1: 修复 fetcher.py 字段解析

**文件**: `src/data/fetcher.py`

**当前代码**:
```python
for item in records_data:
    date, open_p, high, low, close, volume = item  # ❌ 错误顺序
```

**修复后**:
```python
for item in records_data:
    date = item[0]
    open_p = item[1]
    close = item[2]   # ✅ 腾讯API的索引2是close
    high = item[3]     # ✅ 腾讯API的索引3是high
    low = item[4]      # ✅ 腾讯API的索引4是low
    volume = item[5]
```

**验收标准**:
- [ ] 采集510300后，high > close 且 high > open
- [ ] low < close 且 low < open
- [ ] 与新浪API同日期数据对比，close偏差<1%

---

### T-2: 新增数据验证脚本

**文件**: `scripts/cross_validate_data.py` (已创建，待完善)

**功能**:
- [ ] 对比腾讯API、新浪API的数据一致性
- [ ] 抽样验证同日期同ETF的high/low/close
- [ ] 输出验证报告

**验收标准**:
- [ ] 能正确对比3个数据源
- [ ] 能发现字段错误
- [ ] 验证通过后输出"✅ 数据一致"

---

### T-3: 新增数据修复脚本

**文件**: `scripts/repair_data.py` (新建)

**功能**:
1. 从腾讯API重新获取33只缺失ETF的数据
2. 正确解析字段顺序
3. 补充到SQLite

**注意**: 已有33只ETF的数据因字段错误需重新采集

**验收标准**:
- [ ] 能获取全部66只ETF数据
- [ ] high/low/close字段正确
- [ ] 写入SQLite后验证通过

---

### T-4: 更新迁移脚本注释

**文件**: `scripts/migrate_csv_to_sqlite.py`

**修复**: 增加字段映射说明，防止未来误用

**验收标准**:
- [ ] 有明确的字段映射注释
- [ ] CSV格式与数据库字段对应关系清晰

---

### T-5: 端到端回归测试

**文件**: `tests/test_data_validation.py` (新建)

**测试用例**:
1. 采集数据后验证字段顺序
2. 与新浪API交叉验证
3. SQLite读写一致性验证

**验收标准**:
- [ ] 所有测试通过
- [ ] 字段验证测试覆盖high/low/close

---

## 风险评估

| 任务 | 风险 | 缓解措施 |
|------|------|----------|
| T-1 | 影响数据采集模块 | 先验证再部署 |
| T-3 | 重新采集耗时 | 分批采集，使用限流 |
| T-5 | 历史回测结果变化 | 记录变化，用户确认 |

---

## 里程碑

| 时间 | 任务 | 状态 |
|------|------|------|
| 09:00 | 更新设计文档 | ✅ |
| 10:00 | T-1 修复fetcher.py | ✅ 完成 |
| 11:00 | T-2 数据验证脚本 | ✅ 完成 |
| 12:00 | T-3 数据修复脚本 | ✅ 完成 (66只ETF, 62806行) |
| 14:00 | T-4 更新迁移脚本 | ✅ 完成（标记废弃） |
| 16:00 | T-5 端到端回归测试 | ✅ 完成 |
| 18:00 | **修复完成** | ✅ |

---

## 完成状态

### 数据修复结果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| ETF数量 | 33只 | 66只 |
| 数据行数 | 39,660行 | 62,806行 |
| 字段正确性 | ❌ high/low/close错位 | ✅ 所有字段正确 |
| 数据源 | CSV混用 | SQLite单一数据源 |

### 回测结果对比

| 测试期 | 修复前 | 修复后 |
|--------|--------|--------|
| 2023-2025 | +38.7% (错误数据) | +24.3% (真实数据) |
| 交易次数 | 37次 | 49次 |

⚠️ 修复前的高收益是因为混入了31只合成数据的CSV，修复后的+24.3%是真实数据结果。

### 验证通过项

- [x] fetcher.py字段解析正确
- [x] 数据库66只ETF数据正确
- [x] high > close/open, low < close/open
- [x] 与腾讯API、新浪API交叉验证一致
- [x] 指标计算正常
- [x] 回测引擎正常

---

## 关联文档

- [DATA_ACQUISITION.md](./docs/DATA_ACQUISITION.md) - 数据采集规范（已更新）
- [DATA_DICTIONARY.md](./docs/DATA_DICTIONARY.md) - 字段定义