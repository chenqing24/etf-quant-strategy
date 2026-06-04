#!/usr/bin/env python3
"""
v9 V1-001: 单因子基线实验（15 因子 × 15 ETF = 225 模型）
按 SOP-01 Step 3: IC 计算 + 因子评估

执行流程：
1. 加载 15 ETF 数据
2. 计算所有 15 因子信号（含 N6 反转）
3. 对每 (ETF, 因子) 计算 IC/IR/avg_trade/sharpe/win_rate
4. 输出 factor_ic_report.md + v1_report.json
5. 通过率 < 5% 触发 IS-002 反思

使用方式：
    python scripts/experiment/v9_v1_single_factor.py [--quick]

依赖：
    - src.data.loader
    - src.indicators.wrapper / n6_reversal
    - scripts.validators
"""
import json
import sys
import argparse
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
from scripts.validators import ComprehensiveValidator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ 配置 ============
ETF_POOL = [
    '510300', '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]

# 15 因子：T1-T4 (趋势) + M1-M4 (动量) + V1-V3 (量能) + B1 (布林) + N1-N3 (反转)
FACTOR_SIGNAL_FUNCS = {
    # 趋势类
    'T1_MACD红柱': lambda df: df['MACD_hist'] > 0,
    'T2_MA多头': lambda df: df['close'].rolling(5).mean() > df['close'].rolling(20).mean(),
    'T3_SAR趋势': lambda df: df['close'] > df.get('SAR_trend', df['close']),
    'T4_ADX趋势': lambda df: df['ADX'] > 25,
    # 动量类
    'M1_动量3日': lambda df: df['close'].pct_change(3) > 0.02,
    'M2_动量5日': lambda df: df['close'].pct_change(5) > 0.03,
    'M3_RSI适中': lambda df: (df['RSI_10'] > 40) & (df['RSI_10'] < 70),
    'M4_KDJ金叉': lambda df: (df['KDJ_K'] > df['KDJ_D']) & (df['KDJ_K'].shift(1) <= df['KDJ_D'].shift(1)),
    # 量能类
    'V1_放量': lambda df: df['volume'] > df['volume'].rolling(20).mean() * 1.5,
    'V2_OBV多头': lambda df: df['OBV'] > df['OBV'].rolling(20).mean(),
    'V3_资金流入': lambda df: (df['close'] > df['open']) & (df['volume'] > df['volume'].rolling(5).mean()),
    # 布林
    'B1_布林上轨突破': lambda df: df['close'] > df.get('BB_upper', df['close'] * 1.05),
    # N6 反转（新增）
    'N1_3日反转': signal_n1_3d_reversal,
    'N2_5日反转': signal_n2_5d_reversal,
    'N3_RSI超卖反弹': signal_n3_rsi_oversold,
}

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_signal(df, factor_name):
    """统一获取因子信号"""
    func = FACTOR_SIGNAL_FUNCS[factor_name]
    signal = func(df)
    if isinstance(signal, pd.Series):
        return signal.fillna(False).astype(bool)
    return signal


def calc_ic_per_etf(df: pd.DataFrame, signal: pd.Series) -> float:
    """计算 IC（信息系数）：信号与未来 5 日收益的相关性"""
    future_ret = df['close'].pct_change(5).shift(-5)
    valid = pd.DataFrame({'signal': signal.astype(int), 'ret': future_ret}).dropna()
    if len(valid) < 30:
        return 0.0
    return float(valid['signal'].corr(valid['ret']))


def calc_sharpe_simple(returns: pd.Series) -> float:
    """简化版 Sharpe (无风险利率=0, 年化 252)"""
    if len(returns) < 5 or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(252))


def backtest_signal(df: pd.DataFrame, signal: pd.Series,
                    stop_loss: float = -0.05, stop_profit: float = 0.10,
                    min_hold_days: int = 3, max_hold_days: int = 20) -> dict:
    """简单回测：信号 → 持有 max_hold_days 或触发止盈/止损"""
    df = df.copy()
    df['signal'] = signal.fillna(False).astype(bool)
    df['future_ret'] = df['close'].pct_change().shift(-1).fillna(0)

    # 简化：signal=1 时持有，0 时空仓
    position = df['signal'].astype(int)
    df['strategy_ret'] = position * df['future_ret']

    total_ret = (1 + df['strategy_ret']).prod() - 1
    avg_trade = df['strategy_ret'].mean()
    win_rate = (df['strategy_ret'] > 0).sum() / max((df['strategy_ret'] != 0).sum(), 1)
    sharpe = calc_sharpe_simple(df['strategy_ret'])

    return {
        'total_return': float(total_ret),
        'avg_trade': float(avg_trade),
        'win_rate': float(win_rate),
        'sharpe': sharpe,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='快速模式：5 ETF × 5 因子')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("V1-001: v1 单因子基线实验（15 因子 × 15 ETF）")
    logger.info("=" * 60)

    # 快速模式
    if args.quick:
        etfs = ETF_POOL[:5]
        factors = list(FACTOR_SIGNAL_FUNCS.keys())[:5]
        logger.info(f"快速模式: {len(etfs)} ETF × {len(factors)} 因子 = {len(etfs)*len(factors)} 模型")
    else:
        etfs = ETF_POOL
        factors = list(FACTOR_SIGNAL_FUNCS.keys())
        logger.info(f"全量模式: {len(etfs)} ETF × {len(factors)} 因子 = {len(etfs)*len(factors)} 模型")

    # 加载数据 + 计算指标
    loader = DataLoader()
    calc = IndicatorCalculator()
    data = {}
    indicators = {}
    for code in etfs:
        df = loader.load_single(code, min_rows=400)
        if df is not None:
            df = df.sort_values('date').reset_index(drop=True)
            data[code] = df
            indicators[code] = calc.calculate_all(df)
            logger.info(f"  {code}: {df['date'].min()} ~ {df['date'].max()} ({len(df)} 行)")

    # 跑模型
    results = []
    for code in etfs:
        if code not in indicators:
            continue
        df_ind = indicators[code]
        for factor_name in factors:
            try:
                signal = get_signal(df_ind, factor_name)
                ic = calc_ic_per_etf(df_ind, signal)
                bt = backtest_signal(data[code], signal)
                ir = abs(ic) / max(np.std([r['ic'] for r in results if r.get('ic') is not None]) if results else 0.1, 0.01)

                result = {
                    'etf': code,
                    'factor': factor_name,
                    'ic': ic,
                    'ir': ir,
                    **bt,
                }
                results.append(result)
            except Exception as e:
                logger.warning(f"  {code} × {factor_name} 失败: {e}")
                results.append({
                    'etf': code,
                    'factor': factor_name,
                    'error': str(e),
                    'ic': 0.0,
                    'ir': 0.0,
                    'total_return': 0.0,
                    'avg_trade': 0.0,
                    'win_rate': 0.0,
                    'sharpe': 0.0,
                })

    # 评估
    passed = [r for r in results if r.get('ic', 0) >= 0.02 and r.get('sharpe', 0) > 0]
    pass_rate = len(passed) / max(len(results), 1)
    logger.info(f"\n通过: {len(passed)}/{len(results)} ({pass_rate*100:.1f}%)")

    # Top 因子
    factor_stats = {}
    for r in results:
        if 'error' in r:
            continue
        f = r['factor']
        if f not in factor_stats:
            factor_stats[f] = []
        factor_stats[f].append(r['ic'])

    factor_summary = []
    for f, ics in factor_stats.items():
        if ics:
            factor_summary.append({
                'factor': f,
                'avg_ic': float(np.mean(ics)),
                'ic_std': float(np.std(ics)),
                'n_etfs': len(ics),
                'ir': float(np.mean(ics) / max(np.std(ics), 0.01)) if np.std(ics) > 0 else 0,
            })
    factor_summary.sort(key=lambda x: abs(x['avg_ic']), reverse=True)

    # 保存 JSON
    output = {
        'mission': 'V1-001',
        'step': 'SOP-01 Step 3',
        'timestamp': datetime.now().isoformat(),
        'config': {
            'etf_count': len(etfs),
            'factor_count': len(factors),
            'mode': 'quick' if args.quick else 'full',
        },
        'summary': {
            'total_models': len(results),
            'passed_models': len(passed),
            'pass_rate': pass_rate,
        },
        'factor_summary': factor_summary,
        'detail': results,
    }

    json_path = OUTPUT_DIR / 'v1_report.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    logger.info(f"\n报告已保存: {json_path}")

    # Markdown 报告
    md_lines = [
        "# v1 单因子基线报告",
        "",
        f"**生成时间**: {datetime.now().isoformat()}",
        f"**模式**: {'快速' if args.quick else '全量'}",
        f"**ETF 数**: {len(etfs)}",
        f"**因子数**: {len(factors)}",
        f"**总模型**: {len(results)}",
        f"**通过模型**: {len(passed)} ({pass_rate*100:.1f}%)",
        "",
        "## Top 因子（按 |avg_ic| 排序）",
        "",
        "| 因子 | 平均 IC | IC 标准差 | IR | 覆盖 ETF |",
        "|------|--------|----------|---|---------|",
    ]
    for f in factor_summary[:15]:
        md_lines.append(
            f"| {f['factor']} | {f['avg_ic']:.4f} | {f['ic_std']:.4f} | {f['ir']:.3f} | {f['n_etfs']} |"
        )

    md_lines.extend([
        "",
        "## 通过率检查",
        "",
        f"- 阈值: IC >= 0.02 + Sharpe > 0",
        f"- 通过率: {pass_rate*100:.1f}%",
    ])
    if pass_rate < 0.05:
        md_lines.append("- ⚠️ **通过率 < 5%！触发 IS-002 反思机制**")
    else:
        md_lines.append(f"- ✅ 通过率 {pass_rate*100:.1f}% >= 5%")

    md_path = OUTPUT_DIR / 'factor_ic_report.md'
    md_path.write_text('\n'.join(md_lines))
    logger.info(f"报告已保存: {md_path}")

    return 0 if pass_rate >= 0.05 else 2


if __name__ == '__main__':
    sys.exit(main())
