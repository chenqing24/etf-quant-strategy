```yaml
---
file: TOOLS.md
purpose: 项目中所有可用工具索引（按用途分类）
used_by:
  - 所有任务（工具定位）
status: active
last_review: 2026-06-08
review_interval: weekly
---
```

# 📚 ETF量化系统 - 工具清单

> 本文件索引项目中所有可用工具，按用途分类
> 更新：2026-05-30 | 规则：先调研工具，再动手

---

## 一、⭐ SOP标准流程

> 执行任务前，先查阅对应SOP

| SOP | 用途 | 触发场景 |
|-----|------|----------|
| [SOP_01_DATA_MINING.md](./SOP_01_DATA_MINING.md) | 数据挖掘8步流程 | 因子研究 |
| [SOP_02_REFACTOR_DEV.md](./SOP_02_REFACTOR_DEV.md) | 重构与修复流程 | 问题修复/重构 |
| [SOP_03_EXPERIMENT.md](./SOP_03_EXPERIMENT.md) | 实验执行流程 | 批量测试 |
| [SOP_04_DATA_SOURCE.md](./SOP_04_DATA_SOURCE.md) | 数据源接入流程 | 新API验证 |

完整索引: [SOP_INDEX.md](./SOP_INDEX.md)

---

## 二、项目结构总览

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

## 三、🔴 数据层（统一入口）

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

## 四、数据采集工具

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
| `scripts/refetch_etf_data.py` | ETF数据重采集（支持全量/指定列表/指定时间段） | ✅ 可用 |
| `scripts/prefetch_data.py` | 批量预获取历史数据 | ✅ 可用 |
| `scripts/fetch_today.py` | 获取今日数据 | ✅ 可用 |
| `scripts/migrate_csv_to_sqlite.py` | CSV迁移SQLite | ✅ 可用 |
| `python -m src.data.monitor` | 数据质量监控（分钟级告警+完整性检查） | ✅ 可用 |
| `scripts/repair_data.py` | 数据修复 | ✅ 可用 |

---

## 五、🟢 策略层

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

## 六、🟠 风控层

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

## 七、💻 命令行工具

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

## 八、📊 分析脚本

| 脚本 | 用途 | 备注 |
|------|------|------|
| `scripts/analyze_volatility.py` | 波动率分析 | ✅ 可用 |
| `scripts/check_date_gaps.py` | 日期缺口检查 | ✅ 可用 |
| `scripts/compare_data.py` | 数据对比 | ✅ 可用 |
| `scripts/cross_validate_data.py` | 多源验证 | ✅ 可用 |

---

## 九、⚠️ 一次性脚本（谨慎使用）

> 这些脚本用于特定场景，执行后可能不再需要

| 脚本 | 用途 | 状态 |
|------|------|------|
| `scripts/filter_top500*.py` | ETF筛选 | 一次性 |
| `scripts/update_etf_names.py` | 更新名称 | 一次性 |
| `scripts/backup_sqlite.py` | 备份数据库 | 一次性 |
| `scripts/deduplicate_etf.py` | ETF去重 | 一次性 |

> 注: `refetch_etf_data.py` 已合并上述补数功能，支持全量/指定列表/指定时间段

---

## 十、过拟合验证工具

### 10.1 ComprehensiveValidator（综合验证）

```python
from scripts.validators import ComprehensiveValidator, OVERFIT_VALIDATION_CONFIG

# 创建验证器
validator = ComprehensiveValidator(OVERFIT_VALIDATION_CONFIG)

# 准备数据：{etf_code: df}
data = loader.load(min_rows=300)

# 准备信号函数
def my_signal(df):
    return df['close'] > df['MA20']

# 执行验证
result = validator.validate(data, my_signal)

# 检查结果
print(f"综合评分: {result['composite_score']:.2f}")
print(f"通过: {result['pass']}")
```

**返回结果**：
```python
{
    'composite_score': 0.65,
    'pass': True,
    'walk_forward': {
        'overall_pass_rate': 0.45,
        'details': [...]
    },
    'monte_carlo': {
        'significant_rate': 0.35,
        'details': {...}
    },
    'cross_etf': {
        'train_pass_rate': 0.5,
        'test_pass_rate': 0.35,
        'generalization_gap': 0.15
    }
}
```

### 10.2 单独使用各验证器

```python
from scripts.validators import (
    WalkForwardEngine,
    MonteCarloEngine,
    CrossEtfValidator
)

# 滚动窗口验证
wf = WalkForwardEngine()
wf_result = wf.validate(df, signal_func)

# 蒙特卡洛检验
mc = MonteCarloEngine()
mc_result = mc.validate(df, signal_func)

# 跨ETF泛化验证
ce = CrossEtfValidator()
ce_result = ce.validate(etf_data_dict, signal_func)
```

**文件**: `scripts/validators/`

### 10.3 快速验证脚本

```bash
# 全量验证4125个组合
python scripts/full_validation.py

# 输出: data/experiments_v8_sop/full_validation_results.json
```

---

## 十一、快速索引

| 场景 | 工具 |
|------|------|
| **写入数据** | `DataWriter.write_daily()` |
| **读取数据** | `DataLoader.load()` |
| **获取名称** | `ETFNameLoader.get_name()` |
| **获取实时数据** | `AKTools HTTP API` |
| **运行回测** | `quick_run()` |
| **风险控制** | `RiskManager` |
| **每日决策** | `python -m src.cli.main -m daily` |
| **过拟合验证** | `ComprehensiveValidator` |

---

## 十一、工作流程

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