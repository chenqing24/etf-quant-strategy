# ETF量化系统 - 架构改进设计文档 v2.0

> 状态: 待确认 | 创建: 2026-05-28

---

## 一、文档结构

```
┌─────────────────────────────────────────────────────────────┐
│                    设计文档结构                              │
├─────────────────────────────────────────────────────────────┤
│  1. 问题背景      - 为什么要改？当前问题是什么？            │
│  2. 改进方案      - 具体怎么改？涉及哪些模块？              │
│  3. 接口契约      - 模块间怎么通信？                      │
│  4. 验收标准      - 怎么判断改好了？                      │
│  5. 开发计划      - 怎么分工？时间线？                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、问题背景

### 2.1 问题清单

| ID | 问题 | 影响 | 优先级 |
|----|------|------|--------|
| P1 | 配置硬编码 | 策略参数分散在代码中，难以管理和切换 | P0 |
| P2 | 风控逻辑分散 | 止损/止盈分布在多个文件，容易遗漏 | P0 |
| P3 | 策略紧耦合 | 策略和回测引擎"焊接"，难以测试和复用 | P1 |
| P4 | 异常处理缺失 | API失败可能导致决策中断 | P1 |

### 2.2 问题详解

#### P1: 配置硬编码
```python
# 当前: config.py
class BacktestConfig:
    threshold = 0.8
    stop_loss = -0.05
    stop_profit = 0.10

# 问题:
# - 想换策略要改代码
# - 无法对比不同配置
# - 参数版本无法追溯
```

#### P2: 风控逻辑分散
```
当前代码分布:
├── src/strategy/executor.py    → 止损/止盈检查
├── src/strategy/engine.py      → 持仓天数检查
├── src/strategy/scorer.py      → 仓位限制检查
└── src/cli/decision.py         → 部分风控逻辑

问题:
- 改一个规则要改多处
- 可能改漏
- 测试不完整
```

---

## 三、改进方案

### 3.1 改进总览

```
┌─────────────────────────────────────────────────────────────┐
│                      改进后架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐  │
│   │   Config    │     │   Risk      │     │  Strategy   │  │
│   │  (配置层)   │     │  (风控层)   │     │  (策略层)   │  │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘  │
│          │                   │                   │        │
│          └───────────────────┼───────────────────┘        │
│                              │                              │
│                              ▼                              │
│                    ┌─────────────────────┐                 │
│                    │   BacktestEngine    │                 │
│                    │     (回测引擎)       │                 │
│                    └─────────────────────┘                 │
│                              │                              │
│                              ▼                              │
│                    ┌─────────────────────┐                 │
│                    │   DataFacade        │                 │
│                    │     (数据层)         │                 │
│                    └─────────────────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 P0-1: 配置外部化

#### 目标
策略配置从Python代码迁移到YAML文件

#### 目录结构
```
etf_strategy/
├── config/
│   ├── default.yaml              # 默认配置
│   └── strategies/
│       ├── exp50.yaml            # Exp50策略配置
│       ├── exp42.yaml            # Exp42策略配置
│       └── exp36.yaml            # Exp36策略配置
```

#### YAML配置格式
```yaml
# config/strategies/exp50.yaml
version: "1.0"
name: "Exp50"

# 评分因子配置
factors:
  enabled:
    - ADX
    - BB_percent
    - SAR_trend
    - OBV_diff
  weights:
    ADX: 0.5
    BB_percent: 0.2
    SAR_trend: 0.15
    OBV_diff: 0.15
  direction:
    ADX: "long"
    BB_percent: "long"
    SAR_trend: "long"
    OBV_diff: "short"

# 风控配置
risk:
  stop_loss: -0.05          # 止损5%
  stop_profit: 0.055       # 止盈5.5%
  max_position: 1          # 最大持仓1只

# 执行配置
execution:
  threshold: 0.8           # 入场阈值
  hold_days: 3             # 最大持仓天数
  allow_rebalance: false  # 不允许调仓

# 数据配置
data:
  start_date: "2019-01-01"
  end_date: "2024-12-31"
  initial_capital: 20000
```

#### 涉及的模块
| 模块 | 改动 | 说明 |
|------|------|------|
| `src/strategy/config.py` | 重构 | ConfigLoader类 |
| `src/strategy/engine.py` | 适配 | 使用新配置加载器 |
| `src/strategy/store.py` | 适配 | quick_run支持YAML路径 |
| `config/` (新增) | 新增 | 配置文件目录 |

---

### 3.3 P0-2: 风控模块独立

#### 目标
风控逻辑从分散各处集中到RiskManager类

#### 目录结构
```
etf_strategy/
├── src/
│   └── risk/
│       ├── __init__.py
│       ├── manager.py           # 风控管理器
│       ├── rules.py            # 风控规则定义
│       └── config.py           # 风控配置
```

#### 类设计

```python
# src/risk/manager.py
class RiskManager:
    """风控管理器 - 统一管理所有风控逻辑"""
    
    def __init__(self, config: RiskConfig):
        self.stop_loss = config.stop_loss
        self.stop_profit = config.stop_profit
        self.max_position = config.max_position
        self.max_loss = config.max_loss
    
    def check_entry(self, order: Order, portfolio: Portfolio) -> CheckResult:
        """
        检查是否可以入场
        
        返回:
            CheckResult(allowed=True) - 允许入场
            CheckResult(allowed=False, reason="max_position") - 仓位已满
            CheckResult(allowed=False, reason="max_loss") - 亏损超限
        """
        # 检查仓位限制
        if len(portfolio.positions) >= self.max_position:
            return CheckResult(allowed=False, reason="max_position")
        
        # 检查总亏损限制
        if portfolio.total_pnl_pct < self.max_loss:
            return CheckResult(allowed=False, reason="max_loss")
        
        return CheckResult(allowed=True)
    
    def check_exit(self, position: Position, current_price: float) -> ExitSignal:
        """
        检查是否需要退出
        
        返回:
            ExitSignal(reason="stop_loss", pnl=-5.2%) - 止损
            ExitSignal(reason="stop_profit", pnl=5.8%) - 止盈
            ExitSignal(reason="hold_days", days=4) - 到期
            None - 不需要退出
        """
        pnl = position.pnl_pct
        
        # 止损检查
        if pnl <= self.stop_loss:
            return ExitSignal(reason="stop_loss", pnl=pnl)
        
        # 止盈检查
        if pnl >= self.stop_profit:
            return ExitSignal(reason="stop_profit", pnl=pnl)
        
        # 持仓天数检查
        if position.hold_days >= self.hold_days:
            return ExitSignal(reason="hold_days", days=position.hold_days)
        
        return None
```

#### 涉及的模块
| 模块 | 改动 | 说明 |
|------|------|------|
| `src/risk/` (新增) | 新增 | 风控模块 |
| `src/strategy/executor.py` | 删除 | 移除止损/止盈逻辑 |
| `src/strategy/engine.py` | 删除 | 移除持仓天数检查 |
| `src/strategy/scorer.py` | 删除 | 移除仓位限制检查 |

---

## 四、接口契约

### 4.1 配置加载接口

```python
# src/strategy/config_loader.py

class ConfigLoader:
    """配置加载器"""
    
    @staticmethod
    def load(path: str) -> StrategyConfig:
        """
        从YAML文件加载策略配置
        
        参数:
            path: 配置文件路径 (如 "config/strategies/exp50.yaml")
            
        返回:
            StrategyConfig: 策略配置对象
            
        异常:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
    
    @staticmethod
    def load_default() -> StrategyConfig:
        """加载默认配置"""
    
    @staticmethod
    def list_strategies() -> List[str]:
        """列出所有可用策略"""
```

**接口约束**:
- 返回的StrategyConfig必须包含所有必需字段
- 缺少字段时使用默认值
- YAML格式错误时抛出明确异常

---

### 4.2 风控管理接口

```python
# src/risk/manager.py

@dataclass
class CheckResult:
    allowed: bool
    reason: Optional[str] = None

@dataclass
class ExitSignal:
    reason: str  # "stop_loss" | "stop_profit" | "hold_days"
    pnl: Optional[float] = None
    days: Optional[int] = None

class RiskManager:
    """风控管理器"""
    
    def check_entry(self, order: Order, portfolio: Portfolio) -> CheckResult:
        """检查是否可以入场"""
    
    def check_exit(self, position: Position, current_price: float) -> Optional[ExitSignal]:
        """检查是否需要退出"""
```

**接口约束**:
- check_entry必须在交易前调用
- check_exit每个bar都要调用
- 返回ExitSignal时，回测引擎必须执行平仓

---

### 4.3 策略接口

```python
# src/strategy/base.py

class Strategy(ABC):
    """策略基类 - 所有策略必须实现此接口"""
    
    @abstractmethod
    def on_bar(self, bar: Bar) -> Optional[Signal]:
        """
        每个bar触发一次
        
        参数:
            bar: 当前K线数据
            
        返回:
            Signal: 交易信号 (买入/卖出)
            None: 无信号
        """
    
    @abstractmethod
    def on_fill(self, fill: Fill):
        """
        成交时触发
        
        参数:
            fill: 成交信息
        """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
    
    @property
    @abstractmethod
    def config(self) -> StrategyConfig:
        """策略配置"""


class FactorStrategy(Strategy):
    """因子评分策略 - 实现Strategy接口"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.scorer = FactorScorer(...)
    
    def on_bar(self, bar):
        score = self.scorer.calculate(bar)
        if score > self.config.execution.threshold:
            return Signal(type="buy", code=bar.code, score=score)
        return None
```

**接口约束**:
- 所有策略必须实现on_bar/on_fill
- on_bar必须线程安全
- Signal必须包含type/code/score字段

---

## 五、验收标准

### 5.1 P0-1: 配置外部化

| 验收项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| 配置加载 | `ConfigLoader.load("config/strategies/exp50.yaml")` | 返回有效StrategyConfig |
| 配置保存 | 修改YAML后重新加载 | 配置生效 |
| 默认配置 | `ConfigLoader.load_default()` | 返回默认配置 |
| 配置列表 | `ConfigLoader.list_strategies()` | 返回["exp50", "exp42", "exp36", ...] |
| 兼容性 | 原有`quick_run()`调用 | 仍然正常工作 |
| 错误处理 | 加载不存在的文件 | 抛出FileNotFoundError |

**回归测试**:
```bash
# 确保原有功能不受影响
python -m pytest tests/test_config_loader.py -v
python -m pytest tests/test_backtest.py -v
```

---

### 5.2 P0-2: 风控模块独立

| 验收项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| 止损触发 | 持仓亏损5.01% | 触发止损平仓 |
| 止盈触发 | 持仓盈利5.5% | 触发止盈平仓 |
| 持仓到期 | 持仓4天 | 触发到期平仓 |
| 仓位限制 | 已有1持仓 | 拒绝新入场 |
| 亏损限制 | 总亏损10% | 拒绝新入场 |
| 多策略风控 | 运行多个策略 | 每个策略独立风控 |

**单元测试**:
```python
# tests/test_risk_manager.py

def test_stop_loss():
    risk = RiskManager(stop_loss=-0.05)
    position = create_position(pnl_pct=-0.06)
    signal = risk.check_exit(position, price=100)
    assert signal.reason == "stop_loss"

def test_max_position():
    risk = RiskManager(max_position=1)
    portfolio = create_portfolio(positions=1)
    result = risk.check_entry(order, portfolio)
    assert result.allowed == False
    assert result.reason == "max_position"
```

---

### 5.3 P1-1: 策略接口化

| 验收项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| 接口定义 | FactorStrategy继承Strategy | 无错误 |
| on_bar调用 | 传入Bar返回Signal或None | 正常返回 |
| 多策略运行 | 创建多个策略实例 | 互不干扰 |
| 策略切换 | 不同策略产生不同信号 | 信号正确 |

---

### 5.4 P1-2: 异常处理

| 验收项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| 熔断触发 | API连续失败3次 | 进入熔断状态 |
| 熔断恢复 | 30秒后API正常 | 恢复正常 |
| 重试机制 | API失败时自动重试 | 重试3次 |
| 降级策略 | 所有API失败 | 使用昨收价 |

---

## 六、开发计划

### 6.1 任务分解

#### P0-1: 配置外部化 (预计2天)

| 任务 | 说明 | 时间 |
|------|------|------|
| T1.1 | 创建config/目录结构 | 0.5天 |
| T1.2 | 实现ConfigLoader类 | 0.5天 |
| T1.3 | 编写Exp50/Exp42/Exp36配置 | 0.5天 |
| T1.4 | 适配BacktestEngine | 0.5天 |
| T1.5 | 编写单元测试 | 0.5天 |
| T1.6 | 回归测试 | 0.5天 |

#### P0-2: 风控模块独立 (预计3天)

| 任务 | 说明 | 时间 |
|------|------|------|
| T2.1 | 创建src/risk/目录结构 | 0.5天 |
| T2.2 | 实现RiskManager类 | 1天 |
| T2.3 | 迁移风控逻辑 | 0.5天 |
| T2.4 | 编写单元测试 | 0.5天 |
| T2.5 | 集成测试 | 0.5天 |

### 6.2 开发顺序

```
P0-1 (配置外部化)
├── T1.1 创建目录
├── T1.2 实现ConfigLoader
├── T1.3 编写配置文件
└── T1.4-T1.6 适配和测试

         ↓
         
P0-2 (风控独立)
├── T2.1 创建目录
├── T2.2 实现RiskManager
├── T2.3 迁移风控逻辑
└── T2.4-T2.5 测试

         ↓
         
P1-1 (策略接口化)
...
```

### 6.3 里程碑

| 里程碑 | 完成标志 |
|--------|----------|
| M1: P0-1完成 | 配置可以从YAML加载，原有功能正常 |
| M2: P0-2完成 | 风控逻辑集中，测试通过 |
| M3: P1完成 | 策略可插拔，异常处理完善 |

---

## 七、风险与依赖

### 7.1 风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 改动范围大 | 可能引入bug | 充分回归测试 |
| 配置格式变更 | 旧配置不兼容 | 提供迁移脚本 |
| 时间紧迫 | 可能仓促上线 | 严格按验收标准 |

### 7.2 依赖

| 依赖 | 说明 | 前置条件 |
|------|------|----------|
| YAML解析库 | PyYAML | pip install pyyaml |
| 测试框架 | pytest | pip install pytest |
| 回测数据 | etf.db | 已有 |

---

## 八、待确认项

| 项目 | 状态 | 说明 |
|------|------|------|
| P0-1配置外部化 | ⏳ 待确认 | 是否同意上述方案？ |
| P0-2风控独立 | ⏳ 待确认 | 是否同意上述方案？ |
| 接口契约 | ⏳ 待确认 | 接口设计是否合理？ |
| 验收标准 | ⏳ 待确认 | 测试用例是否充分？ |
| 开发计划 | ⏳ 待确认 | 时间线是否可行？ |

---

*文档版本: v2.0 | 创建: 2026-05-28*