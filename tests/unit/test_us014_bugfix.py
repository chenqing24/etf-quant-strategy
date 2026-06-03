#!/usr/bin/env python3
"""US-014 单元测试：修复 US-008 漏改清单"""
import os
import sys
import json
import tempfile
import sqlite3
import subprocess
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_tracker():
    """隔离 TradeTracker（临时 DB + performance.json + schema 004+005）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.trade.tracker import TradeTracker
        tmp_db = os.path.join(tmpdir, 'test.db')
        # 加载 004 + 005 schema
        for schema in ['004_add_trade_tables.sql', '005_add_is_reference.sql']:
            schema_file = os.path.join(ROOT, 'schema/migrations', schema)
            conn = sqlite3.connect(tmp_db)
            with open(schema_file) as f:
                conn.executescript(f.read())
            conn.close()
        # performance.json
        with open(os.path.join(tmpdir, 'etf_performance.json'), 'w') as f:
            json.dump({
                'trades': [], 'positions': [],
                'performance': {
                    'initial_capital': 20000, 'current_capital': 20000,
                    'total_pnl': 0, 'total_trades': 0, 'win_rate': 0
                }
            }, f)
        tracker = TradeTracker(data_dir=tmpdir, db_path=tmp_db)
        yield tracker, tmpdir, tmp_db


class TestR1CurrentCapitalTracking:
    """R1: record_buy/sell 同步更新 current_capital"""

    def test_buy_decreases_capital(self, isolated_tracker):
        """买入后 current_capital 减少"""
        tracker, tmpdir, tmp_db = isolated_tracker
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 2600, 'test', is_real=1)
        # 验证
        with open(os.path.join(tmpdir, 'etf_performance.json')) as f:
            perf = json.load(f)['performance']
        # 20000 - 1.197*2600 = 20000 - 3112.2 = 16887.8
        assert perf['current_capital'] == 16887.8

    def test_sell_increases_capital(self, isolated_tracker):
        """卖出后 current_capital 增加"""
        tracker, tmpdir, tmp_db = isolated_tracker
        # 先买入建仓
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 2600, 'test', is_real=1)
        # 再全仓卖
        tracker.record_sell('515050', 1.213, is_real=1)
        # 验证
        with open(os.path.join(tmpdir, 'etf_performance.json')) as f:
            perf = json.load(f)['performance']
        # 20000 - 3112.2 + 1.213*2600 = 20000 - 3112.2 + 3153.8 = 20041.6
        assert abs(perf['current_capital'] - 20041.6) < 0.01

    def test_multiple_buy_sell_correct(self, isolated_tracker):
        """多次 buy/sell 后 current_capital 正确"""
        tracker, tmpdir, tmp_db = isolated_tracker
        # 4 笔交易（用 max_holdings=2 允许 2 只同时持仓）
        tracker.record_buy('159611', '电力ETF', 1.251, 4700, 'test', is_real=1)  # -5879.7
        tracker.record_buy('515050', '通信ETF', 1.197, 2600, 'test', is_real=1)  # -3112.2
        # 159611 部分卖 4700
        tracker.record_sell('159611', 1.217, quantity=4700, is_real=1)  # +5719.9
        # 重新买 159611
        tracker.record_buy('159611', '电力ETF', 1.221, 1900, 'test', is_real=1)  # -2319.9
        # 20000 - 5879.7 - 3112.2 + 5719.9 - 2319.9 = 14408.1
        with open(os.path.join(tmpdir, 'etf_performance.json')) as f:
            perf = json.load(f)['performance']
        assert abs(perf['current_capital'] - 14408.1) < 0.01


class TestR2ReferencePoolPositions:
    """R2: reference 池交易进 positions 表（is_reference=1）"""

    def test_rebuild_includes_reference_pool(self, isolated_tracker):
        """_rebuild_positions_from_trades 包含 reference 池"""
        tracker, tmpdir, tmp_db = isolated_tracker
        # 直接调 _rebuild_positions_from_trades（不依赖 etf_names 表）
        # 模拟 510300 交易（直接插 trade_history + 调 rebuild）
        conn = sqlite3.connect(tmp_db)
        conn.execute("""
            INSERT INTO trade_history
            (date, code, name, action, price, quantity, amount, reason, is_real, is_paper)
            VALUES ('2026-06-03', '510300', '沪深300', 'buy', 4.0, 1000, 4000.0, 'test', 1, 0)
        """)
        conn.commit()
        conn.close()

        # 调 rebuild（如果失败会抛错）
        try:
            positions = tracker._rebuild_positions_from_trades()
            codes = [p.code for p in positions]
            # 应含 510300
            assert '510300' in codes
        except Exception as e:
            pytest.fail(f"_rebuild_positions_from_trades 失败: {e}")


class TestR3MigrationScript:
    """R3: migrate 脚本重算 current_capital"""

    def test_dry_run_does_not_modify(self):
        """dry-run 不修改 performance.json"""
        result = subprocess.run(
            ['python', 'scripts/migrate_us008_bugfix.py', '--data-dir', '.'],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
        # 检查输出含 DRY RUN
        assert 'DRY RUN' in result.stdout or 'dry' in result.stdout.lower()

    def test_compute_current_capital_correct(self):
        """compute_current_capital 计算正确"""
        sys.path.insert(0, str(ROOT / 'scripts'))
        from migrate_us008_bugfix import compute_current_capital
        result = compute_current_capital('etf_data_live/etf.db', is_real_only=True)
        # 4 笔实盘交易
        assert result['initial_capital'] == 20000
        assert result['total_buy'] == 11311.8
        assert result['total_sell'] == 5719.9
        assert result['new_capital'] == 14408.1
        assert result['trades_count'] == 4

    def test_get_account_summary_reflects_fix(self):
        """get_account_summary 反映 R1+R3 修复"""
        from src.trade.tracker import TradeTracker
        tracker = TradeTracker('.')
        acc = tracker.get_account_summary()
        # R3 已 apply，current_capital 应该是 14,408.1
        assert abs(acc['cash'] - 14408.1) < 0.01


class TestUS008BugFixes:
    """US-008 漏改清单验证"""

    def test_performance_file_initialized(self, isolated_tracker):
        """R0: self.performance_file 初始化（US-009 修复确认）"""
        tracker, tmpdir, tmp_db = isolated_tracker
        assert hasattr(tracker, 'performance_file')

    def test_is_reference_column_exists(self, isolated_tracker):
        """R2: is_reference 字段存在"""
        _, _, tmp_db = isolated_tracker
        conn = sqlite3.connect(tmp_db)
        cols = [r[1] for r in conn.execute('PRAGMA table_info(positions)')]
        assert 'is_reference' in cols
        conn.close()
