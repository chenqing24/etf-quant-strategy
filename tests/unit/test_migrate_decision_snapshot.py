#!/usr/bin/env python3
"""US-003 migrate_decision_snapshot 单元测试（≥4 用例）

测试范围：
    - 迁移函数能从 JSON 读出并 INSERT
    - 重复运行幂等（不重复插入）
    - 回填 is_real=1 buy 交易（按 config 默认值）
    - 重复回填幂等（不回填已有 target_price）
    - 写 audit_log（is_historical_backfill=1）
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# 必须在 sys.path 注入后 import
import scripts.migrate_decision_snapshot as mig  # noqa: E402


SAMPLE_SNAPSHOT_JSON = {
    "snapshot_time": "2026-06-01T14:17:39.876852",
    "snapshot_version": "1.0",
    "auto_generated": True,
    "trigger": "cron_daily_1425",
    "model_info": {
        "name": "ETF量化决策v8_sop",
        "experiment_info": {
            "version": "v8.0_sop",
        },
    },
    "strategy_config": {
        "selection": {"score_threshold": 6, "top_n": 30},
        "position": {"hold_count": 2, "weights": [0.5, 0.5]},
        "rebalance": {"rebalance_days": 10},
        "risk_control": {"stop_loss": -0.10, "stop_gain": 0.15, "max_hold_days": 15},
    },
    "evaluation_metrics": {
        "T1_MACD红柱": {"ic_mean": 0.0423, "ir": 1.4405},
    },
    "top_5_models": [],
    "today_top_10": [{"code": "510300", "score": 8}],
    "backtest_last_10_trades": [{"date": "2026-06-01", "pnl": 0.02}],
}


@pytest.fixture
def isolated_db_with_buy_trade(monkeypatch, tmp_path):
    """创建临时 db，含 1 笔 is_real=1 buy 待回填"""
    db_path = tmp_path / "test.db"
    json_path = tmp_path / "decision_snapshot.json"

    # 写 JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_SNAPSHOT_JSON, f, ensure_ascii=False)

    # 1. 创建 schema 004（trade_history）+ 006（target/stop 字段）+ 007（decision_snapshot）
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, code TEXT, name TEXT, action TEXT,
            price REAL, quantity INTEGER, amount REAL, reason TEXT,
            emotion TEXT, session TEXT, signal_time TEXT, signal_price REAL,
            signal_rsi REAL, signal_adx REAL, signal_score INTEGER,
            realtime_price REAL, price_deviation REAL, rsi_14 REAL,
            day_change_pct REAL, score INTEGER,
            expected_return REAL, actual_pnl REAL, note TEXT,
            trade_time TEXT, is_real INTEGER, is_paper INTEGER,
            model TEXT, strategy TEXT, evaluation TEXT, snapshot_ref TEXT,
            created_at TEXT,
            target_price REAL, stop_loss_price REAL, stop_profit_price REAL,
            risk_reward_ratio REAL, max_hold_days INTEGER
        );
        CREATE TABLE decision_snapshot (
            snapshot_id TEXT PRIMARY KEY,
            snapshot_time TEXT NOT NULL, trigger TEXT,
            model_name TEXT, model_version TEXT, strategy_name TEXT,
            config_json TEXT, evaluation_json TEXT, factor_breakdown_json TEXT,
            today_top_10_json TEXT, backtest_last_10_json TEXT,
            market_regime TEXT, reasoning TEXT, created_at TEXT,
            target_price REAL, stop_loss_price REAL, stop_profit_price REAL,
            risk_reward_ratio REAL, expected_hold_days INTEGER
        );
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, action TEXT, code TEXT,
            from_state TEXT, to_state TEXT, detail TEXT, created_at TEXT
        );
    """)
    # 插 1 笔 is_real=1 buy 无 target_price
    conn.execute(
        """
        INSERT INTO trade_history (
            date, code, name, action, price, quantity, amount, is_real
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-06-02", "515050", "5GETF", "buy", 1.197, 2600, 3112.2, 1),
    )
    conn.commit()
    conn.close()

    # monkeypatch DB_PATH 和 JSON_PATH
    monkeypatch.setattr(mig, "DB_PATH", db_path)
    monkeypatch.setattr(mig, "JSON_PATH", json_path)

    yield db_path, json_path


class TestMigrateSnapshotFromJson:
    """migrate_snapshot_from_json() 测试"""

    def test_inserts_decision_snapshot_from_json(self, isolated_db_with_buy_trade):
        """从 JSON 读出字段并 INSERT 到 decision_snapshot 表"""
        db_path, _ = isolated_db_with_buy_trade
        sid = mig.migrate_snapshot_from_json()
        assert sid is not None
        assert sid.startswith("snap-historical-")

        # 查表确认
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT snapshot_id, snapshot_time, trigger, model_name, model_version "
            "FROM decision_snapshot WHERE snapshot_id=?",
            (sid,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[1] == "2026-06-01T14:17:39.876852"
        assert row[2] == "cron_daily_1425"
        assert row[3] == "ETF量化决策v8_sop"
        assert row[4] == "v8.0_sop"

    def test_idempotent_on_repeated_run(self, isolated_db_with_buy_trade):
        """重复运行不重复插入（幂等）"""
        db_path, _ = isolated_db_with_buy_trade
        sid1 = mig.migrate_snapshot_from_json()
        sid2 = mig.migrate_snapshot_from_json()
        assert sid1 is not None
        assert sid2 is None  # 第二次跳过

        # 确认表中只有 1 行
        conn = sqlite3.connect(db_path)
        cnt = conn.execute("SELECT COUNT(*) FROM decision_snapshot").fetchone()[0]
        conn.close()
        assert cnt == 1

    def test_missing_json_file_returns_none(self, monkeypatch, tmp_path):
        """JSON 不存在时返回 None（不抛错）"""
        db_path = tmp_path / "nojson.db"
        monkeypatch.setattr(mig, "DB_PATH", db_path)
        monkeypatch.setattr(mig, "JSON_PATH", tmp_path / "nonexistent.json")
        result = mig.migrate_snapshot_from_json()
        assert result is None


class TestBackfillTradeTargetStop:
    """backfill_trade_target_stop() 测试"""

    def test_backfill_sets_target_stop_for_is_real_1_buy(self, isolated_db_with_buy_trade):
        """is_real=1 buy 无 target_price 的回填"""
        db_path, _ = isolated_db_with_buy_trade
        count = mig.backfill_trade_target_stop()
        assert count == 1

        # 查回填结果
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT target_price, stop_loss_price, stop_profit_price, "
            "risk_reward_ratio, max_hold_days "
            "FROM trade_history WHERE code='515050' AND action='buy'"
        ).fetchone()
        conn.close()
        # price=1.197, target=1.197×1.15=1.37655, stop_loss=1.197×0.9=1.0773
        assert abs(row[0] - 1.37655) < 0.001  # target_price
        assert abs(row[1] - 1.0773) < 0.001   # stop_loss_price
        assert abs(row[2] - 1.37655) < 0.001  # stop_profit_price（=target）
        assert abs(row[3] - 1.5) < 0.001      # risk_reward_ratio
        assert row[4] == 15                   # max_hold_days

    def test_backfill_writes_audit_log(self, isolated_db_with_buy_trade):
        """回填写 audit_log（is_historical_backfill=1）"""
        db_path, _ = isolated_db_with_buy_trade
        mig.backfill_trade_target_stop()

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT action, code, detail FROM audit_log WHERE action='is_historical_backfill=1'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "is_historical_backfill=1"
        assert rows[0][1] == "515050"
        assert "target=" in rows[0][2]

    def test_backfill_idempotent_on_repeated_run(self, isolated_db_with_buy_trade):
        """重复回填不重复更新（target_price 已非 NULL 跳过）"""
        db_path, _ = isolated_db_with_buy_trade
        count1 = mig.backfill_trade_target_stop()
        count2 = mig.backfill_trade_target_stop()
        assert count1 == 1
        assert count2 == 0

    def test_backfill_skips_is_real_0(self, monkeypatch, tmp_path):
        """is_real=0 的 buy 不回填（按规则 36 is_real 纪律）"""
        db_path = tmp_path / "test_skip.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, code TEXT, name TEXT, action TEXT,
                price REAL, quantity INTEGER, amount REAL, reason TEXT,
                is_real INTEGER, target_price REAL
            );
        """)
        # 插 1 笔 is_real=0 buy
        conn.execute(
            "INSERT INTO trade_history (date, code, name, action, price, quantity, amount, is_real) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-06-01", "510300", "test", "buy", 1.0, 100, 100, 0),
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(mig, "DB_PATH", db_path)
        count = mig.backfill_trade_target_stop()
        assert count == 0
