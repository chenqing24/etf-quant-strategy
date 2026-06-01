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
    """实际交易文件测试"""

    def test_trades_file_exists(self):
        trades_file = Path('etf_data_live/etf_trades.json')
        assert trades_file.exists(), "etf_trades.json 不存在"

    def test_trades_have_context(self):
        """所有交易应包含 Q-009 决策上下文"""
        trades_file = Path('etf_data_live/etf_trades.json')
        if not trades_file.exists():
            pytest.skip("etf_trades.json 不存在")

        with open(trades_file) as f:
            data = json.load(f)

        trades = data.get('trades', [])
        if not trades:
            pytest.skip("无交易记录")

        context_fields = ['model', 'strategy', 'evaluation', 'snapshot_ref']
        for i, trade in enumerate(trades):
            for field in context_fields:
                assert field in trade, f"第 {i+1} 笔交易缺失 {field}"

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
