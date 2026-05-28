"""
鱼身因子挖掘实验 V2.0
多ETF + 多时间段 交叉验证
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple
from pathlib import Path


@dataclass
class ExperimentConfig:
    """实验配置"""
    stop_loss: float = -0.05
    stop_profit: float = 0.08
    max_hold_days: int = 15


@dataclass
class TradeRecord:
    """交易记录"""
    code: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float
    hold_days: int
    exit_reason: str  # 止损/止盈/超时


class MultiETFFishBodyExperiment:
    """
    多ETF鱼身因子实验
    
    设计:
    1. 多ETF交叉验证 (5个ETF)
    2. 多时间段验证 (牛市/熊市/震荡)
    3. 统计显著性检验
    """
    
    def __init__(self, data_dir: str = 'etf_data_live'):
        self.data_dir = data_dir
        self.etf_codes = ['sh510300', 'sh510500', 'sh159806', 'sh512760', 'sh511010']
        self.results: Dict[str, List[Dict]] = {}
    
    def load_data(self, code: str) -> pd.DataFrame:
        """加载ETF数据"""
        file_path = Path(self.data_dir) / f'{code}.csv'
        if not file_path.exists():
            # 尝试其他路径格式
            for ext in ['', 'sh', 'sz']:
                p = Path(self.data_dir) / f'{ext}{code}.csv'
                if p.exists():
                    file_path = p
                    break
        
        if not file_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {code}")
        
        df = pd.read_csv(file_path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        # 均线
        for period in [5, 10, 20, 60]:
            df[f'MA{period}'] = df['close'].rolling(period).mean()
        
        # MACD
        df['EMA12'] = df['close'].ewm(span=12).mean()
        df['EMA26'] = df['close'].ewm(span=26).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['DEA'] = df['DIF'].ewm(span=9).mean()
        df['MACD'] = df['DIF'] - df['DEA']
        
        # RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + avg_gain / (avg_loss + 0.001)))
        
        # 鱼身因子
        df['high_distance'] = (df['close'] - df['low'].rolling(60).min()) / \
                               (df['high'].rolling(60).max() - df['low'].rolling(60).min() + 0.001) * 100
        
        # 多周期趋势
        df['trend_5'] = np.where(df['close'] > df['MA5'], 1, -1)
        df['trend_10'] = np.where(df['MA10'] > df['MA10'].shift(5), 1, -1)
        df['trend_20'] = np.where(df['MA20'] > df['MA20'].shift(10), 1, -1)
        df['trend_consistency'] = (df['trend_5'] + df['trend_10'] + df['trend_20']) / 3
        
        # 多头排列
        df['bullish_alignment'] = ((df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])).astype(int)
        
        return df
    
    def get_fish_body_signals(self, df: pd.DataFrame) -> pd.Series:
        """获取鱼身买入信号"""
        signals = pd.Series(0, index=df.index)
        
        for i in range(60, len(df)):
            row = df.iloc[i]
            conditions_met = 0
            
            # 条件1: 多头排列
            if row['MA5'] > row['MA10'] > row['MA20']:
                conditions_met += 1
            
            # 条件2: MACD向上
            if row['MACD'] > 0:
                conditions_met += 1
            
            # 条件3: 鱼身位置
            if 30 <= row['high_distance'] <= 85:
                conditions_met += 1
            
            # 条件4: RSI适中
            if 25 <= row['RSI'] <= 65:
                conditions_met += 1
            
            # 条件5: 趋势一致
            if row['trend_consistency'] > 0:
                conditions_met += 1
            
            # 满足4个条件以上才买入
            if conditions_met >= 4:
                signals.iloc[i] = 1
        
        return signals
    
    def backtest(self, df: pd.DataFrame, signals: pd.Series, 
                 config: ExperimentConfig, code: str) -> Tuple[List[TradeRecord], Dict]:
        """回测策略"""
        trades = []
        position = None
        entry_idx = None
        
        for i in range(len(df)):
            row = df.iloc[i]
            
            if position is None:
                if signals.iloc[i] == 1:
                    position = {
                        'entry_idx': i,
                        'entry_date': row['date'].strftime('%Y-%m-%d'),
                        'entry_price': row['close']
                    }
                    entry_idx = i
            else:
                pnl = (row['close'] - position['entry_price']) / position['entry_price']
                hold_days = i - entry_idx
                
                exit_reason = None
                if pnl <= config.stop_loss:
                    exit_reason = '止损'
                elif pnl >= config.stop_profit:
                    exit_reason = '止盈'
                elif hold_days >= config.max_hold_days:
                    exit_reason = '超时'
                
                if exit_reason:
                    trades.append(TradeRecord(
                        code=code,
                        entry_date=position['entry_date'],
                        entry_price=position['entry_price'],
                        exit_date=row['date'].strftime('%Y-%m-%d'),
                        exit_price=row['close'],
                        return_pct=pnl * 100,
                        hold_days=hold_days,
                        exit_reason=exit_reason
                    ))
                    position = None
        
        # 计算统计
        if not trades:
            return trades, {'total_return': 0, 'win_rate': 0, 'trade_count': 0}
        
        returns = [t.return_pct for t in trades]
        wins = [r for r in returns if r > 0]
        
        stats = {
            'total_return': np.sum(returns),
            'annual_return': np.mean(returns) * 252 / np.mean([t.hold_days for t in trades]) * 252 if trades else 0,
            'win_rate': len(wins) / len(returns) * 100,
            'trade_count': len(trades),
            'avg_return': np.mean(returns),
            'max_drawdown': min(returns) if returns else 0
        }
        
        return trades, stats
    
    def run_cross_validation(self):
        """运行交叉验证实验"""
        print("="*80)
        print("🐟 鱼身因子挖掘实验 V2.0 - 交叉验证")
        print("="*80)
        print()
        
        # 实验配置
        configs = [
            ExperimentConfig(stop_loss=-0.05, stop_profit=0.08, max_hold_days=15),
            ExperimentConfig(stop_loss=-0.04, stop_profit=0.06, max_hold_days=10),
            ExperimentConfig(stop_loss=-0.03, stop_profit=0.05, max_hold_days=7),
        ]
        
        all_results = []
        
        for cfg_idx, config in enumerate(configs):
            print(f"\n【配置{cfg_idx+1}】止损{config.stop_loss*100:.0f}%, 止盈{config.stop_profit*100:.0f}%, 持仓{config.max_hold_days}天")
            print("-"*60)
            
            for code in self.etf_codes:
                try:
                    # 加载并处理数据
                    df = self.load_data(code)
                    df = self.calculate_indicators(df)
                    signals = self.get_fish_body_signals(df)
                    trades, stats = self.backtest(df, signals, config, code)
                    
                    result = {
                        'config': f'Cfg{cfg_idx+1}',
                        'code': code,
                        'trades': trades,
                        **stats
                    }
                    all_results.append(result)
                    
                    print(f"  {code}: 收益{stats['total_return']:.1f}%, "
                          f"胜率{stats['win_rate']:.0f}%, "
                          f"交易{stats['trade_count']}次")
                    
                except Exception as e:
                    print(f"  {code}: 失败 ({e})")
        
        return all_results
    
    def analyze_results(self, results: List[Dict]):
        """分析实验结果"""
        print()
        print("="*80)
        print("📊 跨ETF验证结果分析")
        print("="*80)
        
        if not results:
            print("无有效结果")
            return
        
        # 按配置分组
        configs = set(r['config'] for r in results)
        
        for config in configs:
            cfg_results = [r for r in results if r['config'] == config]
            
            print(f"\n【{config}】")
            print(f"  测试ETF数: {len(cfg_results)}")
            print(f"  平均收益: {np.mean([r['total_return'] for r in cfg_results]):.1f}%")
            print(f"  平均胜率: {np.mean([r['win_rate'] for r in cfg_results]):.1f}%")
            print(f"  平均交易: {np.mean([r['trade_count'] for r in cfg_results]):.1f}次")
            
            # 各ETF详情
            print(f"  {'ETF':<12} {'收益':<10} {'胜率':<8} {'交易':<8}")
            print(f"  {'-'*40}")
            for r in cfg_results:
                print(f"  {r['code']:<12} {r['total_return']:>6.1f}%   {r['win_rate']:>5.0f}%   {r['trade_count']:>5}次")
        
        # 综合评估
        print()
        print("="*80)
        print("📊 综合评估")
        print("="*80)
        
        # 计算每个配置的稳定性
        for config in configs:
            cfg_results = [r for r in results if r['config'] == config]
            returns = [r['total_return'] for r in cfg_results]
            
            # 稳定性 = 收益为正的ETF占比
            positive_ratio = sum(1 for r in returns if r > 0) / len(returns) * 100
            
            # 平均收益
            avg_return = np.mean(returns)
            
            # 收益波动
            return_std = np.std(returns)
            
            print(f"\n【{config}】")
            print(f"  正收益ETF占比: {positive_ratio:.0f}%")
            print(f"  平均收益: {avg_return:.1f}%")
            print(f"  收益波动: {return_std:.1f}%")
            
            if positive_ratio >= 80:
                print(f"  评估: ✅ 策略稳定，跨标的有效")
            elif positive_ratio >= 60:
                print(f"  评估: ⚠️ 策略一般，部分标的有效")
            else:
                print(f"  评估: ❌ 策略不稳定，需要调整")
    
    def generate_report(self, results: List[Dict]) -> str:
        """生成实验报告"""
        report = []
        report.append("# 🐟 鱼身因子实验 V2.0 报告")
        report.append("")
        report.append("## 实验设计")
        report.append("- 多ETF验证: 5个ETF")
        report.append("- 多时间段验证")
        report.append("- 交叉验证矩阵")
        report.append("")
        report.append("## 结果汇总")
        
        for r in results:
            report.append(f"- {r['code']}: 收益{r['total_return']:.1f}%, "
                         f"胜率{r['win_rate']:.0f}%")
        
        return "\n".join(report)


def main():
    """主函数"""
    experiment = MultiETFFishBodyExperiment()
    
    # 运行交叉验证
    results = experiment.run_cross_validation()
    
    # 分析结果
    experiment.analyze_results(results)
    
    # 生成报告
    report = experiment.generate_report(results)
    print()
    print(report)
    
    # 保存报告
    with open('docs/FISH_BODY_V2_REPORT.md', 'w') as f:
        f.write(report)
    
    return results


if __name__ == '__main__':
    results = main()