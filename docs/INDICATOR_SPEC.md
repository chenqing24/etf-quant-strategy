# 技术指标规范

> 规范各类技术指标的计算方法

## 1. 概述

技术指标模块提供ETF数据分析所需的各类技术指标计算，包括移动平均线、RSI、成交量比等。

## 2. 指标计算

### 2.1 移动平均线 (MA)

```python
def calculate_ma(df: pd.DataFrame, periods: List[int]) -> pd.DataFrame:
    """计算移动平均线
    
    Args:
        df: 价格数据
        periods: 周期列表 [20, 60, 120]
    """
```

| 指标 | 周期 | 用途 |
|------|------|------|
| MA20 | 20日 | 短期趋势 |
| MA60 | 60日 | 中期趋势 |
| MA120 | 120日 | 长期趋势 |

### 2.2 RSI (相对强弱指数)

```python
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算RSI"""
```

**RSI解读**：

| RSI范围 | 信号 | 含义 |
|---------|------|------|
| <30 | 🔴 超卖 | 可能反弹 |
| 30-50 | ⚪ 中性偏弱 | 观望 |
| 50-70 | ⚪ 中性偏强 | 关注 |
| 70-80 | 🟡 超买预警 | 谨慎 |
| >80 | 🔴 超买 | 考虑卖出 |

### 2.3 成交量比 (Vol Ratio)

```python
def calculate_vol_ratio(df: pd.DataFrame, period: int = 5) -> pd.Series:
    """计算成交量比
    
    今日成交量 / 过去N日平均成交量
    """
```

| Vol Ratio | 信号 |
|-----------|------|
| <0.5 | 缩量 |
| 0.5-1.0 | 正常 |
| 1.0-1.5 | 温和放量 ✅ |
| 1.5-2.0 | 明显放量 |
| >2.0 | 天量 🔴 |

## 3. 因子评分

### 3.1 7因子体系

| 因子 | 满分 | 计算条件 |
|------|:----:|----------|
| 站上120日线 | +3 | close > MA120 |
| 60日均线向上 | +2 | 连续5日MA60上涨 |
| 站上60日线 | +2 | close > MA60 |
| 站上20日线 | +1 | close > MA20 |
| RSI正常 | +2 | RSI14 < 70 |
| 温和放量 | +1 | 1.0 < vol_ratio ≤ 1.5 |
| 涨幅适中 | +1 | 0% < change_pct ≤ 5% |

**总分**：12分

**买入门槛**：≥6分

### 3.2 扣分项

| 条件 | 扣分 |
|------|:----:|
| RSI > 80 | -2 |
| RSI > 70 | -1 |
| vol_ratio > 2.0 | -1 |
| change_pct > 8% | -1 |

## 4. 使用示例

```python
from src.indicator import Indicator

# 计算所有指标
df_ind = Indicator.calculate(df)

# 获取最新值
latest = df_ind.iloc[-1]

print(f"MA20: {latest['ma20']:.3f}")
print(f"MA60: {latest['ma60']:.3f}")
print(f"MA120: {latest['ma120']:.3f}")
print(f"RSI14: {latest['rsi_14']:.1f}")
print(f"Vol Ratio: {latest['vol_ratio']:.2f}")
```

## 5. 修订历史

| 日期 | 版本 | 修改内容 |
|------|------|----------|
| 2026-05-26 | 1.0 | 初始版本 |

---

**关联文档**：
- [SELECTION_RULES.md](./SELECTION_RULES.md) - 选股规则
- [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) - 字段定义