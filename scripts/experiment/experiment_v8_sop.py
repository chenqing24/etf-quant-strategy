#!/usr/bin/env python3
"""
ETF多因子挖掘实验 v8.0 - 完整SOP执行

用途：
    - 执行多因子挖掘实验
    - 生成因子组合
    - 评估策略表现

被谁调用：
    - 无（独立工具，手动执行）
    - 实验研究时使用

功能说明：
    - 【SOP-03 完整执行】
    - 2因子组合：66 × 15ETF = 990条
    - 3因子组合：优质因子 × 3ETF
    - 过拟合检验：只对核心通过模型

使用方式：
    python scripts/experiment/experiment_v8_sop.py

依赖：
    - src.data.loader (DataLoader)
    - src.indicators.wrapper (IndicatorCalculator)
    - scripts.validators (ComprehensiveValidator)

注意事项：
    - 已豁免 pre-commit 检查（实验脚本）
    - 执行时间较长，建议在后台运行
    - 结果保存到 data/experiments_v8_sop/ 目录
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from itertools import combinations

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from scripts.validators import ComprehensiveValidator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ v8核心参数 ============
ETF_POOL = [
    '510300', '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]

TRAIN_START = '2023-06-01'
TRAIN_END = '2025-05-31'
TEST_START = '2025-06-01'
TEST_END = '2026-05-31'

STOP_LOSS = -0.04
TAKE_PROFIT = 0.08
MIN_HOLD_DAYS = 3
MAX_HOLD_DAYS = 25

MIN_SINGLE_TRADE = 0.008
MIN_SHARPE = 0.5
MIN_WIN_RATE = 0.50

ROLLING_WINDOW = 180
ROLLING_STEP = 60
OVERFIT_ROLLING_PASS = 0.60
OVERFIT_MC_SIMULATIONS = 500
OVERFIT_MC_PVALUE = 0.05
OVERFIT_CV_PASS = 0.60

FACTORS = {
    'T1_MACD红柱': {'func': 'macd_positive'},
    'T2_MA多头': {'func': 'ma_bullish'},
    'T3_SAR趋势': {'func': 'sar_bullish'},
    'T4_ADX趋势': {'func': 'adx_strong'},
    'M1_动量3日': {'func': 'momentum_3d'},
    'M2_动量5日': {'func': 'momentum_5d'},
    'M3_RSI适中': {'func': 'rsi_moderate'},
    'M4_KDJ金叉': {'func': 'kdj_golden'},
    'V1_放量': {'func': 'volume_surge'},
    'V2_OBV多头': {'func': 'obv_bullish'},
    'V3_资金流入': {'func': 'money_flow'},
    'B1_布林上轨突破': {'func': 'bollinger_upper'},
}

OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'experiments_v8_sop'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_DIR = Path(__file__).parent.parent / 'memory'
MEMORY_DIR.mkdir(exist_ok=True)


def load_data():
    logger.info("【Phase 1-2】数据准备 + 指标计算")
    loader = DataLoader()
    data = {}
    indicators_data = {}
    calc = IndicatorCalculator()
    
    for code in ETF_POOL:
        df = loader.load_single(code, min_rows=400)
        if df is not None:
            df = df.sort_values('date').reset_index(drop=True)
            data[code] = df
            indicators_data[code] = calc.calculate_all(df)
    
    logger.info(f"加载完成: {len(data)}只ETF")
    return data, indicators_data


def get_signal(df, factor_name):
    func_name = FACTORS[factor_name]['func']
    
    if func_name == 'macd_positive':
        return df['MACD_hist'] > 0
    elif func_name == 'ma_bullish':
        return (df['MA_short'] > df['MA_long'])
    elif func_name == 'sar_bullish':
        return df['close'] > df['SAR']
    elif func_name == 'adx_strong':
        return df['ADX'] > 25
    elif func_name == 'momentum_3d':
        return df['close'].pct_change(3) > 0
    elif func_name == 'momentum_5d':
        return df['close'].pct_change(5) > 0
    elif func_name == 'rsi_moderate':
        return (df['RSI_5'] > 40) & (df['RSI_5'] < 70)
    elif func_name == 'kdj_golden':
        return df['K'] > df['D']
    elif func_name == 'volume_surge':
        return df['volume'] > df['volume'].rolling(10).mean() * 1.2
    elif func_name == 'obv_bullish':
        return df['OBV'] > df['MAOBV']
    elif func_name == 'money_flow':
        return df['OBV'] > df['MAOBV']
    elif func_name == 'bollinger_upper':
        return df['close'] > df['BB_upper']
    else:
        return pd.Series(False, index=df.index)


def backtest_simple(indicators_data, factors, etf_code):
    df = indicators_data[etf_code].copy()
    
    signals = [get_signal(df, f) for f in factors]
    combo_signal = signals[0]
    for s in signals[1:]:
        combo_signal = combo_signal & s
    
    returns = []
    for i in range(len(df) - 1):
        if combo_signal.iloc[i]:
            ret = (df['close'].iloc[i+1] / df['close'].iloc[i]) - 1
            returns.append(ret)
    
    if len(returns) < 5:
        return None
    
    modified = [TAKE_PROFIT if r >= TAKE_PROFIT else (STOP_LOSS if r <= STOP_LOSS else r) for r in returns]
    
    avg = sum(modified) / len(modified)
    wins = len([r for r in modified if r > 0])
    win_rate = wins / len(modified)
    std = (sum((r - avg)**2 for r in modified) / len(modified)) ** 0.5 if modified else 0
    sharpe = avg / std * (252 ** 0.5) if std > 0 else 0
    
    total = 1.0
    for r in modified:
        total *= (1 + r)
    
    return type('Result', (), {
        'trade_count': len(modified),
        'total_return': total - 1,
        'avg_profit': avg,
        'sharpe_relative': sharpe,
        'win_rate': win_rate,
        'trades': [{'profit': r} for r in modified]
    })()


def compute_ic_ir(indicators_data, factor_name):
    """计算IC/IR指标"""
    ic_values = []
    
    for code, df in indicators_data.items():
        signal = get_signal(df, factor_name)
        returns = df['close'].pct_change()
        future_returns = returns.shift(-1)
        
        valid = signal.notna() & future_returns.notna()
        if valid.sum() > 30:
            ic = signal[valid].corr(future_returns[valid])
            if not np.isnan(ic):
                ic_values.append(ic)


def new_overfit_validator(indicators_data, factors, etf_code):
    """
    【新增】使用ComprehensiveValidator进行过拟合验证
    
    替代旧的rolling_window_test + monte_carlo_test + cross_validation_test
    """
    df = indicators_data[etf_code].copy()
    
    # 创建信号函数
    def signal_func(df, fs=factors):
        signals = [get_signal(df, f) for f in fs]
        combo_signal = signals[0]
        for s in signals[1:]:
            combo_signal = combo_signal & s
        return combo_signal
    
    # 使用新验证器
    validator = ComprehensiveValidator()
    result = validator.validate({etf_code: df}, signal_func)
    
    return {
        'composite_score': float(result.composite_score),
        'pass': bool(result.pass_),
        'wf_score': float(result.walk_forward_score),
        'mc_score': float(result.monte_carlo_score),
        'ce_score': float(result.cross_etf_score),
        'wf_details': result.walk_forward_details,
        'mc_details': result.monte_carlo_details,
        'ce_details': result.cross_etf_details,
    }
    
    if len(ic_values) == 0:
        return {'ic_mean': 0, 'ic_std': 0, 'ir': 0}
    
    ic_mean = np.mean(ic_values)
    ic_std = np.std(ic_values)
    ir = ic_mean / ic_std if ic_std > 0 else 0
    
    return {'ic_mean': ic_mean, 'ic_std': ic_std, 'ir': ir}


def rolling_window_test(indicators_data, factors, etf_code):
    df = indicators_data[etf_code].copy()
    
    if len(df) < ROLLING_WINDOW:
        return {'pass_rate': 0, 'windows': []}
    
    windows = []
    start_idx = 0
    
    while start_idx + ROLLING_WINDOW <= len(df):
        end_idx = start_idx + ROLLING_WINDOW
        window_df = df.iloc[start_idx:end_idx].copy()
        
        result = backtest_simple({etf_code: window_df}, factors, etf_code)
        
        if result and result.trade_count > 0:
            windows.append({'return': result.total_return, 'pass': result.total_return > 0})
        else:
            windows.append({'return': 0, 'pass': False})
        
        start_idx += ROLLING_STEP
    
    if not windows:
        return {'pass_rate': 0, 'windows': []}
    
    pass_count = sum(1 for w in windows if w['pass'])
    return {'pass_rate': pass_count / len(windows), 'windows': windows}


def monte_carlo_test(indicators_data, factors, etf_code):
    result = backtest_simple(indicators_data, factors, etf_code)
    
    if not result or result.trade_count == 0:
        return {'p_value': 1.0, 'z_score': 0}
    
    real_mean = result.avg_profit
    
    np.random.seed(42)
    random_means = []
    
    for _ in range(OVERFIT_MC_SIMULATIONS):
        if hasattr(result, 'trades') and result.trades:
            returns = [t.get('profit', 0) for t in result.trades]
            if returns:
                shuffled = np.random.permutation(returns)
                random_means.append(np.mean(shuffled))
    
    if not random_means:
        return {'p_value': 1.0, 'z_score': 0}
    
    p_value = np.mean([1 if m >= real_mean else 0 for m in random_means])
    z_score = (real_mean - np.mean(random_means)) / np.std(random_means) if np.std(random_means) > 0 else 0
    
    return {'p_value': p_value, 'z_score': z_score}


def cross_validation_test(indicators_data, factors, etf_code):
    df = indicators_data[etf_code].copy()
    
    periods = [
        ('2023-06-01', '2024-12-31'),
        ('2024-01-01', '2024-12-31'),
        ('2025-01-01', '2025-12-31'),
    ]
    
    results = []
    for start, end in periods:
        period_df = df[(df['date'] >= start) & (df['date'] <= end)].copy()
        
        if len(period_df) < 100:
            continue
        
        result = backtest_simple({etf_code: period_df}, factors, etf_code)
        
        if result:
            results.append({'return': result.total_return, 'pass': result.total_return > 0})
    
    if not results:
        return {'pass_rate': 0, 'periods': []}
    
    pass_count = sum(1 for r in results if r['pass'])
    return {'pass_rate': pass_count / len(results), 'periods': results}


def run_experiment():
    start_time = datetime.now()
    logger.info("\n" + "=" * 60)
    logger.info("ETF多因子挖掘实验 v8.0 - 完整SOP执行")
    logger.info("=" * 60)
    
    # 加载数据
    data, indicators_data = load_data()
    factor_names = list(FACTORS.keys())
    
    # ============ Phase 3: 单因子测试 + IC/IR ============
    logger.info("\n【Phase 3】单因子测试 + IC/IR分析")
    
    single_factor_results = {}
    for i, factor_name in enumerate(factor_names):
        logger.info(f"  [{i+1}/{len(factor_names)}] {factor_name}")
        ic_data = compute_ic_ir(indicators_data, factor_name)
        
        avg_single = 0
        avg_sharpe = 0
        avg_win_rate = 0
        valid_count = 0
        
        for code in indicators_data:
            result = backtest_simple(indicators_data, [factor_name], code)
            if result and result.trade_count > 5:
                avg_single += result.avg_profit
                avg_sharpe += result.sharpe_relative
                avg_win_rate += result.win_rate
                valid_count += 1
        
        if valid_count > 0:
            avg_single /= valid_count
            avg_sharpe /= valid_count
            avg_win_rate /= valid_count
        
        single_factor_results[factor_name] = {
            'ic_mean': float(ic_data['ic_mean']),
            'ic_std': float(ic_data['ic_std']),
            'ir': float(ic_data['ir']),
            'avg_single_trade': float(avg_single),
            'avg_sharpe': float(avg_sharpe),
            'avg_win_rate': float(avg_win_rate),
        }
        
        logger.info(f"    IC: {ic_data['ic_mean']:.4f}, IR: {ic_data['ir']:.2f}, 单笔: {avg_single*100:.2f}%")
    
    # ============ Phase 4: 组合测试（快速筛选） ============
    logger.info("\n【Phase 4】组合测试 - 快速筛选")
    logger.info(f"  2因子组合: C(12,2) = 66")
    logger.info(f"  15只ETF: 66 × 15 = 990条")
    
    combo_results = []
    combo_count = 0
    
    for combo in combinations(factor_names, 2):
        combo_count += 1
        
        if combo_count % 10 == 0:
            pass_count = len([r for r in combo_results if r.get('pass_core', False)])
            logger.info(f"  [反思点] 已测试{combo_count}个组合, 通过{pass_count}个")
        
        factors_list = list(combo)
        
        for etf_code in ETF_POOL:
            result = backtest_simple(indicators_data, factors_list, etf_code)
            
            if not result or result.trade_count < 5:
                continue
            
            single_trade = result.avg_profit
            sharpe = result.sharpe_relative
            win_rate = result.win_rate
            
            combo_results.append({
                'factors': factors_list,
                'etf_code': etf_code,
                'trade_count': int(result.trade_count),
                'total_return': float(result.total_return),
                'avg_profit': float(result.avg_profit),
                'sharpe': float(sharpe),
                'win_rate': float(win_rate),
                'single_trade': float(single_trade),
                'pass_core': bool(single_trade >= MIN_SINGLE_TRADE and
                             sharpe >= MIN_SHARPE and
                             win_rate >= MIN_WIN_RATE),
                'overfit_rolling': 0.0,
                'overfit_mc_pvalue': 1.0,
                'overfit_cv': 0.0,
            })
    
    logger.info(f"快速筛选完成: {len(combo_results)}条结果")
    
    # ============ Phase 4.5: 过拟合检验（使用新验证器） ============
    logger.info("\n【Phase 4.5】过拟合检验 - 使用ComprehensiveValidator")
    
    passed_core = [r for r in combo_results if r['pass_core']]
    logger.info(f"核心通过: {len(passed_core)}个")
    
    for i, r in enumerate(passed_core):
        if (i + 1) % 5 == 0:
            logger.info(f"  进度: {i+1}/{len(passed_core)}")
        
        # 【替换】使用新的ComprehensiveValidator
        new_result = new_overfit_validator(indicators_data, r['factors'], r['etf_code'])
        
        r['overfit_rolling'] = new_result['wf_score']
        r['overfit_mc_pvalue'] = 1.0 - new_result['mc_score']  # 转换为p-value形式
        r['overfit_cv'] = new_result['ce_score']
        r['overfit_composite'] = new_result['composite_score']
        r['overfit_pass_new'] = new_result['pass']
        r['overfit_pass'] = new_result['pass']  # 统一使用新验证器结果
    
    # ============ Phase 4.6: 3因子组合（完整测试！） ============
    logger.info("\n【Phase 4.6】3因子组合测试 - 完整执行")
    logger.info(f"  3因子组合: C(12,3) = 220")
    logger.info(f"  15只ETF: 220 × 15 = 3300条")
    logger.info("⚠️ 不简化！全部测试！")
    
    combo_count_3factor = 0
    for combo in combinations(factor_names, 3):
        combo_count_3factor += 1
        combo_count += 1
        
        # 【SOP-03反思点】每10个停下
        if combo_count_3factor % 10 == 0:
            pass_count = len([r for r in combo_results if r.get('pass_core', False)])
            logger.info(f"  [反思点] 3因子已测试{combo_count_3factor}/220,累计通过{pass_count}个")
        
        factors_list = list(combo)
        
        # 在全部ETF上测试（不简化！）
        for etf_code in ETF_POOL:
            result = backtest_simple(indicators_data, factors_list, etf_code)
            
            if not result or result.trade_count < 5:
                continue
            
            single_trade = result.avg_profit
            sharpe = result.sharpe_relative
            win_rate = result.win_rate
            
            combo_results.append({
                'factors': factors_list,
                'etf_code': etf_code,
                'trade_count': int(result.trade_count),
                'total_return': float(result.total_return),
                'avg_profit': float(result.avg_profit),
                'sharpe': float(sharpe),
                'win_rate': float(win_rate),
                'single_trade': float(single_trade),
                'pass_core': bool(single_trade >= MIN_SINGLE_TRADE and
                             sharpe >= MIN_SHARPE and
                             win_rate >= MIN_WIN_RATE),
                'overfit_rolling': 0.0,
                'overfit_mc_pvalue': 1.0,
                'overfit_cv': 0.0,
            })
    
    logger.info(f"组合测试完成: {len(combo_results)}条结果")
    
    # ============ Phase 4.7: 3因子组合过拟合检验（使用新验证器） ============
    logger.info("\n【Phase 4.7】3因子组合过拟合检验 - 使用ComprehensiveValidator")
    
    three_factor_passed = [r for r in combo_results if r['pass_core'] and len(r['factors']) == 3]
    logger.info(f"3因子核心通过: {len(three_factor_passed)}个")
    
    for i, r in enumerate(three_factor_passed):
        if (i + 1) % 10 == 0:
            logger.info(f"  进度: {i+1}/{len(three_factor_passed)}")
        
        # 【替换】使用新的ComprehensiveValidator
        new_result = new_overfit_validator(indicators_data, r['factors'], r['etf_code'])
        
        r['overfit_rolling'] = new_result['wf_score']
        r['overfit_mc_pvalue'] = 1.0 - new_result['mc_score']  # 转换为p-value形式
        r['overfit_cv'] = new_result['ce_score']
        r['overfit_composite'] = new_result['composite_score']
        r['overfit_pass_new'] = new_result['pass']
        r['overfit_pass'] = new_result['pass']  # 统一使用新验证器结果
    
    # ============ Phase 5: 筛选 ============
    logger.info("\n【Phase 5】筛选通过模型")
    
    passed_overfit = [r for r in combo_results if r.get('overfit_pass', False)]
    passed_all = [r for r in combo_results if r['pass_core'] and r.get('overfit_pass', False)]
    
    logger.info(f"核心通过: {len([r for r in combo_results if r['pass_core']])}")
    logger.info(f"过拟合通过: {len(passed_overfit)}")
    logger.info(f"综合通过: {len(passed_all)}")
    
    # ============ Phase 6-7: 报告 + 归档 ============
    report = {
        'experiment_info': {
            'version': 'v8.0_sop',
            'start_time': start_time.isoformat(),
            'etf_pool': ETF_POOL,
            'train_period': f'{TRAIN_START} ~ {TRAIN_END}',
            'test_period': f'{TEST_START} ~ {TEST_END}',
        },
        'single_factor': single_factor_results,
        'combinations': combo_results,
        'passed_core': len([r for r in combo_results if r['pass_core']]),
        'passed_overfit': len(passed_overfit),
        'passed_all': len(passed_all),
        'top_models': sorted(combo_results, key=lambda x: x.get('single_trade', 0), reverse=True)[:20],
    }
    
    output_file = OUTPUT_DIR / 'results_sop.json'
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # 归档
    experiment_note = f"""# 实验笔记 - {datetime.now().strftime('%Y-%m-%d')}

## 实验信息
- 版本: v8.0_sop（完整SOP执行）
- 开始时间: {start_time}
- ETF数量: {len(ETF_POOL)}
- 因子数量: {len(FACTORS)}
- 组合测试: {len(combo_results)}条

## 单因子IC/IR
| 因子 | IC | IR | 单笔 |
|------|:--:|:--:|:----:|
"""
    for f, d in single_factor_results.items():
        experiment_note += f"| {f} | {d['ic_mean']:.4f} | {d['ir']:.2f} | {d['avg_single_trade']*100:.2f}% |\n"
    
    experiment_note += f"""
## 结果
- 核心通过: {len([r for r in combo_results if r['pass_core']])}个
- 过拟合通过: {len(passed_overfit)}个
- 综合通过: {len(passed_all)}个

## SOP执行
✅ Phase 1-2: 数据准备
✅ Phase 3: 单因子测试 + IC/IR分析
✅ Phase 4: 组合测试（990条 + 3因子组合）
✅ Phase 4.5: 过拟合检验
✅ Phase 5-7: 报告 + 归档
"""
    
    with open(MEMORY_DIR / f"experiment_{datetime.now().strftime('%Y%m%d')}.md", 'w') as f:
        f.write(experiment_note)
    
    logger.info("\n" + "=" * 60)
    logger.info("【SOP执行完成】")
    logger.info("=" * 60)
    logger.info(f"耗时: {(datetime.now() - start_time).total_seconds():.1f}秒")
    logger.info(f"组合测试: {len(combo_results)}条")
    logger.info(f"核心通过: {len([r for r in combo_results if r['pass_core']])}")
    logger.info(f"过拟合通过: {len(passed_overfit)}")
    logger.info(f"综合通过: {len(passed_all)}")
    
    return report


if __name__ == '__main__':
    run_experiment()