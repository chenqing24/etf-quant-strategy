# 变更记录

## [2.2.0] - 2026-05-29

### 新增

- **`src/config/etf_pools.py`**（新建）
  - ETF池配置：核心池48只 + 扩展池28只
  - 采集间隔配置：核心池1~2秒，扩展池1.5~3秒

- **`src/data/etf_name_collector.py`**（新建）
  - `ETFNameCollector` 类：多渠道（腾讯+新浪）采集
  - 失败重试：指数退避（60秒、5分钟、30分钟）
  - 持久化重试队列：存入数据库
  - 监控告警：成功率、失败数量、平均耗时

- **`src/data/etf_lifecycle.py`**（新建）
  - `ETFLifecycleManager` 类：ETF生命周期管理
  - 同步池配置到数据库
  - 检测新ETF/退市ETF
  - 名称变更检测

- **`src/data/api_validator.py`**（新建）
  - `APIFormatValidator` 类：API格式验证器
  - 检测格式变化，连续3次异常告警

- **`src/data/cron_etf_names.py`**（新建）
  - 定时任务入口：fetch_core、fetch_extended、fetch_all、recover、status

- **`src/data/database.py`**（扩展）
  - `init_etf_name_tables()`: 初始化4张新表
  - `save_etf_name_full()`: 保存完整名称信息
  - `get_etf_name_full()`: 获取完整名称信息
  - `add_retry_task()`: 添加重试任务
  - `get_retry_tasks()`: 获取待处理重试任务
  - `complete_retry_task()`: 标记完成
  - `fail_retry_task()`: 标记失败
  - `save_metrics()`: 保存监控指标
  - `get_metrics_summary()`: 获取监控摘要

### 文档

- 新建 `docs/SAFE_ACQUISITION.md`：采集安全规范
- 新建 `docs/MARKET_ETF_LIST.md`：市场主流ETF清单
- 更新 `docs/DATA_DICTIONARY.md`：添加4张新表结构

---

## [2.1.0] - 2026-05-29

### 新增

- **`src/data/database.py`**
  - `migrate_schema()`: 增量扩展表结构（非破坏性）
  - `update_etf_name(code, name)`: 更新ETF名称
  - `get_etf_name(code)`: 获取单个ETF名称
  - `get_all_etf_names()`: 获取所有ETF名称字典

- **`src/data/fetcher.py`**
  - `_fetch_name_from_api(code)`: 从腾讯API获取ETF名称
  - `_get_prefix(code)`: 获取交易所前缀（sh/sz）

- **`scripts/update_etf_names.py`**
  - 一次性回填脚本：将所有ETF名称从腾讯API存入stock_info表
  - 支持 `--dry` 模式用于预览

- **`tests/unit/test_etf_name.py`**
  - ETF名称相关单元测试（10个测试，全部通过）

- **`docs/DATA_DICTIONARY.md`**
  - 添加 stock_info 表结构说明
  - 添加版本历史

### 修复

- 移除硬编码 `ETF_NAMES`
- 报告生成不再强依赖外部网络（从数据库读取）

### 文档

- 更新 DATA_DICTIONARY.md：添加 stock_info 表结构 v2.1
- 新建 CHANGELOG.md：记录变更历史

---

## [2.0.0] - 2026-05-27

### 新增

- 统一字段定义
- SQLite etf.db 表结构
- JSON 热数据格式规范

### 变更

- 所有字段名规范化（小写+下划线）