#!/usr/bin/env python
"""
Top3模型多维度指标分析
"""
import json
import numpy as np
from collections import defaultdict

with open('data/experiments/fishbody_v3.json', 'r') as f:
    data = json.load(f)

results = data['results']

# 按配置分组
config_results = defaultdict(list)
for r in results:
    config_results[r['config']].append(r)

# 按总收益排序Top3
config_ranking = []
for cfg, cfg_results in config_results.items():
    total_ret = sum(r['stats']['total_return'] for r in cfg_results)
    config_ranking.append((cfg, total_ret, cfg_results))

config_ranking.sort(key=lambda x: x[1], reverse=True)
top3 = config_ranking[:3]

# 定义9个评估维度
DIMENSIONS = [
    ('D1', '总收益', '最终收益百分比', '%'),
    ('D2', '年化收益', '平均年化收益', '%'),
    ('D3', '夏普比率', '风险调整收益', ''),
    ('D4', '最大回撤', '历史最大亏损', '%'),
    ('D5', '胜率', '盈利交易占比', '%'),
    ('D6', '盈亏比', '平均盈利/平均亏损', ''),
    ('D7', '交易次数', '总交易数', '次'),
    ('D8', 'IC均值', '因子预测能力', ''),
    ('D9', '因子方向一致', '方向符合预期', '%'),
]

def get_dimension_value(stats, dimension):
    """获取指定维度的值"""
    if dimension == 'D1':
        return stats.get('total_return', 0)
    elif dimension == 'D2':
        return stats.get('annual_return', 0)
    elif dimension == 'D3':
        return stats.get('sharpe_ratio', 0)
    elif dimension == 'D4':
        return stats.get('max_drawdown', 0)
    elif dimension == 'D5':
        return stats.get('win_rate', 0)
    elif dimension == 'D6':
        return stats.get('profit_loss_ratio', 0)
    elif dimension == 'D7':
        return stats.get('trade_count', 0)
    return 0

print("="*100)
print("📊 Top3 模型多维度指标分析")
print("="*100)

# ========== 1. Top3配置综合对比 ==========
print()
print("="*90)
print("一、Top3 配置综合对比")
print("="*90)

for rank, (cfg, total_ret, cfg_results) in enumerate(top3, 1):
    params = cfg_results[0]['params']
    n_etfs = len(cfg_results)
    
    print()
    print(f"🏆 第{rank}名: {cfg}")
    print(f"   配置: 止损{int(params['stop_loss']*100)}%, 止盈{int(params['stop_profit']*100)}%, 持仓{params['max_hold_days']}天")
    print(f"   测试ETF数: {n_etfs}")
    print()
    print("   " + "-"*80)
    
    for dim_id, dim_name, dim_desc, dim_unit in DIMENSIONS:
        values = [get_dimension_value(r['stats'], dim_id) for r in cfg_results]
        avg_val = np.mean(values)
        max_val = max(values)
        min_val = min(values)
        
        if dim_unit == '%':
            print(f"   {dim_id} {dim_name:<10}: 均值{avg_val:>7.2f}{dim_unit}  最大{max_val:>7.2f}{dim_unit}  最小{min_val:>7.2f}{dim_unit}")
        else:
            print(f"   {dim_id} {dim_name:<10}: 均值{avg_val:>7.4f}  最大{max_val:>7.4f}  最小{min_val:>7.4f}")

# ========== 2. 各配置9维度详细数据 ==========
print()
print("="*90)
print("二、各配置9维度详细数据 (按ETF分类)")
print("="*90)

for rank, (cfg, total_ret, cfg_results) in enumerate(top3, 1):
    params = cfg_results[0]['params']
    
    print()
    print(f"🏆 第{rank}名: {cfg} (止损{int(params['stop_loss']*100)}%/止盈{int(params['stop_profit']*100)}%/持仓{params['max_hold_days']}天)")
    print()
    
    # 表头
    print("   " + "{:<14} {:>8} {:>8} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
        "ETF", "总收益", "年化", "夏普", "回撤", "胜率", "盈亏比", "交易"))
    print("   " + "-"*80)
    
    for r in cfg_results:
        stats = r['stats']
        etf = r['code'].replace('sh', '')
        
        print("   " + "{:<14} {:>7.1f}% {:>7.1f}% {:>7.2f} {:>7.1f}% {:>7.1f}% {:>7.2f} {:>7}".format(
            etf,
            stats.get('total_return', 0),
            stats.get('annual_return', 0),
            stats.get('sharpe_ratio', 0),
            stats.get('max_drawdown', 0),
            stats.get('win_rate', 0),
            stats.get('profit_loss_ratio', 0),
            stats.get('trade_count', 0)
        ))
    
    # 合计行
    n = len(cfg_results)
    print("   " + "-"*80)
    print("   " + "{:<14} {:>7.1f}% {:>7.1f}% {:>7.2f} {:>7.1f}% {:>7.1f}% {:>7.2f} {:>7}".format(
        "平均",
        np.mean([r['stats'].get('total_return', 0) for r in cfg_results]),
        np.mean([r['stats'].get('annual_return', 0) for r in cfg_results]),
        np.mean([r['stats'].get('sharpe_ratio', 0) for r in cfg_results]),
        np.mean([r['stats'].get('max_drawdown', 0) for r in cfg_results]),
        np.mean([r['stats'].get('win_rate', 0) for r in cfg_results]),
        np.mean([r['stats'].get('profit_loss_ratio', 0) for r in cfg_results]),
        int(np.mean([r['stats'].get('trade_count', 0) for r in cfg_results]))
    ))

# ========== 3. 因子IC分析 ==========
print()
print("="*90)
print("三、Top3 因子IC分析")
print("="*90)

FACTORS = ['BULLISH_ALIGN', 'MACD_SIGNAL', 'FISHBODY_OK', 'RSI_OK', 'TREND_OK']

for rank, (cfg, total_ret, cfg_results) in enumerate(top3, 1):
    params = cfg_results[0]['params']
    
    print()
    print(f"🏆 第{rank}名: {cfg}")
    print()
    print("   " + "{:<20} {:>10} {:>10} {:>10} {:>10} {:>10}".format(
        "ETF", "BULLISH", "MACD", "FISHBODY", "RSI", "TREND"))
    print("   " + "-"*75)
    
    for r in cfg_results:
        ic = r['stats'].get('ic_results', {})
        etf = r['code'].replace('sh', '')
        
        print("   " + "{:<20} {:>10.4f} {:>10.4f} {:>10.4f} {:>10.4f} {:>10.4f}".format(
            etf,
            ic.get('BULLISH_ALIGN', 0),
            ic.get('MACD_SIGNAL', 0),
            ic.get('FISHBODY_OK', 0),
            ic.get('RSI_OK', 0),
            ic.get('TREND_OK', 0)
        ))
    
    # 平均IC
    print("   " + "-"*75)
    print("   " + "{:<20} {:>10.4f} {:>10.4f} {:>10.4f} {:>10.4f} {:>10.4f}".format(
        "平均IC",
        np.mean([r['stats'].get('ic_results', {}).get('BULLISH_ALIGN', 0) for r in cfg_results]),
        np.mean([r['stats'].get('ic_results', {}).get('MACD_SIGNAL', 0) for r in cfg_results]),
        np.mean([r['stats'].get('ic_results', {}).get('FISHBODY_OK', 0) for r in cfg_results]),
        np.mean([r['stats'].get('ic_results', {}).get('RSI_OK', 0) for r in cfg_results]),
        np.mean([r['stats'].get('ic_results', {}).get('TREND_OK', 0) for r in cfg_results])
    ))
    
    # 有效因子统计
    print()
    print("   有效因子统计 (IC>0):")
    for factor in FACTORS:
        valid_count = sum(1 for r in cfg_results if r['stats'].get('ic_results', {}).get(factor, 0) > 0)
        valid_ratio = valid_count / len(cfg_results) * 100
        avg_ic = np.mean([r['stats'].get('ic_results', {}).get(factor, 0) for r in cfg_results])
        status = "✅" if valid_ratio > 50 else "⚠️" if valid_ratio > 0 else "❌"
        print(f"   {status} {factor:<15}: 有效{valid_count}/{len(cfg_results)} ({valid_ratio:.0f}%)  平均IC={avg_ic:.4f}")

# ========== 4. 各维度排名 ==========
print()
print("="*90)
print("四、Top3 各维度排名")
print("="*90)

print()
print("   " + "{:<20} {:>12} {:>12} {:>12}".format("维度", "第1名(Cfg4)", "第2名(Cfg5)", "第3名(Cfg2)"))
print("   " + "-"*60)

for dim_id, dim_name, dim_desc, dim_unit in DIMENSIONS:
    vals = []
    for cfg, total_ret, cfg_results in top3:
        values = [get_dimension_value(r['stats'], dim_id) for r in cfg_results]
        vals.append(np.mean(values))
    
    if dim_id in ['D1', 'D2', 'D3', 'D5', 'D6']:
        # 这些指标越大越好
        ranks = sorted(range(len(vals)), key=lambda i: vals[i], reverse=True)
        best = [top3[i][0] for i in ranks]
    else:
        # 这些指标越小越好(绝对值或负值)
        ranks = sorted(range(len(vals)), key=lambda i: abs(vals[i]))
        best = [top3[i][0] for i in ranks]
    
    print(f"   {dim_id} {dim_name:<14}: {vals[0]:>10.2f}  {vals[1]:>10.2f}  {vals[2]:>10.2f}")
    print(f"   {'':20} {'排名:'+','.join(best):<40}")

# ========== 5. 综合评分 ==========
print()
print("="*90)
print("五、Top3 综合评分 (9维度加权)")
print("="*90)

# 权重定义
WEIGHTS = {
    'D1': 0.20,  # 总收益
    'D2': 0.15,  # 年化收益
    'D3': 0.15,  # 夏普比率
    'D4': 0.15,  # 最大回撤 (越小越好)
    'D5': 0.10,  # 胜率
    'D6': 0.10,  # 盈亏比
    'D7': 0.05,  # 交易次数
    'D8': 0.05,  # IC均值
    'D9': 0.05,  # 因子方向一致
}

# 计算每个配置每个维度的标准化得分
all_values = defaultdict(list)
for r in results:
    cfg = r['config']
    for dim_id, _, _, _ in DIMENSIONS[:8]:  # D1-D8
        val = get_dimension_value(r['stats'], dim_id)
        all_values[dim_id].append(val)

# 计算每个配置的加权得分
scores = {}
for cfg, total_ret, cfg_results in top3:
    weighted_score = 0
    for dim_id, _, _, _ in DIMENSIONS[:8]:
        vals = [get_dimension_value(r['stats'], dim_id) for r in cfg_results]
        cfg_avg = np.mean(vals)
        
        # 标准化到0-100
        if all_values[dim_id]:
            min_v = min(all_values[dim_id])
            max_v = max(all_values[dim_id])
            if max_v > min_v:
                norm_score = (cfg_avg - min_v) / (max_v - min_v) * 100
            else:
                norm_score = 50
        else:
            norm_score = 50
        
        weighted_score += norm_score * WEIGHTS[dim_id]
    
    scores[cfg] = weighted_score

print()
print("   权重分配:")
for dim_id, _, dim_name, _ in DIMENSIONS[:8]:
    print(f"   {dim_id} {dim_name:<12}: {WEIGHTS[dim_id]*100:.0f}%")

print()
print("   综合得分:")
for cfg, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
    print(f"   {cfg}: {score:.1f}分")

# ========== 6. 风险收益对比 ==========
print()
print("="*90)
print("六、Top3 风险收益对比")
print("="*90)

print()
print("   风险收益指标对比:")
print()
print("   " + "{:<20} {:>15} {:>15} {:>15}".format("配置", "收益/回撤比", "卡玛比率", "盈利效率"))
print("   " + "-"*70)

for cfg, total_ret, cfg_results in top3:
    returns = [r['stats'].get('total_return', 0) for r in cfg_results]
    drawdowns = [abs(r['stats'].get('max_drawdown', 0)) for r in cfg_results]
    
    avg_ret = np.mean(returns)
    avg_dd = np.mean(drawdowns)
    
    # 收益/回撤比
    ratio1 = avg_ret / avg_dd if avg_dd > 0 else 0
    # 卡玛比率 = 年化收益/最大回撤
    annual = np.mean([r['stats'].get('annual_return', 0) for r in cfg_results])
    ratio2 = annual / avg_dd if avg_dd > 0 else 0
    # 盈利效率 = 总收益/总交易次数
    trades = np.mean([r['stats'].get('trade_count', 0) for r in cfg_results])
    ratio3 = avg_ret / trades if trades > 0 else 0
    
    print(f"   {cfg:<20} {ratio1:>12.2f}    {ratio2:>12.2f}    {ratio3:>12.2f}")

print()
print("   指标说明:")
print("   - 收益/回撤比: 每承担1%回撤获得多少收益 (越大越好)")
print("   - 卡玛比率: 年化收益/最大回撤 (越大越好)")
print("   - 盈利效率: 每笔交易平均收益 (越大越好)")