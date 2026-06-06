#!/usr/bin/env python3
"""
US-026 A3 + A2 + A4 联合验证（修方法论 + 扩大样本）

A3: IC 检验改用 20 日未来窗口（修"5 日近因偏置"）
A2: 跑 15 ETF 全部 WalkForward（不只是 512660）
A4: IC 改用 WalkForward 方式（每窗口 IS IC vs OOS IC 对比）

按 SOP-01 v1.1：用现成工具（DataLoader + WalkForwardEngine），不写新工具。
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from scripts.validators.walk_forward import WalkForwardEngine


# Top 10 因子（按 IC 排序）+ 信号函数
FACTOR_SIGNALS = {
    'W5_Garman_Klass': lambda df: (np.sqrt((0.5*np.log(df['high']/df['low'])**2 - (2*np.log(2)-1)*np.log(df['close']/df['open'])**2).rolling(20).mean() * 252) - _safe_shift(np.sqrt((0.5*np.log(df['high']/df['low'])**2 - (2*np.log(2)-1)*np.log(df['close']/df['open'])**2).rolling(20).mean() * 252), 20)) > 0,
    'W6_Keltner': lambda df: df['close'] > (df['close'].ewm(span=20, adjust=False).mean() + 2*_atr(df, 20)),
    'W2_BB_Width_Change': lambda df: ((df['close'].rolling(20).mean() + 2*df['close'].rolling(20).std()) - (df['close'].rolling(20).mean() - 2*df['close'].rolling(20).std()) - _safe_shift((df['close'].rolling(20).mean() + 2*df['close'].rolling(20).std()) - (df['close'].rolling(20).mean() - 2*df['close'].rolling(20).std()), 20)) > 0,
    'W3_Hist_Vol_Change': lambda df: (np.log(df['close']/df['close'].shift(1)).rolling(20).std() * np.sqrt(252) - _safe_shift(np.log(df['close']/df['close'].shift(1)).rolling(20).std() * np.sqrt(252), 20)) > 0,
    'W4_RV_Change': lambda df: (np.sqrt((np.log(df['close']/df['close'].shift(1))**2).rolling(20).sum() * 252) - _safe_shift(np.sqrt((np.log(df['close']/df['close'].shift(1))**2).rolling(20).sum() * 252), 20)) > 0,
    'C2_Weighted_Combo': lambda df: _multi_vote(df) >= 3,
    'M7_CCI_Momentum': lambda df: _cci_mom(df) > 0,
    'M9_WR': lambda df: (-(df['high'].rolling(14).max() - df['close']) / (df['high'].rolling(14).max() - df['low'].rolling(14).min()).replace(0, 1) * 100) > 50,
    'B3_Consolidation_Breakout': lambda df: (df['close'].pct_change().rolling(20).std() < 0.02) & (df['close'] > df['high'].rolling(20).max().shift(1)),
}


def _safe_shift(s, n):
    return s.shift(n) if hasattr(s, 'shift') else pd.Series(s).shift(n)


def _atr(df, n):
    high, low, close = df['high'], df['low'], df['close']
    close_prev = close.shift(1)
    tr = pd.concat([high-low, (high-close_prev).abs(), (low-close_prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _cci_mom(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma_tp = tp.rolling(20).mean()
    md = (tp - ma_tp).abs().rolling(20).mean()
    cci = (tp - ma_tp) / (0.015 * md.replace(0, 1))
    return cci - cci.shift(20)


def _multi_vote(df):
    vol_ratio = df['volume'] / df['volume'].rolling(5).mean()
    v4 = (vol_ratio > 1.5).astype(int)
    high, low, close = df['high'], df['low'], df['close']
    up = high.diff(); down = -low.diff()
    plus_dm = pd.Series(0.0, index=df.index); minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up>down)&(up>0)] = up
    minus_dm[(down>up)&(down>0)] = down
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    t9 = (100*plus_dm.rolling(14).mean()/atr) > (100*minus_dm.rolling(14).mean()/atr)
    high_n = df['high'].rolling(14).max()
    low_n = df['low'].rolling(14).min()
    m9 = (-(high_n - df['close']) / (high_n - low_n).replace(0, 1) * 100) > 50
    returns = df['close'].pct_change()
    vol_n = returns.rolling(20).std()
    b3 = (vol_n < 0.02) & (df['close'] > df['high'].rolling(20).max().shift(1))
    return (v4.astype(int) + t9.astype(int) + m9.astype(int) + b3.astype(int))


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
    print("US-026 A3 + A2 + A4 联合验证")
    print("=" * 70)
    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'
    engine = WalkForwardEngine()

    # A3: 36 因子 5 日 IC 检验（已有报告），加 20 日 IC 检验
    print("\n【A3】20 日未来窗口 IC 检验（15 ETF × 10 因子）")
    print("-" * 70)
    a3_results = {}
    for factor_name, signal_func in FACTOR_SIGNALS.items():
        all_ic_5d = []
        all_ic_20d = []
        for code in CORE_ETF_POOL_15:
            try:
                all_data = loader.load(codes=[code])
                df = all_data.get(code)
                if df is None or df.empty:
                    continue
                if 'date' in df.columns:
                    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
                df['_signal'] = signal_func(df).fillna(False).astype(int)
                df['_ret_5d'] = df['close'].shift(-5) / df['close'] - 1
                df['_ret_20d'] = df['close'].shift(-20) / df['close'] - 1
                ic_5d = compute_ic(df['_signal'], df['_ret_5d'])
                ic_20d = compute_ic(df['_signal'], df['_ret_20d'])
                if not np.isnan(ic_5d):
                    all_ic_5d.append(ic_5d)
                if not np.isnan(ic_20d):
                    all_ic_20d.append(ic_20d)
            except Exception as e:
                pass
        a3_results[factor_name] = {
            'ic_5d': float(np.mean(all_ic_5d)) if all_ic_5d else np.nan,
            'ic_20d': float(np.mean(all_ic_20d)) if all_ic_20d else np.nan,
            'n_etfs_5d': len(all_ic_5d),
            'n_etfs_20d': len(all_ic_20d),
        }
        print(f"  {factor_name}: 5日 IC={a3_results[factor_name]['ic_5d']:.4f} → 20日 IC={a3_results[factor_name]['ic_20d']:.4f}")

    # A2: 15 ETF 全部 WalkForward
    print("\n【A2】15 ETF 全部 WalkForward 验证")
    print("-" * 70)
    a2_results = {}
    for factor_name, signal_func in FACTOR_SIGNALS.items():
        etf_results = []
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
                etf_results.append({
                    'code': code,
                    'avg_test_return': float(result.avg_test_return),
                    'avg_train_return': float(result.avg_train_return),
                    'oos_is': oos_is,
                    'pass_rate': float(result.pass_rate),
                    'n_passed': int(result.n_passed),
                    'n_windows': int(result.n_windows),
                })
            except Exception as e:
                pass

        if etf_results:
            oos_etfs = sum(1 for r in etf_results if r['oos_is'] > 0.5)
            pass_etfs = sum(1 for r in etf_results if r['pass_rate'] > 0.5)
            avg_oos_is = float(np.mean([r['oos_is'] for r in etf_results]))
            a2_results[factor_name] = {
                'avg_oos_is': avg_oos_is,
                'etfs_oos_gt_0.5': oos_etfs,
                'etfs_pass_gt_0.5': pass_etfs,
                'total_etfs': len(etf_results),
                'detail': etf_results,
            }
            print(f"  {factor_name}: avg_OOS/IS={avg_oos_is:.2f} | ETF通过率 OOS/IS>0.5: {oos_etfs}/{len(etf_results)} | pass_rate>0.5: {pass_etfs}/{len(etf_results)}")

    # A4: IC 改用 WalkForward 方式
    print("\n【A4】IC 改用 WalkForward 方式（IS IC vs OOS IC 对比）")
    print("-" * 70)
    a4_results = {}
    for factor_name, signal_func in FACTOR_SIGNALS.items():
        # 用 512660 1 只 ETF
        try:
            all_data = loader.load(codes=['512660'])
            df = all_data.get('512660')
            if df is None or df.empty:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()

            # WalkForward 计算 IS IC vs OOS IC
            # 简化为：用 train 段（每窗口前 6 月）算 IS IC，用 test 段（每窗口后 3 月）算 OOS IC
            df['_signal'] = signal_func(df).fillna(False).astype(int)
            df['_ret_5d'] = df['close'].shift(-5) / df['close'] - 1

            # 6 窗口（每 3 月一个）
            is_ics = []
            oos_ics = []
            n_train_months = 6
            n_test_months = 3
            trading_days = 21

            n = len(df)
            train_days = n_train_months * trading_days
            test_days = n_test_months * trading_days

            i = train_days
            while i + test_days <= n:
                train_df = df.iloc[i - train_days:i]
                test_df = df.iloc[i:i + test_days]
                is_ic = compute_ic(train_df['_signal'], train_df['_ret_5d'])
                oos_ic = compute_ic(test_df['_signal'], test_df['_ret_5d'])
                if not np.isnan(is_ic):
                    is_ics.append(is_ic)
                if not np.isnan(oos_ic):
                    oos_ics.append(oos_ic)
                i += test_days

            if is_ics and oos_ics:
                avg_is_ic = float(np.mean(is_ics))
                avg_oos_ic = float(np.mean(oos_ics))
                decay = avg_oos_ic - avg_is_ic
                a4_results[factor_name] = {
                    'avg_is_ic': avg_is_ic,
                    'avg_oos_ic': avg_oos_ic,
                    'decay': decay,
                    'n_windows': len(is_ics),
                }
                print(f"  {factor_name}: IS IC={avg_is_ic:.4f} → OOS IC={avg_oos_ic:.4f} (衰减={decay:.4f}, n={len(is_ics)})")
        except Exception as e:
            print(f"  ❌ {factor_name}: {e}")

    # 综合报告
    print("\n" + "=" * 70)
    print("📊 A3 + A2 + A4 综合报告")
    print("=" * 70)
    for factor_name in FACTOR_SIGNALS.keys():
        a3 = a3_results.get(factor_name, {})
        a2 = a2_results.get(factor_name, {})
        a4 = a4_results.get(factor_name, {})
        a2_str = f"avg_OOS/IS={a2.get('avg_oos_is', 0):.2f} ({a2.get('etfs_oos_gt_0.5', 0)}/{a2.get('total_etfs', 0)})" if a2 else "N/A"
        a4_str = f"IS={a4.get('avg_is_ic', 0):.4f} OOS={a4.get('avg_oos_ic', 0):.4f}" if a4 else "N/A"
        print(f"  {factor_name}:")
        print(f"    A3 5日 IC={a3.get('ic_5d', np.nan):.4f} | 20日 IC={a3.get('ic_20d', np.nan):.4f}")
        print(f"    A2 15 ETF: {a2_str}")
        print(f"    A4 WalkForward IC: {a4_str}")

    # 保存
    report_path = Path("data/US-026_a3a2a4_report.json")
    with open(report_path, 'w') as f:
        json.dump({
            'a3_results': a3_results,
            'a2_results': a2_results,
            'a4_results': a4_results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 报告: {report_path}")


if __name__ == "__main__":
    main()
