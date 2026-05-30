# 数据库 Schema 目录

此目录存放 ETF 量化系统的数据库结构定义。

## 目录结构

```
schema/
├── 01_etf_live_schema.sql          # 行情数据库 schema
├── 02_etf_factors_schema.sql       # 因子数据库 schema
├── README.md                       # 本文档
├── export_01_etf_live_schema.sql   # 自动导出（可选）
└── export_02_etf_factors_schema.sql # 自动导出（可选）
```

## 数据库说明

| 数据库 | 路径 | 用途 |
|--------|------|------|
| 行情库 | `etf_data_live/etf.db` | ETF每日行情、元数据 |
| 因子库 | `data/etf_factors.db` | 因子计算结果、交易记录、回测结果 |

## 表结构说明

### 行情库 (01_etf_live_schema.sql)

| 表名 | 说明 |
|------|------|
| `daily` | ETF每日行情（code, date, open, high, low, close, volume） |
| `etf_names` | ETF元数据（名称、分类、跟踪指数） |
| `stock_info` | 基础信息 |
| `etf_name_retry_queue` | 名称验证重试队列 |
| `etf_name_metrics` | 名称验证指标 |

### 因子库 (02_etf_factors_schema.sql)

| 表名 | 说明 |
|------|------|
| `daily_price` | 扩展行情（含前复权因子） |
| `factor_data` | 因子计算结果（趋势、动量、量价等40+因子） |
| `ic_results` | IC分析结果 |
| `trade_records` | 交易记录 |
| `backtest_results` | 回测结果 |
| `etf_pools` | ETF池配置 |

## 使用方式

### 1. 初始化数据库

```bash
cd etf_strategy
python scripts/init_database.py
```

### 2. 导出现有数据库 Schema

```bash
python scripts/export_schema.py
```

### 3. 数据迁移

```bash
# 导出
python scripts/migrate_data.py --export --db etf_data_live/etf.db --output data/export_live.json

# 导入
python scripts/migrate_data.py --import --db etf_data_live/etf.db --input data/export_live.json
```

### 4. 手动重建数据库

```bash
cd etf_strategy
rm -f etf_data_live/etf.db data/etf_factors.db
python scripts/init_database.py
```

## 注意事项

- 数据库文件（.db）不应提交到 Git
- 所有表使用 `IF NOT EXISTS`，已有数据不会被覆盖
- 索引在表创建后自动创建
- 建议使用 `scripts/init_database.py` 而非直接执行 SQL