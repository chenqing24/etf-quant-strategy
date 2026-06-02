#!/usr/bin/env python3
"""
SOP-03 Phase 3: 过拟合检验（对 Top 10 参数组合）

对 Phase 1+2 找出的 Top 10 参数组合做 5 折 WalkForward 验证

规则（教训28）：
- 必须全部 5 折通过（或至少 4/5）才算验证通过
- 通过率 < 5% → 立即停 + 反思机制
- 5 折是过拟合的可靠检测器

输出：
- data/experiments_v9_recompute/market_regime_wf5_validation.json
- data/experiments_v9_recompute/market_regime_wf5_validation.md
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============ 指标计算（与 Phase 1 保持一致）============

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


# ============ 5 折 WalkForward（带 SL/SP 的完整持仓管理）============

def backtest_with_position(df, adx_thresh_trend=20, adx_thresh_volatile=15,
                           ma_fast=10, ma_slow=30,
                           position_pct=0.60, stop_loss=-0.08, stop_profit=0.15,
                           max_hold=10):
    """带完整持仓管理的策略回测（返回每日收益序列）"""
    close = df['close'].values
    high = df['high'].values
    volume = df['volume'].values
    n = len(df)
    if n < 60:
        return np.zeros(n), 0

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
    vol_ma = pd.Series(volume).rolling(20, min_periods=1).mean().values
    signal = (
        (macd_hist > 0) &
        (ma_fast_arr > ma_slow_arr) &
        (adx > adx_thresh_trend) &
        (volume > vol_ma * 1.5) &
        (rsi > 40) &
        (obv > pd.Series(obv).rolling(20, min_periods=1).mean().values)
    )

    # 每日收益（0 = 空仓，非0 = 持仓）
    daily_returns = np.zeros(n)
    pos = None

    for i in range(30, n - 1):
        pct = (close[i] - close[i-1]) / close[i-1] if i > 0 else 0

        if pos is None:
            if is_trend[i] and signal[i]:
                pos = {
                    'entry_price': close[i],
                    'entry_idx': i,
                    'mode': 'trend',
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
            elif not is_trend[i]:
                exit_reason = 'trend_end'

            if exit_reason:
                # 平仓日标记当天为持仓
                daily_returns[i] = (close[i] - pos['entry_price']) / pos['entry_price'] - 0.002
                pos = None
            else:
                daily_returns[i] = pct

    return daily_returns, 1 if pos is not None else 0


def compute_sharpe(returns):
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return np.mean(returns) / np.std(returns) * np.sqrt(252)


def run_5fold_wf(df, adx_trend, adx_volatile, ma_fast, ma_slow, min_windows=5):
    """
    5 折 WalkForward 验证
    返回每折的 train/test 指标
    """
    df = df.sort_values('date').reset_index(drop=True)
    n = len(df)

    test_days = int(0.6 * 252)   # 0.6 年
    train_days = int(1.4 * 252)  # 1.4 年

    folds = []
    for fold_idx in range(min_windows):
        test_end_idx = n - fold_idx * test_days
        test_start_idx = test_end_idx - test_days
        if test_start_idx < 0:
            break
        train_end_idx = test_start_idx
        train_start_idx = max(0, train_end_idx - train_days)
        if train_end_idx - train_start_idx < 100:
            break

        folds.append({
            'fold_idx': fold_idx,
            'train_df': df.iloc[train_start_idx:train_end_idx],
            'test_df': df.iloc[test_start_idx:test_end_idx],
        })

    fold_results = []
    for fold in folds:
        train_ret, _ = backtest_with_position(
            fold['train_df'], adx_trend, adx_volatile, ma_fast, ma_slow)
        test_ret, _ = backtest_with_position(
            fold['test_df'], adx_trend, adx_volatile, ma_fast, ma_slow)

        # 过滤持仓日收益
        train_rets = train_ret[train_ret != 0]
        test_rets = test_ret[test_ret != 0]

        train_total = train_rets.sum() if len(train_rets) > 0 else 0
        test_total = test_rets.sum() if len(test_rets) > 0 else 0
        test_sharpe = compute_sharpe(test_rets) if len(test_rets) > 1 else 0

        decay = (test_total - train_total) / abs(train_total) if train_total != 0 else 0

        passed = (test_total > 0) and (test_sharpe > 0.3) and (abs(decay) < 0.5)
        fold_results.append({
            'fold_idx': fold['fold_idx'],
            'train_start': str(fold['train_df']['date'].iloc[0]),
            'train_end': str(fold['train_df']['date'].iloc[-1]),
            'test_start': str(fold['test_df']['date'].iloc[0]),
            'test_end': str(fold['test_df']['date'].iloc[-1]),
            'train_return': float(train_total),
            'test_return': float(test_total),
            'test_sharpe': float(test_sharpe),
            'decay': float(decay),
            'pass': passed,
            'reason': 'OK' if passed else f"ret={test_total:.3f} sh={test_sharpe:.2f} dec={decay:.2f}",
        })

    n_passed = sum(1 for f in fold_results if f['pass'])
    pass_rate = n_passed / len(fold_results) if fold_results else 0

    # 评分
    score_pass = pass_rate * 0.5
    avg_sharpe = np.mean([f['test_sharpe'] for f in fold_results]) if fold_results else 0
    score_sharpe = min(avg_sharpe / 1.0, 1.0) * 0.3
    avg_decay = np.mean([f['decay'] for f in fold_results]) if fold_results else 0
    score_decay = max(1.0 - abs(avg_decay) / 1.0, 0) * 0.2
    score = score_pass + score_sharpe + score_decay

    return {
        'adx_trend': adx_trend,
        'adx_volatile': adx_volatile,
        'ma_fast': ma_fast,
        'ma_slow': ma_slow,
        'n_folds': len(fold_results),
        'n_passed': n_passed,
        'pass_rate': float(pass_rate),
        'avg_train_return': float(np.mean([f['train_return'] for f in fold_results])) if fold_results else 0,
        'avg_test_return': float(np.mean([f['test_return'] for f in fold_results])) if fold_results else 0,
        'avg_test_sharpe': float(avg_sharpe),
        'avg_decay': float(avg_decay),
        'score': float(score),
        'pass': (n_passed >= 4) and (score >= 0.6),
        'confidence': 'HIGH' if pass_rate == 1.0 else ('MEDIUM' if pass_rate >= 0.6 else 'FAIL'),
        'fold_results': fold_results,
    }


# ============ 主程序 ============

def main():
    logger.info("=" * 70)
    logger.info("SOP-03 Phase 3: 过拟合检验（5 折 WalkForward）")
    logger.info("=" * 70)

    ETF_POOL = [
        '510300', '515650', '515070', '512400', '512480', '588000', '520900',
        '512880', '512170', '512660', '512200', '512800', '512980',
        '515050', '515790',
    ]

    # 加载 Phase 1+2 结果
    exp_path = OUTPUT_DIR / 'market_regime_experiment.json'
    if not exp_path.exists():
        logger.error(f"找不到 Phase 1+2 结果文件: {exp_path}")
        logger.error("请先运行: python3 scripts/experiment/market_regime_experiment.py")
        return 1

    with open(exp_path) as f:
        exp_data = json.load(f)

    all_results = exp_data['results']
    # 取 Top 10
    top_results = sorted(all_results, key=lambda x: x['oos_avg_sharpe'], reverse=True)[:10]

    logger.info(f"Phase 1+2 Top 10 参数组合（已按 OOS Sharpe 排序）:")
    for i, r in enumerate(top_results, 1):
        logger.info(f"  {i}. {r['key']}: AT={r['adx_trend']} AV={r['adx_volatile']} "
                    f"MA{r['ma_fast']}{r['ma_slow']} OOSSharpe={r['oos_avg_sharpe']:.2f}")

    logger.info(f"\n对 Top 10 × {len(ETF_POOL)} ETF 做 5 折 WalkForward 验证")
    logger.info("每折验证: 训练1.4年 / 测试0.6年 / 至少4/5折通过")
    logger.info("")

    # 对每个 Top 参数组合，在全 ETF 池上做 5 折 WF
    wf_results = []

    for i, params in enumerate(top_results):
        adx_trend = params['adx_trend']
        adx_volatile = params['adx_volatile']
        ma_fast = params['ma_fast']
        ma_slow = params['ma_slow']
        key = params['key']

        etf_wf_results = []
        for code in ETF_POOL:
            loader = DataLoader()
            df = loader.load_single(code, min_rows=400)
            if df is None:
                continue
            df = df[(df['date'] >= '2023-01-01') & (df['date'] <= '2026-06-01')]
            df = df.sort_values('date').reset_index(drop=True)
            if len(df) < 300:
                continue

            wf = run_5fold_wf(df, adx_trend, adx_volatile, ma_fast, ma_slow)
            etf_wf_results.append(wf)

        # 聚合所有 ETF 的 WF 结果（不保存完整 fold 详情，只保存摘要）
        n_total_etfs = len(etf_wf_results)
        n_pass_etfs = sum(1 for w in etf_wf_results if w['pass'])
        avg_score = np.mean([w['score'] for w in etf_wf_results])
        avg_sharpe = np.mean([w['avg_test_sharpe'] for w in etf_wf_results])
        avg_oos = np.mean([w['avg_test_return'] for w in etf_wf_results])
        avg_decay = np.mean([w['avg_decay'] for w in etf_wf_results])

        # 只保存摘要，不保存完整 fold_results（避免 JSON 序列化失败）
        etf_summaries = [{
            'etf_code': code,
            'n_folds': w['n_folds'],
            'n_passed': w['n_passed'],
            'pass': w['pass'],
            'score': w['score'],
            'test_sharpe': w['avg_test_sharpe'],
            'test_return': w['avg_test_return'],
            'confidence': w['confidence'],
        } for w, code in zip(etf_wf_results, ETF_POOL[:n_total_etfs])]

        wf_summary = {
            'key': key,
            'adx_trend': adx_trend,
            'adx_volatile': adx_volatile,
            'ma_fast': ma_fast,
            'ma_slow': ma_slow,
            'n_etf': n_total_etfs,
            'n_pass_etf': n_pass_etfs,
            'pass_rate': n_pass_etfs / n_total_etfs,
            'pass': n_pass_etfs / n_total_etfs >= 0.6,
            'avg_score': float(avg_score),
            'avg_oos_return': float(avg_oos),
            'avg_oos_sharpe': float(avg_sharpe),
            'avg_decay': float(avg_decay),
            'etf_summaries': etf_summaries,
        }
        wf_results.append(wf_summary)

        logger.info(f"[{i+1}/10] {key}: ETF通过率={n_pass_etfs}/{n_total_etfs} "
                    f"平均Sharpe={avg_sharpe:.2f} 平均Score={avg_score:.2f}")

    # 排序
    wf_results.sort(key=lambda x: (x['pass_rate'], x['avg_score']), reverse=True)

    logger.info("\n" + "=" * 70)
    logger.info("SOP-03 Phase 3 验收标准")
    logger.info("=" * 70)
    passing_wf = [w for w in wf_results if w['pass']]
    passing_rate = len(passing_wf) / len(wf_results) * 100
    logger.info(f"5折WF通过率（≥4/5折 + Score≥0.6）: {passing_rate:.1f}% ({len(passing_wf)}/{len(wf_results)})")

    # SOP-03: 通过率 < 5% → 立即停
    if passing_rate < 5:
        logger.error("❌ 通过率 < 5%，立即停！反思机制触发")
        logger.error("结论：震荡判断标准参数无稳定解，策略存在严重过拟合")
    else:
        logger.info(f"✅ 通过率 {passing_rate:.1f}% ≥ 5%，继续")

    logger.info(f"\n最优参数（WF验证后）:")
    best = wf_results[0]
    logger.info(f"  {best['key']}: ETF通过率={best['n_pass_etf']}/{best['n_etf']} "
                f"平均Sharpe={best['avg_oos_sharpe']:.2f} Score={best['avg_score']:.2f}")

    # 对比默认 SOP-05 参数
    default_key = 'AT25_AV20_MA520'
    default = next((w for w in wf_results if w['key'] == default_key), None)
    if default:
        logger.info(f"\nSOP-05默认 (AT25, AV20, MA5/20): ETF通过率={default['n_pass_etf']}/{default['n_etf']} "
                    f"Sharpe={default['avg_oos_sharpe']:.2f} Score={default['avg_score']:.2f} 【{default.get('confidence', 'N/A')}】")
    else:
        logger.info(f"\nSOP-05默认 {default_key} 不在Top10，跳过WF比较")

    # 输出
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'market_regime_wf5_validation',
        'sop': 'SOP-03 Phase 3',
        'top10_params': [{'key': r['key'], 'adx_trend': r['adx_trend'],
                           'adx_volatile': r['adx_volatile'],
                           'ma_fast': r['ma_fast'], 'ma_slow': r['ma_slow'],
                           'oos_sharpe': r['oos_avg_sharpe']} for r in top_results],
        'wf_results': wf_results,
        'summary': {
            'n_top10': len(wf_results),
            'n_passed': len(passing_wf),
            'passing_rate': float(passing_rate),
            'best_key': wf_results[0]['key'],
            'best_score': wf_results[0]['avg_score'],
            'best_sharpe': wf_results[0]['avg_oos_sharpe'],
            'default_comparison': {
                'key': default_key,
                'n_pass_etf': default['n_pass_etf'] if default else None,
                'pass_rate': default['pass_rate'] if default else None,
                'avg_sharpe': default['avg_oos_sharpe'] if default else None,
                'confidence': default['confidence'] if default else None,
            } if default else None,
        }
    }

    json_path = OUTPUT_DIR / 'market_regime_wf5_validation.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    # Markdown 报告
    md = [
        "# 震荡判断标准 5 折 WalkForward 验证报告",
        "",
        f"**时间**: {datetime.now().isoformat()}",
        f"**SOP**: SOP-03 Phase 3",
        "",
        "## 验收结果",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| Top 10 参数组合 | {len(wf_results)} |",
        f"| **5折WF通过率** | **{passing_rate:.1f}%** |",
        f"| 最优 Score | {wf_results[0]['avg_score']:.3f} |",
        f"| 最优 Sharpe | {wf_results[0]['avg_oos_sharpe']:.2f} |",
        "",
        f"**通过率 < 5% → {'❌ 立即停（反思机制触发）' if passing_rate < 5 else '✅ 继续'}**",
        "",
        "## Top 10 参数 WF 验证结果",
        "",
        "| # | AT | AV | MA | ETF通过率 | Score | OOS Sharpe | OOS 收益 | 置信 |",
        "|--:|--:|--:|--:|--------:|------:|----------:|----------:|------|",
    ]
    for i, w in enumerate(wf_results, 1):
        conf_emoji = {'HIGH': '🟢', 'MEDIUM': '🟡', 'FAIL': '🔴'}.get(w.get('confidence', 'FAIL'), '⚪')
        md.append(f"| {i} | {w['adx_trend']} | {w['adx_volatile']} | "
                  f"MA{w['ma_fast']}{w['ma_slow']} | "
                  f"{w['n_pass_etf']}/{w['n_etf']} | "
                  f"{w['avg_score']:.2f} | {w['avg_oos_sharpe']:.2f} | "
                  f"{w['avg_oos_return']*100:+.1f}% | {conf_emoji} {w.get('confidence', 'N/A')} |")

    if default:
        md.extend(["", "## 与 SOP-05 默认对比", "",
                   f"| 参数 | OOS Sharpe | ETF通过率 | Score | 置信 |",
                   f"|------|----------:|---------:|------:|------|",
                   f"| **修订版最优** {wf_results[0]['key']} | **{wf_results[0]['avg_oos_sharpe']:.2f}** | "
                   f"{wf_results[0]['n_pass_etf']}/{wf_results[0]['n_etf']} | {wf_results[0]['avg_score']:.2f} | "
                   f"{wf_results[0]['confidence']} |",
                   f"| SOP-05 默认 AT25_AV20_MA520 | {default['avg_oos_sharpe']:.2f} | "
                   f"{default['n_pass_etf']}/{default['n_etf']} | {default['avg_score']:.2f} | "
                   f"{default['confidence']} |"])

    md.extend(["", "## 核心发现", ""])
    best = wf_results[0]
    md.append(f"1. **最优参数**: {best['key']}（ADX趋势={best['adx_trend']}，ADX震荡={best['adx_volatile']}，MA={best['ma_fast']}/{best['ma_slow']}）")
    md.append(f"2. **ETF通过率**: {best['n_pass_etf']}/{best['n_etf']} = {best['pass_rate']*100:.0f}%")
    md.append(f"3. **平均 OOS Sharpe**: {best['avg_oos_sharpe']:.2f}")
    if default:
        diff = best['avg_oos_sharpe'] - default['avg_oos_sharpe']
        md.append(f"4. **vs SOP-05 默认**: {'+' if diff > 0 else ''}{diff:.2f}（{'+' if diff > 0 else ''}{diff:.0f}%）")

    md_path = OUTPUT_DIR / 'market_regime_wf5_validation.md'
    md_path.write_text('\n'.join(md))
    logger.info(f"\n输出: {json_path}\n       {md_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())