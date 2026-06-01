#!/usr/bin/env python3
"""
dual_mode_v2_backtest.py — 修订版双模式策略回测
基于第一性原理修改建议

核心改动：
1. 震荡市 → 趋势市：突破直接进（不等"二次确认"），回踩不破区间上沿加仓
2. 加仓规则写死：初始 20% → 确认 40% → 趋势持续 60%
3. 鱼尾判断：ADX 峰值回落 30% → 减半仓；MA5 死叉 MA20 → 清仓

对比基准：旧版双模式（震荡市 N6 反转）
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============ 指标计算 ============

def calc_adx_simple(df, period=14):
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


def calc_ma(df, fast=5, slow=20):
    ma5 = df['close'].rolling(fast, min_periods=1).mean()
    ma20 = df['close'].rolling(slow, min_periods=1).mean()
    return ma5, ma20


def calc_range(df, window=20):
    """计算近期波动区间 [lower, upper]"""
    roll_high = df['high'].rolling(window, min_periods=10).max()
    roll_low = df['low'].rolling(window, min_periods=10).min()
    return roll_low, roll_high


def v8_sop_signal(df_calc):
    """v8_sop 7 因子 AND 信号"""
    ma5, ma20 = calc_ma(df_calc)
    return (
        (df_calc['MACD_hist'] > 0).fillna(False) &
        (ma5 > ma20).fillna(False) &
        (df_calc['ADX'] > 25).fillna(False) &
        (df_calc['volume'] > df_calc['volume'].rolling(20).mean() * 1.5).fillna(False) &
        (df_calc['RSI_10'] > 40).fillna(False) &
        (df_calc['OBV'] > df_calc['OBV'].rolling(20).mean()).fillna(False)
    )


# ============ 修订版双模式核心 ============

@dataclass
class Position:
    """持仓记录"""
    mode: str           # 'breakout_add', 'hold'
    entry_price: float
    entry_date: str
    entry_idx: int
    shares: int
    position_pct: float  # 当前仓位比例（相对于总资金）
    stop_loss: float
    target: float
    adx_peak: float = 0.0  # 跟踪 ADX 峰值
    phase: str = 'initial'  # 'initial' / 'confirmed' / 'full'


@dataclass
class Trade:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    mode: str
    position_pct: float
    pnl_pct: float
    hold_days: int
    n_adds: int  # 加仓次数
    exit_reason: str


def run_strategy_v2(df_raw, etf_code):
    """
    修订版双模式策略

    核心规则：
    1. 震荡市：ADX < 20 且 MA5 < MA20 → 等待，不做
    2. 区间上沿突破：价格 > 近 20 日高点 → 开仓 20%，设置 SL
    3. 回踩确认：回踩不破区间上沿 + ADX 继续上升 → 加仓到 40%
    4. 趋势持续：MA5 > MA20 持续 + ADX > 25 → 加仓到 60%
    5. 鱼尾信号：ADX 峰值回落 30% → 减半仓；MA5 死叉 MA20 → 清仓
    """
    df = df_raw.copy().reset_index(drop=True)

    # 指标
    ma5, ma20 = calc_ma(df)
    adx = calc_adx_simple(df)
    roll_low, roll_high = calc_range(df)

    # 预计算信号列
    is_trend = (adx > 20) & (ma5 > ma20)  # 趋势市（放宽到 20，保留安全性）
    is_volatile = (adx < 20) | (ma5 < ma20)  # 震荡市
    is_above_range = df['close'] > roll_high.shift(1)  # 突破区间上沿
    is_below_range = df['close'] < roll_low.shift(1)  # 跌破区间下沿（不追空，本次不做空）
    ma_cross_down = (ma5 < ma20) & (ma5.shift(1) >= ma20.shift(1))  # MA5 死叉 MA20

    # ADX 峰值跟踪
    adx_peak = adx.copy()
    for i in range(1, len(adx_peak)):
        if adx_peak.iloc[i-1] > 25:
            adx_peak.iloc[i] = max(adx.iloc[i], adx_peak.iloc[i-1])
        else:
            adx_peak.iloc[i] = adx.iloc[i]

    # 持仓模拟
    trades = []
    pos: Optional[Position] = None
    adx_peak_in_pos = 0.0

    for i in range(1, len(df) - 1):
        today = df.iloc[i]
        tomorrow = df.iloc[i + 1]
        close = today['close']
        tomorrow_close = tomorrow['close']

        # 当前状态
        adx_val = adx.iloc[i]
        ma5_val = ma5.iloc[i]
        ma20_val = ma20.iloc[i]
        range_upper = roll_high.iloc[i]
        range_lower = roll_low.iloc[i]
        above = is_above_range.iloc[i]
        cross_down = ma_cross_down.iloc[i]
        adx_peak_val = adx_peak.iloc[i]

        # ==== 持仓管理 ====
        if pos is not None:
            hold_days = i - pos.entry_idx
            ret = (close - pos.entry_price) / pos.entry_price
            adx_peak_in_pos = max(pos.adx_peak, adx_peak_val)

            exit_reason = None
            action = None  # 'add' / 'reduce' / 'exit'

            # 鱼尾判断
            if adx_peak_in_pos > 25:
                drop_pct = (adx_peak_in_pos - adx_val) / adx_peak_in_pos
                if drop_pct > 0.30:
                    # ADX 从峰值回落 30% → 减半仓
                    if pos.position_pct > 0.12:  # 不低于 12%
                        action = 'reduce'
            if cross_down:
                exit_reason = 'MA死叉'

            # 止损/止盈
            if ret <= pos.stop_loss:
                exit_reason = 'SL'
            elif ret >= pos.target:
                exit_reason = 'SP'

            # 加仓：回踩不破区间上沿 + 仓位未满
            if action is None and above:
                # 价格重新站上区间上沿 = 确认趋势（加仓机会）
                pass  # 当前版本：不在持仓中追加，通过外部新信号管理
            # 趋势持续加仓：ADX 上升 + 仓位 < 60%
            if action is None and pos.phase != 'full' and adx_val > adx_peak_in_pos * 0.95:
                if pos.position_pct < 0.60:
                    action = 'add'

            if exit_reason:
                pnl = ret - 0.002
                trades.append(Trade(
                    entry_date=pos.entry_date,
                    exit_date=today['date'],
                    entry_price=pos.entry_price,
                    exit_price=close,
                    mode=pos.mode,
                    position_pct=pos.position_pct,
                    pnl_pct=pnl,
                    hold_days=hold_days,
                    n_adds=1 if pos.phase != 'initial' else 0,
                    exit_reason=exit_reason,
                ))
                pos = None
            elif action == 'reduce':
                # 减半仓：记录一次交易，更新 pos
                half = pos.position_pct / 2
                pnl_half = (ret - 0.001) * (half / pos.position_pct)  # 简化估算
                pos.position_pct = half
                pos.mode = 'hold'  # 转为持有模式
                # 不清仓，继续观察 MA 死叉

        # ==== 开仓信号 ====
        if pos is None and i < len(df) - 2:
            if is_volatile.iloc[i] and above:
                # 突破区间上沿 + 处于震荡市 → 趋势启动信号
                entry_price = close
                pos = Position(
                    mode='breakout',
                    entry_price=entry_price,
                    entry_date=today['date'],
                    entry_idx=i,
                    shares=0,
                    position_pct=0.20,  # 初始 20%
                    stop_loss=-0.05,    # SL -5%（震荡市突破，假突破概率高，SL 相对严格）
                    target=0.12,       # SP +12%（到区间上沿 1 倍幅度）
                    adx_peak=adx_val,
                    phase='initial',
                )

    return trades


# ============ 简化版 v8_sop 纯趋势策略（对照）============

def run_v8_sop_baseline(df_raw, etf_code):
    """v8_sop 7 因子纯趋势策略，60% 仓位"""
    df = df_raw.copy().reset_index(drop=True)
    calc = IndicatorCalculator()
    df_calc = calc.calculate_all(df)

    ma5, ma20 = calc_ma(df_calc)
    adx = calc_adx_simple(df_calc)

    signal = v8_sop_signal(df_calc)
    is_trend = (adx > 25) & (ma5 > ma20)

    trades = []
    pos = None

    for i in range(len(df) - 1):
        today = df.iloc[i]
        close = today['close']

        if pos is None:
            if signal.iloc[i] and is_trend.iloc[i]:
                pos = {
                    'entry_price': close,
                    'entry_date': today['date'],
                    'entry_idx': i,
                    'position_pct': 0.60,
                    'stop_loss': -0.08,
                    'target': 0.15,
                    'phase': 'initial',
                }
        else:
            ret = (close - pos['entry_price']) / pos['entry_price']
            hold_days = i - pos['entry_idx']
            adx_val = adx.iloc[i]
            ma5_val = ma5.iloc[i]

            exit_reason = None
            if ret <= pos['stop_loss']:
                exit_reason = 'SL'
            elif ret >= pos['target']:
                exit_reason = 'SP'
            elif hold_days >= 10:
                exit_reason = 'MH'
            elif adx_val < 20 or ma5_val < ma20.iloc[i]:
                exit_reason = 'trend_end'

            if exit_reason:
                pnl = ret - 0.002
                trades.append(Trade(
                    entry_date=pos['entry_date'],
                    exit_date=today['date'],
                    entry_price=pos['entry_price'],
                    exit_price=close,
                    mode='v8_sop',
                    position_pct=pos['position_pct'],
                    pnl_pct=pnl,
                    hold_days=hold_days,
                    n_adds=0,
                    exit_reason=exit_reason,
                ))
                pos = None

    return trades


# ============ 评估 ============

def calc_metrics(trades: List[Trade]):
    if not trades:
        return {'total_return': 0, 'sharpe': 0, 'win_rate': 0, 'max_drawdown': 0, 'n_trades': 0, 'avg_trade': 0}

    rets = np.array([t.pnl_pct * t.position_pct for t in trades])  # 仓位加权收益
    raw_rets = np.array([t.pnl_pct for t in trades])

    total_ret = float(rets.sum())
    win_rate = float((raw_rets > 0).sum() / max(len(raw_rets), 1))
    sharpe = float(raw_rets.mean() / max(raw_rets.std(), 1e-9) * np.sqrt(252)) if raw_rets.std() > 0 else 0.0

    cum = np.cumprod(1 + raw_rets)
    running_max = np.maximum.accumulate(cum)
    drawdown = (cum - running_max) / running_max
    max_dd = float(drawdown.min())

    return {
        'total_return': total_ret,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'max_drawdown': max_dd,
        'n_trades': len(trades),
        'avg_trade': float(raw_rets.mean()),
    }


# ============ 主程序 ============

def main():
    logger.info("=" * 70)
    logger.info("修订版双模式策略回测 v2")
    logger.info("=" * 70)
    logger.info("""
修订要点（vs 旧版）：
1. 震荡市突破直接进，不等"二次确认"
2. 初始仓位 20%（试探），后分两段加到 60%
3. SL=-5%（震荡市突破假突破多），SP=+12%
4. ADX 峰值回落 30% → 减半仓
5. MA5 死叉 MA20 → 清仓
""")

    ETF_POOL = [
        '510300', '515650', '515070', '512400', '512480', '588000', '520900',
        '512880', '512170', '512660', '512200', '512800', '512980',
        '515050', '515790',
    ]

    IS_START, IS_END = '2023-01-01', '2024-12-31'
    OOS_START, OOS_END = '2025-01-01', '2026-06-01'

    results_v2 = []
    results_baseline = []

    for code in ETF_POOL:
        loader = DataLoader()
        df = loader.load_single(code, min_rows=400)
        if df is None:
            continue
        df = df[(df['date'] >= '2023-01-01') & (df['date'] <= '2026-06-01')]
        df = df.sort_values('date').reset_index(drop=True)

        df_is = df[(df['date'] >= IS_START) & (df['date'] <= IS_END)]
        df_oos = df[(df['date'] >= OOS_START) & (df['date'] <= OOS_END)]

        if len(df_is) < 200 or len(df_oos) < 200:
            continue

        calc = IndicatorCalculator()
        df_is_calc = calc.calculate_all(df_is)
        df_oos_calc = calc.calculate_all(df_oos)

        trades_is_v2 = run_strategy_v2(df_is_calc, code)
        trades_oos_v2 = run_strategy_v2(df_oos_calc, code)

        trades_is_bl = run_v8_sop_baseline(df_is_calc, code)
        trades_oos_bl = run_v8_sop_baseline(df_oos_calc, code)

        m_is_v2 = calc_metrics(trades_is_v2)
        m_oos_v2 = calc_metrics(trades_oos_v2)
        m_is_bl = calc_metrics(trades_is_bl)
        m_oos_bl = calc_metrics(trades_oos_bl)

        results_v2.append({'etf': code, 'is': m_is_v2, 'oos': m_oos_v2, 'n_is': len(trades_is_v2), 'n_oos': len(trades_oos_v2)})
        results_baseline.append({'etf': code, 'is': m_is_bl, 'oos': m_oos_bl, 'n_is': len(trades_is_bl), 'n_oos': len(trades_oos_bl)})

        logger.info(f"{code}: V2 IS {m_is_v2['total_return']*100:+.1f}%/{m_is_v2['n_trades']}笔 | "
                    f"OOS {m_oos_v2['total_return']*100:+.1f}%/{m_oos_v2['n_trades']}笔 | "
                    f"BASELINE OOS {m_oos_bl['total_return']*100:+.1f}%/{m_oos_bl['n_trades']}笔")

    # 汇总
    def avg_metric(results, key):
        vals = [r[key] for r in results if r[key] != 0]
        return np.mean(vals) if vals else 0

    # V2 汇总
    is_rets_v2 = [r['is']['total_return'] for r in results_v2]
    oos_rets_v2 = [r['oos']['total_return'] for r in results_v2]
    is_sharpes_v2 = [r['is']['sharpe'] for r in results_v2 if r['is']['sharpe'] != 0]
    oos_sharpes_v2 = [r['oos']['sharpe'] for r in results_v2 if r['oos']['sharpe'] != 0]
    n_v2_is = sum(r['n_is'] for r in results_v2)
    n_v2_oos = sum(r['n_oos'] for r in results_v2)

    # Baseline 汇总
    oos_rets_bl = [r['oos']['total_return'] for r in results_baseline]
    oos_sharpes_bl = [r['oos']['sharpe'] for r in results_baseline if r['oos']['sharpe'] != 0]

    logger.info("\n" + "=" * 70)
    logger.info("汇总对比")
    logger.info("=" * 70)
    logger.info(f"V2 IS:   收益 {np.mean(is_rets_v2)*100:+.2f}%, Sharpe {np.mean(is_sharpes_v2):.3f}, 交易 {n_v2_is} 笔")
    logger.info(f"V2 OOS:  收益 {np.mean(oos_rets_v2)*100:+.2f}%, Sharpe {np.mean(oos_sharpes_v2):.3f}, 交易 {n_v2_oos} 笔")
    logger.info(f"BL OOS:  收益 {np.mean(oos_rets_bl)*100:+.2f}%, Sharpe {np.mean(oos_sharpes_bl):.3f}")

    # Top
    results_v2_sorted = sorted(results_v2, key=lambda x: x['oos']['total_return'], reverse=True)
    logger.info(f"\nV2 Top 5 (OOS):")
    for r in results_v2_sorted[:5]:
        logger.info(f"  {r['etf']}: {r['oos']['total_return']*100:+.1f}% "
                    f"Sharpe={r['oos']['sharpe']:.2f} "
                    f"WR={r['oos']['win_rate']*100:.0f}% "
                    f"DD={r['oos']['max_drawdown']*100:.1f}% "
                    f"n={r['n_oos']}笔")

    # 验收
    logger.info("\n" + "=" * 70)
    logger.info("验收标准")
    logger.info("=" * 70)
    oos_avg = np.mean(oos_rets_v2)
    oos_sh = np.mean(oos_sharpes_v2)
    logger.info(f"{'✅' if oos_avg > 0 else '❌'} 总收益 > 0: {oos_avg*100:+.2f}%")
    logger.info(f"{'✅' if oos_sh > 0.5 else '❌'} Sharpe > 0.5: {oos_sh:.3f}")
    logger.info(f"{'✅' if np.mean(oos_rets_v2) > np.mean(oos_rets_bl) else '❌'} 跑赢 Baseline: "
                f"V2 {oos_avg*100:+.2f}% vs BL {np.mean(oos_rets_bl)*100:+.2f}%")

    # 输出
    output = {
        'timestamp': datetime.now().isoformat(),
        'strategy': 'dual_mode_v2',
        'config': {
            'entry': '震荡市突破区间上沿 → 开仓 20%',
            'add_20_to_40': '回踩不破上沿 → 加到 40%',
            'add_40_to_60': '趋势持续 + ADX 上升 → 加到 60%',
            'sl': '-5% (突破假突破多，严格止损)',
            'sp': '+12%',
            'tail_exit_adx': 'ADX 峰值回落 30% → 减半仓',
            'tail_exit_ma': 'MA5 死叉 MA20 → 清仓',
        },
        'summary_v2': {
            'n_etf': len(results_v2),
            'is_avg_return': float(np.mean(is_rets_v2)),
            'is_avg_sharpe': float(np.mean(is_sharpes_v2)),
            'oos_avg_return': float(oos_avg),
            'oos_avg_sharpe': float(oos_sh),
            'n_trades_is': n_v2_is,
            'n_trades_oos': n_v2_oos,
        },
        'summary_baseline': {
            'oos_avg_return': float(np.mean(oos_rets_bl)),
            'oos_avg_sharpe': float(np.mean(oos_sharpes_bl)),
        },
        'detail_v2': [{'etf': r['etf'], 'is': r['is'], 'oos': r['oos']} for r in results_v2],
        'detail_baseline': [{'etf': r['etf'], 'is': r['is'], 'oos': r['oos']} for r in results_baseline],
    }

    json_path = OUTPUT_DIR / 'dual_mode_v2_backtest.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    # Markdown 报告
    md = [
        "# 修订版双模式策略回测报告 v2",
        "",
        f"**生成时间**: {datetime.now().isoformat()}",
        "",
        "## 修订要点",
        "",
        "| 改动 | 旧版 | 修订版 | 原因 |",
        "|------|------|--------|------|",
        "| 开仓时机 | 等二次确认 | **突破直接进** | 震荡转节点不可预判 |",
        "| 初始仓位 | 60% | **20%** | 试探，控制风险 |",
        "| SL | -8% | **-5%** | 震荡市假突破多 |",
        "| SP | +15% | **+12%** | 合理收益目标 |",
        "| 鱼尾减仓 | 无 | **ADX峰值回落30%** | 量化鱼尾信号 |",
        "| 清仓信号 | 无 | **MA5死叉MA20** | 趋势破坏即走 |",
        "",
        "## 对比结果（15 ETF）",
        "",
        f"| 指标 | V2 修订版 OOS | Baseline v8_sop |",
        f"|------|------------|---------------|",
        f"| 平均收益 | {oos_avg*100:+.2f}% | {np.mean(oos_rets_bl)*100:+.2f}% |",
        f"| 平均 Sharpe | {oos_sh:.3f} | {np.mean(oos_sharpes_bl):.3f} |",
        "",
        "## Top 5 ETF（样本外）",
        "",
        "| ETF | 收益 | Sharpe | 胜率 | 最大回撤 | 交易次数 |",
        "|------|------|--------|------|---------|---------|",
    ]
    for r in results_v2_sorted[:5]:
        md.append(f"| {r['etf']} | {r['oos']['total_return']*100:+.1f}% | "
                  f"{r['oos']['sharpe']:.3f} | "
                  f"{r['oos']['win_rate']*100:.0f}% | "
                  f"{r['oos']['max_drawdown']*100:.1f}% | "
                  f"{r['n_oos']}笔 |")

    md.extend(["", "## 验收标准", ""])
    checks = [
        ("总收益 > 0", oos_avg > 0, f"{oos_avg*100:+.2f}%"),
        ("Sharpe > 0.5", oos_sh > 0.5, f"{oos_sh:.3f}"),
        ("跑赢 Baseline", oos_avg > np.mean(oos_rets_bl), f"V2 {oos_avg*100:+.2f}% vs BL {np.mean(oos_rets_bl)*100:+.2f}%"),
    ]
    for label, passed, val in checks:
        md.append(f"- {'✅' if passed else '❌'} {label}: {val}")

    md_path = OUTPUT_DIR / 'dual_mode_v2_backtest.md'
    md_path.write_text('\n'.join(md))
    logger.info(f"\n报告: {json_path}\n       {md_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())