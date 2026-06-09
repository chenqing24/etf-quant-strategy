#!/usr/bin/env python3
"""
执行源标识 (Execution Source) — US-001

设计目标：
    1. 区分命令来源（CRON / SKILL / DIALOG / MANUAL / UNKNOWN）
    2. audit log 能记录执行人/执行源
    3. 未来写操作门禁可基于 source 强制规则（US-002）

业界参考：
    - Kafka message header 标识 producer source
    - 12-Factor App § XI Logs
    - clig.dev Robustness (--source 是元数据参数，不算破坏性)

安全规则（按 SOUL 规则 19 宁严勿宽）：
    - 缺省值 = MANUAL（最保守）
    - UNKNOWN 显式拒绝（必须是有效枚举值，防止"忘了填"绕过）
    - 解析优先级：argparse > 环境变量 EXECUTION_SOURCE > 缺省 MANUAL
"""
from __future__ import annotations

import argparse
import os
import sys
from enum import Enum
from typing import Optional, Sequence


class ExecutionSource(str, Enum):
    """命令执行源枚举

    字符串值用小写，便于命令行和日志统一。
    顺序固定，便于在文档/日志里按"自动化程度递减"排序展示。
    """
    CRON = "cron"          # 定时任务
    SKILL = "skill"        # QwenPaw skill 调用
    DIALOG = "dialog"      # 对话/Agent 调用
    MANUAL = "manual"      # 用户手动 CLI
    UNKNOWN = "unknown"    # 哨兵值：显式表示未识别（不应当出现）


# 环境变量名（统一在模块内定义，避免散落）
ENV_VAR_NAME = "EXECUTION_SOURCE"


def _normalize(value: str) -> str:
    """归一化：去空白 + 转小写"""
    if value is None:
        return ""
    return str(value).strip().lower()


def parse_source(value: str) -> ExecutionSource:
    """把字符串解析为 ExecutionSource

    规则：
        - 大小写不敏感
        - "unknown" 视为合法（哨兵值）但下游应当拒绝
        - 非法值抛 ValueError（不静默回退到 MANUAL，
          否则用户误传 "crn" 会静默以 MANUAL 执行，违反规则 19）

    抛出：
        ValueError：value 为 None / 空 / 非法枚举值
    """
    if value is None:
        raise ValueError("source value is None")
    norm = _normalize(value)
    if not norm:
        raise ValueError("source value is empty")
    for src in ExecutionSource:
        if src.value == norm:
            return src
    raise ValueError(
        f"invalid source: {value!r}; "
        f"expected one of {[s.value for s in ExecutionSource]}"
    )


def _extract_source_from_argv(argv: Sequence[str]) -> Optional[str]:
    """从 argv 列表中提取 --source=VALUE 或 --source VALUE

    约定：
        - --source=cron
        - --source cron
        - -s cron        （短选项也支持，便于 Skill 调用更紧凑）
        - --source=cron --date=2026-06-09 都可以

    返回 None 表示 argv 里没有 --source。
    """
    if not argv:
        return None
    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok == "--source" or tok == "-s":
            if i + 1 >= n:
                raise ValueError(f"--source requires a value (got nothing after {tok!r})")
            return argv[i + 1]
        if tok.startswith("--source="):
            return tok.split("=", 1)[1]
        if tok.startswith("-s="):
            return tok.split("=", 1)[1]
        i += 1
    return None


def get_source_from_argv(
    argv: Optional[Sequence[str]] = None,
    *,
    env: Optional[dict] = None,
) -> ExecutionSource:
    """从 argv / 环境变量解析执行源

    解析优先级（高→低）：
        1. 命令行 --source=<value>
        2. 环境变量 EXECUTION_SOURCE
        3. 缺省 MANUAL

    注意：这里不抛错。调用方如需"显式拒绝 UNKNOWN"，
    应使用 ``resolve_source_strict()`` 或在拿到结果后自行判断。
    """
    env_map = env if env is not None else os.environ

    if argv is None:
        argv = sys.argv[1:]

    # 1) argv 解析
    arg_val = _extract_source_from_argv(argv)
    if arg_val is not None:
        return parse_source(arg_val)

    # 2) 环境变量
    env_val = env_map.get(ENV_VAR_NAME)
    if env_val:
        return parse_source(env_val)

    # 3) 缺省
    return ExecutionSource.MANUAL


def resolve_source_strict(
    argv: Optional[Sequence[str]] = None,
    *,
    env: Optional[dict] = None,
) -> ExecutionSource:
    """严格解析：UNKNOWN 显式拒绝

    用途：写操作前的门禁（US-002 会用到）。
    与 ``get_source_from_argv()`` 唯一区别是：
        - 如果解析得到 ExecutionSource.UNKNOWN → 抛 ValueError
        - 其他非法值仍然抛 ValueError（行为一致）

    设计动机：
        ExecutionSource.UNKNOWN 是哨兵值，下游应当明确拒绝。
        例如：用户传了 --source=unknown 想"模糊匹配"，必须显式拒绝
        防止"忘了填"绕过 audit。
    """
    src = get_source_from_argv(argv, env=env)
    if src == ExecutionSource.UNKNOWN:
        raise ValueError(
            "ExecutionSource=UNKNOWN is explicitly rejected; "
            "use one of: cron / skill / dialog / manual"
        )
    return src


def add_source_argument(
    parser,
    *,
    default_help: bool = True,
) -> None:
    """给 argparse.ArgumentParser 加 --source / -s 参数

    设计：
        - choices 来自 ExecutionSource 枚举
        - help 文案统一从这里来，避免散落
    """
    choices = [s.value for s in ExecutionSource]
    help_text = (
        "命令执行源（audit 用）；"
        f"可选: {', '.join(choices)}；"
        "缺省 manual（也可由 EXECUTION_SOURCE 环境变量设置）"
    )
    if not default_help:
        help_text = argparse.SUPPRESS
    parser.add_argument(
        "--source", "-s",
        choices=choices,
        default=None,
        help=help_text,
        dest="source",
    )
