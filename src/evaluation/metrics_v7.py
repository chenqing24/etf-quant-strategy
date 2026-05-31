# -*- coding: utf-8 -*-
"""
ETF量化策略完整评价体系 v7.0
============================
评价维度：8大类，43个指标
文档位置: docs/EVALUATION_SYSTEM_V7.md
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

# ============================================================
# 一、维度定义
# ============================================================
DIMENSIONS = [
    {'key': 'returns', 'name': '收益', 'weight': 0.20},
    {'key': 'risk', 'name': '风险', 'weight': 0.20},
    {'key': 'risk_adjusted', 'name': '风险调整收益', 'weight': 0.15},
    {'key': 'win_rate', 'name': '胜率', 'weight': 0.10},
    {'key': 'trading', 'name': '交易', 'weight': 0.05},
    {'key': 'robustness', 'name': '稳健性', 'weight': 0.15},
    {'key': 'cost', 'name': '成本', 'weight': 0.10},
    {'key': 'lifecycle', 'name': '生命周期', 'weight': 0.05},
]

# ============================================================
# 二、指标元数据
# ============================================================
METRICS = [
    # ----- 收益维度 -----
    {'key': 'absolute_return', 'dimension': 'returns', 'name': '绝对总收益',
     'type': 'higher', 'good': 0.50, 'pass': 0.30, 'weight': 0.05},
    {'key': 'relative_return', 'dimension': 'returns', 'name': '相对总收益',
     'type': 'higher', 'good': 0.15, 'pass': 0.05, 'weight': 0.05},
    {'key': 'annual_return', 'dimension': 'returns', 'name': '年化收益',
     'type': 'higher', 'good': 0.25, 'pass': 0.15, 'weight': 0.04},
    {'key': 'alpha_annual', 'dimension': 'returns', 'name': 'Alpha年化',
     'type': 'higher', 'good': 0.10, 'pass': 0.05, 'weight': 0.04},
    {'key': 'excess_return', 'dimension': 'returns', 'name': '超额收益',
     'type': 'higher', 'good': 0.05, 'pass': 0.02, 'weight': 0.02},

    # ----- 风险维度 -----
    {'key': 'max_drawdown', 'dimension': 'risk', 'name': '最大回撤',
     'type': 'lower', 'good': 0.15, 'pass': 0.30, 'weight': 0.08},
    {'key': 'max_drawdown_duration', 'dimension': 'risk', 'name': '最大回撤持续天数',
     'type': 'lower', 'good': 15, 'pass': 30, 'weight': 0.03},
    {'key': 'max_consecutive_loss', 'dimension': 'risk', 'name': '最大连续亏损',
     'type': 'lower', 'good': 0.08, 'pass': 0.15, 'weight': 0.03},
    {'key': 'daily_volatility', 'dimension': 'risk', 'name': '日波动率',
     'type': 'lower', 'good': 0.015, 'pass': 0.025, 'weight': 0.03},
    {'key': 'var_95', 'dimension': 'risk', 'name': 'VaR(95%)',
     'type': 'lower', 'good': -0.02, 'pass': -0.05, 'weight': 0.03},

    # ----- 风险调整收益 -----
    {'key': 'sharpe_absolute', 'dimension': 'risk_adjusted', 'name': '夏普比率（绝对）',
     'type': 'higher', 'good': 2.0, 'pass': 1.0, 'weight': 0.04},
    {'key': 'sharpe_relative', 'dimension': 'risk_adjusted', 'name': '夏普比率（相对）',
     'type': 'higher', 'good': 1.5, 'pass': 0.5, 'weight': 0.03},
    {'key': 'sortino_ratio', 'dimension': 'risk_adjusted', 'name': '索提诺比率',
     'type': 'higher', 'good': 2.5, 'pass': 1.2, 'weight': 0.02},
    {'key': 'calmar_ratio', 'dimension': 'risk_adjusted', 'name': '卡尔玛比率',
     'type': 'higher', 'good': 2.0, 'pass': 1.0, 'weight': 0.02},
    {'key': 'info_ratio', 'dimension': 'risk_adjusted', 'name': '信息比率IR',
     'type': 'higher', 'good': 1.0, 'pass': 0.5, 'weight': 0.02},
    {'key': 'omega_ratio', 'dimension': 'risk_adjusted', 'name': 'Omega比率',
     'type': 'higher', 'good': 1.5, 'pass': 1.2, 'weight': 0.02},

    # ----- 胜率维度 -----
    {'key': 'win_rate', 'dimension': 'win_rate', 'name': '胜率',
     'type': 'higher', 'good': 0.55, 'pass': 0.50, 'weight': 0.03},
    {'key': 'profit_loss_ratio', 'dimension': 'win_rate', 'name': '盈亏比',
     'type': 'higher', 'good': 1.5, 'pass': 1.0, 'weight': 0.02},
    {'key': 'avg_profit', 'dimension': 'win_rate', 'name': '平均盈利额',
     'type': 'higher', 'good': 0.012, 'pass': 0.008, 'weight': 0.01},
    {'key': 'avg_loss', 'dimension': 'win_rate', 'name': '平均亏损额',
     'type': 'lower', 'good': 0.01, 'pass': 0.015, 'weight': 0.01},
    {'key': 'excess_win_rate', 'dimension': 'win_rate', 'name': '超额胜率',
     'type': 'higher', 'good': 0.55, 'pass': 0.50, 'weight': 0.02},
    {'key': 'relative_profit_loss', 'dimension': 'win_rate', 'name': '相对盈亏比',
     'type': 'higher', 'good': 1.0, 'pass': 0.8, 'weight': 0.01},

    # ----- 交易维度 -----
    {'key': 'total_trades', 'dimension': 'trading', 'name': '总交易笔数',
     'type': 'range', 'good': [400, 600], 'pass': [100, 2000], 'weight': 0.005},
    {'key': 'trade_frequency', 'dimension': 'trading', 'name': '交易频率',
     'type': 'lower', 'good': 3, 'pass': 5, 'weight': 0.005},
    {'key': 'avg_holding_days', 'dimension': 'trading', 'name': '平均持仓天数',
     'type': 'range', 'good': [7, 13], 'pass': [5, 15], 'weight': 0.01},
    {'key': 'max_holding_days', 'dimension': 'trading', 'name': '最大持仓天数',
     'type': 'lower', 'good': 15, 'pass': 20, 'weight': 0.005},
    {'key': 'min_holding_days', 'dimension': 'trading', 'name': '最小持仓天数',
     'type': 'higher', 'good': 3, 'pass': 3, 'weight': 0.005},
    {'key': 'holding_std', 'dimension': 'trading', 'name': '持仓天数标准差',
     'type': 'lower', 'good': 5, 'pass': 8, 'weight': 0.005},
    {'key': 'turnover_rate', 'dimension': 'trading', 'name': '换手率',
     'type': 'lower', 'good': 3.0, 'pass': 5.0, 'weight': 0.005},
    {'key': 'avg_position_size', 'dimension': 'trading', 'name': '平均持仓规模',
     'type': 'range', 'good': [0.25, 0.35], 'pass': [0.15, 0.50], 'weight': 0.01},

    # ----- 稳健性维度 -----
    {'key': 'rolling_pass_rate', 'dimension': 'robustness', 'name': '滚动窗口通过率',
     'type': 'higher', 'good': 0.70, 'pass': 0.60, 'weight': 0.04},
    {'key': 'rolling_avg_return', 'dimension': 'robustness', 'name': '滚动窗口平均收益',
     'type': 'higher', 'good': 0.03, 'pass': 0.02, 'weight': 0.03},
    {'key': 'monte_carlo_pvalue', 'dimension': 'robustness', 'name': '蒙特卡洛p值',
     'type': 'lower', 'good': 0.03, 'pass': 0.10, 'weight': 0.03},
    {'key': 'crossval_pass_rate', 'dimension': 'robustness', 'name': '交叉验证通过率',
     'type': 'higher', 'good': 0.70, 'pass': 0.60, 'weight': 0.03},
    {'key': 'crossval_avg_return', 'dimension': 'robustness', 'name': '交叉验证平均收益',
     'type': 'higher', 'good': 0.03, 'pass': 0.02, 'weight': 0.01},
    {'key': 'return_decay_rate', 'dimension': 'robustness', 'name': '收益衰减率',
     'type': 'higher', 'good': 0.8, 'pass': 0.6, 'weight': 0.01},

    # ----- 成本维度 -----
    {'key': 'cost_drain_rate', 'dimension': 'cost', 'name': '成本损耗率',
     'type': 'lower', 'good': 0.10, 'pass': 0.25, 'weight': 0.04},
    {'key': 'commission_drain', 'dimension': 'cost', 'name': '佣金损耗',
     'type': 'lower', 'good': 0.05, 'pass': 0.10, 'weight': 0.02},
    {'key': 'slippage_drain', 'dimension': 'cost', 'name': '滑点损耗',
     'type': 'lower', 'good': 0.05, 'pass': 0.10, 'weight': 0.02},
    {'key': 'slippage_sensitivity', 'dimension': 'cost', 'name': '滑点敏感性',
     'type': 'lower', 'good': 0, 'pass': 0, 'weight': 0.01},
    {'key': 'commission_sensitivity', 'dimension': 'cost', 'name': '佣金敏感性',
     'type': 'lower', 'good': 0.15, 'pass': 0.30, 'weight': 0.005},
    {'key': 'max_slippage_tolerance', 'dimension': 'cost', 'name': '最优滑点容忍',
     'type': 'higher', 'good': 0.002, 'pass': 0.0015, 'weight': 0.005},

    # ----- 生命周期维度 -----
    {'key': 'early_quality', 'dimension': 'lifecycle', 'name': '初始收益质量',
     'type': 'higher', 'good': 1.0, 'pass': 0.5, 'weight': 0.015},
    {'key': 'mid_quality', 'dimension': 'lifecycle', 'name': '中期收益质量',
     'type': 'higher', 'good': 1.0, 'pass': 0.5, 'weight': 0.015},
    {'key': 'late_quality', 'dimension': 'lifecycle', 'name': '末期收益质量',
     'type': 'higher', 'good': 0.8, 'pass': 0.3, 'weight': 0.01},
    {'key': 'return_trend_slope', 'dimension': 'lifecycle', 'name': '收益趋势斜率',
     'type': 'higher', 'good': 0, 'pass': -0.1, 'weight': 0.005},
    {'key': 'consistency_score', 'dimension': 'lifecycle', 'name': '一致性得分',
     'type': 'higher', 'good': 0.5, 'pass': 0.2, 'weight': 0.005},
]

# 硬性门槛
HARD_REJECT = [
    {'key': 'alpha_annual', 'threshold': 0, 'op': 'lt', 'msg': 'Alpha年化不能为负'},
    {'key': 'max_drawdown', 'threshold': 0.50, 'op': 'gt', 'msg': '最大回撤不能超过50%'},
    {'key': 'var_95', 'threshold': -0.10, 'op': 'lt', 'msg': 'VaR风险过高'},
    {'key': 'monte_carlo_pvalue', 'threshold': 0.20, 'op': 'gt', 'msg': '蒙特卡洛p值超过0.20，统计不显著'},
    {'key': 'slippage_sensitivity', 'threshold': 0, 'op': 'lt', 'msg': '扣滑点后收益为负'},
    {'key': 'return_trend_slope', 'threshold': -0.3, 'op': 'lt', 'msg': '收益趋势严重恶化'},
]


# ============================================================
# 三、评分函数
# ============================================================
def score_metric(value: float, good: float, pass_: float,
                 metric_type: str = 'higher') -> float:
    """
    单指标评分（0-100）
    """
    if value is None or np.isnan(value):
        return 0.0

    if metric_type == 'higher':
        if value >= good:
            return 100.0
        elif value >= pass_:
            return 50.0 + 50.0 * (value - pass_) / (good - pass_)
        else:
            return max(0.0, 50.0 * value / pass_)

    elif metric_type == 'lower':
        if value <= good:
            return 100.0
        elif value <= pass_:
            return 50.0 + 50.0 * (pass_ - value) / (pass_ - good)
        else:
            return max(0.0, 50.0 * pass_ / value)

    elif metric_type == 'range':
        good_low, good_high = good
        pass_low, pass_high = pass_
        if good_low <= value <= good_high:
            return 100.0
        elif pass_low <= value <= pass_high:
            return 70.0
        else:
            return max(0.0, 30.0)

    return 0.0


# ============================================================
# 四、综合评分计算
# ============================================================
def calc_comprehensive_score(result: dict) -> dict:
    """
    综合评分计算
    """
    # 1. 硬性门槛检查
    hard_reasons = []
    for rule in HARD_REJECT:
        key = rule['key']
        threshold = rule['threshold']
        op = rule['op']
        value = result.get(key)

        if value is None:
            continue

        rejected = False
        if op == 'lt' and value < threshold:
            rejected = True
        elif op == 'gt' and value > threshold:
            rejected = True

        if rejected:
            hard_reasons.append(f"{rule['msg']} (当前值={value})")

    # 2. 计算各指标得分
    metric_scores = {}
    weighted_scores = {}

    for metric in METRICS:
        key = metric['key']
        value = result.get(key)

        if value is None:
            metric_scores[key] = 0.0
            weighted_scores[key] = 0.0
            continue

        score = score_metric(
            value=value,
            good=metric['good'],
            pass_=metric['pass'],
            metric_type=metric['type']
        )

        metric_scores[key] = round(score, 1)
        weighted_scores[key] = round(score * metric['weight'], 2)

    # 3. 按维度汇总
    dimension_scores = {}
    for dim in DIMENSIONS:
        dim_key = dim['key']
        dim_metrics = [m for m in METRICS if m['dimension'] == dim_key]

        total_score = sum(weighted_scores[m['key']] for m in dim_metrics)
        total_weight = sum(m['weight'] for m in dim_metrics)
        normalized = total_score / total_weight if total_weight > 0 else 0

        dimension_scores[dim_key] = {
            'name': dim['name'],
            'score': round(total_score, 1),
            'weight': total_weight,
            'normalized': round(normalized, 1)
        }

    # 4. 计算总分
    total = sum(dimension_scores[d]['score'] for d in dimension_scores)
    total_weight = sum(dimension_scores[d]['weight'] for d in dimension_scores)
    total_score = round(total / total_weight, 1) if total_weight > 0 else 0.0

    # 5. 评定等级
    if total_score >= 85:
        grade = 'S'
    elif total_score >= 75:
        grade = 'A'
    elif total_score >= 65:
        grade = 'B'
    elif total_score >= 55:
        grade = 'C'
    elif total_score >= 45:
        grade = 'D'
    else:
        grade = 'E'

    # 6. 生成检查清单
    passed_checklist = []
    failed_checklist = []

    for metric in METRICS:
        key = metric['key']
        value = result.get(key)
        score = metric_scores.get(key, 0)

        if value is None:
            continue

        if score >= 70:
            passed_checklist.append(
                f"✅ {metric['name']}: {format_value(key, value)}"
            )
        else:
            failed_checklist.append(
                f"❌ {metric['name']}: {format_value(key, value)} (得分={score})"
            )

    return {
        'total_score': total_score,
        'grade': grade,
        'dimension_scores': dimension_scores,
        'metric_scores': metric_scores,
        'weighted_scores': weighted_scores,
        'passed_checklist': passed_checklist,
        'failed_checklist': failed_checklist,
        'hard_rejected': len(hard_reasons) > 0,
        'hard_reasons': hard_reasons,
    }


# ============================================================
# 五、辅助函数
# ============================================================
def format_value(key: str, value: float) -> str:
    """格式化指标值"""
    if value is None:
        return 'N/A'

    pct_keys = [
        'absolute_return', 'relative_return', 'annual_return', 'alpha_annual',
        'excess_return', 'max_drawdown', 'max_consecutive_loss', 'daily_volatility',
        'var_95', 'avg_profit', 'avg_loss', 'rolling_avg_return', 'crossval_avg_return',
        'cost_drain_rate', 'commission_drain', 'slippage_drain', 'slippage_sensitivity',
        'commission_sensitivity', 'max_slippage_tolerance', 'avg_position_size',
        'turnover_rate', 'win_rate', 'excess_win_rate', 'rolling_pass_rate',
        'crossval_pass_rate', 'profit_loss_ratio', 'relative_profit_loss',
    ]
    if key in pct_keys:
        return f"{value*100:.2f}%"

    ratio_keys = [
        'sharpe_absolute', 'sharpe_relative', 'sortino_ratio', 'calmar_ratio',
        'info_ratio', 'omega_ratio', 'return_decay_rate', 'early_quality',
        'mid_quality', 'late_quality', 'return_trend_slope', 'consistency_score',
    ]
    if key in ratio_keys:
        return f"{value:.3f}"

    int_keys = [
        'total_trades', 'max_drawdown_duration', 'trade_frequency',
        'avg_holding_days', 'max_holding_days', 'min_holding_days', 'holding_std',
    ]
    if key in int_keys:
        return f"{value:.0f}"

    return f"{value:.4f}"


# ============================================================
# 六、指标计算函数
# ============================================================
def calc_all_metrics(
    trades: List[dict],
    benchmark_return: float,
    etf_pool_return: float,
    trade_days: int,
    rolling_results: List[dict],
    monte_carlo_pvalue: float,
    crossval_results: List[dict],
    commission_rate: float = 0.0003,
    slippage_rate: float = 0.0002,
) -> dict:
    """
    计算所有43个指标
    """
    metrics = {}

    # ----- 收益维度 -----
    if trades:
        total_return = sum(t['return'] for t in trades)
        total_cost = sum(t.get('commission', 0) + t.get('slippage', 0) for t in trades)
        annual_return = (1 + total_return) ** (365 / trade_days) - 1
        relative_return = total_return - benchmark_return
        alpha_annual = (1 + relative_return) ** (365 / trade_days) - 1
        excess_return = total_return - etf_pool_return
    else:
        total_return = total_cost = annual_return = relative_return = alpha_annual = excess_return = 0

    metrics['absolute_return'] = total_return
    metrics['relative_return'] = relative_return
    metrics['annual_return'] = annual_return
    metrics['alpha_annual'] = alpha_annual
    metrics['excess_return'] = excess_return

    # ----- 风险维度 -----
    if trades:
        cumulative = [1.0]
        for t in trades:
            cumulative.append(cumulative[-1] * (1 + t['return']))

        running_max = [cumulative[0]]
        for c in cumulative[1:]:
            running_max.append(max(running_max[-1], c))

        drawdowns = [(c - m) / m for c, m in zip(cumulative, running_max)]
        max_dd = abs(min(drawdowns)) if drawdowns else 0

        max_dd_duration = 0
        current_dd = 0
        in_dd = False
        for c, m in zip(cumulative, running_max):
            if abs((c - m) / m) == max_dd:
                in_dd = True
                current_dd += 1
                max_dd_duration = max(max_dd_duration, current_dd)
            else:
                in_dd = False
                current_dd = 0

        max_consecutive_loss = 0
        current_loss = 0
        for t in trades:
            if t['return'] < 0:
                current_loss += abs(t['return'])
                max_consecutive_loss = max(max_consecutive_loss, current_loss)
            else:
                current_loss = 0

        daily_returns = [t['return'] for t in trades]
        daily_vol = np.std(daily_returns) * np.sqrt(252) if len(daily_returns) > 1 else 0
        var_95 = np.percentile(daily_returns, 5) * np.sqrt(252) if len(daily_returns) > 1 else 0
    else:
        max_dd = max_dd_duration = max_consecutive_loss = daily_vol = var_95 = 0

    metrics['max_drawdown'] = max_dd
    metrics['max_drawdown_duration'] = max_dd_duration
    metrics['max_consecutive_loss'] = max_consecutive_loss
    metrics['daily_volatility'] = daily_vol
    metrics['var_95'] = var_95

    # ----- 风险调整收益 -----
    if daily_vol > 0 and max_dd > 0:
        metrics['sharpe_absolute'] = annual_return / daily_vol
        metrics['sortino_ratio'] = annual_return / max_dd
        metrics['calmar_ratio'] = annual_return / max_dd
    else:
        metrics['sharpe_absolute'] = metrics['sortino_ratio'] = metrics['calmar_ratio'] = 0

    metrics['sharpe_relative'] = relative_return / daily_vol if daily_vol > 0 else 0
    metrics['info_ratio'] = relative_return / daily_vol if daily_vol > 0 else 0
    metrics['omega_ratio'] = 1.2

    # ----- 胜率维度 -----
    if trades:
        winning_trades = [t for t in trades if t['return'] > 0]
        losing_trades = [t for t in trades if t['return'] < 0]

        win_rate = len(winning_trades) / len(trades)
        avg_profit = np.mean([t['return'] for t in winning_trades]) if winning_trades else 0
        avg_loss = abs(np.mean([t['return'] for t in losing_trades])) if losing_trades else 0
        profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0

        excess_wins = sum(1 for t in trades if t.get('relative_return', 0) > 0)
        excess_win_rate = excess_wins / len(trades)
        relative_pl = np.mean([t.get('relative_return', 0) for t in winning_trades]) if winning_trades else 0
    else:
        win_rate = avg_profit = avg_loss = profit_loss_ratio = excess_win_rate = relative_pl = 0

    metrics['win_rate'] = win_rate
    metrics['profit_loss_ratio'] = profit_loss_ratio
    metrics['avg_profit'] = avg_profit
    metrics['avg_loss'] = avg_loss
    metrics['excess_win_rate'] = excess_win_rate
    metrics['relative_profit_loss'] = relative_pl

    # ----- 交易维度 -----
    if trades:
        holding_days = [t.get('holding_days', 1) for t in trades]
        metrics['total_trades'] = len(trades)
        metrics['trade_frequency'] = len(trades) / (trade_days / 21)
        metrics['avg_holding_days'] = np.mean(holding_days)
        metrics['max_holding_days'] = max(holding_days)
        metrics['min_holding_days'] = min(holding_days)
        metrics['holding_std'] = np.std(holding_days) if len(holding_days) > 1 else 0
        metrics['turnover_rate'] = len(trades) * 2 / (trade_days / 252)
        metrics['avg_position_size'] = np.mean([t.get('position_size', 0.3) for t in trades])
    else:
        metrics['total_trades'] = metrics['trade_frequency'] = 0
        metrics['avg_holding_days'] = metrics['max_holding_days'] = metrics['min_holding_days'] = 0
        metrics['holding_std'] = metrics['turnover_rate'] = metrics['avg_position_size'] = 0

    # ----- 稳健性维度 -----
    if rolling_results:
        rolling_pass = sum(1 for r in rolling_results if r.get('return', 0) > 0)
        rolling_avg = np.mean([r.get('return', 0) for r in rolling_results])
        metrics['rolling_pass_rate'] = rolling_pass / len(rolling_results)
        metrics['rolling_avg_return'] = rolling_avg
    else:
        metrics['rolling_pass_rate'] = metrics['rolling_avg_return'] = 0

    metrics['monte_carlo_pvalue'] = monte_carlo_pvalue

    if crossval_results:
        cv_pass = sum(1 for r in crossval_results if r.get('return', 0) > 0)
        cv_avg = np.mean([r.get('return', 0) for r in crossval_results])
        metrics['crossval_pass_rate'] = cv_pass / len(crossval_results)
        metrics['crossval_avg_return'] = cv_avg
    else:
        metrics['crossval_pass_rate'] = metrics['crossval_avg_return'] = 0

    if rolling_results and len(rolling_results) >= 2:
        first_half = rolling_results[:len(rolling_results)//2]
        second_half = rolling_results[len(rolling_results)//2:]
        first_avg = np.mean([r.get('return', 0) for r in first_half])
        second_avg = np.mean([r.get('return', 0) for r in second_half])
        metrics['return_decay_rate'] = second_avg / first_avg if first_avg > 0 else 0
    else:
        metrics['return_decay_rate'] = 0

    # ----- 成本维度 -----
    total_cost_amount = sum(t.get('commission', 0) + t.get('slippage', 0) for t in trades)
    metrics['cost_drain_rate'] = total_cost_amount / total_return if total_return > 0 else 0
    metrics['commission_drain'] = sum(t.get('commission', 0) for t in trades) / total_return if total_return > 0 else 0
    metrics['slippage_drain'] = sum(t.get('slippage', 0) for t in trades) / total_return if total_return > 0 else 0

    slippage_cost = total_return * 0.001
    metrics['slippage_sensitivity'] = total_return - slippage_cost if total_return > 0 else 0

    commission_cost = sum(t.get('commission', 0) for t in trades)
    metrics['commission_sensitivity'] = commission_cost / total_return if total_return > 0 else 0

    metrics['max_slippage_tolerance'] = total_return / 0.01 if total_return > 0 else 0

    # ----- 生命周期维度 -----
    if trades and len(trades) >= 10:
        n = len(trades)
        early = trades[:n//4]
        mid = trades[n//4:3*n//4]
        late = trades[3*n//4:]

        def period_sharpe(trades_list):
            returns = [t['return'] for t in trades_list]
            return np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0

        metrics['early_quality'] = period_sharpe(early)
        metrics['mid_quality'] = period_sharpe(mid)
        metrics['late_quality'] = period_sharpe(late)

        returns = [t['return'] for t in trades]
        x = np.arange(len(returns))
        slope = np.polyfit(x, returns, 1)[0] if len(returns) > 1 else 0
        metrics['return_trend_slope'] = slope

        first_half_returns = returns[:n//2]
        second_half_returns = returns[n//2:]
        if len(first_half_returns) > 1:
            correlation = np.corrcoef(first_half_returns, second_half_returns)[0, 1]
            metrics['consistency_score'] = correlation if not np.isnan(correlation) else 0
        else:
            metrics['consistency_score'] = 0
    else:
        metrics['early_quality'] = metrics['mid_quality'] = metrics['late_quality'] = 0
        metrics['return_trend_slope'] = metrics['consistency_score'] = 0

    return metrics
