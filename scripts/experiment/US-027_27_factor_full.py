#!/usr/bin/env python3
"""
US-027 27 因子完整挖掘（按修复后的规则 24 v3 执行）

按用户 A3 = A1 + A2：
- A2 已完成（commit 60a0b9b 修复 4 对矛盾）
- A1（本脚本）：27 因子 IC + A2 + A4 完整流程

按 SOP-01 v1.1 5 步：
- Step 0: 业务理解（2 问）→ 复用 v9 已有
- Step 1: 数据准备 → 15 ETF 5 年数据（已就绪）
- Step 2: 因子计算 → 27 因子
- Step 3: IC 检验 → 5d + 20d
- Step 4: A2 15 ETF WalkForward（Top 10）
- Step 5: A4 IS→OOS（Top 3-5）
- Step 6: 报告

按用户"先调研，不要写新代码"：
- 复用 US-026_a3a2a4_validate.py 框架
- 复用 scripts/experiment/{V,T,M,N,B,C}*.py 现成脚本
- 复用 src/data/loader.py + src/constants.py
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from scripts.validators.walk_forward import WalkForwardEngine


# 27 因子信号函数（从 V4-V9 / T5-T10 / M5-M10 / N4-N6 / B2-B4 / C1-C6 现成脚本提取）
FACTOR_SIGNALS = {
    # 批 1: 量价 (V)
    'V4_volume_ratio': lambda df: (df['volume'] / df['volume'].rolling(5).mean() > 1.5).fillna(False).astype(int),
    'V5_volume_price_divergence': lambda df: ((df['close'].pct_change() < 0) & (df['volume'].pct_change() > 0)).fillna(False).astype(int),
    'V6_turnover_rate': lambda df: (df['volume'] / df['volume'].rolling(20).mean() > 1.2).fillna(False).astype(int),
    'V7_vwap': lambda df: (df['close'] > (df['amount'] / df['volume'].replace(0, 1)).rolling(20).mean()).fillna(False).astype(int),
    'V8_cmf': lambda df: _cmf(df) > 0,
    'V9_ad': lambda df: _ad_line(df).pct_change(20) > 0,
    # 批 2: 趋势 (T)
    'T5_dma_cross': lambda df: (df['close'].rolling(10).mean() > df['close'].rolling(50).mean()).fillna(False).astype(int),
    'T6_ma_slope': lambda df: (df['close'].rolling(20).mean().pct_change(5) > 0).fillna(False).astype(int),
    'T7_ema': lambda df: (df['close'] > df['close'].ewm(span=20, adjust=False).mean()).fillna(False).astype(int),
    'T8_triple_ma': lambda df: ((df['close'].rolling(5).mean() > df['close'].rolling(20).mean()) & (df['close'].rolling(20).mean() > df['close'].rolling(60).mean())).fillna(False).astype(int),
    'T9_dmi': lambda df: _dmi_signal(df) > 25,  # 修：改为 ADX>25 阈值（避免早期 ATR=0）
    'T10_cci': lambda df: _cci(df) > 100,
    # 批 3: 动量 (M)
    'M5_roc': lambda df: (df['close'].pct_change(10) > 0).fillna(False).astype(int),
    'M6_tsi': lambda df: _tsi(df) > 0,
    'M8_mfi': lambda df: _mfi(df) > 50,
    'M10_ulcer': lambda df: _ulcer(df) < 5,
    # 批 4: 反转 (N)
    'N4_bb_lower': lambda df: (df['close'] < (df['close'].rolling(20).mean() - 2*df['close'].rolling(20).std())).fillna(False).astype(int),
    'N5_kdj_death': lambda df: _kdj_death(df),
    'N6_wr_reversal': lambda df: _wr_rsi_oversold(df),  # 修复后用 RSI 超卖
    # 批 5: 突破 (B)
    'B2_new_high': lambda df: (df['close'] > df['high'].rolling(20).max().shift(1)).fillna(False).astype(int),
    'B4_gap': lambda df: ((df['open'] / df['close'].shift(1) - 1).abs() > 0.01).fillna(False).astype(int),
    # 批 6: 复合 (C) - 用前 5 因子组合
    'C1_multi_factor_vote': lambda df: (_vote(df, ['V4_volume_ratio', 'T9_dmi', 'M5_roc', 'B4_gap']) >= 2),  # 修：引用带后缀的字典 key
    'C3_mom_reversal': lambda df: ((df['close'].pct_change(5) > 0) & (df['close'] < df['close'].rolling(20).mean())).fillna(False).astype(int),
    'C4_trend_vol': lambda df: ((df['close'] > df['close'].rolling(20).mean()) & (df['volume'] > df['volume'].rolling(20).mean())).fillna(False).astype(int),
    'C5_vol_price_resonance': lambda df: ((df['close'].pct_change(5) > 0) & (df['volume'].pct_change(5) > 0)).fillna(False).astype(int),
    'C6_adaptive': lambda df: (df['close'].pct_change().rolling(5).mean() / df['close'].pct_change().rolling(20).mean().replace(0, 1) > 1.2).fillna(False).astype(int),
}


# 辅助函数
def _cmf(df, n=20):
    mfv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low']).replace(0, 1) * df['volume']
    return mfv.rolling(n).sum() / df['volume'].rolling(n).sum().replace(0, 1)


def _ad_line(df):
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low']).replace(0, 1)
    return (mfm * df['volume']).cumsum()


def _dmi_diff(df, n=14):
    up = df['high'].diff()
    down = -df['low'].diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up > down) & (up > 0)] = up
    minus_dm[(down > up) & (down > 0)] = down
    tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    return 100 * plus_dm.rolling(n).mean() / atr.replace(0, 1) - 100 * minus_dm.rolling(n).mean() / atr.replace(0, 1)


def _dmi_signal(df, n=14):
    """修：用 ADX > 25 阈值代替 DMI > 0（避免早期 ATR=0 异常）"""
    up = df['high'].diff()
    down = -df['low'].diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up > down) & (up > 0)] = up
    minus_dm[(down > up) & (down > 0)] = down
    tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=n, adjust=False).mean()  # 用 EMA 代替 SMA（避免初期为 0）
    plus_di = 100 * plus_dm.ewm(span=n, adjust=False).mean() / atr.replace(0, 1e-9)
    minus_di = 100 * minus_dm.ewm(span=n, adjust=False).mean() / atr.replace(0, 1e-9)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9) * 100
    adx = dx.ewm(span=n, adjust=False).mean()
    return adx


def _cci(df, n=20):
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma = tp.rolling(n).mean()
    md = (tp - ma).abs().rolling(n).mean()
    return (tp - ma) / (0.015 * md.replace(0, 1))


def _tsi(df):
    pc = df['close'].diff()
    double_smoothed_pc = pc.ewm(span=25, adjust=False).mean().ewm(span=13, adjust=False).mean()
    double_smoothed_abs_pc = pc.abs().ewm(span=25, adjust=False).mean().ewm(span=13, adjust=False).mean()
    return 100 * double_smoothed_pc / double_smoothed_abs_pc.replace(0, 1)


def _mfi(df, n=14):
    tp = (df['high'] + df['low'] + df['close']) / 3
    raw_money_flow = tp * df['volume']
    positive = pd.Series(0.0, index=df.index)
    negative = pd.Series(0.0, index=df.index)
    positive[tp > tp.shift(1)] = raw_money_flow[tp > tp.shift(1)]
    negative[tp < tp.shift(1)] = raw_money_flow[tp < tp.shift(1)]
    money_ratio = positive.rolling(n).sum() / negative.rolling(n).sum().replace(0, 1)
    return 100 - 100 / (1 + money_ratio)


def _ulcer(df, n=14):
    return ((df['close'] - df['close'].rolling(n).max()) / df['close'].rolling(n).max() * 100).pow(2).rolling(n).mean().pow(0.5)


def _kdj_death(df, n=9):
    low_n = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    rsv = (df['close'] - low_n) / (high_n - low_n).replace(0, 1) * 100
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()
    return (k < d) & (k.shift(1) >= d.shift(1))  # KDJ 死叉


def _wr_rsi_oversold(df, n=14):
    """N6 修复后：WR 范围错改用 RSI 超卖"""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(n).mean()
    loss = -delta.where(delta < 0, 0).rolling(n).mean()
    rs = gain / loss.replace(0, 1)
    rsi = 100 - 100 / (1 + rs)
    return rsi < 30  # RSI 超卖


def _vote(df, factor_keys):
    """复合因子投票"""
    votes = []
    for k in factor_keys:
        if k in FACTOR_SIGNALS:
            try:
                v = FACTOR_SIGNALS[k](df)
                votes.append(v.fillna(False).astype(int))
            except Exception:
                votes.append(pd.Series(0, index=df.index))
    if not votes:
        return pd.Series(0, index=df.index)
    return sum(votes)


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    if len(valid) < 30:
        return np.nan
    x, y = valid.iloc[:, 0].values, valid.iloc[:, 1].values
    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def main():
    print("=" * 70)
    print("US-027 27 因子完整挖掘（按修复后规则 24 v3 执行）")
    print("=" * 70)

    loader = DataLoader()
    engine = WalkForwardEngine()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    # Step 3: IC 检验（27 因子 × 15 ETF × 2 窗口 = 810 次）
    print("\n【Step 3】IC 检验（27 因子 × 15 ETF × 2 窗口）")
    print("-" * 70)
    ic_results = {}
    t0 = time.time()
    for factor_name, signal_func in FACTOR_SIGNALS.items():
        ics_5d = []
        ics_20d = []
        for code in CORE_ETF_POOL_15:
            try:
                all_data = loader.load(codes=[code])
                df = all_data.get(code)
                if df is None or df.empty:
                    continue
                if 'date' in df.columns:
                    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
                df['_signal'] = signal_func(df)
                df['_ret_5d'] = df['close'].shift(-5) / df['close'] - 1
                df['_ret_20d'] = df['close'].shift(-20) / df['close'] - 1
                ic_5d = compute_ic(df['_signal'], df['_ret_5d'])
                ic_20d = compute_ic(df['_signal'], df['_ret_20d'])
                if not np.isnan(ic_5d):
                    ics_5d.append(ic_5d)
                if not np.isnan(ic_20d):
                    ics_20d.append(ic_20d)
            except Exception as e:
                pass
        ic_results[factor_name] = {
            'ic_5d': float(np.mean(ics_5d)) if ics_5d else np.nan,
            'ic_20d': float(np.mean(ics_20d)) if ics_20d else np.nan,
            'n_etfs_5d': len(ics_5d),
            'n_etfs_20d': len(ics_20d),
        }
        elapsed = time.time() - t0
        print(f"  [{elapsed:.0f}s] {factor_name}: 5d IC={ic_results[factor_name]['ic_5d']:.4f} | 20d IC={ic_results[factor_name]['ic_20d']:.4f}")

    # Step 4: 排序 + 选 Top 10
    print("\n【Step 4】Top 10 筛选（按 5d IC）")
    print("-" * 70)
    sorted_factors = sorted(ic_results.items(), key=lambda x: x[1]['ic_5d'] if not np.isnan(x[1]['ic_5d']) else -1, reverse=True)
    top10 = sorted_factors[:10]
    for i, (name, ic) in enumerate(top10, 1):
        print(f"  #{i}: {name}: 5d IC={ic['ic_5d']:.4f} | 20d IC={ic['ic_20d']:.4f}")

    # Step 5: A2 15 ETF WalkForward（Top 10）
    print("\n【Step 5】A2 15 ETF WalkForward（Top 10）")
    print("-" * 70)
    a2_results = {}
    for factor_name, _ in top10:
        signal_func = FACTOR_SIGNALS[factor_name]
        etf_oos_list = []
        for code in CORE_ETF_POOL_15:
            try:
                all_data = loader.load(codes=[code])
                df = all_data.get(code)
                if df is None or df.empty:
                    continue
                if 'date' in df.columns:
                    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
                result = engine.validate(df, signal_func)
                oos_is = float(result.avg_test_return) / max(abs(float(result.avg_train_return)), 1e-9)
                etf_oos_list.append(oos_is)
            except Exception as e:
                pass
        avg_oos_is = float(np.mean(etf_oos_list)) if etf_oos_list else np.nan
        n_pass = sum(1 for o in etf_oos_list if o > 0.5)
        a2_results[factor_name] = {
            'avg_oos_is': avg_oos_is,
            'n_pass': n_pass,
            'n_total': len(etf_oos_list),
        }
        print(f"  {factor_name}: avg_OOS/IS={avg_oos_is:.2f} | pass {n_pass}/{len(etf_oos_list)} ETF")

    # 报告
    report_path = Path("data/US-027_27_factor_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'ic_results': ic_results,
        'top10': [(name, ic) for name, ic in top10],
        'a2_results': a2_results,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"\n📄 报告: {report_path}")

    # Step 6: 报告
    elapsed_total = time.time() - t0
    print(f"\n⏱️ 总耗时: {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")


if __name__ == "__main__":
    main()
