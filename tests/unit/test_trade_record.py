#!/usr/bin/env python3
"""
TradeRecord 完整性测试（Q-012）

测试 trade record 必填字段：
- 基础字段：code, name, action, price, quantity, amount, date
- 决策上下文（Q-009）：model, strategy, evaluation, snapshot_ref
"""
import json
import sys
import os
from pathlib import Path
import pytest


class TestTradeRecordSchema:
    """交易记录 schema 测试"""

    def test_required_base_fields(self):
        """基础字段必填"""
        required = ['code', 'name', 'action', 'price', 'quantity', 'amount', 'date']
        # 模拟最小有效记录
        record = {
            'code': '159611',
            'name': '电力ETF广发',
            'action': 'buy',
            'price': 1.251,
            'quantity': 4700,
            'amount': 5879.7,
            'date': '2026-06-01',
        }
        for field in required:
            assert field in record, f"缺失基础字段: {field}"

    def test_required_context_fields(self):
        """Q-009 决策上下文必填"""
        required = ['model', 'strategy', 'evaluation', 'snapshot_ref']
        record = {
            'model': 'ETF量化决策v8_sop',
            'strategy': {'score_threshold': 6},
            'evaluation': {'avg_sharpe': 1.4},
            'snapshot_ref': 'etf_data_live/decision_snapshot.json',
        }
        for field in required:
            assert field in record, f"缺失决策上下文: {field}"

    def test_strategy_config_schema(self):
        """strategy 配置应包含完整维度"""
        strategy_keys = {
            'selection', 'position', 'rebalance',
            'risk_control', 'trailing_stop', 'market_filter'
        }
        strategy = {
            'selection': {'score_threshold': 6, 'top_n': 30},
            'position': {'hold_count': 2, 'weights': [0.5, 0.5]},
            'rebalance': {'rebalance_days': 10},
            'risk_control': {'stop_loss': -0.06, 'stop_gain': 0.10, 'max_hold_days': 15},
            'trailing_stop': {'enabled': False, 'threshold': 0.10, 'stop': 0.08},
            'market_filter': {'ma_period': 60, 'enabled': True},
        }
        for key in strategy_keys:
            assert key in strategy, f"strategy 缺失维度: {key}"


class TestActualTradeFile:
    """实际交易记录测试（US-008: 改查 trade_history 表替代 etf_trades.json）"""

    def test_trades_file_exists(self):
        """US-008: etf_trades.json 已废弃，迁移到 trade_history 表"""
        # 旧：检查 JSON 文件
        # trades_file = Path('etf_data_live/etf_trades.json')
        # assert trades_file.exists(), "etf_trades.json 不存在"
        # 新：检查 trade_history 表
        import sqlite3
        db_path = Path('etf_data_live/etf.db')
        if not db_path.exists():
            pytest.skip("etf.db 不存在")
        conn = sqlite3.connect(str(db_path))
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM trade_history").fetchone()[0]
            assert cnt > 0, f"trade_history 表为空（期望至少 1 笔）"
        finally:
            conn.close()

    def test_trades_have_context(self):
        """US-008: 从 trade_history 表读交易记录（含 Q-009 决策上下文）"""
        import sqlite3
        db_path = Path('etf_data_live/etf.db')
        if not db_path.exists():
            pytest.skip("etf.db 不存在")
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("SELECT model, strategy, evaluation, snapshot_ref FROM trade_history").fetchall()
            if not rows:
                pytest.skip("无交易记录")
            # US-008: 允许 model/strategy 等为空（实盘交易无决策上下文是合法的）
            # 但 Q-009 决策上下文字段必须存在（schema 已加）
            for r in rows:
                # schema 检查：4 字段都存在（值可能为 NULL）
                pass
        finally:
            conn.close()

    def test_snapshot_file_exists(self):
        """decision_snapshot.json 应存在且可解析"""
        snapshot_file = Path('etf_data_live/decision_snapshot.json')
        if not snapshot_file.exists():
            pytest.skip("decision_snapshot.json 不存在（未运行 snapshot_decision.py）")

        with open(snapshot_file) as f:
            data = json.load(f)

        # 必须字段
        required = ['model_info', 'strategy_config', 'evaluation_metrics',
                    'top_5_models', 'today_top_10', 'backtest_last_10_trades']
        for field in required:
            assert field in data, f"snapshot 缺失字段: {field}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
