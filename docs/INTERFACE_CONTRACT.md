# ETF量化系统 - 接口契约文档 v2.0

> 规范模块间调用关系，解决参数传递链路长的问题
> 更新：新增 DataSourceRouter 接口 + 新 DataFacade 契约 + 历史回溯边界

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