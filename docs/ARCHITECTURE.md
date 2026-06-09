# 热冷数据分离架构

> US-002 数据分层管理方案 | ETF量化决策系统

## 1. 概述

本架构将数据分为两层分离管理：
- **热数据层 (Hot)**: 今日实时价格，盘中持续更新
- **冷数据层 (Cold)**: 历史收盘数据，归档后不修改

## 2. 目录结构

```
etf_data_live/
├── hot/                    # 热数据层（每日重建）
│   ├── 510300.json        # 实时价格，含时间戳
│   ├── 510500.json
│   └── ...
├── cold/                   # 冷数据层（持续累积）
│   ├── 510300.csv         # 历史收盘数据
│   ├── 510500.csv
│   └── ...
├── today_realtime.json     # 今日实时汇总
├── etf_trades.json         # 交易记录
└── etf_performance.json    # 绩效数据
```

## 3. 数据格式

### 热数据 (JSON)
```json
{
  "code": "510300",
  "price": 3.856,
  "change_pct": 1.23,
  "volume": 1234567,
  "timestamp": "2026-05-25T14:30:00"
}
```

### 冷数据 (CSV)
```csv
date,open,high,low,close,volume
2026-05-22,3.80,3.85,3.78,3.82,987654
2026-05-23,3.82,3.90,3.81,3.88,1234567
2026-05-25,3.88,3.90,3.85,3.86,1500000
```

## 4. 生命周期阶段

```
┌─────────────────────────────────────────────────────────────┐
│                    数据生命周期                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   [9:30]          [15:00]         [15:30]        [次日9:30] │
│      │               │              │               │      │
│      ▼               ▼              ▼               ▼      │
│  ┌────────┐    ┌──────────┐   ┌─────────┐   ┌───────────┐  │
│  │ TRADE  │───▶│ CLOSING  │──▶│MIGRATED │───▶│  NEW DAY  │  │
│  │ 盘中   │    │ 收盘确认  │   │  已归档  │   │  重置热层  │  │
│  └────────┘    └──────────┘   └─────────┘   └───────────┘  │
│      │               │              │               │      │
│      ▼               ▼              ▼               ▼      │
│   热数据更新    等待确认        迁移至冷层      热层重建    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 阶段说明

| 阶段 | 时间 | 行为 |
|------|------|------|
| TRADING_HOUR | 9:30-15:00 | 热数据持续更新，价格随行情变动 |
| CLOSING | 15:00-15:30 | 收盘确认，等待最终价格 |
| MIGRATED | 15:30后 | 热数据迁移至冷数据层，热数据清空 |
| NEW_TRADING_DAY | 次日9:30 | 热数据层重建，开始新交易日 |

## 5. 核心类设计

### HotDataManager

```python
class HotDataManager:
    def get(code: str) -> Optional[HotDataRecord]  # 获取热数据
    def set(code: str, data: Dict) -> None         # 更新热数据
    def clear() -> None                            # 清空热数据
    def count() -> int                             # 热数据条数
```

**存储位置**: `etf_data_live/hot/*.json`

### ColdDataManager

```python
class ColdDataManager:
    def get(code: str) -> Optional[List[Dict]]      # 获取历史数据
    def append(code: str, data: Dict) -> None      # 追加归档数据
    def exists(code: str) -> bool                  # 检查是否存在
```

**存储位置**: `etf_data_live/cold/*.csv`

### DataFacade (统一接口)

```python
class DataFacade:
    # 属性
    hot: HotDataManager       # 热数据管理器
    cold: ColdDataManager    # 冷数据管理器
    
    # 方法
    def get_merged_data(code: str) -> Dict        # 合并热冷数据
    def migrate() -> Dict[str, str]              # 触发热→冷迁移
    def get_lifecycle_info() -> Dict             # 获取生命周期状态
    def is_trading_time() -> bool                # 判断是否交易时间
```

## 6. 合并数据逻辑

评分时使用 `get_merged_data(code)` 获取数据：

```
1. 取冷数据作为基础（date, open, high, low, close, volume）
2. 热数据存在时，覆盖以下字段：
   - price（最新价）
   - change_pct（涨跌幅）
   - volume（成交量）
   - close（收盘价用热数据价格）
3. 热数据不存在时，仅使用冷数据
```

## 7. 迁移流程

### 触发条件
- 自动：15:30后定时任务触发
- 手动：调用 `facade.migrate()`

### 执行步骤
```
1. 检查当前生命周期阶段
2. 遍历热数据目录所有 .json 文件
3. 对每个文件：
   a. 读取热数据记录
   b. 构建冷数据格式（date=今日, close=热数据price）
   c. 追加/更新到对应的 cold/*.csv
4. 清空热数据目录
5. 更新生命周期状态为 MIGRATED
```

## 8. 使用示例

```python
from src.data_manager import DataFacade

# 初始化
facade = DataFacade('etf_data_live')

# 盘中：更新热数据
facade.hot.set('510300', {
    'price': 3.856,
    'change_pct': 1.23,
    'volume': 1234567
})

# 评分：合并热冷数据
data = facade.get_merged_data('510300')

# 收盘后：迁移数据
results = facade.migrate()

# 查看状态
lifecycle = facade.get_lifecycle_info()
```

## 9. 与现有系统集成

### 数据采集（data_fetcher.py）
```python
# 盘中采集后更新热数据
fetcher = TencentETFetcher('etf_data_live')
data = fetcher.fetch_realtime('510300')
facade = DataFacade('etf_data_live')
facade.hot.set('510300', data)
```

### 评分系统（realtime_score.py）
```python
# 评分时使用合并数据
facade = DataFacade('etf_data_live')
for code in etf_codes:
    data = facade.get_merged_data(code)
    score = calculate_7_factor_score(data)
```

### 定时任务（cron）
```bash
# 每日收盘后迁移
30 15 * * 1-5 cd /path/etf_strategy && python -c "
from src.data_manager import DataFacade
DataFacade('etf_data_live').migrate()
"
```

## 10. 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/data_manager.py` | Python | 热冷数据管理器实现 |
| `etf_data_live/hot/` | 目录 | 热数据存储（JSON） |
| `etf_data_live/cold/` | 目录 | 冷数据存储（CSV） |
| `docs/ARCHITECTURE.md` | 文档 | 本文档 |

## 11. 验收标准

- [x] `data_manager.py` 存在且包含 `HotDataManager` 和 `ColdDataManager` 类
- [x] `DataFacade.get_merged_data()` 能合并热冷数据
- [x] `DataFacade.migrate()` 能触发热→冷迁移
- [x] 生命周期包含：盘中更新 → 收盘确认 → 归档
- [x] 文档 `docs/ARCHITECTURE.md` 存在

---

*文档版本: v1.0 | 创建日期: 2026-05-25*