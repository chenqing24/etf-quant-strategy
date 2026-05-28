"""
生成Top3模型（Exp1, Exp12, Exp19）的详细交易记录
"""
import pandas as pd
import numpy as np
from pathlib import Path


def calculate_indicators(df):
    """计算所有指标"""
    # 均线
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA10'] = df['close'].rolling(10).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    
    # MACD
    df['EMA12'] = df['close'].ewm(span=12).mean()
    df['EMA26'] = df['close'].ewm(span=26).mean()
    df['DIF'] = df['EMA12'] - df['EMA26']
    df['DEA'] = df['DIF'].ewm(span=9).mean()
    df['MACD'] = (df['DIF'] - df['DEA']) * 2
    
    # RSI
    delta = df['close'].diff()
    gain = delta.apply(lambda x: x if x > 0 else 0)
    loss = delta.apply(lambda x: -x if x < 0 else 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / (avg_loss + 0.001)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 鱼身位置
    df['high_distance'] = (df['close'] - df['low'].rolling(60).min()) / \
                          (df['high'].rolling(60).max() - df['low'].rolling(60).min() + 0.001) * 100
    
    # 趋势一致性
    df['trend_5'] = np.where(df['close'] > df['MA5'], 1, -1)
    df['trend_10'] = np.where(df['MA10'] > df['MA10'].shift(5), 1, -1)
    df['trend_20'] = np.where(df['MA20'] > df['MA20'].shift(10), 1, -1)
    df['trend_consistency'] = (df['trend_5'] + df['trend_10'] + df['trend_20']) / 3
    
    # 多头排列
    df['bullish'] = ((df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])).astype(int)
    
    return df


def get_signal_reasons(row):
    """获取信号原因"""
    reasons = []
    
    # 检查各条件
    if row['MA5'] > row['MA10'] > row['MA20']:
        reasons.append("多头排列")
    if row['MACD'] > 0:
        reasons.append("MACD正")
    if 40 <= row['high_distance'] <= 80:
        reasons.append("鱼身位置")
    if 30 <= row['RSI'] <= 60:
        reasons.append("RSI适中")
    if row['trend_consistency'] > 0.5:
        reasons.append("趋势一致")
    
    return reasons


def backtest_with_trades(df, stop_loss, stop_profit, max_hold_days, name):
    """回测并返回详细交易记录"""
    trades = []
    position = None
    entry_idx = None
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        
        if position is None:
            # 检查买入条件
            reasons = get_signal_reasons(row)
            if len(reasons) >= 4:
                position = {
                    'entry_date': row['date'],
                    'entry_price': row['close'],
                    'entry_idx': i,
                    'reasons': reasons.copy()
                }
                entry_idx = i
        else:
            # 检查平仓条件
            pnl = (row['close'] - position['entry_price']) / position['entry_price']
            hold_days = i - entry_idx
            
            if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold_days:
                reason = "止损" if pnl <= stop_loss else ("止盈" if pnl >= stop_profit else "到期")
                
                trades.append({
                    'model': name,
                    'buy_date': position['entry_date'],
                    'buy_price': position['entry_price'],
                    'buy_reasons': position['reasons'],
                    'sell_date': row['date'],
                    'sell_price': row['close'],
                    'return_pct': pnl * 100,
                    'hold_days': hold_days,
                    'sell_reason': reason,
                    'exit_pnl': pnl
                })
                position = None
    
    return trades


def main():
    print("="*70)
    print("📊 Top3模型详细交易记录分析")
    print("="*70)
    
    # 加载数据
    df = pd.read_csv('etf_data_live/sh159806.csv')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df = calculate_indicators(df)
    
    # Top3配置
    configs = [
        {'stop_loss': -0.05, 'stop_profit': 0.08, 'max_hold_days': 15, 'name': 'Exp1(44.1%)'},
        {'stop_loss': -0.06, 'stop_profit': 0.10, 'max_hold_days': 12, 'name': 'Exp12(44.0%)'},
        {'stop_loss': -0.06, 'stop_profit': 0.12, 'max_hold_days': 25, 'name': 'Exp19(41.8%)'},
    ]
    
    all_trades = []
    
    for config in configs:
        trades = backtest_with_trades(
            df,
            config['stop_loss'],
            config['stop_profit'],
            config['max_hold_days'],
            config['name']
        )
        all_trades.extend(trades)
    
    # 转换为DataFrame
    trades_df = pd.DataFrame(all_trades)
    
    # 按模型分组输出
    for config in configs:
        model_name = config['name']
        model_trades = trades_df[trades_df['model'] == model_name].tail(10)
        
        print()
        print("="*70)
        print(f"📈 {model_name}")
        print(f"   止损: {config['stop_loss']*100:.0f}% | 止盈: {config['stop_profit']*100:.0f}% | 持仓: {config['max_hold_days']}天")
        print("="*70)
        
        if model_trades.empty:
            print("  无交易记录")
            continue
        
        print()
        print(f"{'序号':<4} {'买入日期':<12} {'买入价':<8} {'卖出日期':<12} {'卖出价':<8} {'收益':<8} {'天数':<5} {'买卖原因'}")
        print("-"*70)
        
        for idx, (_, trade) in enumerate(model_trades.iterrows(), 1):
            buy_reasons = " + ".join(trade['buy_reasons'])
            sell_reason = trade['sell_reason']
            
            print(f"{idx:<4} {str(trade['buy_date'])[:10]:<12} {trade['buy_price']:.3f}    "
                  f"{str(trade['sell_date'])[:10]:<12} {trade['sell_price']:.3f}    "
                  f"{trade['return_pct']:+.1f}%   {trade['hold_days']:<5} {buy_reasons}")
            print(f"      → 卖出原因: {sell_reason}")
            print()
    
    # 汇总表
    print()
    print("="*70)
    print("📊 交易汇总对比")
    print("="*70)
    
    summary_data = []
    for config in configs:
        model_name = config['name']
        model_trades = trades_df[trades_df['model'] == model_name]
        
        if not model_trades.empty:
            summary_data.append({
                '模型': model_name,
                '交易数': len(model_trades),
                '平均收益': model_trades['return_pct'].mean(),
                '胜率': (model_trades['return_pct'] > 0).mean() * 100,
                '平均持仓': model_trades['hold_days'].mean(),
                '最大单笔': model_trades['return_pct'].max(),
                '最小单笔': model_trades['return_pct'].min()
            })
    
    summary_df = pd.DataFrame(summary_data)
    print(summary_df.to_string(index=False))


if __name__ == '__main__':
    main()