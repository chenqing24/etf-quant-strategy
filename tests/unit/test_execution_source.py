#!/usr/bin/env python3
"""
US-001: ExecutionSource 单元测试

覆盖：
    1. 枚举值完整性
    2. 5 种 source 解析
    3. 非法值显式拒绝（含 None/空/错值）
    4. 环境变量回退
    5. argv 优先级 > 环境变量 > MANUAL
    6. UNKNOWN 严格拒绝
    7. argparse helper 集成
"""
import os
import sys
import unittest
import argparse
from unittest import mock

# 让 tests/ 能找到 src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.utils.execution_source import (
    ExecutionSource,
    ENV_VAR_NAME,
    parse_source,
    get_source_from_argv,
    resolve_source_strict,
    _extract_source_from_argv,
    add_source_argument,
)


class TestExecutionSourceEnum(unittest.TestCase):
    """枚举完整性"""

    def test_enum_has_five_values(self):
        """枚举必须有 5 个值（按 PRD）"""
        self.assertEqual(len(list(ExecutionSource)), 5)

    def test_enum_values(self):
        """枚举值集合必须精确匹配 PRD"""
        values = {s.value for s in ExecutionSource}
        self.assertEqual(
            values,
            {"cron", "skill", "dialog", "manual", "unknown"},
        )

    def test_enum_is_str_enum(self):
        """枚举值可以直接当字符串用（str(value) == value）"""
        for s in ExecutionSource:
            self.assertEqual(s.value, str(s.value))
            self.assertIsInstance(s, str)


class TestParseSource(unittest.TestCase):
    """parse_source() 5 种 source + 非法拒绝"""

    def test_parse_cron(self):
        self.assertEqual(parse_source("cron"), ExecutionSource.CRON)

    def test_parse_skill(self):
        self.assertEqual(parse_source("skill"), ExecutionSource.SKILL)

    def test_parse_dialog(self):
        self.assertEqual(parse_source("dialog"), ExecutionSource.DIALOG)

    def test_parse_manual(self):
        self.assertEqual(parse_source("manual"), ExecutionSource.MANUAL)

    def test_parse_unknown(self):
        """UNKNOWN 是合法哨兵值，parse 应当通过"""
        self.assertEqual(parse_source("unknown"), ExecutionSource.UNKNOWN)

    def test_case_insensitive(self):
        """大小写不敏感"""
        self.assertEqual(parse_source("CRON"), ExecutionSource.CRON)
        self.assertEqual(parse_source("Skill"), ExecutionSource.SKILL)
        self.assertEqual(parse_source("  MANUAL  "), ExecutionSource.MANUAL)

    def test_invalid_raises(self):
        """非法值显式拒绝（不静默回退 MANUAL，规则 19）"""
        with self.assertRaises(ValueError):
            parse_source("crn")
        with self.assertRaises(ValueError):
            parse_source("auto")

    def test_none_raises(self):
        with self.assertRaises(ValueError):
            parse_source(None)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_source("")
        with self.assertRaises(ValueError):
            parse_source("   ")


class TestExtractFromArgv(unittest.TestCase):
    """_extract_source_from_argv 内部函数"""

    def test_no_flag(self):
        self.assertIsNone(_extract_source_from_argv([]))
        self.assertIsNone(_extract_source_from_argv(["--date", "2026-06-09"]))

    def test_long_form_equals(self):
        self.assertEqual(_extract_source_from_argv(["--source=cron"]), "cron")

    def test_long_form_space(self):
        self.assertEqual(_extract_source_from_argv(["--source", "skill"]), "skill")

    def test_short_form_space(self):
        self.assertEqual(_extract_source_from_argv(["-s", "dialog"]), "dialog")

    def test_short_form_equals(self):
        self.assertEqual(_extract_source_from_argv(["-s=manual"]), "manual")

    def test_long_form_missing_value(self):
        """--source 后面没值应当报错（不静默吞掉）"""
        with self.assertRaises(ValueError):
            _extract_source_from_argv(["--source"])

    def test_mixed_with_other_args(self):
        argv = ["-m", "daily", "--date", "2026-06-09", "--source=cron", "-v"]
        self.assertEqual(_extract_source_from_argv(argv), "cron")


class TestGetSourceFromArgv(unittest.TestCase):
    """get_source_from_argv() 解析优先级"""

    def test_default_is_manual(self):
        """缺省 = MANUAL（规则 19 宁严勿宽）"""
        result = get_source_from_argv([], env={})
        self.assertEqual(result, ExecutionSource.MANUAL)

    def test_argv_wins(self):
        """argv 优先级 > 环境变量"""
        result = get_source_from_argv(
            ["--source=manual"],
            env={ENV_VAR_NAME: "cron"},
        )
        self.assertEqual(result, ExecutionSource.MANUAL)

    def test_env_fallback(self):
        """argv 没传 → 环境变量"""
        result = get_source_from_argv([], env={ENV_VAR_NAME: "skill"})
        self.assertEqual(result, ExecutionSource.SKILL)

    def test_env_case_insensitive(self):
        result = get_source_from_argv([], env={ENV_VAR_NAME: "DIALOG"})
        self.assertEqual(result, ExecutionSource.DIALOG)

    def test_both_missing(self):
        result = get_source_from_argv([], env={})
        self.assertEqual(result, ExecutionSource.MANUAL)

    def test_short_flag(self):
        result = get_source_from_argv(["-s", "cron"])
        self.assertEqual(result, ExecutionSource.CRON)

    def test_invalid_argv_raises(self):
        """argv 非法值必须报错（不静默回退）"""
        with self.assertRaises(ValueError):
            get_source_from_argv(["--source=crn"], env={})

    def test_invalid_env_raises(self):
        with self.assertRaises(ValueError):
            get_source_from_argv([], env={ENV_VAR_NAME: "auto"})


class TestResolveSourceStrict(unittest.TestCase):
    """resolve_source_strict() 显式拒绝 UNKNOWN"""

    def test_manual_allowed(self):
        self.assertEqual(
            resolve_source_strict([], env={}),
            ExecutionSource.MANUAL,
        )

    def test_cron_allowed(self):
        self.assertEqual(
            resolve_source_strict(["--source=cron"]),
            ExecutionSource.CRON,
        )

    def test_unknown_rejected(self):
        """UNKNOWN 必须显式拒绝（防\"忘了填\"绕过 audit）"""
        with self.assertRaises(ValueError) as ctx:
            resolve_source_strict(["--source=unknown"])
        self.assertIn("UNKNOWN", str(ctx.exception))

    def test_unknown_via_env_rejected(self):
        with self.assertRaises(ValueError):
            resolve_source_strict([], env={ENV_VAR_NAME: "unknown"})


class TestAddSourceArgument(unittest.TestCase):
    """add_source_argument() argparse 集成"""

    def test_argparse_with_source(self):
        parser = argparse.ArgumentParser()
        add_source_argument(parser)
        args = parser.parse_args(["--source=cron"])
        self.assertEqual(args.source, "cron")

    def test_argparse_default_none(self):
        """argparse 层不设缺省（让 get_source_from_argv 兜底）"""
        parser = argparse.ArgumentParser()
        add_source_argument(parser)
        args = parser.parse_args([])
        self.assertIsNone(args.source)

    def test_argparse_invalid_choice(self):
        parser = argparse.ArgumentParser()
        add_source_argument(parser)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--source=invalid"])

    def test_argparse_short_flag(self):
        parser = argparse.ArgumentParser()
        add_source_argument(parser)
        args = parser.parse_args(["-s", "skill"])
        self.assertEqual(args.source, "skill")


class TestIntegrationRealUseCases(unittest.TestCase):
    """端到端：模拟真实调用场景"""

    def test_cron_job_invocation(self):
        """cron 任务调用: --source=cron"""
        result = get_source_from_argv(
            ["-m", "daily", "--source=cron", "--date", "2026-06-09"]
        )
        self.assertEqual(result, ExecutionSource.CRON)

    def test_skill_invocation(self):
        """Skill 调用: --source=skill"""
        result = get_source_from_argv(["--source=skill", "-m", "eval"])
        self.assertEqual(result, ExecutionSource.SKILL)

    def test_dialog_invocation(self):
        """对话/Agent 调用: --source=dialog"""
        result = get_source_from_argv(["-s", "dialog"])
        self.assertEqual(result, ExecutionSource.DIALOG)

    def test_manual_default_invocation(self):
        """用户直接跑 CLI，不带 --source"""
        result = get_source_from_argv(["-m", "daily"])
        self.assertEqual(result, ExecutionSource.MANUAL)


if __name__ == "__main__":
    unittest.main()
