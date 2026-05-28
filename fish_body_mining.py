"""
ETF因子挖掘实验框架
遵循"只吃鱼身"原则
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import json
from pathlib import Path


@dataclass
class FactorConfig:
    """因子配置"""
    name: str                           # 因子名称
    description: str                     # 因子描述
    params: Dict = field(default_factory=dict)  # 因子参数
    weight: float = 0.0                  # 因子权重
    threshold: float = 0.0               # 因子阈值
    direction: str = "long"             # 因子方向: long/short/neutral


@dataclass
class ExperimentResult:
    """实验结果"""
    exp_id: int                          # 实验编号
    factors: List[FactorConfig]          # 使用的因子
    total_return: float = 0.0           # 总收益率
    annual_return: float = 0.0          # 年化收益率
    sharpe_ratio: float = 0.0            # 夏普比率
    max_drawdown: float = 0.0           # 最大回撤
    win_rate: float = 0.0               # 胜率
    trade_count: int = 0                # 交易次数
    fish_body_ratio: float = 0.0        # 鱼身交易占比
    notes: str = ""                      # 实验备注


class FishBodyFactorMining:
    """
    鱼身因子挖掘实验框架
    
    遵循原则: 只吃鱼身，不吃鱼尾
    
    实验流程:
    1. 定义候选因子
    2. 因子评分
    3. 组合测试
    4. 评估结果
    5. 迭代优化
    """
    
    def __init__(self, data_dir: str = 'etf_data_live'):
        self.data_dir = data_dir
        self.results: List[ExperimentResult] = []
        self.candidate_factors: List[FactorConfig] = []
        self.best_factors: List[FactorConfig] = []
        
    def load_data(self, code: str = '159806') -> pd.DataFrame:
        """加载ETF数据"""
        file_path = Path(self.data_dir) / f'{code}.csv'
        if not file_path.exists():
            file_path = Path(self.data_dir) / f'sh{code}.csv'
        
        if not file_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {code}")
        
        df = pd.read_csv(file_path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df
    
    def calculate_base_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算基础指标"""
        # 均线系统
        df['MA5'] = df['close'].rolling(5).mean()
        df['MA10'] = df['close'].rolling(10).mean()
        df['MA20'] = df['close'].rolling(20).mean()
        df['MA60'] = df['close'].rolling(60).mean()
        
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
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # OBV
        obv_change = df['close'].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        df['OBV'] = (obv_change * df['volume']).cumsum()
        df['OBV_ma5'] = df['OBV'].rolling(5).mean()
        df['OBV_ma10'] = df['OBV'].rolling(10).mean()
        
        # 布林带
        df['BB_mid'] = df['close'].rolling(20).mean()
        df['BB_std'] = df['close'].rolling(20).std()
        df['BB_upper'] = df['BB_mid'] + 2 * df['BB_std']
        df['BB_lower'] = df['BB_mid'] - 2 * df['BB_std']
        df['BB_percent'] = (df['close'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower']) * 100
        
        # ADX
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['plus_DM'] = df['high'].diff()
        df['minus_DM'] = -df['low'].diff()
        # 使用 numpy 最大值函数
        df['plus_DM'] = np.maximum(df['plus_DM'].fillna(0), 0)
        df['minus_DM'] = np.maximum(df['minus_DM'].fillna(0), 0)
        df['plus_DI'] = 100 * df['plus_DM'].ewm(span=14).mean() / tr.ewm(span=14).mean()
        df['minus_DI'] = 100 * df['minus_DM'].ewm(span=14).mean() / tr.ewm(span=14).mean()
        df['ADX'] = 100 * abs(df['plus_DI'] - df['minus_DI']) / (df['plus_DI'] + df['minus_DI'] + 0.001)
        
        return df
    
    def calculate_fish_body_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算鱼身相关因子
        这是核心新增逻辑
        """
        # ===== 方向A: 趋势阶段因子 =====
        
        # 因子1: 高点距离因子
        df['high_distance'] = (df['close'] - df['low'].rolling(60).min()) / \
                               (df['high'].rolling(60).max() - df['low'].rolling(60).min() + 0.001) * 100
        
        # 因子2: 均线发散度因子
        df['ma_divergence'] = (df['MA5'] - df['MA20']) / df['MA20'] * 100
        
        # 因子3: 趋势角度因子
        df['trend_angle'] = df['MA5'].pct_change(5) * 100
        
        # ===== 方向B: 多周期方向因子 =====
        
        # 因子4: 多周期方向一致性因子
        df['trend_5'] = np.where(df['close'] > df['MA5'], 1, -1)
        df['trend_10'] = np.where(df['MA10'] > df['MA10'].shift(5), 1, -1)
        df['trend_20'] = np.where(df['MA20'] > df['MA20'].shift(10), 1, -1)
        df['trend_consistency'] = (df['trend_5'] + df['trend_10'] + df['trend_20']) / 3
        
        # 因子5: 多头排列因子
        df['bullish_alignment'] = ((df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])).astype(int)
        
        # ===== 方向C: 动量方向因子 =====
        
        # 因子6: MACD方向因子
        df['macd_direction'] = np.where(df['MACD'] > 0, 1, -1)
        
        # 因子7: 动量加速度因子
        df['macd_acceleration'] = df['MACD'].diff()
        
        # 因子8: DIF-DEA金叉死叉
        df['dif_dea_cross'] = np.where(df['DIF'] > df['DEA'], 1, -1)
        
        return df
    
    def get_fish_body_signals(self, df: pd.DataFrame) -> Tuple[pd.Series, List[str]]:
        """
        获取鱼身买入信号
        
        鱼身条件:
        1. 趋势方向: MA5 > MA10 > MA20
        2. MACD方向: MACD柱 > 0
        3. 位置: 高点距离在40-80%
        
        Returns:
            signals: 买入信号序列
            signal_reasons: 信号原因列表
        """
        signals = pd.Series(0, index=df.index)
        signal_reasons = []
        
        for i in range(20, len(df)):
            row = df.iloc[i]
            conditions = []
            
            # 条件1: 多头排列
            if row['MA5'] > row['MA10'] > row['MA20']:
                conditions.append("多头排列")
            
            # 条件2: MACD向上
            if row['MACD'] > 0:
                conditions.append("MACD正")
            
            # 条件3: 位置在鱼身区间
            if 40 <= row['high_distance'] <= 80:
                conditions.append("鱼身位置")
            
            # 条件4: RSI适中 (不过热不过冷)
            if 30 <= row['RSI'] <= 60:
                conditions.append("RSI适中")
            
            # 条件5: 趋势一致性
            if row['trend_consistency'] > 0.5:
                conditions.append("趋势一致")
            
            # 买入信号: 满足至少4个条件
            if len(conditions) >= 4:
                signals.iloc[i] = 1
                signal_reasons.append(f"满足{len(conditions)}个条件: {','.join(conditions)}")
        
        return signals, signal_reasons
    
    def backtest(self, df: pd.DataFrame, signals: pd.Series, 
                 stop_loss: float = -0.05, stop_profit: float = 0.08,
                 max_hold_days: int = 15) -> Dict:
        """
        回测策略
        """
        trades = []
        position = None
        entry_date = None
        entry_price = None
        
        for i in range(len(df)):
            row = df.iloc[i]
            date = row['date']
            
            if position is None:
                # 检查买入信号
                if signals.iloc[i] == 1:
                    position = {
                        'entry_date': date,
                        'entry_price': row['close'],
                        'code': 'test'
                    }
                    entry_date = i
                    entry_price = row['close']
            else:
                # 检查止损/止盈
                pnl = (row['close'] - entry_price) / entry_price
                hold_days = i - entry_date
                
                if pnl <= stop_loss or pnl >= stop_profit or hold_days >= max_hold_days:
                    # 平仓
                    trades.append({
                        'entry_date': position['entry_date'],
                        'entry_price': entry_price,
                        'exit_date': date,
                        'exit_price': row['close'],
                        'return': pnl,
                        'hold_days': hold_days,
                        'reason': 'stop_loss' if pnl <= stop_loss else ('stop_profit' if pnl >= stop_profit else 'time_out')
                    })
                    position = None
        
        # 计算统计指标
        if not trades:
            return {
                'total_return': 0,
                'annual_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0,
                'trade_count': 0
            }
        
        returns = [t['return'] for t in trades]
        wins = [r for r in returns if r > 0]
        
        total_return = (1 + np.array(returns)).prod() - 1
        annual_return = total_return * 252 / len(df) * 252
        win_rate = len(wins) / len(returns) if returns else 0
        
        # 计算夏普比率
        returns_arr = np.array(returns)
        sharpe = returns_arr.mean() / returns_arr.std() * np.sqrt(252) if returns_arr.std() > 0 else 0
        
        # 计算最大回撤
        cumulative = np.cumprod(1 + returns_arr)
        max_dd = (cumulative - np.maximum.accumulate(cumulative)).min()
        
        return {
            'total_return': total_return * 100,
            'annual_return': annual_return * 100,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd * 100,
            'win_rate': win_rate * 100,
            'trade_count': len(trades),
            'trades': trades
        }
    
    def run_experiment(self, exp_id: int, factor_config: Dict) -> ExperimentResult:
        """
        运行单个实验
        """
        # 加载数据
        df = self.load_data()
        df = self.calculate_base_indicators(df)
        df = self.calculate_fish_body_factors(df)
        
        # 获取信号
        signals, reasons = self.get_fish_body_signals(df)
        
        # 回测
        result = self.backtest(
            df, signals,
            stop_loss=factor_config.get('stop_loss', -0.05),
            stop_profit=factor_config.get('stop_profit', 0.08),
            max_hold_days=factor_config.get('max_hold_days', 15)
        )
        
        # 鱼身交易占比
        fish_body_count = sum(1 for r in reasons if '鱼身位置' in r)
        fish_body_ratio = fish_body_count / len(reasons) if reasons else 0
        
        return ExperimentResult(
            exp_id=exp_id,
            factors=[FactorConfig(name=k, description=str(v)) for k, v in factor_config.items()],
            total_return=result['total_return'],
            annual_return=result['annual_return'],
            sharpe_ratio=result['sharpe_ratio'],
            max_drawdown=result['max_drawdown'],
            win_rate=result['win_rate'],
            trade_count=result['trade_count'],
            fish_body_ratio=fish_body_ratio,
            notes=f"鱼身信号数: {len(reasons)}, 鱼身交易占比: {fish_body_ratio:.1%}"
        )


def run_batch_experiments(n_experiments: int = 20, checkpoint_interval: int = 10):
    """
    运行批量实验
    
    Args:
        n_experiments: 实验总数
        checkpoint_interval: 检查点间隔（每多少轮检查一次）
    """
    mining = FishBodyFactorMining()
    results = []
    
    # 定义不同实验配置
    configs = [
        # 基础实验组 (1-5)
        {'stop_loss': -0.05, 'stop_profit': 0.08, 'max_hold_days': 15},
        {'stop_loss': -0.04, 'stop_profit': 0.06, 'max_hold_days': 10},
        {'stop_loss': -0.06, 'stop_profit': 0.10, 'max_hold_days': 20},
        {'stop_loss': -0.03, 'stop_profit': 0.05, 'max_hold_days': 7},
        {'stop_loss': -0.08, 'stop_profit': 0.12, 'max_hold_days': 25},
        
        # 激进实验组 (6-10)
        {'stop_loss': -0.02, 'stop_profit': 0.04, 'max_hold_days': 5},
        {'stop_loss': -0.03, 'stop_profit': 0.08, 'max_hold_days': 10},
        {'stop_loss': -0.04, 'stop_profit': 0.10, 'max_hold_days': 15},
        {'stop_loss': -0.05, 'stop_profit': 0.12, 'max_hold_days': 20},
        {'stop_loss': -0.06, 'stop_profit': 0.15, 'max_hold_days': 25},
        
        # 保守实验组 (11-15)
        {'stop_loss': -0.10, 'stop_profit': 0.05, 'max_hold_days': 5},
        {'stop_loss': -0.08, 'stop_profit': 0.06, 'max_hold_days': 7},
        {'stop_loss': -0.07, 'stop_profit': 0.08, 'max_hold_days': 10},
        {'stop_loss': -0.06, 'stop_profit': 0.10, 'max_hold_days': 12},
        {'stop_loss': -0.05, 'stop_profit': 0.15, 'max_hold_days': 15},
        
        # 优化实验组 (16-20)
        {'stop_loss': -0.04, 'stop_profit': 0.06, 'max_hold_days': 8},
        {'stop_loss': -0.035, 'stop_profit': 0.055, 'max_hold_days': 7},
        {'stop_loss': -0.045, 'stop_profit': 0.065, 'max_hold_days': 9},
        {'stop_loss': -0.038, 'stop_profit': 0.058, 'max_hold_days': 7},
        {'stop_loss': -0.042, 'stop_profit': 0.062, 'max_hold_days': 8},
    ]
    
    print("="*70)
    print("🐟 鱼身因子挖掘实验")
    print("="*70)
    print(f"总实验数: {n_experiments}")
    print(f"检查点间隔: {checkpoint_interval}")
    print()
    
    for i in range(n_experiments):
        config = configs[i] if i < len(configs) else configs[-1]
        
        print(f"[{i+1}/{n_experiments}] 运行实验...")
        
        try:
            result = mining.run_experiment(i + 1, config)
            results.append(result)
            
            print(f"  收益: {result.total_return:.1f}%, "
                  f"夏普: {result.sharpe_ratio:.2f}, "
                  f"回撤: {result.max_drawdown:.1f}%, "
                  f"交易: {result.trade_count}")
            
        except Exception as e:
            print(f"  实验失败: {e}")
            results.append(None)
        
        # 检查点
        if (i + 1) % checkpoint_interval == 0:
            print()
            print("="*70)
            print(f"📊 检查点 {i+1}: 阶段性总结")
            print("="*70)
            
            valid_results = [r for r in results if r is not None]
            if valid_results:
                # 找出最佳配置
                best = max(valid_results, key=lambda x: x.sharpe_ratio)
                
                print(f"已完成: {len(valid_results)}/{i+1} 实验")
                print(f"最佳配置: Exp{best.exp_id}")
                print(f"  收益: {best.total_return:.1f}%")
                print(f"  夏普: {best.sharpe_ratio:.2f}")
                print(f"  回撤: {best.max_drawdown:.1f}%")
                print()
                
                # 分析结果分布
                returns = [r.total_return for r in valid_results]
                sharpes = [r.sharpe_ratio for r in valid_results]
                
                print(f"收益分布: 均{np.mean(returns):.1f}%, 最高{max(returns):.1f}%, 最低{min(returns):.1f}%")
                print(f"夏普分布: 均{np.mean(sharpes):.2f}, 最高{max(sharpes):.2f}")
                
                # 反思优化建议
                print()
                print("【反思与优化建议】")
                
                if np.mean(returns) < 10:
                    print("  - 当前收益偏低，建议调整止损止盈参数")
                if np.mean(sharpes) < 0.5:
                    print("  - 夏普比率偏低，建议增加趋势过滤条件")
                if max(returns) - min(returns) > 50:
                    print("  - 参数敏感度过高，建议使用更稳健的参数")
                
                print("  - 继续下一轮实验...")
            
            print()
    
    # 最终总结
    print("="*70)
    print("📊 最终总结")
    print("="*70)
    
    valid_results = [r for r in results if r is not None]
    if valid_results:
        # 按各项指标排序
        by_return = sorted(valid_results, key=lambda x: x.total_return, reverse=True)
        by_sharpe = sorted(valid_results, key=lambda x: x.sharpe_ratio, reverse=True)
        by_drawdown = sorted(valid_results, key=lambda x: x.max_drawdown)
        
        print(f"\n总实验数: {len(valid_results)}")
        print(f"成功率: {len(valid_results)/len(results)*100:.1f}%")
        
        print("\n【收益TOP3】")
        for i, r in enumerate(by_return[:3]):
            print(f"  {i+1}. Exp{r.exp_id}: {r.total_return:.1f}%")
        
        print("\n【夏普TOP3】")
        for i, r in enumerate(by_sharpe[:3]):
            print(f"  {i+1}. Exp{r.exp_id}: {r.sharpe_ratio:.2f}")
        
        print("\n【回撤最小TOP3】")
        for i, r in enumerate(by_drawdown[:3]):
            print(f"  {i+1}. Exp{r.exp_id}: {r.max_drawdown:.1f}%")
        
        # 综合最佳
        best_overall = max(valid_results, key=lambda x: x.sharpe_ratio * 0.4 + x.total_return * 0.3 - abs(x.max_drawdown) * 0.3)
        print(f"\n【综合最佳】Exp{best_overall.exp_id}")
        print(f"  收益: {best_overall.total_return:.1f}%")
        print(f"  夏普: {best_overall.sharpe_ratio:.2f}")
        print(f"  回撤: {best_overall.max_drawdown:.1f}%")
        print(f"  交易: {best_overall.trade_count}")
        print(f"  备注: {best_overall.notes}")
        
    return results


if __name__ == '__main__':
    results = run_batch_experiments(n_experiments=20, checkpoint_interval=10)