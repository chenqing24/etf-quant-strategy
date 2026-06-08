```yaml
---
file: INDEX.md
purpose: ETF量化系统场景索引（快速定位工具和文档）
used_by:
  - 所有任务（文档定位）
  - 新人入门
status: active
last_review: 2026-06-08
review_interval: weekly
---
```

# 📋 ETF量化系统 - 场景索引

> 快速定位工具和文档 | 更新: 2026-05-31

---

## 一、🔴 按场景查找

| 场景 | 工具/文档 | 位置 |
|------|-----------|------|
| **写入数据到数据库** | `DataWriter.write_daily()` | `src/data/writer.py` |
| **读取数据库数据** | `DataLoader.load()` | `src/data/loader.py` |
| **获取ETF名称** | `ETFNameLoader.get_name()` | `src/data/loader.py` |
| **采集实时数据** | AKTools HTTP API | `http://127.0.0.1:8080` |
| **运行回测实验** | `quick_run()` | `src/strategy/store.py` |
| **风控检查** | `RiskManager` | `src/risk/manager.py` |
| **每日决策** | CLI | `python -m src.cli.main -m daily` |
| **数据质量检查** | `python -m src.data.monitor` | `src/data/monitor.py` |
| **修复数据问题** | `scripts/repair_data.py` | `scripts/` |
| **补充历史数据** | AKTools + DataWriter | 见下方工作流 |
| **获取ETF池** | `ETFListLoader.load()` | `src/data/etf_pool_loader.py` |

---

## 二、SOP标准流程索引

| 场景 | SOP文档 |
|------|---------|
| 因子挖掘研究 | [SOP_01_DATA_MINING.md](./SOP_01_DATA_MINING.md) |
| 问题修复/重构 | [SOP_02_REFACTOR_DEV.md](./SOP_02_REFACTOR_DEV.md) |
| 批量实验执行 | [SOP_03_EXPERIMENT.md](./SOP_03_EXPERIMENT.md) |
| 接入新数据源 | [SOP_04_DATA_SOURCE.md](./SOP_04_DATA_SOURCE.md) |

---

## 三、数据层（核心）

### 写入数据（必须使用）

```python
from src.data.writer import DataWriter

writer = DataWriter()
df = pd.DataFrame({...})
count = writer.write_daily(code, df)  # 自动增量+防重复
```

❌ **禁止**：直接 `sqlite3.execute(INSERT)`

### 读取数据

```python
from src.data.loader import DataLoader

loader = DataLoader()
data = loader.load()           # 加载所有
df = loader.load_single(code)  # 加载单个
codes = loader.get_etf_list()  # 获取列表
```

### 名称获取

```python
from src.data.loader import ETFNameLoader

loader = ETFNameLoader()
name = loader.get_name('510300')
```

---

## 四、数据采集

### AKTools HTTP API（推荐）

```python
import requests

AKTOOLS_URL = "http://127.0.0.1:8080"
AKTOOLS_INTERVAL = 5  # 限速：≥5秒/次

# 全市场ETF实时（1486条）
r = requests.get(f"{AKTOOLS_URL}/api/public/fund_etf_spot_em")

# 单只ETF历史日线
r = requests.get(
    f"{AKTOOLS_URL}/api/public/fund_etf_hist_sina",
    params={"symbol": "sz159919"}
)
```

**服务**：见 TOOLS.md 第3节

### 脚本工具

| 脚本 | 用途 |
|------|------|
| `scripts/refetch_etf_data.py` | ETF数据重采集（全量/指定列表/指定时间段） |
| `scripts/prefetch_data.py` | 批量预获取 |
| `scripts/migrate_csv_to_sqlite.py` | CSV迁移 |
| `python -m src.data.monitor` | 数据质量监控（分钟级告警+完整性检查） |
| `scripts/repair_data.py` | 数据修复 |

---

## 五、策略层

### 快速实验

```python
from src.strategy.store import quick_run

result = quick_run(
    name='test',
    factors=['ADX', 'BB_percent'],
    weights={'ADX': 0.6, 'BB_percent': 0.4},
    stop_loss=-0.05,
    stop_profit=0.10,
    threshold=0.8,
    hold_days=3
)
```

---

## 六、风控层

```python
from src.risk.manager import RiskManager

risk = RiskManager(
    stop_loss=-0.05,
    stop_profit=0.10,
    max_position=1,
    hold_days=5
)

risk.check_entry(portfolio)
risk.check_exit(position, current_price)
```

---

## 七、命令行工具

```bash
# 每日决策
python -m src.cli.main -m daily

# 完整评估
python -m src.cli.main -m eval

# 记录交易
python -m src.cli.main -m trade --code 510300 --action buy --price 3.50 --quantity 1000

# 查看绩效
python -m src.cli.main -m perf

# 更新ETF池
python -m src.cli.main -m update_pool
```

---

## 八、项目结构

```
etf_strategy/
├── src/
│   ├── cli/                  # 命令行
│   ├── data/                 # 🔴 数据层（统一入口）
│   │   ├── writer.py         # DataWriter（写入）
│   │   ├── loader.py         # DataLoader, ETFNameLoader（读取）
│   │   └── manager.py        # DataFacade（门面）
│   ├── strategy/             # 🟢 策略层
│   │   ├── engine.py         # BacktestEngine
│   │   ├── scorer.py         # FactorScorer
│   │   └── store.py          # quick_run()
│   ├── risk/                 # 🟠 风控层
│   │   └── manager.py        # RiskManager
│   └── indicators/           # 📊 指标
├── scripts/                  # 🟡 脚本工具
├── tests/                    # 测试
├── docs/                     # 📄 文档
│   ├── README.md             # 文档索引（主入口）
│   ├── INDEX.md              # 本文档（场景索引）
│   ├── TOOLS.md              # 工具清单
│   ├── SOP_INDEX.md          # SOP文档索引
│   └── archive/              # 历史文档
└── etf_data_live/            # 💾 SQLite数据
```

---

## 九、快速索引

| 任务 | 标准做法 |
|------|----------|
| 补充历史数据 | AKTools采集 → DataFrame转换 → `DataWriter.write_daily()` |
| 读取数据 | `DataLoader.load()` |
| 运行回测 | `quick_run()` |
| 获取ETF池 | `ETFListLoader.load()` → `to_tencent_codes()` |
| 风控检查 | `RiskManager` |
| 获取实时数据 | AKTools HTTP API |

---

## 十、工作流程（标准）

```
┌────────────────────────────────────────────────────────────┐
│  补充历史数据标准流程                                        │
├────────────────────────────────────────────────────────────┤
│  1. 调研工具                                               │
│     ✓ 查看 docs/INDEX.md（场景索引）                        │
│     ✓ 查看 docs/TOOLS.md（工具清单）                        │
│                                                            │
│  2. 确定工具                                               │
│     ✓ 数据采集：AKTools HTTP API / 腾讯API                  │
│     ✓ 数据写入：DataWriter.write_daily()                    │
│     ✓ 禁止：直接sqlite3.execute(INSERT)                    │
│                                                            │
│  3. 编写脚本                                               │
│     ✓ 使用统一工具                                          │
│     ✓ 参考TOOLS.md中的示例代码                              │
│                                                            │
│  4. 测试验证                                               │
│     ✓ 小批量测试                                           │
│     ✓ 用DataLoader验证写入结果                              │
└────────────────────────────────────────────────────────────┘
```

---

---

## 十一、文档资产清单（单一真相源）

> 管理所有文档的"用途、使用者、状态"
> 审查频率：每周
> **每次新增/删除/修改文档后，必须更新此清单**

### 活跃文档（有 metadata 头部）

| 文件 | 用途 | 使用者 |状态 | metadata | 最后审查 |
|------|------|--------|------|:--------:|----------|
| `SOP_01_DATA_MINING.md` | 因子挖掘标准流程 | 所有因子研究任务 | 活跃 | ✅ | 2026-06-08 |
| `SOP_02_REFACTOR_DEV.md` | 重构开发流程 | 所有开发任务 | 活跃 | ✅ | 2026-06-08 |
| `SOP_03_EXPERIMENT.md` | 实验执行流程 | 所有实验任务 | 活跃 | ✅ | 2026-06-08 |
| `SOP_04_DATA_SOURCE.md` | 数据源接入流程 | 数据采集任务 | 活跃 | ✅ | 2026-06-08 |
| `SOP_05_DUAL_MODE.md` | 双模式决策 | 每日决策 | 活跃 | ✅ | 2026-06-08 |
| `SOP_06_MANUAL_TRADE.md` | 手动交易记录 | decision_cli, tracker | 活跃 | ✅ | 2026-06-08 |
| `SOP_07_V9_MISSION_INTEGRATION.md` | v9因子集成 | US-026 | 活跃 | ✅ | 2026-06-08 |
| `SOP_INDEX.md` | SOP文档索引 | 所有SOP入口 | 活跃 | ✅ | 2026-06-08 |
| `POSITION_MANAGEMENT.md` | 持仓参数 + 核心池定义（14只） | etf_pool_loader.py, selector.py | 活跃 | ✅ | 2026-06-08 |
| `TRADE_RECORD_SPEC.md` | 交易字段规范 | tracker.py | 活跃 | ✅ | 2026-06-08 |
| `ARCHITECTURE_DECOUPLING.md` | 架构解耦设计 | 架构重构 | 活跃 | ✅ | 2026-06-08 |
| `EVALUATION_SYSTEM_V7.md` | 评估系统设计 | 回测引擎 | 活跃 | ✅ | 2026-06-08 |
| `DATA_SOURCE_REFERENCE.md` | 数据源参考 | 数据采集 | 活跃 | ✅ | 2026-06-08 |
| `MODULES.md` | 模块依赖 | 架构设计 | 活跃 | ✅ | 2026-06-08 |
| `TOOLS.md` | 工具清单 | 所有任务 | 活跃 | ✅ | 2026-06-08 |

### 需补充 metadata 的活跃文档

| 文件 | 用途 | 优先级 |
|------|------|--------|
| `CHANGELOG.md` | 变更记录 | 🟡 中 |
| `README.md` | 主入口文档 | 🟡 中 |
| `BACKTEST_ENGINE_V8_DESIGN.md` | 回测引擎设计 | 🟢 低 |
| `DATA_LAYER.md` | 数据层设计 | 🟢 低 |
| `FACTOR_MINING_PLAN_v2.md` | 因子挖掘计划 | 🟢 低 |

### 废弃文档（建议归档）

| 文件 | 原因 | 替代文档 |
|------|------|----------|
| `ARCHITECTURE.md` | 旧版架构 | ARCHITECTURE_DECOUPLING.md |
| `ARCHITECTURE_DESIGN.md` | 旧版架构 | ARCHITECTURE_DESIGN_V3.md |
| `ARCHITECTURE_DESIGN_V3.md` | 旧版架构 | ARCHITECTURE_FULL.md |
| `ARCHITECTURE_FULL.md` | 旧版架构 | ARCHITECTURE_DECOUPLING.md |
| `ARCHITECTURE_MINDMAP.md` | 旧版架构 | ARCHITECTURE_DECOUPLING.md |
| `EXPERIMENT_REPORT_V7.md` | 旧版实验报告 | archive/experiment_reports/ |
| `EXPERIMENT_REPORT_V8.md` | 旧版实验报告 | archive/experiment_reports/ |
| `FISH_BODY_V3_REPORT.md` | 旧版实验报告 | archive/experiment_reports/ |
| `8FACTOR_MINING_PLAN.md` | 旧版计划 | SOP_01_DATA_MINING.md |
| `MINING_PLAN_V6.md` | 旧版计划 | SOP_01_DATA_MINING.md |
| `MINING_PLAN_V8.md` | 旧版计划 | SOP_01_DATA_MINING.md |
| `TOP3_COMPLETE_REPORT.md` | 旧版TOP报告 | TOP3_FULL_DIMENSION_REPORT.md |
| `TOP3_DIMENSION_REPORT.md` | 旧版TOP报告 | archive/top3/ |
| `TOP3_FULL_TABLE.md` | 旧版TOP报告 | archive/top3/ |
| `EXECUTION_PLAN_V2.md` | 旧版执行计划 | SOP_03_EXPERIMENT.md |
| `STRATEGY_IMPROVEMENT.md` | 旧版策略改进 | 已有新文档 |
| `TODO_REFACTOR.md` | 旧TODO | ISSUES.md |
| `TODAY_PLAN.md` | 临时文档 | 删除 |

### 归档文档（已在 archive/）

|目录 | 内容 | 归档日期 |
|------|------|----------|
| `archive/architecture/` | 旧版架构文档 | 2026-06-07 |
| `archive/experiment_reports/` | 旧版实验报告 | 2026-06-07 |
| `archive/plans/` | 旧版计划文档 | 2026-06-07 |
| `archive/top3/` | 旧版TOP3报告 | 2026-06-07 |

### 文档 metadata 头部（示例）

每个活跃文档头部应包含：

```yaml
---
file: SOP-06.md
purpose: 标准化用户手动记录 ETF 买卖操作
used_by:
  - src/cli/decision.py
  - src/trade/tracker.py
status: active
last_review: 2026-06-08
review_interval: weekly
---
```

### 审查流程

```
1. 每次新增/删除/修改文档 → 更新此清单
2. 每周一 → 检查"声明的使用者"是否还引用
3. 状态变更（活跃 → 废弃）→ 移动到 archive/ 目录
4. AI 会话开始 → 读取此清单 → 知道哪些文档在用
```

---

*文档版本: v5.0 | 更新: 2026-06-08*
*变更：US-087 完善文档资产清单 -16个活跃文档已添加metadata，更新废弃文档列表*