# ETF量化系统 - 执行层架构

> 策略到交易的最后一公里

## 1. 概述

### 1.1 定义
执行层负责将策略信号转化为实际交易动作，是量化系统的核心出口。

### 1.2 目标
- **可靠**：信号到执行的转化不能丢失
- **快速**：减少信号到成交的延迟
- **可追溯**：每笔交易都有完整的上下文

### 1.3 范围

```
策略层 → 信号生成 → 执行层 → 券商API → 交易所
           ↓
      [执行层内部]
           ↓
    信号确认 → 订单生成 → 订单执行 → 成交回报
```

---

## 2. 执行流程

### 2.1 标准执行流程

```
T+0 14:25
  │
  ▼
┌─────────────────────┐
│  1. 信号生成        │
│     decision_cli    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  2. 信号确认        │
│     用户手动确认    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  3. 订单生成        │
│     TradeGenerator  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  4. 订单执行        │
│     BrokerAPI      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  5. 成交回报        │
│     记录到trades   │
└─────────────────────┘
```

### 2.2 执行模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **手动执行** | 用户看到信号后手动操作 | 当前实现 |
| **半自动** | 确认后自动执行 | 下一阶段 |
| **全自动** | 信号直接执行 | 最终目标 |

---

## 3. 模块设计

### 3.1 SignalGenerator

```python
@dataclass
class Signal:
    """交易信号"""
    code: str
    name: str
    action: Literal['buy', 'sell']
    price: float
    quantity: int
    reason: str
    timestamp: str
    priority: int = 0  # 优先级，越高越优先

class SignalGenerator:
    """信号生成器"""
    
    def generate(self, decision: DecisionResult) -> Signal:
        """从决策结果生成交易信号"""
        pass
    
    def validate(self, signal: Signal) -> bool:
        """验证信号合法性"""
        # 数量检查：至少100股
        # 价格检查：非零
        # 代码检查：6位数字
        pass
```

### 3.2 TradeGenerator

```python
@dataclass
class Order:
    """订单"""
    order_id: str              # 订单号
    code: str                  # ETF代码
    action: str                # buy/sell
    price: float               # 委托价格
    quantity: int              # 委托数量
    order_type: str            # limit/market
    status: str                # pending/filled/cancelled
    created_at: str
    filled_at: Optional[str] = None

class TradeGenerator:
    """订单生成器"""
    
    def __init__(self, config: BrokerConfig):
        self.broker = BrokerAPI(config)
    
    def create_order(self, signal: Signal) -> Order:
        """从信号创建订单"""
        pass
    
    def calculate_quantity(self, signal: Signal, capital: float) -> int:
        """计算买入数量
        
        规则：
        - 按信号价格计算最大可买数量
        - 向下取整到100股（ETF最小单位）
        - 预留手续费
        """
        max_qty = int(capital / signal.price / 100) * 100
        fee = capital * 0.0003  # 万三手续费
        return int((capital - fee) / signal.price / 100) * 100
```

### 3.3 BrokerAPI（券商接口）

```python
class BrokerAPI:
    """券商交易接口（抽象层）"""
    
    def __init__(self, config: BrokerConfig):
        self.config = config
        self.session = None
    
    def connect(self) -> bool:
        """连接券商"""
        pass
    
    def disconnect(self):
        """断开连接"""
        pass
    
    def place_order(self, order: Order) -> str:
        """下单，返回订单号"""
        pass
    
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        pass
    
    def query_order(self, order_id: str) -> OrderStatus:
        """查询订单状态"""
        pass
    
    def query_position(self) -> List[Position]:
        """查询持仓"""
        pass
    
    def query_balance(self) -> Balance:
        """查询资金"""
        pass
```

### 3.4 PositionManager

```python
class PositionManager:
    """持仓管理器"""
    
    def __init__(self, tracker: TradeTracker):
        self.tracker = tracker
    
    def get_position(self, code: str) -> Optional[Position]:
        """获取持仓"""
        pass
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        pass
    
    def update_position(self, code: str, filled: Order):
        """更新持仓（成交后调用）"""
        pass
    
    def check_risk(self, code: str) -> RiskResult:
        """风控检查
        
        返回：
        - 是否需要止损
        - 是否需要止盈
        - 是否需要移动止盈
        """
        pass
```

---

## 4. 风控规则

### 4.1 止损规则

```python
class StopLossRule:
    """止损规则"""
    
    DEFAULT_THRESHOLD = -0.05  # -5%
    
    def should_trigger(self, position: Position) -> bool:
        """是否触发止损"""
        return position.pnl_pct <= self.threshold
    
    def get_stop_price(self, entry_price: float) -> float:
        """计算止损价"""
        return entry_price * (1 + self.threshold)
```

### 4.2 止盈规则

```python
class StopGainRule:
    """止盈规则"""
    
    DEFAULT_THRESHOLD = 0.08  # +8%
    
    def should_trigger(self, position: Position) -> bool:
        """是否触发止盈"""
        return position.pnl_pct >= self.threshold
```

### 4.3 移动止盈规则

```python
class TrailingStopRule:
    """移动止盈规则"""
    
    def __init__(self, threshold: float = 0.10, trailing: float = 0.04):
        self.threshold = threshold   # 盈利达到10%后激活
        self.trailing = trailing     # 回撤4%触发
    
    def should_activate(self, position: Position) -> bool:
        """是否激活"""
        return position.pnl_pct >= self.threshold
    
    def should_trigger(self, position: Position) -> bool:
        """是否触发"""
        if not self.should_activate(position):
            return False
        
        peak = position.peak_pnl_pct  # 历史最高盈利
        return (peak - position.pnl_pct) >= self.trailing
```

---

## 5. 订单类型

### 5.1 限价单

```python
order = Order(
    order_type='limit',
    price=1.101,        # 限价
    quantity=15000,
)
```

### 5.2 市价单

```python
order = Order(
    order_type='market',
    quantity=15000,
)
```

### 5.3 条件单

```python
order = Order(
    order_type='conditional',
    trigger_price=1.046,  # 触发价
    price=1.046,           # 触发后委托价
    quantity=15000,
)
```

---

## 6. 状态机

### 6.1 订单状态

```
pending → submitted → partial → filled
    │           │
    └───────────┴──→ cancelled → rejected
```

| 状态 | 说明 |
|------|------|
| pending | 等待提交 |
| submitted | 已提交到券商 |
| partial | 部分成交 |
| filled | 全部成交 |
| cancelled | 用户撤单 |
| rejected | 订单被拒绝 |

### 6.2 信号状态

```
generated → confirmed → executing → executed
     │            │           │
     └────────────┴─────→ cancelled
```

---

## 7. 错误处理

### 7.1 错误分类

| 错误类型 | 处理策略 |
|----------|----------|
| 网络断开 | 重试3次，间隔5秒 |
| 券商系统繁忙 | 重试3次，间隔10秒 |
| 资金不足 | 记录并告警，人工确认 |
| 持仓不足 | 记录并告警，人工确认 |
| 价格超限 | 重新计算价格 |

### 7.2 重试机制

```python
class RetryPolicy:
    """重试策略"""
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def execute(self, func, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except NetworkError as e:
                if attempt == self.max_retries - 1:
                    raise
                sleep(5 * (attempt + 1))  # 指数退避
```

---

## 8. 实现路线图

### 8.1 Phase 1: 手动执行（当前）

```
信号生成 → 用户手动操作 → 记录到 trades.json
```

### 8.2 Phase 2: 半自动

```
信号生成 → 钉钉确认 → 自动记录交易
```

### 8.3 Phase 3: 自动执行

```
信号生成 → 自动下单 → 成交回报 → 更新持仓
```

---

## 9. 修订历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-26 | v1.0 | 初始版本 |