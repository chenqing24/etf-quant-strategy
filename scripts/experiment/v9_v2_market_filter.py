#!/usr/bin/env python3
"""
v9 V2-001: 单因子 + 大盘过滤 + N6 反转
按 SOP-01 Step 4: 叠加 510300 大盘状态过滤

策略：仅当 510300 处于上升趋势时，跟随 ETF 的买入信号才生效
大盘状态：MA5 > MA20 = 1（上升），否则 0
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
from src.indicators.n6_reversal import (
    signal_n1_3d_reversal,
    signal_n2_5d_reversal,
    signal_n3_rsi_oversold,
)
from scripts.experiment.v9_v1_single_factor import (
    FACTOR_SIGNAL_FUNCS,
    get_signal,
    calc_ic_per_etf,
    calc_sharpe_simple,
    ETF_POOL,
    OUTPUT_DIR,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calc_market_regime(df_510300: pd.DataFrame) -> pd.Series:
    """计算 510300 大盘状态：MA5>MA20 → 1"""
    ma5 = df_510300['close'].rolling(5, min_periods=1).mean()
    ma20 = df_510300['close'].rolling(20, min_periods=1).mean()
    return (ma5 > ma20).astype(int).fillna(0)


def backtest_with_market_filter(
    df: pd.DataFrame,
    df_market: pd.DataFrame,
    signal: pd.Series,
) -> dict:
    """大盘过滤回测：仅在 510300 上升时启用信号"""
    df = df.copy()
    df_market = df_market.copy()

    market_regime = calc_market_regime(df_market)
    market_map = pd.Series(market_regime.values, index=df_market['date'].values)
    market_aligned = df['date'].map(market_map).fillna(0).astype(int)

    position = (signal.fillna(False).astype(int) * market_aligned)
    future_ret = df['close'].pct_change().shift(-1).fillna(0)
    strategy_ret = position * future_ret

    total_ret = (1 + strategy_ret).prod() - 1
    avg_trade = strategy_ret[strategy_ret != 0].mean() if (strategy_ret != 0).any() else 0
    win_rate = (strategy_ret > 0).sum() / max((strategy_ret != 0).sum(), 1)
    sharpe = calc_sharpe_simple(strategy_ret)

    return {
        'total_return': float(total_ret),
        'avg_trade': float(avg_trade),
        'win_rate': float(win_rate),
        'sharpe': sharpe,
        'market_pct': float(market_aligned.mean()),
    }


def main():
    logger.info("=" * 60)
    logger.info("V2-001: 单因子 + 大盘过滤 + N6 反转")
    logger.info("=" * 60)

    # 加载数据
    loader = DataLoader()
    calc = IndicatorCalculator()
    data = {}
    indicators = {}
    for code in ETF_POOL:
        df = loader.load_single(code, min_rows=400)
        if df is not None:
            df = df.sort_values('date').reset_index(drop=True)
            data[code] = df
            indicators[code] = calc.calculate_all(df)

    if '510300' not in indicators:
        logger.error("510300 大盘数据缺失")
        return 1

    df_market = data['510300']
    market_days = calc_market_regime(df_market).sum()
    logger.info(f"510300 大盘上升期: {market_days}/{len(df_market)} ({market_days/len(df_market)*100:.1f}%)")

    # 跑模型
    results = []
    for code in ETF_POOL:
        if code not in indicators:
            continue
        df_ind = indicators[code]
        for factor_name in FACTOR_SIGNAL_FUNCS.keys():
            try:
                signal = get_signal(df_ind, factor_name)
                ic = calc_ic_per_etf(df_ind, signal)
                bt = backtest_with_market_filter(data[code], df_market, signal)

                result = {
                    'etf': code,
                    'factor': factor_name,
                    'ic': ic,
                    **bt,
                }
                results.append(result)
            except Exception as e:
                logger.warning(f"  {code} × {factor_name} 失败: {e}")

    # 评估
    passed = [r for r in results if r.get('ic', 0) >= 0.02 and r.get('sharpe', 0) > 0]
    pass_rate = len(passed) / max(len(results), 1)
    logger.info(f"\n通过: {len(passed)}/{len(results)} ({pass_rate*100:.1f}%)")

    # 因子聚合
    factor_stats = {}
    for r in results:
        f = r['factor']
        factor_stats.setdefault(f, []).append(r)

    factor_summary = []
    for f, rs in factor_stats.items():
        avg_ic = np.mean([r['ic'] for r in rs])
        avg_sharpe = np.mean([r['sharpe'] for r in rs])
        avg_win = np.mean([r['win_rate'] for r in rs])
        factor_summary.append({
            'factor': f,
            'avg_ic': float(avg_ic),
            'avg_sharpe': float(avg_sharpe),
            'avg_win_rate': float(avg_win),
            'n_etfs': len(rs),
        })
    factor_summary.sort(key=lambda x: x['avg_sharpe'], reverse=True)

    # 输出
    output = {
        'mission': 'V2-001',
        'step': 'SOP-01 Step 4',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'market_filter': '510300 MA5>MA20',
            'market_up_pct': float(market_days/len(df_market)),
            'factor_count': len(FACTOR_SIGNAL_FUNCS),
        },
        'summary': {
            'total_models': len(results),
            'passed_models': len(passed),
            'pass_rate': pass_rate,
        },
        'factor_summary': factor_summary,
        'detail': results,
    }

    json_path = OUTPUT_DIR / 'v2_report.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    logger.info(f"报告已保存: {json_path}")

    # Markdown
    md_lines = [
        "# v2 单因子 + 大盘过滤 + N6 报告",
        "",
        f"**大盘过滤**: 510300 MA5>MA20 = 上升期",
        f"**大盘上升占比**: {market_days/len(df_market)*100:.1f}%",
        f"**通过率**: {pass_rate*100:.1f}% ({len(passed)}/{len(results)})",
        "",
        "## Top 因子（按 avg_sharpe 排序）",
        "",
        "| 因子 | 平均 IC | 平均 Sharpe | 平均胜率 | 覆盖 ETF |",
        "|------|--------|------------|---------|---------|",
    ]
    for f in factor_summary[:15]:
        md_lines.append(
            f"| {f['factor']} | {f['avg_ic']:.4f} | {f['avg_sharpe']:.3f} | {f['avg_win_rate']*100:.1f}% | {f['n_etfs']} |"
        )

    md_lines.extend([
        "",
        "## 与 v1 对比",
        "",
        f"- v1 基础: 55.6%",
        f"- v2 + 大盘过滤: {pass_rate*100:.1f}%",
        f"- 提升: {(pass_rate-0.556)*100:+.1f} pp",
    ])

    md_path = OUTPUT_DIR / 'v2_report.md'
    md_path.write_text('\n'.join(md_lines))
    logger.info(f"报告已保存: {md_path}")

    return 0 if pass_rate >= 0.05 else 2


if __name__ == '__main__':
    sys.exit(main())
