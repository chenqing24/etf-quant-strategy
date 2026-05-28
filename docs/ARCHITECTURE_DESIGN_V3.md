# ETF量化系统 - 架构改进设计文档 v3.0（最佳实践版）

> 参考: Clean Architecture / 12-Factor / Microsoft API Design Guidelines / Google Testing
> 状态: 待确认 | 创建: 2026-05-28

---

## 一、文档结构

```
┌─────────────────────────────────────────────────────────────┐
│  1. 问题背景      - 为什么要改？当前问题是什么？            │
│  2. 技术选型      - 为什么选这个技术？备选方案？            │
│  3. 改进方案      - 具体怎么改？涉及哪些模块？              │
│  4. 接口契约      - 模块间怎么通信？（含错误码）          │
│  5. 验收标准      - 怎么判断改好了？（含覆盖率）          │
│  6. 风险控制      - 有哪些风险？怎么恢复？                │
│  7. 扩展指南      - 怎么加新因子/新策略？                │
│  8. 开发计划      - 怎么分工？时间线？                    │
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
    threshold = 0.8  # 问题: 想换策略要改代码
    stop_loss = -0.05
    stop_profit = 0.10
```

#### P2: 风控逻辑分散
```
当前代码分布:
├── src/strategy/executor.py    → 止损/止盈检查
├── src/strategy/engine.py      → 持仓天数检查
├── src/strategy/scorer.py      → 仓位限制检查
```

---

## 三、技术选型

### 3.1 选型原则

参考12-Factor App原则：
1. **声明性** - 配置必须声明式，不能命令行传递
2. **可移植** - 环境变量优于硬编码
3. **松耦合** - 后端服务必须可替换

### 3.2 技术对比

| 技术 | 优点 | 缺点 | 选择理由 |
|------|------|------|----------|
| **YAML** | 人类可读、支持注释、易于编辑 | 解析速度慢于JSON | ✅ 优先选择（可读性优先） |
| JSON | 解析快、广泛支持 | 不支持注释、冗长 | 备选方案 |
| TOML | 简洁、语义清晰 | Python支持较弱 | 不推荐 |
| ENV | 12-Factor标准 | 不适合复杂结构 | 仅用于简单配置 |

### 3.3 依赖声明

```yaml
# requirements.txt
# 核心依赖（必须版本化）
pyyaml>=6.0,<7.0         # 配置解析
pandas>=2.0.0            # 数据处理
numpy>=1.24.0            # 数值计算

# 测试依赖
pytest>=7.0.0            # 测试框架
pytest-cov>=4.0.0        # 覆盖率

# 可选依赖（便于扩展）
python-dotenv>=1.0.0     # 环境变量
structlog>=23.0.0        # 结构化日志

# Python版本要求
python>=3.9,<3.12        # 确保兼容性
```

### 3.4 版本策略

| 类型 | 策略 | 示例 |
|------|------|------|
| 主版本 | 不兼容变更 | 1.0 → 2.0 |
| 次版本 | 功能新增 | 1.0 → 1.1 |
| 补丁版本 | bug修复 | 1.0.0 → 1.0.1 |

---

## 四、改进方案

### 4.1 目录结构

```
etf_strategy/
├── config/                          # 配置文件（声明式）
│   ├── default.yaml                 # 默认配置
│   ├── strategies/                  # 策略配置
│   │   ├── exp50.yaml
│   │   ├── exp42.yaml
│   │   └── exp36.yaml
│   └── risk/                        # 风控配置
│       └── default.yaml
│
├── src/
│   ├── strategy/                     # 策略层
│   │   ├── base.py                   # Strategy接口
│   │   ├── factor.py                 # FactorStrategy
│   │   ├── config_loader.py          # 配置加载器
│   │   └── ...
│   │
│   ├── risk/                         # 风控层（P0-2）
│   │   ├── manager.py                # RiskManager
│   │   ├── rules.py                  # 风控规则
│   │   └── errors.py                 # 风控错误码
│   │
│   └── ...
│
├── tests/                            # 测试
│   ├── unit/                         # 单元测试
│   ├── integration/                  # 集成测试
│   └── benchmark/                    # 性能测试
│
└── docs/
    ├── ARCHITECTURE_DESIGN.md        # 设计文档
    └── EXTENSION_GUIDE.md            # 扩展指南
```

### 4.2 P0-1: 配置外部化

#### 配置格式（YAML）

```yaml
# config/strategies/exp50.yaml
version: "1.0"
name: "Exp50"

# ========== 评分因子配置 ==========
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

# ========== 风控配置 ==========
risk:
  stop_loss: -0.05          # 止损5%
  stop_profit: 0.055       # 止盈5.5%
  max_position: 1          # 最大持仓1只
  max_loss: -0.10          # 总亏损限制10%
  hold_days: 3             # 最大持仓天数

# ========== 执行配置 ==========
execution:
  threshold: 0.8           # 入场阈值
  allow_rebalance: false  # 不允许调仓

# ========== 数据配置 ==========
data:
  start_date: "2019-01-01"
  end_date: "2024-12-31"
  initial_capital: 20000
  commission: 0.0003       # 手续费0.03%
```

#### 配置加载器

```python
# src/strategy/config_loader.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import yaml
from pathlib import Path

@dataclass
class FactorConfig:
    """因子配置"""
    enabled: List[str]
    weights: Dict[str, float]
    direction: Dict[str, str]

@dataclass 
class RiskConfig:
    """风控配置"""
    stop_loss: float = -0.05
    stop_profit: float = 0.10
    max_position: int = 1
    max_loss: float = -0.10
    hold_days: int = 3

@dataclass
class ExecutionConfig:
    """执行配置"""
    threshold: float = 0.8
    allow_rebalance: bool = False

@dataclass
class DataConfig:
    """数据配置"""
    start_date: str = "2019-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 20000
    commission: float = 0.0003

@dataclass
class StrategyConfig:
    """策略配置（根配置）"""
    version: str = "1.0"
    name: str = "default"
    factors: FactorConfig = field(default_factory=FactorConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    data: DataConfig = field(default_factory=DataConfig)

class ConfigLoader:
    """配置加载器（线程安全）"""
    
    _instance: Optional['ConfigLoader'] = None
    _cache: Dict[str, StrategyConfig] = {}
    
    @classmethod
    def get_instance(cls) -> 'ConfigLoader':
        """单例模式，确保配置只加载一次"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def load(self, path: str) -> StrategyConfig:
        """
        从YAML文件加载策略配置
        
        参数:
            path: 配置文件路径
            
        返回:
            StrategyConfig: 策略配置对象
            
        异常:
            ConfigNotFoundError (错误码: E1001): 配置文件不存在
            ConfigFormatError (错误码: E1002): 配置文件格式错误
            ConfigVersionError (错误码: E1003): 配置版本不兼容
        """
        # 检查缓存
        if path in self._cache:
            return self._cache[path]
        
        # 解析YAML
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            raise ConfigNotFoundError(f"配置文件不存在: {path}", code="E1001")
        except yaml.YAMLError as e:
            raise ConfigFormatError(f"YAML格式错误: {e}", code="E1002")
        
        # 验证版本
        if data.get('version') != "1.0":
            raise ConfigVersionError(
                f"配置版本不兼容: {data.get('version')}",
                code="E1003"
            )
        
        # 构建配置对象
        config = self._build_config(data)
        
        # 缓存
        self._cache[path] = config
        return config
    
    def _build_config(self, data: dict) -> StrategyConfig:
        """构建配置对象"""
        return StrategyConfig(
            version=data.get('version', '1.0'),
            name=data.get('name', 'default'),
            factors=FactorConfig(
                enabled=data.get('factors', {}).get('enabled', []),
                weights=data.get('factors', {}).get('weights', {}),
                direction=data.get('factors', {}).get('direction', {})
            ),
            risk=RiskConfig(**data.get('risk', {})),
            execution=ExecutionConfig(**data.get('execution', {})),
            data=DataConfig(**data.get('data', {}))
        )
    
    @staticmethod
    def list_strategies() -> List[str]:
        """列出所有可用策略"""
        strategy_dir = Path('config/strategies')
        if not strategy_dir.exists():
            return []
        return [f.stem for f in strategy_dir.glob('*.yaml')]
```

### 4.3 P0-2: 风控模块独立

#### 错误码体系

```python
# src/risk/errors.py

class RiskError(Exception):
    """风控基础异常"""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)

class ConfigNotFoundError(RiskError):
    """配置文件不存在 (E1001)"""
    pass

class ConfigFormatError(RiskError):
    """配置文件格式错误 (E1002)"""
    pass

class ConfigVersionError(RiskError):
    """配置版本不兼容 (E1003)"""
    pass

class RiskLimitError(RiskError):
    """风控限制触发 (E2001)"""
    pass

class PositionLimitError(RiskLimitError):
    """仓位限制触发 (E2001-01)"""
    pass

class LossLimitError(RiskLimitError):
    """亏损限制触发 (E2001-02)"""
    pass

class StopLossError(RiskLimitError):
    """止损触发 (E2002-01)"""
    pass

class StopProfitError(RiskLimitError):
    """止盈触发 (E2002-02)"""
    pass

class HoldDaysLimitError(RiskLimitError):
    """持仓天数限制触发 (E2002-03)"""
    pass

# 错误码对照表
ERROR_CODE_TABLE = {
    "E1001": "配置文件不存在",
    "E1002": "配置文件格式错误",
    "E1003": "配置版本不兼容",
    "E2001-01": "仓位已满，无法入场",
    "E2001-02": "总亏损超限，无法入场",
    "E2002-01": "止损触发",
    "E2002-02": "止盈触发",
    "E2002-03": "持仓天数到期"
}
```

#### 风控管理器

```python
# src/risk/manager.py

from dataclasses import dataclass
from typing import Optional
from .errors import *

@dataclass
class CheckResult:
    """入场检查结果"""
    allowed: bool
    reason: Optional[str] = None
    code: Optional[str] = None

@dataclass
class ExitSignal:
    """退出信号"""
    reason: str  # "stop_loss" | "stop_profit" | "hold_days"
    pnl: Optional[float] = None
    days: Optional[int] = None

@dataclass
class Position:
    """持仓信息"""
    code: str
    quantity: int
    avg_price: float
    current_price: float
    entry_date: str
    
    @property
    def pnl_pct(self) -> float:
        """盈亏百分比"""
        return (self.current_price - self.avg_price) / self.avg_price
    
    @property
    def hold_days(self) -> int:
        """持仓天数"""
        from datetime import datetime
        entry = datetime.strptime(self.entry_date, '%Y-%m-%d')
        return (datetime.now() - entry).days

@dataclass
class Portfolio:
    """组合信息"""
    positions: list
    cash: float
    total_value: float
    
    @property
    def total_pnl_pct(self) -> float:
        """总盈亏百分比"""
        if self.total_value == 0:
            return 0
        return (self.total_value - self.cash) / self.cash

class RiskManager:
    """风控管理器 - 统一管理所有风控逻辑"""
    
    def __init__(
        self,
        stop_loss: float = -0.05,
        stop_profit: float = 0.10,
        max_position: int = 1,
        max_loss: float = -0.10,
        hold_days: int = 3
    ):
        self.stop_loss = stop_loss
        self.stop_profit = stop_profit
        self.max_position = max_position
        self.max_loss = max_loss
        self.hold_days = hold_days
    
    @classmethod
    def from_config(cls, config: RiskConfig) -> 'RiskManager':
        """从配置创建风控管理器"""
        return cls(
            stop_loss=config.stop_loss,
            stop_profit=config.stop_profit,
            max_position=config.max_position,
            max_loss=config.max_loss,
            hold_days=config.hold_days
        )
    
    def check_entry(self, portfolio: Portfolio) -> CheckResult:
        """
        检查是否可以入场
        
        规则:
        1. 仓位限制: 已有持仓 < max_position
        2. 亏损限制: 总亏损 > max_loss
        
        返回:
            CheckResult(allowed=True) - 允许入场
            CheckResult(allowed=False, reason="max_position", code="E2001-01")
            CheckResult(allowed=False, reason="max_loss", code="E2001-02")
        """
        # 规则1: 仓位限制
        if len(portfolio.positions) >= self.max_position:
            return CheckResult(
                allowed=False,
                reason="max_position",
                code="E2001-01"
            )
        
        # 规则2: 亏损限制
        if portfolio.total_pnl_pct < self.max_loss:
            return CheckResult(
                allowed=False,
                reason="max_loss",
                code="E2001-02"
            )
        
        return CheckResult(allowed=True)
    
    def check_exit(self, position: Position, current_price: float) -> Optional[ExitSignal]:
        """
        检查是否需要退出
        
        规则:
        1. 止损: 盈亏 <= stop_loss
        2. 止盈: 盈亏 >= stop_profit
        3. 持仓到期: 持仓天数 >= hold_days
        
        返回:
            ExitSignal(reason="stop_loss", pnl=-5.2%)
            ExitSignal(reason="stop_profit", pnl=5.8%)
            ExitSignal(reason="hold_days", days=4)
            None - 不需要退出
        """
        # 更新持仓价格
        position.current_price = current_price
        
        # 规则1: 止损
        if position.pnl_pct <= self.stop_loss:
            return ExitSignal(
                reason="stop_loss",
                pnl=position.pnl_pct
            )
        
        # 规则2: 止盈
        if position.pnl_pct >= self.stop_profit:
            return ExitSignal(
                reason="stop_profit",
                pnl=position.pnl_pct
            )
        
        # 规则3: 持仓天数
        if position.hold_days >= self.hold_days:
            return ExitSignal(
                reason="hold_days",
                days=position.hold_days
            )
        
        return None
```

---

## 五、接口契约

### 5.1 接口定义

| 接口 | 类 | 方法 | 输入 | 输出 | 错误码 |
|------|-----|------|------|------|--------|
| 配置加载 | ConfigLoader | load(path) | str | StrategyConfig | E1001/E1002/E1003 |
| 配置加载 | ConfigLoader | list_strategies() | - | List[str] | - |
| 入场检查 | RiskManager | check_entry(portfolio) | Portfolio | CheckResult | E2001-01/E2001-02 |
| 退出检查 | RiskManager | check_exit(position, price) | Position, float | ExitSignal | E2002-01/02/03 |
| 策略接口 | Strategy | on_bar(bar) | Bar | Signal | - |
| 策略接口 | Strategy | on_fill(fill) | Fill | - | - |

### 5.2 数据类型定义

```python
# src/strategy/types.py

@dataclass
class Bar:
    """K线数据"""
    code: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class Signal:
    """交易信号"""
    type: str  # "buy" | "sell"
    code: str
    score: float
    timestamp: str

@dataclass
class Order:
    """订单"""
    code: str
    type: str  # "buy" | "sell"
    price: float
    quantity: int
    timestamp: str

@dataclass
class Fill:
    """成交"""
    order: Order
    executed_price: float
    executed_quantity: int
    commission: float
    timestamp: str
```

---

## 六、验收标准

### 6.1 测试覆盖率要求

| 模块 | 覆盖率要求 | 说明 |
|------|------------|------|
| risk/manager.py | ≥90% | 风控核心模块 |
| strategy/config_loader.py | ≥90% | 配置加载模块 |
| strategy/base.py | ≥80% | 策略接口 |
| 整体项目 | ≥80% | 最低要求 |

### 6.2 P0-1: 配置外部化验收

| 验收项 | 测试用例 | 预期结果 | 覆盖率 |
|--------|----------|----------|--------|
| 配置加载 | `loader.load("config/strategies/exp50.yaml")` | 返回有效StrategyConfig | ✅ |
| 配置缓存 | 连续加载同一文件 | 从缓存返回，不读文件 | ✅ |
| 错误处理 | 加载不存在的文件 | 抛出ConfigNotFoundError(code=E1001) | ✅ |
| 格式错误 | 加载格式错误的YAML | 抛出ConfigFormatError(code=E1002) | ✅ |
| 版本验证 | 加载版本不兼容的配置 | 抛出ConfigVersionError(code=E1003) | ✅ |
| 默认配置 | `loader.load_default()` | 返回默认配置 | ✅ |
| 策略列表 | `loader.list_strategies()` | 返回["exp50", "exp42", "exp36"] | ✅ |
| 兼容性 | 原quick_run()调用 | 仍然正常工作 | ✅ |

**单元测试**:
```python
# tests/unit/test_config_loader.py

def test_load_success():
    loader = ConfigLoader.get_instance()
    config = loader.load("config/strategies/exp50.yaml")
    assert config.name == "Exp50"
    assert config.factors.enabled == ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff']

def test_load_file_not_found():
    with pytest.raises(ConfigNotFoundError) as exc_info:
        loader.load("config/strategies/nonexistent.yaml")
    assert exc_info.value.code == "E1001"

def test_load_yaml_error():
    with pytest.raises(ConfigFormatError) as exc_info:
        loader.load("tests/fixtures/broken.yaml")
    assert exc_info.value.code == "E1002"

def test_cache():
    config1 = loader.load("config/strategies/exp50.yaml")
    config2 = loader.load("config/strategies/exp50.yaml")
    assert config1 is config2  # 同一对象
```

### 6.3 P0-2: 风控模块独立验收

| 验收项 | 测试用例 | 预期结果 | 覆盖率 |
|--------|----------|----------|--------|
| 止损触发 | 持仓亏损5.01% | ExitSignal(reason="stop_loss", pnl=-5.01%) | ✅ |
| 止盈触发 | 持仓盈利5.5% | ExitSignal(reason="stop_profit", pnl=5.5%) | ✅ |
| 持仓到期 | 持仓4天 | ExitSignal(reason="hold_days", days=4) | ✅ |
| 仓位限制 | 已有1持仓 | CheckResult(allowed=False, code="E2001-01") | ✅ |
| 亏损限制 | 总亏损11% | CheckResult(allowed=False, code="E2001-02") | ✅ |
| 正常入场 | 空仓+盈利>max_loss | CheckResult(allowed=True) | ✅ |
| 多策略隔离 | 2个RiskManager实例 | 独立风控，互不影响 | ✅ |

**单元测试**:
```python
# tests/unit/test_risk_manager.py

def test_stop_loss_trigger():
    risk = RiskManager(stop_loss=-0.05)
    position = Position(
        code='510300',
        quantity=1000,
        avg_price=3.00,
        current_price=2.85,  # 亏损5%
        entry_date='2026-05-25'
    )
    signal = risk.check_exit(position, current_price=2.85)
    assert signal is not None
    assert signal.reason == "stop_loss"
    assert abs(signal.pnl - (-0.05)) < 0.001

def test_stop_profit_trigger():
    risk = RiskManager(stop_profit=0.055)
    position = Position(
        code='510300',
        quantity=1000,
        avg_price=3.00,
        current_price=3.165,  # 盈利5.5%
        entry_date='2026-05-25'
    )
    signal = risk.check_exit(position, current_price=3.165)
    assert signal is not None
    assert signal.reason == "stop_profit"

def test_max_position():
    risk = RiskManager(max_position=1)
    portfolio = Portfolio(
        positions=[Position(...)],  # 已有1个持仓
        cash=10000,
        total_value=25000
    )
    result = risk.check_entry(portfolio)
    assert result.allowed == False
    assert result.code == "E2001-01"
```

### 6.4 集成测试

```python
# tests/integration/test_strategy_pipeline.py

def test_strategy_with_risk():
    """端到端测试：策略+风控"""
    # 1. 加载配置
    config = ConfigLoader.get_instance().load("config/strategies/exp50.yaml")
    
    # 2. 创建风控
    risk = RiskManager.from_config(config.risk)
    
    # 3. 创建策略
    strategy = FactorStrategy(config)
    
    # 4. 模拟回测
    for bar in get_test_bars():
        signal = strategy.on_bar(bar)
        
        if signal and signal.type == "buy":
            result = risk.check_entry(portfolio)
            assert result.allowed == True  # 或False
        
        # 检查退出
        for pos in portfolio.positions:
            exit_signal = risk.check_exit(pos, bar.close)
            if exit_signal:
                # 执行平仓
                pass
```

### 6.5 性能基准测试

```python
# tests/benchmark/test_config_loading.py

def test_load_performance():
    """配置加载性能基准"""
    import time
    loader = ConfigLoader.get_instance()
    
    start = time.time()
    for _ in range(100):
        loader.load("config/strategies/exp50.yaml")
    elapsed = time.time() - start
    
    # 要求: 100次加载 < 1秒
    assert elapsed < 1.0, f"加载太慢: {elapsed}s"
```

---

## 七、风险控制

### 7.1 风险识别表

| ID | 风险 | 影响 | 概率 | 等级 | 缓解措施 | 恢复步骤 |
|----|------|------|------|------|----------|----------|
| R1 | 改动范围大引入bug | 高 | 中 | 🔴 | 充分回归测试 | 回滚到上一版本 |
| R2 | 配置格式变更旧配置不兼容 | 中 | 低 | 🟡 | 版本校验+迁移脚本 | 降级配置加载器 |
| R3 | 时间紧迫仓促上线 | 中 | 中 | 🟡 | 严格按验收标准 | 推迟上线 |
| R4 | 团队不熟悉新技术 | 低 | 中 | 🟢 | 培训+代码评审 | 保留旧代码备选 |

### 7.2 回滚方案

#### 方案A: Git回滚
```bash
# 如果P0-1出问题，回滚到上一个稳定版本
git revert <commit_hash>
git push

# 恢复配置
git checkout HEAD~1 -- config/
```

#### 方案B: 配置回滚
```python
# 如果只是配置问题，快速切换到默认配置
config = ConfigLoader.load("config/default.yaml")
```

#### 方案C: 特性开关
```python
# 添加开关控制新旧逻辑
if os.getenv('USE_NEW_RISK') == 'true':
    risk = RiskManager.from_config(config.risk)
else:
    risk = OldRiskManager()  # 保留旧实现
```

### 7.3 熔断机制

```python
# src/utils/circuit_breaker.py

from datetime import datetime, timedelta
from typing import Callable, TypeVar

T = TypeVar('T')

class CircuitBreaker:
    """熔断器 - 防止级联故障"""
    
    def __init__(
        self,
        failure_threshold: int = 3,
        timeout: int = 60,
        half_open_max_calls: int = 1
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed/open/half_open
        self.half_open_calls = 0
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """执行函数，带熔断保护"""
        # 检查状态
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise CircuitOpenError("熔断器打开，拒绝调用")
        
        if self.state == "half_open":
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError("半开状态调用次数用尽")
            self.half_open_calls += 1
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """检查是否可以尝试恢复"""
        if self.last_failure_time is None:
            return True
        elapsed = (datetime.now() - self.last_failure_time).seconds
        return elapsed >= self.timeout
    
    def _on_success(self):
        """成功后重置"""
        if self.state == "half_open":
            self.state = "closed"
        self.failure_count = 0
    
    def _on_failure(self):
        """失败后处理"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"

class CircuitOpenError(Exception):
    """熔断器打开异常"""
    pass
```

---

## 八、扩展指南

### 8.1 添加新因子

```python
# 1. 在 config/default.yaml 中声明
factors:
  enabled:
    - ADX
    - BB_percent
    - NEW_FACTOR  # 新增因子

# 2. 实现因子计算
# src/indicators/new_factor.py
class NewFactorIndicator(BaseIndicator):
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        # 实现计算逻辑
        return result

# 3. 在 FactorScorer 中注册
FACTOR_REGISTRY = {
    'ADX': ADXIndicator,
    'BB_percent': BollingerIndicator,
    'NEW_FACTOR': NewFactorIndicator,  # 注册
}
```

### 8.2 添加新策略

```python
# 1. 实现Strategy接口
# src/strategy/momentum.py
class MomentumStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.name = "MomentumStrategy"
    
    def on_bar(self, bar: Bar) -> Optional[Signal]:
        # 实现动量策略逻辑
        return signal
    
    @property
    def config(self) -> StrategyConfig:
        return self._config

# 2. 创建配置文件
# config/strategies/momentum.yaml
version: "1.0"
name: "MomentumStrategy"
...

# 3. 使用新策略
strategy = MomentumStrategy(
    ConfigLoader.get_instance().load("config/strategies/momentum.yaml")
)
```

### 8.3 添加新风控规则

```python
# src/risk/rules.py

class MaxDrawdownRule(Rule):
    """最大回撤规则"""
    
    def __init__(self, max_drawdown: float = -0.15):
        self.max_drawdown = max_drawdown
    
    def check(self, portfolio: Portfolio) -> RuleResult:
        if portfolio.max_drawdown < self.max_drawdown:
            return RuleResult(
                passed=False,
                reason="max_drawdown",
                message=f"最大回撤{portfolio.max_drawdown:.1%}超过限制{self.max_drawdown:.1%}"
            )
        return RuleResult(passed=True)

# 在RiskManager中组合使用
class RiskManager:
    def __init__(self, rules: List[Rule] = None):
        self.rules = rules or [
            MaxDrawdownRule(),
            # ... 其他规则
        ]
```

---

## 九、开发计划

### 9.1 任务分解（细化人天）

#### P0-1: 配置外部化 (预计3人天)

| 任务 | 负责人 | 预计时间 | 前置条件 |
|------|--------|----------|----------|
| T1.1 创建config/目录结构 | DEV | 0.25天 | - |
| T1.2 实现ConfigLoader类 | DEV | 1天 | - |
| T1.3 编写配置文件(3个) | DEV | 0.25天 | T1.2 |
| T1.4 适配BacktestEngine | DEV | 0.5天 | T1.2 |
| T1.5 单元测试 | QA | 0.5天 | T1.4 |
| T1.6 集成测试 | QA | 0.5天 | T1.5 |

#### P0-2: 风控模块独立 (预计4人天)

| 任务 | 负责人 | 预计时间 | 前置条件 |
|------|--------|----------|----------|
| T2.1 创建src/risk/目录结构 | DEV | 0.25天 | - |
| T2.2 实现错误码体系 | DEV | 0.5天 | - |
| T2.3 实现RiskManager类 | DEV | 1.5天 | T2.2 |
| T2.4 迁移风控逻辑 | DEV | 0.75天 | T2.3 |
| T2.5 单元测试 | QA | 0.5天 | T2.4 |
| T2.6 集成测试 | QA | 0.5天 | T2.5 |

### 9.2 时间线

```
Week 1 (Mon-Fri)
├── Mon-Tue: T1.1-T1.2 配置加载器
├── Wed: T1.3-T1.4 配置文件+适配
├── Thu-Fri: T1.5-T1.6 测试
│
└── Week 2 (Mon-Wed)
    ├── Mon-Tue: T2.1-T2.3 风控模块
    ├── Wed: T2.4-T2.5 测试
    └── Thu-Fri: 缓冲+修复
```

### 9.3 里程碑

| 里程碑 | 完成标志 | 验收人 |
|--------|----------|--------|
| M1: P0-1完成 | 配置可从YAML加载，测试覆盖率≥90% | 用户 |
| M2: P0-2完成 | 风控逻辑集中，测试覆盖率≥90% | 用户 |
| M3: 集成完成 | 端到端测试通过，性能基准达标 | 用户 |

---

## 十、待确认项

| 项目 | 状态 | 说明 |
|------|------|------|
| 技术选型(YAML) | ⏳ | 是否同意使用YAML？ |
| 版本策略 | ⏳ | 是否同意上述版本号规则？ |
| 错误码体系 | ⏳ | 是否同意错误码定义？ |
| 测试覆盖率 | ⏳ | 是否同意≥80%要求？ |
| 工作量估算 | ⏳ | 是否同意3+4人天？ |
| 回滚方案 | ⏳ | 是否同意特性开关方案？ |

---

*文档版本: v3.0 | 创建: 2026-05-28 | 参考: Clean Architecture / 12-Factor / Microsoft API Design*