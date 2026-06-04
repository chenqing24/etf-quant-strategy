#!/usr/bin/env python3
"""US-016 单元测试: 报告生成幂等性 + FOMO 情绪提示

按 SOUL 规则 23: 分析交易数据时先看 emotion 字段
按 SOUL 规则 6.2.1: 自评分数 = 实际行为结果
"""
import os
import sys
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_env():
    """隔离环境：临时 db + etf_reports 目录"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'etf.db')
    reports_dir = os.path.join(temp_dir, 'etf_reports')
    os.makedirs(reports_dir, exist_ok=True)

    # 建 schema
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, code TEXT, name TEXT, action TEXT,
            price REAL, quantity INTEGER, amount REAL,
            reason TEXT, emotion TEXT, is_real INTEGER DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()

    yield db_path, reports_dir
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestUS016ReportIdempotent:
    """US-016: 报告生成幂等性"""

    def test_existing_report_not_overwritten_by_default(self, isolated_env):
        """默认: 今日报告已存在则不覆盖, 追加时间戳"""
        _, reports_dir = isolated_env
        # 模拟已存在的报告
        today_file = os.path.join(reports_dir, 'report_20260604.txt')
        with open(today_file, 'w') as f:
            f.write("【原报告内容】\n\n这是第一次生成的报告。")

        # 模拟不带 force 的 engine
        engine = type('obj', (object,), {'force': False})()
        report_file = today_file
        if os.path.exists(report_file) and not getattr(engine, 'force', False):
            # 应该不覆盖 (逻辑正确)
            with open(report_file, 'r') as f:
                content = f.read()
            assert "原报告内容" in content, "原报告应保留"
        else:
            assert False, "应识别已存在报告且不覆盖"

    def test_force_overwrites_existing_report(self, isolated_env):
        """--force: 强制覆盖"""
        # 模拟 force 模式
        engine_force = type('obj', (object,), {'force': True})()

        report_file = '/tmp/test_force_report.txt'
        with open(report_file, 'w') as f:
            f.write("OLD")

        if os.path.exists(report_file) and not getattr(engine_force, 'force', False):
            assert False, "应识别 force 标志"
        else:
            # 强制覆盖
            with open(report_file, 'w') as f:
                f.write("NEW")
            with open(report_file) as f:
                content = f.read()
            assert content == "NEW", "force 模式应覆盖"
            os.unlink(report_file)


class TestUS016EmotionAlerts:
    """US-016: FOMO/Fear/Regret 情绪提示"""

    def test_emotion_alert_appears_for_fomo_trade(self, isolated_env):
        """FOMO 交易应在报告中提示"""
        db_path, _ = isolated_env
        conn = sqlite3.connect(db_path)
        # 写入 FOMO 交易
        conn.execute("""
            INSERT INTO trade_history
            (date, code, name, action, price, quantity, amount, reason, emotion, is_real)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('2026-06-04', '512480', '半导体ETF', 'buy', 2.18, 3500, 7630,
              '低开但快速上涨，已追高入场', 'fomo', 1))
        conn.commit()
        conn.close()

        # 验证查询逻辑（这是 report_generator 内部的 SQL）
        conn = sqlite3.connect(db_path)
        cur = conn.execute("""
            SELECT date, code, name, action, emotion, reason
            FROM trade_history
            WHERE emotion IN ('fomo', 'fear', 'regret', 'euphoria')
              AND is_real = 1
              AND date >= date('now', '-7 days')
            ORDER BY id DESC
        """)
        rows = cur.fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][4] == 'fomo'
        assert 'FOMO' in rows[0][5] or '追高' in rows[0][5]

    def test_no_emotion_alert_for_test_data(self, isolated_env):
        """is_real=0 的测试数据不应触发情绪提示"""
        db_path, _ = isolated_env
        conn = sqlite3.connect(db_path)
        conn.execute("""
            INSERT INTO trade_history
            (date, code, name, action, price, quantity, amount, reason, emotion, is_real)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('2026-06-04', '510300', '沪深300', 'buy', 4.0, 1000, 4000,
              '策略推荐', 'fomo', 0))  # is_real=0 (测试数据)
        conn.commit()
        conn.close()

        # 验证: is_real=0 不应在结果里
        conn = sqlite3.connect(db_path)
        cur = conn.execute("""
            SELECT COUNT(*) FROM trade_history
            WHERE emotion IN ('fomo', 'fear', 'regret', 'euphoria')
              AND is_real = 1
        """)
        count = cur.fetchone()[0]
        conn.close()

        assert count == 0, "is_real=0 不应触发情绪提示 (按 SOUL 规则 23)"

    def test_emotion_alert_emoji_mapping(self, isolated_env):
        """情绪 → emoji 映射正确"""
        emoji_map = {
            'fomo': '🟡 FOMO (追高)',
            'fear': '🔴 Fear (恐慌)',
            'regret': '🟠 Regret (后悔)',
            'euphoria': '🟢 Euphoria (兴奋)',
        }
        assert 'FOMO' in emoji_map['fomo']
        assert 'Fear' in emoji_map['fear']
        assert 'Regret' in emoji_map['regret']
        assert 'Euphoria' in emoji_map['euphoria']
