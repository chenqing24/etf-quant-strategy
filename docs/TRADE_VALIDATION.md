# 交易验证规范

> 规范买入前实时校验机制

## 1. 概述

交易验证模块在用户执行买入前，对信号价格与实时价格进行比对，确保偏差在可接受范围内。

```
交易验证流程
    │
    ├── 信号校验          # 信号价 vs 当前价
    ├── 数据源降级        # 腾讯 → 东方财富 → 新浪
    ├── 技术指标计算      # RSI、偏离度
    └── 风险提示          # 偏离警告、RSI超买
```

## 2. 核心概念

### 2.1 价格偏差

```
偏差 = (当前价 - 信号价) / 信号价 * 100%
```

| 偏差范围 | 信号 |
|----------|------|
| ≤5% | ✅ 正常 |
| 5%~10% | ⚠️ 偏高 |
| >10% | 🔴 建议重新评估 |

### 2.2 RSI指标

| RSI范围 | 信号 |
|---------|------|
| <70 | ✅ 正常 |
| 70~80 | ⚠️ 轻微超买 |
| >80 | 🔴 超买警告 |

### 2.3 距止损/止盈

```
距止损 = (当前价 - 止损价) / 当前价 * 100%
距止盈 = (止盈价 - 当前价) / 当前价 * 100%
```

## 3. 数据源降级

### 3.1 优先级

1. **腾讯财经** (https://web.ifzq.gtimg.cn)
2. **东方财富** (http://push2his.eastmoney.com)
3. **新浪财经** (https://hq.sinajs.cn)

### 3.2 降级逻辑

```python
for source in [DataSource.TENCENT, DataSource.EMF, DataSource.SINA]:
    try:
        data = fetch_from_source(source, code)
        if data:
            return data
    except Exception as e:
        logger.warning(f"{source.value} API异常: {e}")
        continue
```

### 3.3 数据格式转换

| 字段 | 来源 | 转换 |
|------|------|------|
| price | 实时价格 | float |
| pct | 涨跌幅 | 百分比 |
| volume | 成交量 | int |
| name | 名称 | string |

## 4. 验证结果

### 4.1 ValidationResult

```python
@dataclass
class ValidationResult:
    code: str                    # ETF代码
    signal_price: float          # 信号价格
    current_price: float          # 当前价格
    price_deviation: float        # 价格偏差(%)
    rsi_5: float                 # RSI(5日)
    rsi_14: float                # RSI(14日)
    stop_loss: float             # 止损价
    take_profit: float            # 止盈价
    target_gap: float            # 距止盈(%)
    stop_gap: float              # 距止损(%)
    recommendation: str          # 建议
    warning_messages: List[str]  # 警告信息
```

### 4.2 建议类型

| 建议 | 条件 |
|------|------|
| `立即买入` | 偏差≤3% 且 RSI<70 |
| `谨慎买入` | 偏差3-8% 或 RSI 70-80 |
| `建议观望` | 偏差>8% 或 RSI>80 |
| `建议等待` | 偏差>15% |

## 5. 使用示例

```python
from src.trade_validator import TradeValidator, DataSource

validator = TradeValidator()

# 验证买入信号
result = validator.validate(
    code='515050',
    signal_price=1.101,
    stop_loss=1.046,
    take_profit=1.189
)

print(f"偏差: {result.price_deviation:+.1f}%")
print(f"建议: {result.recommendation}")
```

## 6. 修订历史

| 日期 | 版本 | 修改内容 |
|------|------|----------|
| 2026-05-26 | 1.0 | 初始版本 |

---

**关联文档**：
- [EXECUTION_LAYER.md](./EXECUTION_LAYER.md) - 交易执行流程
- [SELECTION_RULES.md](./SELECTION_RULES.md) - 选股规则