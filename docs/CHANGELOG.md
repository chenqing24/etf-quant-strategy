# 变更记录

## [3.0.0] - 2026-06-10

### 文档升级（US-001 决策快照文档先行）

> **范围**：仅 docs/ 目录，不涉及代码改动
> **规则**：先文档后代码（按规则 3.1 文档同步）

### 新增

- **`docs/POSITION_MANAGEMENT.md` v8.1**
  - 加第 4 节"决策快照机制"（4.1~4.6）
  - 引用 `etf.db` 的 `decision_snapshot` 表（schema 007）
  - 说明 target/stop 价格计算公式
  - 与文件系统（JSON）方案对比
  - 与 `etf.db.decision_snapshot` 表关联的 SQL 示例

- **`docs/SOP_06_V2_DESIGN.md` v2.2**
  - 加第 7 节"决策快照持久化"（7.1~7.7）
  - 方案自评分：7.6/10 → **8.6/10**（+1.0）
  - 业界参考：MiFID II / QuantConnect Lean / Backtrader / CQRS Event Sourcing
  - US-001/002/003 任务划分

- **`docs/INTERFACE_CONTRACT.md` v2.1**
  - 加第 9 节"DecisionSnapshot 接口契约"
  - `DecisionSnapshot` dataclass 完整字段定义（13 必填 + 3 可选）
  - `DecisionSnapshotRepository` 接口（save / get_by_id / get_by_code / list_recent / delete）
  - `make_snapshot_from_strategy()` 工厂函数签名
  - 与 TradeRecord 的关系图
  - 错误处理 + 测试要求

- **`docs/INDEX.md` v5.1**
  - 加"查询决策快照"场景入口
  - 加 `decision_snapshot` 表速查（schema 007）
  - 文档资产清单更新（5 文档版本号）

### 变更

- **`docs/TRADE_RECORD_SPEC.md` v1.0 → v1.1**
  - 加 5 字段到必填段：`target_price` / `stop_loss_price` / `stop_profit_price` / `risk_reward_ratio` / `max_hold_days`
  - 加示例 + 计算公式
  - 加 `validate_trade_record()` v1.1 验证逻辑
  - 加变更历史（v1.1 changelog）

- **`docs/SOP_06_MANUAL_TRADE.md` v2.1 → v2.2**
  - 加"Target / Stop 价格字段"小节
  - CLI 示例加 5 个新参数（`--target_price` 等）
  - 参数说明表加"推荐"标记
  - 加 `compute_target_stop()` 自动计算函数

- **`docs/V9_BACKLOG.md` v1.0 → v1.1**
  - 加 TODO-013 决策快照任务（US-001/002/003）
  - 完成记录表加 2026-06-10 TODO-013 ✅
  - 总体状态表更新（11 总数）

### 待办（US-002/003，下一阶段）

- schema/migrations/006_add_trade_target_stop.sql（trade_history 加 5 字段）
- schema/migrations/007_add_decision_snapshot_table.sql（CREATE TABLE + 2 索引）
- scripts/init_database.py 应用 006/007
- src/trade/decision_snapshot.py（US-003 实现模块）
- scripts/migrate_snapshot_to_sqlite.py（US-003 迁移脚本）

### 参考来源

| 来源 | 借鉴点 |
|------|--------|
| MiFID II 交易记录法规 | 强制记录决策上下文（target/stop/reason）|
| QuantConnect Lean Insight | 决策快照持久化 |
| Backtrader | target/stop 价格随交易记录 |
| CQRS Event Sourcing | 决策作为不可变事件存储 |
| mransbro/tradingjournal | 基础字段（含 reason）|

---

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