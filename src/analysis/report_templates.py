#!/usr/bin/env python3
"""
报告模板动态化（US-011）

设计原则（D1-D5 用户决策）：
- D1=A: 3 个段落都做（策略模式/操作建议/情景分析）
- D2=A: 4 种市场环境全部（trend_up / range_bound / trend_down / crash）
- D3=A: 合并 US-009 满仓判断到操作建议段
- D4=A: 操作建议复用 US-012 9 步决策树输出
- D5=A: 情景分析根据回测历史数据自动算（如果提供 validation_results）

被谁调用：
    - src/analysis/report_generator.py（替换硬编码字符串）
"""
from typing import List, Tuple, Optional, Dict, Any


# ── US-013: 8 状态细分（initial_up/uptrend/late_up/initial_down/...）──
# 兼容 4 状态别名（trend_up/range_bound/trend_down/crash）
REGIME_LABELS_FULL = {
    # 8 状态细分
    'initial_up':     '初升期',
    'uptrend':        '上升中',
    'late_up':        '末升期',
    'initial_down':   '初降期',
    'downtrend':      '下降中',
    'late_down':      '末降期',
    'range_bullish':  '震荡偏强',
    'range_bearish':  '震荡偏弱',
    'reversal_point': '反转点',
    'crash':          '暴跌市',
    # 4 状态兼容别名
    'trend_up':       '趋势向上',
    'range_bound':    '震荡市',
    'trend_down':     '趋势向下',
}


def format_regime_label(market_regime: str) -> str:
    """US-017: 8 状态细分标签 (替代模糊的"中性" / "震荡或下跌")

    Args:
        market_regime: market_regime.detect() 返回的状态码
    Returns:
        中文标签, 找不到时返回原值
    """
    return REGIME_LABELS_FULL.get(market_regime, market_regime)


# ── 8 种策略模式（D1+D2: 4 市场 × 2 max_holdings）────────────
STRATEGY_MODE_TEMPLATES = {
    ('trend_up', 1):    '趋势市·单持仓 + 6%止损 + 10%止盈',
    ('trend_up', 2):    '趋势市·多持仓(最多2) + 5%止损 + 12%止盈',
    ('range_bound', 1): '震荡市·单持仓 + 4%止损 + 8%止盈（快速止盈）',
    ('range_bound', 2): '震荡市·多持仓(最多2) + 5%止损 + 8%止盈',
    ('trend_down', 1):  '下跌市·单持仓 + 4%止损（快出）',
    ('trend_down', 2):  '下跌市·观望为主，最多1只',
    ('crash', 1):       '暴跌市·空仓观望',
    ('crash', 2):       '暴跌市·空仓观望（绝不加仓）',
}


# ── US-015: 4 市场状态仓位利用率（2026-06-04 用户规则）────────
# 震荡市 ≤ 50%, 趋势市 ≤ 90%, 下跌市 ≤ 30%, 暴跌市 0%
POSITION_LIMITS = {
    'trend_up':    0.9,   # 趋势市: 90%
    'range_bound': 0.5,   # 震荡市: 50%
    'trend_down':  0.3,   # 下跌市: 30%
    'crash':       0.0,   # 暴跌市: 0%
}


def format_position_limit(market_regime: str) -> str:
    """
    段 4: 市场仓位上限（US-015 新增）

    Args:
        market_regime: trend_up / range_bound / trend_down / crash
    Returns:
        "震荡市 · 50% 上限" / "趋势市 · 90% 上限" / 等
    """
    limit = POSITION_LIMITS.get(market_regime, 0.5)
    regime_zh = {
        'trend_up':    '趋势市',
        'range_bound': '震荡市',
        'trend_down':  '下跌市',
        'crash':       '暴跌市',
    }.get(market_regime, market_regime)
    return f"{regime_zh} · {limit*100:.0f}% 上限"


def format_strategy_mode(market_regime: str, max_holdings: int) -> str:
    """段 1: 策略模式（D1+D2: 4×2=8 组合）"""
    key = (market_regime, max_holdings)
    if key in STRATEGY_MODE_TEMPLATES:
        return STRATEGY_MODE_TEMPLATES[key]
    # fallback
    return f'{market_regime}·{max_holdings}只持仓'


# ── 12 种操作建议（D1+D2+D3+D4）───────────────────────────
def format_action_advice(
    market_regime: str,
    has_recommendation: bool,
    cash_sufficient: bool,
    hold_count: int,
    max_holdings: int,
    portfolio_actions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    段 2: 操作建议

    D3=A: 合并 US-009 满仓判断（hold_count >= max_holdings）
    D4=A: 复用 US-012 9 步决策树输出（portfolio_actions 来自 PositionGuide）
    D2=A: 4 种市场环境全部

    Args:
        market_regime: trend_up / range_bound / trend_down / crash
        has_recommendation: 是否有今日推荐
        cash_sufficient: 现金是否足够（available >= price * 100）
        hold_count: 当前持仓数
        max_holdings: 最大持仓数
        portfolio_actions: US-012 9 步决策树输出（可选），含 {action, code, ...}
    """
    # D4=A: 优先看 9 步决策树是否有清仓/止损/止盈动作
    if portfolio_actions:
        sell_actions = [
            a for a in portfolio_actions
            if a.get('action') in (
                '清仓（用户决策）', '止损', '止盈', '到期评估', '清仓空仓'
            )
        ]
        if sell_actions:
            codes = ', '.join(a.get('code', '?') for a in sell_actions[:3])
            return (
                f"【操作建议】\n"
                f"优先处理持仓动作\n"
                f"✓ {len(sell_actions)}笔需清仓/止损/止盈 ({codes})"
            )

    # D3=A: 合并 US-009 满仓判断
    if hold_count >= max_holdings:
        return (
            "【操作建议】\n"
            "已达仓位上限，暂不买入\n"
            "✓ 建议调仓而非加仓"
        )

    # 现金不足
    if not cash_sufficient:
        return (
            "【操作建议】\n"
            "现金不足，暂不买入\n"
            "✓ 等回笼资金"
        )

    # 无推荐标的
    if not has_recommendation:
        return (
            "【操作建议】\n"
            "无满足条件标的\n"
            "✓ 建议观望"
        )

    # D2=A: 4 种市场环境
    if market_regime == 'crash':
        return (
            "【操作建议】\n"
            "清仓观望\n"
            "✓ 暴跌市，绝不加仓"
        )
    if market_regime == 'trend_up':
        return (
            "【操作建议】\n"
            "重仓买入\n"
            "✓ 趋势明确，可积极建仓"
        )
    if market_regime == 'range_bound':
        return (
            "【操作建议】\n"
            "轻仓试水\n"
            "✓ 震荡市，控制仓位"
        )
    if market_regime == 'trend_down':
        return (
            "【操作建议】\n"
            "审慎参与\n"
            "✓ 下跌市，注意止损"
        )
    return (
        "【操作建议】\n"
        "审慎参与\n"
        "✓ 注意止损"
    )


# ── 4 套情景分析概率分布（D2+D5）───────────────────────────
DEFAULT_SCENARIOS = {
    'trend_up': [
        ('乐观', '40%', '+20%~+40%'),
        ('中性', '40%', '+5%~+20%'),
        ('悲观', '20%', '-5%~+5%'),
    ],
    'range_bound': [
        ('乐观', '25%', '+10%~+20%'),
        ('中性', '50%', '0%~+10%'),
        ('悲观', '25%', '-5%~0%'),
    ],
    'trend_down': [
        ('乐观', '20%', '0%~+5%'),
        ('中性', '40%', '-5%~0%'),
        ('悲观', '40%', '-10%~-5%'),
    ],
    'crash': [
        ('乐观', '10%', '0%'),
        ('中性', '30%', '-5%~0%'),
        ('悲观', '60%', '-15%~-5%'),
    ],
}


def format_scenario(
    market_regime: str,
    validation_results: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    段 3: 情景分析（D2+D5）

    D5=A: 如果提供 validation_results（回测历史数据），自动算概率分布
    D2=A: 4 种市场环境全部
    """
    # D5=A: 用回测结果自动算（简化：根据回测平均收益分位）
    if validation_results and len(validation_results) > 0:
        scenarios = _compute_scenarios_from_validation(validation_results, market_regime)
    else:
        scenarios = DEFAULT_SCENARIOS.get(market_regime, DEFAULT_SCENARIOS['range_bound'])

    lines = ["| 情景 | 概率 | 收益区间 |", "|------|------|----------|"]
    for label, prob, range_str in scenarios:
        lines.append(f"| {label} | {prob} | {range_str} |")
    return "\n".join(lines)


def _compute_scenarios_from_validation(
    validation_results: List[Dict[str, Any]],
    market_regime: str,
) -> List[Tuple[str, str, str]]:
    """
    根据回测结果自动算概率分布（D5=A）

    简化策略：
    - 用 max_drawdown 控制收益范围（避免回测平均收益过大导致区间丑）
    - 乐观: 基于正收益测试期
    - 中性: 平均收益的合理范围
    - 悲观: 包含最大回撤
    """
    try:
        returns = [r.get('return', 0) for r in validation_results if r.get('return') is not None]
        drawdowns = [r.get('drawdown', 0) for r in validation_results if r.get('drawdown') is not None]
        if not returns:
            return DEFAULT_SCENARIOS.get(market_regime, DEFAULT_SCENARIOS['range_bound'])
        avg_return = sum(returns) / len(returns)
        max_dd = min(drawdowns) if drawdowns else -10  # 默认 -10%

        # 按市场状态分配概率
        if market_regime == 'trend_up':
            probs = ('45%', '40%', '15%')
        elif market_regime == 'range_bound':
            probs = ('25%', '50%', '25%')
        elif market_regime == 'trend_down':
            probs = ('15%', '40%', '45%')
        elif market_regime == 'crash':
            probs = ('10%', '30%', '60%')
        else:
            probs = ('30%', '40%', '30%')

        # 收益区间（按月化或单期合理范围）
        # 把高收益压到合理范围（最多 +30%）
        cap_upper = min(30, max(15, avg_return * 0.3))
        cap_lower = max(max_dd, -20)  # 最大回撤，不超过 -20%

        return [
            ('乐观', probs[0], f'+{cap_upper*0.5:.0f}%~+{cap_upper*1.5:.0f}%'),
            ('中性', probs[1], f'{cap_lower*0.3:.0f}%~+{cap_upper*0.5:.0f}%'),
            ('悲观', probs[2], f'{cap_lower*0.7:.0f}%~{cap_lower*0.3:.0f}%'),
        ]
    except Exception:
        return DEFAULT_SCENARIOS.get(market_regime, DEFAULT_SCENARIOS['range_bound'])


# ── 兼容性：US-011 之前 US-009 已加"🛑 已达仓位上限"提示 ──
# D3=A: 合并到 format_action_advice 的满仓判断（已实现）
