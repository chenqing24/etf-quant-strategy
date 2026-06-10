#!/usr/bin/env python3
"""
AuditLogger 单元测试 (US-003)

覆盖 7+ 场景：
    1. 正常事件 (started/success)
    2. 失败事件 (failed + error_msg)
    3. 拒绝事件 (denied_by_safety_gate)
    4. 敏感字段过滤（password / token / client_secret / api_key 等）
    5. JSON 格式校验（每行是合法 JSON object）
    6. 时区正确（Asia/Shanghai + ISO 8601）
    7. 异常不影响主流程（即使 stdout 写失败也不抛）
"""
import io
import json
import re
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# 把项目根加入 sys.path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.audit_logger import (
    AuditLogger,
    _redact,
    _now_iso_shanghai,
    _SENSITIVE_KEY_RE,
)


def _capture_stdout(fn):
    """执行 fn，把 fn 写向 sys.stdout 的内容捕获为字符串"""
    buf = io.StringIO()
    real = sys.stdout
    sys.stdout = buf
    try:
        fn()
    finally:
        sys.stdout = real
    return buf.getvalue()


class TestAuditLoggerNormal(unittest.TestCase):
    """场景 1: 正常事件"""

    def test_started_event_writes_one_line(self):
        audit = AuditLogger()
        out = _capture_stdout(lambda: audit.write_event(
            event_type="started",
            command="decision.py --mode=daily",
            source="manual",
            actor="月海巫师",
            args={"mode": "daily", "capital": 20000},
        ))
        lines = [l for l in out.strip().split("\n") if l]
        self.assertEqual(len(lines), 1, f"应只写一行，实际 {len(lines)}: {lines!r}")
        rec = json.loads(lines[0])
        self.assertEqual(rec["event_type"], "started")
        self.assertEqual(rec["source"], "manual")
        self.assertEqual(rec["actor"], "月海巫师")
        self.assertEqual(rec["outcome"], "success")
        self.assertEqual(rec["command"], "decision.py --mode=daily")
        self.assertEqual(rec["args"]["mode"], "daily")

    def test_success_event_with_duration(self):
        audit = AuditLogger()
        out = _capture_stdout(lambda: audit.write_event(
            event_type="success",
            command="monitor.py --json",
            source="cron",
            duration_ms=123.45,
        ))
        rec = json.loads(out.strip())
        self.assertEqual(rec["event_type"], "success")
        self.assertEqual(rec["duration_ms"], 123.45)
        self.assertEqual(rec["source"], "cron")


class TestAuditLoggerFailed(unittest.TestCase):
    """场景 2: 失败事件"""

    def test_failed_event_carries_error_msg(self):
        audit = AuditLogger()
        out = _capture_stdout(lambda: audit.write_event(
            event_type="failed",
            command="decision.py --mode=trade",
            source="manual",
            outcome="failed",
            error_msg="network timeout",
        ))
        rec = json.loads(out.strip())
        self.assertEqual(rec["outcome"], "failed")
        self.assertEqual(rec["error_msg"], "network timeout")
        self.assertEqual(rec["event_type"], "failed")


class TestAuditLoggerDenied(unittest.TestCase):
    """场景 3: 拒绝事件（SafetyGate 拦截）"""

    def test_denied_by_safety_gate_event(self):
        audit = AuditLogger()
        out = _capture_stdout(lambda: audit.write_event(
            event_type="denied_by_safety_gate",
            command="decision.py --mode=trade",
            source="manual",
            outcome="denied",
            error_msg="Moderate 操作需要 --force",
            op="trade_record",
        ))
        rec = json.loads(out.strip())
        self.assertEqual(rec["event_type"], "denied_by_safety_gate")
        self.assertEqual(rec["outcome"], "denied")
        self.assertIn("--force", rec["error_msg"])
        self.assertEqual(rec["op"], "trade_record")


class TestAuditLoggerSensitiveFilter(unittest.TestCase):
    """场景 4: 敏感字段过滤"""

    def test_redact_password_token_apikey(self):
        audit = AuditLogger()
        out = _capture_stdout(lambda: audit.write_event(
            event_type="started",
            command="backup.py",
            source="manual",
            args={
                "db_path": "/data/etf.db",
                "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=ABC123",
                "api_key": "sk-12345",
                "password": "mysecret",
                "client_secret": "shhh",
            },
        ))
        rec = json.loads(out.strip())
        # 业务字段保留
        self.assertEqual(rec["args"]["db_path"], "/data/etf.db")
        # 敏感 KEY 字段被替换
        self.assertEqual(rec["args"]["password"], "***REDACTED***")
        self.assertEqual(rec["args"]["api_key"], "***REDACTED***")
        self.assertEqual(rec["args"]["client_secret"], "***REDACTED***")
        # 非敏感 KEY 的 URL 保留（业界实践：按 KEY 名脱敏，URL 内的 token 属业务方责任）
        self.assertIn("access_token=ABC123", rec["args"]["webhook_url"])

    def test_redact_nested_in_extra(self):
        audit = AuditLogger()
        out = _capture_stdout(lambda: audit.write_event(
            event_type="started",
            command="x.py",
            source="manual",
            extra={"payload": {"token": "abc", "ok": True}},
        ))
        rec = json.loads(out.strip())
        # extra 是顶层 key，其内部递归脱敏
        self.assertEqual(rec["extra"]["payload"]["token"], "***REDACTED***")
        self.assertEqual(rec["extra"]["payload"]["ok"], True)

    def test_redact_unit(self):
        """直接测 _redact 工具函数"""
        self.assertEqual(_redact({"password": "x", "name": "y"}),
                         {"password": "***REDACTED***", "name": "y"})
        self.assertEqual(_redact([{"token": "a"}, {"safe": 1}]),
                         [{"token": "***REDACTED***"}, {"safe": 1}])
        self.assertEqual(_redact("plain"), "plain")


class TestAuditLoggerJSONFormat(unittest.TestCase):
    """场景 5: JSON 格式校验"""

    def test_each_line_is_valid_json(self):
        audit = AuditLogger()
        out = _capture_stdout(lambda: (
            audit.write_event("started", "a.py", "manual"),
            audit.write_event("success", "b.py", "cron", duration_ms=10.0),
            audit.write_event("failed", "c.py", "skill", error_msg="boom"),
        ))
        lines = [l for l in out.strip().split("\n") if l]
        self.assertEqual(len(lines), 3)
        for line in lines:
            # 必须能解析为 dict
            rec = json.loads(line)
            self.assertIsInstance(rec, dict)
            # 必须包含核心字段
            for k in ("timestamp", "source", "event_type", "command", "outcome"):
                self.assertIn(k, rec, f"缺字段 {k}: {rec!r}")

    def test_no_trailing_garbage(self):
        """每行只有 JSON object，没有额外字符"""
        audit = AuditLogger()
        out = _capture_stdout(lambda: audit.write_event("started", "x.py", "manual"))
        line = out.strip()
        # 必须以 } 结尾
        self.assertTrue(line.endswith("}"))
        # 不含换行
        self.assertNotIn("\n", line)


class TestAuditLoggerTimezone(unittest.TestCase):
    """场景 6: 时区正确（Asia/Shanghai, ISO 8601）"""

    def test_timestamp_is_shanghai_iso(self):
        ts = _now_iso_shanghai()
        # 形如 2026-06-10T15:30:45.123+08:00
        m = re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+08:00$", ts)
        self.assertIsNotNone(m, f"时区戳格式不对: {ts}")

    def test_timestamp_actually_shanghai(self):
        """验证 _now_iso_shanghai 输出的时间 = UTC+8 的本地时间"""
        ts = _now_iso_shanghai()
        # 解析
        dt = datetime.fromisoformat(ts)
        # 用 UTC 算 +8
        utc_now = datetime.now(timezone.utc)
        shanghai_now = utc_now.astimezone(timezone(timedelta(hours=8)))
        # 容差 1 秒
        self.assertLess(abs((dt - shanghai_now).total_seconds()), 1.0)


class TestAuditLoggerResilience(unittest.TestCase):
    """场景 7: 异常不影响主流程"""

    def test_write_event_suppresses_exceptions(self):
        """即使 stdout 写失败，write_event 也不抛"""
        audit = AuditLogger()
        # 把 sys.stdout 替换成会抛异常的
        class BrokenStream:
            def write(self, *a, **kw):
                raise OSError("disk full")
            def flush(self, *a, **kw):
                pass
        real = sys.stdout
        sys.stdout = BrokenStream()
        try:
            # 不应抛错
            audit.write_event("started", "x.py", "manual")
        finally:
            sys.stdout = real
        # OK = 走到这里没抛

    def test_redact_handles_unusual_input(self):
        """_redact 对奇怪输入也安全"""
        # 嵌套循环引用不展开到死循环（dict 不递归引用）
        d = {"a": {"b": {"c": 1}}}
        self.assertEqual(_redact(d), {"a": {"b": {"c": 1}}})
        # None
        self.assertIsNone(_redact(None))
        # 数字
        self.assertEqual(_redact(42), 42)


if __name__ == "__main__":
    unittest.main(verbosity=2)
