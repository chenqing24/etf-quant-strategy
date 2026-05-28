# ETF量化系统 - 待开发计划

> 状态: 待确认 | 创建: 2026-05-28

---

## 概念说明（先看这个！）

### 问题1: 配置乱放 → 像杂乱的抽屉
**当前**: 策略参数写在代码里，改一个参数要翻代码
**改进后**: 所有配置在一个YAML文件里，像整理好的文件夹

### 问题2: 风控散落 → 像没有保安的大楼
**当前**: 止损、止盈、仓位限制分布在多个文件中
**改进后**: 找一个"保安"（风控模块）统一管理

### 问题3: 策略紧耦合 → 像焊接死的零件
**当前**: 策略逻辑和回测引擎"焊"在一起
**改进后**: 策略变成"可拔插的插件"，想换就换

详情见: `docs/ARCHITECTURE_SIMPLE.md`

---

## P0 - 必须实施 (立即执行)

### P0-1: 配置外部化

**问题**: 策略配置硬编码在Python代码中，难以管理和切换

**改进内容**:
- 创建 `config/strategies/` 目录
- 将Exp50/Exp42/Exp36等策略配置迁移到YAML文件
- 实现 `ConfigLoader` 加载器

**交付物**:
```
config/
├── default.yaml           # 默认配置
└── strategies/
    ├── exp50.yaml          # Exp50配置
    ├── exp42.yaml          # Exp42配置
    └── exp36.yaml          # Exp36配置
```

**预期收益**: 配置管理统一，可快速切换策略

---

### P0-2: 风控模块独立

**问题**: 止损/止盈/持仓限制逻辑散落在executor.py和engine.py中

**改进内容**:
- 创建 `src/risk/manager.py`
- 迁移所有风控逻辑到RiskManager类
- 添加仓位限制、最大亏损限制

**交付物**:
```
src/risk/
├── __init__.py
├── manager.py              # 风控管理器
├── rules.py                # 风控规则
└── config.py               # 风控配置
```

**预期收益**: 风控逻辑集中，便于调整和审计

---

## P1 - 重要实施 (下一阶段)

### P1-1: 策略接口化

**问题**: 策略逻辑与回测引擎强耦合，难以测试和复用

**改进内容**:
- 定义 `Strategy` 抽象基类
- 重构 `FactorStrategy` 实现该接口
- 解耦 `BacktestEngine`

**交付物**:
```python
class Strategy(ABC):
    @abstractmethod
    def on_bar(self, bar): pass
    
    @abstractmethod
    def on_signal(self, signal): pass

class FactorStrategy(Strategy):
    # 具体实现
```

**预期收益**: 策略可测试、可替换、支持多策略

---

### P1-2: 异常处理机制

**问题**: 数据源失败时无熔断/重试，可能导致决策中断

**改进内容**:
- 实现 `CircuitBreaker` 熔断器
- 添加API重试机制
- 实现降级策略（API失败时使用昨收价）

**交付物**:
```python
class CircuitBreaker:
    def call(self, func, *args, **kwargs): ...
    
class RetryPolicy:
    def execute(self, func, max_retries=3): ...
```

**预期收益**: 系统更健壮，数据源故障不中断决策

---

## P2 - 优化实施 (后续阶段)

### P2-1: 事件驱动架构

**改进内容**:
- 实现 `EventBus` 事件总线
- 事件类型: BAR_DATA/SIGNAL/ORDER/FILL/RISK_ALERT
- 解耦数据、策略、执行层

### P2-2: 结构化日志

**改进内容**:
- 引入 structlog
- 添加 request_id 追踪
- 统一日志格式

---

## 开发顺序

```
阶段1 (本周)    阶段2 (下周)    阶段3 (后续)
────────────    ────────────    ───────────
P0-1 配置外部化  P1-1 策略接口化  P2-1 事件驱动
P0-2 风控独立    P1-2 异常处理   P2-2 结构化日志
```

---

## 待确认

| 项目 | 确认状态 |
|------|----------|
| P0-1 配置外部化 | ⏳ 待确认 |
| P0-2 风控独立 | ⏳ 待确认 |
| P1-1 策略接口化 | ⏳ 待确认 |
| P1-2 异常处理 | ⏳ 待确认 |
| P2-1 事件驱动 | ⏳ 待确认 |
| P2-2 结构化日志 | ⏳ 待确认 |

---

*文档版本: v1.0 | 创建: 2026-05-28*