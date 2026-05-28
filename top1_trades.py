#!/usr/bin/env python
"""Top1模型各ETF最近10个交易"""
import json

with open('data/experiments/fishbody_v3.json', 'r') as f:
    data = json.load(f)

results = data['results']
cfg4_results = [r for r in results if r['config'] == 'Cfg4']

ETF_NAMES = {
    'sh510300': '沪深300',
    'sh510500': '中证500',
    'sh159915': '创业板',
    'sh159806': '新能源',
    'sh512760': '医疗',
    'sh515050': '5G',
    'sh511010': '纳指',
}

print("="*100)
print("Top1模型 (Cfg4) 各ETF最近10个交易记录")
print("配置: 止损-6%, 止盈10%, 持仓20天")
print("="*100)

for r in cfg4_results:
    code = r['code']
    etf_name = ETF_NAMES.get(code, code)
    stats = r['stats']
    trades = r.get('trades', [])
    
    print()
    print("-"*80)
    print("ETF: {} ({})".format(etf_name, code))
    print("总收益: {:.2f}%, 胜率: {:.1f}%, 交易: {}次".format(
        stats['total_return'], stats['win_rate'], stats['trade_count']))
    print("-"*80)
    
    if not trades:
        print("无交易记录")
        continue
    
    sorted_trades = sorted(trades, key=lambda x: x['entry_date'], reverse=True)[:10]
    
    print()
    print("  #  买入日期       买入价    卖出日期       卖出价     收益   天数 原因  评级")
    print("  " + "-"*75)
    
    for idx, trade in enumerate(sorted_trades, 1):
        sc = trade.get('signal_conditions', {})
        conditions_count = sum(sc.values()) if sc else 0
        
        ret = trade['return_pct']
        if ret > 10:
            rating = "***"
        elif ret > 5:
            rating = "**"
        elif ret > 0:
            rating = "*"
        else:
            rating = "XXX"
        
        print("  {}  {}  {:.3f}  {}  {:.3f}  {:>6.1f}%   {:>2}  {:<6}  {}".format(
            idx, trade['entry_date'], trade['entry_price'],
            trade['exit_date'], trade['exit_price'],
            ret, trade['hold_days'], trade['exit_reason'], rating))
        
        if sc:
            signals = []
            if sc.get('bullish_align'): signals.append("多头")
            if sc.get('macd_signal'): signals.append("MACD")
            if sc.get('fishbody'): signals.append("鱼身")
            if sc.get('rsi_ok'): signals.append("RSI")
            if sc.get('trend_ok'): signals.append("趋势")
            print("        信号: {}({}/5)".format("+".join(signals), conditions_count))
    
    total_return = sum(t['return_pct'] for t in sorted_trades)
    avg_return = total_return / len(sorted_trades) if sorted_trades else 0
    wins = sum(1 for t in sorted_trades if t['return_pct'] > 0)
    print()
    print("  统计: 总收益{:.1f}%, 均收益{:.1f}%, 胜率{}/{}".format(
        total_return, avg_return, wins, len(sorted_trades)))