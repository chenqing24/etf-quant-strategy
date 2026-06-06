# SOP-07：v9 Mission 因子集成标准流程

**版本**：v1.0
**创建日期**：2026-06-07
**作者**：福猫管家 🐱
**目标读者**：所有 v9 mission 维护者
**状态**：开发路线图

---

## 一、目标

为 v9 mission 的"**新因子集成**"提供标准化流程，避免以下历史问题：

| 历史问题 | 出现时间 | 影响 |
|----------|----------|------|
| v9_v7a_debug 破坏回测 | 2026-05 | 全量回测重跑 3 次 |
| v9_v8_top3_updated 期望错位 | 2026-06 | 5 测试失败 |
| US-026 36 因子未集成 v9 | 2026-06 | W4/W3/W2 仅登记候选 |

---

## 二、触发条件

满足以下**任一**条件，必须走本 SOP：

1. **新因子加入 v9 mission**（v9_v{N+1}_*.py）
2. **v9 决策核心改动**（decision.py / engine.py）
3. **v9 风控参数调整**（stop_profit / stop_loss / max_holdings）
4. **W4/W3/W2 候选因子正式集成**

---

## 三、Phase 1：设计文档（强制停止点）

### 1.1 输出物

```
docs/US-{编号}-DESIGN.md
```

### 1.2 必须包含 7 个章节

1. **背景**：为什么需要集成？（v9 当前缺什么？）
2. **目标**：集成后达到什么指标？（Sharpe > 1.5？pass_rate > 0.5？）
3. **设计**：因子如何与 v9 现有 15 因子共存？（加权？投票？分层？）
4. **验收标准**：4 项强制：
   - [ ] 新因子必须通过 A2（15 ETF WalkForward）
   - [ ] 新因子必须通过 A3（5d+20d IC 检验）
   - [ ] 新因子必须通过 A4（IS→OOS 衰减 < 0.05）
   - [ ] v9 全量回测不退化（Sharpe 不降 > 10%）
5. **回归测试清单**：至少 5 个用例：
   - [ ] 旧 v9 决策输出不变（基线对比）
   - [ ] 新因子信号能正确触发买入
   - [ ] 风控参数不被破坏
   - [ ] trade_history 记录正确
   - [ ] 钉钉告警链路正常
6. **风险清单**：3 个常见风险：
   - [ ] 因子过拟合（必须用 A4 IS→OOS 衰减）
   - [ ] 现金/持仓状态错位（必须测 US-024 路径）
   - [ ] v9 决策延迟（必须测 cron 14:30 时长）
7. **回滚方案**：1 步回滚（`git revert` 或 config 切回）

### 1.3 等用户确认（强制停止点）

按 SOUL 规则 4.1：**设计文档必须等用户确认后再实现**。

---

## 四、Phase 2：实现（设计确认后）

### 2.1 文件命名规范

```
scripts/experiment/v9_v{N+1}_{name}.py
```

示例：`v9_v9_volatility_combo.py`（W4+W3+W2 集成）

### 2.2 代码模板

```python
#!/usr/bin/env python3
"""
v9 mission - {因子名} 集成
US-{编号} 实现
设计文档：docs/US-{编号}-DESIGN.md
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from src.indicators.volatility import (  # 新因子必须放 src/indicators/
    w4_rv_change,
    w3_hist_vol_change,
    w2_bb_width_change,
)


class V9{N+1}VolatilityCombo:
    """v9 v{N+1} - 波动率类因子组合"""

    VERSION = "v{N+1}"
    NAME = "{因子名}"

    def __init__(self, config: dict = None):
        self.config = config or {
            'w4_weight': 0.40,
            'w3_weight': 0.30,
            'w2_weight': 0.30,
            'threshold': 0.5,  # combo > 0.5 → 买入
        }

    def compute_signal(self, df: pd.DataFrame) -> pd.Series:
        """计算因子信号（0/1）"""
        w4 = w4_rv_change(df).fillna(False).astype(int)
        w3 = w3_hist_vol_change(df).fillna(False).astype(int)
        w2 = w2_bb_width_change(df).fillna(False).astype(int)
        combo = (
            self.config['w4_weight'] * w4 +
            self.config['w3_weight'] * w3 +
            self.config['w2_weight'] * w2
        )
        return (combo > self.config['threshold']).astype(int)

    def integrate_with_v9(self, v9_scores: pd.Series) -> pd.Series:
        """与 v9 现有分数合并"""
        # 默认策略：v9 分数 > 0 AND 波动率信号 = 1 → 触发
        return (v9_scores > 0) & (self.compute_signal(...) == 1)
```

### 2.3 配置注册

```python
# src/constants.py 加 1 行
V9_FACTOR_REGISTRY = {
    'v9_v1': {...},  # 现有 15 因子
    'v9_v9_volatility_combo': {  # 新增
        'class': 'V99VolatilityCombo',
        'weight': 0.20,  # v9 总分数中的权重
        'enabled': True,
    },
}
```

---

## 五、Phase 3：测试（5 类强制）

### 3.1 单元测试（必跑）

```python
# tests/unit/test_us{N+1}_v9_volatility.py
def test_v9_v{N+1}_signal_basic():
    """基本信号计算"""
    combo = V9{N+1}VolatilityCombo()
    signal = combo.compute_signal(mock_df)
    assert signal.dtype == int
    assert signal.isin([0, 1]).all()

def test_v9_v{N+1}_integrate_with_v9():
    """与 v9 分数合并"""
    v9_scores = pd.Series([0.5, -0.2, 0.8])
    # ...

def test_v9_v{N+1}_weight_config():
    """权重配置正确"""
    combo = V9{N+1}VolatilityCombo({'w4_weight': 0.5})
    assert combo.config['w4_weight'] == 0.5
```

### 3.2 集成测试（必跑）

```python
# tests/integration/test_us{N+1}_v9_e2e.py
def test_v9_e2e_with_volatility():
    """v9 决策 e2e（含波动率因子）"""
    # 用 v9 决策引擎跑一遍
    # 验证：买入/卖出信号 + trade_history + report
    ...
```

### 3.3 回归测试（必跑）

```python
# tests/regression/test_v9_baseline.py
def test_v9_decision_output_unchanged():
    """v9 决策输出不变（基线对比）"""
    # 用同样的输入数据
    # 旧 v9 输出 vs 新 v9 输出（不含新因子时）
    # 字节级一致
    ...
```

### 3.4 真实数据契约测试（必跑）

```python
# tests/integration/test_us{N+1}_real_data.py
def test_real_data_512660():
    """512660 军工 ETF 真实数据测试"""
    loader = DataLoader()
    df = loader.load(codes=['512660'])
    combo = V9{N+1}VolatilityCombo()
    signal = combo.compute_signal(df)
    assert signal.isin([0, 1]).all()
    # 抽样验证：手动算 5 个点对比
```

### 3.5 cron 集成测试（必跑）

```python
# tests/integration/test_us{N+1}_cron.py
def test_cron_14_30_invocation():
    """cron 14:30 调度测试"""
    # 模拟 cron 触发
    # 验证：决策报告生成 + 钉钉发送 + trade_history 写入
    ...
```

---

## 六、Phase 4：上线（3 步）

### 6.1 模拟盘（7 天强制）

```bash
# 1. 启用模拟盘
python -m src.cli.decision -m eval --simulate  # 7 天模拟盘
# 2. 每日检查：模拟盘结果 vs 实盘预期
# 3. 7 天后评估：是否转入实盘
```

### 6.2 实盘（小仓位 2 周）

```bash
# 1. 配置 1000 元小仓位
# 2. cron 14:30 自动跑
# 3. 每日 16:00 人工核对
# 4. 2 周后评估：是否扩大仓位
```

### 6.3 监控（持续）

```bash
# 已加 cron（id=8782c244，每日 14:00）
# 异常检测：IC < 0.02 持续 5 天 → 钉钉告警
```

---

## 七、Phase 5：监控与回滚

### 7.1 监控指标

| 指标 | 阈值 | 告警 |
|------|:---:|:---:|
| 5d IC | < 0.02 | 钉钉 WARNING |
| 15 ETF 通过率 | < 30% | 钉钉 CRITICAL |
| pass_rate | < 0.5 | 钉钉 CRITICAL |
| 实盘 Sharpe | < 0.5 | 人工介入 |

### 7.2 回滚流程（1 步）

```bash
# 1. config 切回旧 v9
vim src/constants.py  # V9_FACTOR_REGISTRY['v9_v9_volatility_combo']['enabled'] = False
# 2. 验证 cron 决策报告不变
# 3. 监控 3 天
```

### 7.3 失败重试

如果回滚后 v9 仍异常：
1. `git revert <commit>` 1 步回滚
2. `git tag v9-pre-us{N+1}-rollback`
3. 立即通知用户

---

## 八、检查清单（开发前必查）

- [ ] **设计文档已确认**（US-{编号}-DESIGN.md）
- [ ] **A2/A3/A4 验证已通过**（data/US-{编号}_*.json）
- [ ] **5 类测试全部写完**（单元/集成/回归/真实数据/cron）
- [ ] **pre-commit 拦截通过**（无硬编码）
- [ ] **回归测试基线已保存**（data/v9_baseline.json）
- [ ] **钉钉告警已测试**（人工发 1 次测试消息）

---

## 九、相关文档

- [SOP-01 数据挖掘标准流程](./SOP_01_DATA_MINING.md) - 因子挖掘
- [SOP-02 重构与修复开发流程](./SOP_02_REFACTOR_DEV.md) - 通用重构
- [SOP-03 实验执行标准流程](./SOP_03_EXPERIMENT.md) - 批量实验
- [data/US-026_top3_volatility_factors.json](../data/US-026_top3_volatility_factors.json) - 3 因子配置
- [data/US-026_a3a2a4_report.json](../data/US-026_a3a2a4_report.json) - 验证结果

---

## 十、版本历史

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| v1.0 | 2026-06-07 | 初版（D 选项）| 福猫管家 🐱 |
