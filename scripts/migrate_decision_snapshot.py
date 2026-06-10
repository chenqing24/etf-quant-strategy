#!/usr/bin/env python3
"""决策快照迁移脚本（US-003）

功能：
    Step 1: 读 etf_data_live/decision_snapshot.json → INSERT decision_snapshot 表
    Step 2: 回填 is_real=1 的 buy 交易的 target/stop 字段（按 utils/config.py 默认值）
    Step 3: 写 audit_log（is_historical_backfill=1）标记这是历史回填

用法：
    python scripts/migrate_decision_snapshot.py

幂等性：
    - 重复执行不重复插入（按 snapshot_time 检查）
    - 重复执行不重复回填（按 target_price IS NULL 检查）
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 路径注入
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "etf_data_live" / "etf.db"
JSON_PATH = PROJECT_ROOT / "etf_data_live" / "decision_snapshot.json"

# 按 src/utils/config.py StrategyConfig 默认值（规则 19 黑名单：保守默认）
# 这里用 StrategyConfig 的 stop_gain=0.15 / stop_loss=-0.10 / max_hold_days=15
DEFAULT_STOP_GAIN = 0.15
DEFAULT_STOP_LOSS = -0.10
DEFAULT_MAX_HOLD_DAYS = 15
DEFAULT_RISK_REWARD = abs(DEFAULT_STOP_GAIN / DEFAULT_STOP_LOSS)  # 1.5


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def migrate_snapshot_from_json() -> str | None:
    """读 decision_snapshot.json → INSERT decision_snapshot

    幂等：按 snapshot_time 检查，已存在则跳过。

    Returns:
        snapshot_id (str) 成功；None 跳过/失败
    """
    if not JSON_PATH.exists():
        print(f"⚠️  {JSON_PATH} 不存在，跳过")
        return None

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        d = json.load(f)

    snapshot_time = d.get("snapshot_time", "")
    if not snapshot_time:
        print("⚠️  JSON 中无 snapshot_time 字段，跳过")
        return None

    conn = _conn()
    try:
        # 幂等检查
        cur = conn.execute(
            "SELECT COUNT(*) FROM decision_snapshot WHERE snapshot_time=?",
            (snapshot_time,),
        )
        if cur.fetchone()[0] > 0:
            print(f"⏭️  跳过（已存在）: snapshot_time={snapshot_time}")
            return None

        # 生成历史 snapshot_id（标记是迁移数据）
        version_tag = d.get("snapshot_version", "v1")[:6].replace(".", "")
        sid = (
            f"snap-historical-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            f"-{version_tag}"
        )

        # 提取嵌套字段
        model_info = d.get("model_info", {}) or {}
        exp_info = model_info.get("experiment_info", {}) or {}

        # INSERT
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
                sid, snapshot_time, d.get("trigger", "cron_daily_1425"),
                model_info.get("name", ""), exp_info.get("version", ""),
                "",  # strategy_name (JSON 中无此字段)
                json.dumps(d.get("strategy_config", {}), ensure_ascii=False),
                json.dumps(d.get("evaluation_metrics", {}), ensure_ascii=False),
                json.dumps(d.get("top_5_models", []), ensure_ascii=False),
                json.dumps(d.get("today_top_10", []), ensure_ascii=False),
                json.dumps(d.get("backtest_last_10_trades", []), ensure_ascii=False),
                "",  # market_regime (历史数据无此字段)
                "",  # reasoning (历史数据无此字段)
                None, None, None, None,  # target/stop/risk_reward 派生字段历史无
                15,  # expected_hold_days 默认
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        print(f"✅  迁移: {sid} (snapshot_time={snapshot_time})")
        return sid
    finally:
        conn.close()


def backfill_trade_target_stop() -> int:
    """回填 is_real=1 且 action='buy' 且 target_price IS NULL 的交易

    字段：
        - target_price: price × (1 + 0.15)
        - stop_loss_price: price × (1 - 0.10)
        - stop_profit_price: target_price (与 target_price 同值，规则 17 兼容)
        - risk_reward_ratio: 1.5
        - max_hold_days: 15

    幂等：WHERE target_price IS NULL 保证只回填一次。

    Returns:
        回填笔数
    """
    conn = _conn()
    try:
        # 1. 找出待回填交易
        cur = conn.execute(
            """
            SELECT id, code, date, price, quantity
            FROM trade_history
            WHERE is_real = 1 AND action = 'buy' AND target_price IS NULL
            """
        )
        rows = cur.fetchall()
        if not rows:
            print("⏭️  无需回填（is_real=1 buy 已全部有 target_price）")
            return 0

        count = 0
        for r in rows:
            tid, code, date_, price, quantity = r
            target = round(price * (1 + DEFAULT_STOP_GAIN), 4)
            stop_loss = round(price * (1 + DEFAULT_STOP_LOSS), 4)
            stop_profit = target  # 规则 17：止盈即目标价
            risk_reward = DEFAULT_RISK_REWARD

            conn.execute(
                """
                UPDATE trade_history
                SET target_price=?, stop_loss_price=?, stop_profit_price=?,
                    risk_reward_ratio=?, max_hold_days=?
                WHERE id=? AND is_real=1 AND target_price IS NULL
                """,
                (target, stop_loss, stop_profit, risk_reward, DEFAULT_MAX_HOLD_DAYS, tid),
            )

            # audit_log: 标 is_historical_backfill=1
            # 实际 schema: id/timestamp/action/code/from_state/to_state/detail/created_at
            # 把"事件类型"放进 action, "详情"放进 detail
            conn.execute(
                """
                INSERT INTO audit_log (timestamp, action, code, detail, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    "is_historical_backfill=1",
                    code,
                    (
                        f"migrate_decision_snapshot: id={tid} {date_} @ {price} | "
                        f"target={target}, stop_loss={stop_loss}, stop_profit={stop_profit}, "
                        f"risk_reward={risk_reward}, max_hold={DEFAULT_MAX_HOLD_DAYS}"
                    ),
                    datetime.now().isoformat(),
                ),
            )
            count += 1

        conn.commit()
        print(f"✅  回填 {count} 笔 is_real=1 buy 交易（target/stop）")
        return count
    finally:
        conn.close()


def main() -> int:
    """主入口"""
    print("=" * 60)
    print("US-003 决策快照迁移")
    print("=" * 60)
    print()
    print("=== Step 1: 迁 decision_snapshot.json → db ===")
    sid = migrate_snapshot_from_json()
    print()
    print("=== Step 2: 回填 is_real=1 buy 交易 target/stop ===")
    count = backfill_trade_target_stop()
    print()
    print("=" * 60)
    print(f"完成: snapshot={'已迁移' if sid else '跳过'}, backfill={count} 笔")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
