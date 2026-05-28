# 文档与代码一致性检查报告

> 检查时间: 2026-05-28
> 检查结果: 发现不一致项需要修正

---

## 一、检查结果汇总

| 类别 | 文档描述 | 实际代码 | 状态 |
|------|----------|----------|------|
| CLI命令 | `-m daily/eval/trade/history/perf/update_pool` | ✅ 匹配 | 一致 |
| Python API | quick_run() | ✅ 存在 | 一致 |
| scripts目录 | 10个脚本 | ✅ 11个(含test_sina) | 一致 |
| DataFacade | get_hot/get_daily/get_hourly | ❌ 方法名不同 | **需修正** |
| BacktestConfig | allow_rebalance字段 | ✅ 存在 | 一致 |
| FactorScorer | calculate() | ✅ 存在 | 一致 |
| TradeExecutor | buy/sell() | ✅ 存在 | 一致 |

---

## 二、需要修正的问题

### 问题1: DataFacade方法名不匹配

**文档描述** (`docs/TOOLS.md`):
```python
facade.get_hot('510300')      # 获取实时数据
facade.get_all_hot()          # 获取所有实时数据
facade.get_daily('510300', days=30)   # 获取日线
facade.get_hourly('510300', limit=100) # 获取小时线
facade.get_merged('510300', days=30)  # 合并数据
facade.migrate()              # 迁移数据
```

**实际代码** (`src/data/manager.py`):
```python
hot_manager.get('510300')     # 获取实时数据
hot_manager.get_all()         # 获取所有实时数据
cold_manager.get('510300', days=30)   # 获取日线 (via SQLite)
# get_hourly 不存在
facade.get_merged_data('510300')      # 合并数据
facade.migrate()              # 迁移数据
```

**修正方案**: 更新 `docs/TOOLS.md` 第4.1节的方法名

---

## 三、已确认一致的部分

### 3.1 CLI命令 (✅ 一致)
```bash
python -m src.cli.decision -m daily
python -m src.cli.decision -m eval
python -m src.cli.decision -m trade --code 516050 --action buy --price 1.384 --quantity 13000
python -m src.cli.decision -m history
python -m src.cli.decision -m perf
python -m src.cli.decision -m update_pool
```

### 3.2 Python API (✅ 一致)
```python
from src.strategy.store import quick_run
r = quick_run(
    name='test',
    factors=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
    weights={'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15},
    threshold=0.8,
    allow_rebalance=False
)
```

### 3.3 scripts目录 (✅ 一致)
```
scripts/
├── analyze_volatility.py     ✅
├── check_date_gaps.py        ✅
├── check_missing_etfs.py      ✅
├── compare_data.py            ✅
├── cross_validate_data.py    ✅
├── daily_data_check.py        ✅
├── migrate_csv_to_sqlite.py   ✅
├── prefetch_data.py           ✅
├── repair_data.py             ✅
├── supplement_history_data.py ✅
└── test_sina_hourly_api.py    ✅ (额外)
```

### 3.4 模块文件 (✅ 一致)
```
src/strategy/
├── config.py      ✅ BacktestConfig
├── engine.py      ✅ BacktestEngine
├── executor.py    ✅ TradeExecutor
├── scorer.py      ✅ FactorScorer
└── store.py       ✅ quick_run
```

---

## 四、修正计划

1. 更新 `docs/TOOLS.md` 第4.1节 DataFacade 方法名
2. 更新 `docs/MODULES.md` 中的接口描述
3. 检查其他文档是否引用了旧方法名

---

*检查完成时间: 2026-05-28*