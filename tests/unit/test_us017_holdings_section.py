#!/usr/bin/env python3
"""US-017 单元测试: 报告持仓管理段

3 个问题:
1. 持仓止盈止损缺失
2. 持仓评分缺失
3. 市场环境含义模糊（"中性"、"符合条件 2 只"）

设计文档: memory/2026-06-04.md (US-017 Phase 3 v1.0)

测试策略: TDD 红 → 绿
"""
import os
import sys
import json
import sqlite3
import tempfile
import shutil
import re
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────
# 测试数据 fixture
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_env(tmp_path):
    """隔离环境: 临时 db + 临时 core 池"""
    db_path = str(tmp_path / "etf.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, code TEXT, name TEXT, action TEXT,
            price REAL, quantity INTEGER, amount REAL,
            reason TEXT, emotion TEXT, session TEXT,
            signal_time TEXT, signal_price REAL, signal_rsi REAL,
            signal_adx REAL, signal_score INTEGER,
            realtime_price REAL, price_deviation REAL,
            rsi_14 REAL, day_change_pct REAL, score INTEGER,
            expected_return REAL, actual_pnl REAL, note TEXT,
            trade_time TEXT, is_real INTEGER, is_paper INTEGER,
            model TEXT, strategy TEXT, evaluation TEXT, snapshot_ref TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE etf_names (
            code TEXT PRIMARY KEY, name TEXT, tradable INTEGER, pool_role TEXT
        );
        CREATE TABLE positions (
            code TEXT PRIMARY KEY,
            name TEXT, entry_date TEXT, entry_price REAL,
            quantity INTEGER, current_price REAL, pnl_pct REAL,
            hold_days INTEGER, status TEXT, score INTEGER,
            is_real INTEGER, legacy_holding INTEGER,
            is_reference INTEGER, updated_at TEXT
        );
    """)
    # core 池 14 只
    core_codes = ['512170', '512200', '512400', '512480', '512660', '512800',
                  '512880', '512980', '515050', '515070', '515650', '515790',
                  '520900', '588000']
    name_map = {
        '512170': '医疗ETF华宝', '512200': '房地产ETF南方', '512400': '有色金属ETF南方',
        '512480': '国联安半导体ETF', '512660': '军工ETF国泰', '512800': '银行ETF华宝',
        '512880': '证券ETF国泰', '512980': '传媒ETF广发', '515050': '通信ETF华夏',
        '515070': '人工智能ETF华夏', '515650': '消费50ETF富国', '515790': '光伏ETF华泰柏瑞',
        '520900': '港股通红利ETF广发', '588000': '科创50ETF华夏',
    }
    for code in core_codes:
        conn.execute(
            "INSERT INTO etf_names (code, name, tradable, pool_role) VALUES (?, ?, 1, 'core')",
            (code, name_map[code])
        )
    # 持仓 2 只: 515050 (3天前建仓) + 512480 (今天建仓)
    conn.execute("""INSERT INTO trade_history
        (date, code, name, action, price, quantity, amount, reason, emotion,
         is_real, is_paper, trade_time, created_at)
        VALUES (?, ?, ?, 'buy', ?, ?, ?, ?, ?, 1, 0, ?, ?)""",
        ('2026-06-02', '515050', '通信ETF华夏', 1.197, 2600, 3112.2, 'MA20突破', 'calm',
         '2026-06-02T14:30:00', '2026-06-02 14:30:00'))
    conn.execute("""INSERT INTO trade_history
        (date, code, name, action, price, quantity, amount, reason, emotion,
         is_real, is_paper, trade_time, created_at)
        VALUES (?, ?, ?, 'buy', ?, ?, ?, ?, ?, 1, 0, ?, ?)""",
        ('2026-06-04', '512480', '国联安半导体ETF', 2.174, 3500, 7609.0, '低开加仓', 'fomo',
         '2026-06-04T14:30:00', '2026-06-04 14:30:00'))
    conn.commit()
    conn.close()
    return {"db_path": db_path, "tmp_path": tmp_path, "core_codes": core_codes}


# ─────────────────────────────────────────────────────────────
# T1: 持仓管理段存在
# ─────────────────────────────────────────────────────────────

def test_holdings_section_exists(isolated_env):
    """报告必须包含【持仓管理】段"""
    from src.analysis.report_generator import ETFReportGenerator
    gen = ETFReportGenerator(data_dir=str(isolated_env["tmp_path"]))
    report = gen.generate_report(capital=20000)
    assert "【持仓管理】" in report, "报告缺少【持仓管理】段"


# ─────────────────────────────────────────────────────────────
# T2: 持仓止盈止损显示
# ─────────────────────────────────────────────────────────────

def test_holdings_stop_profit_loss_displayed(isolated_env):
    """每只持仓必须显示止盈价/止损价"""
    from src.analysis.report_generator import ETFReportGenerator
    gen = ETFReportGenerator(data_dir=str(isolated_env["tmp_path"]))
    report = gen.generate_report(capital=20000)
    # 515050: 成本 1.197, 止盈 1.317 (+10%), 止损 1.125 (-6%)
    assert "止盈1.317" in report, "515050 止盈价缺失或错误"
    assert "止损1.125" in report, "515050 止损价缺失或错误"
    # 512480: 成本 2.174, 止盈 2.391 (+10%), 止损 2.044 (-6%)
    assert "止盈2.391" in report, "512480 止盈价缺失或错误"
    assert "止损2.044" in report, "512480 止损价缺失或错误"


# ─────────────────────────────────────────────────────────────
# T3: 持仓评分显示
# ─────────────────────────────────────────────────────────────

def test_holdings_score_displayed(isolated_env):
    """每只持仓必须显示评分"""
    from src.analysis.report_generator import ETFReportGenerator
    gen = ETFReportGenerator(data_dir=str(isolated_env["tmp_path"]))
    report = gen.generate_report(capital=20000)
    # 持仓段每行必须有"分X"模式
    holdings_section = re.search(r"【持仓管理】.*?(?=\n={5,}|\Z)", report, re.DOTALL)
    assert holdings_section, "【持仓管理】段不存在"
    assert re.search(r"分\d+", holdings_section.group()), "持仓段缺少评分"


# ─────────────────────────────────────────────────────────────
# T4: 持仓动作标签
# ─────────────────────────────────────────────────────────────

def test_holdings_action_label(isolated_env):
    """持仓必须显示动作标签 (🆕刚买入/🟢持有/🟡接近止盈/🔴触发止损/⏰到期)"""
    from src.analysis.report_generator import ETFReportGenerator
    gen = ETFReportGenerator(data_dir=str(isolated_env["tmp_path"]))
    report = gen.generate_report(capital=20000)
    holdings_section = re.search(r"【持仓管理】.*?(?=\n={5,}|\Z)", report, re.DOTALL)
    assert holdings_section, "【持仓管理】段不存在"
    # 至少包含 1 个动作 emoji
    actions = ['🆕', '🟢', '🟡', '🔴', '⏰']
    assert any(a in holdings_section.group() for a in actions), \
        f"持仓段缺少动作标签，应包含 {actions} 之一"


# ─────────────────────────────────────────────────────────────
# T5: 市场环境 8 状态细分（不是"中性"）
# ─────────────────────────────────────────────────────────────

def test_market_regime_8_states_not_neutral(isolated_env):
    """【市场环境】段必须显示 US-013 8 状态细分之一, 不是"中性" """
    from src.analysis.report_generator import ETFReportGenerator
    gen = ETFReportGenerator(data_dir=str(isolated_env["tmp_path"]))
    report = gen.generate_report(capital=20000)
    # 提取【综合评估】或市场相关段
    # 不应出现孤立的"市场环境: 中性"
    assert not re.search(r"市场环境:\s*中性", report), \
        "市场环境仍是模糊'中性', 应改为 8 状态细分"
    # 应有 8 状态之一
    regime_keywords = ['初升', '上升中', '末升', '初降', '下降中', '末降',
                       '震荡偏强', '震荡偏弱', '反转点', '暴跌']
    assert any(k in report for k in regime_keywords), \
        f"市场环境缺少 8 状态细分标签，应包含 {regime_keywords} 之一"


# ─────────────────────────────────────────────────────────────
# T6: 评分阈值显式说明
# ─────────────────────────────────────────────────────────────

def test_qualified_threshold_explicit(isolated_env):
    """报告必须显式说明"符合买入条件"的评分阈值（≥6 分）"""
    from src.analysis.report_generator import ETFReportGenerator
    gen = ETFReportGenerator(data_dir=str(isolated_env["tmp_path"]))
    report = gen.generate_report(capital=20000)
    # 提取"符合买入条件"行
    qualified_line = re.search(r"符合买入条件[（(]?[≥>=]?6\s*分[）)]?.*?只", report)
    assert qualified_line, \
        "评分阈值未显式说明，应写为'符合买入条件（≥6 分）：N 只'"


# ─────────────────────────────────────────────────────────────
# T7: 持仓持有天数
# ─────────────────────────────────────────────────────────────

def test_holdings_hold_days(isolated_env):
    """持仓必须显示持有天数"""
    from src.analysis.report_generator import ETFReportGenerator
    gen = ETFReportGenerator(data_dir=str(isolated_env["tmp_path"]))
    report = gen.generate_report(capital=20000)
    holdings_section = re.search(r"【持仓管理】.*?(?=\n={5,}|\Z)", report, re.DOTALL)
    assert holdings_section, "【持仓管理】段不存在"
    # 至少显示"持X天"
    assert re.search(r"持\d+天", holdings_section.group()), \
        "持仓段缺少持有天数，应为'持X天'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
