# 📋 ETF量化系统 - 项目索引

> 本文件帮助快速定位项目中的工具和文档
> 更新：2026-05-30 | 规则：先调研，再动手

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
| **数据质量检查** | `scripts/daily_data_check.py` | `scripts/` |
| **修复数据问题** | `scripts/repair_data.py` | `scripts/` |
| **补充历史数据** | `AKTools + DataWriter` | 见下方工作流 |

---

## 二、数据层（核心）

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

### 统一门面

```python
from src.data.manager import DataFacade

facade = DataFacade('etf_data_live')
df = facade.get_daily(code, days=30)
```

---

## 三、数据采集

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
| `scripts/prefetch_data.py` | 批量预获取 |
| `scripts/fetch_today.py` | 获取今日 |
| `scripts/supplement_history_data.py` | 补全历史 |
| `scripts/migrate_csv_to_sqlite.py` | CSV迁移 |
| `scripts/daily_data_check.py` | 数据检查 |
| `scripts/repair_data.py` | 数据修复 |

---

## 四、策略层

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

result['train'].total_return
result['test'].sharpe_ratio
```

### 回测引擎

```python
from src.strategy.engine import BacktestEngine

engine = BacktestEngine(config)
result = engine.run(data, initial_capital=20000)
```

---

## 五、风控层

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

## 六、命令行工具

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

## 七、一次性脚本（⚠️ 谨慎使用）

> 这些脚本用于特定场景，执行后可能不再需要

| 脚本 | 用途 | 状态 |
|------|------|------|
| `scripts/filter_top500*.py` | ETF筛选 | 一次性 |
| `scripts/fill_missing_etf_history.py` | 补数据 | 已重构 |
| `scripts/update_etf_names.py` | 更新名称 | 一次性 |
| `scripts/backup_sqlite.py` | 备份数据库 | 一次性 |

---

## 八、项目结构

```
etf_strategy/
├── src/
│   ├── cli/                  # 命令行
│   │   └── main.py           # CLI入口
│   ├── data/                 # 🔴 数据层（统一入口）
│   │   ├── writer.py         # DataWriter（写入）
│   │   ├── loader.py         # DataLoader, ETFNameLoader（读取）
│   │   ├── manager.py        # DataFacade（门面）
│   │   ├── contracts.py      # 数据契约
│   │   └── exceptions.py     # 异常类
│   ├── strategy/             # 🟢 策略层
│   │   ├── engine.py         # BacktestEngine
│   │   ├── scorer.py         # FactorScorer
│   │   ├── executor.py       # TradeExecutor
│   │   └── store.py          # quick_run()
│   ├── risk/                 # 🟠 风控层
│   │   └── manager.py        # RiskManager
│   ├── indicators/           # 📊 指标
│   │   └── *.py              # ADX, MACD, KDJ等
│   └── notify/              # 🔔 通知
│       └── dingtalk.py      # 钉钉通知
├── scripts/                  # 🟡 脚本工具
│   ├── data/                 # 数据脚本
│   ├── analysis/            # 分析脚本
│   ├── factor_mining/        # 因子挖掘
│   └── *.py                 # 工具脚本
├── tests/                    # 测试
├── docs/                     # 📄 文档
│   ├── INDEX.md              # 本文档（场景索引）
│   ├── TOOLS.md              # 工具清单
│   ├── DATA_SOURCE_REFERENCE.md  # 数据源参考
│   └── *.md                  # 其他文档
├── etf_data_live/            # 💾 SQLite数据
│   └── etf.db
└── data/                      # 其他数据
    └── experiments/          # 实验结果
```

---

## 九、快速索引

| 任务 | 标准做法 |
|------|----------|
| 补充历史数据 | AKTools采集 → DataFrame转换 → `DataWriter.write_daily()` |
| 读取数据 | `DataLoader.load()` |
| 运行回测 | `quick_run()` |
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
│                                                            │
│  5. 提交代码                                               │
│     ✓ 小步提交                                             │
│     ✓ 更新文档（如需）                                      │
└────────────────────────────────────────────────────────────┘
```

---

*文档版本: v2.0 | 更新: 2026-05-30*