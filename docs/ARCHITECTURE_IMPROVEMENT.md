# ETF量化系统 - 架构改进建议

> 参考: Backtrader/Zipline/Aqquant等成熟量化框架
> 更新: 2026-05-28

---

## 一、成熟量化系统架构特点

### 1.1 Backtrader架构
```
┌─────────────────────────────────────────────────────────────┐
│                     Cerebro (大脑)                          │
│  - 加载数据 (Data Feeds)                                    │
│  - 添加策略 (Strategies)                                    │
│  - 添加经纪人 (Broker)                                      │
│  - 执行分析 (Analyzers)                                     │
└─────────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
    ┌────────┐    ┌──────────┐   ┌──────────┐
    │Data Feed│    │ Strategy │   │ Observer │
    │ (数据) │    │ (策略)   │   │ (观察者) │
    └────────┘    └──────────┘   └──────────┘
         │              │              │
         ▼              ▼              ▼
    ┌────────┐    ┌──────────┐   ┌──────────┐
    │ Store  │    │   Next   │   │ Indicators│
    │ (存储) │    │ (下一步) │   │ (指标)    │
    └────────┘    └──────────┘   └──────────┘
```

**关键设计**:
- **事件驱动**: 每个bar触发`next()`回调
- **数据与策略解耦**: Data Feed可插拔
- **Broker独立**: 模拟/实盘切换
- **观察者模式**: 实时监控和通知

### 1.2 Zipline架构
```
┌─────────────────────────────────────────────────────────────┐
│                   Pipeline (数据管道)                       │
│  - 自定义因子 (Custom Factors)                             │
│  - 数据清洗 (Data Cleaning)                                │
│  - 因子计算 (Factor Computation)                           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Algo Engine (算法引擎)                    │
│  - initialize() 初始化                                     │
│  - handle_data() 每日处理                                  │
│  - before_trading_start() 开盘前                           │
│  - record() 记录指标                                       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Risk Manager (风险管理)                   │
│  - 仓位限制 (Position Limits)                              │
│  - 亏损限制 (Loss Limits)                                  │
│  - 相关性限制 (Correlation Limits)                         │
└─────────────────────────────────────────────────────────────┘
```

**关键设计**:
- **Pipeline模式**: 数据处理流水线
- **生命周期钩子**: initialize/handle_data/before_trading_start
- **风险管理独立**: 内置风控模块

### 1.3 成熟系统通用特征

| 特征 | 说明 |
|------|------|
| 事件驱动 | 基于时间/数据事件触发策略 |
| 配置外部化 | YAML/JSON配置文件 |
| 模块可插拔 | 数据源/策略/经纪人可替换 |
| 风控独立 | 风险管理独立模块 |
| 日志完善 | 结构化日志 + 指标追踪 |
| 异常处理 | 熔断/重试/降级 |
| 回测/实盘合一 | 同一套代码支持两种模式 |

---

## 二、当前架构问题分析

### 2.1 问题清单

| 问题 | 严重程度 | 说明 |
|------|----------|------|
| 策略与回测强耦合 | 🔴 高 | BacktestEngine直接调用策略逻辑 |
| 风险管理缺失 | 🔴 高 | 无独立风控模块，止损/止盈硬编码 |
| 配置分散 | 🟡 中 | 配置分散在config.py各参数中 |
| 异常处理薄弱 | 🟡 中 | 无熔断/降级机制 |
| 日志不结构化 | 🟡 中 | 日志缺少请求ID/追踪ID |
| 数据加载不统一 | 🟡 中 | 多处直接调用API |
| 回测/实盘代码不共用 | 🟡 中 | 决策代码可能与回测不同 |

### 2.2 问题详解

#### 问题1: 策略与回测强耦合
```python
# 当前设计
class BacktestEngine:
    def run(self, data, config):
        # 策略逻辑内嵌在引擎中
        for bar in data:
            score = self.scorer.calculate(bar)
            if score > threshold:
                self.executor.buy(...)
```

#### 问题2: 风险管理缺失
```python
# 当前设计 - 风控逻辑散落各处
# 1. executor.py 中有止损/止盈
# 2. engine.py 中有持仓天数检查
# 3. 无统一风控模块
```

#### 问题3: 配置外部化程度低
```python
# 当前设计 - 配置在代码中
config = BacktestConfig(
    threshold=0.8,
    stop_loss=-0.05,  # 硬编码
    stop_profit=0.10   # 硬编码
)

# 成熟设计 - 外部YAML
# config/strategy/default.yaml
strategy:
  threshold: 0.8
  risk:
    stop_loss: -0.05
    stop_profit: 0.10
    max_position: 1
```

---

## 三、改进建议

### 3.1 改进方案总览

```
当前架构                          目标架构
─────────────────────────         ─────────────────────────
CLI + Engine                      EventBus + Strategy + Broker
    │                                   │
    ▼                                   ▼
策略硬编码                         策略可插拔 (Strategy Interface)
    │                                   │
    ▼                                   ▼
风控散落各处                     RiskManager独立模块
    │                                   │
    ▼                                   ▼
配置在代码                       配置外部化 (YAML/JSON)
    │                                   │
    ▼                                   ▼
异常无处理                       熔断 + 重试 + 降级
```

### 3.2 具体改进建议

#### 改进1: 引入事件驱动架构

```python
# 改进后: 事件总线
class EventBus:
    """事件总线 - 解耦策略和数据"""
    
    def publish(self, event: Event):
        """发布事件"""
        for handler in self._handlers[event.type]:
            handler.handle(event)
    
    def subscribe(self, event_type: str, handler):
        """订阅事件"""

# 事件类型
class Event:
    BAR_DATA = "bar_data"        # 新数据
    SIGNAL = "signal"           # 交易信号
    ORDER = "order"             # 订单
    FILL = "fill"              # 成交
    RISK_ALERT = "risk_alert"   # 风控警告
```

#### 改进2: 策略接口化

```python
# 改进后: 策略接口
from abc import ABC, abstractmethod

class Strategy(ABC):
    """策略基类"""
    
    @abstractmethod
    def on_bar(self, bar: Bar):
        """每个bar触发"""
        pass
    
    @abstractmethod
    def on_signal(self, signal: Signal):
        """信号触发"""
        pass

# 具体策略
class FactorStrategy(Strategy):
    def __init__(self, factors, weights):
        self.scorer = FactorScorer(factors, weights)
    
    def on_bar(self, bar):
        score = self.scorer.calculate(bar)
        if score > self.threshold:
            self.emit_signal('buy', bar.code, score)
```

#### 改进3: 风控独立模块

```python
# 改进后: 风控模块
class RiskManager:
    """风险管理器"""
    
    def __init__(self, config: RiskConfig):
        self.max_position = config.max_position
        self.max_loss = config.max_loss
        self.stop_loss = config.stop_loss
        self.stop_profit = config.stop_profit
    
    def check_order(self, order: Order) -> OrderResult:
        """检查订单"""
        # 检查仓位限制
        if self.positions.count >= self.max_position:
            return OrderResult(rejected=True, reason="max_position")
        
        # 检查亏损限制
        if self.total_pnl < self.max_loss:
            return OrderResult(rejected=True, reason="max_loss")
        
        return OrderResult(rejected=False)
    
    def check_exit(self, position: Position) -> ExitSignal:
        """检查是否需要退出"""
        pnl = position.pnl_pct
        if pnl <= self.stop_loss:
            return ExitSignal(reason="stop_loss", pnl=pnl)
        if pnl >= self.stop_profit:
            return ExitSignal(reason="stop_profit", pnl=pnl)
        return None
```

#### 改进4: 配置外部化

```yaml
# config/strategy/exp50.yaml
strategy:
  name: "Exp50"
  factors:
    - ADX
    - BB_percent
    - SAR_trend
    - OBV_diff
  weights:
    ADX: 0.5
    BB_percent: 0.2
    SAR_trend: 0.15
    OBV_diff: 0.15
  threshold: 0.8

risk:
  stop_loss: -0.05
  stop_profit: 0.055
  max_position: 1
  max_loss: -0.10

execution:
  allow_rebalance: false
  hold_days: 3

data:
  start_date: "2019-01-01"
  end_date: "2024-12-31"
  initial_capital: 20000
```

```python
# 加载配置
import yaml

def load_strategy_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)
```

#### 改进5: 异常处理机制

```python
# 改进后: 异常处理
class CircuitBreaker:
    """熔断器"""
    
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "closed"  # closed/open/half_open
    
    def call(self, func, *args, **kwargs):
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half_open"
            else:
                raise CircuitOpenError()
        
        try:
            result = func(*args, **kwargs)
            if self.state == "half_open":
                self.state = "closed"
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            raise

# 使用熔断器
router_circuit = CircuitBreaker(failure_threshold=3, timeout=30)
data = router_circuit.call(router.fetch_realtime, '510300')
```

#### 改进6: 结构化日志

```python
# 改进后: 结构化日志
import structlog

logger = structlog.get_logger()

def log_signal(code, score, signal_type):
    logger.info(
        "signal_generated",
        code=code,
        score=score,
        signal_type=signal_type,
        timestamp=datetime.now().isoformat(),
        request_id=get_request_id()  # 请求追踪ID
    )

def log_trade(trade):
    logger.info(
        "trade_executed",
        code=trade.code,
        action=trade.action,
        price=trade.price,
        quantity=trade.quantity,
        pnl=trade.pnl,
        request_id=get_request_id()
    )
```

---

## 四、改进优先级

| 优先级 | 改进项 | 工作量 | 收益 |
|--------|--------|--------|------|
| P0 | 配置外部化 (YAML) | 低 | 高 |
| P0 | 风控模块独立 | 中 | 高 |
| P1 | 策略接口化 | 中 | 中 |
| P1 | 异常处理机制 | 低 | 中 |
| P2 | 事件驱动架构 | 高 | 高 |
| P2 | 结构化日志 | 低 | 中 |

---

## 五、实施建议

### 阶段1: 配置外部化 (1天)
```python
# 1. 创建 config/strategies/ 目录
# 2. 编写策略配置文件
# 3. 实现配置加载器
```

### 阶段2: 风控模块独立 (2天)
```python
# 1. 创建 src/risk/manager.py
# 2. 迁移止损/止盈逻辑
# 3. 添加仓位限制
```

### 阶段3: 策略接口化 (3天)
```python
# 1. 定义 Strategy 抽象类
# 2. 重构 FactorStrategy
# 3. 解耦 BacktestEngine
```

### 阶段4: 异常处理 (1天)
```python
# 1. 实现 CircuitBreaker
# 2. 添加重试机制
# 3. 添加降级策略
```

---

*文档版本: v1.0 | 创建: 2026-05-28*