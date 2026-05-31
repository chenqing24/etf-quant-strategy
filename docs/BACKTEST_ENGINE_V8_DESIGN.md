# 回测引擎统一设计 v8.0 FINAL

> 基于业界最佳实践（FMZ、Backtrader、Zipline）+ 自测问题分析

---

## 一、核心原则

| 原则 | 说明 |
|------|------|
| 三个一致性 | 工具调用、执行流程、评价标准 |
| 唯一入口 | `FactorBacktester` (src/backtest/engine.py) |
| 废弃 | `simple_backtest` (scripts/factor_mining/) |

---

## 二、架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     数据层 (DataLoader)                     │
│                 从SQLite读取ETF数据                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              因子层 (IndicatorCalculator + RelativeCalculator) │
│              计算指标 + 相对大盘指标                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│               回测层 (FactorBacktester 唯一)                │
│                     持仓管理 + 止盈止损                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    评价层 (metrics_v7)                      │
│                   8个核心指标 + 综合评分                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、交易执行模型（关键改进1）

### 业界最佳实践

| 方案 | 说明 | 优缺点 |
|------|------|--------|
| **方案A（推荐）** | T日收盘信号 → T+1日开盘价成交 | ✅ 无look-ahead bias，接近真实 |
| 方案B | T日收盘价成交 | ❌ look-ahead bias，高估收益 |

### 本项目采用方案A

```
信号日(T)：
  - 收盘计算指标
  - 生成信号
  - 记录：T日需要买入

成交日(T+1)：
  - 用T+1开盘价买入
  - 开始计算持仓天数

卖出同理：
  - T日触发止损信号 → T+1开盘价卖出
  - T日到期 → T+1开盘价卖出
```

---

## 四、持仓管理（关键改进2）

### 管理规则

| 规则 | 默认值 | 说明 |
|------|--------|------|
| 每只ETF最多一个持仓 | - | 避免重复买入 |
| 最大同时持仓数 | 2 | 避免过度分散 |
| 最小持仓天数 | 3 | 止盈生效门槛 |
| 最大持仓天数 | 20 | 强制平仓 |

### 逻辑流程

```python
# 开仓检查
if code not in positions:           # 不在持仓中
    if len(positions) < max_pos:     # 未满仓
        if signal触发:              # 有买入信号
            买入

# 平仓检查
if code in positions:
    pnl = 当前价格 / 入场价格 - 1
    
    if pnl <= stop_loss:             # 止损（任何时候）
        卖出(止损)
    elif hold_days >= min_days:
        if pnl >= stop_profit:       # 止盈（需满足min_days）
            卖出(止盈)
    if hold_days >= max_days:        # 到期
        卖出(到期)
```

---

## 五、止盈止损逻辑（关键改进3）

### 业界最佳实践

```
止损：保护本金，任何时候可触发
止盈：需满足最小持仓，避免频繁交易
到期：达到最大持仓天数，强制平仓
```

### 本项目逻辑

| 条件 | 触发 | 优先级 |
|------|------|--------|
| 止损 | pnl ≤ -4% | **最高** |
| 止盈 | pnl ≥ +6% **且** hold_days ≥ 3 | 中 |
| 到期 | hold_days ≥ 20 | 最低 |

---

## 六、收益计算

### 单笔交易

```
买入价 = T+1开盘价
卖出价 = 触发日次日开盘价（止损/止盈/到期）

单笔收益 = (卖出价 - 买入价) / 买入价
交易成本 = 买入价 × 0.03% + 卖出价 × 0.03%
滑点损耗 = 买入价 × 0.02% + 卖出价 × 0.02%
净收益 = 单笔收益 - 交易成本 - 滑点损耗
```

### 相对收益

```
策略收益 = 净收益
基准收益 = (T+1开盘价_510300 / T开盘价_510300) - 1
相对收益 = 策略收益 - 基准收益
```

---

## 七、评价指标（精简为8个核心）

### 业界最佳实践 vs 本项目

| 类别 | 业界常用 | 本项目采用 |
|------|----------|------------|
| 收益 | 年化收益、最大收益 | ✅ 绝对收益、相对收益、年化收益 |
| 风险 | 最大回撤、VaR | ✅ 最大回撤、日波动率 |
| 风险调整 | 夏普比率、Calmar | ✅ 夏普比率（相对）、Calmar比率 |
| 交易 | 胜率、盈亏比 | ✅ 胜率、交易频率 |

### 8个核心指标

| # | 指标 | 类型 | 说明 |
|---|------|------|------|
| 1 | 绝对收益 | higher | 总收益 |
| 2 | 相对收益 | higher | 相对510300 |
| 3 | 年化收益 | higher | 年化 |
| 4 | 最大回撤 | lower | 历史最大 |
| 5 | 夏普比率 | higher | 风险调整 |
| 6 | Calmar比率 | higher | 回撤调整 |
| 7 | 胜率 | higher | 盈利占比 |
| 8 | 交易频率 | context | 年均次数 |

---

## 八、API设计

### 核心接口

```python
class FactorBacktester:
    def __init__(self, config: BacktestConfig):
        """配置"""
        
    def backtest(
        self,
        price_data: Dict[str, pd.DataFrame],
        signal_func: Callable[[pd.DataFrame], pd.Series],
        benchmark_data: pd.DataFrame = None,
        start_date: str = None,
        end_date: str = None,
    ) -> BacktestResult:
        """
        统一回测入口
        
        Args:
            price_data: ETF数据 {code: df}
            signal_func: 信号函数（AND组合）
            benchmark_data: 大盘数据
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            BacktestResult: 包含8个核心指标
        """
```

### 使用示例

```python
from src.backtest.engine import FactorBacktester, BacktestConfig

# 1. 配置
config = BacktestConfig(
    stop_loss=-0.04,
    stop_profit=0.06,
    min_hold_days=3,
    max_hold_days=20,
    max_positions=2,
)

# 2. 信号函数
def signal_func(df):
    return (df['MACD_hist'] > 0) & (df['DMA'] > 0)

# 3. 回测
backtester = FactorBacktester(config)
result = backtester.backtest(
    price_data=data,
    signal_func=signal_func,
    benchmark_data=benchmark,
    start_date='2023-01-01',
    end_date='2024-12-31'
)

# 4. 结果
print(f"绝对收益: {result.total_return:.2%}")
print(f"相对收益: {result.relative_return:.2%}")
print(f"胜率: {result.win_rate:.2%}")
print(f"夏普: {result.sharpe_relative:.2f}")
```

---

## 九、配置项

```python
@dataclass
class BacktestConfig:
    """回测配置"""
    # 止盈止损
    stop_loss: float = -0.04      # 止损4%
    stop_profit: float = 0.06      # 止盈6%
    
    # 持仓管理
    min_hold_days: int = 3         # 最小持仓3天
    max_hold_days: int = 20        # 最大持仓20天
    max_positions: int = 2        # 最大同时持仓2只
    
    # 成本
    commission_rate: float = 0.0003   # 佣金0.03%
    slippage_rate: float = 0.0002    # 滑点0.02%


@dataclass
class BacktestResult:
    """回测结果"""
    # 收益
    total_return: float            # 绝对收益
    relative_return: float        # 相对收益
    annual_return: float           # 年化收益
    
    # 风险
    max_drawdown: float           # 最大回撤
    daily_volatility: float       # 日波动率
    
    # 风险调整
    sharpe_relative: float        # 夏普比率（相对）
    calmar_ratio: float           # Calmar比率
    
    # 交易
    win_rate: float               # 胜率
    trade_count: int              # 交易数
    annual_trades: float          # 年均交易次数
    
    # 详情
    trades: List[Dict]            # 交易列表
```

---

## 十、执行计划

| Phase | 任务 | 状态 | 产出 | 验收 |
|-------|------|------|------|------|
| **Phase 1** | 重构 engine.py | ✅ 完成 | 唯一回测引擎 | 9个单元测试通过 |
| **Phase 2** | 集成测试 | ✅ 完成 | 全链路验证 | 5个集成测试通过 |
| **Phase 3** | 回归测试 | ✅ 完成 | 行为一致性 | 5个回归测试通过 |
| **Phase 4** | 迁移脚本 | ⏳ 待执行 | 使用新API | unified_mining_v7适配 |
| **Phase 5** | 清理归档 | ⏳ 待执行 | 无废弃代码 | 删除archived目录 |

## 执行时间线

```
2026-05-31
├── Phase 1: 单元测试 9/9 ✅
├── Phase 2: 集成测试 5/5 ✅  
├── Phase 3: 回归测试 5/5 ✅
├── Phase 4: 迁移脚本 ⏳
└── Phase 5: 清理归档 ⏳
```

---

## 十一、验收标准

| # | 标准 | 检查方法 | 目标 |
|---|------|----------|------|
| 1 | 无look-ahead | 成交价=下日开盘 | 100% |
| 2 | 无重复买入 | 同一ETF连续买入 | 0% |
| 3 | 持仓分布 | min_days=3时，<3天 | <5% |
| 4 | 相对收益 | 有值，范围合理 | -5%~+20% |
| 5 | 8核心指标 | 全部输出 | 8/8 |
| 6 | 回归测试 | 原有功能 | 100%通过 |

---

## 十二、文件变更

```
修改: src/backtest/engine.py      # 核心重构（200+行）
修改: scripts/factor_mining/unified_mining_v7.py  # 使用新API
修改: src/evaluation/metrics_v7.py  # 精简指标

删除: scripts/factor_mining/archived/*  # 23个废弃脚本
删除: scripts/archived/*          # 3个废弃脚本
```

---

## 参考来源

1. **FMZ量化** - 交易开拓者论坛，业界实践
2. **Backtrader文档** - 交易执行模型
3. **Zipline文档** - 收益计算
4. **本项目自测** - 交易数异常分析