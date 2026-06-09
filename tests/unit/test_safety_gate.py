#!/usr/bin/env python3
"""
US-002: Safety Gate 单元测试

覆盖（按 PRD AC 要求 7 种场景，11+ 用例）：
    1. CRON 跳过检查（不论 severity，自动放行）
    2. DIALOG Mild pass（无 force 也放行）
    3. DIALOG Moderate 无 force 拒绝
    4. DIALOG Moderate 有 force pass
    5. DIALOG Severe 需 force=对象名
    6. 装饰器嵌套（多层装饰不破坏 require_force）
    7. dry-run 输出（不抛错，仅日志）
    + 额外：MANUAL 规则、未注册 op、argparse helper、Error 信息友好
"""
import os
import sys
import unittest
import argparse
import logging
from unittest import mock

# 让 tests/ 能找到 src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.utils.safety_gate import (
    DangerLevel,
    DESTRUCTIVE_OPS,
    SafetyGateError,
    require_force,
    apply_to_destructive,
    add_force_argument,
    add_dry_run_argument,
    get_danger,
)
from src.utils.execution_source import ExecutionSource


# ────────────────────────────── 基础结构 ──────────────────────────────


class TestDangerLevelEnum(unittest.TestCase):
    """DangerLevel 枚举完整性"""

    def test_enum_has_three_values(self):
        """必须 3 个值（Mild/Moderate/Severe，按 clig.dev）"""
        self.assertEqual(len(list(DangerLevel)), 3)

    def test_enum_values(self):
        values = {d.value for d in DangerLevel}
        self.assertEqual(values, {"mild", "moderate", "severe"})


class TestDestructiveOpsRegistry(unittest.TestCase):
    """DESTRUCTIVE_OPS 注册表完整性"""

    def test_has_expected_ops(self):
        """PRD 要求的 ops 必须在注册表里"""
        self.assertIn("backup_daily", DESTRUCTIVE_OPS)
        self.assertIn("dingtalk_send", DESTRUCTIVE_OPS)
        self.assertIn("clear_positions", DESTRUCTIVE_OPS)
        self.assertIn("reset_db", DESTRUCTIVE_OPS)
        self.assertIn("drop_table", DESTRUCTIVE_OPS)

    def test_severity_assignment(self):
        """PRD 要求的分级必须正确"""
        self.assertEqual(DESTRUCTIVE_OPS["dingtalk_send"], DangerLevel.MODERATE)
        self.assertEqual(DESTRUCTIVE_OPS["report_overwrite"], DangerLevel.MODERATE)
        self.assertEqual(DESTRUCTIVE_OPS["clear_positions"], DangerLevel.SEVERE)
        self.assertEqual(DESTRUCTIVE_OPS["reset_db"], DangerLevel.SEVERE)
        self.assertEqual(DESTRUCTIVE_OPS["backup_daily"], DangerLevel.MILD)


class TestGetDanger(unittest.TestCase):
    """get_danger() 查表 + 拒绝未注册"""

    def test_registered_op(self):
        self.assertEqual(get_danger("dingtalk_send"), DangerLevel.MODERATE)

    def test_unregistered_raises(self):
        """未注册的 op 必须拒绝（防止漏写注册表）"""
        with self.assertRaises(SafetyGateError) as ctx:
            get_danger("unknown_op_xyz")
        self.assertIn("未在 DESTRUCTIVE_OPS 注册", str(ctx.exception))


# ────────────────────────────── 7 种核心场景 ──────────────────────────────


class TestScenario1CRONPass(unittest.TestCase):
    """场景 1: CRON 跳过（不论 severity）"""

    def test_cron_moderate_no_force_passes(self):
        """CRON 触发 Moderate，无 force 也应放行"""
        require_force(
            "dingtalk_send",
            source=ExecutionSource.CRON,
            force=False,
            dry_run=False,
        )

    def test_cron_severe_no_force_passes(self):
        """CRON 触发 Severe，无 force 也应放行"""
        require_force(
            "reset_db",
            source=ExecutionSource.CRON,
            force=False,
            dry_run=False,
            target="db",
        )

    def test_skill_also_skips(self):
        """SKILL 源也应跳过（自动化任务自身有审计）"""
        require_force(
            "clear_positions",
            source=ExecutionSource.SKILL,
            force=False,
            dry_run=False,
            target="positions",
        )


class TestScenario2DialogMild(unittest.TestCase):
    """场景 2: DIALOG Mild pass（无 force 也放行）"""

    def test_dialog_mild_no_force_passes(self):
        require_force(
            "backup_daily",
            source=ExecutionSource.DIALOG,
            force=False,
            dry_run=False,
        )


class TestScenario3DialogModerateReject(unittest.TestCase):
    """场景 3: DIALOG Moderate 无 force 拒绝"""

    def test_dialog_moderate_no_force_raises(self):
        with self.assertRaises(SafetyGateError) as ctx:
            require_force(
                "dingtalk_send",
                source=ExecutionSource.DIALOG,
                force=False,
                dry_run=False,
            )
        # 错误信息要友好
        err = str(ctx.exception)
        self.assertIn("dingtalk_send", err)
        self.assertIn("--force", err)
        self.assertIn("--dry-run", err)

    def test_manual_moderate_no_force_raises(self):
        """MANUAL 触发 Moderate 也应拒绝（防止脚本冒充用户）"""
        with self.assertRaises(SafetyGateError):
            require_force(
                "dingtalk_send",
                source=ExecutionSource.MANUAL,
                force=False,
                dry_run=False,
            )


class TestScenario4DialogModeratePass(unittest.TestCase):
    """场景 4: DIALOG Moderate 有 force pass"""

    def test_dialog_moderate_with_force_passes(self):
        require_force(
            "dingtalk_send",
            source=ExecutionSource.DIALOG,
            force=True,
            dry_run=False,
        )

    def test_dialog_moderate_with_force_string_passes(self):
        """force 传 "true" 字符串也应通过（argparse const=True）"""
        require_force(
            "report_overwrite",
            source=ExecutionSource.DIALOG,
            force="positions",  # 任意非空值都行
            dry_run=False,
        )


class TestScenario5DialogSevereRequiresTarget(unittest.TestCase):
    """场景 5: DIALOG Severe 需 force=对象名精确匹配"""

    def test_dialog_severe_no_force_raises(self):
        """Severe 无 force 必拒"""
        with self.assertRaises(SafetyGateError) as ctx:
            require_force(
                "clear_positions",
                source=ExecutionSource.DIALOG,
                force=False,
                dry_run=False,
                target="positions",
            )
        self.assertIn("--force=<对象名>", str(ctx.exception))

    def test_dialog_severe_force_bool_raises(self):
        """Severe 收到 bool True 也应拒（必须字符串）"""
        with self.assertRaises(SafetyGateError) as ctx:
            require_force(
                "clear_positions",
                source=ExecutionSource.DIALOG,
                force=True,
                dry_run=False,
                target="positions",
            )
        self.assertIn("--force=<对象名>", str(ctx.exception))

    def test_dialog_severe_wrong_target_raises(self):
        """Severe 对象名错配必拒"""
        with self.assertRaises(SafetyGateError) as ctx:
            require_force(
                "clear_positions",
                source=ExecutionSource.DIALOG,
                force="wrong_name",
                dry_run=False,
                target="positions",
            )
        err = str(ctx.exception)
        self.assertIn("'positions'", err)
        self.assertIn("'wrong_name'", err)

    def test_dialog_severe_correct_target_passes(self):
        """Severe 对象名精确匹配通过"""
        require_force(
            "clear_positions",
            source=ExecutionSource.DIALOG,
            force="positions",
            dry_run=False,
            target="positions",
        )

    def test_severe_missing_target_param_raises(self):
        """Severe 缺 target 参数必拒（防呆）"""
        with self.assertRaises(SafetyGateError):
            require_force(
                "reset_db",
                source=ExecutionSource.DIALOG,
                force="db",
                dry_run=False,
                target=None,
            )


class TestScenario6DecoratorNesting(unittest.TestCase):
    """场景 6: 装饰器嵌套（多层装饰不破坏 require_force）"""

    def test_decorator_blocks_when_no_force(self):
        """装饰器包裹的函数，无 force 时应被拒"""
        @apply_to_destructive("dingtalk_send")
        def send_alert(*, source, force=False, dry_run=False, **kwargs):
            return "SENT"

        with self.assertRaises(SafetyGateError):
            send_alert(source=ExecutionSource.DIALOG, force=False)

    def test_decorator_passes_with_force(self):
        """装饰器包裹的函数，有 force 时放行"""
        @apply_to_destructive("dingtalk_send")
        def send_alert(*, source, force=False, dry_run=False, **kwargs):
            return "SENT"

        result = send_alert(source=ExecutionSource.DIALOG, force=True)
        self.assertEqual(result, "SENT")

    def test_decorator_nested_with_other_decorator(self):
        """装饰器嵌套（@require_force 在 @timing 之外）"""
        def timing_decorator(func):
            def wrapper(*args, **kwargs):
                kwargs['_timed'] = True
                return func(*args, **kwargs)
            return wrapper

        @apply_to_destructive("dingtalk_send")
        @timing_decorator
        def send_alert(*, source, force=False, dry_run=False, **kwargs):
            return f"SENT timed={kwargs.get('_timed')}"

        # 无 force：被 SafetyGate 拒（即使 timing 已执行）
        with self.assertRaises(SafetyGateError):
            send_alert(source=ExecutionSource.DIALOG, force=False)

        # 有 force：放行，timing 也生效
        result = send_alert(source=ExecutionSource.DIALOG, force=True)
        self.assertEqual(result, "SENT timed=True")

    def test_decorator_unregistered_op_raises_at_def_time(self):
        """未注册的 op 在装饰时（而非调用时）立即抛错"""
        with self.assertRaises(ValueError):
            apply_to_destructive("not_registered_op_xyz")

    def test_decorator_preserves_metadata(self):
        """装饰器保留原函数元信息（functools.wraps）"""
        @apply_to_destructive("dingtalk_send")
        def my_named_function(*, source, force=False, **kwargs):
            """原 docstring"""
            return "x"

        self.assertEqual(my_named_function.__name__, "my_named_function")
        self.assertEqual(my_named_function.__doc__, "原 docstring")


class TestScenario7DryRun(unittest.TestCase):
    """场景 7: dry-run 不抛错，仅打印"""

    def test_dry_run_dialog_moderate_no_force(self):
        """DIALOG Moderate dry-run 无 force 不应抛错"""
        # 不应抛错
        require_force(
            "dingtalk_send",
            source=ExecutionSource.DIALOG,
            force=False,
            dry_run=True,
        )

    def test_dry_run_dialog_severe_no_force(self):
        """DIALOG Severe dry-run 无 force 不应抛错"""
        require_force(
            "reset_db",
            source=ExecutionSource.DIALOG,
            force=False,
            dry_run=True,
            target="db",
        )

    def test_dry_run_logs_intent(self):
        """dry-run 应当记录"将执行"日志"""
        with self.assertLogs("src.utils.safety_gate", level="INFO") as cm:
            require_force(
                "dingtalk_send",
                source=ExecutionSource.DIALOG,
                force=False,
                dry_run=True,
            )
        log_text = "\n".join(cm.output)
        self.assertIn("dry-run", log_text)
        self.assertIn("dingtalk_send", log_text)


# ────────────────────────────── argparse helper ──────────────────────────────


class TestArgparseHelpers(unittest.TestCase):
    """argparse 集成测试"""

    def test_add_force_argument_moderate(self):
        """Moderate 模式 --force 不带值 → True"""
        parser = argparse.ArgumentParser()
        add_force_argument(parser)
        args = parser.parse_args(["--force"])
        self.assertTrue(args.force)

    def test_add_force_argument_with_value(self):
        """--force=positions → 字符串"""
        parser = argparse.ArgumentParser()
        add_force_argument(parser)
        args = parser.parse_args(["--force=positions"])
        self.assertEqual(args.force, "positions")

    def test_add_force_argument_short_flag(self):
        """短选项 -f"""
        parser = argparse.ArgumentParser()
        add_force_argument(parser)
        args = parser.parse_args(["-f"])
        self.assertTrue(args.force)

    def test_add_force_argument_default_false(self):
        """缺省 False"""
        parser = argparse.ArgumentParser()
        add_force_argument(parser)
        args = parser.parse_args([])
        self.assertFalse(args.force)

    def test_add_dry_run_argument(self):
        parser = argparse.ArgumentParser()
        add_dry_run_argument(parser)
        args = parser.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)

        args2 = parser.parse_args([])
        self.assertFalse(args2.dry_run)


# ────────────────────────────── Error 信息 ──────────────────────────────


class TestSafetyGateErrorMessage(unittest.TestCase):
    """错误信息要友好（含 op_name / source / 建议）"""

    def test_error_message_contains_key_fields(self):
        try:
            require_force(
                "dingtalk_send",
                source=ExecutionSource.DIALOG,
                force=False,
                dry_run=False,
            )
        except SafetyGateError as e:
            msg = str(e)
            self.assertIn("dingtalk_send", msg)
            self.assertIn("dialog", msg)
            self.assertIn("--force", msg)
            self.assertIn("--dry-run", msg)
            # 属性也要保留
            self.assertEqual(e.op_name, "dingtalk_send")
            self.assertEqual(e.source, ExecutionSource.DIALOG)
            self.assertEqual(e.danger, DangerLevel.MODERATE)
        else:
            self.fail("应抛 SafetyGateError")


if __name__ == "__main__":
    # 开启 logging 以便测试 dry-run 日志
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()