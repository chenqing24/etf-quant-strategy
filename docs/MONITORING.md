# ETF量化系统 - 监控层架构

> 系统运行状态的实时监控与告警

## 1. 概述

### 1.1 定义
监控层负责实时监控系统运行状态，在异常发生时及时告警。

### 1.2 监控目标

| 类别 | 指标 | 阈值 |
|------|------|------|
| 策略性能 | 日收益、回撤、夏普 | 低于基准告警 |
| 持仓风险 | 浮亏、持仓天数 | 触发风控线告警 |
| 系统健康 | 数据延迟、接口可用性 | 异常告警 |
| 交易状态 | 订单状态、资金余额 | 异常告警 |

### 1.3 告警级别

| 级别 | 颜色 | 含义 | 通知方式 |
|------|------|------|----------|
| INFO | 蓝色 | 一般信息 | 日志 |
| WARN | 黄色 | 需要关注 | 钉钉+日志 |
| ERROR | 红色 | 需要处理 | 钉钉+电话 |
| CRITICAL | 紫色 | 严重问题 | 钉钉+电话 |

---

## 2. 监控指标体系

### 2.1 策略性能指标

```python
@dataclass
class StrategyMetrics:
    """策略性能指标"""
    
    # 收益指标
    daily_return: float          # 日收益率（%）
    cumulative_return: float    # 累计收益率（%）
    
    # 风险指标
    max_drawdown: float         # 最大回撤（%）
    current_drawdown: float      # 当前回撤（%）
    volatility: float            # 波动率
    
    # 风险调整收益
    sharpe_ratio: float         # 夏普比率
    sortino_ratio: float        # 索提诺比率
    
    # 交易指标
    win_rate: float             # 胜率（%）
    profit_loss_ratio: float    # 盈亏比
    avg_hold_days: float        # 平均持仓天数
    
    # 时间戳
    timestamp: str
```

### 2.2 持仓监控指标

```python
@dataclass
class PositionMetrics:
    """持仓监控指标"""
    
    code: str                    # ETF代码
    quantity: int                # 持仓数量
    avg_cost: float             # 平均成本
    
    # 盈亏
    current_price: float        # 当前价格
    unrealized_pnl: float      # 浮动盈亏（元）
    pnl_pct: float             # 盈亏比例（%）
    
    # 风控状态
    stop_loss_triggered: bool   # 止损触发
    stop_gain_triggered: bool   # 止盈触发
    trailing_stop_active: bool  # 移动止盈激活
    
    # 时间
    entry_date: str            # 买入日期
    hold_days: int              # 持仓天数
    max_hold_days: int          # 最大持仓天数
    
    # 预警
    near_stop_loss: bool        # 接近止损
    near_stop_gain: bool        # 接近止盈
    hold_days_exceeded: bool    # 超时持仓
```

### 2.3 系统健康指标

```python
@dataclass
class SystemHealth:
    """系统健康指标"""
    
    # 数据状态
    data_freshness: str         # 数据新鲜度（如 "5分钟前更新"）
    data_delay_minutes: int     # 数据延迟（分钟）
    
    # 接口状态
    broker_api_available: bool  # 券商接口可用
    data_api_available: bool   # 数据接口可用
    
    # 运行时状态
    last_signal_time: str       # 上次信号时间
    last_trade_time: str        # 上次交易时间
    system_uptime: str          # 系统运行时间
    
    # 告警状态
    active_alerts: int          # 活跃告警数
    last_alert_time: str        # 最近告警时间
```

---

## 3. 告警规则

### 3.1 策略告警规则

```python
class StrategyAlertRules:
    """策略告警规则"""
    
    # 日收益告警
    DAILY_RETURN_THRESHOLD = -2.0  # 日收益低于-2%告警
    
    # 回撤告警
    DRAWDOWN_WARNING = -5.0         # 回撤超过-5%警告
    DRAWDOWN_ERROR = -10.0          # 回撤超过-10%错误
    
    # 夏普比率告警
    SHARPE_WARNING = 0.5             # 夏普低于0.5警告
    SHARPE_ERROR = 0.0              # 夏普为负错误

def check_strategy_alerts(metrics: StrategyMetrics) -> List[Alert]:
    alerts = []
    
    if metrics.daily_return <= StrategyAlertRules.DAILY_RETURN_THRESHOLD:
        alerts.append(Alert(
            level=AlertLevel.WARN,
            title=f"日收益告警: {metrics.daily_return:.2f}%",
            message=f"今日亏损超过阈值"
        ))
    
    if metrics.current_drawdown <= StrategyAlertRules.DRAWDOWN_WARNING:
        alerts.append(Alert(
            level=AlertLevel.ERROR,
            title=f"回撤告警: {metrics.current_drawdown:.2f}%",
            message="当前回撤超过-5%，建议检查持仓"
        ))
    
    return alerts
```

### 3.2 持仓告警规则

```python
class PositionAlertRules:
    """持仓告警规则"""
    
    # 止损告警（到达止损价的90%）
    NEAR_STOP_LOSS_RATIO = 0.9
    
    # 止盈告警（到达止盈价的90%）
    NEAR_STOP_GAIN_RATIO = 1.1
    
    # 超时持仓阈值
    MAX_HOLD_DAYS_WARNING = 12     # 持仓超过12天警告
    MAX_HOLD_DAYS_ERROR = 15       # 持仓超过15天强制调仓

def check_position_alerts(position: PositionMetrics) -> List[Alert]:
    alerts = []
    
    # 接近止损
    if position.near_stop_loss:
        alerts.append(Alert(
            level=AlertLevel.WARN,
            title=f"⚠️ {position.code} 接近止损",
            message=f"当前亏损 {position.pnl_pct:.2f}%，请关注"
        ))
    
    # 止损触发
    if position.stop_loss_triggered:
        alerts.append(Alert(
            level=AlertLevel.ERROR,
            title=f"🚨 {position.code} 触发止损",
            message="建议立即执行卖出"
        ))
    
    # 超时持仓
    if position.hold_days_exceeded:
        alerts.append(Alert(
            level=AlertLevel.WARN,
            title=f"⏰ {position.code} 超时持仓",
            message=f"已持仓 {position.hold_days} 天"
        ))
    
    return alerts
```

### 3.3 系统告警规则

```python
class SystemAlertRules:
    """系统告警规则"""
    
    # 数据延迟告警
    DATA_DELAY_WARNING = 30    # 延迟超过30分钟警告
    DATA_DELAY_ERROR = 60     # 延迟超过60分钟错误
    
    # 接口可用性
    API_TIMEOUT = 10           # 接口超时阈值（秒）

def check_system_alerts(health: SystemHealth) -> List[Alert]:
    alerts = []
    
    if health.data_delay_minutes >= SystemAlertRules.DATA_DELAY_ERROR:
        alerts.append(Alert(
            level=AlertLevel.CRITICAL,
            title="数据延迟严重",
            message=f"数据已延迟 {health.data_delay_minutes} 分钟"
        ))
    
    if not health.broker_api_available:
        alerts.append(Alert(
            level=AlertLevel.ERROR,
            title="券商接口不可用",
            message="无法连接券商系统，请检查网络"
        ))
    
    return alerts
```

---

## 4. 告警通知

### 4.1 钉钉通知

```python
class AlertNotifier:
    """告警通知器"""
    
    def __init__(self, webhook_url: str):
        self.webhook = webhook_url
    
    def send(self, alert: Alert):
        """发送告警到钉钉"""
        message = self._format_message(alert)
        
        # 根据级别选择颜色
        color_map = {
            AlertLevel.INFO: "172,193,212",    # 蓝色
            AlertLevel.WARN: "255,230,153",    # 黄色
            AlertLevel.ERROR: "255,102,102",   # 红色
            AlertLevel.CRITICAL: "204,153,255" # 紫色
        }
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": alert.title,
                "text": message
            },
            "theme": color_map.get(alert.level, "172,193,212")
        }
        
        requests.post(self.webhook, json=payload)
    
    def _format_message(self, alert: Alert) -> str:
        """格式化告警消息"""
        return f"""### {alert.title}
        
**级别**: {alert.level.name}
**时间**: {alert.timestamp}
**详情**: {alert.message}
"""
```

### 4.2 告警模板

```markdown
## 🚨 ETF系统告警

**⚠️ 接近止损** 515050 科技50

当前亏损: **-4.5%**（止损线-5%）

建议: 关注走势，跌破止损价立即卖出

---
时间: 2026-05-26 14:25
```

---

## 5. 监控面板

### 5.1 日报表

```markdown
# 📊 每日监控报告 - 2026-05-26

## 策略表现
| 指标 | 今日 | 累计 |
|------|-----:|-----:|
| 日收益 | +1.2% | +8.5% |
| 最大回撤 | - | -3.2% |
| 夏普 | - | 1.23 |

## 持仓状态
| 代码 | 盈亏 | 持仓天数 | 状态 |
|------|-----:|----------|------|
| 515050 | +3.2% | 5天 | ✅正常 |
| 516050 | -2.1% | 8天 | ⚠️接近止损 |

## 告警记录
| 时间 | 级别 | 内容 |
|------|------|------|
| 14:25 | WARN | 516050接近止损 |
| 09:30 | INFO | 系统启动正常 |
```

### 5.2 实时状态

```markdown
# 📈 实时状态 - 14:30

## 系统健康
- 数据延迟: 5分钟 ✅
- 券商接口: 正常 ✅
- 最后信号: 14:25 ✅

## 持仓概览
- 持仓数量: 1只
- 总市值: 18,500元
- 浮动盈亏: +520元 (+2.9%)

## 活跃告警
(无)
```

---

## 6. 监控实现

### 6.1 健康检查器

```python
class HealthChecker:
    """健康检查器"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self.data_facade = DataFacade(config.data_dir)
        self.tracker = TradeTracker(config.data_dir)
    
    def check(self) -> SystemHealth:
        """执行健康检查"""
        return SystemHealth(
            data_freshness=self._get_data_freshness(),
            data_delay_minutes=self._get_data_delay(),
            broker_api_available=self._check_broker_api(),
            data_api_available=self._check_data_api(),
            last_signal_time=self._get_last_signal_time(),
            last_trade_time=self._get_last_trade_time(),
            system_uptime=self._get_uptime(),
            active_alerts=len(self._get_active_alerts()),
            last_alert_time=self._get_last_alert_time()
        )
```

### 6.2 定时监控

```python
# 每日收盘后监控
@cron.schedule("30 15 * * 1-5")
def daily_monitor():
    checker = HealthChecker()
    health = checker.check()
    
    alerts = []
    alerts.extend(check_strategy_alerts(get_metrics()))
    alerts.extend(check_position_alerts(get_positions()))
    alerts.extend(check_system_alerts(health))
    
    if alerts:
        for alert in alerts:
            AlertNotifier().send(alert)
```

---

## 7. 修订历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-26 | v1.0 | 初始版本 |