#!/usr/bin/env python3
"""
US-015 5年4折 Walk-Forward 回测 + 仓位规则应用

设计：
- 5年：2021-01-01 ~ 2026-06-04
- 4折：每个 OOS 半年，IS 递增
- 应用 US-015 仓位规则（震荡 50% / 趋势 90% / 下跌 30% / 暴跌 0%）
- 对比 baseline（90% 一刀切） vs US-015 分档

按 SOP-03 Phase 3 实施
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.backtest.engine import FactorBacktester, BacktestConfig


# ============================================================
# ETF 池（14 只核心，US-002 标记的 tradable）
# ============================================================
TRADE_ETFS = [
    '588000', '512480', '512880', '512170', '520900',
    '515790', '515050', '512400', '512660', '515070',
    '512800', '512980', '512200', '515650',
]
MARKET_ETF = '510300'  # 大盘参考
ALL_ETFS = [MARKET_ETF] + TRADE_ETFS


# ============================================================
# 5年4折日期分段（2021-01-01 ~ 2026-06-04）
# ============================================================
FOLD_CONFIGS_5Y = [
    # fold, is_start, is_end, oos_start, oos_end
    (1, '2021-01-01', '2023-12-31', '2024-01-01', '2024-06-30'),
    (2, '2021-01-01', '2024-06-30', '2024-07-01', '2024-12-31'),
    (3, '2021-01-01', '2024-12-31', '2025-01-01', '2025-06-30'),
    (4, '2021-01-01', '2025-06-30', '2025-07-01', '2026-06-04'),
]


# US-015 仓位规则
POSITION_LIMITS = {
    'trend_up':    0.9,
    'range_bound': 0.5,
    'trend_down':  0.3,
    'crash':       0.0,
}


def _add_ma_vol_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """添加 Selector 需要的 ma/vol/rsi 列"""
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


def detect_market_regime(price_df: pd.DataFrame) -> str:
    """
    检测市场环境（简化版，使用 MA 排列）
    """
    if price_df is None or len(price_df) < 130:
        return 'range_bound'
    df = price_df.copy()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['ma120'] = df['close'].rolling(120).mean()
    latest = df.iloc[-1]
    if pd.isna(latest['ma120']):
        return 'range_bound'
    # 趋势市: ma20 > ma60 > ma120
    if latest['ma20'] > latest['ma60'] > latest['ma120']:
        return 'trend_up'
    # 下跌市: ma20 < ma60 < ma120
    if latest['ma20'] < latest['ma60'] < latest['ma120']:
        return 'trend_down'
    # 暴跌市: 5d 跌 5%+
    recent_5d = df['close'].iloc[-5]
    recent_0 = df['close'].iloc[-1]
    if (recent_0 - recent_5d) / recent_5d < -0.05:
        return 'crash'
    return 'range_bound'


def run_single_fold(
    all_data: Dict[str, pd.DataFrame],
    fold: int,
    is_start: str,
    is_end: str,
    oos_start: str,
    oos_end: str,
    hold_count: int = 2,
    apply_us015: bool = True,
) -> dict:
    """
    跑单个 Fold

    Args:
        apply_us015: True 应用 US-015 仓位规则；False 用 90% baseline
    """
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
            start_date=oos_start,
            end_date=oos_end,
            valid_factors=[],
        )
        # US-015: 按市场状态应用仓位规则
        if apply_us015:
            # 检测 OOS 期间市场状态
            market_510300 = all_data.get(MARKET_ETF)
            if market_510300 is not None:
                oos_510300 = market_510300[
                    (market_510300['date'] >= oos_start) &
                    (market_510300['date'] <= oos_end)
                ]
                if len(oos_510300) > 0:
                    regime = detect_market_regime(oos_510300)
                    position_limit = POSITION_LIMITS[regime]
                else:
                    regime = 'range_bound'
                    position_limit = 0.5
            else:
                regime = 'range_bound'
                position_limit = 0.5
            # 模拟仓位限制对最终收益的影响
            # baseline 是 90% 仓位，US-015 按 position_limit
            # 收益调整: total_return_adjusted = total_return * (position_limit / 0.9)
            # (简化的线性调整)
            adjusted_return = result.total_return * 100 * (position_limit / 0.9)
        else:
            regime = 'baseline'
            position_limit = 0.9
            adjusted_return = result.total_return * 100

        return {
            'fold': fold,
            'is': f'{is_start} ~ {is_end}',
            'oos': f'{oos_start} ~ {oos_end}',
            'sharpe': result.sharpe_relative or 0,
            'return': result.total_return * 100,
            'win_rate': result.win_rate * 100,
            'profit_loss_ratio': result.profit_loss_ratio or 0,
            'trades': result.trade_count,
            'max_drawdown': result.max_drawdown * 100,
            'market_regime': regime,
            'position_limit': position_limit,
            'adjusted_return_us015': round(adjusted_return, 2) if apply_us015 else None,
        }
    except Exception as e:
        return {'fold': fold, 'error': str(e)}


def run_5y_wf(apply_us015: bool = True) -> List[dict]:
    """跑 5年4折全部 Fold"""
    print(f'\n=== 5年4折 Walk-Forward (US-015={apply_us015}) ===\n')
    loader = DataLoader()
    # 加载所有 ETF 数据（用 wf4.py 同样的接口：loader.load_single）
    all_data = {}
    for code in ALL_ETFS:
        try:
            df = loader.load_single(code, min_rows=400)
            if df is not None and len(df) > 0:
                df = _add_ma_vol_rsi(df)
                all_data[code] = df
        except Exception as e:
            print(f'⚠️ 跳过 {code}: {e}')

    print(f'已加载 {len(all_data)} 只 ETF 数据')
    print(f'日期范围: {min(d["date"].min() for d in all_data.values())} ~ '
          f'{max(d["date"].max() for d in all_data.values())}')

    results = []
    for fold, is_start, is_end, oos_start, oos_end in FOLD_CONFIGS_5Y:
        print(f'\n--- Fold {fold}: OOS {oos_start} ~ {oos_end} ---')
        result = run_single_fold(
            all_data, fold, is_start, is_end, oos_start, oos_end,
            hold_count=2, apply_us015=apply_us015
        )
        results.append(result)
        if 'error' in result:
            print(f'  ❌ 错误: {result["error"]}')
        else:
            print(f'  收益: {result["return"]:+.1f}% | '
                  f'夏普: {result["sharpe"]:.2f} | '
                  f'胜率: {result["win_rate"]:.1f}% | '
                  f'最大回撤: {result["max_drawdown"]:+.1f}%')
            if apply_us015:
                print(f'  市场: {result["market_regime"]} | '
                      f'仓位上限: {result["position_limit"]*100:.0f}% | '
                      f'调整后收益: {result["adjusted_return_us015"]:+.1f}%')

    return results


def main():
    """主流程：跑 baseline + US-015 对比"""
    print('=' * 70)
    print('US-015 5年4折 Walk-Forward 回测')
    print('=' * 70)

    # 1. Baseline (90% 固定)
    baseline = run_5y_wf(apply_us015=False)

    # 2. US-015 应用（按市场分档）
    us015 = run_5y_wf(apply_us015=True)

    # 3. 对比汇总
    print('\n' + '=' * 70)
    print('对比汇总')
    print('=' * 70)
    print(f'{"Fold":<6} {"Baseline%":<12} {"US-015%":<12} {"市场":<14} {"仓位%":<8} {"差异%"}')
    print('-' * 70)
    for b, u in zip(baseline, us015):
        if 'error' in b or 'error' in u:
            print(f'{"F"+str(b.get("fold", "?")):<6} ❌ 错误')
            continue
        diff = u['adjusted_return_us015'] - b['return']
        print(f'F{b["fold"]:<5} {b["return"]:<+12.1f} {u["adjusted_return_us015"]:<+12.1f} '
              f'{u["market_regime"]:<14} {u["position_limit"]*100:<8.0f} {diff:+.1f}')

    # 4. 保存结果
    output = {
        'generated_at': datetime.now().isoformat(),
        'us': 'US-015',
        'period': '5年 (2021-01-01 ~ 2026-06-04)',
        'folds': 4,
        'baseline': baseline,
        'us015': us015,
    }
    output_path = ROOT / 'data' / 'wf4_us015_5y_results.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n✅ 结果已保存: {output_path}')


if __name__ == '__main__':
    main()
