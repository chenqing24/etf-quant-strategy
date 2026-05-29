# 项目索引

> 本文件帮助快速定位项目中的文档、工具和功能
> 生成时间: 2026-05-28 | 更新: 每次变更时

---

## 一、按场景查找

### 场景1: 想运行每日决策

→ `docs/USAGE.md` 第1节"命令行调用"
```bash
python -m src.decision_cli -m daily
```

---

### 场景2: 想批量运行实验

→ `docs/TOOLS.md` 第1.2节"批量实验运行"
```python
from src.strategy.store import quick_run
r = quick_run(name='test', factors=[...], ...)
```

---

### 场景3: 想修改策略参数

→ `docs/STRATEGY_FRAMEWORK_DESIGN.md`
或直接查看 `src/strategy/config.py`

---

### 场景4: 想修复数据问题

→ `docs/TOOLS.md` 第2.2节"数据修复"
```bash
python scripts/repair_data.py --dry-run
```

---

### 场景5: 想理解系统架构

→ `docs/ARCHITECTURE.md` (数据层架构)
→ `docs/DATA_LAYER.md` (统一数据层 v3.0)
→ `docs/INTERFACE_CONTRACT.md` (模块接口)

---

### 场景6: 想查看实验结果

→ `data/experiments/round2_fixed.json` (修复后45个实验结果)
→ `docs/round2_summary.md` (实验汇总)

---

### 场景7: 想添加新指标

→ `docs/INDICATOR_SPEC.md` (指标规范)
→ `docs/FACTOR_MINING_PLAN_v2.md` (因子挖掘计划)

---

### 场景8: 想了解回测逻辑

→ `docs/BACKTEST_SPEC.md` (回测规范)
→ `src/strategy/engine.py` (引擎实现)

---

### 场景9: 想监控数据质量

→ `docs/DATA_LAYER.md` 第3节"监控机制"
```bash
python -m src.data.monitor --json
python scripts/backup_sqlite.py --status
```

---

### 场景10: 想备份数据库

→ `docs/DATA_LAYER.md` 第5节"备份管理"
```bash
python scripts/backup_sqlite.py --type daily
```

---

## 二、按文件名查找

### 核心代码

| 文件 | 功能 | 关键类/函数 |
|------|------|------------|
| `src/decision_cli.py` | 命令行入口 | `main()` |
| `src/data/manager.py` | 数据统一入口 | `DataFacade` |
| `src/data/fetcher.py` | 数据采集 | `TencentETFetcher` |
| `src/data/writer.py` | 统一写入 | `DataWriter` |
| `src/data/loader.py` | 统一读取 | `DataLoader` |
| `src/strategy/engine.py` | 回测引擎 | `BacktestEngine` |
| `src/strategy/config.py` | 配置管理 | `BacktestConfig` |
| `src/strategy/scorer.py` | 因子评分 | `FactorScorer` |
| `src/strategy/executor.py` | 交易执行 | `TradeExecutor` |
| `src/strategy/store.py` | 结果存储 | `quick_run()` |

---

### 数据脚本

| 文件 | 功能 |
|------|------|
| `scripts/daily_data_check.py` | 每日数据检查 |
| `scripts/repair_data.py` | 数据修复 |
| `scripts/cross_validate_data.py` | 数据交叉验证 |
| `scripts/prefetch_data.py` | 数据预获取 |
| `scripts/migrate_csv_to_sqlite.py` | CSV→SQLite迁移 |
| `scripts/supplement_history_data.py` | 历史数据补全 |
| `scripts/backup_sqlite.py` | SQLite备份管理 |

---

### 数据层（v3.0统一数据入口）

| 文件 | 功能 | 关键类/函数 |
|------|------|------------|
| `src/data/writer.py` | 统一写入器 | `DataWriter` |
| `src/data/loader.py` | 统一读取器 | `DataLoader` |
| `src/data/fetcher.py` | 数据采集 | `TencentETFetcher` |
| `src/data/monitor.py` | 数据监控 | `DataQualityMonitor` |
| `src/data/exceptions.py` | 异常定义 | `DataValidationError` |
| `src/data/types.py` | 数据类型 | `RealtimeQuote`, `DailyRecord` |

---

### 分析脚本

| 文件 | 功能 |
|------|------|
| `scripts/analyze_volatility.py` | 波动率分析 |
| `scripts/check_date_gaps.py` | 日期缺口检查 |
| `scripts/check_missing_etfs.py` | 缺失ETF检查 |
| `scripts/compare_data.py` | 数据对比 |
| `scripts/test_sina_hourly_api.py` | 新浪API测试 |

---

### 分析报告

| 文件 | 内容 |
|------|------|
| `docs/overfitting_analysis.md` | 过拟合分析 |
| `docs/future_function_check.md` | 未来函数检测 |
| `docs/hold_days_analysis.md` | 持仓时间分析 |
| `docs/indicator_future_check.md` | 指标未来函数检查 |
| `docs/strategy_detail.md` | 策略详细方案 |
| `docs/round2_summary.md` | 实验汇总 |

---

## 三、按关键词查找

| 关键词 | 相关文档 |
|--------|---------|
| 批量实验/quick_run | TOOLS.md, store.py |
| 每日决策/decision_cli | USAGE.md |
| 数据采集 | DATA_LAYER.md, ARCHITECTURE.md |
| 策略参数/阈值 | TOOLS.md, STRATEGY_FRAMEWORK_DESIGN.md |
| 回测/Backtest | BACKTEST_SPEC.md, engine.py |
| 因子/指标 | INDICATOR_SPEC.md, scorer.py |
| 数据修复 | TOOLS.md, repair_data.py |
| 实验结果 | round2.json, round2_fixed.json |
| 过拟合 | overfitting_analysis.md |
| 未来函数 | future_function_check.md |
| SQLite/统一数据层 | DATA_LAYER.md, writer.py |
| 数据监控/backup | DATA_LAYER.md, monitor.py |

---

## 四、目录结构

```
etf_strategy/
├── src/
│   ├── decision_cli.py       # CLI入口
│   ├── data/                 # 数据层
│   │   ├── manager.py        # DataFacade
│   │   └── fetcher.py        # DataSourceRouter
│   └── strategy/             # 策略层
│       ├── engine.py          # 回测引擎
│       ├── config.py          # 配置
│       ├── scorer.py          # 评分器
│       ├── executor.py        # 执行器
│       └── store.py          # 结果存储
├── scripts/                  # 数据脚本
├── tests/                    # 测试
├── docs/                     # 文档
│   ├── ARCHITECTURE.md       # 架构
│   ├── INTERFACE_CONTRACT.md # 接口契约
│   ├── TOOLS.md             # 工具清单
│   ├── INDEX.md             # 本文档
│   └── ...                   # 其他文档
├── data/
│   ├── experiments/          # 实验结果
│   │   ├── round2.json      # 原始结果
│   │   ├── round3.json
│   │   ├── round4.json
│   │   ├── round5.json
│   │   └── round2_fixed.json # 修复后结果
│   └── etf_pool.json        # ETF股票池
└── etf_data_live/           # 实时数据
```

---

## 五、常用命令速查

```bash
# 1. 每日决策
python -m src.decision_cli -m daily

# 2. 查看绩效
python -m src.decision_cli -m perf

# 3. 查看历史
python -m src.decision_cli -m history

# 4. 数据检查
python scripts/daily_data_check.py

# 5. 数据修复
python scripts/repair_data.py --dry-run

# 6. 预获取数据
python scripts/prefetch_data.py --days 30
```

---

## 六、关键配置

| 配置项 | 位置 | 默认值 |
|--------|------|--------|
| 阈值 threshold | config.py | 0.8 |
| 止损 stop_loss | config.py | -0.05 |
| 止盈 stop_profit | config.py | 0.10 |
| 持仓 hold_days | config.py | 3 |
| 允许调仓 allow_rebalance | config.py | False |
| 本金 initial_capital | executor.py | 20000 |

---

*文档版本: v1.0 | 创建: 2026-05-28*