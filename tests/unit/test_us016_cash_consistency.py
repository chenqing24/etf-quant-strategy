#!/usr/bin/env python3
"""US-016 单元测试: 现金一致性契约

按 SOUL 规则 15: 事实源是 trade_history, etf_performance.json 是缓存
按 SOUL 规则 14: 旧模块必须有回归测试
本测试: 验证 recompute_cash() 与 trade_history 算出的 cash 完全一致
       验证 record_buy/record_sell 后 cash 立即正确
       验证 etf_performance.json 不被错误覆盖
"""
import os
import sys
import json
import sqlite3
import tempfile
import shutil
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_tracker():
    """隔离的 TradeTracker（用临时 db + performance file）"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'etf.db')

    # 建最小 schema
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
        CREATE TABLE positions (
            code TEXT PRIMARY KEY,
            name TEXT, entry_date TEXT, entry_price REAL,
            quantity INTEGER, current_price REAL, pnl_pct REAL,
            hold_days INTEGER, status TEXT, score INTEGER,
            is_real INTEGER, legacy_holding INTEGER,
            is_reference INTEGER, updated_at TEXT
        );
    """)
    conn.close()

    # 创建 performance file
    perf_file = os.path.join(temp_dir, 'etf_performance.json')
    with open(perf_file, 'w') as f:
        json.dump({
            'trades': [],
            'positions': [],
            'performance': {
                'initial_capital': 20000,
                'current_capital': 20000,
                'total_pnl': 0,
                'total_trades': 0,
                'win_rate': 0,
            }
        }, f)

    from src.trade.tracker import TradeTracker
    tracker = TradeTracker(temp_dir)
    tracker.db_path = db_path
    tracker.performance_file = perf_file
    tracker._conn = None  # 强制重建连接

    yield tracker, db_path, perf_file, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestUS016CashConsistency:
    """US-016: 现金 = trade_history 重算结果"""

    def test_cash_after_no_trades_equals_initial(self, isolated_tracker):
        """零交易时 cash = initial_capital"""
        tracker, _, _, _ = isolated_tracker
        cash = tracker.recompute_cash()
        assert cash == 20000, f"cash {cash} != 20000"

    def test_cash_after_buy_decreases(self, isolated_tracker):
        """买入后 cash 减少"""
        tracker, _, _, _ = isolated_tracker
        tracker.record_buy(code='159919', name='测试ETF',
                           price=1.0, quantity=1000, is_real=0)
        cash = tracker.recompute_cash()
        assert cash == 19000, f"cash {cash} != 20000 - 1000 = 19000"

    def test_cash_after_buy_sell_cycle(self, isolated_tracker):
        """买卖循环后 cash 正确"""
        tracker, _, _, _ = isolated_tracker
        # 买入 1000股 @1.0
        tracker.record_buy(code='159919', name='测试ETF',
                           price=1.0, quantity=1000, is_real=0)
        # 卖出 1000股 @1.2 (盈利 200)
        tracker.record_sell(code='159919', price=1.2, actual_pnl=200,
                            quantity=1000, is_real=0)
        cash = tracker.recompute_cash()
        # cash = 20000 - 1000 + 1200 = 20200
        assert cash == 20200, f"cash {cash} != 20000 - 1000 + 1200 = 20200"

    def test_cash_with_real_production_data(self, isolated_tracker):
        """真实生产数据验证（已知预期值）

        基于 2026-06-04 真实 trade_history 计算:
        - 20000 - 5879.7 (买159611 4700股) - 2319.9 (加仓) - 3112.2 (买515050) - 7609 (买512480)
        + 5719.9 (卖159611 4700股) + 2371.2 (卖159611 1900股)
        = 9170.3
        """
        tracker, db_path, _, _ = isolated_tracker
        # 写入真实交易
        conn = sqlite3.connect(db_path)
        trades = [
            ('2026-06-01', '159611', '电力ETF广发', 'buy',  1.251, 4700, 5879.7),
            ('2026-06-02', '515050', '通信ETF华夏', 'buy',  1.197, 2600, 3112.2),
            ('2026-06-03', '159611', '电力ETF广发', 'buy',  1.221, 1900, 2319.9),
            ('2026-06-03', '159611', '电力ETF广发', 'sell', 1.217, 4700, 5719.9),
            ('2026-06-04', '159611', '电力ETF广发', 'sell', 1.248, 1900, 2371.2),
            ('2026-06-04', '512480', '半导体ETF',  'buy',  2.174, 3500, 7609.0),
        ]
        for date, code, name, action, price, qty, amount in trades:
            conn.execute(
                "INSERT INTO trade_history (date, code, name, action, price, quantity, amount, is_real) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (date, code, name, action, price, qty, amount)
            )
        conn.commit()
        conn.close()

        cash = tracker.recompute_cash()
        assert abs(cash - 9170.3) < 0.01, f"cash {cash} != 9170.3 (期望值)"

    def test_cash_not_use_dirty_positions_quantity(self, isolated_tracker):
        """cash 不应受 positions 表脏数据影响"""
        tracker, db_path, _, _ = isolated_tracker
        # 写入 trade_history 一笔 buy
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO trade_history (date, code, name, action, price, quantity, amount, is_real) "
            "VALUES ('2026-06-01', '159611', 'X', 'buy', 1.0, 1000, 1000, 1)"
        )
        # 同时在 positions 表写入不一致的 quantity（5000 假数据）
        conn.execute(
            "INSERT INTO positions (code, name, quantity, entry_price, status) "
            "VALUES ('159611', 'X', 5000, 1.0, 'HOLDING')"
        )
        conn.commit()
        conn.close()

        cash = tracker.recompute_cash()
        # cash 应该 = 20000 - 1000 = 19000 (基于 trade_history)
        # 不应该 = 20000 - 5000 = 15000 (基于 positions 表)
        assert cash == 19000, f"cash {cash} 受 positions 表污染，应为 19000"

    def test_performance_file_not_overwritten_dirty(self, isolated_tracker):
        """recompute_cash() 不应把错误数据写回 etf_performance.json"""
        tracker, _, perf_file, _ = isolated_tracker
        # 故意把 performance file 写脏成 22371.2
        with open(perf_file, 'w') as f:
            json.dump({
                'trades': [],
                'positions': [],
                'performance': {
                    'initial_capital': 20000,
                    'current_capital': 22371.2,  # 错误值
                    'total_pnl': 0,
                    'total_trades': 0,
                    'win_rate': 0,
                }
            }, f)

        # 写入一笔交易
        tracker.record_buy(code='159919', name='测试ETF',
                           price=1.0, quantity=1000, is_real=0)

        # 调用 recompute_cash 后，performance file 不应保留 22371.2
        tracker.recompute_cash()
        with open(perf_file) as f:
            data = json.load(f)
        perf = data.get('performance', {})
        # current_capital 应该是 19000，不是 22371.2
        # 允许字段缺失（如果不再写 current_capital），但不允许错误值
        if 'current_capital' in perf:
            assert perf['current_capital'] != 22371.2, \
                f"performance.current_capital 仍为脏值 22371.2"


class TestUS016DataConsistency:
    """US-016: 多数据源一致性"""

    def test_daily_mode_total_asset_equals_eval_report(self, isolated_tracker):
        """daily 模式日志的"总资产"必须 == eval 报告的"总资产"

        这是数据契约：同一个时间点，两条数据流必须收敛
        """
        tracker, db_path, perf_file, _ = isolated_tracker
        # 写入生产 trade_history
        conn = sqlite3.connect(db_path)
        trades = [
            ('2026-06-02', '515050', '通信ETF华夏', 'buy',  1.197, 2600, 3112.2),
            ('2026-06-04', '512480', '半导体ETF',  'buy',  2.174, 3500, 7609.0),
        ]
        for date, code, name, action, price, qty, amount in trades:
            conn.execute(
                "INSERT INTO trade_history (date, code, name, action, price, quantity, amount, is_real) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (date, code, name, action, price, qty, amount)
            )
        conn.commit()
        conn.close()

        # 模拟 daily 模式调用路径
        cash = tracker.recompute_cash()
        holdings = tracker.get_holdings()
        market_value = sum(h.entry_price * h.quantity for h in holdings)  # 简化用 entry_price
        daily_total = cash + market_value

        # 模拟 eval 报告调用路径
        perf = tracker.get_performance_summary()
        eval_total = perf.get('current_capital', 0) + market_value

        # 两个必须相等
        assert abs(daily_total - eval_total) < 0.01, \
            f"daily 总资产 {daily_total} != eval 总资产 {eval_total}"
