"""
因子回测引擎

支持:
- 多因子综合评分
- 止盈止损
- 持仓管理
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class BacktestConfig:
    """回测配置"""
    stop_loss: float = -0.05
    stop_profit: float = 0.10
    min_score: float = 0.6
    hold_days: int = 5
    min_factors: int = 2


@dataclass
class BacktestResult:
    """回测结果"""
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    avg_profit: float
    avg_loss: float
    trade_count: int
    trades: List[Dict]


class FactorBacktester:
    """因子回测引擎"""
    
    def __init__(
        self,
        factors: List[str],
        weights: Dict[str, float],
        factor_direction: Dict[str, str],
        config: BacktestConfig = None
    ):
        self.factors = factors
        self.weights = weights
        self.factor_direction = factor_direction
        self.config = config or BacktestConfig()
    
    def calculate_score(self, row: pd.Series, valid_factors: List[str]) -> Tuple[float, Dict]:
        """计算综合评分"""
        total_score = 0
        factor_scores = {}
        
        for factor in valid_factors:
            if pd.isna(row.get(factor)):
                continue
            
            value = row[factor]
            direction = self.factor_direction.get(factor, 'neutral')
            if direction == 'neutral':
                continue
            
            weight = self.weights.get(factor, 0)
            score = 0
            
            if factor == 'ADX':
                score = min(value / 50, 1) if direction == 'long' else min((50 - value) / 50, 1)
            elif factor == 'BB_percent':
                score = min((50 - value) / 50, 1) if direction == 'long' else min(value / 50, 1)
            elif factor == 'SAR_trend':
                score = value if direction == 'long' else (1 - value)
            elif factor == 'RSI_5':
                score = min((50 - value) / 50, 1) if direction == 'long' else min(value / 50, 1)
            elif factor == 'K':
                score = min((100 - value) / 100, 1) if direction == 'short' else min(value / 100, 1)
            elif factor == 'DIF':
                score = min((value + 1) / 2, 1) if direction == 'short' else min((1 - value) / 2, 1)
            elif factor == 'OBV_diff':
                score = 0.5 - value / 2000 if direction == 'short' else 0.5 + value / 2000
            elif factor == 'DMA':
                score = min((value + 1) / 2, 1) if value >= 0 else min((1 - value) / 2, 1)
            
            score = max(0, min(1, score))
            factor_scores[factor] = score
            total_score += score * weight
        
        return total_score, factor_scores
    
    def backtest(self, price_data: Dict, start_date: str, end_date: str, valid_factors: List[str]) -> BacktestResult:
        """回测"""
        trades = []
        positions = {}
        
        all_dates = set()
        for df in price_data.values():
            all_dates.update(df['date'].tolist())
        sorted_dates = sorted([d for d in all_dates if start_date <= d <= end_date])
        
        for current_date in sorted_dates:
            current_prices = {}
            for code, df in price_data.items():
                day_data = df[df['date'] == current_date]
                if not day_data.empty:
                    current_prices[code] = day_data.iloc[0].to_dict()
            
            if not current_prices:
                continue
            
            # 平仓检查
            for code in list(positions.keys()):
                pos = positions[code]
                current_price = current_prices.get(code, {}).get('close', pos['entry_price'])
                
                if current_price == 0:
                    current_price = pos['entry_price']
                
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                
                should_close = False
                reason = ""
                
                if pnl_pct <= self.config.stop_loss:
                    should_close, reason = True, "止损"
                elif pnl_pct >= self.config.stop_profit:
                    should_close, reason = True, "止盈"
                elif pos['hold_days'] >= self.config.hold_days:
                    should_close, reason = True, "到期"
                
                if should_close:
                    trades.append({
                        'code': code, 'entry_date': pos['entry_date'], 'exit_date': current_date,
                        'entry_price': pos['entry_price'], 'exit_price': current_price,
                        'pnl_pct': pnl_pct, 'hold_days': pos['hold_days'],
                        'exit_reason': reason, 'entry_score': pos['entry_score']
                    })
                    del positions[code]
            
            # 开仓
            if len(positions) < 2:
                scores = [(code, self.calculate_score(pd.Series(row), valid_factors)[0], row['close'])
                          for code, row in current_prices.items() if code not in positions]
                scores.sort(key=lambda x: x[1], reverse=True)
                
                for code, score, close in scores:
                    if score >= self.config.min_score:
                        positions[code] = {'entry_price': close, 'entry_date': current_date,
                                          'entry_score': score, 'hold_days': 0}
                        break
            
            # 持仓天数+1
            for pos in positions.values():
                pos['hold_days'] += 1
        
        # 期末平仓
        if sorted_dates:
            final_date = sorted_dates[-1]
            for code, pos in positions.items():
                last_df = price_data.get(code)
                if last_df is not None:
                    last_row = last_df[last_df['date'] == final_date]
                    exit_price = last_row.iloc[0]['close'] if not last_row.empty else pos['entry_price']
                    pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    trades.append({
                        'code': code, 'entry_date': pos['entry_date'], 'exit_date': final_date,
                        'entry_price': pos['entry_price'], 'exit_price': exit_price,
                        'pnl_pct': pnl_pct, 'hold_days': pos['hold_days'],
                        'exit_reason': '期末平仓', 'entry_score': pos['entry_score']
                    })
        
        return self._calculate_metrics(trades, start_date, end_date)
    
    def _calculate_metrics(self, trades: List, start_date: str, end_date: str) -> BacktestResult:
        """计算绩效"""
        if not trades:
            return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0, [])
        
        df = pd.DataFrame(trades)
        df = df.sort_values('exit_date')
        cumulative = (1 + df['pnl_pct']).cumprod()
        total_return = cumulative.iloc[-1] - 1
        
        days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days
        years = max(days / 365, 0.01)
        annual_return = (1 + total_return) ** (1 / years) - 1
        
        sharpe = df['pnl_pct'].mean() / df['pnl_pct'].std() * np.sqrt(252) if df['pnl_pct'].std() > 0 else 0
        
        peak = cumulative.expanding().max()
        drawdown = (cumulative - peak) / peak
        max_drawdown = abs(drawdown.min()) if drawdown.min() < 0 else 0
        
        wins = df[df['pnl_pct'] > 0]
        win_rate = len(wins) / len(df) if len(df) > 0 else 0
        avg_profit = wins['pnl_pct'].mean() if len(wins) > 0 else 0
        losses = df[df['pnl_pct'] < 0]
        avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else 0
        
        return BacktestResult(
            total_return, annual_return, sharpe, max_drawdown, win_rate,
            profit_loss_ratio, avg_profit, avg_loss, len(trades), trades
        )
    
    def run_backtest(self, db_path: str = "data/etf_factors.db",
                    train_start: str = "2022-01-01", train_end: str = "2024-12-31",
                    test_start: str = "2025-01-01", test_end: str = "2026-05-27") -> Dict:
        """运行回测"""
        from src.data.database import Database
        from src.indicators.wrapper import IndicatorCalculator, calculate_returns
        
        db = Database(db_path)
        calculator = IndicatorCalculator()
        
        stock_info = db.query("SELECT code FROM stock_info")
        codes = [row['code'] for row in stock_info 
                 if row['code'] not in ['behavior_log', 'etf_performance', 'etf_positions', 'etf_trades', 'realtime_cache', 'test_code']]
        
        price_data = {}
        for code in codes:
            df = db.query_df("SELECT code, date, open, high, low, close, volume FROM daily_price WHERE code = ? ORDER BY date", (code,))
            if df.empty or len(df) < 60:
                continue
            df = calculator.calculate_all(df)
            df = calculate_returns(df)
            price_data[code] = df
        
        effective_factors = [f for f, d in self.factor_direction.items() if d != 'neutral']
        results = {}
        
        for period_name, start, end in [('train', train_start, train_end), ('test', test_start, test_end)]:
            print(f"\n📊 {period_name}: {start} ~ {end}")
            result = self.backtest(price_data, start, end, effective_factors)
            results[period_name] = result
            print(f"  收益:{result.total_return:.2%} 年化:{result.annual_return:.2%} 夏普:{result.sharpe_ratio:.2f} "
                  f"回撤:{result.max_drawdown:.2%} 胜率:{result.win_rate:.2%} 盈亏比:{result.profit_loss_ratio:.2f} 交易:{result.trade_count}")
        
        return results