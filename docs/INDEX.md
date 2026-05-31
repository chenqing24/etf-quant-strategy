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
| **数据质量检查** | `scripts/daily_data_check.py` | `scripts/` |
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
| `scripts/prefetch_data.py` | 批量预获取 |
| `scripts/fetch_today.py` | 获取今日 |
| `scripts/supplement_history_data.py` | 补全历史 |
| `scripts/migrate_csv_to_sqlite.py` | CSV迁移 |
| `scripts/daily_data_check.py` | 数据检查 |
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

*文档版本: v3.0 | 更新: 2026-05-31*