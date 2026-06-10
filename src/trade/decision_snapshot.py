#!/usr/bin/env python3
"""决策快照模块（US-003）

按规则 19 Single Source of Truth：决策快照从 etf_data_live/decision_snapshot.json
迁到 SQLite decision_snapshot 表。

业界参考：MiFID II（决策可追溯）/ QuantConnect Lean Insight / CQRS Event Sourcing
"""
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# DB 路径（与 src/constants.py DB_PATH 一致）
DB_PATH = Path(__file__).parent.parent.parent / "etf_data_live" / "etf.db"


class DecisionSnapshot:
    """决策快照 CRUD（US-003）

    设计原则：
    - create() 自动生成 snapshot_id = snap-{ts}-{uuid6}
    - get() 返回字典（含 JSON 字段反序列化）
    - list_by_time_range() 用于报告生成
    - 所有方法独立打开/关闭连接（不持有状态）
    """

    @staticmethod
    def _conn() -> sqlite3.Connection:
        return sqlite3.connect(DB_PATH)

    @staticmethod
    def _make_id(snapshot_time: str) -> str:
        """生成 snapshot_id：snap-{ts}-{uuid6}

        snapshot_time 形如 '2026-06-01T14:17:39.876852'
        处理后取前 15 字符（YYYYMMDDHHMMSS）
        """
        ts = (snapshot_time
              .replace(":", "")
              .replace("-", "")
              .replace("T", "-")
              .replace("Z", "")[:15])
        return f"snap-{ts}-{uuid.uuid4().hex[:6]}"

    @staticmethod
    def create(
        snapshot_time: str,
        trigger: str = "daily",
        model_name: str = "",
        model_version: str = "",
        strategy_name: str = "",
        config: Optional[Dict[str, Any]] = None,
        evaluation: Optional[Dict[str, Any]] = None,
        factor_breakdown: Optional[List[Any]] = None,
        today_top_10: Optional[List[Any]] = None,
        backtest_last_10: Optional[List[Any]] = None,
        market_regime: str = "",
        reasoning: str = "",
        target_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        stop_profit_price: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None,
        expected_hold_days: int = 15,
    ) -> str:
        """创建决策快照，返回 snapshot_id

        Args:
            snapshot_time: ISO8601 时间
            trigger: 触发原因（cron_daily_1425 / manual / backtest）
            model_name: 模型名
            model_version: 模型版本
            strategy_name: 策略名
            config: 策略配置 dict
            evaluation: 评价指标 dict
            factor_breakdown: 因子分解 list
            today_top_10: 当日 Top 10 list
            backtest_last_10: 回测最近 10 笔 list
            market_regime: 市场状态（trend_up / range_bound / trend_down / crash）
            reasoning: 决策理由
            target_price: 目标价
            stop_loss_price: 止损价
            stop_profit_price: 止盈价
            risk_reward_ratio: 风险回报比
            expected_hold_days: 预期持仓天数

        Returns:
            snapshot_id (str)
        """
        sid = DecisionSnapshot._make_id(snapshot_time)
        conn = DecisionSnapshot._conn()
        try:
            conn.execute(
                """
                INSERT INTO decision_snapshot (
                    snapshot_id, snapshot_time, trigger, model_name, model_version,
                    strategy_name, config_json, evaluation_json, factor_breakdown_json,
                    today_top_10_json, backtest_last_10_json, market_regime, reasoning,
                    target_price, stop_loss_price, stop_profit_price, risk_reward_ratio,
                    expected_hold_days, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid, snapshot_time, trigger, model_name, model_version, strategy_name,
                    json.dumps(config or {}, ensure_ascii=False),
                    json.dumps(evaluation or {}, ensure_ascii=False),
                    json.dumps(factor_breakdown or {}, ensure_ascii=False),
                    json.dumps(today_top_10 or [], ensure_ascii=False),
                    json.dumps(backtest_last_10 or [], ensure_ascii=False),
                    market_regime, reasoning,
                    target_price, stop_loss_price, stop_profit_price, risk_reward_ratio,
                    expected_hold_days, datetime.now().isoformat(),
                ),
            )
            conn.commit()
            logger.info(f"决策快照已创建: {sid}")
            return sid
        finally:
            conn.close()

    @staticmethod
    def get(snapshot_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 查询完整快照（返回 dict，None 表示不存在）"""
        conn = DecisionSnapshot._conn()
        try:
            cur = conn.execute(
                "SELECT * FROM decision_snapshot WHERE snapshot_id=?",
                (snapshot_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        finally:
            conn.close()

    @staticmethod
    def get_by_time(snapshot_time: str) -> Optional[Dict[str, Any]]:
        """按 snapshot_time 查询（迁移脚本幂等检查用）"""
        conn = DecisionSnapshot._conn()
        try:
            cur = conn.execute(
                "SELECT * FROM decision_snapshot WHERE snapshot_time=? LIMIT 1",
                (snapshot_time,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        finally:
            conn.close()

    @staticmethod
    def list_by_time_range(
        start_time: str, end_time: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """按时间范围查询（报告生成用）"""
        conn = DecisionSnapshot._conn()
        try:
            cur = conn.execute(
                """
                SELECT * FROM decision_snapshot
                WHERE snapshot_time BETWEEN ? AND ?
                ORDER BY snapshot_time DESC
                LIMIT ?
                """,
                (start_time, end_time, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def count() -> int:
        """统计快照总数（测试用）"""
        conn = DecisionSnapshot._conn()
        try:
            return conn.execute("SELECT COUNT(*) FROM decision_snapshot").fetchone()[0]
        finally:
            conn.close()
