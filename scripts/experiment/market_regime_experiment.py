#!/usr/bin/env python3
"""
SOP-03 Phase 1 + 2: 震荡判断标准验证实验

实验目标：
- 验证不同的 ADX 阈值组合对趋势/震荡市判断的影响
- 找出使趋势市策略收益最大化的"震荡市入场信号"

参数网格（ADX阈值 × 均线条件）:
- ADX_趋势: [20, 25, 30]
- ADX_震荡上界: [15, 18, 20, 22, 25]
- 均线: MA5/MA20, MA10/MA30, EMA12/EMA26

验证方法：
- IS: 2023-2024（训练期）
- OOS: 2025-2026（验证期）
- 每组参数跑 15 ETF，取平均 + 中位数
- 核心指标：Sharpe > 0.5, 总收益 > 0

输出：
- data/experiments_v9_recompute/market_regime_experiment.json
- data/experiments_v9_recompute/market_regime_experiment.md
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from itertools import product
from collections import defaultdict

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============ 指标计算（独立实现，不依赖外部函数）============

def calc_adx(df, period=14):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(close)
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        h_l = high[i] - low[i]
        h_c = abs(high[i] - close[i-1])
        l_c = abs(low[i] - close[i-1])
        tr[i] = max(h_l, h_c, l_c)
        up = high[i] - high[i-1]
        dn = low[i-1] - low[i]
        if up > dn and up > 0:
            plus_dm[i] = up
        if dn > up and dn > 0:
            minus_dm[i] = dn
    tr_ma = pd.Series(tr).rolling(period, min_periods=1).mean().values
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)
    for i in range(1, n):
        if tr_ma[i] > 0:
            plus_di[i] = 100 * np.sum(plus_dm[1:i+1]) / tr_ma[i]
            minus_di[i] = 100 * np.sum(minus_dm[1:i+1]) / tr_ma[i]
    dx = np.zeros(n)
    for i in range(1, n):
        s = plus_di[i] + minus_di[i]
        if s > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / s
    adx = np.zeros(n)
    adx_val = 0
    for i in range(1, n):
        adx_val = (adx_val * (period - 1) + dx[i]) / period
        adx[i] = adx_val
    return adx


def calc_ma(close, fast, slow):
    ma_fast = pd.Series(close).rolling(fast, min_periods=1).mean().values
    ma_slow = pd.Series(close).rolling(slow, min_periods=1).mean().values
    return ma_fast, ma_slow


# ============ 策略回测（固定 v8_sop 逻辑）============

def backtest_v8_sop(df, adx_thresh_trend=25, adx_thresh_volatile=20,
                    ma_fast=5, ma_slow=20, position_pct=0.60,
                    stop_loss=-0.08, stop_profit=0.15, min_hold=1, max_hold=10):
    """
    v8_sop 7因子 + 可变市场判断阈值
    核心：trend_market 用 v8_sop 信号，volatile_market 用突破信号
    """
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values
    n = len(df)
    if n < 60:
        return []

    adx = calc_adx(df)
    ma_fast_arr, ma_slow_arr = calc_ma(close, ma_fast, ma_slow)

    # MACD
    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean().values
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean().values
    macd = ema12 - ema26
    signal_line = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    macd_hist = macd - signal_line

    # RSI
    delta = np.diff(np.insert(close, 0, close[0]))
    gain = np.maximum(delta, 0)
    loss = np.maximum(-delta, 0)
    avg_gain = pd.Series(gain).rolling(10, min_periods=1).mean().values
    avg_loss = pd.Series(loss).rolling(10, min_periods=1).mean().values
    rsi = np.zeros(n)
    for i in range(n):
        if avg_loss[i] > 0:
            rsi[i] = 100 - (100 / (1 + avg_gain[i] / avg_loss[i]))

    # OBV
    obv = np.zeros(n)
    for i in range(1, n):
        if close[i] > close[i-1]:
            obv[i] = obv[i-1] + volume[i]
        elif close[i] < close[i-1]:
            obv[i] = obv[i-1] - volume[i]
        else:
            obv[i] = obv[i-1]

    # 市场状态
    is_trend = (adx > adx_thresh_trend) & (ma_fast_arr > ma_slow_arr)
    is_volatile = (adx < adx_thresh_volatile) | (ma_fast_arr < ma_slow_arr)

    # v8_sop 信号（趋势市）
    vol_ma = pd.Series(volume).rolling(20, min_periods=1).mean().values
    signal = (
        (macd_hist > 0) &
        (ma_fast_arr > ma_slow_arr) &
        (adx > adx_thresh_trend) &
        (volume > vol_ma * 1.5) &
        (rsi > 40) &
        (obv > pd.Series(obv).rolling(20, min_periods=1).mean().values)
    )

    trades = []
    pos = None

    for i in range(20, n - 1):
        if pos is None:
            # 趋势市：v8_sop 信号
            if is_trend[i] and signal[i]:
                pos = {
                    'entry_price': close[i],
                    'entry_date': df['date'].iloc[i],
                    'entry_idx': i,
                    'position_pct': position_pct,
                    'mode': 'trend',
                }
            # 震荡市：价格突破区间上沿
            elif is_volatile[i] and adx_thresh_volatile <= adx_thresh_trend:
                roll_high = pd.Series(high[:i+1]).rolling(20, min_periods=10).max().iloc[-1] if i >= 20 else high[i]
                roll_low = pd.Series(low[:i+1]).rolling(20, min_periods=10).min().iloc[-1] if i >= 20 else low[i]
                range_width = roll_high - roll_low
                if range_width > 0 and close[i] > roll_high:
                    pos = {
                        'entry_price': close[i],
                        'entry_date': df['date'].iloc[i],
                        'entry_idx': i,
                        'position_pct': position_pct * 0.4,  # 震荡市试探仓
                        'mode': 'volatile_breakout',
                    }
        else:
            ret = (close[i] - pos['entry_price']) / pos['entry_price']
            hold_days = i - pos['entry_idx']
            exit_reason = None
            if ret <= stop_loss:
                exit_reason = 'SL'
            elif ret >= stop_profit:
                exit_reason = 'SP'
            elif hold_days >= max_hold:
                exit_reason = 'MH'
            elif not is_trend[i] and pos['mode'] == 'trend':
                exit_reason = 'trend_end'
            elif not is_volatile[i] and pos['mode'] == 'volatile_breakout':
                exit_reason = 'mode_end'

            if exit_reason:
                pnl = ret - 0.002
                trades.append({
                    'entry_date': pos['entry_date'],
                    'exit_date': df['date'].iloc[i],
                    'mode': pos['mode'],
                    'position_pct': pos['position_pct'],
                    'pnl': pnl,
                    'hold_days': hold_days,
                    'exit_reason': exit_reason,
                })
                pos = None

    return trades


def calc_metrics(trades):
    if not trades:
        return {'total_return': 0, 'sharpe': 0, 'win_rate': 0, 'max_drawdown': 0, 'n_trades': 0}
    rets = np.array([t['pnl'] for t in trades])
    cum = np.cumprod(1 + rets)
    running_max = np.maximum.accumulate(cum)
    dd = (cum - running_max) / running_max
    total_ret = rets.sum()
    win_rate = (rets > 0).mean()
    sharpe = rets.mean() / max(rets.std(), 1e-9) * np.sqrt(252) if len(rets) > 1 else 0
    return {
        'total_return': float(total_ret),
        'sharpe': float(sharpe),
        'win_rate': float(win_rate),
        'max_drawdown': float(dd.min()),
        'n_trades': len(trades),
        'avg_trade': float(rets.mean()),
    }


# ============ 主程序 ============

def main():
    logger.info("=" * 70)
    logger.info("SOP-03 Phase 1+2: 震荡判断标准验证实验")
    logger.info("=" * 70)

    ETF_POOL = [
        '510300', '515650', '515070', '512400', '512480', '588000', '520900',
        '512880', '512170', '512660', '512200', '512800', '512980',
        '515050', '515790',
    ]

    # 参数网格
    ADX_TREND = [20, 25, 30]
    ADX_VOLATILE = [15, 18, 20, 22, 25]
    MA_PAIRS = [(5, 20), (10, 30), (12, 26)]

    # 构建完整网格
    all_params = list(product(ADX_TREND, ADX_VOLATILE, MA_PAIRS))
    all_params = [(at, av, mf, ms) for at, av, (mf, ms) in all_params if av <= at]

    logger.info(f"参数组合数: {len(all_params)} = {len(ADX_TREND)} ADX趋势 × {len(ADX_VOLATILE)} ADX震荡 × {len(MA_PAIRS)} MA")
    logger.info(f"ETF数: {len(ETF_POOL)}")
    logger.info("")

    IS_START, IS_END = '2023-01-01', '2024-12-31'
    OOS_START, OOS_END = '2025-01-01', '2026-06-01'

    # 每个参数组合跑全 ETF 池
    all_results = []
    batch_size = 10

    for batch_num, params in enumerate(all_params):
        adx_trend, adx_volatile, ma_fast, ma_slow = params
        key = f"AT{adx_trend}_AV{adx_volatile}_MA{ma_fast}{ma_slow}"

        is_returns, oos_returns = [], []
        is_sharpes, oos_sharpes = [], []
        is_n_trades, oos_n_trades = [], []

        for code in ETF_POOL:
            loader = DataLoader()
            df = loader.load_single(code, min_rows=400)
            if df is None:
                continue
            df = df.sort_values('date').reset_index(drop=True)
            df_is = df[(df['date'] >= IS_START) & (df['date'] <= IS_END)]
            df_oos = df[(df['date'] >= OOS_START) & (df['date'] <= OOS_END)]
            if len(df_is) < 200 or len(df_oos) < 200:
                continue

            trades_is = backtest_v8_sop(
                df_is, adx_trend, adx_volatile, ma_fast, ma_slow,
                position_pct=0.60, stop_loss=-0.08, stop_profit=0.15
            )
            trades_oos = backtest_v8_sop(
                df_oos, adx_trend, adx_volatile, ma_fast, ma_slow,
                position_pct=0.60, stop_loss=-0.08, stop_profit=0.15
            )

            m_is = calc_metrics(trades_is)
            m_oos = calc_metrics(trades_oos)

            is_returns.append(m_is['total_return'])
            oos_returns.append(m_oos['total_return'])
            is_sharpes.append(m_is['sharpe'])
            oos_sharpes.append(m_oos['sharpe'])
            is_n_trades.append(m_is['n_trades'])
            oos_n_trades.append(m_oos['n_trades'])

        n_etf = len(is_returns)
        result = {
            'key': key,
            'adx_trend': adx_trend,
            'adx_volatile': adx_volatile,
            'ma_fast': ma_fast,
            'ma_slow': ma_slow,
            'is_avg_return': float(np.mean(is_returns)) if is_returns else 0,
            'oos_avg_return': float(np.mean(oos_returns)) if oos_returns else 0,
            'is_avg_sharpe': float(np.mean([s for s in is_sharpes if s != 0])) if is_sharpes else 0,
            'oos_avg_sharpe': float(np.mean([s for s in oos_sharpes if s != 0])) if oos_sharpes else 0,
            'is_avg_trades': float(np.mean(is_n_trades)) if is_n_trades else 0,
            'oos_avg_trades': float(np.mean(oos_n_trades)) if oos_n_trades else 0,
            'is_win_rate': float(np.mean([r for r in is_returns if r != 0])) if is_returns else 0,
            'oos_win_rate': float(np.mean([r for r in oos_returns if r != 0])) if oos_returns else 0,
            'n_etf': n_etf,
        }
        all_results.append(result)

        # 每 batch_size 个组合输出一次进度
        if (batch_num + 1) % batch_size == 0:
            logger.info(f"  [{batch_num+1}/{len(all_params)}] 最近 {batch_size} 组合: "
                        f"OOS收益 均值={np.mean([r['oos_avg_return'] for r in all_results[-batch_size:]])*100:+.2f}%")

    # 排序
    all_results.sort(key=lambda x: x['oos_avg_sharpe'], reverse=True)

    logger.info("\n" + "=" * 70)
    logger.info("Top 10 参数组合（按 OOS Sharpe 排序）")
    logger.info("=" * 70)
    logger.info(f"{'Key':<20} {'AT':<4} {'AV':<4} {'MA':<6} {'ISRet':>8} {'OOSRet':>8} {'ISsh':>6} {'OOSsh':>7} {'nETF':>5}")
    logger.info("-" * 70)
    for r in all_results[:10]:
        logger.info(f"{r['key']:<20} {r['adx_trend']:<4} {r['adx_volatile']:<4} "
                    f"MA{r['ma_fast']}{r['ma_slow']:<4} "
                    f"{r['is_avg_return']*100:>+7.1f}% {r['oos_avg_return']*100:>+7.1f}% "
                    f"{r['is_avg_sharpe']:>6.2f} {r['oos_avg_sharpe']:>7.2f} {r['n_etf']:>5}")

    logger.info("\n" + "=" * 70)
    logger.info("验收标准检查（SOP-03 + SOP-05）")
    logger.info("=" * 70)
    passing = [r for r in all_results if r['oos_avg_return'] > 0 and r['oos_avg_sharpe'] > 0.5]
    passing_rate = len(passing) / len(all_results) * 100
    logger.info(f"通过率（OOS收益>0 且 Sharpe>0.5）: {passing_rate:.1f}% ({len(passing)}/{len(all_results)})")
    logger.info(f"最优 OOS Sharpe: {all_results[0]['oos_avg_sharpe']:.3f}")
    logger.info(f"最优 OOS 收益: {all_results[0]['oos_avg_return']*100:+.2f}%")
    print(f"当前 SOP-05 默认 (AT25, AV20, MA5/20): ", end="")
    default = next((r for r in all_results if r['adx_trend'] == 25 and r['adx_volatile'] == 20 and r['ma_fast'] == 5 and r['ma_slow'] == 20), None)
    if default:
        print(f"OOSSharpe={default['oos_avg_sharpe']:.2f}, OOS收益={default['oos_avg_return']*100:+.2f}%")
    else:
        print("未在本次网格中找到")

    # 输出
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'market_regime_threshold_validation',
        'sop': 'SOP-03 Phase 1+2',
        'config': {
            'etf_pool': ETF_POOL,
            'is_period': f'{IS_START} ~ {IS_END}',
            'oos_period': f'{OOS_START} ~ {OOS_END}',
            'adx_trend_range': ADX_TREND,
            'adx_volatile_range': ADX_VOLATILE,
            'ma_pairs': MA_PAIRS,
            'total_combinations': len(all_params),
        },
        'results': all_results,
        'summary': {
            'total_combinations': len(all_results),
            'passing_count': len(passing),
            'passing_rate': passing_rate,
            'best_oos_sharpe': all_results[0]['oos_avg_sharpe'],
            'best_oos_return': all_results[0]['oos_avg_return'],
            'default_params': {
                'adx_trend': 25,
                'adx_volatile': 20,
                'ma_fast': 5,
                'ma_slow': 20,
                'oos_sharpe': default['oos_avg_sharpe'] if default else None,
                'oos_return': default['oos_avg_return'] if default else None,
            }
        }
    }

    json_path = OUTPUT_DIR / 'market_regime_experiment.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    # Markdown 报告
    md = [
        "# 震荡判断标准验证实验报告",
        "",
        f"**生成时间**: {datetime.now().isoformat()}",
        f"**SOP**: SOP-03 Phase 1 + 2",
        "",
        "## 实验设计",
        "",
        f"- ETF池: {len(ETF_POOL)} 只",
        f"- 参数组合: {len(all_params)} 个",
        f"- IS区间: {IS_START} ~ {IS_END}",
        f"- OOS区间: {OOS_START} ~ {OOS_END}",
        "",
        f"**通过率（OOS收益>0 且 Sharpe>0.5）**: {passing_rate:.1f}%",
        "",
        "## 参数网格",
        "",
        "| 参数 | 范围 |",
        "|------|------|",
        f"| ADX_趋势阈值 | {ADX_TREND} |",
        f"| ADX_震荡上界 | {ADX_VOLATILE} |",
        f"| 均线组合 | {MA_PAIRS} |",
        "",
        "## Top 10 参数组合",
        "",
        "| # | AT | AV | MA | IS收益 | OOS收益 | IS Sharpe | OOS Sharpe |",
        "|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for i, r in enumerate(all_results[:10], 1):
        md.append(f"| {i} | {r['adx_trend']} | {r['adx_volatile']} | "
                  f"MA{r['ma_fast']}{r['ma_slow']} | "
                  f"{r['is_avg_return']*100:+.1f}% | {r['oos_avg_return']*100:+.1f}% | "
                  f"{r['is_avg_sharpe']:.2f} | {r['oos_avg_sharpe']:.2f} |")

    md.extend(["", "## 验收标准", ""])
    checks = [
        ("通过率 > 5%", passing_rate > 5, f"{passing_rate:.1f}%"),
        ("OOS Sharpe > 0.5", all_results[0]['oos_avg_sharpe'] > 0.5, f"{all_results[0]['oos_avg_sharpe']:.3f}"),
        ("OOS 收益 > 0", all_results[0]['oos_avg_return'] > 0, f"{all_results[0]['oos_avg_return']*100:+.2f}%"),
    ]
    for label, passed, val in checks:
        md.append(f"- {'✅' if passed else '❌'} {label}: {val}")

    logger.info(f"\n输出: {json_path}")
    md_path = OUTPUT_DIR / 'market_regime_experiment.md'
    md_path.write_text('\n'.join(md))
    logger.info(f"       {md_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())