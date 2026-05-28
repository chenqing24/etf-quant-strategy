# 工具清单

> 本文件索引项目中所有可用脚本、命令行工具和Python API
> 生成时间: 2026-05-28 | 更新: 每次添加新工具时

---

## 一、命令行工具

### 1.1 决策系统CLI

```bash
# 每日决策（工作日下午2:30执行）
python -m src.decision_cli -m daily

# 完整评估
python -m src.decision_cli -m eval

# 记录交易
python -m src.decision_cli -m trade --code 516050 --action buy --price 1.384 --quantity 13000

# 查看历史
python -m src.decision_cli -m history

# 绩效分析
python -m src.decision_cli -m perf

# 更新ETF池（每2周）
python -m src.decision_cli -m update_pool
```

**位置**: `src/decision_cli.py`

---

### 1.2 批量实验运行

```python
from src.strategy.store import quick_run

# 基本用法
r = quick_run(
    name='test',
    factors=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
    weights={'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15},
    direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'},
    stop_loss=-0.05, stop_profit=0.10, threshold=0.8, hold_days=3,
    allow_rebalance=False  # 禁止调仓
)

# 返回结果
r['train']  # 训练期结果
r['test']   # 测试期结果
r['train'].total_return  # 总收益
r['train'].sharpe_ratio  # 夏普比率
r['train'].trade_count   # 交易次数
r['train'].trade_list    # 交易记录列表
```

**位置**: `src/strategy/store.py` → `quick_run()`

---

### 1.3 配置加载器 (P0-1新增)

```python
from src.strategy import ConfigLoader, StrategyConfig

# 获取单例
loader = ConfigLoader.get_instance()

# 加载配置
config = loader.load("config/strategies/exp50.yaml")

# 加载默认配置
config = loader.load_default()

# 列出所有可用策略
strategies = ConfigLoader.list_strategies()
# ['exp50', 'exp36', 'default']

# 清除缓存
ConfigLoader.clear_cache()

# 类型安全的配置对象
config.name           # 策略名称
config.factors.enabled  # ['ADX', 'BB_percent']
config.factors.weights  # {'ADX': 0.4, ...}
config.risk.stop_loss   # -0.05
config.risk.stop_profit # 0.10
```

**错误码**:
- `ConfigNotFoundError(code=E1001)`: 配置文件不存在
- `ConfigFormatError(code=E1002)`: 配置文件格式错误
- `ConfigVersionError(code=E1003)`: 配置版本不兼容

**位置**: `src/strategy/config_loader.py`

---

### 1.4 风控管理器 (P0-2新增)

```python
from src.risk import RiskManager, Portfolio, Position

# 创建风控管理器
risk = RiskManager(
    stop_loss=-0.05,    # 止损 -5%
    stop_profit=0.10,   # 止盈 +10%
    max_position=1,     # 最多1个持仓
    max_loss=-0.15,     # 最大亏损 -15%
    hold_days=5          # 最多持仓5天
)

# 或者从配置创建
from src.risk import RiskConfig
config = RiskConfig(stop_loss=-0.05, ...)
risk = RiskManager.from_config(config)

# 检查是否可以入场
portfolio = Portfolio(positions=[], cash=10000, total_value=10000)
result = risk.check_entry(portfolio)
# result.allowed = True/False
# result.code = "E2001-01"(仓位满)/"E2001-02"(亏损超限)

# 检查是否需要退出
position = Position(code='510300', quantity=1000, avg_price=3.00, 
                     current_price=2.85, entry_date='2026-05-25')
signal = risk.check_exit(position, current_price=2.85)
# signal.reason = "stop_loss"/"stop_profit"/"hold_days"
# signal.pnl = -0.05  # 触发时的盈亏
```

**错误码**:
- `E2001-01`: 仓位已满，无法入场
- `E2001-02`: 总亏损超限，无法入场
- `E2002-01`: 止损触发
- `E2002-02`: 止盈触发
- `E2002-03`: 持仓天数到期

**位置**: `src/risk/manager.py`

---

## 二、数据采集脚本

### 2.1 每日数据检查

```bash
# 检查ETF数据完整性和质量
python scripts/daily_data_check.py

# 选项
python scripts/daily_data_check.py --verbose  # 详细输出
python scripts/daily_data_check.py --codes 510300,159806  # 指定ETF
```

**功能**:
- 检查数据缺失
- 验证数据格式
- 生成数据质量报告

---

### 2.2 数据修复

```bash
# 自动修复数据问题
python scripts/repair_data.py

# 选项
python scripts/repair_data.py --dry-run  # 预览不执行
python scripts/repair_data.py --code 510300  # 指定ETF
```

**功能**:
- 填充缺失日期
- 修复异常值
- 补全历史数据

---

### 2.3 数据交叉验证

```bash
# 多源交叉验证
python scripts/cross_validate_data.py
```

**功能**:
- 对比多个数据源
- 发现数据不一致
- 生成验证报告

---

### 2.4 数据预获取

```bash
# 收盘后预获取数据
python scripts/prefetch_data.py

# 选项
python scripts/prefetch_data.py --codes 510300,159806  # 指定ETF
python scripts/prefetch_data.py --days 30  # 获取天数
```

**功能**:
- 批量获取历史数据
- 更新SQLite缓存
- 支持并发请求

---

### 2.5 CSV迁移到SQLite

```bash
# 将CSV数据迁移到SQLite
python scripts/migrate_csv_to_sqlite.py
```

**功能**:
- 批量迁移历史数据
- 创建索引
- 验证迁移结果

---

### 2.6 历史数据补全

```bash
# 补全缺失的历史数据
python scripts/supplement_history_data.py
```

**功能**:
- 自动补全数据缺口
- 多源协调补全

---

## 三、分析脚本

### 3.1 波动率分析

```bash
# 分析ETF波动率特征
python scripts/analyze_volatility.py
```

**功能**:
- 计算波动率指标
- 识别异常波动
- 生成波动率报告

---

### 3.2 日期缺口检查

```bash
# 检查数据日期连续性
python scripts/check_date_gaps.py
```

**功能**:
- 发现缺失日期
- 标记数据断层

---

### 3.3 缺失ETF检查

```bash
# 检查ETF池覆盖情况
python scripts/check_missing_etfs.py
```

**功能**:
- 发现未覆盖ETF
- 提示数据缺失

---

### 3.4 数据对比

```bash
# 对比两个数据源
python scripts/compare_data.py
```

**功能**:
- 对比数据差异
- 生成对比报告

---

## 四、Python API

### 4.1 数据层

```python
from src.data.manager import DataFacade, HotDataManager, ColdDataManager

# 初始化
facade = DataFacade('etf_data_live')

# 热数据管理（实时数据）
hot = HotDataManager('etf_data_live')
hot_data = hot.get('510300')        # 获取单只ETF实时数据
all_hot = hot.get_all()             # 获取所有实时数据

# 冷数据管理（日线历史数据，从SQLite）
cold = ColdDataManager('etf_data_live')
daily_data = cold.get('510300', days=30)  # 获取日线数据

# 合并热数据+冷数据
merged = facade.get_merged_data('510300')  # 合并数据

# 迁移热数据到冷数据（收盘后执行）
facade.migrate()

# 获取生命周期信息
info = facade.get_lifecycle_info()  # 返回 {'stage': 'TRADING', ...}
```

**位置**: `src/data/manager.py`
**类**: `DataFacade`, `HotDataManager`, `ColdDataManager`

---

### 4.2 策略层

```python
from src.strategy.engine import BacktestEngine
from src.strategy.config import BacktestConfig

# 创建配置
config = BacktestConfig(
    threshold=0.8,
    stop_loss=-0.05,
    stop_profit=0.10,
    hold_days=3,
    allow_rebalance=False
)

# 创建引擎
engine = BacktestEngine(config)

# 运行回测
result = engine.run(data, initial_capital=20000)
```

**位置**: `src/strategy/engine.py`, `src/strategy/config.py`

---

### 4.3 评分器

```python
from src.strategy.scorer import FactorScorer

# 创建评分器
scorer = FactorScorer(factors, weights, direction)

# 计算评分
score, details = scorer.calculate(row)
```

**位置**: `src/strategy/scorer.py`

---

### 4.4 交易执行

```python
from src.strategy.executor import TradeExecutor

# 创建执行器
executor = TradeExecutor(initial_capital=20000)

# 执行买入
executor.buy('510300', price=3.50, quantity=1000, date='2026-05-28')

# 执行卖出
executor.sell('510300', price=3.70, quantity=1000, date='2026-05-28')

# 获取持仓
positions = executor.positions

# 获取绩效
perf = executor.performance()
```

**位置**: `src/strategy/executor.py`

---

## 五、目录结构

```
etf_strategy/
├── src/
│   ├── decision_cli.py       # 命令行入口
│   ├── data/
│   │   ├── manager.py        # DataFacade
│   │   └── fetcher.py        # DataSourceRouter
│   └── strategy/
│       ├── engine.py          # BacktestEngine
│       ├── config.py          # BacktestConfig
│       ├── scorer.py          # FactorScorer
│       ├── executor.py        # TradeExecutor
│       └── store.py          # quick_run
├── scripts/                  # 数据采集脚本
│   ├── daily_data_check.py
│   ├── repair_data.py
│   ├── cross_validate_data.py
│   ├── prefetch_data.py
│   ├── migrate_csv_to_sqlite.py
│   ├── supplement_history_data.py
│   ├── analyze_volatility.py
│   ├── check_date_gaps.py
│   ├── check_missing_etfs.py
│   └── compare_data.py
└── docs/
    ├── ARCHITECTURE.md       # 架构文档
    ├── INTERFACE_CONTRACT.md # 接口契约
    ├── TOOLS.md              # 本文档
    └── ...
```

---

## 六、快速索引

| 功能 | 命令/函数 | 位置 |
|------|----------|------|
| 每日决策 | `python -m src.decision_cli -m daily` | decision_cli.py |
| 批量实验 | `quick_run()` | store.py |
| 数据检查 | `python scripts/daily_data_check.py` | scripts/ |
| 数据修复 | `python scripts/repair_data.py` | scripts/ |
| 获取数据 | `facade.get_daily()` | manager.py |
| 运行回测 | `BacktestEngine.run()` | engine.py |
| 计算评分 | `FactorScorer.calculate()` | scorer.py |
| 执行交易 | `TradeExecutor.buy/sell()` | executor.py |

---

*文档版本: v1.0 | 创建: 2026-05-28*