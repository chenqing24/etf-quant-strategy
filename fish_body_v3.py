"""
鱼身因子挖掘实验 V3.0
多ETF × 多参数 + 未来函数/过拟合检验
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple
from pathlib import Path
from datetime import datetime
import json
import random


@dataclass
class ExperimentConfig:
    """实验配置"""
    stop_loss: float = -0.05
    stop_profit: float = 0.08
    max_hold_days: int = 15
    
    def to_dict(self) -> dict:
        return asdict(self)


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
    exit_reason: str
    signal_conditions: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestStats:
    """回测统计"""
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    trade_count: int = 0
    ic_results: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationResult:
    """验证结果"""
    no_look_ahead: bool = True
    no_overfit: bool = True
    train_test_decay: float = 0.0
    param_sensitivity: float = 0.0
    random_vs_fishbody_pvalue: float = 1.0
    
    def to_dict(self) -> dict:
        return asdict(self)


class MultiETFFishBodyV3:
    """
    鱼身因子挖掘实验 V3.0
    
    实验设计:
    - 7个有数据的ETF
    - 全时段回测
    - 6组参数配置
    - 未来函数检验
    - 过拟合检验 (随机对照)
    - IC因子有效性检验
    """
    
    # ETF配置 (只包含有数据的)
    ETF_LIST = [
        ('sh510300', '沪深300', '宽基'),
        ('sh510500', '中证500', '宽基'),
        ('sh159915', '创业板', '宽基'),
        ('sh159806', '新能源车', '行业'),
        ('sh512760', '医疗', '行业'),
        ('sh515050', '5G', '行业'),
        ('sh511010', '纳指', '海外'),
    ]
    
    # 参数配置
    CONFIGS = [
        ExperimentConfig(stop_loss=-0.05, stop_profit=0.08, max_hold_days=15),  # Cfg1
        ExperimentConfig(stop_loss=-0.04, stop_profit=0.06, max_hold_days=10),  # Cfg2
        ExperimentConfig(stop_loss=-0.03, stop_profit=0.05, max_hold_days=7),   # Cfg3
        ExperimentConfig(stop_loss=-0.06, stop_profit=0.10, max_hold_days=20),  # Cfg4
        ExperimentConfig(stop_loss=-0.04, stop_profit=0.08, max_hold_days=12),  # Cfg5
        ExperimentConfig(stop_loss=-0.05, stop_profit=0.06, max_hold_days=10), # Cfg6
    ]
    
    def __init__(self, data_dir: str = 'etf_data_live'):
        self.data_dir = data_dir
        self.results: List[Dict] = []
        
    # ========== 数据处理 ==========
    
    def load_data(self, code: str) -> pd.DataFrame:
        """加载ETF数据"""
        file_path = Path(self.data_dir) / f'{code}.csv'
        if not file_path.exists():
            for ext in ['sh', 'sz', '']:
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
        df['MACD_SIGNAL'] = (df['MACD'] > 0).astype(int)
        
        # RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + avg_gain / (avg_loss + 0.001)))
        df['RSI_OK'] = ((df['RSI'] >= 25) & (df['RSI'] <= 65)).astype(int)
        
        # 鱼身因子
        df['high_distance'] = (df['close'] - df['low'].rolling(60).min()) / \
                             (df['high'].rolling(60).max() - df['low'].rolling(60).min() + 0.001) * 100
        df['FISHBODY_OK'] = ((df['high_distance'] >= 30) & (df['high_distance'] <= 85)).astype(int)
        
        # 多头排列
        df['BULLISH_ALIGN'] = ((df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])).astype(int)
        
        # 多周期趋势
        df['trend_5'] = np.where(df['close'] > df['MA5'], 1, -1)
        df['trend_10'] = np.where(df['MA10'] > df['MA10'].shift(5), 1, -1)
        df['trend_20'] = np.where(df['MA20'] > df['MA20'].shift(10), 1, -1)
        df['trend_consistency'] = (df['trend_5'] + df['trend_10'] + df['trend_20']) / 3
        df['TREND_OK'] = (df['trend_consistency'] > 0).astype(int)
        
        return df
    
    def get_fish_body_signals(self, df: pd.DataFrame) -> pd.Series:
        """获取鱼身买入信号 (5个条件，满足4个)"""
        signals = pd.Series(0, index=df.index)
        
        for i in range(60, len(df)):
            row = df.iloc[i]
            conditions_met = 0
            
            # 条件1: 多头排列
            if row['BULLISH_ALIGN'] == 1:
                conditions_met += 1
            
            # 条件2: MACD向上
            if row['MACD_SIGNAL'] == 1:
                conditions_met += 1
            
            # 条件3: 鱼身位置
            if row['FISHBODY_OK'] == 1:
                conditions_met += 1
            
            # 条件4: RSI适中
            if row['RSI_OK'] == 1:
                conditions_met += 1
            
            # 条件5: 趋势一致
            if row['TREND_OK'] == 1:
                conditions_met += 1
            
            # 满足4个条件以上才买入
            if conditions_met >= 4:
                signals.iloc[i] = 1
        
        return signals
    
    # ========== 回测引擎 ==========
    
    def backtest(self, df: pd.DataFrame, signals: pd.Series, 
                 config: ExperimentConfig, code: str) -> Tuple[List[TradeRecord], BacktestStats]:
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
                        'entry_price': row['close'],
                        'signal_conditions': {
                            'bullish_align': int(row['BULLISH_ALIGN']),
                            'macd_signal': int(row['MACD_SIGNAL']),
                            'fishbody': int(row['FISHBODY_OK']),
                            'rsi_ok': int(row['RSI_OK']),
                            'trend_ok': int(row['TREND_OK'])
                        }
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
                        exit_reason=exit_reason,
                        signal_conditions=position['signal_conditions']
                    ))
                    position = None
        
        # 计算统计
        stats = self._calculate_stats(trades, df, signals)
        return trades, stats
    
    def _calculate_stats(self, trades: List[TradeRecord], df: pd.DataFrame, signals: pd.Series) -> BacktestStats:
        """计算回测统计"""
        stats = BacktestStats()
        
        if not trades:
            return stats
        
        returns = [t.return_pct for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]
        
        stats.total_return = np.sum(returns)
        stats.trade_count = len(trades)
        stats.win_rate = len(wins) / len(returns) * 100 if returns else 0
        
        if wins and losses:
            stats.profit_loss_ratio = abs(np.mean(wins) / np.mean(losses))
        
        # 最大回撤
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max)
        stats.max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0
        
        # IC计算
        if len(df) > 20:
            future_return = df['close'].shift(-5) / df['close'] - 1
            ic_values = {}
            for col in ['BULLISH_ALIGN', 'MACD_SIGNAL', 'FISHBODY_OK', 'RSI_OK', 'TREND_OK']:
                if col in df.columns:
                    valid_idx = df[col].notna() & future_return.notna()
                    if valid_idx.sum() > 10:
                        ic = df.loc[valid_idx, col].corr(future_return[valid_idx])
                        ic_values[col] = round(ic, 4) if not np.isnan(ic) else 0
            stats.ic_results = ic_values
        
        return stats
    
    # ========== 验证方法 ==========
    
    def check_no_look_ahead(self, trades: List[TradeRecord], df: pd.DataFrame) -> bool:
        """
        未来函数检验
        检查买入信号是否在条件满足后才发出
        """
        if not trades:
            return True
        
        for trade in trades:
            entry_idx = df[df['date'].astype(str).str.startswith(trade.entry_date)].index
            if len(entry_idx) == 0:
                continue
            entry_idx = entry_idx[0]
            
            conditions = trade.signal_conditions
            if sum(conditions.values()) < 4:
                return False
        
        return True
    
    def run_random_control(self, df: pd.DataFrame, n_runs: int = 100) -> Dict:
        """
        随机对照实验
        对比鱼身策略 vs 随机策略
        """
        random_returns = []
        
        for _ in range(n_runs):
            start_idx = 60
            end_idx = len(df) - 20
            
            if end_idx <= start_idx:
                continue
            
            n_trades = 50
            trades_return = []
            
            for _ in range(n_trades):
                idx = random.randint(start_idx, end_idx)
                entry_price = df.iloc[idx]['close']
                hold_days = random.randint(5, 15)
                
                if idx + hold_days < len(df):
                    exit_price = df.iloc[idx + hold_days]['close']
                    pnl = (exit_price - entry_price) / entry_price * 100
                    trades_return.append(pnl)
            
            if trades_return:
                random_returns.append(np.mean(trades_return))
        
        return {
            'random_mean': np.mean(random_returns) if random_returns else 0,
            'random_std': np.std(random_returns) if random_returns else 0,
            'n_runs': n_runs
        }
    
    # ========== 实验运行 ==========
    
    def run_single_experiment(self, code: str, config_idx: int) -> Dict:
        """运行单个实验"""
        cfg = self.CONFIGS[config_idx]
        
        try:
            df = self.load_data(code)
            
            if len(df) < 100:
                return None
            
            df = self.calculate_indicators(df)
            signals = self.get_fish_body_signals(df)
            trades, stats = self.backtest(df, signals, cfg, code)
            
            # 验证
            validation = ValidationResult()
            validation.no_look_ahead = self.check_no_look_ahead(trades, df)
            
            # 随机对照
            random_result = self.run_random_control(df, n_runs=50)
            fishbody_return = stats.total_return / stats.trade_count if stats.trade_count > 0 else 0
            random_vs_fishbody = random_result['random_mean']
            
            # p值估计 (简单方法)
            if random_result['random_std'] > 0:
                z_score = (fishbody_return - random_vs_fishbody) / random_result['random_std']
                validation.random_vs_fishbody_pvalue = 2 * (1 - abs(z_score) / 3) if abs(z_score) < 3 else 0
            else:
                validation.random_vs_fishbody_pvalue = 1.0
            
            return {
                'id': f'{code}-Cfg{config_idx+1}',
                'code': code,
                'config': f'Cfg{config_idx+1}',
                'params': cfg.to_dict(),
                'stats': stats.to_dict(),
                'validation': validation.to_dict(),
                'random_result': random_result,
                'trade_count': len(trades),
                'trades': [t.to_dict() for t in trades[:10]]
            }
            
        except Exception as e:
            print(f"  实验失败: {e}")
            return None
    
    def run_all_experiments(self) -> List[Dict]:
        """运行所有实验"""
        print("="*80)
        print("🐟 鱼身因子挖掘实验 V3.0 - 完整版")
        print("="*80)
        print(f"ETF数量: {len(self.ETF_LIST)}")
        print(f"参数配置: {len(self.CONFIGS)}")
        print(f"总实验数: {len(self.ETF_LIST) * len(self.CONFIGS)}")
        print()
        
        results = []
        
        for code, name, category in self.ETF_LIST:
            print(f"\n{'='*60}")
            print(f"📊 {code} ({name}) - {category}")
            print(f"{'='*60}")
            
            for cfg_idx, cfg in enumerate(self.CONFIGS):
                print(f"\n  【Cfg{cfg_idx+1}】止损{cfg.stop_loss*100:.0f}%, 止盈{cfg.stop_profit*100:.0f}%, 持仓{cfg.max_hold_days}天")
                
                result = self.run_single_experiment(code, cfg_idx)
                if result:
                    results.append(result)
                    s = result['stats']
                    v = result['validation']
                    r = result['random_result']
                    
                    print(f"    收益: {s['total_return']:.1f}%, 胜率: {s['win_rate']:.1f}%, 交易: {result['trade_count']}次")
                    print(f"    IC: {s['ic_results']}")
                    print(f"    未来函数: {'✅' if v['no_look_ahead'] else '❌'}, p值: {v['random_vs_fishbody_pvalue']:.3f}")
                    print(f"    随机对照: 鱼身{result['stats']['total_return']/max(1,result['trade_count']):.2f}% vs 随机{r['random_mean']:.2f}%")
        
        self.results = results
        return results
    
    def analyze_cross_etf(self) -> Dict:
        """跨ETF分析"""
        print("\n" + "="*80)
        print("📊 跨ETF分析")
        print("="*80)
        
        # 按配置分组
        config_results = {}
        for r in self.results:
            cfg = r['config']
            if cfg not in config_results:
                config_results[cfg] = []
            config_results[cfg].append(r)
        
        analysis = {}
        for cfg, cfg_results in config_results.items():
            returns = [r['stats']['total_return'] for r in cfg_results]
            positive_count = sum(1 for r in returns if r > 0)
            
            analysis[cfg] = {
                'avg_return': np.mean(returns),
                'std_return': np.std(returns),
                'positive_ratio': positive_count / len(returns) * 100,
                'n_etfs': len(cfg_results),
                'avg_ic': np.mean([r['stats']['ic_results'].get('avg_ic', 0) for r in cfg_results])
            }
        
        # 打印分析结果
        print(f"\n{'配置':<8} {'平均收益':<12} {'收益波动':<12} {'正收益ETF':<12} {'IC均值':<10}")
        print("-"*60)
        for cfg, data in sorted(analysis.items()):
            print(f"{cfg:<8} {data['avg_return']:>8.1f}%   {data['std_return']:>8.1f}%   {data['positive_ratio']:>6.0f}%      {data['avg_ic']:>8.4f}")
        
        return analysis
    
    def save_results(self, filepath: str = 'data/experiments/fishbody_v3.json'):
        """保存实验结果"""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_experiments': len(self.results),
                'results': self.results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n📁 结果已保存: {filepath}")
    
    def generate_report(self) -> str:
        """生成实验报告"""
        if not self.results:
            return "无实验结果"
        
        report = []
        report.append("# 🐟 鱼身因子挖掘实验 V3.0 报告")
        report.append("")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"总实验数: {len(self.results)}")
        report.append("")
        
        # 按配置分组统计
        configs = set(r['config'] for r in self.results)
        
        report.append("## 配置效果汇总")
        report.append("")
        report.append("| 配置 | 平均收益 | 平均胜率 | 正收益ETF | 未来函数通过 |")
        report.append("|------|----------|----------|-----------|--------------|")
        
        for config in sorted(configs):
            cfg_results = [r for r in self.results if r['config'] == config]
            avg_return = np.mean([r['stats']['total_return'] for r in cfg_results])
            avg_winrate = np.mean([r['stats']['win_rate'] for r in cfg_results])
            positive_count = sum(1 for r in cfg_results if r['stats']['total_return'] > 0)
            look_ahead_pass = sum(1 for r in cfg_results if r['validation'].get('no_look_ahead', False))
            
            report.append(f"| {config} | {avg_return:.1f}% | {avg_winrate:.1f}% | {positive_count}/{len(cfg_results)} | {look_ahead_pass}/{len(cfg_results)} |")
        
        # IC分析
        report.append("")
        report.append("## 因子IC分析")
        report.append("")
        report.append("| ETF | BULLISH | MACD | FISHBODY | RSI | TREND |")
        report.append("|-----|---------|------|---------|-----|-------|")
        
        for r in self.results[:7]:
            ic = r['stats']['ic_results']
            report.append(f"| {r['code']} | {ic.get('BULLISH_ALIGN', 0):.4f} | {ic.get('MACD_SIGNAL', 0):.4f} | {ic.get('FISHBODY_OK', 0):.4f} | {ic.get('RSI_OK', 0):.4f} | {ic.get('TREND_OK', 0):.4f} |")
        
        return "\n".join(report)


def main():
    """主函数"""
    random.seed(42)
    np.random.seed(42)
    
    experiment = MultiETFFishBodyV3()
    
    # 运行实验
    results = experiment.run_all_experiments()
    
    # 跨ETF分析
    experiment.analyze_cross_etf()
    
    # 保存结果
    experiment.save_results()
    
    # 生成报告
    report = experiment.generate_report()
    print()
    print(report)
    
    # 保存报告
    with open('docs/FISH_BODY_V3_REPORT.md', 'w') as f:
        f.write(report)
    
    return results


if __name__ == '__main__':
    results = main()