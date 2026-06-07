# US-028 W4 RV v9 mission 集成设计文档

**版本**：v1.0
**创建日期**：2026-06-07
**作者**：福猫管家 🐱
**依据**：SOP-07 v9 mission 因子集成标准流程
**US-027 状态**：C+A 完成（单因子部署 + 1 周监控启动）

---

## 一、背景

US-026 / US-027 完整因子挖掘 + 严格 WalkForward 验证发现：
- **W4_RV_Change**（已实现波动率变化）是**唯一稳健因子**
  - 5d IC = 0.0859（强）
  - 20d IC = 0.0371（强）
  - 15 ETF WalkForward OOS/IS = 0.77（**9/15 通过**）
  - 严格 median OOS/IS = **0.12**（**6 因子中唯一正**）
- 其他 5 因子（C1/V6/T9/M5/T7）严格验证下**全负 median**
- 1 周监控数据收集（2026-06-07 ~ 2026-06-14）已启动

**v9 mission 现状**：
- 核心：`v9_v1_single_factor.py`（15 因子单因子验证）
- 决策：`src/cli/decision.py`（通用 MA 趋势策略，**未与 7 因子组合打通**）
- 风控：max_holdings=2 / stop_profit=6% / stop_loss=10%（src/constants.py）

**集成需求**：W4 RV 作为 v9 新因子，**单因子部署**（不带 W3/W2，避免拉低）。

---

## 二、目标

### 业务目标
- W4 RV 因子加入 v9 决策，单因子 weight=1.0
- 5 个工作日内收集监控数据
- 1 周后（2026-06-14）评估通过后正式集成

### 技术目标
- W4 RV 信号可正确触发买入/卖出
- 现金/持仓状态正确
- trade_history 正确记录
- 钉钉告警正常
- 决策报告生成正常

### 性能目标
- 5d IC ≥ 0.04（强 IC 阈值）
- 15 ETF WalkForward OOS/IS ≥ 0.5
- pass_rate ≥ 0.5
- 实盘 Sharpe ≥ 1.0（小仓位 2 周验证）

---

## 三、设计

### 3.1 文件结构

```
scripts/experiment/v9_v9_w4_rv.py  # 集成主脚本
src/indicators/volatility.py        # W4 RV 因子函数（已存在）
src/constants.py                    # 注册 v9_v9_w4_rv
tests/unit/test_us028_w4_rv.py      # 单元测试
tests/integration/test_us028_e2e.py # 集成测试
tests/regression/test_v9_baseline.py # 回归测试
docs/US-028-DESIGN.md               # 本文档
data/US-028_deployment_report.json  # 部署报告
```

### 3.2 因子函数（已存在，src/indicators/volatility.py）

```python
def w4_rv_change(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """W4: 已实现波动率变化（RV 放大 → 买入信号）
    
    Args:
        df: K线数据（必须含 close 列）
        n: 滚动窗口（默认 20 日）
    
    Returns:
        pd.Series[bool]: True = 买入信号
    """
    log_ret = np.log(df['close'] / df['close'].shift(1))
    rv = np.sqrt((log_ret ** 2).rolling(n).sum() * 252)
    rv_change = rv - rv.shift(n)
    return (rv_change > 0).fillna(False)
```

### 3.3 v9 集成主类（v9_v9_w4_rv.py）

```python
class V9V9W4RV:
    """W4 RV v9 集成（US-028）"""
    
    VERSION = "v9_v9"
    NAME = "W4_RV_Change"
    SOURCE = "US-026 + US-027 严格验证"
    
    def __init__(self, config: dict = None):
        self.config = config or {
            'window_n': 20,
            'threshold': 0.0,  # RV 变化 > 0
            'weight_in_v9': 1.0,  # 单因子部署
        }
    
    def compute_signal(self, df: pd.DataFrame) -> pd.Series:
        """计算 W4 RV 买入信号（0/1）"""
        return w4_rv_change(df, n=self.config['window_n']).astype(int)
    
    def integrate_with_v9(self, v9_scores: pd.Series, df: pd.DataFrame) -> pd.Series:
        """与 v9 现有分数合并
        
        策略: v9 分数 > 0 AND W4 RV 信号 = 1 → 触发买入
        """
        w4_signal = self.compute_signal(df)
        return (v9_scores > 0) & (w4_signal == 1)
```

### 3.4 配置注册（src/constants.py）

```python
V9_FACTOR_REGISTRY = {
    'v9_v1': {...},  # 现有 15 因子
    'v9_v9_w4_rv': {  # 新增
        'class': 'V9V9W4RV',
        'weight': 1.0,
        'enabled': True,  # 1 周监控通过后启用
    },
}
```

---

## 四、验收标准（按 SOP-07，4 项强制）

### 4.1 A2 验证
- [ ] 15 ETF WalkForward OOS/IS > 0.5
- [ ] pass_rate ≥ 0.5
- [ ] **已完成**（US-026：9/15 ETF OOS/IS>0.5）

### 4.2 A3 IC 检验
- [ ] 5d IC > 0.04
- [ ] 20d IC > 0.02
- [ ] **已完成**（US-026：5d=0.0859, 20d=0.0371）

### 4.3 A4 IS→OOS 衰减
- [ ] IS→OOS 衰减 < 0.05
- [ ] **已完成**（US-026：IS=0.1148 → OOS=0.1425，OOS > IS = +0.0277）

### 4.4 v9 全量回测不退化
- [ ] Sharpe 不降 > 10%
- [ ] max_drawdown 不恶化
- [ ] 胜率不降

---

## 五、回归测试清单（5 类必跑）

### 5.1 单元测试（tests/unit/test_us028_w4_rv.py）
- [ ] test_w4_rv_basic_signal: 基本信号计算正确
- [ ] test_w4_rv_with_nan: NaN 处理不崩
- [ ] test_w4_rv_with_short_data: 短数据不崩
- [ ] test_v9_v9_w4_rv_class: 集成类初始化正确
- [ ] test_integrate_with_v9: 与 v9 分数合并逻辑正确

### 5.2 集成测试（tests/integration/test_us028_e2e.py）
- [ ] test_e2e_full_workflow: e2e 流程跑通
- [ ] test_cron_invocation: cron 14:30 调度测试
- [ ] test_dingtalk_alert: 钉钉告警测试

### 5.3 回归测试（tests/regression/test_v9_baseline.py）
- [ ] test_v9_output_unchanged: v9 决策输出**字节级一致**（不启用 W4 RV）
- [ ] test_v9_holdings_unchanged: 持仓状态不变

### 5.4 真实数据契约测试（tests/integration/test_us028_real_data.py）
- [ ] test_512660_w4_rv: 512660 军工 ETF 真实数据
- [ ] test_515050_w4_rv: 515050 通信 ETF 真实数据
- [ ] test_15_etf_w4_rv: 15 ETF 全部真实数据

### 5.5 cron 集成测试
- [ ] test_cron_14_30: 14:30 cron 调度
- [ ] test_alert_when_ic_low: IC < 0.02 持续 5 天告警

---

## 六、风险清单（3 个常见风险）

### 6.1 因子过拟合
- **风险**：W4 RV 在历史数据强，但未来失效
- **缓解**：US-026 + US-027 双重验证（5 年数据 + 严格 WalkForward）
- **监控**：5d IC < 0.02 持续 5 天 → 钉钉告警（已加）

### 6.2 现金/持仓状态错位
- **风险**：W4 RV 信号与 trade_history 不同步
- **缓解**：复用 US-024 record_buy/sell 事务顺序（检查 → 入库 → 返回）
- **测试**：US-005 + US-008 + US-015 回归测试

### 6.3 v9 决策延迟
- **风险**：W4 RV 集成后 cron 14:30 超时
- **缓解**：W4 RV 计算 0.07s/因子（5 年数据），预计 1s 完成
- **测试**：cron 14:30 总时长 < 60s

---

## 七、回滚方案（1 步）

### 7.1 配置文件回滚
```python
# src/constants.py
V9_FACTOR_REGISTRY['v9_v9_w4_rv']['enabled'] = False
```

### 7.2 git 回滚（如配置回滚无效）
```bash
git revert <us-028-commit>
# 或
git reset --hard <us-028-pre-commit>
```

### 7.3 完整回滚（极端情况）
```bash
# 1. config 改回
vim src/constants.py  # enabled = False
# 2. cron 删除
qwenpaw cron pause 8782c244
# 3. 监控脚本暂停
# 4. 通知用户
```

---

## 八、实施时间表

| 阶段 | 内容 | 时间 | 状态 |
|------|------|------|:---:|
| **设计** | 本文档 | 2026-06-07 07:00 | ✅ |
| **1 周监控** | 5 个工作日数据收集 | 2026-06-07 ~ 06-14 | 🟡 进行中 |
| **实现** | v9_v9_w4_rv.py + constants.py | 2026-06-14 | ⏳ |
| **单元测试** | 5 个测试 | 2026-06-14 | ⏳ |
| **集成测试** | 3 个测试 | 2026-06-14 | ⏳ |
| **回归测试** | 2 个测试 | 2026-06-14 | ⏳ |
| **真实数据测试** | 3 个测试 | 2026-06-15 | ⏳ |
| **模拟盘** | 7 天 | 2026-06-15 ~ 06-22 | ⏳ |
| **小仓位** | 2 周 | 2026-06-23 ~ 07-07 | ⏳ |
| **全量上线** | 评估后 | 2026-07-08+ | ⏳ |

---

## 九、3 个待确认点

### 9.1 W3/W2 集成策略
- **选项 A**：仅 W4 RV 单因子（**推荐**）
- **选项 B**：W4 + W3/W2 加权（之前 v1.0 方案）
- **决策依据**：US-027 严格验证 W4 RV 唯一稳健，W3/W2 弱稳健

### 9.2 v9 集成深度
- **选项 A**：W4 RV 作为**信号增强**（不替换 v9 决策）
- **选项 B**：W4 RV 作为**独立触发器**（绕过 v9 决策）
- **决策依据**：A 更安全（不破坏现有 v9），B 更激进

### 9.3 监控告警阈值
- **当前**：IC < 0.02 持续 5 天
- **选项**：3 天 / 5 天 / 7 天
- **决策依据**：5 天 = 平衡灵敏度 + 误报率

---

## 十、相关文档

- [SOP-07 v9 mission 集成标准流程](./SOP_07_V9_MISSION_INTEGRATION.md)
- [US-026 因子配置（v1.0 旧方案）](../data/US-026_top3_volatility_factors.json)
- [US-027 严格验证报告](../data/US-027_strict_wf_validation.json)
- [US-027 W4 RV 部署报告](../data/US-027_W4_RV_deployment.md)
- [W4 RV 监控脚本](../../scripts/monitoring/monitor_top3_volatility.py)
- [W4 RV 监控 cron spec](../../scripts/cron_job_monitor_top3_volatility.json)

---

## 十一、版本历史

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| v1.0 | 2026-06-07 | 初版（US-027 后 1 周监控前）| 福猫管家 🐱 |
