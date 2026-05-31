# 回测引擎统一设计 v8.0

## 一、问题根源

### 1.1 当前状态

| 引擎 | 位置 | 问题 |
|------|------|------|
| FactorBacktester | `src/backtest/engine.py` | 唯一标准，但功能不足 |
| simple_backtest | `scripts/factor_mining/unified_mining_v7.py` | 重复实现，无持仓管理 |

### 1.2 违反原则

- **三个一致性**：存在两个回测引擎，工具调用不一致
- **使用现有工具**：自己编脚本，未用FactorBacktester

### 1.3 发现的问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | 无持仓管理 | 交易数爆炸（2241笔），89.5%连续买入 |
| 2 | 无最小持仓检查 | 1天持仓触发止盈（违反min_hold_days=3） |
| 3 | 无相对收益 | 只计算绝对收益 |
| 4 | 无信号AND组合 | 只有评分制 |
| 5 | 无完整评价体系 | 只有基础指标 |

---

## 二、设计目标

### 2.1 核心原则

```
【三个一致性】
1. 工具调用一致：DataLoader + IndicatorCalculator + RelativeCalculator + 统一回测引擎
2. 执行流程一致：数据加载 → 因子计算 → 相对指标 → 回测 → 评价
3. 评价标准一致：43指标 + 8维度 + 硬性门槛
```

### 2.2 统一架构

```
┌─────────────────────────────────────────────────────────────┐
│                    统一回测引擎 (v8.0)                      │
│                   src/backtest/engine.py                    │
├─────────────────────────────────────────────────────────────┤
│  输入:                                                      │
│    - price_data: Dict[str, pd.DataFrame]  # ETF数据         │
│    - signal_func: callable                   # 信号生成函数  │
│    - benchmark_data: pd.DataFrame            # 大盘基准      │
│    - config: BacktestConfig                  # 回测配置      │
├─────────────────────────────────────────────────────────────┤
│  处理:                                                      │
│    - 持仓管理（检查是否持仓）                                │
│    - 止盈止损（支持min_hold_days）                          │
│    - 相对收益计算                                            │
│    - 多ETF并行                                               │
├─────────────────────────────────────────────────────────────┤
│  输出:                                                      │
│    - BacktestResult（基础指标）                             │
│    - FullMetricsResult（43指标 + 评分）                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 信号模式

支持两种信号模式：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `signal` | pd.Series[bool]，信号触发买入 | 因子AND组合 |
| `score` | pd.Series[float]，评分排序 | 评分选优 |

---

## 三、配置设计

### 3.1 BacktestConfig

```python
@dataclass
class BacktestConfig:
    """统一回测配置"""
    # 止盈止损
    stop_loss: float = -0.04           # 止损4%
    stop_profit: float = 0.06           # 止盈6%
    
    # 持仓管理
    min_hold_days: int = 3              # 最小持仓天数
    max_hold_days: int = 20             # 最大持仓天数
    max_positions: int = 2              # 最大同时持仓数
    
    # 成本
    commission_rate: float = 0.0003      # 佣金0.03%
    slippage_rate: float = 0.0002        # 滑点0.02%
    
    # 评分模式
    min_score: float = 0.6              # 最小评分（评分模式）
    min_factors: int = 2                # 最小因子数
```

### 3.2 回测结果结构

```python
@dataclass
class BacktestResult:
    """基础回测结果"""
    # 收益
    total_return: float                 # 总收益
    annual_return: float               # 年化收益
    relative_return: float             # 相对收益（新增）
    
    # 风险
    max_drawdown: float                # 最大回撤
    max_drawdown_duration: int         # 最大回撤持续天数（新增）
    max_consecutive_loss: int           # 最大连续亏损（新增）
    daily_volatility: float             # 日波动率（新增）
    var_95: float                      # VaR(95%)（新增）
    
    # 风险调整
    sharpe_absolute: float             # 夏普比率（绝对）
    sharpe_relative: float              # 夏普比率（相对，新增）
    
    # 胜率
    win_rate: float                    # 胜率
    profit_loss_ratio: float           # 盈亏比
    avg_profit: float                  # 平均盈利
    avg_loss: float                    # 平均亏损
    
    # 交易
    trade_count: int                   # 交易数
    trades: List[Dict]                 # 交易详情
    
    # 稳健性（新增）
    score: float                       # 综合评分
    pass_rate: float                   # 通过率
    dimension_scores: Dict              # 各维度评分


@dataclass
class FullMetricsResult:
    """完整评价结果（43指标）"""
    result: BacktestResult             # 基础结果
    metrics: Dict[str, float]          # 43个指标
    dimension_scores: Dict[str, float] # 8个维度评分
    hard_reject: List[str]             # 硬性拒绝原因
    recommendation: str                # 建议
```

---

## 四、核心逻辑设计

### 4.1 持仓管理（新增）

```python
def _check_exit(self, pos, current_price, current_date) -> Tuple[bool, str]:
    """检查是否需要平仓"""
    pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
    hold_days = pos['hold_days']
    
    # 1. 先检查持仓天数是否满足最小要求
    if hold_days < self.config.min_hold_days:
        # 未满足最小持仓，不考虑止盈止损
        return False, ""
    
    # 2. 检查止盈止损（满足最小持仓后才生效）
    if pnl_pct <= self.config.stop_loss:
        return True, "止损"
    if pnl_pct >= self.config.stop_profit:
        return True, "止盈"
    
    # 3. 检查最大持仓
    if hold_days >= self.config.max_hold_days:
        return True, "到期"
    
    return False, ""


def _can_open(self, code, positions) -> bool:
    """检查是否可以开仓"""
    # 已在持仓中，不重复买入
    if code in positions:
        return False
    # 达到最大持仓数
    if len(positions) >= self.config.max_positions:
        return False
    return True
```

### 4.2 相对收益计算

```python
def _calculate_relative_return(self, trade, benchmark_df) -> float:
    """计算相对收益"""
    entry_date = trade['entry_date']
    exit_date = trade['exit_date']
    
    # 获取基准在入场和出场日的收盘价
    entry_benchmark = benchmark_df[benchmark_df['date'] == entry_date]['close'].values
    exit_benchmark = benchmark_df[benchmark_df['date'] == exit_date]['close'].values
    
    if len(entry_benchmark) == 0 or len(exit_benchmark) == 0:
        return 0.0
    
    benchmark_return = (exit_benchmark[0] / entry_benchmark[0]) - 1
    relative_return = trade['pnl_pct'] - benchmark_return
    
    return relative_return
```

### 4.3 完整回测流程

```python
def backtest(
    self,
    price_data: Dict[str, pd.DataFrame],
    signal_func: Callable[[pd.DataFrame], pd.Series] = None,
    score_func: Callable[[pd.DataFrame], pd.Series] = None,
    benchmark_data: pd.DataFrame = None,
    start_date: str = None,
    end_date: str = None,
) -> FullMetricsResult:
    """
    统一回测入口
    
    Args:
        price_data: ETF数据字典 {code: df}
        signal_func: 信号生成函数（AND组合模式）
        score_func: 评分函数（评分模式）
        benchmark_data: 大盘基准数据
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        FullMetricsResult: 完整评价结果
    """
    trades = []
    positions = {}  # 持仓管理
    
    # 日期对齐
    all_dates = self._get_trading_dates(price_data, start_date, end_date)
    
    for current_date in all_dates:
        # 1. 获取当日行情
        current_prices = self._get_current_prices(price_data, current_date)
        if not current_prices:
            continue
        
        # 2. 平仓检查
        for code in list(positions.keys()):
            if code not in current_prices:
                continue
            
            should_close, reason = self._check_exit(
                positions[code],
                current_prices[code]['close'],
                current_date
            )
            
            if should_close:
                trade = self._create_trade(positions[code], code, current_date,
                                          current_prices[code]['close'], reason)
                
                # 计算相对收益
                if benchmark_data is not None:
                    trade['relative_return'] = self._calculate_relative_return(trade, benchmark_data)
                
                trades.append(trade)
                del positions[code]
        
        # 3. 开仓检查
        if len(positions) < self.config.max_positions:
            candidates = self._get_candidates(
                current_prices, positions, signal_func, score_func
            )
            
            for code, score in candidates:
                if self._can_open(code, positions) and score >= self.config.min_score:
                    positions[code] = {
                        'entry_price': current_prices[code]['close'],
                        'entry_date': current_date,
                        'entry_score': score,
                        'hold_days': 0
                    }
                    if len(positions) >= self.config.max_positions:
                        break
        
        # 4. 持仓天数+1
        for pos in positions.values():
            pos['hold_days'] += 1
    
    # 5. 期末平仓
    trades.extend(self._close_all_positions(positions, all_dates, current_prices, benchmark_data))
    
    # 6. 计算完整指标
    return self._calculate_full_metrics(trades, start_date, end_date)
```

---

## 五、API设计

### 5.1 信号模式（AND组合）

```python
# 示例：MACD + DMA + SAR 三因子AND组合
def signal_func(df):
    return (df['MACD_hist'] > 0) & (df['DMA'] > 0) & (df['SAR_trend'] > 0.5)

result = backtester.backtest(
    price_data=price_data,
    signal_func=signal_func,
    benchmark_data=benchmark_df,
    start_date='2023-01-01',
    end_date='2024-12-31'
)
```

### 5.2 评分模式（兼容旧接口）

```python
# 示例：评分选优
def score_func(df):
    score = pd.Series(0.5, index=df.index)
    score += (df['MACD_hist'] > 0).astype(float) * 0.3
    score += (df['DMA'] > 0).astype(float) * 0.3
    score += (df['SAR_trend'] / 2) * 0.4
    return score.clip(0, 1)

result = backtester.backtest(
    price_data=price_data,
    score_func=score_func,
    min_score=0.6,
    benchmark_data=benchmark_df,
    start_date='2023-01-01',
    end_date='2024-12-31'
)
```

### 5.3 unified_mining_v7 适配

```python
# 修改后的使用方式
from src.backtest.engine import FactorBacktester, BacktestConfig

# 1. 定义信号
def signal_func(df):
    return combine_signals(df, factor_names, FACTORS_V7)

# 2. 执行回测
backtester = FactorBacktester(
    factors=list(FACTORS_V7.keys()),
    weights={f: 1.0 for f in FACTORS_V7.keys()},
    factor_direction=FACTOR_DIRECTIONS,
    config=BacktestConfig(
        stop_loss=-0.04,
        stop_profit=0.06,
        min_hold_days=3,
        max_hold_days=20,
        max_positions=2,
    )
)

result = backtester.backtest(
    price_data=price_data,
    signal_func=signal_func,
    benchmark_data=benchmark_df,
    start_date='2023-01-01',
    end_date='2024-12-31'
)

# 3. 获取结果
print(f"总分: {result.score}")
print(f"交易数: {result.trade_count}")
print(f"相对收益: {result.relative_return}")
```

---

## 六、改进清单

### 6.1 必须改进（v8.0）

| # | 改进项 | 说明 |
|---|--------|------|
| 1 | 持仓管理 | 检查是否已有持仓，避免重复买入 |
| 2 | min_hold_days | 止盈止损需满足最小持仓天数 |
| 3 | 相对收益 | 计算与大盘的相对收益 |
| 4 | 完整评价 | 接入43指标评价体系 |
| 5 | 唯一入口 | 废弃simple_backtest，统一使用FactorBacktester |

### 6.2 建议改进（v8.1）

| # | 改进项 | 说明 |
|---|--------|------|
| 1 | 分批建仓 | 支持固定金额分批买入 |
| 2 | 风控熔断 | 单日最大亏损限制 |
| 3 | 流动性约束 | 大额交易限制 |
| 4 | 动态仓位 | 根据评分调整仓位 |
| 5 | 因子权重优化 | 机器学习优化权重 |

### 6.3 废弃功能

| # | 废弃项 | 替代 |
|---|--------|------|
| 1 | simple_backtest | FactorBacktester.backtest() |
| 2 | scripts/factor_mining/unified_mining_v7.py | src/backtest/engine.py |
| 3 | scripts/factor_mining/archived/ | 无需恢复 |

---

## 七、迁移计划

### Phase 1: 修复核心逻辑
1. 修改 `src/backtest/engine.py`，添加持仓管理
2. 添加 `min_hold_days` 支持
3. 添加相对收益计算
4. 运行单元测试

### Phase 2: 适配评价体系
1. 接入 `metrics_v7.py` 完整指标
2. 修改返回类型为 `FullMetricsResult`
3. 运行集成测试

### Phase 3: 迁移脚本
1. 修改 `unified_mining_v7.py` 使用新API
2. 删除 `simple_backtest` 函数
3. 运行回归测试

### Phase 4: 清理归档
1. 删除 `scripts/factor_mining/archived/`
2. 删除 `scripts/archived/`
3. 确认无其他回测引擎

---

## 八、验收标准

| # | 标准 | 检查方法 |
|---|------|----------|
| 1 | 无重复买入 | 连续买入交易比例 = 0% |
| 2 | 持仓分布正确 | min_hold_days=3时，持仓<3天比例 < 5% |
| 3 | 相对收益计算正确 | 对比benchmark_return = pnl_pct - relative_return |
| 4 | 完整指标输出 | 43指标 + 8维度评分 + 硬性门槛 |
| 5 | 唯一入口 | grep "simple_backtest" 无结果 |
| 6 | 回归测试通过 | pytest tests/regression/ 100% |

---

## 九、文件变更

### 9.1 修改文件

| 文件 | 变更 |
|------|------|
| `src/backtest/engine.py` | 核心重构 |
| `scripts/factor_mining/unified_mining_v7.py` | API适配 |
| `src/evaluation/metrics_v7.py` | 可能需要小调整 |

### 9.2 删除文件

| 文件 | 原因 |
|------|------|
| `scripts/factor_mining/archived/*` | 废弃版本 |
| `scripts/archived/*` | 废弃脚本 |

### 9.3 新增文件

| 文件 | 说明 |
|------|------|
| `docs/BACKTEST_ENGINE_V8_DESIGN.md` | 本文档 |

---

## 十、执行顺序

```
1. 修改 src/backtest/engine.py
   ├── BacktestConfig 添加字段
   ├── BacktestResult 添加字段
   ├── backtest() 添加持仓管理
   ├── backtest() 支持 min_hold_days
   ├── backtest() 计算相对收益
   └── _calculate_metrics() 接入43指标

2. 单元测试
   ├── test_position_management
   ├── test_min_hold_days
   └── test_relative_return

3. 修改 unified_mining_v7.py
   ├── 移除 simple_backtest
   └── 使用 FactorBacktester

4. 回归测试
   └── 验证原有功能

5. 清理归档
   └── 删除 archived 目录
```