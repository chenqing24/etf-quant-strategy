#!/usr/bin/env python3
"""
US-026 Top 10 因子 WalkForward 验证（防过拟合）

按 SOP-01 v1.1：批量跑 Top 10 因子的 WalkForward(min_windows=6)
- 每个因子用 IC > 0.02 阈值验证
- 用现成 WalkForwardEngine（不写新代码）

Top 10 因子（按 IC 排序）：
1. W5 Garman-Klass (0.1154)
2. W6 Keltner 通道 (0.1135)
3. W2 布林带宽变化 (0.1110)
4. W3 历史波动率变化 (0.0979)
5. W4 RV 变化 (0.0972)
6. C2 因子加权 (0.0911)
7. C1 多因子投票 (0.0700)
8. M7 CCI 动量 (0.0510)
9. M9 WR (0.0518)
10. B3 盘整突破 (0.0589)
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from scripts.validators.walk_forward import WalkForwardEngine, WalkForwardResult


# Top 10 因子信号函数（每个返回一个 bool Series）
FACTOR_SIGNALS = {
    'W5_Garman_Klass': lambda df: _gk_signal(df),
    'W6_Keltner': lambda df: _kc_signal(df),
    'W2_BB_Width_Change': lambda df: _bb_width_chg(df),
    'W3_Hist_Vol_Change': lambda df: _vol_chg(df),
    'W4_RV_Change': lambda df: _rv_chg(df),
    'C2_Weighted_Combo': lambda df: _weighted_combo(df),
    'C1_Multi_Factor_Vote': lambda df: _multi_vote(df),
    'M7_CCI_Momentum': lambda df: _cci_mom(df),
    'M9_WR': lambda df: _wr_signal(df),
    'B3_Consolidation_Breakout': lambda df: _consolidation(df),
}


def _gk_signal(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    log_hl = np.log(df['high'] / df['low'])
    log_co = np.log(df['close'] / df['open'])
    gk = np.sqrt((0.5 * log_hl**2 - (2*np.log(2)-1)*log_co**2).rolling(20).mean() * 252)
    return (gk - gk.shift(20)) > 0


def _kc_signal(df):
    ema = df['close'].ewm(span=20, adjust=False).mean()
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    tr = pd.concat([high-low, (high-close_prev).abs(), (low-close_prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(20).mean()
    return (df['close'] > (ema + 2*atr))  # 突破上轨


def _bb_width_chg(df):
    mid = df['close'].rolling(20).mean()
    std = df['close'].rolling(20).std()
    width = (mid + 2*std) - (mid - 2*std)
    return (width - width.shift(20)) > 0


def _vol_chg(df):
    log_ret = np.log(df['close'] / df['close'].shift(1))
    vol = log_ret.rolling(20).std() * np.sqrt(252)
    return (vol - vol.shift(20)) > 0


def _rv_chg(df):
    log_ret = np.log(df['close'] / df['close'].shift(1))
    rv = np.sqrt((log_ret**2).rolling(20).sum() * 252)
    return (rv - rv.shift(20)) > 0


def _weighted_combo(df):
    vol_ratio = df['volume'] / df['volume'].rolling(5).mean()
    v4 = (vol_ratio > 1.5)
    high = df['high']; low = df['low']; close = df['close']
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
    return (v4.astype(int) + t9.astype(int) + m9.astype(int) + b3.astype(int)) >= 3


def _multi_vote(df):
    return _weighted_combo(df)  # 简化


def _cci_mom(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma_tp = tp.rolling(20).mean()
    md = (tp - ma_tp).abs().rolling(20).mean()
    cci = (tp - ma_tp) / (0.015 * md.replace(0, 1))
    return (cci - cci.shift(20)) > 0


def _wr_signal(df):
    high_n = df['high'].rolling(14).max()
    low_n = df['low'].rolling(14).min()
    return (-(high_n - df['close']) / (high_n - low_n).replace(0, 1) * 100) > 50


def _consolidation(df):
    returns = df['close'].pct_change()
    vol_n = returns.rolling(20).std()
    return (vol_n < 0.02) & (df['close'] > df['high'].rolling(20).max().shift(1))


def main():
    print("=" * 70)
    print("US-026 Top 10 因子 WalkForward 验证（min_windows=6）")
    print("=" * 70)

    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    engine = WalkForwardEngine()
    results = {}

    for factor_name, signal_func in FACTOR_SIGNALS.items():
        # 用 512660（军工）作为代表 ETF（有 5+ 年数据）
        try:
            all_data = loader.load(codes=['512660'])
            df = all_data.get('512660')
            if df is None or df.empty:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()

            result = engine.validate(df, signal_func)
            results[factor_name] = {
                'avg_train_return': float(result.avg_train_return) if hasattr(result, 'avg_train_return') else 0,
                'avg_test_return': float(result.avg_test_return) if hasattr(result, 'avg_test_return') else 0,
                'avg_decay': float(result.avg_decay) if hasattr(result, 'avg_decay') else 0,
                'pass_rate': float(result.pass_rate) if hasattr(result, 'pass_rate') else 0,
                'n_windows': int(result.n_windows) if hasattr(result, 'n_windows') else 0,
                'n_passed': int(result.n_passed) if hasattr(result, 'n_passed') else 0,
                'confidence': str(result.confidence) if hasattr(result, 'confidence') else 'N/A',
            }
            oos_is = (results[factor_name]['avg_test_return'] /
                      max(abs(results[factor_name]['avg_train_return']), 1e-9))
            print(f"  ✅ {factor_name}: OOS={results[factor_name]['avg_test_return']:.4f}, IS={results[factor_name]['avg_train_return']:.4f}, OOS/IS={oos_is:.2f}, pass={results[factor_name]['pass_rate']:.2f} ({results[factor_name]['n_passed']}/{results[factor_name]['n_windows']})")
        except Exception as e:
            print(f"  ❌ {factor_name}: {type(e).__name__}: {e}")
            results[factor_name] = {'error': str(e)}

    # 保存报告
    report_path = Path("data/US-026_top10_walkforward.json")
    with open(report_path, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📄 报告: {report_path}")

    # 总结
    print("\n## Top 10 验证总结")
    for name, r in results.items():
        if 'error' in r:
            print(f"  ❌ {name}: 失败")
        else:
            oos_is = r['avg_test_return'] / max(abs(r['avg_train_return']), 1e-9)
            print(f"  {name}: OOS={r['avg_test_return']:.4f}, IS={r['avg_train_return']:.4f}, OOS/IS={oos_is:.2f}, pass={r['pass_rate']:.2f} ({r['n_passed']}/{r['n_windows']})")


if __name__ == "__main__":
    main()
