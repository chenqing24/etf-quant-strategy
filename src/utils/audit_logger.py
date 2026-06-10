#!/usr/bin/env python3
"""
Audit Logger — 审计事件写 stdout (US-003)

设计目标（按 12-Factor App § XI Logs）：
    1. 写 stdout 不写文件（由 cron / shell 路由到文件 / journald / log aggregator）
    2. 输出格式 = JSON Lines（一行一个 JSON object）
    3. 写 stdout 失败不能影响主流程（try/except 全包）
    4. 敏感字段过滤：password / token / client_secret 永远不落日志

业界参考（按 SOUL 规则 13 标注来源）：
    - 12-Factor App § XI. Logs (https://12factor.net/logs)
        * "A twelve-factor app never concerns itself with routing or storage
           of its output stream. It should not attempt to write to or manage
           logfiles. Instead, each running process writes its event stream,
           unbuffered, to stdout."
    - OWASP ASVS V7 Logging：审计必填字段 actor / event_type / outcome
        https://owasp.org/www-project-application-security-verification-standard/
    - Kafka JSON Lines 业界惯例（一行一事件，便于 stream 处理）

字段约定：
    timestamp      ISO 8601 + Asia/Shanghai 时区（可读性 + 明确性）
    source         执行源（来自 US-001 ExecutionSource）
    actor          行为人/agent 名（可空）
    event_type     事件类型（started / success / failed / denied_by_safety_gate / ...）
    command        触发命令（如 "decision.py --mode=trade"）
    args           关键参数（敏感字段过滤后）
    duration_ms    耗时（毫秒）
    outcome        success / failed / denied
    error_msg      失败原因（成功时为空）
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

# 唯一时区常量：Asia/Shanghai（避免每次新建）
_TZ_SHANGHAI = timezone(timedelta(hours=8))

# 敏感字段白名单：键名匹配（regex，不区分大小写）
# 命中后整个键值替换为 "***REDACTED***"
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|pwd|token|api[_-]?key|client[_-]?secret|secret|access[_-]?key|authorization)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def _now_iso_shanghai() -> str:
    """返回 ISO 8601 + Asia/Shanghai 时区的时间戳"""
    return datetime.now(_TZ_SHANGHAI).isoformat(timespec="milliseconds")


def _redact(obj: Any) -> Any:
    """递归过滤敏感字段

    命中规则：键名（不论层级）匹配 _SENSITIVE_KEY_RE → 值替换为 ***REDACTED***
    非 dict/list 直接返回原值
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SENSITIVE_KEY_RE.search(k):
                out[k] = _REDACTED
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class AuditLogger:
    """审计事件写 stdout（单例风格，无状态）

    使用方式：
        audit = AuditLogger()
        audit.write_event(
            event_type="started",
            command="decision.py --mode=trade",
            source="manual",
            actor="月海巫师",
        )
    """

    def write_event(
        self,
        event_type: str,
        command: str,
        source: Optional[str] = None,
        actor: Optional[str] = None,
        args: Optional[dict] = None,
        outcome: str = "success",
        duration_ms: Optional[float] = None,
        error_msg: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """写一条 audit 事件到 stdout（JSON Lines 格式）

        任何异常都吞掉，不能影响主流程。

        参数：
            event_type   事件类型（started/success/failed/denied_by_safety_gate/...）
            command      触发的命令字符串
            source       执行源（cron/skill/dialog/manual/unknown）
            actor        行为人（user/agent 名）
            args         命令参数（dict，会过滤敏感字段）
            outcome      success / failed / denied
            duration_ms  耗时（毫秒）
            error_msg    失败原因
            **extra      其它要记录的字段
        """
        try:
            record = {
                "timestamp": _now_iso_shanghai(),
                "source": source or "unknown",
                "actor": actor,
                "event_type": event_type,
                "command": command,
                "args": _redact(args) if args else {},
                "duration_ms": duration_ms,
                "outcome": outcome,
                "error_msg": error_msg,
            }
            # 合并额外字段（不覆盖核心字段）
            for k, v in extra.items():
                if k not in record:
                    record[k] = _redact(v)
            # 一行一个 JSON object（JSON Lines）
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            # 写 stdout（flush=True 让事件立即可见，便于 cron 路由）
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            # 永远不抛错 — audit 失败不能影响主流程
            # 用 stderr 简短提示（可选，避免完全静默）
            try:
                sys.stderr.write("[audit] write_event failed (suppressed)\n")
                sys.stderr.flush()
            except Exception:
                pass


# 模块级单例（无状态，可直接调用）
_default_audit = AuditLogger()


def get_audit() -> AuditLogger:
    """获取默认 AuditLogger 实例（推荐用法）"""
    return _default_audit
