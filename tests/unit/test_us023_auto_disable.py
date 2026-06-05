#!/usr/bin/env python3
"""US-023 单元测试: 持仓恢复正常 → 自动 disable 监控 cron

设计: 持仓数 ≤ 2 → pause 4 个监控 cron
TDD: 红 → 绿
"""
import os
import sys
import json
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))


# ─────────────────────────────────────────────────────────────
# 测试: pause_cron / is_cron_paused 调用
# ─────────────────────────────────────────────────────────────

class TestCronControl:
    """测试 qwenpaw cron pause 调用"""

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    def test_pause_cron_success(self, mock_run):
        """pause_cron 成功返回 True"""
        from auto_disable_monitor_when_normal import pause_cron
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        assert pause_cron('test-id') is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert 'pause' in args
        assert 'test-id' in args

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    def test_pause_cron_failure(self, mock_run):
        """pause_cron 失败返回 False"""
        from auto_disable_monitor_when_normal import pause_cron
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='error')
        assert pause_cron('test-id') is False

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    def test_is_cron_paused_true(self, mock_run):
        """is_cron_paused 返回 True"""
        from auto_disable_monitor_when_normal import is_cron_paused
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({'paused': True})
        )
        assert is_cron_paused('test-id') is True

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    def test_is_cron_paused_false(self, mock_run):
        """is_cron_paused 返回 False"""
        from auto_disable_monitor_when_normal import is_cron_paused
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({'paused': False})
        )
        assert is_cron_paused('test-id') is False


# ─────────────────────────────────────────────────────────────
# 测试: get_monitor_cron_job_ids
# ─────────────────────────────────────────────────────────────

class TestGetMonitorCronIds:
    """测试获取 4 个监控 cron 的 job_id"""

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    def test_finds_4_monitor_crons(self, mock_run):
        """找到 4 个匹配的 cron"""
        from auto_disable_monitor_when_normal import get_monitor_cron_job_ids
        mock_data = [
            {'id': 'id-1', 'name': '持仓偏离监控-10:00'},
            {'id': 'id-2', 'name': '持仓偏离监控-11:00'},
            {'id': 'id-3', 'name': '持仓偏离监控-13:00'},
            {'id': 'id-4', 'name': '持仓偏离监控-14:00'},
            {'id': 'id-5', 'name': '数据质量监控'},  # 不匹配
            {'id': 'id-6', 'name': '新闻早报'},  # 不匹配
        ]
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(mock_data)
        )
        result = get_monitor_cron_job_ids()
        assert len(result) == 4
        assert 'id-5' not in result
        assert 'id-6' not in result

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    def test_empty_when_cron_list_empty(self, mock_run):
        """cron 列表为空时返回空"""
        from auto_disable_monitor_when_normal import get_monitor_cron_job_ids
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps([]))
        assert get_monitor_cron_job_ids() == []

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    def test_empty_on_subprocess_error(self, mock_run):
        """subprocess 失败时返回空 (graceful)"""
        from auto_disable_monitor_when_normal import get_monitor_cron_job_ids
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='err')
        assert get_monitor_cron_job_ids() == []


# ─────────────────────────────────────────────────────────────
# 测试: 主逻辑 (持仓数 → pause 行为)
# ─────────────────────────────────────────────────────────────

class TestMainLogic:
    """主逻辑: 持仓数 ≤ 2 → pause 4 个监控 cron"""

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    @patch('auto_disable_monitor_when_normal.TradeTracker')
    def test_holdings_le_2_pauses_all(self, mock_tracker, mock_run):
        """持仓 ≤ 2 → pause 4 个 cron"""
        from auto_disable_monitor_when_normal import main

        # Mock 持仓 = 2 (正常)
        mock_tracker.return_value.get_holdings.return_value = [
            MagicMock(code='515050'),
            MagicMock(code='512480'),
        ]

        # Mock qwenpaw cron list 返回 4 个监控 cron
        mock_list = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {'id': 'id-1', 'name': '持仓偏离监控-10:00'},
                {'id': 'id-2', 'name': '持仓偏离监控-11:00'},
                {'id': 'id-3', 'name': '持仓偏离监控-13:00'},
                {'id': 'id-4', 'name': '持仓偏离监控-14:00'},
            ])
        )
        # Mock state: 都未 paused
        mock_state = MagicMock(returncode=0, stdout=json.dumps({'paused': False}))
        # Mock pause: 成功
        mock_pause = MagicMock(returncode=0, stdout='', stderr='')

        # 按调用顺序返回: list → state×4 → pause×4
        mock_run.side_effect = [mock_list] + [mock_state] * 4 + [mock_pause] * 4

        result = main()
        assert result == 0
        # 4 次 pause 调用
        pause_calls = [c for c in mock_run.call_args_list if 'pause' in c[0][0]]
        assert len(pause_calls) == 4

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    @patch('auto_disable_monitor_when_normal.TradeTracker')
    def test_holdings_gt_2_does_not_pause(self, mock_tracker, mock_run):
        """持仓 > 2 → 不 pause"""
        from auto_disable_monitor_when_normal import main

        # Mock 持仓 = 3 (偏离)
        mock_tracker.return_value.get_holdings.return_value = [
            MagicMock(code='515050'),
            MagicMock(code='512480'),
            MagicMock(code='515070'),
        ]

        result = main()
        assert result == 0
        # 0 次 pause 调用
        pause_calls = [c for c in mock_run.call_args_list if 'pause' in c[0][0]]
        assert len(pause_calls) == 0

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    @patch('auto_disable_monitor_when_normal.TradeTracker')
    def test_holdings_zero_pauses(self, mock_tracker, mock_run):
        """持仓 = 0 → pause (边界)"""
        from auto_disable_monitor_when_normal import main

        mock_tracker.return_value.get_holdings.return_value = []

        mock_list = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {'id': 'id-1', 'name': '持仓偏离监控-10:00'},
                {'id': 'id-2', 'name': '持仓偏离监控-11:00'},
                {'id': 'id-3', 'name': '持仓偏离监控-13:00'},
                {'id': 'id-4', 'name': '持仓偏离监控-14:00'},
            ])
        )
        mock_state = MagicMock(returncode=0, stdout=json.dumps({'paused': False}))
        mock_pause = MagicMock(returncode=0, stdout='', stderr='')

        mock_run.side_effect = [mock_list] + [mock_state] * 4 + [mock_pause] * 4

        result = main()
        assert result == 0
        pause_calls = [c for c in mock_run.call_args_list if 'pause' in c[0][0]]
        assert len(pause_calls) == 4

    @patch('auto_disable_monitor_when_normal.subprocess.run')
    @patch('auto_disable_monitor_when_normal.TradeTracker')
    def test_already_paused_skipped(self, mock_tracker, mock_run):
        """已 paused 的 cron 跳过 (不重复 pause)"""
        from auto_disable_monitor_when_normal import main

        mock_tracker.return_value.get_holdings.return_value = [MagicMock(code='515050')]

        mock_list = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {'id': 'id-1', 'name': '持仓偏离监控-10:00'},
                {'id': 'id-2', 'name': '持仓偏离监控-11:00'},
            ])
        )
        # 1 个 paused, 1 个未 paused
        mock_state_paused = MagicMock(returncode=0, stdout=json.dumps({'paused': True}))
        mock_state_active = MagicMock(returncode=0, stdout=json.dumps({'paused': False}))
        mock_pause = MagicMock(returncode=0, stdout='', stderr='')

        mock_run.side_effect = [mock_list, mock_state_paused, mock_state_active, mock_pause]

        result = main()
        assert result == 0
        # 只 1 次 pause (跳过已 paused)
        pause_calls = [c for c in mock_run.call_args_list if 'pause' in c[0][0]]
        assert len(pause_calls) == 1
