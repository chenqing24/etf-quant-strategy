```yaml
---
file: TRADE_RECORD_SPEC.md
purpose: 交易记录字段规范（决策上下文、模型参数、快照引用）
used_by:
  - tracker.py
  - decision_cli
status: active
last_review: 2026-06-08
review_interval: weekly
---
```

# 交易记录规范（TRADE_RECORD_SPEC）

> 版本: 1.0 | 生效: 2026-06-01
> 引用: Q-009 改进项

## 目的

确保每笔交易都自带**决策上下文**，包括：
- 用了什么模型
- 策略全维度参数
- 评价指标
- 决策快照引用

这样事后能完整追溯：为什么买 → 当时怎么评估 → 实盘表现如何。

## 必填字段

```python
@dataclass
class TradeRecord:
    # ===== 基础字段 =====
    code: str                    # ETF代码 (如 '159611')
    name: str                    # ETF名称
    action: str                  # 'buy' / 'sell'
    price: float                 # 成交价
    quantity: int                # 数量
    amount: float                # 金额 = price × quantity
    date: str                    # 交易日期 (YYYY-MM-DD)
    reason: str                  # 交易原因

    # ===== 决策上下文（Q-009 必填）=====
    model: str                   # 模型名 (如 'ETF量化决策v8_sop')
    strategy: dict               # 策略配置（见下）
    evaluation: dict             # 评价指标（见下）
    snapshot_ref: str            # 决策快照文件路径
```

## 策略配置 schema

```python
{
    "selection": {
        "score_threshold": int,  # 选股分数门槛
        "top_n": int            # 选股数量
    },
    "position": {
        "hold_count": int,      # 持仓数量
        "weights": List[float]  # 仓位权重
    },
    "rebalance": {
        "rebalance_days": int   # 调仓周期
    },
    "risk_control": {
        "stop_loss": float,     # 止损比例
        "stop_gain": float,     # 止盈比例
        "max_hold_days": int    # 最大持仓天数
    },
    "trailing_stop": {
        "enabled": bool,
        "threshold": float,
        "stop": float
    },
    "market_filter": {
        "ma_period": int,
        "enabled": bool
    }
}
```

## 评价指标 schema

```python
{
    "single_factor_count": int,     # 参与评估的单因子数
    "total_combinations": int,      # 参与回测的组合数
    "avg_sharpe": float,            # 平均夏普
    "avg_return": float,            # 平均收益
    "model_version": str            # 模型版本号
}
```

## 决策快照引用

`snapshot_ref` 指向的文件应包含：
- 完整的策略配置
- 全维度评价指标
- Top N 推荐
- 回测最后 10 条交易

参考：`etf_data_live/decision_snapshot.json`

## 示例

```json
{
  "code": "159611",
  "name": "电力ETF广发",
  "action": "buy",
  "price": 1.251,
  "quantity": 4700,
  "amount": 5879.7,
  "date": "2026-06-01",
  "reason": "策略推荐",
  "model": "ETF量化决策v8_sop",
  "strategy": {
    "selection": {"score_threshold": 6, "top_n": 30},
    "risk_control": {"stop_loss": -0.06, "stop_gain": 0.10}
  },
  "evaluation": {
    "single_factor_count": 12,
    "total_combinations": 4125,
    "avg_sharpe": 1.408,
    "avg_return": 0.3491,
    "model_version": "v8_sop"
  },
  "snapshot_ref": "etf_data_live/decision_snapshot.json"
}
```

## 检查规则

```python
def validate_trade_record(record: dict) -> List[str]:
    """验证交易记录完整性"""
    errors = []
    required = ['code', 'name', 'action', 'price', 'quantity', 'amount', 'date']
    for field in required:
        if field not in record:
            errors.append(f"缺失基础字段: {field}")

    # Q-009 必填字段
    context_fields = ['model', 'strategy', 'evaluation', 'snapshot_ref']
    for field in context_fields:
        if field not in record:
            errors.append(f"缺失决策上下文: {field}")

    return errors
```

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-06-01 | 初始版本，建立规范（Q-009 改进）|
