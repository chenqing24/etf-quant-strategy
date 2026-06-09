#!/usr/bin/env python3
"""
Safety Gate — 破坏性写操作强制门禁 (US-002)

设计目标：
    1. 防止误触（误传 --dingtalk、--reset 等破坏性参数）
    2. 强制人工二次确认（DIALOG/MANUAL 触发破坏性操作必须 --force）
    3. CRON 自动化任务不受阻（cron 自身有审计，US-001 已加 --source）

业界参考（按 SOUL 规则 13 标注来源）：
    - Command Line Interface Guidelines § Robustness (https://clig.dev/#robustness)
        * 破坏性操作必须 confirm
        * 业界惯例：-f / --force（git/rsync/rm 都用）
        * Danger 分级：Mild / Moderate / Severe
        * Severe 级别需要 --force=对象名（如 --force=positions）防止误敲
    - US-001 ExecutionSource（同一个 mission，source 联动）

安全规则：
    - CRON / SKILL 源：跳过 --force 检查（自动化任务自身有审计）
    - DIALOG 源：Moderate 必须 --force；Severe 必须 --force=对象名
    - MANUAL 源：同 DIALOG（防止脚本冒充用户身份）
    - dry-run=True：永远不抛错，只打印"将执行"清单
    - Mild 级别：--force 可选（但 dry-run 仍打印提示）

错误信息友好：
    - 提示具体缺什么 + 建议先 --dry-run
    - 不暴露实现细节
"""
from __future__ import annotations

import functools
import logging
from enum import Enum
from typing import Any, Callable, Optional

from src.utils.execution_source import ExecutionSource

logger = logging.getLogger(__name__)


# ────────────────────────────── Danger 分级 ──────────────────────────────


class DangerLevel(Enum):
    """破坏性操作的危险级别（按 clig.dev 业界惯例）

    MILD：
        本地小改动，无数据丢失风险。
        --force 可选；但 dry-run 仍打印提示。

    MODERATE：
        远程副作用或重要改动（如钉钉推送、报告覆盖）。
        --force 必填。

    SEVERE：
        删库级操作（清持仓、重置数据库、删表）。
        --force=对象名 必填（要求用户敲不容易敲错的精确字符串）。
    """
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


# ────────────────────────────── 破坏性操作注册表 ──────────────────────────────


# 集中管理所有破坏性操作（op_name → DangerLevel）
# 加新操作时只需改这一处 + 在 CLI 中加对应分支
DESTRUCTIVE_OPS: dict[str, DangerLevel] = {
    # ── Mild（本地小改动，可选 --force） ──
    "backup_daily": DangerLevel.MILD,
    "backup_weekly": DangerLevel.MILD,
    "migrate_dry_run": DangerLevel.MILD,

    # ── Moderate（远程副作用或重要改动，必填 --force） ──
    "dingtalk_send": DangerLevel.MODERATE,       # 钉钉推送（不可撤回）
    "report_overwrite": DangerLevel.MODERATE,    # 覆盖现有报告
    "snapshot_save": DangerLevel.MODERATE,       # 保存决策快照（覆盖上一份）
    "trade_record": DangerLevel.MODERATE,        # 写入交易记录

    # ── Severe（删库级，必填 --force=对象名） ──
    "clear_positions": DangerLevel.SEVERE,       # 清空持仓
    "reset_db": DangerLevel.SEVERE,              # 重置数据库
    "drop_table": DangerLevel.SEVERE,            # 删表
}


# ────────────────────────────── 异常类 ──────────────────────────────


class SafetyGateError(Exception):
    """Safety Gate 拒绝执行的异常

    抛出场景：
        - DIALOG/MANUAL 触发 Moderate 操作但未传 --force
        - DIALOG/MANUAL 触发 Severe 操作但 --force 不是对象名
        - 调用的 op_name 不在 DESTRUCTIVE_OPS 注册表里

    抛出信息必须包含：
        1. 触发的 op_name 和 danger level
        2. 当前 source（方便定位问题）
        3. 修复建议（加 --force / --force=对象名 / --dry-run 先看）
    """

    def __init__(
        self,
        op_name: str,
        danger: DangerLevel,
        source: ExecutionSource,
        hint: str,
    ):
        self.op_name = op_name
        self.danger = danger
        self.source = source
        self.hint = hint
        super().__init__(self._format())

    def _format(self) -> str:
        return (
            f"[SafetyGate] 拒绝执行 {self.danger.value} 级操作 "
            f"op={self.op_name!r} source={self.source.value!r}\n"
            f"  原因：{self.hint}\n"
            f"  建议：加 --force 显式确认；或先 --dry-run 查看将执行内容"
        )


# ────────────────────────────── 核心函数 ──────────────────────────────


def get_danger(op_name: str) -> DangerLevel:
    """查 op_name 的危险级别；未注册时抛 SafetyGateError（防止漏写）"""
    if op_name not in DESTRUCTIVE_OPS:
        raise SafetyGateError(
            op_name=op_name,
            danger=DangerLevel.MODERATE,  # 失败用保守值
            source=ExecutionSource.UNKNOWN,
            hint=f"op {op_name!r} 未在 DESTRUCTIVE_OPS 注册表中注册",
        )
    return DESTRUCTIVE_OPS[op_name]


def require_force(
    op_name: str,
    *,
    source: ExecutionSource,
    force: Any,            # bool 或 str（Severe 时要求 str）
    dry_run: bool = False,
    target: Optional[str] = None,  # Severe 级别要求 --force==target
) -> None:
    """破坏性操作的 --force 门禁

    Args:
        op_name: 操作名（必须在 DESTRUCTIVE_OPS 中）
        source: 执行源（来自 US-001 ExecutionSource）
        force: --force 参数值
                - bool True：普通确认（Mild/Moderate 用）
                - str：精确对象名（Severe 用）
        dry_run: True 则永远不抛错，仅打印
        target: 被操作对象名（Severe 时与 force 字符串匹配）

    规则：
        CRON / SKILL → 跳过（自动化任务自身有审计）
        MILD         → --force 可选；dry-run 打印
        MODERATE     → DIALOG/MANUAL 需 force=True
        SEVERE       → DIALOG/MANUAL 需 force==target 字符串精确匹配

    Raises:
        SafetyGateError: 规则不满足时
    """
    danger = get_danger(op_name)

    # ── CRON / SKILL：跳过检查 ──
    if source in (ExecutionSource.CRON, ExecutionSource.SKILL):
        if dry_run:
            logger.info(
                f"[dry-run] {source.value} 触发的 {danger.value} 操作 "
                f"op={op_name!r} 已自动放行（无需 --force）"
            )
        else:
            logger.info(
                f"[SafetyGate] {source.value} 自动放行 {danger.value} "
                f"op={op_name!r}（cron/skill 自身有审计）"
            )
        return

    # ── dry-run：永远不抛错，只打印 ──
    if dry_run:
        logger.info(
            f"[dry-run] 将执行 {danger.value} 级操作 "
            f"op={op_name!r} source={source.value!r} "
            f"force={force!r} target={target!r}"
        )
        return

    # ── Mild：可选 --force ──
    if danger == DangerLevel.MILD:
        if not force:
            logger.info(
                f"[SafetyGate] MILD 操作 op={op_name!r} 放行 "
                f"（--force 可选，建议加 --dry-run 预览）"
            )
        return

    # ── Moderate：DIALOG/MANUAL 需 force=True ──
    if danger == DangerLevel.MODERATE:
        if not force:
            raise SafetyGateError(
                op_name=op_name,
                danger=danger,
                source=source,
                hint=f"DIALOG/MANUAL 触发 {op_name!r} 需要显式 --force 确认",
            )
        return

    # ── Severe：DIALOG/MANUAL 需 force==target 精确字符串 ──
    if danger == DangerLevel.SEVERE:
        # force 必须是字符串（bool 是 int 的子类，先排除 bool）
        if isinstance(force, bool) or not isinstance(force, str):
            raise SafetyGateError(
                op_name=op_name,
                danger=danger,
                source=source,
                hint=(
                    f"SEVERE 操作 {op_name!r} 需要 --force=<对象名> "
                    f"（如 --force={target or '对象名'}）防止误敲"
                ),
            )
        if target is None:
            raise SafetyGateError(
                op_name=op_name,
                danger=danger,
                source=source,
                hint=f"SEVERE 操作 {op_name!r} 调用方必须传 target 参数",
            )
        if force != target:
            raise SafetyGateError(
                op_name=op_name,
                danger=danger,
                source=source,
                hint=(
                    f"SEVERE 操作 {op_name!r} 要求 --force={target!r} "
                    f"精确匹配（实际收到 --force={force!r}）"
                ),
            )
        return

    # 防御性：未知 DangerLevel
    raise SafetyGateError(
        op_name=op_name,
        danger=danger,
        source=source,
        hint=f"未知的 DangerLevel: {danger!r}",
    )


# ────────────────────────────── 装饰器 ──────────────────────────────


def apply_to_destructive(op_name: str) -> Callable:
    """装饰器：把函数标记为破坏性，自动套用 require_force 门禁

    用法：
        @apply_to_destructive("dingtalk_send")
        def send_dingtalk(*, force=False, dry_run=False, source, **kwargs):
            ...

    函数必须接受以下 kwargs：
        source: ExecutionSource
        force: bool | str
        dry_run: bool（可选，缺省 False）
        target: str（Severe 时必填）

    支持多层嵌套：装饰器用 functools.wraps 保留原函数元信息。
    """
    if op_name not in DESTRUCTIVE_OPS:
        raise ValueError(
            f"op {op_name!r} 未在 DESTRUCTIVE_OPS 中注册；"
            f"请先在 safety_gate.py 注册后再用装饰器"
        )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            require_force(
                op_name,
                source=kwargs["source"],
                force=kwargs.get("force", False),
                dry_run=kwargs.get("dry_run", False),
                target=kwargs.get("target"),
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ────────────────────────────── argparse helper ──────────────────────────────


def add_force_argument(
    parser,
    *,
    severe_target: Optional[str] = None,
) -> None:
    """给 argparse.ArgumentParser 加 --force / -f 参数

    Args:
        parser: argparse parser
        severe_target: 如果操作是 Severe 级别，传入 target 名（如 "positions"）
                       此时 --force 接受字符串值（nargs="?"）

    用法：
        # Moderate
        add_force_argument(parser)

        # Severe
        add_force_argument(parser, severe_target="positions")

    设计：
        - 短选项 -f（业界惯例）
        - nargs="?"：允许 --force（bool True）和 --force=positions（str）
        - const=True：--force 无值时为 True
        - default=False
    """
    if severe_target:
        help_text = (
            f"强制确认（Severe 操作：必填 --force={severe_target} 精确对象名）；"
            f"短选项 -f"
        )
    else:
        help_text = (
            "强制确认（Moderate 操作：必填 --force 才执行）；短选项 -f"
        )
    parser.add_argument(
        "--force", "-f",
        nargs="?",
        const=True,
        default=False,
        help=help_text,
    )


def add_dry_run_argument(parser) -> None:
    """给 argparse.ArgumentParser 加 --dry-run 参数（clig.dev 强推）"""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="仅显示将执行的内容，不实际执行（clig.dev 推荐）",
    )