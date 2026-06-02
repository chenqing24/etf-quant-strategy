#!/usr/bin/env python3
"""
dual_mode_backtest.py — 双模式量化策略回测
SOP-05 + SOP-03 Phase 5 执行

双模式：
- 趋势市：ADX > 25 且 MA5 > MA20 → 顺势（v8_sop 7因子）
- 震荡市：ADX < 20 或 MA5 < MA20 → 逆势（N6 反转）

仓位：
- 趋势市：60% 仓位，SL=-8% SP=+15% MH=5天
- 震荡市：20% 仓位，SL=-3% SP=+6% MH=2天
- 模糊市：观望
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.indicators.n6_reversal import signal_n2_5d_reversal, signal_n1_3d_reversal
from scripts.experiment.v9_v1_single_factor import FACTOR_SIGNAL_FUNCS, get_signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============ 双模式判断 ============

def calc_adx_simple(df, period=14):
    """简化 ADX"""
    high = df['high']
    low = df['low']
    close = df['close']
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=1).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period, min_periods=1).sum() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period, min_periods=1).sum() / atr.replace(0, np.nan)
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100 * di_diff / di_sum.replace(0, np.nan)
    adx = dx.rolling(period, min_periods=1).mean()
    return adx.fillna(15.0)


def classify_market(df):
    """市场状态分类：trend / volatile / unclear"""
    adx = calc_adx_simple(df)
    ma5 = df['close'].rolling(5, min_periods=1).mean()
    ma20 = df['close'].rolling(20, min_periods=1).mean()

    last = -1  # 最新行
    adx_val = adx.iloc[last] if len(adx) > 0 else 15.0
    ma5_val = ma5.iloc[last] if len(ma5) > 0 else 0
    ma20_val = ma20.iloc[last] if len(ma20) > 0 else 0

    if adx_val > 25 and ma5_val > ma20_val:
        return 'trend'
    elif adx_val < 20 or ma5_val < ma20_val:
        return 'volatile'
    else:
        return 'unclear'


def classify_market_series(df):
    """每日市场状态 series"""
    adx = calc_adx_simple(df)
    ma5 = df['close'].rolling(5, min_periods=1).mean()
    ma20 = df['close'].rolling(20, min_periods=1).mean()

    is_trend = (adx > 25) & (ma5 > ma20)
    is_volatile = (adx < 20) | (ma5 < ma20)
    mode = pd.Series('unclear', index=df.index)
    mode[is_trend] = 'trend'
    mode[is_volatile] = 'volatile'
    return mode.fillna('unclear')


# ============ 信号 ============

def v8_sop_signal(df):
    """v8_sop 7 因子 AND 信号"""
    from src.indicators.wrapper import IndicatorCalculator
    calc = IndicatorCalculator()
    df_calc = calc.calculate_all(df)

    signals = [
        (df_calc['MACD_hist'] > 0).fillna(False),          # T1
        (df_calc['close'].rolling(5).mean() > df_calc['close'].rolling(20).mean()).fillna(False),  # T2
        (df_calc['close'] > df_calc.get('SAR_trend', df_calc['close'])).fillna(False),  # T3
        (df_calc['ADX'] > 25).fillna(False),               # T4
        (df_calc['volume'] > df_calc['volume'].rolling(20).mean() * 1.5).fillna(False),  # V1
        (df_calc['RSI_10'] > 40).fillna(False),           # M3
        (df_calc['OBV'] > df_calc['OBV'].rolling(20).mean()).fillna(False),  # V2
    ]
    and_signal = pd.concat(signals, axis=1).all(axis=1)
    return and_signal.fillna(False)


def n6_signal(df):
    """N6 反转信号（OR 模式：任一触发即可）"""
    n1 = signal_n1_3d_reversal(df)
    n2 = signal_n2_5d_reversal(df)
    return (n1 | n2).fillna(False)


# ============ 持仓模拟 ============

@dataclass
class TradeResult:
    mode: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    shares: int
    pnl_pct: float
    hold_days: int


def simulate_trades(df, mode_col, signal_col,
                    trend_sl=-0.08, trend_sp=0.15, trend_mh=5,
                    volt_sl=-0.03, volt_sp=0.06, volt_mh=2,
                    transaction_cost=0.002):
    """模拟持仓：信号触发 → 持仓 → SL/SP/MH 出场"""
    df = df.copy().reset_index(drop=True)
    df['mode'] = mode_col
    df['signal'] = signal_col.fillna(False).astype(int)

    trades = []
    pos = None  # 当前持仓

    for i in range(len(df) - 1):
        today = df.iloc[i]
        mode = today['mode']
        sig = today['signal']

        if pos is None and sig == 1:
            # 开仓
            entry_price = today['close']
            entry_date = today['date']
            if mode == 'trend':
                sl = trend_sl
                sp = trend_sp
                mh = trend_mh
                position_pct = 0.6
            elif mode == 'volatile':
                sl = volt_sl
                sp = volt_sp
                mh = volt_mh
                position_pct = 0.2
            else:
                continue  # unclear 不做

            pos = {
                'entry_price': entry_price,
                'entry_date': entry_date,
                'entry_idx': i,
                'mode': mode,
                'sl': sl,
                'sp': sp,
                'mh': mh,
                'position_pct': position_pct,
                'shares': 0,
            }

        elif pos is not None:
            # 持仓中
            hold_days = i - pos['entry_idx']
            ret = (today['close'] - pos['entry_price']) / pos['entry_price']
            exit_reason = None

            if ret <= pos['sl']:
                exit_reason = 'SL'
            elif ret >= pos['sp']:
                exit_reason = 'SP'
            elif hold_days >= pos['mh']:
                exit_reason = 'MH'

            if exit_reason:
                pnl_pct = ret - transaction_cost
                trades.append(TradeResult(
                    mode=pos['mode'],
                    entry_date=pos['entry_date'],
                    entry_price=pos['entry_price'],
                    exit_date=today['date'],
                    exit_price=today['close'],
                    shares=pos['shares'],
                    pnl_pct=pnl_pct,
                    hold_days=hold_days,
                ))
                pos = None

    return trades


# ============ 主回测 ============

def run_backtest(etf_code, start_date='2023-01-01', end_date='2026-06-01'):
    """回测单个 ETF"""
    loader = DataLoader()
    df = loader.load_single(etf_code, min_rows=400)
    if df is None:
        return None

    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
    df = df.sort_values('date').reset_index(drop=True)
    df = IndicatorCalculator().calculate_all(df)

    # 每日模式
    mode_series = classify_market_series(df)

    # 信号（趋势市用 v8_sop，震荡市用 N6）
    trend_sig = v8_sop_signal(df)
    volt_sig = n6_signal(df)

    # 合并信号
    combined_signal = pd.Series(False, index=df.index)
    combined_signal[(mode_series == 'trend') & trend_sig] = True
    combined_signal[(mode_series == 'volatile') & volt_sig] = True

    # 模拟交易
    trades = simulate_trades(df, mode_series, combined_signal)

    return {
        'etf': etf_code,
        'n_trades': len(trades),
        'trades': trades,
        'mode_series': mode_series.value_counts().to_dict(),
    }


def calc_metrics(trades):
    if not trades:
        return {'total_return': 0, 'sharpe': 0, 'win_rate': 0, 'max_drawdown': 0}

    rets = [t.pnl_pct for t in trades]
    rets_arr = np.array(rets)

    total_ret = float(rets_arr.sum())
    win_rate = float((rets_arr > 0).sum() / max(len(rets_arr), 1))
    sharpe = float(rets_arr.mean() / max(rets_arr.std(), 1e-9) * np.sqrt(252)) if rets_arr.std() > 0 else 0.0

    # 最大回撤
    cum = np.cumprod(1 + rets_arr)
    running_max = np.maximum.accumulate(cum)
    drawdown = (cum - running_max) / running_max
    max_dd = float(drawdown.min())

    return {
        'total_return': total_ret,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'max_drawdown': max_dd,
        'n_trades': len(trades),
        'avg_trade': float(rets_arr.mean()),
    }


# ============ 主程序 ============

def main():
    logger.info("=" * 70)
    logger.info("双模式量化策略回测")
    logger.info("趋势市: v8_sop 7因子 60%仓 SL=-8% SP=+15%")
    logger.info("震荡市: N6反转   20%仓 SL=-3% SP=+6%")
    logger.info("=" * 70)

    ETF_POOL = [
        '510300', '515650', '515070', '512400', '512480', '588000', '520900',
        '512880', '512170', '512660', '512200', '512800', '512980',
        '515050', '515790',
    ]

    # 样本内 / 样本外
    in_start, in_end = '2023-01-01', '2024-12-31'
    oos_start, oos_end = '2025-01-01', '2026-06-01'

    all_results = []
    for code in ETF_POOL:
        res_in = run_backtest(code, in_start, in_end)
        res_oos = run_backtest(code, oos_start, oos_end)

        if res_in is None or res_oos is None:
            continue

        metrics_in = calc_metrics(res_in['trades'])
        metrics_oos = calc_metrics(res_oos['trades'])

        # 分模式统计
        mode_stats = {}
        for t in res_in['trades'] + res_oos['trades']:
            m = t.mode
            if m not in mode_stats:
                mode_stats[m] = {'pnl': [], 'n': 0}
            mode_stats[m]['pnl'].append(t.pnl_pct)
            mode_stats[m]['n'] += 1

        mode_summary = {}
        for m, data in mode_stats.items():
            arr = np.array(data['pnl'])
            mode_summary[m] = {
                'n_trades': data['n'],
                'total_return': float(arr.sum()),
                'win_rate': float((arr > 0).sum() / max(len(arr), 1)),
            }

        all_results.append({
            'etf': code,
            'is': metrics_in,
            'oos': metrics_oos,
            'mode_stats': mode_summary,
            'mode_days': res_in['mode_series'],
        })

        logger.info(f"{code}: IS ret={metrics_in['total_return']*100:+.1f}% "
                    f"Sharpe={metrics_in['sharpe']:.2f} | "
                    f"OOS ret={metrics_oos['total_return']*100:+.1f}% "
                    f"Sharpe={metrics_oos['sharpe']:.2f}")

    # 汇总
    is_rets = [r['is']['total_return'] for r in all_results]
    oos_rets = [r['oos']['total_return'] for r in all_results]
    is_sharpes = [r['is']['sharpe'] for r in all_results]
    oos_sharpes = [r['oos']['sharpe'] for r in all_results]

    # 分模式汇总
    trend_n = sum(r['mode_stats'].get('trend', {'n_trades': 0})['n_trades'] for r in all_results)
    volt_n = sum(r['mode_stats'].get('volatile', {'n_trades': 0})['n_trades'] for r in all_results)
    unclear_n = sum(r['mode_stats'].get('unclear', {'n_trades': 0})['n_trades'] for r in all_results)

    logger.info("\n" + "=" * 70)
    logger.info("汇总")
    logger.info("=" * 70)
    logger.info(f"ETF 数: {len(all_results)}")
    logger.info(f"IS 平均收益: {np.mean(is_rets)*100:+.2f}%")
    logger.info(f"IS 平均 Sharpe: {np.mean(is_sharpes):.3f}")
    logger.info(f"OOS 平均收益: {np.mean(oos_rets)*100:+.2f}%")
    logger.info(f"OOS 平均 Sharpe: {np.mean(oos_sharpes):.3f}")
    logger.info(f"\n模式分布（总交易次数）:")
    logger.info(f"  趋势市: {trend_n} 次")
    logger.info(f"  震荡市: {volt_n} 次")
    logger.info(f"  模糊市: {unclear_n} 次")

    # Top ETF
    if all_results:
        all_results.sort(key=lambda x: x['oos']['total_return'], reverse=True)
        logger.info(f"\nTop 5 (OOS 收益):")
        for r in all_results[:5]:
            logger.info(f"  {r['etf']}: OOS {r['oos']['total_return']*100:+.1f}% "
                        f"Sharpe={r['oos']['sharpe']:.2f} "
                        f"WR={r['oos']['win_rate']*100:.0f}% "
                        f"DD={r['oos']['max_drawdown']*100:.1f}%")

    # 输出报告
    output = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'trend_mode': 'v8_sop 7因子, 60%仓, SL=-8%, SP=+15%, MH=5天',
            'volatile_mode': 'N6反转, 20%仓, SL=-3%, SP=+6%, MH=2天',
            'market_classification': 'ADX>25+MA5>MA20→trend; ADX<20|MA5<MA20→volatile',
        },
        'summary': {
            'n_etf': len(all_results),
            'is_avg_return': float(np.mean(is_rets)),
            'is_avg_sharpe': float(np.mean(is_sharpes)),
            'oos_avg_return': float(np.mean(oos_rets)),
            'oos_avg_sharpe': float(np.mean(oos_sharpes)),
            'trend_trades': int(trend_n),
            'volatile_trades': int(volt_n),
            'unclear_trades': int(unclear_n),
        },
        'detail': [{
            'etf': r['etf'],
            'is': r['is'],
            'oos': r['oos'],
            'mode_stats': r['mode_stats'],
        } for r in all_results],
    }

    json_path = OUTPUT_DIR / 'dual_mode_backtest.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    # Markdown
    md = [
        "# 双模式量化策略回测报告",
        "",
        f"**生成时间**: {datetime.now().isoformat()}",
        "",
        "## 配置",
        "",
        "| 模式 | 策略 | 仓位 | SL | SP | MH |",
        "|------|------|------|-----|-----|-----|",
        f"| 趋势市 | v8_sop 7因子 | 60% | -8% | +15% | 5天 |",
        f"| 震荡市 | N6反转 | 20% | -3% | +6% | 2天 |",
        f"| 模糊市 | 观望 | — | — | — | — |",
        "",
        "## 样本内 / 样本外汇总",
        "",
        f"| 指标 | 样本内 (IS) | 样本外 (OOS) |",
        f"|------|------------|------------|",
        f"| 平均收益 | {np.mean(is_rets)*100:+.2f}% | {np.mean(oos_rets)*100:+.2f}% |",
        f"| 平均 Sharpe | {np.mean(is_sharpes):.3f} | {np.mean(oos_sharpes):.3f} |",
        f"| 平均胜率 | {np.mean([r['is']['win_rate'] for r in all_results])*100:.1f}% | {np.mean([r['oos']['win_rate'] for r in all_results])*100:.1f}% |",
        "",
        "## 模式分布",
        "",
        f"| 模式 | 交易次数 | 占比 |",
        f"|------|---------|------|",
        f"| 趋势市 | {trend_n} | {trend_n/max(trend_n+volt_n+unclear_n,1)*100:.1f}% |",
        f"| 震荡市 | {volt_n} | {volt_n/max(trend_n+volt_n+unclear_n,1)*100:.1f}% |",
        f"| 模糊市 | {unclear_n} | {unclear_n/max(trend_n+volt_n+unclear_n,1)*100:.1f}% |",
        "",
        "## Top 5 ETF（样本外）",
        "",
        "| ETF | OOS收益 | Sharpe | 胜率 | 最大回撤 |",
        "|------|---------|--------|------|---------|",
    ]
    for r in all_results[:5]:
        md.append(f"| {r['etf']} | {r['oos']['total_return']*100:+.1f}% | "
                  f"{r['oos']['sharpe']:.3f} | "
                  f"{r['oos']['win_rate']*100:.0f}% | "
                  f"{r['oos']['max_drawdown']*100:.1f}% |")

    md.extend(["", "## 验收标准检查", ""])
    oos_avg_ret = np.mean(oos_rets)
    oos_avg_sharpe = np.mean(oos_sharpes)
    checks = [
        ("总收益率 > 0", oos_avg_ret > 0, f"{oos_avg_ret*100:+.2f}%"),
        ("Sharpe > 0.5", oos_avg_sharpe > 0.5, f"{oos_avg_sharpe:.3f}"),
    ]
    for label, passed, value in checks:
        icon = "✅" if passed else "❌"
        md.append(f"- {icon} {label}: {value}")

    md_path = OUTPUT_DIR / 'dual_mode_backtest.md'
    md_path.write_text('\n'.join(md))

    logger.info(f"\n报告已保存:")
    logger.info(f"  {json_path}")
    logger.info(f"  {md_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())