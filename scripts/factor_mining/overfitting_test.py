#!/usr/bin/env python3
"""
过拟合检验与鲁棒性分析
"""
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class OverfittingResult:
    test_name: str = ""
    passed: bool = False
    details: dict = None
    
    def to_dict(self) -> dict:
        return asdict(self)


class OverfittingTester:
    """过拟合检验器"""
    
    START_DATE = '2021-05-01'
    END_DATE = '2026-05-29'
    TRAIN_END = '2024-05-01'
    TEST_START = '2024-05-01'
    
    def __init__(self):
        self.pool_loader = ETFListLoader()
        self.data_loader = DataLoader()
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.market_data = None
        
    def load_data(self):
        """加载数据"""
        logger.info("加载ETF数据...")
        self.etf_data = self.data_loader.load(min_rows=200)
        
        for code in list(self.etf_data.keys()):
            df = self.etf_data[code]
            df = df[(df['date'] >= self.START_DATE) & (df['date'] <= self.END_DATE)]
            if len(df) < 100:
                del self.etf_data[code]
                continue
            df = df.sort_values('date').reset_index(drop=True)
            df['date'] = pd.to_datetime(df['date'])
            self.etf_data[code] = df
        
        if '510300' in self.etf_data:
            self.market_data = self.etf_data['510300'].copy()
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
    
    def _add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加因子"""
        df = df.copy()
        
        for n in [20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd_hist'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
        df['macd_hist'] = (df['macd_hist']) * 2
        
        df['return_3d'] = df['close'].pct_change(3)
        
        return df
    
    def _is_market_bullish(self, date: pd.Timestamp) -> bool:
        if self.market_data is None:
            return True
        
        df = self.market_data.copy()
        for n in [20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        df_before = df[df['date'] <= date]
        if len(df_before) < 60:
            return True
        
        latest = df_before.iloc[-1]
        return (
            latest['close'] > latest['ma20'] and
            latest['close'] > latest['ma60'] and
            latest['ma20'] > latest['ma60']
        )
    
    def backtest_single(self, df: pd.DataFrame, start: str, end: str,
                        sl: float, sp: float, mh: int) -> Tuple[float, int]:
        """单次回测"""
        df = self._add_factors(df)
        df = df[(df['date'] >= start) & (df['date'] <= end)]
        
        if len(df) < 50:
            return 0, 0
        
        condition = "(macd_hist > 0) & (return_3d > 0)"
        
        trades = []
        pos, entry_price, entry_date = None, None, None
        
        for _, row in df.iterrows():
            if pos is None:
                try:
                    if eval(condition, {'np': np}, row.to_dict()) and self._is_market_bullish(row['date']):
                        pos, entry_price, entry_date = 'long', row['close'], row['date']
                except:
                    pass
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                if pnl <= sl or pnl >= sp or hold_days >= mh:
                    trades.append(pnl)
                    pos = None
        
        total_return = sum(trades) if trades else 0
        return total_return, len(trades)
    
    def rolling_window_test(self) -> OverfittingResult:
        """滚动窗口验证"""
        logger.info("=" * 60)
        logger.info("滚动窗口验证")
        logger.info("=" * 60)
        
        target_codes = set(self.pool_loader.load())
        window_results = []
        
        # 窗口定义
        windows = [
            ('2021-05-01', '2023-05-01', '2023-05-01', '2024-05-01'),
            ('2022-05-01', '2024-05-01', '2024-05-01', '2025-05-01'),
            ('2023-05-01', '2025-05-01', '2025-05-01', '2026-05-29'),
        ]
        
        for train_start, train_end, test_start, test_end in windows:
            train_returns, test_returns = [], []
            
            for code in target_codes:
                if code not in self.etf_data:
                    continue
                
                df = self.etf_data[code]
                train_ret, _ = self.backtest_single(df, train_start, train_end, -0.06, 0.12, 5)
                test_ret, _ = self.backtest_single(df, test_start, test_end, -0.06, 0.12, 5)
                
                if train_ret != 0:
                    train_returns.append(train_ret)
                if test_ret != 0:
                    test_returns.append(test_ret)
            
            if train_returns and test_returns:
                avg_train = np.mean(train_returns)
                avg_test = np.mean(test_returns)
                decay = (avg_test - avg_train) / abs(avg_train) if avg_train != 0 else 0
                
                window_results.append({
                    'train_period': f"{train_start}~{train_end}",
                    'test_period': f"{test_start}~{test_end}",
                    'train_return': avg_train,
                    'test_return': avg_test,
                    'oos_decay': decay,
                    'passed': abs(decay) < 0.30  # <30% 通过
                })
                
                logger.info(f"窗口 {test_start}~{test_end}: 训练={avg_train:.2%} 测试={avg_test:.2%} 衰减={decay:.2%} {'✅' if abs(decay) < 0.30 else '❌'}")
        
        all_passed = all(w['passed'] for w in window_results)
        
        return OverfittingResult(
            test_name="滚动窗口验证",
            passed=all_passed,
            details={'windows': window_results}
        )
    
    def monte_carlo_test(self, n_simulations: int = 100) -> OverfittingResult:
        """蒙特卡洛随机化检验"""
        logger.info("=" * 60)
        logger.info(f"蒙特卡洛检验（{n_simulations}次模拟）")
        logger.info("=" * 60)
        
        target_codes = list(set(self.pool_loader.load()))
        
        # 真实策略收益
        real_returns = []
        for code in target_codes:
            if code not in self.etf_data:
                continue
            df = self.etf_data[code]
            ret, _ = self.backtest_single(df, '2024-05-01', '2026-05-29', -0.06, 0.12, 5)
            if ret != 0:
                real_returns.append(ret)
        
        real_mean = np.mean(real_returns) if real_returns else 0
        
        # 随机策略收益
        random_returns = []
        np.random.seed(42)
        
        for _ in range(n_simulations):
            sim_returns = []
            
            for code in target_codes:
                if code not in self.etf_data:
                    continue
                
                df = self.etf_data[code].copy()
                df = self._add_factors(df)
                df = df[df['date'] >= '2024-05-01']
                
                if len(df) < 50:
                    continue
                
                # 随机打乱return_3d
                random_returns_series = df['return_3d'].sample(frac=1, replace=False).values
                df['random_return'] = random_returns_series
                
                # 用随机因子测试
                condition = "(macd_hist > 0) & (random_return > 0)"
                
                trades = []
                pos, entry_price = None, None
                
                for _, row in df.iterrows():
                    if pos is None:
                        try:
                            if eval(condition, {'np': np}, row.to_dict()) and self._is_market_bullish(row['date']):
                                pos, entry_price = 'long', row['close']
                        except:
                            pass
                    else:
                        hold_days = 1  # 简化
                        pnl = (row['close'] - entry_price) / entry_price
                        if pnl <= -0.06 or pnl >= 0.12 or hold_days >= 5:
                            trades.append(pnl)
                            pos = None
                
                if trades:
                    sim_returns.append(sum(trades))
            
            if sim_returns:
                random_returns.append(np.mean(sim_returns))
        
        # 计算p-value（真实策略超过随机策略的比例）
        if random_returns:
            p_value = sum(1 for r in random_returns if r >= real_mean) / len(random_returns)
        else:
            p_value = 0
        
        passed = p_value < 0.05
        
        logger.info(f"真实策略收益: {real_mean:.2%}")
        logger.info(f"随机策略平均: {np.mean(random_returns):.2%}")
        logger.info(f"p-value: {p_value:.4f} {'✅ <0.05 通过' if passed else '❌ >0.05 未通过'}")
        
        return OverfittingResult(
            test_name="蒙特卡洛检验",
            passed=passed,
            details={
                'real_mean': real_mean,
                'random_mean': np.mean(random_returns) if random_returns else 0,
                'random_std': np.std(random_returns) if random_returns else 0,
                'p_value': p_value,
                'n_simulations': n_simulations
            }
        )
    
    def parameter_sensitivity_test(self) -> OverfittingResult:
        """参数敏感性分析"""
        logger.info("=" * 60)
        logger.info("参数敏感性分析")
        logger.info("=" * 60)
        
        target_codes = set(self.pool_loader.load())
        
        # 参数网格
        stop_losses = [-0.04, -0.05, -0.06, -0.07, -0.08]
        stop_profits = [0.10, 0.12, 0.14, 0.16]
        max_holds = [4, 5, 6, 7]
        
        results = []
        
        for sl in stop_losses:
            for sp in stop_profits:
                for mh in max_holds:
                    returns = []
                    
                    for code in target_codes:
                        if code not in self.etf_data:
                            continue
                        
                        df = self.etf_data[code]
                        ret, _ = self.backtest_single(df, '2024-05-01', '2026-05-29', sl, sp, mh)
                        if ret != 0:
                            returns.append(ret)
                    
                    if returns:
                        results.append({
                            'sl': sl, 'sp': sp, 'mh': mh,
                            'return': np.mean(returns)
                        })
        
        if not results:
            return OverfittingResult(test_name="参数敏感性", passed=False, details={'error': '无结果'})
        
        # 分析参数±10%变化的影响
        base_return = next((r['return'] for r in results if r['sl'] == -0.06 and r['sp'] == 0.12 and r['mh'] == 5), None)
        
        sensitivity_results = []
        
        for param_name, param_values in [('止损', [-0.05, -0.06, -0.07]), ('止盈', [0.10, 0.12, 0.14]), ('持仓', [4, 5, 6])]:
            param_returns = []
            for r in results:
                if param_name == '止损' and r['sl'] in param_values and r['sp'] == 0.12 and r['mh'] == 5:
                    param_returns.append(r['return'])
                elif param_name == '止盈' and r['sp'] in param_values and r['sl'] == -0.06 and r['mh'] == 5:
                    param_returns.append(r['return'])
                elif param_name == '持仓' and r['mh'] in param_values and r['sl'] == -0.06 and r['sp'] == 0.12:
                    param_returns.append(r['return'])
            
            if param_returns:
                max_ret = max(param_returns)
                min_ret = min(param_returns)
                sensitivity = (max_ret - min_ret) / abs(base_return) if base_return else 0
                sensitivity_results.append({
                    'param': param_name,
                    'max_return': max_ret,
                    'min_return': min_ret,
                    'sensitivity': sensitivity,
                    'passed': sensitivity < 0.30  # <30% 通过
                })
                logger.info(f"{param_name}: 范围={min_ret:.2%}~{max_ret:.2%} 敏感度={sensitivity:.2%} {'✅' if sensitivity < 0.30 else '❌'}")
        
        all_passed = all(s['passed'] for s in sensitivity_results)
        
        return OverfittingResult(
            test_name="参数敏感性",
            passed=all_passed,
            details={'sensitivities': sensitivity_results, 'base_return': base_return}
        )
    
    def run_all(self) -> List[OverfittingResult]:
        """运行所有检验"""
        results = []
        
        results.append(self.rolling_window_test())
        results.append(self.monte_carlo_test(n_simulations=50))
        results.append(self.parameter_sensitivity_test())
        
        return results
    
    def save_results(self, results: List[OverfittingResult]):
        """保存结果"""
        output_dir = PROJECT_ROOT / 'data' / 'experiments'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / 'overfitting_results.json'
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': len(results),
                'passed': sum(1 for r in results if r.passed),
                'all_passed': all(r.passed for r in results)
            },
            'results': [r.to_dict() for r in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"结果已保存: {output_file}")


def main():
    tester = OverfittingTester()
    tester.load_data()
    
    results = tester.run_all()
    tester.save_results(results)
    
    # 汇总
    print("\n" + "=" * 60)
    print("过拟合检验汇总")
    print("=" * 60)
    
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"{r.test_name}: {status}")
    
    all_passed = all(r.passed for r in results)
    print(f"\n总体结论: {'✅ 策略稳健，通过所有检验' if all_passed else '❌ 存在过拟合风险'}")


if __name__ == '__main__':
    main()