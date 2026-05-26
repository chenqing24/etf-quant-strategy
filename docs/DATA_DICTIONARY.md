# ETF量化系统 - 数据字典

> 统一字段定义，解决代码中硬编码字段名的问题

## 1. 概述

### 1.1 目的
- 统一ETF系统所有数据字段的命名和定义
- 消除代码中的硬编码字段名
- 为跨模块数据传递提供标准契约

### 1.2 范围
- CSV历史数据字段
- JSON实时数据字段
- 内存数据模型字段
- API请求/响应字段

---

## 2. CSV历史数据格式

### 2.1 标准格式

**文件名**：`{CODE}.csv`（如 `510300.csv`）

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| date | string | ✅ | 日期，YYYY-MM-DD格式 | 2026-05-26 |
| open | float | ✅ | 开盘价 | 3.856 |
| high | float | ✅ | 最高价 | 3.920 |
| low | float | ✅ | 最低价 | 3.840 |
| close | float | ✅ | 收盘价 | 3.890 |
| volume | int | ✅ | 成交量 | 1234567 |

### 2.2 扩展字段（可选）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| amount | float | 成交额（元） |
| change | float | 涨跌额 |
| pct_change | float | 涨跌幅（%，可选） |

### 2.3 命名规范

```python
# ✅ 正确：小写+下划线
df['date']
df['close_price']

# ❌ 错误：驼峰/全大写
df['dateTime']
df['CLOSE']
```

---

## 3. JSON实时数据格式

### 3.1 热数据格式

**路径**：`etf_data_live/hot/{CODE}.json`

```json
{
  "code": "510300",
  "name": "沪深300ETF",
  "price": 3.890,
  "prev_close": 3.856,
  "open": 3.860,
  "high": 3.920,
  "low": 3.840,
  "change": 0.034,
  "change_pct": 0.88,
  "volume": 1234567,
  "amount": 4789012.34,
  "timestamp": "2026-05-26T13:15:30",
  "source": "tencent"
}
```

### 3.2 字段定义

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code | string | ✅ | ETF代码（6位数字） |
| name | string | ❌ | ETF名称 |
| price | float | ✅ | 当前价格 |
| prev_close | float | ✅ | 昨收价 |
| open | float | ✅ | 今日开盘价 |
| high | float | ✅ | 今日最高价 |
| low | float | ✅ | 今日最低价 |
| change | float | ✅ | 涨跌额 |
| change_pct | float | ✅ | 涨跌幅（%） |
| volume | int | ✅ | 成交量 |
| amount | float | ❌ | 成交额 |
| timestamp | string | ✅ | 数据时间戳（ISO 8601） |
| source | string | ❌ | 数据来源 |

---

## 4. 内存数据模型

### 4.1 ETFDataFrame

```python
@dataclass
class ETFDataPoint:
    """单条ETF数据"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    # 可选扩展字段
    amount: Optional[float] = None
    change: Optional[float] = None
    pct_change: Optional[float] = None
```

### 4.2 IndicatorData

```python
@dataclass
class IndicatorData:
    """技术指标数据"""
    # 均线
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma120: Optional[float] = None
    ma250: Optional[float] = None
    
    # 动量指标
    rsi5: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    
    # 成交量指标
    vol_ratio: Optional[float] = None  # 放量倍数（相比MA5）
    vol_ma5: Optional[float] = None
    
    # 趋势指标
    trend: Optional[str] = None  # 'up' | 'down' | 'sideways'
```

---

## 5. 交易数据模型

### 5.1 TradeRecord

```python
@dataclass
class TradeRecord:
    """交易记录"""
    # 基础信息
    id: str                          # UUID，唯一标识
    code: str                        # ETF代码
    name: str                        # ETF名称
    action: str                      # 'buy' | 'sell'
    
    # 成交信息
    price: float                     # 成交价格
    quantity: int                    # 成交数量
    amount: float                    # 成交金额
    
    # 时间信息
    trade_date: str                  # 交易日期 YYYY-MM-DD
    trade_time: str                  # 交易时间 HH:MM:SS
    created_at: str                   # 记录创建时间
    
    # 关联信息
    signal_date: Optional[str] = None  # 信号日期
    reason: Optional[str] = None      # 交易原因
```

### 5.2 Position

```python
@dataclass
class Position:
    """持仓信息"""
    code: str                        # ETF代码
    name: str                        # ETF名称
    quantity: int                    # 持仓数量
    avg_cost: float                  # 平均成本价
    
    # 盈亏计算
    current_price: float             # 当前价格
    market_value: float              # 市值
    unrealized_pnl: float            # 浮动盈亏
    pnl_pct: float                   # 盈亏比例（%）
    
    # 风控信息
    stop_loss: float                 # 止损价
    stop_gain: float                 # 止盈价
    trailing_active: bool           # 移动止盈是否激活
    
    # 时间信息
    entry_date: str                 # 买入日期
    hold_days: int                  # 持仓天数
```

---

## 6. 决策结果数据模型

### 6.1 DecisionResult

```python
@dataclass
class DecisionResult:
    """决策结果"""
    # 决策信息
    action: Literal['buy', 'sell', 'hold', 'wait']
    code: Optional[str]              # ETF代码
    name: Optional[str]              # ETF名称
    
    # 价格信息
    signal_price: float             # 信号价格
    current_price: Optional[float]  # 当前价格
    price_deviation: Optional[float] # 价格偏差（%）
    
    # 风控信息
    stop_loss: Optional[float]       # 止损价
    stop_gain: Optional[float]       # 止盈价
    
    # 评分信息
    score: Optional[int]            # 总分
    reasons: Optional[List[str]]    # 选股理由
    
    # 技术指标
    indicators: Optional[IndicatorData]  # 技术指标
    
    # 元信息
    timestamp: str                  # 决策时间
    period_start: Optional[str] = None   # 持仓期开始
    period_end: Optional[str] = None     # 持仓期结束
```

### 6.2 BacktestResult

```python
@dataclass
class BacktestResult:
    """回测结果"""
    # 核心指标
    return_pct: float               # 收益率（%）
    max_drawdown: float             # 最大回撤（%）
    sharpe_ratio: float             # 夏普比率
    win_rate: float                 # 胜率（%）
    
    # 交易统计
    total_trades: int               # 总交易次数
    winning_trades: int            # 盈利交易次数
    losing_trades: int              # 亏损交易次数
    avg_hold_days: float            # 平均持仓天数
    
    # 时间信息
    period_start: str               # 回测开始日期
    period_end: str                 # 回测结束日期
```

---

## 7. ETF代码映射

### 7.1 核心ETF代码

| 代码 | 名称 | 类型 | 排除 |
|------|------|------|------|
| 510300 | 沪深300 | 宽基 | ❌ |
| 510500 | 中证500 | 宽基 | ❌ |
| 159919 | 创业板 | 宽基 | ❌ |
| 515050 | 5GETF | 行业 | ❌ |
| 516050 | 科创成长 | 行业 | ❌ |
| 512010 | 医药ETF | 行业 | ❌ |
| 512760 | 芯片ETF | 行业 | ❌ |

### 7.2 排除规则

| 类型 | 示例 | 排除原因 |
|------|------|----------|
| 红利ETF | 512890 | 分红特殊处理 |
| 港股通 | 513550 | 汇率风险 |
| 证券ETF | 512880 | 强周期 |
| 债券ETF | 511010 | 无趋势性 |
| 黄金ETF | 518880 | 商品属性 |

---

## 8. 错误码定义

### 8.1 系统错误码

| 错误码 | 含义 | HTTP状态码 |
|--------|------|------------|
| E1000 | 系统未知错误 | 500 |
| E1001 | 系统初始化失败 | 500 |

### 8.2 数据错误码

| 错误码 | 含义 | 处理建议 |
|--------|------|----------|
| E2001 | 数据文件不存在 | 检查路径 |
| E2002 | 数据格式错误 | 检查CSV格式 |
| E2003 | 数据不足 | 等待数据累积 |
| E2004 | 数据过期 | 重新获取 |

### 8.3 策略错误码

| 错误码 | 含义 | 处理建议 |
|--------|------|----------|
| E3001 | 市场过滤失败 | 空仓观望 |
| E3002 | 无合格标的 | 降低门槛 |
| E3003 | 止损触发 | 执行卖出 |
| E3004 | 止盈触发 | 执行卖出 |

---

## 9. 修订历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-26 | v1.0 | 初始版本 |