# 回测规范

> 规范每日评分回测的机制和流程

## 1. 概述

回测模块验证策略在实际持仓期间的表现，每天重新评分持仓ETF，检测是否需要调仓。

```
回测流程
    │
    ├── 加载持仓          # 获取当前持仓
    ├── 每日评分          # 用当日数据重新评分
    ├── 对比分数          # 当前分数 vs 买入时分数
    └── 调仓决策          # 分数下降超过阈值则卖出
```

## 2. 核心概念

### 2.1 每日评分

每天用最新数据重新评估持仓ETF：
```python
score = selector.evaluate(df, date)  # 返回(int, List[str])
```

### 2.2 分数阈值

| 分数变化 | 信号 |
|----------|------|
| ≥6分 | ✅ 强势，继续持有 |
| 4-5分 | ⚠️ 注意，关注 |
| <4分 | 🔴 弱势，考虑卖出 |

### 2.3 止损/止盈

| 条件 | 动作 |
|------|------|
| 亏损 ≥5% | 🔴 止损卖出 |
| 盈利 ≥8% | 🟢 止盈卖出 |

## 3. 回测引擎

### 3.1 BacktestEngine类

```python
class BacktestEngine:
    """回测引擎"""
    
    def run_daily_review(self, date: str) -> dict:
        """每日回顾
        
        Args:
            date: 日期 (YYYY-MM-DD)
            
        Returns:
            {
                'positions': [...],      # 持仓状态
                'score_changes': {...},  # 分数变化
                'actions': [...]          # 建议操作
            }
        """
```

### 3.2 回测报告

```python
def generate_backtest_report(self) -> str:
    """生成回测报告"""
```

**报告内容**：
- 总交易次数
- 胜率
- 平均持仓天数
- 最大回撤
- 夏普比率

## 4. 分数计算

### 4.1 7因子评分

| 因子 | 满分 | 条件 |
|------|:----:|------|
| 站上120日线 | +3 | close > MA120 |
| 60日均线向上 | +2 | 连续5日上升 |
| 站上60日线 | +2 | close > MA60 |
| 站上20日线 | +1 | close > MA20 |
| RSI正常 | +2 | RSI14 < 70 |

### 4.2 扣分项

| 条件 | 扣分 |
|------|:----:|
| RSI > 80 | -2 |
| RSI > 70 | -1 |
| 放量超2倍 | -1（谨慎） |

## 5. 使用示例

```python
from src.backtest import BacktestEngine

engine = BacktestEngine()

# 每日回顾
result = engine.run_daily_review('2026-05-26')

for action in result['actions']:
    print(f"{action['code']}: {action['reason']}")

# 生成报告
report = engine.generate_backtest_report()
```

## 6. 修订历史

| 日期 | 版本 | 修改内容 |
|------|------|----------|
| 2026-05-26 | 1.0 | 初始版本 |

---

**关联文档**：
- [SELECTION_RULES.md](./SELECTION_RULES.md) - 7因子评分规则
- [POSITION_MANAGEMENT.md](./POSITION_MANAGEMENT.md) - 持仓管理
- [MONITORING.md](./MONITORING.md) - 监控指标