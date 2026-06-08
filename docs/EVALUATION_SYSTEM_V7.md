```yaml
---
file: EVALUATION_SYSTEM_V7.md
purpose: ETF量化策略评价体系（v7版本：IC/IR/盈利期望/最大回撤/夏普）
used_by:
  - 回测引擎
  - 实验验证
status: active
last_review: 2026-06-08
review_interval: weekly
---
```

# ETF量化策略完整评价体系 v7.0

_版本: 7.0_
_创建时间: 2026-05-31_
_用途: 策略筛选的唯一标准，所有模型必须通过全部指标验证_

---

## 一、评价维度总览（8大类，43个指标）

| 维度 | 指标数 | 权重 | 说明 |
|------|--------|------|------|
| 收益维度 | 5 | 20% | 核心：能赚钱 |
| 风险维度 | 5 | 20% | 核心：控风险 |
| 风险调整收益 | 6 | 15% | 核心：风险调整后收益 |
| 胜率维度 | 6 | 10% | 重要：交易质量 |
| 交易维度 | 8 | 5% | 重要：交易效率 |
| 稳健性维度 | 6 | 15% | 核心：时序稳健 |
| 成本维度 | 6 | 10% | 重要：成本可控 |
| 生命周期 | 5 | 5% | 重要：长期有效 |

---

## 二、指标详细定义

### 2.1 收益维度（5个，权重20%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 1 | absolute_return | 绝对总收益 | (期末净值/期初净值) - 1 | higher | 50% | 30% | 5% |
| 2 | relative_return | 相对总收益 | 绝对收益 - 大盘收益 | higher | 15% | 5% | 5% |
| 3 | annual_return | 年化收益 | (1+绝对收益)^(365/天数) - 1 | higher | 25% | 15% | 4% |
| 4 | alpha_annual | Alpha年化 | (1+相对收益)^(365/天数) - 1 | higher | 10% | 5% | 4% |
| 5 | excess_return | 超额收益 | 策略收益 - ETF池收益 | higher | 5% | 2% | 2% |

### 2.2 风险维度（5个，权重20%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 6 | max_drawdown | 最大回撤 | max(回撤幅度序列) | lower | 15% | 30% | 8% |
| 7 | max_drawdown_duration | 最大回撤持续天数 | 连续处于最大回撤的天数 | lower | 15 | 30 | 3% |
| 8 | max_consecutive_loss | 最大连续亏损 | 连续亏损次数 × 平均亏损额 | lower | 8% | 15% | 3% |
| 9 | daily_volatility | 日波动率 | std(日收益序列) × sqrt(252) | lower | 1.5% | 2.5% | 3% |
| 10 | var_95 | VaR(95%) | 5%分位点日收益 × sqrt(252) | lower | -2% | -5% | 3% |

### 2.3 风险调整收益（6个，权重15%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 11 | sharpe_absolute | 夏普比率（绝对） | 年化收益 / 年化波动率 | higher | 2.0 | 1.0 | 4% |
| 12 | sharpe_relative | 夏普比率（相对） | Alpha年化 / 跟踪误差年化 | higher | 1.5 | 0.5 | 3% |
| 13 | sortino_ratio | 索提诺比率 | 年化收益 / 下行波动率 | higher | 2.5 | 1.2 | 2% |
| 14 | calmar_ratio | 卡尔玛比率 | 年化收益 / 最大回撤 | higher | 2.0 | 1.0 | 2% |
| 15 | info_ratio | 信息比率IR | Alpha年化 / 跟踪误差 | higher | 1.0 | 0.5 | 2% |
| 16 | omega_ratio | Omega比率 | 收益期望 / 亏损期望 | higher | 1.5 | 1.2 | 2% |

### 2.4 胜率维度（6个，权重10%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 17 | win_rate | 胜率 | 盈利笔数 / 总笔数 | higher | 55% | 50% | 3% |
| 18 | profit_loss_ratio | 盈亏比 | 平均盈利额 / 平均亏损额 | higher | 1.5 | 1.0 | 2% |
| 19 | avg_profit | 平均盈利额 | 盈利交易收益均值 | higher | 1.2% | 0.8% | 1% |
| 20 | avg_loss | 平均亏损额 | 亏损交易收益均值（绝对值） | lower | 1.0% | 1.5% | 1% |
| 21 | excess_win_rate | 超额胜率 | 跑赢大盘笔数 / 总笔数 | higher | 55% | 50% | 2% |
| 22 | relative_profit_loss | 相对盈亏比 | 相对收益盈亏比 | higher | 1.0 | 0.8 | 1% |

### 2.5 交易维度（8个，权重5%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 23 | total_trades | 总交易笔数 | 完整交易次数 | range | 500 | [100, 2000] | 0.5% |
| 24 | trade_frequency | 交易频率 | 月均交易次数 | lower | 3 | 5 | 0.5% |
| 25 | avg_holding_days | 平均持仓天数 | 持仓天数均值 | range | 10 | [5, 15] | 1% |
| 26 | max_holding_days | 最大持仓天数 | 单笔最长持仓 | lower | 15 | 20 | 0.5% |
| 27 | min_holding_days | 最小持仓天数 | 单笔最短持仓 | higher | 3 | 3 | 0.5% |
| 28 | holding_std | 持仓天数标准差 | 持仓天数std | lower | 5 | 8 | 0.5% |
| 29 | turnover_rate | 换手率 | 年均换手比例 | lower | 300% | 500% | 0.5% |
| 30 | avg_position_size | 平均持仓规模 | 平均持仓市值/总资金 | range | 30% | [15%, 50%] | 1% |

### 2.6 稳健性维度（6个，权重15%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 31 | rolling_pass_rate | 滚动窗口通过率 | 正收益窗口数/总窗口数 | higher | 70% | 60% | 4% |
| 32 | rolling_avg_return | 滚动窗口平均收益 | 各窗口相对收益均值 | higher | 3% | 2% | 3% |
| 33 | monte_carlo_pvalue | 蒙特卡洛p值 | 模拟检验p值 | lower | 0.03 | 0.10 | 3% |
| 34 | crossval_pass_rate | 交叉验证通过率 | CV正收益窗口比例 | higher | 70% | 60% | 3% |
| 35 | crossval_avg_return | 交叉验证平均收益 | CV各窗口收益均值 | higher | 3% | 2% | 1% |
| 36 | return_decay_rate | 收益衰减率 | 新窗口收益/旧窗口收益 | higher | 0.8 | 0.6 | 1% |

### 2.7 成本维度（6个，权重10%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 37 | cost_drain_rate | 成本损耗率 | 总成本 / 总收益 | lower | 10% | 25% | 4% |
| 38 | commission_drain | 佣金损耗 | 佣金总额 / 总收益 | lower | 5% | 10% | 2% |
| 39 | slippage_drain | 滑点损耗 | 滑点总额 / 总收益 | lower | 5% | 10% | 2% |
| 40 | slippage_sensitivity | 滑点敏感性 | 扣0.1%滑点后收益变化 | lower | 0% | 0% | 1% |
| 41 | commission_sensitivity | 佣金敏感性 | 扣佣金后收益衰减 | lower | 15% | 30% | 0.5% |
| 42 | max_slippage_tolerance | 最优滑点容忍 | 收益仍为正的滑点上限 | higher | 0.20% | 0.15% | 0.5% |

### 2.8 生命周期维度（5个，权重5%）

| # | 指标Key | 显示名 | 计算公式 | 类型 | 优秀值 | 及格值 | 权重 |
|---|---------|--------|----------|------|--------|--------|------|
| 43 | early_quality | 初始收益质量 | 前1/4周期夏普比率 | higher | 1.0 | 0.5 | 1.5% |
| 44 | mid_quality | 中期收益质量 | 中间1/2周期夏普比率 | higher | 1.0 | 0.5 | 1.5% |
| 45 | late_quality | 末期收益质量 | 后1/4周期夏普比率 | higher | 0.8 | 0.3 | 1% |
| 46 | return_trend_slope | 收益趋势斜率 | 收益-时间回归斜率 | higher | 0 | -0.1 | 0.5% |
| 47 | consistency_score | 一致性得分 | 前后半段收益相关性 | higher | 0.5 | 0.2 | 0.5% |

---

## 三、不通过判定规则（硬性门槛）

**任意一项不通过，直接淘汰：**

| 维度 | 指标Key | 硬性门槛 | 说明 |
|------|---------|----------|------|
| 收益 | alpha_annual | <0% | 不能跑输大盘 |
| 风险 | max_drawdown | >50% | 回撤太大无法承受 |
| 风险 | var_95 | <-10% | 日风险过高 |
| 稳健 | monte_carlo_pvalue | >0.20 | 统计不显著 |
| 成本 | slippage_sensitivity | 扣滑点后收益<0 | 交易成本吃掉所有利润 |
| 生命 | return_trend_slope | < -0.3 | 收益趋势严重恶化 |

---

## 四、综合评分方法

### 4.1 评分函数

```python
def score_metric(value: float, good: float, pass_: float, 
                 metric_type: str = 'higher_better') -> float:
    """
    单指标评分（0-100）
    
    Args:
        value: 实际值
        good: 优秀阈值
        pass_: 及格阈值
        metric_type: 
            - 'higher_better': 越高越好
            - 'lower_better': 越低越好
            - 'range': 在区间内越好
    """
    if metric_type == 'higher_better':
        if value >= good:
            return 100.0
        elif value >= pass_:
            return 50.0 + 50.0 * (value - pass_) / (good - pass_)
        else:
            return max(0.0, 50.0 * value / pass_)
    
    elif metric_type == 'lower_better':
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
```

### 4.2 综合评分计算

```python
def calc_comprehensive_score(result: dict) -> dict:
    """综合评分计算"""
    
    scores = {}
    weighted_scores = {}
    
    for metric in METRICS:
        key = metric['key']
        value = result.get(key)
        
        if value is None:
            scores[key] = 0
            weighted_scores[key] = 0
            continue
        
        score = score_metric(
            value=value,
            good=metric['good'],
            pass_=metric['pass'],
            metric_type=metric['type']
        )
        
        scores[key] = round(score, 1)
        weighted_scores[key] = round(score * metric['weight'], 2)
    
    # 按维度汇总
    dimension_scores = {}
    for dim in DIMENSIONS:
        dim_key = dim['key']
        dim_metrics = [m for m in METRICS if m['dimension'] == dim_key]
        
        total_score = sum(weighted_scores[m['key']] for m in dim_metrics)
        total_weight = sum(m['weight'] for m in dim_metrics)
        normalized = total_score / total_weight if total_weight > 0 else 0
        
        dimension_scores[dim_key] = {
            'score': round(total_score, 1),
            'weight': total_weight,
            'normalized': round(normalized, 1)
        }
    
    total = sum(dimension_scores[d]['score'] for d in dimension_scores)
    total_weight = sum(dimension_scores[d]['weight'] for d in dimension_scores)
    
    return {
        'total_score': round(total / total_weight, 1),
        'dimension_scores': dimension_scores,
        'metric_scores': scores,
        'weighted_scores': weighted_scores
    }
```

---

## 五、等级评定

| 等级 | 分数 | 含义 | 行动建议 |
|------|------|------|----------|
| 🥇 S级 | 85-100 | 卓越 | 可直接实盘 |
| 🥈 A级 | 75-84 | 优秀 | 优化后实盘 |
| 🥉 B级 | 65-74 | 良好 | 小资金测试 |
| 📋 C级 | 55-64 | 及格 | 需大幅优化 |
| ⚠️ D级 | 45-54 | 勉强 | 参考，谨慎使用 |
| ❌ E级 | <45 | 不合格 | 放弃 |

---

## 六、维度权重汇总

```python
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
```

---

## 七、指标元数据

```python
METRICS = [
    # 收益维度
    {'key': 'absolute_return', 'dimension': 'returns', 'name': '绝对总收益', 'type': 'higher', 'good': 0.50, 'pass': 0.30, 'weight': 0.05},
    {'key': 'relative_return', 'dimension': 'returns', 'name': '相对总收益', 'type': 'higher', 'good': 0.15, 'pass': 0.05, 'weight': 0.05},
    {'key': 'annual_return', 'dimension': 'returns', 'name': '年化收益', 'type': 'higher', 'good': 0.25, 'pass': 0.15, 'weight': 0.04},
    {'key': 'alpha_annual', 'dimension': 'returns', 'name': 'Alpha年化', 'type': 'higher', 'good': 0.10, 'pass': 0.05, 'weight': 0.04},
    {'key': 'excess_return', 'dimension': 'returns', 'name': '超额收益', 'type': 'higher', 'good': 0.05, 'pass': 0.02, 'weight': 0.02},
    # 风险维度
    {'key': 'max_drawdown', 'dimension': 'risk', 'name': '最大回撤', 'type': 'lower', 'good': 0.15, 'pass': 0.30, 'weight': 0.08},
    {'key': 'max_drawdown_duration', 'dimension': 'risk', 'name': '最大回撤持续天数', 'type': 'lower', 'good': 15, 'pass': 30, 'weight': 0.03},
    {'key': 'max_consecutive_loss', 'dimension': 'risk', 'name': '最大连续亏损', 'type': 'lower', 'good': 0.08, 'pass': 0.15, 'weight': 0.03},
    {'key': 'daily_volatility', 'dimension': 'risk', 'name': '日波动率', 'type': 'lower', 'good': 0.015, 'pass': 0.025, 'weight': 0.03},
    {'key': 'var_95', 'dimension': 'risk', 'name': 'VaR(95%)', 'type': 'lower', 'good': -0.02, 'pass': -0.05, 'weight': 0.03},
    # 风险调整收益
    {'key': 'sharpe_absolute', 'dimension': 'risk_adjusted', 'name': '夏普比率（绝对）', 'type': 'higher', 'good': 2.0, 'pass': 1.0, 'weight': 0.04},
    {'key': 'sharpe_relative', 'dimension': 'risk_adjusted', 'name': '夏普比率（相对）', 'type': 'higher', 'good': 1.5, 'pass': 0.5, 'weight': 0.03},
    {'key': 'sortino_ratio', 'dimension': 'risk_adjusted', 'name': '索提诺比率', 'type': 'higher', 'good': 2.5, 'pass': 1.2, 'weight': 0.02},
    {'key': 'calmar_ratio', 'dimension': 'risk_adjusted', 'name': '卡尔玛比率', 'type': 'higher', 'good': 2.0, 'pass': 1.0, 'weight': 0.02},
    {'key': 'info_ratio', 'dimension': 'risk_adjusted', 'name': '信息比率IR', 'type': 'higher', 'good': 1.0, 'pass': 0.5, 'weight': 0.02},
    {'key': 'omega_ratio', 'dimension': 'risk_adjusted', 'name': 'Omega比率', 'type': 'higher', 'good': 1.5, 'pass': 1.2, 'weight': 0.02},
    # 胜率维度
    {'key': 'win_rate', 'dimension': 'win_rate', 'name': '胜率', 'type': 'higher', 'good': 0.55, 'pass': 0.50, 'weight': 0.03},
    {'key': 'profit_loss_ratio', 'dimension': 'win_rate', 'name': '盈亏比', 'type': 'higher', 'good': 1.5, 'pass': 1.0, 'weight': 0.02},
    {'key': 'avg_profit', 'dimension': 'win_rate', 'name': '平均盈利额', 'type': 'higher', 'good': 0.012, 'pass': 0.008, 'weight': 0.01},
    {'key': 'avg_loss', 'dimension': 'win_rate', 'name': '平均亏损额', 'type': 'lower', 'good': 0.01, 'pass': 0.015, 'weight': 0.01},
    {'key': 'excess_win_rate', 'dimension': 'win_rate', 'name': '超额胜率', 'type': 'higher', 'good': 0.55, 'pass': 0.50, 'weight': 0.02},
    {'key': 'relative_profit_loss', 'dimension': 'win_rate', 'name': '相对盈亏比', 'type': 'higher', 'good': 1.0, 'pass': 0.8, 'weight': 0.01},
    # 交易维度
    {'key': 'total_trades', 'dimension': 'trading', 'name': '总交易笔数', 'type': 'range', 'good': 500, 'pass': [100, 2000], 'weight': 0.005},
    {'key': 'trade_frequency', 'dimension': 'trading', 'name': '交易频率', 'type': 'lower', 'good': 3, 'pass': 5, 'weight': 0.005},
    {'key': 'avg_holding_days', 'dimension': 'trading', 'name': '平均持仓天数', 'type': 'range', 'good': 10, 'pass': [5, 15], 'weight': 0.01},
    {'key': 'max_holding_days', 'dimension': 'trading', 'name': '最大持仓天数', 'type': 'lower', 'good': 15, 'pass': 20, 'weight': 0.005},
    {'key': 'min_holding_days', 'dimension': 'trading', 'name': '最小持仓天数', 'type': 'higher', 'good': 3, 'pass': 3, 'weight': 0.005},
    {'key': 'holding_std', 'dimension': 'trading', 'name': '持仓天数标准差', 'type': 'lower', 'good': 5, 'pass': 8, 'weight': 0.005},
    {'key': 'turnover_rate', 'dimension': 'trading', 'name': '换手率', 'type': 'lower', 'good': 3.0, 'pass': 5.0, 'weight': 0.005},
    {'key': 'avg_position_size', 'dimension': 'trading', 'name': '平均持仓规模', 'type': 'range', 'good': 0.30, 'pass': [0.15, 0.50], 'weight': 0.01},
    # 稳健性维度
    {'key': 'rolling_pass_rate', 'dimension': 'robustness', 'name': '滚动窗口通过率', 'type': 'higher', 'good': 0.70, 'pass': 0.60, 'weight': 0.04},
    {'key': 'rolling_avg_return', 'dimension': 'robustness', 'name': '滚动窗口平均收益', 'type': 'higher', 'good': 0.03, 'pass': 0.02, 'weight': 0.03},
    {'key': 'monte_carlo_pvalue', 'dimension': 'robustness', 'name': '蒙特卡洛p值', 'type': 'lower', 'good': 0.03, 'pass': 0.10, 'weight': 0.03},
    {'key': 'crossval_pass_rate', 'dimension': 'robustness', 'name': '交叉验证通过率', 'type': 'higher', 'good': 0.70, 'pass': 0.60, 'weight': 0.03},
    {'key': 'crossval_avg_return', 'dimension': 'robustness', 'name': '交叉验证平均收益', 'type': 'higher', 'good': 0.03, 'pass': 0.02, 'weight': 0.01},
    {'key': 'return_decay_rate', 'dimension': 'robustness', 'name': '收益衰减率', 'type': 'higher', 'good': 0.8, 'pass': 0.6, 'weight': 0.01},
    # 成本维度
    {'key': 'cost_drain_rate', 'dimension': 'cost', 'name': '成本损耗率', 'type': 'lower', 'good': 0.10, 'pass': 0.25, 'weight': 0.04},
    {'key': 'commission_drain', 'dimension': 'cost', 'name': '佣金损耗', 'type': 'lower', 'good': 0.05, 'pass': 0.10, 'weight': 0.02},
    {'key': 'slippage_drain', 'dimension': 'cost', 'name': '滑点损耗', 'type': 'lower', 'good': 0.05, 'pass': 0.10, 'weight': 0.02},
    {'key': 'slippage_sensitivity', 'dimension': 'cost', 'name': '滑点敏感性', 'type': 'lower', 'good': 0, 'pass': 0, 'weight': 0.01},
    {'key': 'commission_sensitivity', 'dimension': 'cost', 'name': '佣金敏感性', 'type': 'lower', 'good': 0.15, 'pass': 0.30, 'weight': 0.005},
    {'key': 'max_slippage_tolerance', 'dimension': 'cost', 'name': '最优滑点容忍', 'type': 'higher', 'good': 0.002, 'pass': 0.0015, 'weight': 0.005},
    # 生命周期维度
    {'key': 'early_quality', 'dimension': 'lifecycle', 'name': '初始收益质量', 'type': 'higher', 'good': 1.0, 'pass': 0.5, 'weight': 0.015},
    {'key': 'mid_quality', 'dimension': 'lifecycle', 'name': '中期收益质量', 'type': 'higher', 'good': 1.0, 'pass': 0.5, 'weight': 0.015},
    {'key': 'late_quality', 'dimension': 'lifecycle', 'name': '末期收益质量', 'type': 'higher', 'good': 0.8, 'pass': 0.3, 'weight': 0.01},
    {'key': 'return_trend_slope', 'dimension': 'lifecycle', 'name': '收益趋势斜率', 'type': 'higher', 'good': 0, 'pass': -0.1, 'weight': 0.005},
    {'key': 'consistency_score', 'dimension': 'lifecycle', 'name': '一致性得分', 'type': 'higher', 'good': 0.5, 'pass': 0.2, 'weight': 0.005},
]

# 硬性门槛（任意一项不通过直接淘汰）
HARD_REJECT = [
    {'key': 'alpha_annual', 'threshold': 0, 'op': 'lt', 'msg': 'Alpha年化不能为负'},
    {'key': 'max_drawdown', 'threshold': 0.50, 'op': 'gt', 'msg': '最大回撤不能超过50%'},
    {'key': 'var_95', 'threshold': -0.10, 'op': 'lt', 'msg': 'VaR风险过高'},
    {'key': 'monte_carlo_pvalue', 'threshold': 0.20, 'op': 'gt', 'msg': '蒙特卡洛p值超过0.20，统计不显著'},
    {'key': 'slippage_sensitivity', 'threshold': 0, 'op': 'lt', 'msg': '扣滑点后收益为负'},
    {'key': 'return_trend_slope', 'threshold': -0.3, 'op': 'lt', 'msg': '收益趋势严重恶化'},
]
```

---

_文档位置: etf_strategy/docs/EVALUATION_SYSTEM_V7.md_
