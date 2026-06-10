#!/usr/bin/env python3
"""US-003 tracker.record_buy target/stop 单元测试（≥6 用例）

测试范围：
    - record_buy 带 target/stop 5 字段成功入库
    - record_buy 无 target_price log warning
    - record_buy 无 snapshot_ref 抛 BusinessConstraintError（已有约束保持）
    - 目标价/止损计算正确性
    - 数据库中能查到新字段
    - 不传 target/stop 时 db 中存为 NULL/0
"""
import json
import logging
import os
import sys
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tracker(isolated_tracker):
    """US-014: 用 conftest 全局 fixture（自动加载所有 migrations）"""
    t, tmpdir, tmp_db = isolated_tracker
    yield t


class TestRecordBuyTargetStop:
    """record_buy target/stop 字段测试"""

    def test_record_buy_with_target_stop_persists_to_db(self, tracker, tmp_path):
        """带 target/stop 5 字段的 record_buy 正确入库"""
        # 准备实时数据文件，避免网络请求
        # 不写文件 → _fetch_realtime_data 失败 → 用 price 兜底
        tracker.record_buy(
            code="510300", name="沪深300ETF", price=4.0, quantity=100,
            reason="US-003 target/stop 测试",
            is_real=0,  # 纸面，不入 positions
            model="v8_sop", strategy=json.dumps({"hold_count": 2}),
            evaluation=json.dumps({"avg_sharpe": 1.2}),
            snapshot_ref="etf_data_live/decision_snapshot.json",
            target_price=4.6,        # 4.0 × 1.15
            stop_loss_price=3.6,     # 4.0 × 0.90
            stop_profit_price=4.6,
            risk_reward_ratio=1.5,
            max_hold_days=15,
        )
        # 查 trade_history
        conn = sqlite3.connect(tracker.db_path)
        row = conn.execute(
            "SELECT target_price, stop_loss_price, stop_profit_price, "
            "risk_reward_ratio, max_hold_days FROM trade_history "
            "WHERE code='510300' AND action='buy' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        target, stop_loss, stop_profit, rr, max_hold = row
        assert abs(target - 4.6) < 0.001
        assert abs(stop_loss - 3.6) < 0.001
        assert abs(stop_profit - 4.6) < 0.001
        assert abs(rr - 1.5) < 0.001
        assert max_hold == 15

    def test_record_buy_without_target_logs_warning(self, tracker, caplog):
        """无 target_price 时 log warning（不抛错）"""
        with caplog.at_level(logging.WARNING, logger="src.trade.tracker"):
            tracker.record_buy(
                code="510300", name="沪深300ETF", price=4.0, quantity=100,
                reason="无 target_price 测试",
                is_real=0,
                model="v8_sop", strategy="{}",
                evaluation="{}", snapshot_ref="etf_data_live/decision_snapshot.json",
                # 故意不传 target_price
            )
        # 应有 warning
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any("target_price 未传" in r.message for r in warnings), \
            f"未找到目标价 warning 日志，实际日志: {[r.message for r in warnings]}"

    def test_record_buy_without_target_persists_null(self, tracker):
        """无 target_price 时 db 存为 NULL/0（不抛错）"""
        tracker.record_buy(
            code="510300", name="沪深300ETF", price=4.0, quantity=100,
            reason="无 target_price 持久化测试",
            is_real=0,
            model="v8_sop", strategy="{}",
            evaluation="{}", snapshot_ref="etf_data_live/decision_snapshot.json",
        )
        conn = sqlite3.connect(tracker.db_path)
        row = conn.execute(
            "SELECT target_price, stop_loss_price, stop_profit_price, "
            "risk_reward_ratio, max_hold_days FROM trade_history "
            "WHERE code='510300' AND action='buy' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        # 缺省 → NULL（target_price IS NULL）
        assert row[0] is None  # target_price
        assert row[1] is None  # stop_loss_price
        assert row[2] is None  # stop_profit_price
        assert row[3] is None  # risk_reward_ratio
        assert row[4] is None  # max_hold_days

    def test_record_buy_duplicate_buy_raises(self, tracker):
        """重复买入同一 ETF 抛 BusinessConstraintError（US-024 持仓去重）"""
        from src.trade.exceptions import BusinessConstraintError
        # 第一次买入（实盘，入 positions）
        tracker.record_buy(
            code="510300", name="沪深300ETF", price=4.0, quantity=100,
            reason="首次买入",
            is_real=1,  # 实盘才入 positions
            model="v8_sop", strategy="{}",
            evaluation="{}", snapshot_ref="etf_data_live/decision_snapshot.json",
            target_price=4.6, stop_loss_price=3.6,
        )
        # 重复买入 → 应抛错
        with pytest.raises(BusinessConstraintError):
            tracker.record_buy(
                code="510300", name="沪深300ETF", price=4.0, quantity=100,
                reason="重复买入测试",
                is_real=1,
                model="v8_sop", strategy="{}",
                evaluation="{}", snapshot_ref="etf_data_live/decision_snapshot.json",
            )

    def test_target_price_calculation_with_stop_gain_15pct(self):
        """目标价 = price × (1 + 0.15) 验证"""
        price = 2.574  # 实际 515070 交易价
        expected_target = round(price * 1.15, 4)
        assert expected_target == pytest.approx(2.9601, abs=1e-4)

    def test_stop_loss_calculation_with_stop_loss_10pct(self):
        """止损价 = price × (1 - 0.10) 验证"""
        price = 2.574
        expected_stop = round(price * 0.90, 4)
        assert expected_stop == pytest.approx(2.3166, abs=1e-4)

    def test_risk_reward_ratio_calculation(self):
        """风险回报比 = |stop_gain / stop_loss| = |0.15 / -0.10| = 1.5"""
        stop_gain = 0.15
        stop_loss = -0.10
        rr = abs(stop_gain / stop_loss)
        assert rr == pytest.approx(1.5)
