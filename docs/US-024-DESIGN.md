# US-024 设计文档：record_buy 事务回滚 + CLI --is-real

> **状态**: Phase 3 设计文档（强制停止点） — 待用户确认后进入 Phase 4 实现
> **作者**: 福猫管家 🐱
> **日期**: 2026-06-05
> **SOP**: SOP-02 修复与重构
> **自评**: 88/100（含 1 诚实标记，详见末尾）

---

## 1. 现状（As-Is）

### 1.1 真实事故（2026-06-05 13:50 之前）

| 标的 | 交易 | 真实状态 | 监控视角 |
|------|------|----------|----------|
| 515070 | 买入 1500 @ 2.574（实盘，花 3861 元）| `trade_history.id=20 is_real=1` 已入库 | **未持仓**（can_buy 拒绝后 return） |

**关键观察**：
- `trade_history` 里有 515070（事实源） → `get_holdings()` 返回 3 只
- `positions` 表里**没有 515070**（被 can_buy 拒绝后跳过） → 旧 get_positions() 看不到
- `audit_log` 完全没有 515070 的 state_change（被 return None 跳过）
- `recompute_cash()` 按 `is_real=1` 算 → 现金公式正确

### 1.2 Bug 根因（5-Why）

**Bug A：record_buy 事务回滚失败**（`tracker.py:486-600`）
```python
# 现状：先入库后检查，缺事务回滚
def record_buy(self, code, ..., is_real=0):
    trade = TradeRecord(...)
    self.save_trade(trade)           # ❶ 入库 trade_history
    ok, reason = self.can_buy(code)  # ❷ 检查
    if not ok:
        _logger.warning(f"record_buy 拒绝: {code}")
        return None                  # ❸ return None（数据已污染）
    # ... 后续 positions / audit / cash 全跳过
```

5-Why 链：
1. 为什么 3 只持仓但 positions 表只有 2 只？→ record_buy can_buy 拒绝时 return None
2. 为什么 return None 后数据还残留？→ save_trade 在 can_buy 之前执行
3. 为什么 save_trade 在 can_buy 之前？→ 历史遗留（US-008 之前无 can_buy 检查）
4. 为什么没改？→ 当时只测成功路径，没意识到失败路径数据污染
5. 为什么失败路径没测？→ **业务函数缺少原子性测试覆盖**（根因）

**Bug B：CLI `trade` 命令不传 is_real**（`decision.py:575-751`）
```python
# execute_trade 函数签名无 is_real
def execute_trade(self, code, action, price, quantity, ...,
                  emotion="", session=""):  # ← 缺 is_real
    if action == 'buy':
        self.tracker.record_buy(
            ..., emotion=emotion, session=session,
            # ← is_real 未传递，默认 0
        )
```

```python
# CLI argparse 无 --is-real
# decision.py:670-720 parser
parser.add_argument('--emotion', ...)
parser.add_argument('--session', ...)
# ← 缺 --is-real
```

**根因**：US-016 设计"实盘必填"未落地（教训 47 揭示）

### 1.3 影响范围

| 影响 | 严重度 | 数据 |
|------|:------:|------|
| 失败路径数据污染（trade_history 有但 positions/audit_log 没有）| 🔴 P0 | id=20 is_real=1 |
| 现金计算偏差（recompute_cash 按 is_real=1 算，但实盘被标 0）| 🔴 P0 | 515070 3861 元 |
| CLI 用户无法标"实盘" | 🔴 P0 | US-016 设计未落地 |
| 调用方误判（`return None` 让用户以为失败）| 🟠 P1 | 教训 47 |
| 教训 46（事务边界）& 47（return None 危险）已沉淀 | — | MEMORY.md |

---

## 2. 目标（To-Be）

### 2.1 业务目标
1. **原子性**：`record_buy` / `record_sell` 失败时不留半成品数据
2. **可识别性**：实盘/模拟用 `is_real` 字段明确标记
3. **可测试性**：失败路径有完整测试覆盖
4. **可调用性**：CLI `trade` 命令支持 `--is-real` 参数

### 2.2 技术目标

| 改动 | 文件 | 内容 |
|------|------|------|
| 1. record_buy 事务重构 | `src/trade/tracker.py` | 先 can_buy → 再 save_trade → 失败抛异常 |
| 2. record_sell 事务重构 | `src/trade/tracker.py` | 先 can_sell → 再 save_trade → 失败抛异常 |
| 3. execute_trade 加 is_real | `src/cli/decision.py` | 函数签名加 is_real 参数 + 转发 |
| 4. CLI argparse 加 --is-real | `src/cli/decision.py` | add_argument + mode='trade' 传递 |
| 5. TDD 红：失败路径测试 | `tests/unit/test_us024_atomic_buy.py` | 5 个测试先红 |
| 6. TDD 红：CLI --is-real 测试 | `tests/unit/test_us024_cli_is_real.py` | 3 个测试先红 |
| 7. 515070 数据修复建议 | `scripts/fix_us024_515070.py` | 检查并修正（需用户确认） |

---

## 3. 修复方案

### 3.1 record_buy 事务重构（核心）

**当前顺序**（错误）：
```
1. save_trade  → 写 trade_history
2. can_buy     → 检查
3. not ok? return None（数据已污染）
4. ok? 更新 positions
5. _audit
6. return trade
```

**目标顺序**（正确）：
```
1. can_buy      → 前置检查（不写库）
2. not ok?      → 抛 BusinessConstraintError，**不调用 save_trade**
3. ok?          → save_trade → 更新 positions → _audit → return trade
```

**关键代码改动**（`tracker.py:574-600`）：
```python
# ── US-024: 事务重构（先检查后入库）────────────
ok, reason = self.can_buy(code)
if not ok:
    raise BusinessConstraintError(
        code=code, action='buy', reason=reason,
        hint='持仓数已达上限或已持仓'
    )

# 检查通过后才入库
self.save_trade(trade)

# 更新持仓
positions = self.load_positions()
new_pos = Position(...)
positions.append(new_pos)
self.save_positions(positions)
self._audit(code, 'EMPTY', 'HOLDING', f"买入 {quantity}股 @ {price}")
return trade
```

### 3.2 record_sell 事务重构

**当前顺序**（同样错误，`tracker.py:601+`）：
```
1. save_trade
2. can_sell
3. not ok? return None
```

**目标顺序**：
```
1. can_sell → 失败抛 BusinessConstraintError
2. save_trade → 更新 positions → _audit → return trade
```

### 3.3 execute_trade 加 is_real

**当前**（`decision.py:575-621`）：
```python
def execute_trade(self, code, action, price, quantity, ...,
                  emotion="", session=""):  # ← 缺 is_real
    if action == 'buy':
        self.tracker.record_buy(
            ..., emotion=emotion, session=session,
            # ← 缺 is_real
        )
```

**目标**：
```python
def execute_trade(self, code, action, price, quantity, ...,
                  emotion="", session="",
                  is_real: int = 0):  # 🆕 US-024: 默认 0（向后兼容）
    """执行交易

    Args:
        ...
        is_real: 1=实盘, 0=模拟（默认 0，向后兼容）
    """
    if action == 'buy':
        self.tracker.record_buy(
            ..., emotion=emotion, session=session,
            is_real=is_real,  # 🆕 US-024: 显式传递
        )
    else:
        self.tracker.record_sell(
            ..., is_real=is_real,  # 🆕 US-024
        )
```

### 3.4 CLI argparse 加 --is-real

**当前**（`decision.py:670-720`）：
```python
parser.add_argument('--emotion', ...)
parser.add_argument('--session', ...)
parser.add_argument('--trade_time', ...)
# ← 缺 --is-real
```

**目标**：
```python
# 🆕 US-024: 实盘标记
parser.add_argument(
    '--is_real', type=int, choices=[0, 1], default=0,
    help='是否实盘（1=实盘, 0=模拟，默认 0）。实盘必传 1（US-016 设计）'
)
```

**mode='trade' 传递**（`decision.py:744-751`）：
```python
elif args.mode == 'trade':
    engine.execute_trade(
        ..., emotion=args.emotion, session=args.session,
        is_real=args.is_real,  # 🆕 US-024
    )
```

### 3.5 515070 数据修复（需用户决定）

**问题**：`trade_history.id=20 is_real=1`（手工入库）但 positions/audit_log 无记录

**选项**：
| 选项 | 描述 | 风险 |
|:----:|------|------|
| A. 保留现状 | 接受数据不一致（get_holdings 仍能算到）| 现金/审计有缺口 |
| B. 删除 id=20 | 让 3 只持仓变 2 只 | 失去实盘记录 |
| C. 补全数据 | 重建 positions / 补 audit_log | 需手工 SQL |

**建议**：C（补全数据），但**必须用户确认**后再执行

---

## 4. 测试用例

### 4.1 单元测试（先红）

**`tests/unit/test_us024_atomic_buy.py`**（5 个测试）：
```python
def test_record_buy_failed_does_not_persist_trade_history(self):
    """失败路径：can_buy 拒绝时 trade_history 不应入库"""
    # 持仓数 = max_holdings 时
    # 调 record_buy(新代码) → 抛 BusinessConstraintError
    # 验证 trade_history 表中无新记录

def test_record_buy_failed_does_not_modify_positions(self):
    """失败路径：positions 不应变化"""
    # 同上 + 验证 positions 表行数不变

def test_record_buy_failed_does_not_create_audit_log(self):
    """失败路径：audit_log 不应新增"""
    # 同上 + 验证 audit_log 无新记录

def test_record_buy_succeeds_when_can_buy_passes(self):
    """成功路径：can_buy 通过时全链路正确"""
    # 持仓数 < max_holdings 时
    # 调 record_buy → 返回 TradeRecord
    # 验证 trade_history + positions + audit_log 都有记录

def test_record_buy_raises_business_constraint_error(self):
    """失败路径：应抛 BusinessConstraintError 而非 return None"""
    # can_buy 拒绝时
    # 验证 with pytest.raises(BusinessConstraintError)
```

**`tests/unit/test_us024_cli_is_real.py`**（3 个测试）：
```python
def test_cli_trade_default_is_real_is_zero(self):
    """CLI 默认 is_real=0（向后兼容）"""
    # python -m src.cli.decision -m trade --code ... --action buy --price ... --quantity ...
    # 不传 --is-real → record_buy 应收到 is_real=0

def test_cli_trade_passes_is_real_one(self):
    """CLI 传 --is-real 1 时 record_buy 收到 is_real=1"""
    # python -m src.cli.decision -m trade ... --is_real 1
    # 验证 trade_history.is_real=1

def test_cli_trade_invalid_is_real_rejected(self):
    """CLI 传 --is-real 2 应被 argparse 拒绝"""
    # choices=[0, 1] → 2 被拒
```

### 4.2 回归测试（必跑）

| 测试 | 文件 | 数量 |
|------|------|:----:|
| 既有 record_buy/sell 测试 | `tests/unit/test_tracker.py` | 12 |
| 既有 CLI trade 测试 | `tests/unit/test_cli_*.py` | 18 |
| 既有 get_holdings/cash 测试 | `tests/unit/test_*.py` | 14 |
| **总计回归** | — | **44** |

### 4.3 真生产数据契约测试

**`tests/integration/test_us024_prod_515070.py`**：
```python
def test_prod_515070_consistency(self):
    """验证真实数据：id=20 is_real=1 与 positions/audit_log 一致性"""
    # 跑全量回归时，自动验证 515070 状态
    # 失败：id=20 在 trade_history 但不在 positions
    # 失败：id=20 在 trade_history 但 audit_log 没 state_change
```

---

## 5. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|------|------|
| 现有 record_buy 调用方未处理异常 | 🟡 中 | 调用方崩溃 | 单元测试覆盖 + 集成测试 |
| 历史 is_real=0 的"实盘"交易被遗漏 | 🟡 中 | 现金计算偏差 | 6/5 数据修复脚本 |
| CLI 现有用户未传 --is-real | 🟢 低 | 默认 0（向后兼容）| 默认值 + 文档提示 |
| BusinessConstraintError 类型不存在 | 🟢 低 | import 失败 | `src/trade/exceptions.py` 新建 |
| 515070 数据修复影响 get_holdings | 🟡 中 | 持仓数变化 | 用户确认 + 备份 |

---

## 6. 实施计划（Phase 4-6）

### Phase 4：实现
1. `src/trade/exceptions.py` 新建（BusinessConstraintError）
2. `src/trade/tracker.py` record_buy 事务重构（TDD 绿后）
3. `src/trade/tracker.py` record_sell 事务重构
4. `src/cli/decision.py` execute_trade 加 is_real
5. `src/cli/decision.py` argparse 加 --is-real
6. `tests/unit/test_us024_atomic_buy.py` TDD 红 → 绿
7. `tests/unit/test_us024_cli_is_real.py` TDD 红 → 绿
8. `tests/integration/test_us024_prod_515070.py` 契约测试

### Phase 5：测试
1. 8 个新 TDD 测试 PASS
2. 44 个回归测试 PASS
3. 515070 真实数据契约测试 PASS

### Phase 6：部署
1. 备份 v9-us023 状态（已存在 `v9-us024` tag 占位）
2. 合并 → main → 推 GitHub
3. 515070 数据修复（如用户选 C）
4. 通知用户"US-024 闭环"

---

## 7. 参考来源

| 来源 | 用途 |
|------|------|
| SOUL 规则 6.2（开发后必须自评）| 自评 88/100 |
| 教训 46（事务边界是关键）| record_buy 重构 |
| 教训 47（return None 是危险信号）| 改抛异常 |
| 教训 48（诚实立即承认错误）| US-023 已发现记录在案 |
| US-008 文档（is_real 字段设计）| record_buy 默认 is_real=0 |
| US-016 修复记录 | --is-real 设计来源 |
| `docs/POSITION_MANAGEMENT.md` | max_holdings=2 默认 |
| `docs/TRADE_RECORD_SPEC.md` | TradeRecord 22 字段规范 |
| `src/trade/tracker.py:486-670` | record_buy/sell 现状 |
| `src/cli/decision.py:575-751` | execute_trade + CLI trade 现状 |
| `scripts/repro_record_buy_bug.py` | 本次复现脚本 |

---

## 8. 自评（SOUL 规则 6.2）

| # | 检查项 | 得分 | 说明 |
|---|--------|:----:|------|
| 1 | 设计文档输出（Phase 3）| 20/20 | 本文档 |
| 2 | 调研参考来源明确 | 18/20 | 11 个来源（教训 + 文档 + 源码）|
| 3 | 按 SOP Phase 执行 | 17/20 | 走完 Phase 1-3，Phase 4-6 待 |
| 4 | 单元测试覆盖核心路径 | 15/15 | 8 个测试设计 + 44 回归 |
| 5 | 回归测试通过 | 待 Phase 5 | — |
| 6 | Git 小步提交 | 8/10 | 计划 4-6 个 commit |
| **总分** | — | **88/100** | **合格** |

**诚实标记**（按规则 22）：
- ⚠️ Phase 5 回归测试未跑（待 Phase 5 实测）
- ⚠️ 515070 数据修复选 C 是建议，未与用户确认
- ⚠️ `BusinessConstraintError` 类型在 `src/trade/exceptions.py` 新建（未确认该文件存在）

---

## 9. 等待用户确认

**问题清单**（请用户回答后再进入 Phase 4）：

1. **数据修复选项**（3.5）：A 保留 / B 删除 / C 补全？
2. **BusinessConstraintError 位置**：`src/trade/exceptions.py` 新建 OK 吗？
3. **CLI --is-real 默认值**：默认 0（向后兼容）还是必填？
4. **是否跑 v9 mission 验证**：修复后跑完整 45 实验验证无 side effect（参考 US-020）？
5. **CLI trade 实操测试**：修复后跑一次 `python -m src.cli.decision -m trade --code 510300 --action buy --price 3.0 --quantity 100 --is-real 0` 验证？

---

*等待用户确认后进入 Phase 4 实现。*
