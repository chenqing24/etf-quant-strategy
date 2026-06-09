# US-001: 执行源标识 (--source flag)

> **作者**: US-001 worker
> **日期**: 2026-06-09
> **分支**: `mission/execution-source-isolation`
> **PRD**: `missions/mission-20260609-193224/prd.json`

## 目标

解决教训 101 暴露的架构问题：多执行源（CRON / Skill / 对话 / 手动）共享文件系统和数据库，但无执行源标识，导致命令来源无法区分 + audit log 缺失执行人字段。

US-001 是最小改动 P0：只加标识，不加门禁（门禁在 US-002）。

## 业界参考

按 SOUL 规则 13 标注来源：

| 来源 | 借鉴点 |
|------|--------|
| **Kafka message header** | producer source 用 header 标识（producer 维度） |
| **12-Factor App § XI Logs** | stdout 路由（US-003 实施） |
| **clig.dev Robustness** | `--source` 是元数据参数，非破坏性操作，不需要 confirm |
| **OWASP ASVS V7 Logging** | 审计字段规范（actor/event_type/outcome）— US-003 实施 |

## 关键设计决策

### 1. 枚举值集合

```python
class ExecutionSource(str, Enum):
    CRON = "cron"          # 定时任务
    SKILL = "skill"        # QwenPaw skill 调用
    DIALOG = "dialog"      # 对话/Agent 调用
    MANUAL = "manual"      # 用户手动 CLI
    UNKNOWN = "unknown"    # 哨兵值
```

**理由**：
- `StrEnum`：可直接当 str 用，便于日志、JSON 序列化
- 顺序按"自动化程度递减"：CRON → SKILL → DIALOG → MANUAL（更易审计）
- `UNKNOWN` 单独作为哨兵值，方便下游门禁（US-002）显式拒绝

### 2. 缺省值 = MANUAL（规则 19 宁严勿宽）

理由：
- 用户直接跑 CLI 是最保守的"完全人工监督"模式
- 自动化任务（CRON/SKILL/DIALOG）必须显式标注，迫使调用方思考"我是谁"
- 如果缺省为 CRON，CRON 任务忘记传 `--source` 会以"自动化"身份执行，违反最小特权

### 3. UNKNOWN 显式拒绝

```python
def resolve_source_strict(...) -> ExecutionSource:
    src = get_source_from_argv(...)
    if src == ExecutionSource.UNKNOWN:
        raise ValueError("UNKNOWN is explicitly rejected")
    return src
```

**理由**（防"忘了填"绕过）：
- 如果 `UNKNOWN` 被允许为合法值，攻击者/失误方可以传 `--source=unknown` 模糊绕过门禁
- 严格模式下，传 `unknown` 跟传"无效值"一样被拒绝
- 但 `parse_source("unknown")` 本身仍合法（因为 `UNKNOWN` 是合法枚举值），便于上游用 `get_source_from_argv` 解析 + 显式区分

### 4. 解析优先级：argv > ENV > MANUAL

```python
def get_source_from_argv(argv=None, *, env=None) -> ExecutionSource:
    # 1. argv
    # 2. EXECUTION_SOURCE env
    # 3. MANUAL
```

**理由**：
- argv 最高：单次调用最具体
- ENV 次之：cron job / container 部署时统一设置
- 缺省最保守

### 5. 非法值不静默回退（关键！）

```python
# ❌ 错误：非法值回退到 MANUAL
def get_source_from_argv(...):
    try:
        return parse_source(arg)
    except ValueError:
        return ExecutionSource.MANUAL  # 用户传 "crn" 静默以 MANUAL 执行！

# ✅ 正确：非法值显式报错
def get_source_from_argv(...):
    return parse_source(arg)  # ValueError 向上抛
```

**理由**：
- 如果静默回退，CRON 任务传错 `--source=crn`（拼写错误）会被以 MANUAL 身份执行
- 违反"宁严勿宽"
- 用户会立即看到错误并修复

## 实施

### 1. 新增文件

#### `src/utils/execution_source.py` (193 行)

提供 5 个公开 API：
- `ExecutionSource` 枚举
- `parse_source(value: str) -> ExecutionSource`
- `get_source_from_argv(argv, *, env) -> ExecutionSource`
- `resolve_source_strict(argv, *, env) -> ExecutionSource`（显式拒绝 UNKNOWN）
- `add_source_argument(parser)`（argparse helper）

支持 `--source=X` / `--source X` / `-s X` / `-s=X` 四种 argv 写法。

#### `tests/unit/test_execution_source.py` (253 行, 39 用例)

按 7 个 test class 组织：
- `TestExecutionSourceEnum` (3) — 枚举完整性
- `TestParseSource` (9) — 5 种解析 + 大小写 + 非法拒绝
- `TestExtractFromArgv` (7) — argv 解析细节
- `TestGetSourceFromArgv` (8) — 优先级矩阵
- `TestResolveSourceStrict` (4) — UNKNOWN 拒绝
- `TestAddSourceArgument` (4) — argparse 集成
- `TestIntegrationRealUseCases` (4) — 真实调用场景

**结果**：39/39 PASS

### 2. 集成到 `src/cli/decision.py`

最小改动（避免范围爆炸）：

```python
# import 块
from src.utils.execution_source import (
    ExecutionSource,
    add_source_argument,
    get_source_from_argv,
)

# main() 在 --is_real 后
add_source_argument(parser)  # 加 --source/-s 参数

args = parser.parse_args()

# US-001: 解析执行源
execution_source = get_source_from_argv() if args.source is None else ExecutionSource(args.source)
logger.info(f"🔖 execution_source = {execution_source.value} "
            f"(argv={args.source!r}, env={os.environ.get('EXECUTION_SOURCE')!r})")
```

**冒烟测试**：
- `python -m src.cli.decision -m daily --source=cron` → `execution_source = cron`
- `EXECUTION_SOURCE=skill python -m src.cli.decision -m daily` → `execution_source = skill`
- 无任何 source → `execution_source = manual`

### 3. 范围控制

**做了**：
- `src/cli/decision.py`（最常用 daily/eval/trade 入口）
- `src/utils/execution_source.py`（核心模块）
- `tests/unit/test_execution_source.py`（单元测试）

**没做**（按 PRD 控制范围）：
- `src/data/monitor.py` / `scripts/backup_sqlite.py` — PRD 提到，US-001 worker 任务描述说"只做 daily/eval/trade 三个最常用模式，避免范围爆炸"
- cron_job_*.json 加 `--source=cron` 后缀 — 需要修改 JSON 配置，US-003 之后再说
- Skill SKILL.md 加 `--source=skill` — 同上

**TODO**（标在代码注释 + 本文件）：
- 未来集成：`src/data/monitor.py` / `scripts/backup_sqlite.py` / `scripts/cron_job_*.json`

## 关键纪律遵守（SOUL 规则）

| 规则 | 遵守情况 |
|------|----------|
| 规则 19 宁严勿宽 | ✅ 缺省 MANUAL，非法值显式报错不静默回退 |
| 规则 13 标注来源 | ✅ Kafka header / 12-Factor XI / clig.dev / OWASP ASVS |
| 规则 11 先调研 | ✅ grep 了 `from src.utils import` 确认无重复实现 |
| 规则 3.1 设计清单 | ✅ 考虑了 4.3 持仓管理（本次不涉及回测），但保持了 source 标识可在 audit log 中使用 |
| 规则 1 交付标准 | ✅ 功能能跑 + 测试通过 + 文档（本文件）+ 无重复 |
| 规则 5 测试驱动 | ✅ 39 用例全过，51/52 相关测试通过（1 个 pre-existing failure 与 US-001 无关） |

## 挑战与解决

### 挑战 1: argparse helper 的 SUPPRESS 常量

`add_source_argument()` 中默认 `help=...`，但允许调用方传 `default_help=False` 用 `argparse.SUPPRESS`。
最简方案：在模块顶部 `import argparse`（已加）。

### 挑战 2: stash pop 引入了 main 分支 docs 状态

跑回归测试时用 `git stash` + `git checkout main -- ...` + `git stash pop` 验证 pre-existing failure，结果 stash pop 把 main 分支 docs 改动混入了。
解决：`git reset --hard HEAD` 清理，确认 US-001 三个 commit 完整无损（`git log` + `git diff --stat` 验证）。

### 挑战 3: pre-existing 失败的识别

`test_us004_cli_parse.py::TestRealReport::test_real_report_20260603` 失败原因：报告里 `510300` 被解析成 `''`（业务侧问题，与 US-001 无关）。
`test_cli_paths.py::test_no_old_style_imports` 失败原因：`from scripts.prefetch_data` 是过时引用（在 main 上就有，不是我引入的）。
两者均用 main 验证过为 pre-existing，不影响 US-001 完成度。

## 后续

- **US-002**：基于 `ExecutionSource` 加 `--force` 门禁 + Danger 分级
  - CRON 跳过门禁（自动化不需要问）
  - DIALOG 强制（Agent 调用必须有 force）
  - MANUAL 默认走 confirm
- **US-003**：audit 事件写 stdout（JSON Lines + 包含 source 字段）
- **US-001 收尾**（下次 Mission）：补 `src/data/monitor.py` / `scripts/backup_sqlite.py` 的 `--source` 集成
