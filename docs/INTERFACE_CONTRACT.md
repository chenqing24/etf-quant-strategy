# ETF量化系统 - 接口契约文档 v2.1

> 规范模块间调用关系，解决参数传递链路长的问题
> 更新：v2.1 新增 DecisionSnapshot 接口契约（US-001 决策快照）
> v2.0：新增 DataSourceRouter 接口 + 新 DataFacade 契约 + 历史回溯边界

## 1. 核心原则

### 1.1 单一职责
每个模块只做一件事，接口清晰

### 1.2 依赖注入
通过构造函数注入依赖，而非全局状态

### 1.3 最小暴露
只暴露必要的接口，隐藏内部实现

### 1.4 禁止裸 requests（新增）
所有外部API请求必须经过 DataSourceRouter，禁止直接 requests.get

---

## 2. 模块架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      ETFDecisionEngine                      │
│                    (决策引擎 - 顶层入口)                    │
└─────────────────────┬─────────────────────────────────────┘
                      │
      ┌───────────────┼───────────────┐
      ▼               ▼               ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│ DataLayer │  │ Strategy  │  │ Notifier  │
│  数据层   │  │  策略层   │  │  通知层   │
└─────┬─────┘  └─────┬─────┘  └─────┬─────┘
      │              │              │
      ▼              ▼              ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│DataFacade │  │ Selector  │  │ DingTalk  │
│ (统一入口)│  │ Backtest  │  │  Sender   │
└─────┬─────┘  └───────────┘  └───────────┘
      │
      ▼
┌───────────────────┐     ┌─────────────────────┐
│ DataSourceRouter  │     │  External APIs      │
│  (采集层统一入口)  │ ──▶ │  (新浪/腾讯/东财)   │
└───────────────────┘     └─────────────────────┘
```

---

## 3. 数据层接口

### 3.1 DataFacade（统一入口）

```python
class DataFacade:
    """数据层唯一统一入口"""

    def get_hot(self, code: str) -> Optional[HotDataRecord]:
        """获取实时价格（热数据层）"""

    def get_all_hot(self) -> Dict[str, HotDataRecord]:
        """获取所有ETF实时价格"""

    def get_daily(self, code: str, days: int = 30) -> pd.DataFrame:
        """获取日线历史数据（冷数据层，从SQLite）"""

    def get_hourly(self, code: str, limit: int = 100) -> pd.DataFrame:
        """获取小时线数据（新浪API，缓存）"""

    def get_with_signal(self, code: str, days: int = 30) -> Dict:
        """获取日线 + 小时线信号（用于策略共振）"""

    def get_merged(self, code: str, days: int = 30) -> Dict:
        """获取合并数据（日线 + 最新热数据）"""
```

### 3.2 DataSourceRouter（采集层统一入口）

```python
class DataSourceRouter:
    """数据采集层统一入口 - 强制所有外部API请求经过此路由器"""

    def fetch_realtime(self, code: str) -> Dict:
        """获取实时价格，优先级：内存缓存 > 新浪API > 腾讯API"""

    def fetch_daily(self, code: str, source: str = "tencent") -> pd.DataFrame:
        """获取日线数据，优先级：SQLite缓存 > 腾讯API"""

    def fetch_hourly(self, code: str, limit: int = 1800) -> pd.DataFrame:
        """获取小时线数据，直接调新浪API"""

    def fetch_multi(self, codes: List[str], data_type: str = "realtime") -> Dict[str, Any]:
        """批量获取，支持并发（每个请求间隔2-5秒随机）"""
```

### 3.3 旧接口（兼容性保留）

```python
class DataLoader:
    """旧接口，保持向后兼容"""
    def load(self, code: str, days: int = 30) -> pd.DataFrame: ...
    def load_all(self, days: int = 30) -> Dict[str, pd.DataFrame]: ...

class HotDataManager:
    """热数据管理器（内存缓存）"""
    def get(self, code: str) -> Optional[HotDataRecord]: ...
    def get_all(self) -> Dict[str, HotDataRecord]: ...
    def refresh(self, codes: List[str]) -> None: ...

class ColdDataManager:
    """冷数据管理器（SQLite）"""
    def get(self, code: str, days: int = 30) -> Optional[pd.DataFrame]: ...
    def save(self, code: str, df: pd.DataFrame) -> None: ...
```

---

## 4. 策略层接口

### 4.1 Selector（选股器）

```python
class Selector:
    def evaluate(self, signals: Dict[str, Signal]) -> List[ETFRecommendation]:
        """
        输入: {code: Signal}
        输出: 按评分排序的ETF列表
        """
```

### 4.2 BacktestEngine（回测引擎）

```python
class BacktestEngine:
    def run(self,
            trades: List[Trade],
            prices: pd.DataFrame,
            initial_capital: float = 20000) -> BacktestResult:
        """
        输入: 交易记录、价格数据、本金
        输出: 回测绩效
        """
```

---

## 5. 数据源路由规则

### 5.1 数据类型 → 数据源映射

| 数据类型 | 主力源 | 降级源 | 回溯时长 | 请求频率 |
|---------|--------|--------|---------|---------|
| **实时价格** | 新浪 `hq.sinajs.cn` | 腾讯API | 当日 | 每分钟 |
| **ETF日线** | 腾讯API直连 | BaoStock | ~300天 | 每天1次 |
| **ETF小时线** | 新浪 `scale=30` | 无 | ~1800条/1.5年 | 每天1次 |
| **股票日线** | BaoStock | Tushare Pro | ~300天 | 每天1次 |
| **股票分钟线** | AKShare | 无 | 不稳定 | 参考用 |

### 5.2 历史回溯能力边界（实测值）

```
新浪scale=30（小时线）：
- 理论上限：1800条记录
- 实测覆盖：约340天（约11个月，偏差-37.8%）
- 边界日期：所有ETF截断到2025-06-20

腾讯API（日线）：
- 理论上限：约300个交易日
- 实际覆盖：约1年
- 支持复权：qfq后复权

BaoStock（股票日线）：
- 理论上限：约300个交易日
- 实际覆盖：约1年
```

### 5.3 新浪API小时线URL

```
https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={code}&scale=30&ma=no&datalen=1800

参数说明：
- symbol: 股票代码，sh510300
- scale: 时间周期，30=30分钟
- ma: 均线，no=无
- datalen: 获取条数，最多1800条
```

---

## 6. 错误处理

### 6.1 超时处理

```python
# 实时价格：超时3秒，降级到下一个数据源
# 日线数据：超时10秒，使用缓存数据（可能过期）
# 小时线数据：超时15秒，跳过本次更新
```

### 6.2 重试策略

```python
# 指数退避：第1次失败等待2秒，第2次等待4秒，第3次等待8秒
# 最多重试3次，超过则记录日志并降级
```

---

## 7. 采集层约束

### 7.1 随机等待策略

```python
import random
import time

def random_wait():
    """随机等待2-5秒，避免限流"""
    wait_time = random.uniform(2, 5)
    time.sleep(wait_time)

# 所有外部API请求前必须调用
random_wait()
```

### 7.2 缓存策略

```python
# 实时价格：5分钟TTL
# 日线数据：当天内不重复请求
# 小时线数据：每天收盘后请求一次
```

---

## 8. 接口变更日志

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2025-05-24 | 初始版本：DataLoader/DataFacade |
| v2.0 | 2026-05-26 | 新增DataSourceRouter + 历史回溯边界 |
| v2.1 | 2026-06-10 | 新增DecisionSnapshot接口契约（US-001决策快照）|

---

## 9. DecisionSnapshot 接口契约（US-001）

> **模块路径**：`src/trade/decision_snapshot.py`（US-003 实现）
> **存储位置**：SQLite `etf.db` 的 `decision_snapshot` 表（schema 007）

### 9.1 类签名

```python
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class DecisionSnapshot:
    """决策快照数据类 - US-001 决策快照持久化"""

    # ===== 必填字段 =====
    snapshot_time: str             # ISO 8601 时间戳 "2026-06-10T10:30:00"
    code: str                      # ETF代码 '159611'
    action: str                    # 'buy' / 'sell'
    cost: float                    # 决策时价格（cost basis）

    # ===== Target / Stop 价格（v1.1 必填）=====
    target_price: float            # 目标价 = cost × (1 + stop_gain)
    stop_loss_price: float         # 止损价 = cost × (1 + stop_loss)
    stop_profit_price: float       # 止盈价（冗余）
    risk_reward_ratio: float       # 盈亏比
    max_hold_days: int             # 计划持仓天数

    # ===== 决策上下文（Q-009 必填）=====
    model_name: str                # 模型名 'ETF量化决策v8_sop'
    strategy_json: str             # strategy 配置（JSON 字符串）
    evaluation_json: str           # evaluation 指标（JSON 字符串）

    # ===== 可选字段 =====
    rationale: Optional[str] = None        # 决策理由（人工注释）
    id: Optional[int] = None               # 数据库自增 ID（写入后填充）
    created_at: Optional[str] = None       # 数据库写入时间（自动填充）

    # ===== 关联字段（不入库）=====
    snapshot_ref: Optional[str] = None     # 反向引用（"snapshot:{id}"）
```

### 9.2 Repository 类接口

```python
class DecisionSnapshotRepository:
    """决策快照仓储类 - SQLite 持久化"""

    def save(self, snapshot: DecisionSnapshot) -> int:
        """保存决策快照，返回 id
        - 自动设置 created_at
        - 返回自增主键
        """

    def get_by_id(self, snapshot_id: int) -> Optional[DecisionSnapshot]:
        """按 ID 查询单个快照"""

    def get_by_code(self, code: str, limit: int = 50) -> List[DecisionSnapshot]:
        """按 ETF 代码查询（按时间倒序）"""

    def get_by_time_range(self, start: str, end: str) -> List[DecisionSnapshot]:
        """按时间范围查询（snapshot_time BETWEEN）"""

    def list_recent(self, limit: int = 100) -> List[DecisionSnapshot]:
        """查询最近的 N 条快照（用于调试/复盘）"""

    def delete(self, snapshot_id: int) -> bool:
        """删除快照（谨慎使用，通常只用于测试清理）"""
```

### 9.3 工厂函数

```python
def make_snapshot_from_strategy(
    code: str,
    action: str,
    cost: float,
    strategy: dict,
    evaluation: dict,
    rationale: Optional[str] = None,
) -> DecisionSnapshot:
    """从 strategy 配置自动计算 target/stop，构造 DecisionSnapshot

    计算逻辑：
      target_price     = cost × (1 + strategy.risk_control.stop_gain)
      stop_loss_price  = cost × (1 + strategy.risk_control.stop_loss)
      stop_profit_price = target_price
      risk_reward_ratio = (target - cost) / (cost - stop_loss)
      max_hold_days    = strategy.risk_control.max_hold_days
    """
```

### 9.4 与 TradeRecord 的关系

| 维度 | TradeRecord | DecisionSnapshot |
|------|-------------|------------------|
| 存储表 | trade_history | decision_snapshot |
| 创建时机 | 实际成交时 | 决策生成时 |
| 价格字段 | price（成交价）| cost（决策时价）|
| target/stop | 5 字段（schema 006）| 5 字段 |
| 关联方式 | snapshot_ref = "snapshot:{id}" | id 自增 |
| 写入顺序 | 1. save snapshot → 2. save trade | trade 引用 snapshot.id |

### 9.5 使用示例

```python
from src.trade.decision_snapshot import (
    DecisionSnapshot, DecisionSnapshotRepository, make_snapshot_from_strategy
)

# 1. 构造（自动计算 target/stop）
strategy = {"risk_control": {"stop_gain": 0.10, "stop_loss": -0.06, "max_hold_days": 15}}
snapshot = make_snapshot_from_strategy(
    code="159611",
    action="buy",
    cost=1.251,
    strategy=strategy,
    evaluation={"avg_sharpe": 1.408, "model_version": "v8_sop"},
    rationale="MA20 突破 + 量能放大",
)

# 2. 持久化
repo = DecisionSnapshotRepository()
snapshot_id = repo.save(snapshot)

# 3. 写入 trade（关联快照）
trade = TradeRecord(
    code="159611", price=1.251, ..., snapshot_ref=f"snapshot:{snapshot_id}",
    target_price=snapshot.target_price,
    stop_loss_price=snapshot.stop_loss_price,
    ...
)

# 4. 查询（复盘）
recent = repo.list_recent(limit=10)
for s in recent:
    print(f"{s.snapshot_time} {s.code} {s.action} target={s.target_price}")
```

### 9.6 错误处理

| 场景 | 行为 |
|------|------|
| strategy 缺少 risk_control | 抛 `ValueError("strategy.risk_control 必填")` |
| cost ≤ 0 | 抛 `ValueError("cost 必须为正")` |
| action 不是 buy/sell | 抛 `ValueError("action 必须是 buy 或 sell")` |
| 数据库写入失败 | 抛 `sqlite3.Error`（事务回滚）|
| snapshot_ref 格式错误 | 查询时返回 None（不抛错）|

### 9.7 测试要求（US-003）

- 单元测试：构造、计算、序列化（10+ 用例）
- 集成测试：save/get/list/delete（8+ 用例）
- 边界测试：cost=0 / stop_loss 接近 cost / max_hold_days=0

---