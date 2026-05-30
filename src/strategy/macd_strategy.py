#!/usr/bin/env python3
"""
MACD红柱策略信号生成器
====================
基于10轮实验验证的最优策略：
- 入场条件：(macd_hist > 0) & (return_3d > 0) & 大盘多头
- 止损：-6%
- 止盈：12%
- 最大持仓：5天
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sqlite3

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import ETFListLoader
from src.data.loader import DataLoader
from src.utils.logger import get_logger

logger = get_logger()


class MACDStrategy:
    """MACD红柱策略"""
    
    # 参数（基于实验优化）
    STOP_LOSS = -0.06      # 止损6%
    STOP_PROFIT = 0.12     # 止盈12%
    MAX_HOLD_DAYS = 5      # 最大持仓5天
    MARKET_CODE = '510300' # 大盘ETF
    
    def __init__(self):
        self.pool_loader = ETFListLoader()
        self.data_loader = DataLoader()
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.market_data: Optional[pd.DataFrame] = None
        self._load_data()
    
    def _load_data(self):
        """加载数据"""
        logger.info("加载ETF数据...")
        
        self.etf_data = self.data_loader.load(min_rows=100)
        
        # 过滤时间
        for code in list(self.etf_data.keys()):
            df = self.etf_data[code]
            df = df.sort_values('date').reset_index(drop=True)
            df['date'] = pd.to_datetime(df['date'])
            self.etf_data[code] = df
        
        # 加载大盘数据
        if self.MARKET_CODE in self.etf_data:
            self.market_data = self.etf_data[self.MARKET_CODE].copy()
        
        logger.info(f"加载了 {len(self.etf_data)} 只ETF数据")
    
    def _add_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加技术指标"""
        df = df.copy()
        
        # MA
        for n in [5, 10, 20, 60]:
            df[f'ma{n}'] = df['close'].rolling(n).mean()
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['dif'] = ema12 - ema26
        df['dea'] = df['dif'].ewm(span=9).mean()
        df['macd_hist'] = (df['dif'] - df['dea']) * 2
        
        # 动量
        df['return_3d'] = df['close'].pct_change(3)
        
        return df
    
    def _is_market_bullish(self, date: pd.Timestamp) -> bool:
        """判断大盘是否多头"""
        if self.market_data is None:
            return True
        
        # 添加因子
        self.market_data = self._add_factors(self.market_data)
        
        df_before = self.market_data[self.market_data['date'] <= date]
        if len(df_before) < 60:
            return True
        
        latest = df_before.iloc[-1]
        
        # 检查是否有必要的列
        if 'ma20' not in latest or 'ma60' not in latest:
            return True
        
        return (
            latest['close'] > latest['ma20'] and
            latest['close'] > latest['ma60'] and
            latest['ma20'] > latest['ma60']
        )
    
    def check_entry(self, code: str, date: Optional[pd.Timestamp] = None) -> Tuple[bool, str]:
        """
        检查是否满足入场条件
        返回：(是否入场, 原因)
        """
        if code not in self.etf_data:
            return False, "无数据"
        
        df = self.etf_data[code]
        df = self._add_factors(df)
        
        if date is None:
            date = df['date'].max()
        else:
            df = df[df['date'] <= date]
        
        if len(df) < 20:
            return False, "数据不足"
        
        latest = df.iloc[-1]
        
        # 检查大盘
        if not self._is_market_bullish(date):
            return False, f"大盘({self.MARKET_CODE})非多头"
        
        # 检查入场条件
        macd_ok = latest['macd_hist'] > 0
        momentum_ok = latest['return_3d'] > 0
        
        if macd_ok and momentum_ok:
            return True, f"MACD={latest['macd_hist']:.4f}, 3日动量={latest['return_3d']:.2%}"
        elif macd_ok:
            return False, f"MACD红柱但3日动量={latest['return_3d']:.2%}<0"
        elif momentum_ok:
            return False, f"3日动量正但MACD={latest['macd_hist']:.4f}<0"
        else:
            return False, f"MACD={latest['macd_hist']:.4f}, 3日动量={latest['return_3d']:.2%}"
    
    def get_signals(self, target_codes: Optional[List[str]] = None) -> List[Dict]:
        """
        获取当前信号
        返回：[{code, name, signal, reason, score}, ...]
        """
        # 默认使用目标ETF池
        if target_codes is None:
            target_codes = self.pool_loader.load()
            # 排除510300
            target_codes = [c for c in target_codes if c != self.MARKET_CODE]
        
        signals = []
        market_ok = self._is_market_bullish(pd.Timestamp.now())
        
        for code in target_codes:
            if code not in self.etf_data:
                continue
            
            df = self.etf_data[code]
            latest = df.iloc[-1]
            
            entry_ok, reason = self.check_entry(code)
            
            # 计算信号强度
            df = self._add_factors(df)
            latest = df.iloc[-1]
            
            signal_strength = 0
            if latest['macd_hist'] > 0:
                signal_strength += 50
            if latest['return_3d'] > 0:
                signal_strength += 30
            if latest['close'] > latest['ma20']:
                signal_strength += 10
            if latest['close'] > latest['ma60']:
                signal_strength += 10
            
            signals.append({
                'code': code,
                'name': latest.get('name', code),
                'signal': 'BUY' if entry_ok else 'WAIT',
                'reason': reason,
                'score': signal_strength if entry_ok else 0,
                'macd_hist': latest.get('macd_hist', 0),
                'return_3d': latest.get('return_3d', 0),
                'date': str(latest['date'].date()) if hasattr(latest['date'], 'date') else str(latest['date']),
                'market_ok': market_ok,
                'strategy': 'MACD红柱+动量3'
            })
        
        # 按信号强度排序
        signals.sort(key=lambda x: x['score'], reverse=True)
        
        return signals
    
    def run_backtest(self, code: str, start_date: str = '2024-05-01', 
                     end_date: str = '2026-05-29') -> Dict:
        """运行回测"""
        if code not in self.etf_data:
            return {}
        
        df = self.etf_data[code]
        df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        df = self._add_factors(df)
        
        trades = []
        position = None
        entry_date = None
        entry_price = None
        
        for _, row in df.iterrows():
            if position is None:
                # 检查入场
                if row['macd_hist'] > 0 and row['return_3d'] > 0 and self._is_market_bullish(row['date']):
                    position = 'long'
                    entry_date = row['date']
                    entry_price = row['close']
            else:
                hold_days = (row['date'] - entry_date).days
                pnl = (row['close'] - entry_price) / entry_price
                
                if pnl <= self.STOP_LOSS or pnl >= self.STOP_PROFIT or hold_days >= self.MAX_HOLD_DAYS:
                    reason = "止损" if pnl <= self.STOP_LOSS else ("止盈" if pnl >= self.STOP_PROFIT else "到期")
                    trades.append({
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'exit_date': row['date'],
                        'exit_price': row['close'],
                        'pnl': pnl,
                        'hold_days': hold_days,
                        'reason': reason
                    })
                    position = None
        
        # 汇总
        if trades:
            total_return = sum(t['pnl'] for t in trades)
            win_count = len([t for t in trades if t['pnl'] > 0])
            
            return {
                'code': code,
                'total_return': total_return,
                'trade_count': len(trades),
                'win_rate': win_count / len(trades),
                'avg_hold_days': np.mean([t['hold_days'] for t in trades]),
                'best_trade': max(t['pnl'] for t in trades),
                'worst_trade': min(t['pnl'] for t in trades)
            }
        
        return {'code': code, 'total_return': 0, 'trade_count': 0}


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("MACD红柱策略信号生成器")
    logger.info("=" * 60)
    
    strategy = MACDStrategy()
    
    # 获取当前信号
    logger.info("\n当前信号：")
    signals = strategy.get_signals()
    
    if not signals:
        logger.info("无信号")
        return
    
    # 打印买入信号
    buy_signals = [s for s in signals if s['signal'] == 'BUY']
    wait_signals = [s for s in signals if s['signal'] == 'WAIT']
    
    logger.info(f"\n大盘状态：{'多头' if signals[0]['market_ok'] else '空头'}")
    logger.info(f"\n买入信号（{len(buy_signals)}只）：")
    print("-" * 80)
    
    if buy_signals:
        print(f"{'代码':<8} {'名称':<15} {'MACD':<10} {'3日动量':<10} {'信号分':<8}")
        print("-" * 80)
        for s in buy_signals[:10]:
            print(f"{s['code']:<8} {s['name']:<15} {s['macd_hist']:<10.4f} {s['return_3d']:<10.2%} {s['score']:>8}")
    else:
        print("无买入信号")
    
    logger.info(f"\n等待信号（{len(wait_signals)}只）：")
    for s in wait_signals[:5]:
        print(f"  {s['code']}: {s['reason']}")
    
    # 打印策略参数
    logger.info("\n" + "=" * 60)
    logger.info("策略参数")
    logger.info("=" * 60)
    logger.info(f"止损：{strategy.STOP_LOSS:.0%}")
    logger.info(f"止盈：{strategy.STOP_PROFIT:.0%}")
    logger.info(f"最大持仓：{strategy.MAX_HOLD_DAYS}天")
    logger.info(f"大盘过滤：{strategy.MARKET_CODE}收盘>MA20>MA60")


if __name__ == '__main__':
    main()