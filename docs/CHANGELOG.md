# 变更记录

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