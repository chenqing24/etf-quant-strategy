# 模块说明

> 描述每个模块的职责、接口和依赖关系
> 生成时间: 2026-05-28 | 参考: INTERFACE_CONTRACT.md

---

## 一、模块依赖图

```
┌─────────────────────────────────────────────────────────────┐
│                    decision_cli.py                          │
│                    (命令行入口)                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ETFDecisionEngine                        │
│                    (决策引擎 - 顶层)                         │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌───────────────┐  ┌─────────────────┐  ┌───────────────┐
│   DataLayer   │  │    Strategy     │  │   Notifier    │
│    数据层      │  │     策略层       │  │    通知层      │
└───────┬───────┘  └────────┬────────┘  └───────┬───────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐  ┌─────────────────┐  ┌───────────────┐
│  DataFacade   │  │     Selector    │  │   DingTalk    │
│  (统一入口)   │  │    (选股器)     │  │   (钉钉)      │
└───────┬───────┘  └────────┬────────┘  └───────────────┘
        │                    │
        ▼                    ▼
┌─────────────────────────┐  ┌─────────────────┐
│   DataSourceRouter      │  │  BacktestEngine │
│   (采集层统一入口)       │  │   (回测引擎)    │
└────────────┬────────────┘  └────────┬────────┘
             │                         │
             ▼                         ▼
┌─────────────────────────┐  ┌─────────────────┐
│  External APIs         │  │    执行器        │
│  (新浪/腾讯/东财)       │  │  Executor       │
└─────────────────────────┘  └─────────────────┘
```

---

## 二、数据层 (DataLayer)

### 2.1 DataFacade

**文件**: `src/data/manager.py`

**职责**: 数据层唯一统一入口，封装热数据/冷数据切换逻辑

```python
class DataFacade:
    """数据层唯一统一入口"""
    
    def get_merged_data(self, code: str) -> Dict[str, Any]:
        """获取合并数据（日线 + 最新热数据）"""
    
    def migrate(self) -> Dict[str, str]:
        """热数据迁移到冷数据（收盘后执行）"""
    
    def get_lifecycle_info(self) -> Dict[str, Any]:
        """获取生命周期信息"""
    
    def is_trading_time(self) -> bool:
        """判断是否在交易时间"""

class HotDataManager:
    """热数据管理器（内存缓存）"""
    
    def get(self, code: str) -> Optional[HotDataRecord]:
        """获取单只ETF实时数据"""
    
    def get_all(self) -> Dict[str, HotDataRecord]:
        """获取所有ETF实时数据"""
    
    def set(self, code: str, data: Dict[str, Any]):
        """设置实时数据"""
    
    def clear(self):
        """清空缓存"""

class ColdDataManager:
    """冷数据管理器（SQLite）"""
    
    def get(self, code: str, days: int = 30) -> Optional[pd.DataFrame]:
        """获取日线历史数据"""
    
    def exists(self, code: str) -> bool:
        """检查ETF是否存在"""
```

**依赖**: DataSourceRouter

**调用方**: decision_cli.py, ETFDecisionEngine

---

### 2.2 DataSourceRouter

**文件**: `src/data/fetcher.py`

**职责**: 所有外部API请求的统一入口，带缓存和限速

```python
class DataSourceRouter:
    """数据采集层统一入口"""
    
    def fetch_realtime(self, code: str) -> Dict:
        """获取实时价格，优先级：内存缓存 > 新浪API > 腾讯API"""
    
    def fetch_daily(self, code: str, source: str = "tencent") -> pd.DataFrame:
        """获取日线数据，优先级：SQLite缓存 > 腾讯API"""
    
    def fetch_hourly(self, code: str, limit: int = 1800) -> pd.DataFrame:
        """获取小时线数据，直接调新浪API"""
    
    def fetch_multi(self, codes: List[str], data_type: str = "realtime") -> Dict[str, Any]:
        """批量获取，支持并发（每个请求间隔2-5秒随机）"""
```

**约束**:
- 所有请求经过 RateLimiter(2-5秒随机等待)
- 所有请求带5分钟缓存TTL
- 主源失败自动切换备源

---

## 三、策略层 (Strategy)

### 3.1 BacktestEngine

**文件**: `src/strategy/engine.py`

**职责**: 回测引擎，执行策略逻辑

```python
class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        """初始化引擎"""
    
    def run(self, data: pd.DataFrame, initial_capital: float = 20000) -> BacktestResult:
        """
        运行回测
        
        参数:
            data: 日线数据 (必须包含: code, date, open, high, low, close, volume)
            initial_capital: 初始资金
            
        返回:
            BacktestResult: 回测结果
        """
    
    def calculate_metrics(self, trades: List[Trade]) -> Dict:
        """计算绩效指标"""
```

**依赖**: BacktestConfig, FactorScorer, TradeExecutor

---

### 3.2 BacktestConfig

**文件**: `src/strategy/config.py`

**职责**: 回测配置管理

```python
class BacktestConfig:
    """回测配置"""
    
    # 评分相关
    threshold: float = 0.8           # 入场阈值
    weights: Dict[str, float]       # 因子权重
    direction: Dict[str, str]      # 因子方向
    
    # 风控相关
    stop_loss: float = -0.05       # 止损线
    stop_profit: float = 0.10      # 止盈线
    
    # 持仓相关
    hold_days: int = 3             # 最大持仓天数
    allow_rebalance: bool = False  # 是否允许调仓
    
    # 数据相关
    start_date: str = "2019-01-01" # 回测开始日期
    end_date: str = "2026-05-28"   # 回测结束日期
```

---

### 3.3 FactorScorer

**文件**: `src/strategy/scorer.py`

**职责**: 计算因子综合评分

```python
class FactorScorer:
    def __init__(self, factors: List[str], weights: Dict, direction: Dict):
        """
        参数:
            factors: 因子列表 ['ADX', 'BB_percent', ...]
            weights: 因子权重 {'ADX': 0.5, ...}
            direction: 因子方向 {'ADX': 'long', 'BB_percent': 'long', ...}
        """
    
    def calculate(self, row: pd.Series) -> Tuple[float, Dict]:
        """
        计算单只ETF的评分
        
        返回:
            score: 综合评分 (0-1)
            details: 详细分解 {'ADX': 0.8, 'BB_percent': 0.6, ...}
        """
    
    def get_signal(self, row: pd.Series) -> str:
        """获取交易信号: 'buy', 'sell', 'hold'"""
```

**依赖**: 因子计算指标

---

### 3.4 TradeExecutor

**文件**: `src/strategy/executor.py`

**职责**: 交易执行和持仓管理

```python
class TradeExecutor:
    def __init__(self, initial_capital: float = 20000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # {code: {'quantity': 1000, 'avg_price': 3.50, ...}}
    
    def buy(self, code: str, price: float, quantity: int, date: str):
        """买入"""
    
    def sell(self, code: str, price: float, quantity: int, date: str, reason: str = ""):
        """卖出"""
    
    def check_and_close(self, code: str, price: float, date: str, reason: str = ""):
        """检查并平仓（止损/止盈/到期）"""
    
    def get_trades(self) -> List[Trade]:
        """获取交易记录"""
    
    def performance(self) -> Dict:
        """计算绩效"""
```

**约束**:
- 单一持仓（同时最多持有1只ETF）
- 自动计算持仓盈亏

---

### 3.5 quick_run (便捷函数)

**文件**: `src/strategy/store.py`

**职责**: 快速运行单个实验

```python
def quick_run(
    name: str,
    factors: List[str],
    weights: Dict[str, float],
    direction: Dict[str, str],
    stop_loss: float = -0.05,
    stop_profit: float = 0.10,
    threshold: float = 0.8,
    hold_days: int = 3,
    allow_rebalance: bool = False,
    start_date: str = "2019-01-01",
    end_date: str = "2024-12-31"
) -> Dict[str, BacktestResult]:
    """
    快速运行实验
    
    返回:
        {'train': BacktestResult, 'test': BacktestResult}
        
    BacktestResult属性:
        total_return: 总收益
        annual_return: 年化收益
        sharpe_ratio: 夏普比率
        max_drawdown: 最大回撤
        trade_count: 交易次数
        win_rate: 胜率
        trade_list: 交易记录列表
    """
```

---

## 四、通知层 (Notifier)

### 4.1 DingTalk

**文件**: `src/dingtalk_sender.py` 或通过 skill

**职责**: 钉钉消息推送

```python
def send_message(content: str, at_mobiles: List[str] = None):
    """发送钉钉消息"""
```

---

## 五、CLI入口

### 5.1 decision_cli

**文件**: `src/decision_cli.py`

**职责**: 命令行入口，分发命令到各模块

```python
# 模式
-m daily     # 每日决策
-m eval      # 完整评估
-m trade     # 记录交易
-m history   # 查看历史
-m perf      # 绩效分析
-m update_pool  # 更新ETF池
```

---

## 六、模块间契约

| 调用方 | 被调用 | 接口 | 说明 |
|--------|--------|------|------|
| decision_cli | ETFDecisionEngine | `run()` | 执行决策 |
| ETFDecisionEngine | DataFacade | `get_merged()` | 获取数据 |
| ETFDecisionEngine | BacktestEngine | `run()` | 评估策略 |
| BacktestEngine | FactorScorer | `calculate()` | 计算评分 |
| BacktestEngine | TradeExecutor | `buy/sell()` | 执行交易 |
| DataFacade | DataSourceRouter | `fetch_*()` | 采集数据 |

---

## 七、约束规则

### 7.1 数据约束
- 所有外部API请求必须经过 DataSourceRouter
- 禁止裸 `requests.get()`
- 所有请求带随机2-5秒等待

### 7.2 策略约束
- 单一持仓（同时最多1只ETF）
- 止损/止盈触发后立即执行
- 持仓天数到达上限强制平仓

### 7.3 接口约束
- 禁止跨层直接调用（如CLI不能直接调DataSourceRouter）
- 必须通过统一入口

---

*文档版本: v1.0 | 创建: 2026-05-28 | 参考: INTERFACE_CONTRACT.md*