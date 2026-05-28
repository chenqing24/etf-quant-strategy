# ETF量化系统 - 数据字典 v2.1

> 统一字段定义，解决代码中硬编码字段名的问题
> 更新：新增 ETF名称存储字段，腾讯API单一数据源

## 1. 概述

### 1.1 目的
- 统一ETF系统所有数据字段的命名和定义
- 消除代码中的硬编码字段名
- 为跨模块数据传递提供标准契约

### 1.2 范围
- SQLite历史数据字段（etf.db）
- CSV历史数据字段（迁移过渡期）
- JSON实时数据字段
- API请求/响应字段

---

## 2. SQLite etf.db 表结构

### 2.1 daily（日线数据）

```sql
CREATE TABLE daily (
    code TEXT NOT NULL,          -- 标的代码，如 '510300'
    date TEXT NOT NULL,         -- 交易日期，YYYY-MM-DD
    open REAL,                  -- 开盘价
    high REAL,                  -- 最高价
    low REAL,                   -- 最低价
    close REAL,                 -- 收盘价
    volume INTEGER,             -- 成交量
    UNIQUE(code, date) ON CONFLICT REPLACE
);
CREATE INDEX idx_daily_code_date ON daily(code, date);
CREATE INDEX idx_daily_date ON daily(date);
```

### 2.2 hourly（小时线数据）

```sql
CREATE TABLE hourly (
    code TEXT NOT NULL,              -- 标的代码
    timestamp TEXT NOT NULL,          -- 时间戳，YYYY-MM-DD HH:MM:SS
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    UNIQUE(code, timestamp) ON CONFLICT REPLACE
);
CREATE INDEX idx_hourly_code_ts ON hourly(code, timestamp);
```

### 2.3 min30（30分钟线数据）

```sql
CREATE TABLE min30 (
    code TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    UNIQUE(code, timestamp) ON CONFLICT REPLACE
);
CREATE INDEX idx_min30_code_ts ON min30(code, timestamp);
```

### 2.4 metadata（标的属性缓存）

```sql
CREATE TABLE metadata (
    code TEXT PRIMARY KEY,       -- 标的代码，主键
    name TEXT,                   -- 标的名称
    type TEXT,                   -- 类型：etf/stock
    list_date TEXT,              -- 上市日期，YYYY-MM-DD
    updated_at TEXT              -- 更新时间
);
```

### 2.5 trades（交易记录）

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,          -- 标的代码
    action TEXT NOT NULL,        -- 交易动作：buy/sell
    price REAL NOT NULL,         -- 成交价格
    quantity INTEGER,             -- 成交数量
    fee REAL,                   -- 手续费
    timestamp TEXT NOT NULL      -- 交易时间
);
CREATE INDEX idx_trades_code ON trades(code);
CREATE INDEX idx_trades_timestamp ON trades(timestamp);
```

### 2.6 stock_info（ETF基本信息）

> v2.1 新增：etf_type、name_updated_at 字段用于ETF名称管理

```sql
CREATE TABLE stock_info (
    code                TEXT PRIMARY KEY,  -- ETF代码
    name                TEXT,               -- ETF名称（腾讯API获取）
    exchange            TEXT,               -- 交易所（SH/SZ）
    full_code           TEXT,               -- 完整代码（sh.510300）
    etf_type           TEXT,               -- ETF类型（新增）
    name_updated_at    TEXT,               -- 名称更新时间（新增）
    data_source         TEXT,               -- 数据来源
    created_at         TEXT,               -- 创建时间
    updated_at         TEXT                -- 更新时间
);
```

**字段说明**：
| 字段 | 来源 | 更新频率 | 说明 |
|------|------|----------|------|
| name | 腾讯API | 首次添加时获取，按需更新 | 真实名称，如"沪深300ETF华泰柏瑞" |
| name_updated_at | 自动 | 名称变更时更新 | YYYY-MM-DD HH:MM:SS 格式 |
| etf_type | 自动 | 创建时设置 | 固定值 'ETF' |

### 2.7 etf_pools（ETF池配置）

> v2.2 新增：ETF池配置表

```sql
CREATE TABLE etf_pools (
    code TEXT PRIMARY KEY,           -- ETF代码
    pool_type TEXT NOT NULL,         -- 池类型（core/extended）
    scale_rank INTEGER DEFAULT 0,    -- 规模排名
    daily_volume REAL DEFAULT 0,     -- 日均成交量
    last_fetch_at TEXT,              -- 最后采集时间
    fetch_count INTEGER DEFAULT 0,   -- 采集次数
    status TEXT DEFAULT 'active',    -- active/inactive/failed
    created_at TEXT,                 -- 创建时间
    updated_at TEXT                  -- 更新时间
);
```

### 2.8 etf_names（ETF名称）

> v2.2 新增：ETF名称表（多渠道验证）

```sql
CREATE TABLE etf_names (
    code TEXT PRIMARY KEY,           -- ETF代码
    name TEXT NOT NULL,              -- ETF名称（腾讯API）
    name_sina TEXT,                 -- ETF名称（新浪API）
    verified BOOLEAN DEFAULT 0,      -- 是否验证通过
    verify_count INTEGER DEFAULT 0, -- 验证次数
    last_verify_at TEXT,            -- 最后验证时间
    created_at TEXT,                -- 创建时间
    updated_at TEXT                 -- 更新时间
);
```

### 2.9 etf_name_retry_queue（重试队列）

> v2.2 新增：持久化重试队列表

```sql
CREATE TABLE etf_name_retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,             -- ETF代码
    attempt_count INTEGER DEFAULT 0, -- 重试次数
    last_error TEXT,                -- 最后错误
    status TEXT DEFAULT 'pending',  -- pending/in_progress/failed/done
    priority INTEGER DEFAULT 0,     -- 优先级
    created_at TEXT,                -- 创建时间
    next_retry_at TEXT,            -- 下次重试时间
    finished_at TEXT                -- 完成时间
);
CREATE INDEX idx_retry_status ON etf_name_retry_queue(status, next_retry_at);
```

### 2.10 etf_name_metrics（采集监控）

> v2.2 新增：采集监控指标表

```sql
CREATE TABLE etf_name_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,             -- ETF代码
    success BOOLEAN,               -- 是否成功
    verified BOOLEAN,               -- 是否验证通过
    duration_ms INTEGER,            -- 耗时（毫秒）
    sources_tried TEXT,            -- 尝试的渠道（逗号分隔）
    created_at TEXT                -- 创建时间
);
CREATE INDEX idx_metrics_code ON etf_name_metrics(code);
CREATE INDEX idx_metrics_time ON etf_name_metrics(created_at);
```

### 2.11 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v2.2 | 2026-05-29 | 添加 etf_pools、etf_names、etf_name_retry_queue、etf_name_metrics 表 |
| v2.1 | 2026-05-29 | 添加 stock_info.etf_type、name_updated_at 字段 |
| v2.0 | 2026-05-27 | 统一字段定义 |

---

## 3. CSV历史数据格式（迁移过渡期）

### 3.1 标准格式

**文件名**：`{CODE}.csv`（如 `510300.csv`）

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| date | string | ✅ | 日期，YYYY-MM-DD格式 | 2026-05-26 |
| open | float | ✅ | 开盘价 | 3.856 |
| high | float | ✅ | 最高价 | 3.920 |
| low | float | ✅ | 最低价 | 3.840 |
| close | float | ✅ | 收盘价 | 3.890 |
| volume | int | ✅ | 成交量 | 1234567 |

### 3.2 命名规范

```python
# ✅ 正确：小写+下划线
df['date']
df['close_price']

# ❌ 错误：驼峰/全大写
df['dateTime']
df['CLOSE']
```

---

## 4. JSON实时数据格式

### 4.1 热数据格式（hot层）

**路径**：`etf_data_live/hot/{CODE}.json`

```json
{
  "code": "510300",
  "name": "沪深300ETF",
  "price": 3.890,
  "prev_close": 3.856,
  "open": 3.860,
  "high": 3.920,
  "low": 3.840,
  "volume": 1234567,
  "change_pct": 0.88,
  "timestamp": "2026-05-26T14:30:00"
}
```

### 4.2 字段映射

| JSON字段 | SQLite字段 | 说明 |
|----------|------------|------|
| code | code | 标的代码 |
| name | — | 标的名称（metadata） |
| price | — | 最新价（内存） |
| prev_close | — | 昨收（内存） |
| open | open | 开盘价 |
| high | high | 最高价 |
| low | low | 最低价 |
| close | close | 收盘价 |
| volume | volume | 成交量 |
| change_pct | — | 涨跌幅（计算） |
| timestamp | date/timestamp | 时间戳 |

---

## 5. DataFrame标准字段

### 5.1 日线DataFrame

```python
# 标准字段顺序
columns = ['date', 'open', 'high', 'low', 'close', 'volume']

# 可选扩展字段
optional = ['amount', 'change', 'pct_change']
```

### 5.2 小时线DataFrame

```python
columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
```

---

## 6. 数据源响应格式

### 6.1 新浪API（实时价格）

```
hq.sinajs.cn/list=sh510300,sh510500
返回：var hq_str_sh510300="沪深300ETF,3.890,3.856,3.860,3.920,3.840,1234567,..."
```

### 6.2 新浪API（小时线）

```json
{
  "symbol": "sh510300",
  "data": [
    {"day": "2026-05-25 14:30:00", "open": 3.88, "high": 3.90, "low": 3.85, "close": 3.86, "volume": 1500000},
    ...
  ]
}
```

### 6.3 腾讯API（日线）

```json
{
  "qfq_day": [
    ["2026-05-22", "3.80", "3.85", "3.78", "3.82", "987654"],
    ...
  ]
}
```

---

## 7. 数据类型转换

### 7.1 SQLite → DataFrame

```python
def read_daily(code: str, days: int = 30) -> pd.DataFrame:
    """从SQLite读取日线数据，返回标准DataFrame"""
    df = pd.read_sql(
        f"SELECT date, open, high, low, close, volume FROM daily
         WHERE code = ? ORDER BY date DESC LIMIT ?",
        db, params=[code, days]
    )
    return df

def read_hourly(code: str, limit: int = 100) -> pd.DataFrame:
    """从SQLite读取小时线数据"""
    df = pd.read_sql(
        f"SELECT timestamp, open, high, low, close, volume FROM hourly
         WHERE code = ? ORDER BY timestamp DESC LIMIT ?",
        db, params=[code, limit]
    )
    return df
```

### 7.2 新浪JSON → SQLite

```python
def parse_sina_hourly(response_json: dict, code: str) -> pd.DataFrame:
    """解析新浪小时线JSON，转为DataFrame"""
    data = response_json.get('data', [])
    df = pd.DataFrame(data)
    df['code'] = code
    df = df.rename(columns={'day': 'timestamp'})
    df = df[['code', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]
    return df
```

---

## 8. 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2025-05-24 | 初始版本：CSV/JSON字段定义 |
| v2.0 | 2026-05-26 | 新增SQLite表结构（daily/hourly/min30/metadata/trades） |