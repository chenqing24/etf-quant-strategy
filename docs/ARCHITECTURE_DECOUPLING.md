# 回测引擎解耦改造（US-009）

**Story ID**: US-009
**优先级**: P0（架构原则）
**创建日期**: 2026-06-04
**状态**: 🚧 Phase 4 实施中

---

## 1. 用户架构原则（2026-06-04 明确）

> "我们的回测引擎应该是对立的、和策略是解耦的，
> 也就是说引擎本身不能包含固定的策略，而是独立的。"

**原则表述**：
- **回测引擎独立**（不依赖具体策略）
- **执行 ≠ 策略**（引擎做执行，策略做决策）
- **策略可插拔**（任何符合接口的策略都能跑）

---

## 2. 现有违规（架构审计）

`src/backtest/engine.py` (679 行) 的违规点：

| 位置 | 现状 | 违反原则 |
|------|------|----------|
| `BacktestConfig.use_selector` | 引擎内置 Selector 评分 | 引擎含固定策略 |
| `BacktestConfig.score_threshold` | 配置含策略阈值 | 配置污染 |
| `FactorBacktester._get_score()` | 引擎内嵌 Selector 调用 | 引擎含策略逻辑 |
| `backtest()` 主循环 `if use_selector` 分支 | 引擎自己做选股 | 引擎含策略 |

---

## 3. 解耦设计（Phase 3 方案）

### 3.1 引擎只做 4 件事

```python
class FactorBacktester:
    """回测引擎（纯执行，零策略）"""
    
    def backtest(
        self,
        price_data: Dict[str, DataFrame],
        signal_func: Callable[[DataFrame], pd.Series],  # ★ 必传，外部信号
        start_date: str = None,
        end_date: str = None,
    ) -> BacktestResult:
        """
        引擎职责（解耦后）:
        1. 日期循环
        2. 持仓管理（positions dict）
        3. 调 signal_func(date, df_dict) 拿外部信号
        4. T+1 撮合 / 仓位计算 / 损益统计
        """
```

### 3.2 接口契约

```python
SignalFunction = Callable[[str, Dict[str, DataFrame]], Dict[str, Signal]]
# 签名: signal_func(date, df_dict) -> {code: Signal}
# 例: Combiner 信号函数
#   def combiner_signals(date, df_dict):
#       regime = detect_market_regime(...)
#       signals = combiner.select_signals(df_dict, regime)
#       return {s.code: s for s in signals}
```

### 3.3 改动范围

| 文件 | 改动 |
|------|------|
| `src/backtest/engine.py` | 删 use_selector / _get_score；signal_func 改必传；加解耦注释 |
| `src/strategy/combiner.py` | 暴露 `combiner_signals(date, df_dict)` 适配接口 |
| `scripts/validators/wf4_us016.py` | 改造回测调用（用 Combiner 信号函数）|
| 7 个使用回测的测试 | 适配新接口 |

### 3.4 兼容性策略

按"向后兼容"——保留 `use_selector` 旧路径但加 deprecation warning，让老测试有时间迁移。

---

## 4. 验收标准

- [ ] `BacktestConfig` 删 `use_selector` 字段
- [ ] `FactorBacktester._get_score` 删（移到 `Selector.evaluate`）
- [ ] `backtest(signal_func=...)` 必传
- [ ] `Combiner.combiner_signals(date, df_dict)` 接口
- [ ] `wf4_us016.py` 改造：真用 Combiner 信号驱动回测
- [ ] 全量回归通过（D8=B）
- [ ] 5年4折回测重跑：v3 真的按市态切换策略

---

## 5. 风险控制

| 风险 | 缓解 |
|------|------|
| 老测试因 signal_func 必传而失败 | 兼容层 + deprecation warning |
| v3 回测效果仍差（说明方案本身有问题）| 保留 wf4_us015 baseline 对比 |
| FactorBacktester 改造太大 | 小步 commit：先删字段 → 再删方法 → 改接口 |

---

## 6. 调研来源（按 SOUL 规则 13）

| 框架 | 架构 | 来源 |
|------|------|------|
| Backtrader | Strategy 子类化注入，Cerebro 引擎 | 业界标杆 |
| Zipline | Pipeline API + Algorithm | 业界标杆 |
| VectorBT | Portfolio = 策略 + 引擎 | 业界标杆 |
| QuantConnect | Alpha 模型独立 | 业界标杆 |

---

## 7. 后续影响

- v3 (US-007) 真的能按市态切换策略 ✅
- US-002~008 已有产物不需要大改
- 老 `use_selector` 路径保留（向后兼容）

---

*创建: 2026-06-04 | 用户原则: 回测引擎应该是对立的、和策略是解耦的*
