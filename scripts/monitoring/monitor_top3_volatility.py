#!/usr/bin/env python3
"""
US-026 Top 3 波动率因子每日监控（C2 选项）

按 SOP-01 v1.1：每日 14:00 跑
- 计算 W4+W3+W2 三个因子的当日 IC
- 输出 monitor_top3_report.json（钉钉/console 报告）
- 异常检测：IC < 0.02 持续 5 天 → 钉钉告警

调度（用 qwenpaw cron 加）：
  qwenpaw cron create --type agent --name "US-026 Top3 波动率监控" \
    --cron "0 14 * * mon-fri" --text "cd /home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy && python scripts/monitoring/monitor_top3_volatility.py"
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_w4_rv(df):
    log_ret = np.log(df['close'] / df['close'].shift(1))
    rv = np.sqrt((log_ret**2).rolling(20).sum() * 252)
    return (rv - rv.shift(20)) > 0


def compute_w3_hist_vol(df):
    log_ret = np.log(df['close'] / df['close'].shift(1))
    vol = log_ret.rolling(20).std() * np.sqrt(252)
    return (vol - vol.shift(20)) > 0


def compute_w2_bb_width(df):
    mid = df['close'].rolling(20).mean()
    std = df['close'].rolling(20).std()
    width = (mid + 2*std) - (mid - 2*std)
    return (width - width.shift(20)) > 0


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    if len(valid) < 30:
        return np.nan
    x, y = valid.iloc[:, 0].values, valid.iloc[:, 1].values
    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


FACTOR_FUNCS = {
    'W4_RV_Change': compute_w4_rv,
    'W3_Hist_Vol_Change': compute_w3_hist_vol,
    'W2_BB_Width_Change': compute_w2_bb_width,
}


def main():
    print("=" * 70)
    print("US-026 Top 3 波动率因子每日监控")
    print("=" * 70)

    loader = DataLoader()
    today = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')

    daily_report = {
        'date': today,
        'factors': {},
        'alerts': [],
    }

    for factor_name, factor_func in FACTOR_FUNCS.items():
        print(f"\n【{factor_name}】")
        factor_ics_5d = []
        factor_ics_20d = []
        factor_signals = {}

        for code in CORE_ETF_POOL_15:
            try:
                all_data = loader.load(codes=[code])
                df = all_data.get(code)
                if df is None or df.empty:
                    continue
                if 'date' in df.columns:
                    df = df[(df['date'] >= start_date)].copy()
                df['_signal'] = factor_func(df).fillna(False).astype(int)
                df['_ret_5d'] = df['close'].shift(-5) / df['close'] - 1
                df['_ret_20d'] = df['close'].shift(-20) / df['close'] - 1
                ic_5d = compute_ic(df['_signal'], df['_ret_5d'])
                ic_20d = compute_ic(df['_signal'], df['_ret_20d'])
                if not np.isnan(ic_5d):
                    factor_ics_5d.append(ic_5d)
                if not np.isnan(ic_20d):
                    factor_ics_20d.append(ic_20d)
                if len(df) > 0:
                    today_signal = bool(df['_signal'].iloc[-1])
                    factor_signals[code] = today_signal
            except Exception as e:
                pass

        mean_ic_5d = float(np.mean(factor_ics_5d)) if factor_ics_5d else np.nan
        mean_ic_20d = float(np.mean(factor_ics_20d)) if factor_ics_20d else np.nan
        n_buy = sum(1 for s in factor_signals.values() if s)

        daily_report['factors'][factor_name] = {
            'ic_5d': mean_ic_5d,
            'ic_20d': mean_ic_20d,
            'n_etfs': len(factor_ics_5d),
            'n_buy_signal': n_buy,
            'buy_etfs': [c for c, s in factor_signals.items() if s],
        }

        print(f"  5d IC: {mean_ic_5d:.4f} | 20d IC: {mean_ic_20d:.4f}")
        print(f"  当日买入信号: {n_buy}/15 ETF")

        if mean_ic_5d < 0.02 and not np.isnan(mean_ic_5d):
            daily_report['alerts'].append({
                'factor': factor_name,
                'type': 'IC_LOW',
                'message': f"{factor_name} 5d IC {mean_ic_5d:.4f} < 0.02 阈值",
                'severity': 'WARNING',
            })

    report_path = Path("data/monitor_top3_volatility_daily.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    history_path = Path("data/monitor_top3_volatility_history.json")
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except Exception:
            history = []
    history.append(daily_report)
    history = history[-30:]
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report_path.write_text(json.dumps(daily_report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    print(f"\n📄 今日报告: {report_path}")
    print(f"📄 历史 (30 天): {history_path}")

    if daily_report['alerts']:
        print(f"\n⚠️ {len(daily_report['alerts'])} 个告警:")
        for alert in daily_report['alerts']:
            print(f"  [{alert['severity']}] {alert['factor']}: {alert['message']}")


if __name__ == "__main__":
    main()
