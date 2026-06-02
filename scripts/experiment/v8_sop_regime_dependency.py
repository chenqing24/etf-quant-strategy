#!/usr/bin/env python3
"""
TODO-003-扩展: v8_sop 市场环境依赖性分析

目标：找出 v8_sop 在哪种市场环境下有效，在哪种环境下无效

方法：
1. 对每个 ETF 的每个交易日，标记市场环境（趋势市/震荡市/模糊市）
2. 统计 v8_sop 信号在不同市场环境下的表现
3. 分析信号触发频率、胜率、收益与市场环境的相关性

市场环境定义（SOP-05 v1.1）：
- 趋势市：ADX > 25 且 MA5 > MA20
- 震荡市：ADX < 20 或 MA5 < MA20
- 模糊市：其他
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============ 指标计算 ============

def calc_adx(high, low, close, period=14):
    n = len(close)
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
        up = high[i] - high[i-1]
        dn = low[i-1] - low[i]
        if up > dn and up > 0: plus_dm[i] = up
        if dn > up and dn > 0: minus_dm[i] = dn
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
        if s > 0: dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / s
    adx = np.zeros(n)
    adx_val = 0
    for i in range(1, n):
        adx_val = (adx_val * (period - 1) + dx[i]) / period
        adx[i] = adx_val
    return adx


def calc_ma(close, fast=5, slow=20):
    return pd.Series(close).rolling(fast, min_periods=1).mean().values, pd.Series(close).rolling(slow, min_periods=1).mean().values


# ============ v8_sop 信号计算 ============

def calc_v8_signal(df):
    """计算 v8_sop 7 因子 AND 信号"""
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values
    n = len(df)
    if n < 60: return np.zeros(n, dtype=bool)

    adx = calc_adx(high, low, close)
    ma5, ma20 = calc_ma(close, 5, 20)

    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean().values
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean().values
    macd = ema12 - ema26
    signal_line = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    macd_hist = macd - signal_line

    delta = np.diff(np.insert(close, 0, close[0]))
    gain = np.maximum(delta, 0)
    loss = np.maximum(-delta, 0)
    avg_gain = pd.Series(gain).rolling(10, min_periods=1).mean().values
    avg_loss = pd.Series(loss).rolling(10, min_periods=1).mean().values
    rsi = np.zeros(n)
    for i in range(n):
        if avg_loss[i] > 0: rsi[i] = 100 - (100 / (1 + avg_gain[i] / avg_loss[i]))

    obv = np.zeros(n)
    for i in range(1, n):
        if close[i] > close[i-1]: obv[i] = obv[i-1] + volume[i]
        elif close[i] < close[i-1]: obv[i] = obv[i-1] - volume[i]
        else: obv[i] = obv[i-1]

    vol_ma = pd.Series(volume).rolling(20, min_periods=1).mean().values
    obv_ma = pd.Series(obv).rolling(20, min_periods=1).mean().values

    signal = (
        (macd_hist > 0) &
        (ma5 > ma20) &
        (adx > 25) &
        (volume > vol_ma * 1.5) &
        (rsi > 40) &
        (obv > obv_ma)
    )
    return np.array(signal, dtype=bool)


def classify_market(adx, ma5, ma20):
    """市场环境分类"""
    if adx > 25 and ma5 > ma20:
        return 'trend'       # 趋势市
    elif adx < 20 or ma5 < ma20:
        return 'volatile'   # 震荡市
    else:
        return 'unclear'    # 模糊市


# ============ 持仓管理 + 分环境统计 ============

def analyze_regime_dependency(df, etf_code):
    """分析单个 ETF 的市场环境依赖性"""
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    n = len(df)
    if n < 60:
        return None

    adx = calc_adx(high, low, close)
    ma5, ma20 = calc_ma(close, 5, 20)
    signal = calc_v8_signal(df)

    # 标记每日市场环境
    regimes = np.array([classify_market(adx[i], ma5[i], ma20[i]) for i in range(n)])

    # 统计各环境的交易日数
    regime_days = {
        'trend': np.sum(regimes == 'trend'),
        'volatile': np.sum(regimes == 'volatile'),
        'unclear': np.sum(regimes == 'unclear'),
    }

    # 统计信号在各环境的触发情况
    signal_by_regime = {
        'trend': np.sum(signal & (regimes == 'trend')),
        'volatile': np.sum(signal & (regimes == 'volatile')),
        'unclear': np.sum(signal & (regimes == 'unclear')),
    }

    # 模拟持仓，计算收益
    trades = []
    pos = None

    for i in range(30, n - 1):
        if pos is None:
            if signal[i]:
                pos = {
                    'entry_price': close[i],
                    'entry_idx': i,
                    'entry_regime': regimes[i],
                    'entry_date': df['date'].iloc[i],
                }
        else:
            ret = (close[i] - pos['entry_price']) / pos['entry_price']
            hold_days = i - pos['entry_idx']
            exit_reason = None
            if ret <= -0.08: exit_reason = 'SL'
            elif ret >= 0.15: exit_reason = 'SP'
            elif hold_days >= 10: exit_reason = 'MH'
            elif adx[i] < 20 or ma5[i] < ma20[i]: exit_reason = 'trend_end'

            if exit_reason:
                trades.append({
                    'entry_date': pos['entry_date'],
                    'exit_date': df['date'].iloc[i],
                    'entry_regime': pos['entry_regime'],
                    'pnl': ret - 0.002,
                    'hold_days': hold_days,
                    'exit_reason': exit_reason,
                })
                pos = None

    # 按开仓时的市场环境分组统计
    regime_stats = defaultdict(lambda: {'n': 0, 'wins': 0, 'total_pnl': 0, 'returns': []})
    for t in trades:
        r = t['entry_regime']
        regime_stats[r]['n'] += 1
        regime_stats[r]['total_pnl'] += t['pnl']
        regime_stats[r]['returns'].append(t['pnl'])
        if t['pnl'] > 0:
            regime_stats[r]['wins'] += 1

    # 汇总
    result = {
        'etf': etf_code,
        'total_days': n,
        'regime_days': regime_days,
        'signal_by_regime': signal_by_regime,
        'total_trades': len(trades),
        'regime_stats': {},
    }
    for r, stats in regime_stats.items():
        rets = stats['returns']
        result['regime_stats'][r] = {
            'n_trades': stats['n'],
            'n_wins': stats['wins'],
            'win_rate': stats['wins'] / max(stats['n'], 1),
            'total_pnl': stats['total_pnl'],
            'avg_pnl': np.mean(rets) if rets else 0,
            'sharpe': (np.mean(rets) / max(np.std(rets), 1e-9) * np.sqrt(252)) if len(rets) > 1 else 0,
        }

    return result


# ============ 主程序 ============

def main():
    logger.info("=" * 70)
    logger.info("TODO-003 扩展：v8_sop 市场环境依赖性分析")
    logger.info("SOP-03 Phase 3 分析 + SOP-05 v1.1")
    logger.info("=" * 70)

    ETF_POOL = [
        '510300', '515650', '515070', '512400', '512480', '588000', '520900',
        '512880', '512170', '512660', '512200', '512800', '512980',
        '515050', '515790',
    ]

    logger.info(f"\n分析 ETF 池: {len(ETF_POOL)} 只")
    logger.info("市场环境定义（v1.1）：")
    logger.info("  - 趋势市：ADX > 25 且 MA5 > MA20")
    logger.info("  - 震荡市：ADX < 20 或 MA5 < MA20")
    logger.info("  - 模糊市：其他")
    logger.info("")

    all_results = []
    total_regime_days = defaultdict(int)
    total_signal_by_regime = defaultdict(int)
    total_trades_by_regime = defaultdict(lambda: {'n': 0, 'wins': 0, 'total_pnl': 0, 'returns': []})

    for i, code in enumerate(ETF_POOL):
        loader = DataLoader()
        df = loader.load_single(code, min_rows=400)
        if df is None:
            logger.info(f"[{i+1}/{len(ETF_POOL)}] {code}: 数据加载失败")
            continue

        df = df.sort_values('date').reset_index(drop=True)
        logger.info(f"[{i+1}/{len(ETF_POOL)}] {code}: {len(df)} 天 "
                    f"({df['date'].iloc[0]} ~ {df['date'].iloc[-1]})")

        result = analyze_regime_dependency(df, code)
        if result is None:
            continue
        all_results.append(result)

        # 聚合
        for r, d in result['regime_days'].items():
            total_regime_days[r] += d
        for r, d in result['signal_by_regime'].items():
            total_signal_by_regime[r] += d
        for r, stats in result['regime_stats'].items():
            total_trades_by_regime[r]['n'] += stats['n_trades']
            total_trades_by_regime[r]['wins'] += stats['n_wins']
            total_trades_by_regime[r]['total_pnl'] += stats['total_pnl']

        logger.info(f"    趋势市 {result['regime_days']['trend']} 天 | "
                    f"信号 {result['signal_by_regime']['trend']} 次 | "
                    f"交易 {result['regime_stats'].get('trend', {}).get('n_trades', 0)} 笔 | "
                    f"收益 {result['regime_stats'].get('trend', {}).get('total_pnl', 0)*100:+.1f}%")

    # 汇总
    logger.info("\n" + "=" * 70)
    logger.info("汇总分析")
    logger.info("=" * 70)

    n_total = sum(total_regime_days.values())
    logger.info(f"\n全池交易日分布（{n_total} 天）:")
    for r in ['trend', 'volatile', 'unclear']:
        n = total_regime_days[r]
        pct = n / n_total * 100
        sig = total_signal_by_regime[r]
        logger.info(f"  {r:8s}: {n:5d} 天 ({pct:5.1f}%) | 信号 {sig:4d} 次")

    logger.info(f"\n全池交易统计（按开仓时市场环境）:")
    logger.info(f"{'环境':<10} {'交易数':>6} {'胜率':>6} {'总收益':>8} {'平均收益':>8}")
    logger.info("-" * 45)

    for r in ['trend', 'volatile', 'unclear']:
        stats = total_trades_by_regime[r]
        n = stats['n']
        if n == 0:
            logger.info(f"{r:<10} {n:>6d} {'—':>6} {'—':>8} {'—':>8}")
            continue
        wr = stats['wins'] / n
        total_pnl = stats['total_pnl']
        avg_pnl = total_pnl / n
        logger.info(f"{r:<10} {n:>6d} {wr:>6.0%} {total_pnl:>8.1%} {avg_pnl:>8.2%}")

    # 按 ETF 汇总
    logger.info(f"\n各 ETF 趋势市交易统计:")
    logger.info(f"{'ETF':<8} {'趋势日':>6} {'趋势信号':>7} {'趋势交易':>7} {'趋势收益':>8} {'胜率':>6} {'Sharpe':>6}")
    logger.info("-" * 55)
    for r in all_results:
        rd = r['regime_days']
        sd = r['signal_by_regime']
        ts = r['regime_stats'].get('trend', {})
        n = ts.get('n_trades', 0)
        pnl = ts.get('total_pnl', 0)
        wr = ts.get('win_rate', 0)
        sh = ts.get('sharpe', 0)
        logger.info(f"{r['etf']:<8} {rd['trend']:>6d} {sd['trend']:>7d} {n:>7d} {pnl:>8.1%} {wr:>6.0%} {sh:>6.2f}")

    # 关键发现
    trend_trades = total_trades_by_regime['trend']
    volt_trades = total_trades_by_regime['volatile']
    trend_pct = trend_trades['n'] / max(trend_trades['n'] + volt_trades['n'], 1)
    trend_wr = trend_trades['wins'] / max(trend_trades['n'], 1)
    trend_pnl = trend_trades['total_pnl']

    logger.info("\n" + "=" * 70)
    logger.info("关键发现")
    logger.info("=" * 70)
    logger.info(f"趋势市交易占比: {trend_pct:.0%}")
    logger.info(f"趋势市胜率: {trend_wr:.0%}")
    logger.info(f"趋势市总收益: {trend_pnl:.1%}")
    logger.info(f"震荡市交易数: {volt_trades['n']}")

    # 验收
    logger.info("\n验收标准:")
    logger.info(f"  {'✅' if trend_pct > 0.3 else '❌'} 趋势市交易占比 > 30%: {trend_pct:.0%}")
    logger.info(f"  {'✅' if trend_wr > 0.4 else '❌'} 趋势市胜率 > 40%: {trend_wr:.0%}")
    logger.info(f"  {'✅' if trend_pnl > 0 else '❌'} 趋势市总收益 > 0: {trend_pnl:.1%}")

    # 输出
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'v8_sop_regime_dependency',
        'etf_pool': ETF_POOL,
        'n_etf': len(all_results),
        'total_regime_days': dict(total_regime_days),
        'total_signal_by_regime': dict(total_signal_by_regime),
        'total_trades_by_regime': {
            r: {'n': s['n'], 'wins': s['wins'], 'total_pnl': s['total_pnl']}
            for r, s in total_trades_by_regime.items()
        },
        'per_etf_results': [
            {k: v for k, v in r.items() if k != 'regime_stats'}
            | {'regime_stats': r['regime_stats']}
            for r in all_results
        ],
        'summary': {
            'trend_trade_pct': float(trend_pct),
            'trend_win_rate': float(trend_wr),
            'trend_total_pnl': float(trend_pnl),
        }
    }

    json_path = OUTPUT_DIR / 'v8_sop_regime_dependency.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    # Markdown
    md = [
        "# v8_sop 市场环境依赖性分析",
        "",
        f"**时间**: {datetime.now().isoformat()}",
        f"**ETF 池**: {len(all_results)} 只",
        "",
        "## 1. 市场环境定义（v1.1）",
        "",
        "| 环境 | 判断条件 | 含义 |",
        "|------|---------|------|",
        "| 趋势市 | ADX > 25 且 MA5 > MA20 | 方向明确，只吃鱼身 |",
        "| 震荡市 | ADX < 20 或 MA5 < MA20 | 无方向，空仓 |",
        "| 模糊市 | 其他 | 不做 |",
        "",
        "## 2. 全池交易日分布",
        "",
        "| 环境 | 交易日数 | 占比 | 信号次数 |",
        "|------|:-------:|:----:|--------:|",
    ]
    for r in ['trend', 'volatile', 'unclear']:
        n = total_regime_days[r]
        pct = n / n_total * 100
        sig = total_signal_by_regime[r]
        md.append(f"| {r} | {n} | {pct:.1f}% | {sig} |")

    md.extend(["", "## 3. 全池交易统计（按开仓时环境）", "",
               "| 环境 | 交易数 | 胜率 | 总收益 | 平均收益 |",
               "|------|:------:|:----:|:------:|:--------:|"])
    for r in ['trend', 'volatile', 'unclear']:
        stats = total_trades_by_regime[r]
        n = stats['n']
        if n == 0:
            md.append(f"| {r} | 0 | — | — | — |")
        else:
            wr = stats['wins'] / n
            total_pnl = stats['total_pnl']
            avg_pnl = total_pnl / n
            md.append(f"| {r} | {n} | {wr:.0%} | {total_pnl:.1%} | {avg_pnl:.2%} |")

    md.extend(["", "## 4. 关键发现", ""])
    checks = [
        ("趋势市交易占比 > 30%", trend_pct > 0.3, f"{trend_pct:.0%}"),
        ("趋势市胜率 > 40%", trend_wr > 0.4, f"{trend_wr:.0%}"),
        ("趋势市总收益 > 0", trend_pnl > 0, f"{trend_pnl:.1%}"),
    ]
    for label, passed, val in checks:
        md.append(f"- {'✅' if passed else '❌'} {label}: {val}")

    md_path = OUTPUT_DIR / 'v8_sop_regime_dependency.md'
    md_path.write_text('\n'.join(md))
    logger.info(f"\n输出: {json_path}\n       {md_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())