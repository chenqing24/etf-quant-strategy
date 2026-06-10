#!/usr/bin/env python3
"""US-003 DecisionSnapshot 单元测试（≥8 用例）

测试范围：
    - create() 基本功能 + snapshot_id 格式
    - get() 存在/不存在
    - get_by_time() 幂等检查
    - list_by_time_range() 时间范围
    - count() 统计
    - JSON 字段序列化/反序列化
    - 缺字段默认值
    - 目标价/止损字段
"""
import json
import os
import sys
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.trade.decision_snapshot import DecisionSnapshot  # noqa: E402


@pytest.fixture
def isolated_db(monkeypatch):
    """创建临时 db，monkeypatch DecisionSnapshot 的 DB_PATH"""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_snapshot.db"

    # 1. 复制 schema 006/007 结构（用 init_database 风格，但只跑新表）
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS decision_snapshot (
            snapshot_id TEXT PRIMARY KEY,
            snapshot_time TEXT NOT NULL,
            trigger TEXT,
            model_name TEXT,
            model_version TEXT,
            strategy_name TEXT,
            config_json TEXT,
            evaluation_json TEXT,
            factor_breakdown_json TEXT,
            today_top_10_json TEXT,
            backtest_last_10_json TEXT,
            market_regime TEXT,
            reasoning TEXT,
            created_at TEXT,
            target_price REAL,
            stop_loss_price REAL,
            stop_profit_price REAL,
            risk_reward_ratio REAL,
            expected_hold_days INTEGER
        );
    """)
    conn.commit()
    conn.close()

    # 2. monkeypatch DB_PATH
    import src.trade.decision_snapshot as ds_mod
    monkeypatch.setattr(ds_mod, "DB_PATH", db_path)

    yield db_path


class TestDecisionSnapshotCreate:
    """create() 基础功能"""

    def test_create_minimal_returns_snapshot_id(self, isolated_db):
        """最简调用：仅 snapshot_time + trigger，返回 ID"""
        sid = DecisionSnapshot.create(snapshot_time="2026-06-10T10:00:00", trigger="manual")
        assert sid.startswith("snap-")
        assert len(sid) == len("snap-") + 15 + 1 + 6  # snap- + 15 位 ts + - + 6 位 uuid

    def test_create_persists_to_db(self, isolated_db):
        """create 后能在 db 中查到"""
        sid = DecisionSnapshot.create(
            snapshot_time="2026-06-10T10:00:00", trigger="cron_daily_1425",
            model_name="v8_sop", model_version="v8.0",
        )
        row = DecisionSnapshot.get(sid)
        assert row is not None
        assert row["snapshot_id"] == sid
        assert row["model_name"] == "v8_sop"
        assert row["model_version"] == "v8.0"
        assert row["trigger"] == "cron_daily_1425"

    def test_create_serializes_json_fields(self, isolated_db):
        """JSON 字段（config/evaluation/factor_breakdown/today_top_10/backtest_last_10）正确序列化"""
        config = {"selection": {"score_threshold": 6, "top_n": 30}}
        evaluation = {"avg_sharpe": 1.4, "ir": 0.85}
        factor_breakdown = [{"name": "T1_MACD", "ic": 0.04}, {"name": "T2_MA", "ic": -0.01}]
        today_top_10 = [{"code": "510300", "score": 8}, {"code": "515050", "score": 7}]
        backtest_last_10 = [{"date": "2026-06-01", "pnl": 0.02}]

        sid = DecisionSnapshot.create(
            snapshot_time="2026-06-10T10:00:00",
            config=config, evaluation=evaluation,
            factor_breakdown=factor_breakdown,
            today_top_10=today_top_10,
            backtest_last_10=backtest_last_10,
        )
        row = DecisionSnapshot.get(sid)
        assert json.loads(row["config_json"]) == config
        assert json.loads(row["evaluation_json"]) == evaluation
        assert json.loads(row["factor_breakdown_json"]) == factor_breakdown
        assert json.loads(row["today_top_10_json"]) == today_top_10
        assert json.loads(row["backtest_last_10_json"]) == backtest_last_10

    def test_create_with_target_stop_fields(self, isolated_db):
        """带 target/stop 字段"""
        sid = DecisionSnapshot.create(
            snapshot_time="2026-06-10T10:00:00",
            target_price=1.32, stop_loss_price=1.08,
            stop_profit_price=1.32, risk_reward_ratio=1.5,
            expected_hold_days=15,
        )
        row = DecisionSnapshot.get(sid)
        assert row["target_price"] == 1.32
        assert row["stop_loss_price"] == 1.08
        assert row["stop_profit_price"] == 1.32
        assert row["risk_reward_ratio"] == 1.5
        assert row["expected_hold_days"] == 15

    def test_create_idempotency_unique_ids(self, isolated_db):
        """create 两次产生不同 snapshot_id"""
        sid1 = DecisionSnapshot.create(snapshot_time="2026-06-10T10:00:00")
        sid2 = DecisionSnapshot.create(snapshot_time="2026-06-10T10:00:00")
        # 时间戳相同但 uuid 不同
        assert sid1 != sid2
        # 都应能查到（不幂等：业务层做幂等，create 自身不幂等）
        assert DecisionSnapshot.get(sid1) is not None
        assert DecisionSnapshot.get(sid2) is not None

    def test_create_default_expected_hold_days_is_15(self, isolated_db):
        """expected_hold_days 默认 15"""
        sid = DecisionSnapshot.create(snapshot_time="2026-06-10T10:00:00")
        row = DecisionSnapshot.get(sid)
        assert row["expected_hold_days"] == 15


class TestDecisionSnapshotGet:
    """get() 查询功能"""

    def test_get_existing_returns_dict(self, isolated_db):
        """存在的 snapshot_id 返回 dict"""
        sid = DecisionSnapshot.create(snapshot_time="2026-06-10T10:00:00", trigger="manual")
        row = DecisionSnapshot.get(sid)
        assert isinstance(row, dict)
        assert row["snapshot_id"] == sid

    def test_get_nonexistent_returns_none(self, isolated_db):
        """不存在的 snapshot_id 返回 None（不抛错）"""
        assert DecisionSnapshot.get("snap-doesnotexist-abcdef") is None

    def test_get_by_time_finds_matching(self, isolated_db):
        """按时间能查到刚插入的"""
        DecisionSnapshot.create(snapshot_time="2026-06-10T11:00:00", trigger="test")
        row = DecisionSnapshot.get_by_time("2026-06-10T11:00:00")
        assert row is not None
        assert row["trigger"] == "test"

    def test_list_by_time_range(self, isolated_db):
        """按时间范围查询返回多条"""
        DecisionSnapshot.create(snapshot_time="2026-06-09T10:00:00", trigger="a")
        DecisionSnapshot.create(snapshot_time="2026-06-10T10:00:00", trigger="b")
        DecisionSnapshot.create(snapshot_time="2026-06-11T10:00:00", trigger="c")
        # BETWEEN 是闭区间 [start, end]；用一天的范围保证只查到 1 条
        rows = DecisionSnapshot.list_by_time_range("2026-06-10T00:00:00", "2026-06-10T23:59:59")
        assert len(rows) == 1
        assert rows[0]["trigger"] == "b"

    def test_count_returns_inserted_count(self, isolated_db):
        """count() 正确统计"""
        assert DecisionSnapshot.count() == 0
        DecisionSnapshot.create(snapshot_time="2026-06-10T10:00:00")
        DecisionSnapshot.create(snapshot_time="2026-06-10T11:00:00")
        assert DecisionSnapshot.count() == 2
