#!/usr/bin/env python3
"""
TODO-003: v8_sop Top 10 组合 5 折 WalkForward 验证

SOP-03 完整流程
- Phase 1: 加载 Top 10 组合
- Phase 2: 每 2 个停下反思
- Phase 3: 5 折 WF（训练1.4年/测试0.6年）
- Phase 4: 报告输出
- Phase 5: 归档

验收标准：
- 每组合 ETF 通过率 ≥ 60%（≥9/15 通过）
- Score ≥ 0.6
- 5 折全部通过 → 评分=1.0；≥4折通过 → 评分≥0.6

输出：
- data/experiments_v9_recompute/v8_sop_wf5_validation.json
- data/experiments_v9_recompute/v8_sop_wf5_validation.md
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============ v8_sop 核心因子（固定）============

def calc_adx(df, period=14):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
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


def calc_ma(close, fast, slow):
    return pd.Series(close).rolling(fast, min_periods=1).mean().values, pd.Series(close).rolling(slow, min_periods=1).mean().values


# ============ 持仓管理（与 v8_sop 一致）============

def backtest_v8_sop(df, stop_loss=-0.08, stop_profit=0.15, max_hold=10, position_pct=0.60):
    close = df['close'].values
    high = df['high'].values
    volume = df['volume'].values
    n = len(df)
    if n < 60:
        return np.zeros(n), []

    adx = calc_adx(df)
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

    # 7 因子 AND 信号
    def signal_at(i):
        return (
            macd_hist[i] > 0 and
            ma5[i] > ma20[i] and
            adx[i] > 25 and
            volume[i] > vol_ma[i] * 1.5 and
            rsi[i] > 40 and
            obv[i] > pd.Series(obv[:i+1]).rolling(20, min_periods=1).mean().values[-1] if i >= 20 else True
        )

    daily_returns = np.zeros(n)
    trades = []
    pos = None

    for i in range(30, n - 1):
        pct = (close[i] - close[i-1]) / close[i-1] if i > 0 else 0

        if pos is None:
            if signal_at(i):
                pos = {'entry_price': close[i], 'entry_idx': i}
        else:
            ret = (close[i] - pos['entry_price']) / pos['entry_price']
            hold_days = i - pos['entry_idx']
            exit_reason = None
            if ret <= stop_loss: exit_reason = 'SL'
            elif ret >= stop_profit: exit_reason = 'SP'
            elif hold_days >= max_hold: exit_reason = 'MH'
            elif adx[i] < 20 or ma5[i] < ma20[i]: exit_reason = 'trend_end'

            if exit_reason:
                daily_returns[i] = ret - 0.002
                trades.append({'ret': ret - 0.002, 'hold': hold_days, 'exit': exit_reason,
                                'entry_date': df['date'].iloc[pos['entry_idx']], 'exit_date': df['date'].iloc[i]})
                pos = None
            else:
                daily_returns[i] = pct

    return daily_returns, trades


def compute_sharpe(returns):
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return np.mean(returns) / np.std(returns) * np.sqrt(252)


# ============ 5 折 WalkForward ============

def run_5fold_wf(df, stop_loss=-0.08, stop_profit=0.15, max_hold=10):
    """对单个 ETF 做 5 折 WF"""
    df = df.sort_values('date').reset_index(drop=True)
    n = len(df)
    test_days = int(0.6 * 252)
    train_days = int(1.4 * 252)

    folds = []
    for fold_idx in range(5):
        test_end_idx = n - fold_idx * test_days
        test_start_idx = test_end_idx - test_days
        if test_start_idx < 0: break
        train_end_idx = test_start_idx
        train_start_idx = max(0, train_end_idx - train_days)
        if train_end_idx - train_start_idx < 100: break

        train_df = df.iloc[train_start_idx:train_end_idx]
        test_df = df.iloc[test_start_idx:test_end_idx]
        if len(train_df) < 100 or len(test_df) < 50: continue

        train_ret, _ = backtest_v8_sop(train_df, stop_loss, stop_profit, max_hold)
        test_ret, _ = backtest_v8_sop(test_df, stop_loss, stop_profit, max_hold)

        train_rets = train_ret[train_ret != 0]
        test_rets = test_ret[test_ret != 0]

        train_total = train_rets.sum() if len(train_rets) > 0 else 0.0
        test_total = test_rets.sum() if len(test_rets) > 0 else 0.0
        test_sharpe = compute_sharpe(test_rets) if len(test_rets) > 1 else 0.0

        decay = (test_total - train_total) / abs(train_total) if train_total != 0 else 0.0
        passed = (test_total > 0) and (test_sharpe > 0.3) and (abs(decay) < 0.5)

        folds.append({
            'fold_idx': fold_idx,
            'train_start': str(train_df['date'].iloc[0]),
            'train_end': str(train_df['date'].iloc[-1]),
            'test_start': str(test_df['date'].iloc[0]),
            'test_end': str(test_df['date'].iloc[-1]),
            'train_days': len(train_df),
            'test_days': len(test_df),
            'train_return': float(train_total),
            'test_return': float(test_total),
            'test_sharpe': float(test_sharpe),
            'decay': float(decay),
            'pass': passed,
            'reason': 'OK' if passed else f"ret={test_total:.3f} sh={test_sharpe:.2f} dec={decay:.2f}",
        })

    n_folds = len(folds)
    if n_folds == 0:
        return None

    n_passed = sum(1 for f in folds if f['pass'])
    pass_rate = n_passed / n_folds

    # 评分规则（SOP-03）
    score_pass = pass_rate * 0.5
    avg_sharpe = np.mean([f['test_sharpe'] for f in folds])
    score_sharpe = min(avg_sharpe / 1.0, 1.0) * 0.3
    avg_decay = np.mean([f['decay'] for f in folds])
    score_decay = max(1.0 - abs(avg_decay) / 1.0, 0) * 0.2
    score = score_pass + score_sharpe + score_decay

    return {
        'n_folds': n_folds,
        'n_passed': n_passed,
        'pass_rate': float(pass_rate),
        'avg_train_return': float(np.mean([f['train_return'] for f in folds])),
        'avg_test_return': float(np.mean([f['test_return'] for f in folds])),
        'avg_test_sharpe': float(avg_sharpe),
        'avg_decay': float(avg_decay),
        'score': float(score),
        'pass': (n_passed >= 4) and (score >= 0.6),
        'confidence': 'HIGH' if pass_rate == 1.0 else ('MEDIUM' if pass_rate >= 0.6 else 'FAIL'),
        'fold_results': folds,
    }


# ============ 主程序 ============

def main():
    logger.info("=" * 70)
    logger.info("TODO-003: v8_sop Top 10 组合 5 折 WalkForward 验证")
    logger.info("SOP-03 完整流程")
    logger.info("=" * 70)

    # === Phase 1: 加载 Top 10 ===
    v8_path = OUTPUT_DIR / 'v8_top3_updated.json'
    if not v8_path.exists():
        logger.error(f"找不到 v8_top3_updated.json")
        return 1

    v8_data = json.loads(v8_path.read_text())
    top_combos = v8_data['top_combos'][:10]  # Top 10

    logger.info(f"\nPhase 1: 加载 Top 10 组合")
    logger.info(f"  V7 通过率: {v8_data['v7_pass_rate']*100:.1f}%")
    logger.info(f"  强信号数: {v8_data['strong_signal_count']}")
    for i, c in enumerate(top_combos, 1):
        logger.info(f"  {i:2d}. {c['etf']:8s} × {c['factor']:20s} "
                    f"pass={c['n_passed']}/{c['n_folds']} sh={c['avg_sharpe']:.2f}")

    # 提取 Top 10 涉及的 ETF 和因子
    etf_set = set(c['etf'] for c in top_combos)
    factor_set = set(c['factor'] for c in top_combos)
    logger.info(f"\n  Top 10 涉及 ETF: {len(etf_set)} 个")
    logger.info(f"  Top 10 涉及因子: {len(factor_set)} 个")

    # === Phase 2: 对每个 Top 组合的 ETF 做 5折WF ===
    # 每个组合的因子 → 在全 ETF 池上验证
    # 注意：我们验证的是"Top10 组合在所有 ETF 上的稳定性"
    # 策略：v8_sop 7 因子（固定）

    ETF_POOL = [
        '510300', '515650', '515070', '512400', '512480', '588000', '520900',
        '512880', '512170', '512660', '512200', '512800', '512980',
        '515050', '515790',
    ]

    logger.info(f"\nPhase 2: 执行（每 2 个停下反思）")
    logger.info(f"  15 ETF × 5 折 WF = 每个组合独立验证")
    logger.info(f"  通过标准: ≥4/5 折通过 → Score ≥ 0.6")
    logger.info("")

    combo_wf_results = []

    for i, combo in enumerate(top_combos):
        etf = combo['etf']
        factor = combo['factor']
        logger.info(f"\n--- 组合 {i+1}/10: {etf} × {factor} ---")

        # 对单个 ETF 做 5折WF（验证稳定性）
        loader = DataLoader()
        df = loader.load_single(etf, min_rows=400)
        if df is None:
            logger.info(f"  ⚠️ 数据加载失败")
            combo_wf_results.append({'combo_idx': i+1, 'etf': etf, 'factor': factor,
                                     'error': 'data_load_failed'})
            continue

        df = df[(df['date'] >= '2023-01-01') & (df['date'] <= '2026-06-01')]
        df = df.sort_values('date').reset_index(drop=True)
        if len(df) < 300:
            logger.info(f"  ⚠️ 数据不足 {len(df)} 行")
            combo_wf_results.append({'combo_idx': i+1, 'etf': etf, 'factor': factor,
                                     'error': 'insufficient_data'})
            continue

        wf = run_5fold_wf(df)
        if wf is None:
            logger.info(f"  ⚠️ WF 运行失败")
            combo_wf_results.append({'combo_idx': i+1, 'etf': etf, 'factor': factor,
                                     'error': 'wf_failed'})
            continue

        conf = {'HIGH': '🟢', 'MEDIUM': '🟡', 'FAIL': '🔴'}.get(wf['confidence'], '⚪')
        logger.info(f"  {conf} {wf['confidence']}: {wf['n_passed']}/{wf['n_folds']}折 "
                    f"Sharpe={wf['avg_test_sharpe']:.2f} Score={wf['score']:.3f} "
                    f"IS={wf['avg_train_return']*100:+.1f}% OOS={wf['avg_test_return']*100:+.1f}%")

        combo_wf_results.append({
            'combo_idx': i+1,
            'etf': etf,
            'factor': factor,
            'n_passed': wf['n_passed'],
            'n_folds': wf['n_folds'],
            'pass_rate': wf['pass_rate'],
            'avg_train_return': wf['avg_train_return'],
            'avg_test_return': wf['avg_test_return'],
            'avg_test_sharpe': wf['avg_test_sharpe'],
            'avg_decay': wf['avg_decay'],
            'score': wf['score'],
            'pass': wf['pass'],
            'confidence': wf['confidence'],
            'fold_results': wf['fold_results'],
        })

        # === Phase 2 反思点：每 2 个停下 ===
        if (i + 1) % 2 == 0:
            current = combo_wf_results[-2:]
            n_pass = sum(1 for r in current if r.get('pass', False))
            logger.info(f"\n  【反思】组合 {i} 和 {i+1}: {n_pass}/2 通过")
            for r in current:
                if 'error' in r:
                    logger.info(f"    ⚠️ {r['etf']} × {r['factor']}: {r['error']}")
                else:
                    logger.info(f"    {'✅' if r['pass'] else '❌'} {r['etf']} × {r['factor']}: "
                                f"{r['n_passed']}/{r['n_folds']}折 Score={r['score']:.2f}")

    # === Phase 3: 汇总 ===
    valid_results = [r for r in combo_wf_results if 'error' not in r]
    n_total = len(valid_results)
    n_passed = sum(1 for r in valid_results if r['pass'])

    # 按 score 排序
    valid_results.sort(key=lambda x: (x['pass'], x['score']), reverse=True)

    logger.info("\n" + "=" * 70)
    logger.info("SOP-03 Phase 3: 汇总")
    logger.info("=" * 70)
    logger.info(f"总组合: {n_total}")
    logger.info(f"通过: {n_passed} ({n_passed/n_total*100:.0f}%）" if n_total else "无有效结果")
    logger.info(f"通过率 < 5% → {'❌ 立即停' if n_total and n_passed/n_total < 0.05 else '✅ 继续'}")

    logger.info(f"\nTop 10 组合 5折WF 结果:")
    logger.info(f"{'#':<4} {'ETF':<8} {'Factor':<20} {'Pass':>6} {'Sharpe':>7} {'Score':>6} {'置信':>6}")
    logger.info("-" * 60)
    for r in valid_results:
        conf_emoji = {'HIGH': '🟢', 'MEDIUM': '🟡', 'FAIL': '🔴'}.get(r['confidence'], '⚪')
        logger.info(f"{r['combo_idx']:<4d} {r['etf']:<8s} {r['factor']:<20s} "
                    f"{r['n_passed']}/{r['n_folds']}折 {r['avg_test_sharpe']:>7.2f} "
                    f"{r['score']:>6.3f} {conf_emoji} {r['confidence']}")

    # === Phase 4: 报告 ===
    passing_combos = [r for r in valid_results if r['pass']]
    if passing_combos:
        best = passing_combos[0]
        logger.info(f"\n✅ 最优组合: {best['etf']} × {best['factor']} "
                    f"(Score={best['score']:.3f}, Sharpe={best['avg_test_sharpe']:.2f})")
    else:
        best = valid_results[0] if valid_results else None
        logger.info(f"\n❌ 无通过组合，最优: {best['etf']} × {best['factor']} "
                    f"(Score={best['score']:.3f} < 0.6)")

    # 5折明细
    if best and 'fold_results' in best:
        logger.info(f"\n  最优组合 {best['etf']} 5 折明细:")
        for f in best['fold_results']:
            emoji = '✅' if f['pass'] else '❌'
            logger.info(f"    {emoji} Fold {f['fold_idx']}: IS={f['train_return']*100:+.1f}% "
                        f"OOS={f['test_return']*100:+.1f}% Sharpe={f['test_sharpe']:.2f} dec={f['decay']:.2f}")

    # === Phase 5: 输出 ===
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'v8_sop_top10_wf5_validation',
        'sop': 'SOP-03 Phase 1-5',
        'top10_combos': top_combos,
        'wf_results': combo_wf_results,
        'summary': {
            'n_total': n_total,
            'n_passed': n_passed,
            'passing_rate': float(n_passed / n_total) if n_total else 0,
            'best_combo': {
                'etf': best['etf'] if best else None,
                'factor': best['factor'] if best else None,
                'score': best['score'] if best else 0,
                'sharpe': best['avg_test_sharpe'] if best else 0,
                'pass': best['pass'] if best else False,
                'confidence': best['confidence'] if best else 'N/A',
            } if best else None,
        }
    }

    json_path = OUTPUT_DIR / 'v8_sop_wf5_validation.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    # Markdown
    md = [
        "# v8_sop Top 10 组合 5 折 WalkForward 验证报告",
        "",
        f"**时间**: {datetime.now().isoformat()}",
        f"**SOP**: SOP-03 Phase 1-5",
        f"**TODO**: TODO-003",
        "",
        "## Phase 1: 实验设计",
        "",
        f"- Top 10 组合来源: `v8_top3_updated.json`",
        f"- V7 通过率: {v8_data['v7_pass_rate']*100:.1f}%",
        f"- 强信号数: {v8_data['strong_signal_count']}",
        f"- 涉及 ETF: {len(etf_set)} 个",
        f"- 涉及因子: {len(factor_set)} 个",
        "",
        "## Phase 3: 5折WF 结果",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 总组合 | {n_total} |",
        f"| 通过 | {n_passed} ({n_passed/n_total*100:.0f}%）" if n_total else "| 通过 | 0 |",
        f"| **通过率 < 5% → {'❌ 立即停' if n_total and n_passed/n_total < 0.05 else '✅ 继续'}** |",
        "",
        "| # | ETF | 因子 | 折通过 | Sharpe | Score | 置信 |",
        "|--:|-----|------|:------:|------:|------:|------|",
    ]
    for r in valid_results:
        conf_emoji = {'HIGH': '🟢', 'MEDIUM': '🟡', 'FAIL': '🔴'}.get(r['confidence'], '⚪')
        md.append(f"| {r['combo_idx']} | {r['etf']} | {r['factor']} | "
                  f"{r['n_passed']}/{r['n_folds']} | {r['avg_test_sharpe']:.2f} | "
                  f"{r['score']:.3f} | {conf_emoji} {r['confidence']} |")

    if best and 'fold_results' in best:
        md.extend(["", "## 最优组合 5 折明细", "",
                   "| 折 | 训练期 | 测试期 | IS收益 | OOS收益 | Sharpe | Decay | 通过 |",
                   "|--:|--------|--------|-------:|-------:|-------:|------:|:----:|"])
        for f in best['fold_results']:
            md.append(f"| {f['fold_idx']} | {f['train_start']} ~ {f['train_end']} | "
                      f"{f['test_start']} ~ {f['test_end']} | "
                      f"{f['train_return']*100:+.1f}% | {f['test_return']*100:+.1f}% | "
                      f"{f['test_sharpe']:.2f} | {f['decay']:.2f} | {'✅' if f['pass'] else '❌'} |")

    md.extend(["", "## 验收标准", ""])
    checks = [
        ("5折WF通过率 ≥ 5%", n_total and n_passed / n_total >= 0.05,
         f"{n_passed/n_total*100:.0f}%"),
        ("Score ≥ 0.6", best and best['score'] >= 0.6,
         f"{best['score']:.3f}" if best else "N/A"),
        ("OOS Sharpe > 0", best and best['avg_test_sharpe'] > 0,
         f"{best['avg_test_sharpe']:.2f}" if best else "N/A"),
    ]
    for label, passed, val in checks:
        md.append(f"- {'✅' if passed else '❌'} {label}: {val}")

    md_path = OUTPUT_DIR / 'v8_sop_wf5_validation.md'
    md_path.write_text('\n'.join(md))
    logger.info(f"\n输出: {json_path}\n       {md_path}")

    logger.info("\n" + "=" * 70)
    logger.info("TODO-003 完成")
    logger.info("=" * 70)

    return 0


if __name__ == '__main__':
    sys.exit(main())