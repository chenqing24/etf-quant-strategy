"""
查看Top3模型的详细交易记录
"""
import pandas as pd
import numpy as np
from pathlib import Path


def calculate_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算基础指标"""
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA10'] = df['close'].rolling(10).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    
    df['EMA12'] = df['close'].ewm(span=12).mean()
    df['EMA26'] = df['close'].ewm(span=26).mean()
    df['DIF'] = df['EMA12'] - df['EMA26']
    df['DEA'] = df['DIF'].ewm(span=9).mean()
    df['MACD'] = (df['DIF'] - df['DEA']) * 2
    
    delta = df['close'].diff()
    gain = delta.apply(lambda x: x if x > 0 else 0)
    loss = delta.apply(lambda x: -x if x < 0 else 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df


def calculate_fish_body_factors(df: pd.DataFrame) -> pd.DataFrame:
    """计算鱼身相关因子"""
    df['high_distance'] = (df['close'] - df['low'].rolling(60).min()) / \
                           (df['high'].rolling(60).max() - df['low'].rolling(60).min() + 0.001) * 100
    
    df['trend_5'] = np.where(df['close'] > df['MA5'], 1, -1)
    df['trend_10'] = np.where(df['MA10'] > df['MA10'].shift(5), 1, -1)
    df['trend_20'] = np.where(df['MA20'] > df['MA20'].shift(10), 1, -1)
    df['trend_consistency'] = (df['trend_5'] + df['trend_10'] + df['trend_20']) / 3
    df['bullish_alignment'] = ((df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])).astype(int)
    df['macd_direction'] = np.where(df['MACD'] > 0, 1, -1)
    
    return df


def get_fish_body_signals(df: pd.DataFrame):
    """获取鱼身买入信号"""
    signals = pd.Series(0, index=df.index)
    signal_reasons = []
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        conditions = []
        
        if row['MA5'] > row['MA10'] > row['MA20']:
            conditions.append("多头排列")
        
        if row['MACD'] > 0:
            conditions.append("MACD正")
        
        if 40 <= row['high_distance'] <= 80:
            conditions.append("鱼身位置")
        
        if 30 <= row['RSI'] <= 60:
            conditions.append("RSI适中")
        
        if row['trend_consistency'] > 0.5:
            conditions.append("趋势一致")
        
        if len(conditions) >= 4:
            signals.iloc[i] = 1
            signal_reasons.append({
                'date': row['date'],
                'close': row['close'],
                'conditions': conditions
            })
    
    return signals, signal_reasons


def backtest_with_trades(df: pd.DataFrame, signals: pd.Series, 
                         stop_loss: float, stop_profit: float,
                         max_hold_days: int):
    """回测并返回详细交易记录"""
    trades = []
    position = None
    entry_idx = None
    
    for i in range(len(df)):
        row = df.iloc[i]
        date = row['date']
        
        if position is None:
            if signals.iloc[i] == 1:
                position = {'entry_idx': i, 'entry_date': date, 'entry_price': row['close']}
                entry_idx = i
        else:
            pnl = (row['close'] - position['entry_price']) / position['entry_price']
            hold_days = i - entry_idx
            
            exit_reason = None
            if pnl <= stop_loss:
                exit_reason = "止损"
            elif pnl >= stop_profit:
                exit_reason = "止盈"
            elif hold_days >= max_hold_days:
                exit_reason = "超时"
            
            if exit_reason:
                trades.append({
                    'entry_date': position['entry_date'],
                    'entry_price': position['entry_price'],
                    'exit_date': date,
                    'exit_price': row['close'],
                    'return': pnl * 100,
                    'hold_days': hold_days,
                    'reason': exit_reason
                })
                position = None
    
    return trades


def analyze_and_print_trades(exp_name: str, config: dict, trades: list, signal_reasons: list):
    """分析并打印交易记录"""
    print()
    print("="*80)
    print(f"📊 {exp_name}")
    print("="*80)
    print(f"配置: 止损{config['stop_loss']*100:.0f}%, 止盈{config['stop_profit']*100:.0f}%, 持仓{config['max_hold_days']}天")
    print()
    
    if not trades:
        print("无交易记录")
        return
    
    print(f"总交易次数: {len(trades)}")
    print()
    
    # 显示最后10笔
    recent_trades = trades[-10:] if len(trades) >= 10 else trades
    start_idx = len(trades) - len(recent_trades)
    
    for i, trade in enumerate(recent_trades):
        idx = start_idx + i + 1
        entry_date = pd.to_datetime(trade['entry_date']).strftime('%Y-%m-%d')
        exit_date = pd.to_datetime(trade['exit_date']).strftime('%Y-%m-%d')
        
        print(f"【第{idx}笔交易】")
        print(f"  买入: {entry_date} @ {trade['entry_price']:.3f}")
        print(f"  卖出: {exit_date} @ {trade['exit_price']:.3f}")
        print(f"  收益率: {trade['return']:.1f}%")
        print(f"  持仓: {trade['hold_days']}天")
        print(f"  原因: {trade['reason']}")
        
        # 尝试匹配买入信号原因
        for reason in signal_reasons:
            reason_date = pd.to_datetime(reason['date']).strftime('%Y-%m-%d')
            if reason_date == entry_date:
                print(f"  信号: {', '.join(reason['conditions'])}")
                break
        
        print()


def main():
    # 加载数据
    df = pd.read_csv('etf_data_live/sh159806.csv')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df = calculate_base_indicators(df)
    df = calculate_fish_body_factors(df)
    
    signals, signal_reasons = get_fish_body_signals(df)
    
    # Top3配置
    configs = {
        'Exp1 (收益最高)': {'stop_loss': -0.05, 'stop_profit': 0.08, 'max_hold_days': 15},
        'Exp12 (收益第二)': {'stop_loss': -0.08, 'stop_profit': 0.06, 'max_hold_days': 7},
        'Exp19 (收益第三)': {'stop_loss': -0.038, 'stop_profit': 0.058, 'max_hold_days': 7},
    }
    
    for exp_name, config in configs.items():
        trades = backtest_with_trades(df, signals, **config)
        analyze_and_print_trades(exp_name, config, trades, signal_reasons)
    
    # 汇总对比
    print()
    print("="*80)
    print("📊 Top3 模型对比")
    print("="*80)
    print()
    print(f"{'模型':<20} {'总交易':<8} {'盈利次数':<8} {'亏损次数':<8} {'胜率':<8} {'平均收益':<10}")
    print("-"*80)
    
    for exp_name, config in configs.items():
        trades = backtest_with_trades(df, signals, **config)
        wins = [t for t in trades if t['return'] > 0]
        losses = [t for t in trades if t['return'] <= 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_return = np.mean([t['return'] for t in trades]) if trades else 0
        
        print(f"{exp_name:<20} {len(trades):<8} {len(wins):<8} {len(losses):<8} {win_rate:.1f}%{'':<4} {avg_return:.1f}%")


if __name__ == '__main__':
    main()