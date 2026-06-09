# US-002: 破坏性写操作加 --force 强制门禁

> **作者**: US-002 worker（福猫管家）
> **日期**: 2026-06-10
> **分支**: `mission/us-002-safety-gate`（基于 `mission/execution-source-isolation`）
> **PRD**: `missions/mission-20260609-193224/prd.json` → US-002

## 目标

解决教训 101（多执行源共享文件系统 + 数据库，无破坏性门禁）的第 2 步：
所有破坏性写操作（覆盖文件 / 写入交易 / 钉钉推送 / 删库）必须显式 `--force` 才执行。
防止误触 + 强制人工二次确认。

US-002 依赖 US-001（必须有 ExecutionSource 才能判断 source）。

## 业界参考（按 SOUL 规则 13 标注来源）

| 来源 | 借鉴点 |
|------|--------|
| **clig.dev Robustness** (https://clig.dev/#robustness) | 破坏性操作 confirm；惯例 `-f` / `--force` |
| **clig.dev Danger 分级** | Mild（可选） / Moderate（必填） / Severe（必填 + 对象名） |
| **Git / rsync / rm -f** | `--force` 是业界惯例，不是 `--confirm` |
| **US-001 ExecutionSource** | source 联动：CRON/SKILL 跳过；DIALOG/MANUAL 强制 |
| **12-Factor App § XII Admin Processes** | 一次性任务与常驻进程同环境 → cron 自身有审计 |

## 关键设计决策

### 1. 用 `--force`，不用 `--confirm`

按 clig.dev 业界惯例（git / rsync / rm 都用 `--force`），
不是 PRD 最初写的 `--confirm`。

### 2. Danger 分级（按 clig.dev 三级）

| 级别 | 含义 | --force 要求 | 例子 |
|------|------|--------------|------|
| **MILD** | 本地小改动 | 可选 | `backup_daily`, `migrate_dry_run` |
| **MODERATE** | 远程副作用或重要改动 | 必填 | `dingtalk_send`, `report_overwrite`, `trade_record` |
| **SEVERE** | 删库级 | 必填 + 对象名精确匹配 | `clear_positions`（`--force=positions`）, `reset_db`（`--force=db`） |

### 3. `--force` 的两种形式（argparse nargs="?"）

```bash
--force              # bool True（Mild/Moderate 够用）
--force=positions    # str（Severe 必须精确匹配对象名）
-f                   # 短选项同 --force
```

### 4. 与 ExecutionSource 联动规则

```
CRON  / SKILL → 跳过（自动化任务自身有审计）
DIALOG / MANUAL + MILD → --force 可选（dry-run 仍打印）
DIALOG / MANUAL + MODERATE → --force 必填，否则 SafetyGateError
DIALOG / MANUAL + SEVERE → --force 必须是 target 字符串精确匹配
dry-run=True → 永远不抛错，仅打印将执行清单
```

为什么 MANUAL 也强制？防止"脚本冒充用户"绕过门禁（SOUL 规则 19：宁严勿宽）。

### 5. 装饰器 + 显式调用两种 API

```python
# 方式 1：装饰器（最常用）
@apply_to_destructive("dingtalk_send")
def send_alert(*, source, force=False, dry_run=False, **kwargs):
    ...

# 方式 2：显式调用（CLI 入口处用）
require_force("trade_record", source=execution_source,
              force=args.force, dry_run=args.dry_run)
```

装饰器用 `functools.wraps` 保留元信息，支持多层嵌套（如 `@timing @apply_to_destructive`）。

### 6. 集成范围：3 个最常用 CLI（避免爆炸）

| CLI | 集成点 | Op 名 | Severity |
|-----|--------|-------|----------|
| `src/cli/decision.py` | `--mode trade` | `trade_record` | Moderate |
| `src/cli/decision.py` | `--mode eval` | `dingtalk_send` | Moderate |
| `src/data/monitor.py` | `--dingtalk` | `dingtalk_send` | Moderate |
| `scripts/backup_sqlite.py` | `--type=reset` | `reset_db` | Severe (`--force=db`) |
| `scripts/backup_sqlite.py` | `--type=daily/weekly/manual` | `backup_*` | Mild |

**未集成**（按"先做 3 个最常用，避免爆炸"）：
- `scripts/migrate_data.py`、`scripts/analyze_*.py` 等次常用脚本
- 后续可按需扩展（DESTRUCTIVE_OPS 注册表已支持）

## 改动文件清单（4 个 commit）

```
src/utils/safety_gate.py        | 349 +++++++   (新增)
src/cli/decision.py             |  48 +++       (加 --force-target/--dry-run + 门禁)
src/data/monitor.py             |  27 +++       (加 --force/--dry-run + 钉钉门禁)
scripts/backup_sqlite.py        |  34 +++       (加 --force/--dry-run + reset门禁)
tests/unit/test_safety_gate.py  | 416 +++++     (新增)
notes/us002-safety-gate.md      | (本文档)
```

## 测试覆盖（33 用例全通过）

| 场景 | 用例数 | 说明 |
|------|--------|------|
| 枚举完整性 | 2 | 3 个 DangerLevel 值 |
| 注册表 | 3 | 10 个 op + severity 分配 + 未注册拒绝 |
| 场景1: CRON/SKILL pass | 3 | Moderate/Severe 都自动放行 |
| 场景2: DIALOG Mild pass | 1 | 无 force 也放行 |
| 场景3: DIALOG Moderate 拒绝 | 2 | DIALOG + MANUAL 双源 |
| 场景4: DIALOG Moderate pass | 2 | bool + str 都行 |
| 场景5: DIALOG Severe target | 5 | 4 种拒绝 + 1 种 pass |
| 场景6: 装饰器嵌套 | 5 | wraps + 多层装饰 + 未注册拒绝 |
| 场景7: dry-run | 3 | 不抛错 + 日志输出 |
| argparse helper | 5 | `--force`/`-f`/`--force=value`/`--dry-run` |
| Error 信息 | 1 | 含 op_name/source/建议 |

## 遇到的挑战

### 1. decision.py 已有 `--force`（bool 覆盖报告用）

冲突：US-002 也需要 `--force`（bool 或 str）作为门禁。
但 decision.py 原本的 `--force` 是覆盖今日报告（已有 trade 模式不传 force 的能力）。

**解决**：保留原 `--force`（bool，覆盖报告用），新增 `--force-target`（str，Severe 用）。
`--force` 同时承担"覆盖报告"和"门禁"两职（语义统一：都表示"强制"）。
副作用：用户传 `--force` 跑 `--mode trade` 也会同时覆盖今日报告——这是预期行为。

### 2. dry-run 后仍执行了 trade（业务约束报错才暴露）

第一版集成时，require_force 通过后**未阻断**实际执行，导致 dry-run 模式下也调用了 trade。
**修复**：在 require_force 通过后，立即 `if args.dry_run: sys.exit(0)` 阻断。
教训：dry-run 必须**显式阻断**实际执行，不能依赖业务逻辑的副作用检查。

## 业界参考完整列表

- **clig.dev Robustness** https://clig.dev/#robustness — Danger 分级 + --force 惯例
- **git --force, rsync --force, rm -f** — `-f/--force` 业界惯例
- **US-001 ExecutionSource** — source 联动
- **12-Factor § XII Admin Processes** — cron 自身有审计

## 后续工作（不在 US-002 范围）

- US-003: audit 写 stdout（12-Factor XI）
- 集成到次常用 CLI（migrate_data.py 等）
- 添加 `--force-target=positions` 到 decision.py trade mode（目前只在 backup_sqlite 演示 Severe）
- 给 cron 配置加 `--force`（cron 自动放行，但若想保留 audit 痕迹可加）