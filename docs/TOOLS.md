# 📚 ETF量化系统 - 工具清单

> 本文件索引项目中所有可用工具，按用途分类
> 更新：2026-05-30 | 规则：先调研工具，再动手

---

## 一、项目结构总览

```
etf_strategy/
├── src/
│   ├── data/              # 🔴 数据层（统一入口）
│   │   ├── writer.py      # DataWriter（写入）
│   │   ├── loader.py      # DataLoader, ETFNameLoader（读取）
│   │   ├── manager.py     # DataFacade（统一门面）
│   │   ├── fetcher.py     # 数据采集器
│   │   ├── contracts.py   # 数据契约定义
│   │   └── exceptions.py  # 数据异常类
│   ├── strategy/          # 🟢 策略层
│   │   ├── engine.py      # BacktestEngine
│   │   ├── scorer.py      # FactorScorer
│   │   ├── executor.py    # TradeExecutor
│   │   └── store.py       # quick_run()
│   ├── risk/              # 🟠 风控层
│   │   └── manager.py     # RiskManager
│   ├── indicators/        # 📊 指标计算
│   │   └── *.py           # ADX, MACD, KDJ, SAR等
│   └── cli/               # 💻 命令行
│       └── decision.py    # 决策CLI
├── scripts/               # 🟡 脚本工具
│   ├── data/              # 数据采集
│   │   └── fetch_today.py
│   ├── filter_*.py        # ETF筛选（一次性）
│   ├── analyze_*.py       # 分析脚本
│   └── fill_*.py          # 数据补全
├── docs/                  # 📄 文档
│   ├── INDEX.md           # 场景索引
│   ├── TOOLS.md           # 本文档
│   └── *.md               # 其他文档
└── etf_data_live/        # 💾 数据存储
    └── etf.db             # SQLite数据库
```

---

## 二、🔴 数据层（统一入口）

> **核心原则：数据只存一份（SQLite），入口只有一个**

### 2.1 DataWriter（写入）

```python
from src.data.writer import DataWriter

writer = DataWriter()

# 写入日线数据（自动增量+防重复）
df = pd.DataFrame({
    'date': ['2026-05-29', '2026-05-30'],
    'open': [3.50, 3.55],
    'high': [3.60, 3.58],
    'low': [3.48, 3.52],
    'close': [3.55, 3.56],
    'volume': [1000000, 1200000]
})
count = writer.write_daily('510300', df)
# count = 新增记录数
```

**文件**: `src/data/writer.py`

### 2.2 DataLoader（读取）

```python
from src.data.loader import DataLoader

loader = DataLoader()

# 加载所有ETF数据
data = loader.load(min_rows=300)  # 返回 {code: DataFrame}

# 加载单个ETF
df = loader.load_single('510300')

# 获取ETF列表
codes = loader.get_etf_list()

# 获取日期范围
range = loader.get_date_range('510300')
# {'min': '2023-09-26', 'max': '2026-05-29'}
```

**文件**: `src/data/loader.py`

### 2.3 ETFNameLoader（名称）

```python
from src.data.loader import ETFNameLoader

loader = ETFNameLoader()

# 获取单个名称
name = loader.get_name('510300')  # '沪深300ETF华泰柏瑞'

# 批量获取
names = loader.get_names(['510300', '588000'])
# {'510300': '沪深300ETF华泰柏瑞', '588000': '科创50ETF华夏'}
```

**文件**: `src/data/loader.py`

### 2.4 DataFacade（统一门面）

```python
from src.data.manager import DataFacade

facade = DataFacade('etf_data_live')

# 获取日线数据
df = facade.get_daily('510300', days=30)

# 获取实时数据
hot = facade.get_realtime('510300')

# 获取合并数据
merged = facade.get_merged('510300')
```

**文件**: `src/data/manager.py`

---

## 三、数据采集工具

### 3.1 AKTools HTTP API（本地服务）

```python
import requests

AKTOOLS_URL = "http://127.0.0.1:8080"

# 获取全市场ETF实时行情（1486条）
r = requests.get(f"{AKTOOLS_URL}/api/public/fund_etf_spot_em", timeout=60)
etf_list = r.json()

# 获取单只ETF历史日线
r = requests.get(
    f"{AKTOOLS_URL}/api/public/fund_etf_hist_sina",
    params={"symbol": "sz159919"}
)
daily = r.json()

# 获取ETF分类
r = requests.get(f"{AKTOOLS_URL}/api/public/fund_etf_category_sina")
cats = r.json()

# 获取上交所ETF规模
r = requests.get(f"{AKTOOLS_URL}/api/public/fund_etf_scale_sse")
scale = r.json()
```

**服务**: `cd aktools-server && python -m aktools`
**限速**: ≥5秒/次

### 3.2 腾讯API（直接调用）

```python
import requests

# K线数据
url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
params = {'param': 'sh510300,day,,,2000,qfq'}
r = requests.get(url, params=params, timeout=15)
data = r.json()['data']['sh510300']['qfqday']
```

**限速**: ≥2秒/次

### 3.3 脚本工具

| 脚本 | 用途 | 状态 |
|------|------|------|
| `scripts/prefetch_data.py` | 批量预获取历史数据 | ✅ 可用 |
| `scripts/fetch_today.py` | 获取今日数据 | ✅ 可用 |
| `scripts/supplement_history_data.py` | 补全历史数据 | ✅ 可用 |
| `scripts/migrate_csv_to_sqlite.py` | CSV迁移SQLite | ✅ 可用 |
| `scripts/daily_data_check.py` | 每日数据检查 | ✅ 可用 |
| `scripts/repair_data.py` | 数据修复 | ✅ 可用 |

---

## 四、🟢 策略层

### 4.1 quick_run（快速实验）

```python
from src.strategy.store import quick_run

result = quick_run(
    name='test',
    factors=['ADX', 'BB_percent', 'SAR_trend'],
    weights={'ADX': 0.5, 'BB_percent': 0.3, 'SAR_trend': 0.2},
    direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long'},
    stop_loss=-0.05,
    stop_profit=0.10,
    threshold=0.8,
    hold_days=3,
    allow_rebalance=False
)

result['train'].total_return   # 训练期收益
result['test'].sharpe_ratio   # 测试期夏普
```

**文件**: `src/strategy/store.py`

### 4.2 BacktestEngine

```python
from src.strategy.engine import BacktestEngine

engine = BacktestEngine(config)
result = engine.run(data, initial_capital=20000)
```

**文件**: `src/strategy/engine.py`

### 4.3 FactorScorer

```python
from src.strategy.scorer import FactorScorer

scorer = FactorScorer(factors, weights, direction)
score, details = scorer.calculate(row)
```

**文件**: `src/strategy/scorer.py`

---

## 五、🟠 风控层

### 5.1 RiskManager

```python
from src.risk.manager import RiskManager

risk = RiskManager(
    stop_loss=-0.05,   # 止损 -5%
    stop_profit=0.10,  # 止盈 +10%
    max_position=1,    # 最多1个持仓
    hold_days=5        # 最多持仓5天
)

# 检查入场
result = risk.check_entry(portfolio)
# result.allowed = True/False

# 检查出场
signal = risk.check_exit(position, current_price=3.50)
# signal.reason = "stop_loss"/"stop_profit"/"hold_days"
```

**文件**: `src/risk/manager.py`

---

## 六、💻 命令行工具

### 6.1 决策CLI

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

**文件**: `src/cli/main.py`

---

## 七、📊 分析脚本

| 脚本 | 用途 | 备注 |
|------|------|------|
| `scripts/analyze_volatility.py` | 波动率分析 | ✅ 可用 |
| `scripts/check_date_gaps.py` | 日期缺口检查 | ✅ 可用 |
| `scripts/compare_data.py` | 数据对比 | ✅ 可用 |
| `scripts/cross_validate_data.py` | 多源验证 | ✅ 可用 |

---

## 八、⚠️ 一次性脚本（谨慎使用）

> 这些脚本用于特定场景，执行后可能不再需要

| 脚本 | 用途 | 状态 |
|------|------|------|
| `scripts/filter_top500*.py` | ETF筛选 | 一次性 |
| `scripts/fill_missing_etf_history.py` | 补数据 | 一次性 |
| `scripts/update_etf_names.py` | 更新名称 | 一次性 |
| `scripts/backup_sqlite.py` | 备份数据库 | 一次性 |
| `scripts/deduplicate_etf.py` | ETF去重 | 一次性 |

---

## 九、快速索引

| 场景 | 工具 |
|------|------|
| **写入数据** | `DataWriter.write_daily()` |
| **读取数据** | `DataLoader.load()` |
| **获取名称** | `ETFNameLoader.get_name()` |
| **获取实时数据** | `AKTools HTTP API` |
| **运行回测** | `quick_run()` |
| **风险控制** | `RiskManager` |
| **每日决策** | `python -m src.cli.main -m daily` |

---

## 十、工作流程

```
┌─────────────────────────────────────────────────────────┐
│  任务：补充历史数据                                      │
├─────────────────────────────────────────────────────────┤
│  1. 调研工具                                            │
│     - 查看 TOOLS.md                                     │
│     - 查看 INDEX.md                                     │
│                                                         │
│  2. 确定工具                                            │
│     - 数据采集：AKTools HTTP API                        │
│     - 数据写入：DataWriter.write_daily()                │
│     - 禁止：直接sqlite3.execute(INSERT)                 │
│                                                         │
│  3. 编写脚本                                            │
│     - 使用统一工具                                      │
│     - 参考TOOLS.md中的示例代码                          │
│                                                         │
│  4. 测试验证                                            │
│     - 小批量测试                                        │
│     - 验证写入结果                                      │
└─────────────────────────────────────────────────────────┘
```

---

*文档版本: v2.0 | 更新: 2026-05-30*