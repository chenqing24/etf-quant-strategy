# 数据层文档

> **核心原则**："数据只存一份：SQLite；入口只有一个：DataSourceRouter"

---

## 一、架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      调用方（业务层）                        │
│   Selector | ReportGenerator | TradeTracker | CronJob     │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    数据访问层（DataAccessLayer）               │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  DataLoader │  │ DataWriter  │  │ DataSourceRouter   │  │
│  │  (统一读取)  │  │ (统一写入)   │  │    (统一入口)       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       数据存储层                             │
│                                                             │
│   etf.db ←──────────────────────┐                          │
│   ├── daily                    │                           │
│   ├── stock_info               │                           │
│   └── realtime_cache          │                           │
│                                 │                           │
│   ┌────────────────────────────┴───────────────────────┐  │
│   │                    监控层 (Monitor)                    │  │
│   │   - DataQualityMonitor（数据质量）                    │  │
│   │   - SQLiteBackupManager（定期备份）                   │  │
│   └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

外部备份：
../etf_backup/csv/  ← 导出/备份用，不参与业务逻辑
```

---

## 二、核心组件

### 2.1 DataWriter（统一写入器）

**文件**: `src/data/writer.py`

**职责**:
- 写入 SQLite（唯一数据源）
- 事务管理
- 增量更新（只写入新数据）
- 防重复写入
- 数据校验

**核心方法**:

```python
from src.data.writer import DataWriter

writer = DataWriter()

# 写入单只ETF日线数据
df = pd.DataFrame({
    'date': ['2024-01-01', '2024-01-02'],
    'open': [3.5, 3.6],
    'high': [3.6, 3.7],
    'low': [3.4, 3.5],
    'close': [3.55, 3.65],
    'volume': [1000000, 1100000]
})
count = writer.write_daily('510300', df)
print(f"写入 {count} 条记录")

# 批量写入
records = {
    '510300': df1,
    '159577': df2
}
results = writer.write_daily_batch(records)

# 获取最新日期
latest = writer.get_latest_date('510300')
```

### 2.2 DataQualityMonitor（数据质量监控）

**文件**: `src/data/monitor.py`

**职责**:
- 检查数据新鲜度
- 检查数据完整性
- 检查存储健康度
- 生成监控报告

**使用方法**:

```bash
# 检查并输出报告
python -m src.data.monitor

# 输出JSON格式
python -m src.data.monitor --json

# 发送到钉钉
python -m src.data.monitor --dingtalk
```

**告警阈值**:

| 指标 | 阈值 | 处理 |
|------|------|------|
| 数据延迟 | > 3天 | 🔴 告警 |
| ETF缺失 | > 15% | 🔴 告警 |
| SQLite大小 | > 100MB | ⚠️ 提示 |

### 2.3 SQLiteBackupManager（备份管理）

**文件**: `scripts/backup_sqlite.py`

**职责**:
- 每日备份（收盘后自动执行）
- 每周备份（周五保留）
- 手动备份（重大变更前）
- 自动清理过期备份

**使用方法**:

```bash
# 每日备份
python scripts/backup_sqlite.py --type daily

# 每周备份
python scripts/backup_sqlite.py --type weekly

# 手动备份
python scripts/backup_sqlite.py --type manual

# 列出备份
python scripts/backup_sqlite.py --list

# 查看状态
python scripts/backup_sqlite.py --status

# 恢复
python scripts/backup_sqlite.py --restore backup_file.db
```

**保留策略**:

| 类型 | 频率 | 保留份数 |
|------|------|----------|
| daily | 每日 | 7份 |
| weekly | 每周五 | 4份 |
| manual | 手动 | 10份 |

---

## 三、数据结构

### 3.1 daily 表（日线行情）

```sql
CREATE TABLE daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,           -- 证券代码（无前缀）
    date TEXT NOT NULL,           -- 日期 YYYY-MM-DD
    open REAL,                    -- 开盘价
    high REAL,                    -- 最高价
    low REAL,                     -- 最低价
    close REAL,                   -- 收盘价
    volume INTEGER,               -- 成交量
    amount REAL,                  -- 成交额
    source TEXT DEFAULT 'tencent',-- 数据来源
    created_at TEXT,               -- 创建时间
    updated_at TEXT,              -- 更新时间
    UNIQUE(code, date)            -- 防重复
);
```

**索引**:
- `idx_daily_code`: code 字段索引
- `idx_daily_date`: date 字段索引

### 3.2 stock_info 表（证券信息）

```sql
CREATE TABLE stock_info (
    code TEXT PRIMARY KEY,
    name TEXT,
    exchange TEXT,               -- SH/SZ/BJ
    category TEXT DEFAULT 'ETF',
    status TEXT DEFAULT 'active',
    list_date TEXT,
    delist_date TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

### 3.3 realtime_cache 表（实时行情缓存）

```sql
CREATE TABLE realtime_cache (
    code TEXT PRIMARY KEY,
    name TEXT,
    price REAL,
    change REAL,
    change_pct REAL,
    volume REAL,
    amount REAL,
    timestamp TEXT,
    updated_at TEXT
);
```

---

## 四、异常定义

**文件**: `src/data/exceptions.py`

| 异常 | 说明 |
|------|------|
| `DataValidationError` | 数据校验失败 |
| `DataSourceError` | 数据源不可用 |
| `DataNotFoundError` | 数据不存在 |
| `DatabaseConnectionError` | 数据库连接失败 |

---

## 五、测试

**文件**: `tests/unit/test_data_layer.py`

```bash
# 运行所有单元测试
python -m pytest tests/unit/test_data_layer.py -v

# 运行特定测试类
python -m pytest tests/unit/test_data_layer.py::TestDataWriter -v
```

**测试覆盖**:

| 测试类 | 用例数 | 覆盖内容 |
|--------|--------|----------|
| TestExceptions | 3 | 异常定义 |
| TestTypes | 3 | 数据类型 |
| TestDataWriter | 6 | 写入逻辑 |
| TestBackupManager | 2 | 备份管理 |
| TestDataQualityMonitor | 4 | 监控功能 |

---

## 六、定时任务配置

### 6.1 数据采集（交易日 15:30）

```bash
# ETF数据采集
30 15 * * 1-5 cd /path/to/etf_strategy && python scripts/fetch_etf_data.py
```

### 6.2 数据库备份

```bash
# 每日备份（收盘后）
30 16 * * 1-5 cd /path/to/etf_strategy && python scripts/backup_sqlite.py --type daily

# 每周备份（每周五）
30 16 * * 5 cd /path/to/etf_strategy && python scripts/backup_sqlite.py --type weekly
```

### 6.3 数据质量监控

```bash
# 每小时检查一次
0 * * * * cd /path/to/etf_strategy && python -m src.data.monitor

# 每日汇总报告（9:00）
0 9 * * * cd /path/to/etf_strategy && python -m src.data.monitor --dingtalk
```

---

## 七、迁移说明（v2.0 → v3.0）

### 7.1 变更点

| 项目 | 原方案 | 新方案 |
|------|--------|--------|
| 数据存储 | CSV + SQLite | 仅 SQLite |
| 写入方式 | 多处写入 | 统一 DataWriter |
| CSV定位 | 数据源 | 外部备份（仅导出） |

### 7.2 迁移步骤

| 阶段 | 任务 | 状态 |
|------|------|------|
| Phase 1 | 新增 DataWriter（保持旧逻辑） | ✅ |
| Phase 2 | 切换写入入口，测试集成 | ✅ |
| Phase 3 | 回归测试，清理死代码 | ✅ |

### 7.3 回滚方案

如需回滚：
1. 停止新数据写入
2. 使用最近备份恢复 SQLite
3. 恢复旧代码

---

## 八、测试覆盖

### 8.1 测试文件

| 文件 | 用例数 | 说明 |
|------|--------|------|
| `tests/unit/test_data_layer.py` | 18 | 核心组件单元测试 |
| `tests/unit/test_data_regression.py` | 12 | 回归测试 |
| `tests/integration/test_data_integration.py` | 7 | 集成测试 |
| `tests/e2e/test_data_e2e.py` | 6 | 端到端测试 |
| `tests/e2e/test_data_production.py` | 8 | 生产场景测试 |
| **总计** | **51** | **全部通过** |

### 8.2 运行测试

```bash
# 运行所有数据层测试
python -m pytest tests/unit/test_data_layer.py \
                 tests/unit/test_data_regression.py \
                 tests/integration/test_data_integration.py \
                 tests/e2e/test_data_e2e.py \
                 tests/e2e/test_data_production.py -v

# 快速检查
python -m pytest tests/unit/test_data_layer.py -v

# 回归测试
python -m pytest tests/unit/test_data_regression.py -v

# 生产场景测试
python -m pytest tests/e2e/test_data_production.py -v
```

---

## 八、参考来源

| 来源 | 引用内容 |
|------|----------|
| SQLite 官方文档 | VACUUM INTO、WAL 模式、PRAGMA |
| Python typing | dataclass、Protocol、TypedDict |
| Clean Architecture | 数据映射器模式、依赖注入 |