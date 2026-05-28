#!/usr/bin/env python
"""
Top3模型交易记录详细分析
"""
import json
from collections import defaultdict

with open('data/experiments/fishbody_v3.json', 'r') as f:
    data = json.load(f)

results = data['results']

# 按配置分组并计算总收益
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

print("="*100)
print("🏆 Top3 模型交易记录详细分析")
print("="*100)

for rank, (cfg, total_ret, cfg_results) in enumerate(top3, 1):
    params = cfg_results[0]['params']
    
    print()
    print("="*90)
    print(f"🥇 第{rank}名: {cfg}")
    print(f"   配置: 止损{int(params['stop_loss']*100)}%, 止盈{int(params['stop_profit']*100)}%, 持仓{params['max_hold_days']}天")
    print(f"   总收益: {total_ret:.1f}%, 平均收益: {total_ret/len(cfg_results):.1f}%")
    print("="*90)
    
    # 收集所有交易记录
    all_trades = []
    for r in cfg_results:
        for trade in r.get('trades', []):
            trade['etf'] = r['code']
            trade['config'] = cfg
            all_trades.append(trade)
    
    # 按日期排序，取最近的10条
    all_trades.sort(key=lambda x: x['entry_date'], reverse=True)
    recent_trades = all_trades[:10]
    
    print()
    print(f"{'#':<3} {'ETF':<12} {'买入日期':<12} {'价格':<8} {'卖出日期':<12} {'价格':<8} {'收益':<8} {'天数':<4} {'原因':<6} {'决策评分'}")
    print("-"*100)
    
    for idx, trade in enumerate(recent_trades, 1):
        # 信号条件
        sc = trade.get('signal_conditions', {})
        conditions_count = sum(sc.values()) if sc else 0
        
        # 决策评分
        score = conditions_count * 20  # 每个条件20分，满分100
        
        # 收益评级
        ret = trade['return_pct']
        if ret > 10:
            rating = "⭐⭐⭐"
        elif ret > 5:
            rating = "⭐⭐"
        elif ret > 0:
            rating = "⭐"
        else:
            rating = "❌"
        
        print(f"{idx:<3} {trade['etf']:<12} {trade['entry_date']:<12} {trade['entry_price']:<8.3f} "
              f"{trade['exit_date']:<12} {trade['exit_price']:<8.3f} {ret:>6.1f}%   {trade['hold_days']:<4} "
              f"{trade['exit_reason']:<6} {rating}")
        
        # 信号详情
        if sc:
            signals = []
            if sc.get('bullish_align'): signals.append("多头")
            if sc.get('macd_signal'): signals.append("MACD+")
            if sc.get('fishbody'): signals.append("鱼身")
            if sc.get('rsi_ok'): signals.append("RSI")
            if sc.get('trend_ok'): signals.append("趋势")
            print(f"      信号: {' + '.join(signals)} ({conditions_count}/5) 评分: {score}/100")
    
    # 统计
    print()
    total_return = sum(t['return_pct'] for t in recent_trades)
    avg_return = total_return / len(recent_trades)
    wins = sum(1 for t in recent_trades if t['return_pct'] > 0)
    print(f"  统计: 总收益{total_return:.1f}%, 均收益{avg_return:.1f}%, 胜率{wins}/{len(recent_trades)}")

# 汇总分析
print()
print("="*100)
print("📊 Top3 模型决策分析汇总")
print("="*100)

print()
print("【决策因素评分标准】")
print("  每个鱼身因子条件满足 = 20分")
print("  5个条件全部满足 = 100分 (最强信号)")
print("  4个条件满足 = 80分 (标准买入)")
print("  3个条件满足 = 60分 (谨慎观望)")
print()

print("【各模型决策特点】")
for rank, (cfg, total_ret, cfg_results) in enumerate(top3, 1):
    params = cfg_results[0]['params']
    
    # 统计信号分布
    signal_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in cfg_results:
        for trade in r.get('trades', []):
            sc = trade.get('signal_conditions', {})
            cnt = sum(sc.values()) if sc else 0
            if cnt in signal_dist:
                signal_dist[cnt] += 1
    
    total_signals = sum(signal_dist.values())
    print()
    print(f"  {cfg} (止损{int(params['stop_loss']*100)}%/止盈{int(params['stop_profit']*100)}%/持仓{params['max_hold_days']}天)")
    print(f"    信号分布: 5条件={signal_dist[5]}次, 4条件={signal_dist[4]}次, 3条件={signal_dist[3]}次")
    print(f"    强信号(4+)比例: {(signal_dist[4]+signal_dist[5])/max(1,total_signals)*100:.1f}%")