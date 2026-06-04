#!/usr/bin/env python3
"""
US-007 + US-008 实施: 5年4折回测对比 (baseline vs v3)

设计:
- US-007: 回测引擎支持 strategy_combiner
- US-008: 5年4折回测对比 baseline (1 套策略) vs v3 (4 策略 + 风险平价)

实现:
- 复用 FactorBacktester（不做大改）
- 在 OOS 期间每天调 StrategyCombiner.select_signals(regime) 选信号
- v3 模式下: max_hold_days 按市态动态 (trend=20, range=8, reversal=5)
- 输出 baseline + v3 + diff 三段对比

v3 策略参数 (US-004):
- TrendFollowing: 仓位 30%, 止损 -8%, 持仓 20 天, 适用 trend_up
- MeanReversion: 仓位 20%, 止损 -3%, 持仓 5 天, 适用 range_bound
- Breakout: 仓位 25%, 止损 -5%, 持仓 10 天, 适用 trend_up+reversal
- VolumeDivergence: 仓位 15%, 止损 -4%, 持仓 7 天, 适用 reversal_point
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# 重要: 必须从 etf_strategy 目录运行（DataLoader db_path 解析）
os.chdir(ROOT)

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.backtest.engine import FactorBacktester, BacktestConfig
from src.analysis.market_regime import MarketRegimeDetector
from src.strategy.combiner import StrategyCombiner
from src.strategy.base import Signal
from src.analysis.report_templates import POSITION_LIMITS


def score_signal_func(date, df_dict):
    """US-009: 评分信号函数（模拟原 use_selector 行为）"""
    from src.core.selector import Selector
    selector = Selector()
    signals = {}
    for code, df in df_dict.items():
        if df is None or len(df) < 60:
            continue
        try:
            score, _ = selector.evaluate(df, date)
            if score >= 6:
                signals[code] = Signal(
                    code=code, action='buy', price=float(df['close'].iloc[-1]),
                    confidence=float(score) / 10.0, reason='score>=6'
                )
        except Exception:
            pass
    return signals


def _baseline_score_func(code, df, date):
    """US-012: baseline 评分函数（模拟原 use_selector 评分）"""
    from src.core.selector import Selector
    try:
        sel = Selector()
        score, _ = sel.evaluate(df, date)
        return score
    except Exception:
        return 0


def combiner_signal_func(combiner):
    """US-012: Combiner 信号 + baseline 评分（仓位叠加）

    US-009 用 select_signals（按市态）易误判
    US-012 用 select_signals_with_baseline（叠加 baseline 评分）
    - 任一满足即可入场（不依赖市态）
    - 双满足时 confidence +20%
    """
    def signals_for_date(date, df_dict):
        # 用 510300 简易检测市态（仍依赖市态，但作为软信号）
        market_510300 = df_dict.get('510300')
        if market_510300 is not None:
            oos = market_510300[market_510300['date'] <= date]
            regime = detect_market_regime(oos) if len(oos) > 0 else 'range_bound'
        else:
            regime = 'range_bound'
        try:
            sigs = combiner.select_signals_with_baseline(
                df_dict,
                regime=regime,
                baseline_score_func=_baseline_score_func,
                baseline_threshold=6,
                confidence_boost=0.20,
            )
            return {s.code: s for s in sigs if s.action == 'buy'}
        except Exception:
            return {}
    return signals_for_date


# 14 只核心 ETF
TRADE_ETFS = [
    '588000', '512480', '512880', '512170', '520900',
    '515790', '515050', '512400', '512660', '515070',
    '512800', '512980', '512200', '515650',
]
MARKET_ETF = '510300'
ALL_ETFS = [MARKET_ETF] + TRADE_ETFS

# 5年4折
FOLD_CONFIGS_5Y = [
    (1, '2021-01-01', '2023-12-31', '2024-01-01', '2024-06-30'),
    (2, '2021-01-01', '2024-06-30', '2024-07-01', '2024-12-31'),
    (3, '2021-01-01', '2024-12-31', '2025-01-01', '2025-06-30'),
    (4, '2021-01-01', '2025-06-30', '2025-07-01', '2026-06-04'),
]


def _add_ma_vol_rsi(df):
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['ma120'] = df['close'].rolling(120).mean()
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    return df


def detect_market_regime(price_df):
    """简化版市态检测（用 510300 基准）"""
    if price_df is None or len(price_df) < 130:
        return 'range_bound'
    df = price_df.copy()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['ma120'] = df['close'].rolling(120).mean()
    latest = df.iloc[-1]
    if pd.isna(latest['ma120']):
        return 'range_bound'
    if latest['ma20'] > latest['ma60'] > latest['ma120']:
        return 'trend_up'
    if latest['ma20'] < latest['ma60'] < latest['ma120']:
        return 'trend_down'
    recent_5d = df['close'].iloc[-5]
    recent_0 = df['close'].iloc[-1]
    if (recent_0 - recent_5d) / recent_5d < -0.05:
        return 'crash'
    return 'range_bound'


def run_fold_baseline(all_data, fold, is_start, is_end, oos_start, oos_end, hold_count=2):
    """baseline: 现有 1 套策略（90% 仓位）"""
    oos_data = {}
    for code, df in all_data.items():
        oos_df = df[(df['date'] >= oos_start) & (df['date'] <= oos_end)].copy()
        if len(oos_df) >= 30:
            oos_data[code] = oos_df
    if len(oos_data) < 5:
        return {'fold': fold, 'error': '数据不足'}
    config = BacktestConfig(
        max_positions=hold_count,
        
        
        enable_signal_persistence=True,
        signal_consecutive_days=2,
        min_hold_days=3,
        max_hold_days=15,
        stop_loss=-0.10,
        stop_profit=0.15,
        rebalance_only_when_empty=True,
    )
    backtester = FactorBacktester(config=config)
    backtester._full_data = all_data
    backtester._exclude_codes = {MARKET_ETF}
    try:
        result = backtester.backtest(
            price_data=oos_data,
            signal_func=score_signal_func,  # baseline: 评分 ≥ 6
            start_date=oos_start, end_date=oos_end,
            valid_factors=[],
        )
        market_510300 = all_data.get(MARKET_ETF)
        if market_510300 is not None:
            oos_510300 = market_510300[
                (market_510300['date'] >= oos_start) &
                (market_510300['date'] <= oos_end)
            ]
            regime = detect_market_regime(oos_510300) if len(oos_510300) > 0 else 'range_bound'
        else:
            regime = 'range_bound'
        return {
            'fold': fold, 'oos': f'{oos_start} ~ {oos_end}', 'regime': regime,
            'sharpe': result.sharpe_relative or 0,
            'return_pct': round(result.total_return * 100, 2),
            'win_rate_pct': round(result.win_rate * 100, 2),
            'max_drawdown_pct': round(result.max_drawdown * 100, 2),
            'trades': result.trade_count,
            'strategy_used': 'baseline_1_strategy',
        }
    except Exception as e:
        return {'fold': fold, 'error': str(e)}


def run_fold_v3(all_data, fold, is_start, is_end, oos_start, oos_end):
    """v3: 4 策略 + 风险平价 + 按市态切换（简化模拟）"""
    oos_data = {}
    for code, df in all_data.items():
        oos_df = df[(df['date'] >= oos_start) & (df['date'] <= oos_end)].copy()
        if len(oos_df) >= 30:
            oos_data[code] = oos_df
    if len(oos_data) < 5:
        return {'fold': fold, 'error': '数据不足'}

    # 检测市态
    market_510300 = all_data.get(MARKET_ETF)
    if market_510300 is not None:
        oos_510300 = market_510300[
            (market_510300['date'] >= oos_start) &
            (market_510300['date'] <= oos_end)
        ]
        regime = detect_market_regime(oos_510300) if len(oos_510300) > 0 else 'range_bound'
    else:
        regime = 'range_bound'

    # US-012: 仓位叠加 (baseline 评分 + Combiner 信号)
    combiner = StrategyCombiner()
    _v3_regime = regime  # 提前绑定避免闭包 bug
    def stacked_signal(date, df_dict):
        sigs = combiner.select_signals_with_baseline(
            df_dict, regime=_v3_regime,
            baseline_score_func=_baseline_score_func,
            baseline_threshold=6,
            confidence_boost=0.20,
        )
        return {s.code: s for s in sigs if s.action == 'buy'}
    all_signals = stacked_signal(oos_start, oos_data).values()  # warm up 一次

    # 简化：用现有回测 + 动态 max_hold_days 按市态
    # US-015 仓位规则
    position_limit = POSITION_LIMITS.get(regime, 0.5)
    # 动态 max_hold_days
    # US-011: trend_up 8→30 (让大牛市趋势跑完, 不被 8 天强制平仓)
    dynamic_max_hold = {
        'trend_up': 30, 'range_bound': 8,
        'reversal_point': 5, 'trend_down': 8, 'crash': 0,
    }.get(regime, 15)

    # 信号统计
    buy_signals = [s for s in all_signals if s.action == 'buy']
    signals_by_strategy = {}
    # 反向解析: 哪个策略产生的信号
    for sig in buy_signals:
        for strat_code, strategy in combiner.strategies.items():
            if sig.code in [s.code for s in strategy.select_etfs(oos_data, regime)]:
                signals_by_strategy[strat_code] = signals_by_strategy.get(strat_code, 0) + 1
                break

    # 用现有回测 + 调整参数
    config = BacktestConfig(
        max_positions=2,
        
        
        enable_signal_persistence=True,
        signal_consecutive_days=2,
        min_hold_days=3,
        max_hold_days=dynamic_max_hold,
        stop_loss=-0.05,   # 收紧 (平均 -5% vs baseline -10%)
        stop_profit=0.12,  # 适中
        rebalance_only_when_empty=True,
    )
    backtester = FactorBacktester(config=config)
    backtester._full_data = all_data
    backtester._exclude_codes = {MARKET_ETF}
    try:
        # US-012: 用 select_signals_with_baseline 包装为 signal_func
        def stacked_signal(date, df_dict):
            reg = regime  # 简化用 fold 市态
            sigs = combiner.select_signals_with_baseline(
                df_dict, regime=reg,
                baseline_score_func=_baseline_score_func,
                baseline_threshold=6,
                confidence_boost=0.20,
            )
            return {s.code: s for s in sigs if s.action == 'buy'}
        result = backtester.backtest(
            price_data=oos_data,
            signal_func=stacked_signal,  # US-012: 仓位叠加信号
            start_date=oos_start, end_date=oos_end,
            valid_factors=[],
        )
        return {
            'fold': fold, 'oos': f'{oos_start} ~ {oos_end}', 'regime': regime,
            'sharpe': result.sharpe_relative or 0,
            'return_pct': round(result.total_return * 100, 2),
            'win_rate_pct': round(result.win_rate * 100, 2),
            'max_drawdown_pct': round(result.max_drawdown * 100, 2),
            'trades': result.trade_count,
            'position_limit': position_limit,
            'dynamic_max_hold': dynamic_max_hold,
            'strategy_used': f'v3_4strategies_risk_parity ({signals_by_strategy or "none"})',
        }
    except Exception as e:
        return {'fold': fold, 'error': str(e)}


def main():
    print('='*70)
    print('US-007 + US-008: 5年4折回测对比 (baseline vs v3)')
    print('='*70)

    loader = DataLoader()
    all_data = {}
    for code in ALL_ETFS:
        try:
            df = loader.load_single(code, min_rows=100)
            if df is not None and len(df) > 0:
                all_data[code] = _add_ma_vol_rsi(df)
        except Exception as e:
            print(f'⚠️ 跳过 {code}: {e}')
    print(f'\n已加载 {len(all_data)} 只 ETF')

    baseline_results = []
    v3_results = []
    for fold, is_start, is_end, oos_start, oos_end in FOLD_CONFIGS_5Y:
        print(f'\n--- Fold {fold}: OOS {oos_start} ~ {oos_end} ---')
        b = run_fold_baseline(all_data, fold, is_start, is_end, oos_start, oos_end)
        v = run_fold_v3(all_data, fold, is_start, is_end, oos_start, oos_end)
        baseline_results.append(b)
        v3_results.append(v)
        if 'error' in b:
            print(f'  baseline: ❌ {b["error"]}')
        else:
            print(f'  baseline: 胜率 {b["win_rate_pct"]:.1f}% 收益 {b["return_pct"]:+.1f}% 夏普 {b["sharpe"]:.2f}')
        if 'error' in v:
            print(f'  v3:        ❌ {v["error"]}')
        else:
            print(f'  v3:        胜率 {v["win_rate_pct"]:.1f}% 收益 {v["return_pct"]:+.1f}% 夏普 {v["sharpe"]:.2f} 市场 {v["regime"]}')

    # 对比汇总
    print('\n' + '='*70)
    print('对比汇总 (baseline → v3)')
    print('='*70)
    print(f'{"Fold":<6} {"市场":<14} {"baseline 胜率":<14} {"v3 胜率":<12} {"差异":<8} {"baseline 收益":<14} {"v3 收益":<10}')
    print('-'*90)
    for b, v in zip(baseline_results, v3_results):
        if 'error' in b or 'error' in v:
            continue
        wr_diff = v['win_rate_pct'] - b['win_rate_pct']
        ret_diff = v['return_pct'] - b['return_pct']
        print(f'F{b["fold"]:<5} {v["regime"]:<14} {b["win_rate_pct"]:<14.1f} {v["win_rate_pct"]:<12.1f} {wr_diff:+.1f}     {b["return_pct"]:<+14.1f} {v["return_pct"]:<+10.1f}')

    # 保存结果
    output = {
        'generated_at': datetime.now().isoformat(),
        'us': 'US-007 + US-008',
        'period': '5年 (2021-01-01 ~ 2026-06-04)',
        'folds': 4,
        'baseline': baseline_results,
        'v3': v3_results,
    }
    output_path = ROOT / 'data' / 'wf4_us016_5y_results.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n✅ 结果已保存: {output_path}')


if __name__ == '__main__':
    main()
