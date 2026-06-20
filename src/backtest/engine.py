"""
因子回测引擎 v8.0

【三个一致性】
1. 工具调用一致：DataLoader + IndicatorCalculator + RelativeCalculator + FactorBacktester
2. 执行流程一致：信号生成 → 回测 → 评价
3. 评价标准一致：8核心指标

【核心改进】
- T+1开盘价成交：避免look-ahead bias
- 持仓管理：避免重复买入
- min_hold_days：止盈需满足最小持仓
- 相对收益：计算与大盘的相对收益

参考来源：
- Backtrader交易执行模型
- Zipline收益计算
- FMZ量化最佳实践
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field


# ============================================================
# 配置
# ============================================================

@dataclass
class BacktestConfig:
    """回测配置"""
    # 止盈止损
    stop_loss: float = -0.04         # 止损4%
    stop_profit: float = 0.06         # 止盈6%
    
    # 持仓管理
    min_hold_days: int = 3           # 最小持仓3天
    max_hold_days: int = 20          # 最大持仓20天
    max_positions: int = 2           # 最大同时持仓2只
    
    # 成本
    commission_rate: float = 0.0003   # 佣金0.03%
    slippage_rate: float = 0.0002    # 滑点0.02%
    
    # 信号模式（兼容旧接口）
    min_score: float = 0.6           # 最小评分
    min_factors: int = 2             # 最小因子数


@dataclass
class BacktestResult:
    """回测结果"""
    # 收益
    total_return: float = 0.0
    relative_return: float = 0.0
    annual_return: float = 0.0
    
    # 风险
    max_drawdown: float = 0.0
    daily_volatility: float = 0.0
    
    # 风险调整
    sharpe_relative: float = 0.0
    calmar_ratio: float = 0.0
    
    # 交易
    win_rate: float = 0.0
    trade_count: int = 0
    annual_trades: float = 0.0
    
    # 盈亏
    profit_loss_ratio: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    
    # 详情
    trades: List[Dict] = field(default_factory=list)


# ============================================================
# 回测引擎
# ============================================================

class FactorBacktester:
    """因子回测引擎 v8.0"""
    
    def __init__(
        self,
        factors: List[str] = None,
        weights: Dict[str, float] = None,
        factor_direction: Dict[str, str] = None,
        config: BacktestConfig = None
    ):
        """
        初始化
        
        Args:
            factors: 因子列表
            weights: 因子权重
            factor_direction: 因子方向
            config: 回测配置
        """
        self.factors = factors or []
        self.weights = weights or {}
        self.factor_direction = factor_direction or {}
        self.config = config or BacktestConfig()
    
    def backtest(
        self,
        price_data: Dict[str, pd.DataFrame],
        signal_func: Callable[[pd.DataFrame], pd.Series] = None,
        score_func: Callable[[pd.DataFrame], pd.Series] = None,
        benchmark_data: pd.DataFrame = None,
        start_date: str = None,
        end_date: str = None,
        valid_factors: List[str] = None,
    ) -> BacktestResult:
        """
        统一回测入口
        
        Args:
            price_data: ETF数据 {code: df}
            signal_func: 信号函数（AND组合模式）
            score_func: 评分函数（评分模式，兼容旧接口）
            benchmark_data: 大盘基准数据
            start_date: 开始日期
            end_date: 结束日期
            valid_factors: 有效因子列表（评分模式用）
        
        Returns:
            BacktestResult: 回测结果
        """
        trades = []
        positions = {}  # 持仓管理 {code: pos_info}
        closed_today = set()  # 当日已平仓的ETF（防止同日再买入）
        
        # 1. 日期对齐
        all_dates = self._get_trading_dates(price_data, start_date, end_date)
        if len(all_dates) < 2:
            return BacktestResult()
        
        # 2. 准备基准数据
        benchmark_prices = self._prepare_benchmark(benchmark_data) if benchmark_data is not None else {}
        
        # 3. 主循环
        for i, current_date in enumerate(all_dates[:-1]):  # 最后一天不平仓
            current_prices = self._get_current_prices(price_data, current_date)
            if not current_prices:
                continue
            
            # 重置当日已平仓记录
            closed_today.clear()
            
            # === 平仓检查 ===
            for code in list(positions.keys()):
                pos = positions[code]
                current_price = current_prices.get(code, {}).get('close', pos['entry_price'])
                
                if current_price == 0:
                    current_price = pos['entry_price']
                
                # 检查是否需要平仓
                should_close, reason = self._check_exit(pos, current_price, current_date)
                
                if should_close:
                    # T+1开盘价成交
                    next_date = all_dates[i + 1]
                    next_prices = self._get_current_prices(price_data, next_date)
                    exit_price = next_prices.get(code, {}).get('open', current_price)
                    
                    # 计算收益（含成本）
                    trade = self._create_trade(
                        pos, code, current_date, next_date,
                        current_price, exit_price, reason
                    )
                    
                    # 计算相对收益
                    if benchmark_prices:
                        trade['relative_return'] = self._calculate_relative_return(
                            trade, benchmark_prices, price_data.get(code)
                        )
                    
                    trades.append(trade)
                    del positions[code]
                    closed_today.add(code)  # 标记为当日已平仓
            
            # === 开仓检查 ===
            if len(positions) < self.config.max_positions:
                # 获取候选ETF
                candidates = self._get_candidates(
                    current_date, current_prices, positions, 
                    signal_func, score_func,
                    price_data, valid_factors
                )
                
                for code, score in candidates:
                    # 检查：不在持仓中，不在当日已平仓中
                    if self._can_open(code, positions) and code not in closed_today:
                        # T+1开盘价买入
                        next_date = all_dates[i + 1]
                        next_prices = self._get_current_prices(price_data, next_date)
                        entry_price = next_prices.get(code, {}).get('open', 
                                                                   current_prices.get(code, {}).get('close', 0))
                        
                        if entry_price > 0:
                            positions[code] = {
                                'entry_price': entry_price,
                                'entry_date': next_date,
                                'entry_signal_date': current_date,
                                'entry_score': score,
                                'hold_days': 0,
                                'concurrent_positions': len(positions) + 1,
                            }
                            
                            if len(positions) >= self.config.max_positions:
                                break
            
            # === 持仓天数+1 ===
            for pos in positions.values():
                pos['hold_days'] += 1
        
        # 4. 期末平仓
        if all_dates and positions:
            final_date = all_dates[-1]
            for code, pos in positions.items():
                # 期末以收盘价平仓
                last_df = price_data.get(code)
                if last_df is not None:
                    last_row = last_df[last_df['date'] == final_date]
                    if not last_row.empty:
                        exit_price = last_row.iloc[0]['close']
                        trade = self._create_trade(
                            pos, code, pos['entry_date'], final_date,
                            pos['entry_price'], exit_price, '期末平仓'
                        )
                        if benchmark_prices:
                            trade['relative_return'] = self._calculate_relative_return(
                                trade, benchmark_prices, price_data.get(code)
                            )
                        trades.append(trade)
        
        # 5. 计算指标
        return self._calculate_metrics(trades, start_date, end_date, benchmark_prices)
    
    def _get_trading_dates(
        self, 
        price_data: Dict[str, pd.DataFrame], 
        start_date: str, 
        end_date: str
    ) -> List[str]:
        """获取交易日列表"""
        all_dates = set()
        for df in price_data.values():
            if 'date' in df.columns:
                all_dates.update(df['date'].tolist())
        
        dates = sorted([d for d in all_dates if d and 
                       (start_date is None or d >= start_date) and 
                       (end_date is None or d <= end_date)])
        return dates
    
    def _get_current_prices(
        self, 
        price_data: Dict[str, pd.DataFrame], 
        date: str
    ) -> Dict[str, Dict]:
        """获取当日行情"""
        prices = {}
        for code, df in price_data.items():
            day_data = df[df['date'] == date]
            if not day_data.empty:
                row = day_data.iloc[0]
                prices[code] = {
                    'open': row.get('open', row.get('close', 0)),
                    'close': row.get('close', 0),
                    'high': row.get('high', row.get('close', 0)),
                    'low': row.get('low', row.get('close', 0)),
                }
        return prices
    
    def _prepare_benchmark(self, benchmark_df: pd.DataFrame) -> Dict[str, float]:
        """准备基准价格序列"""
        prices = {}
        if 'date' in benchmark_df.columns:
            for _, row in benchmark_df.iterrows():
                prices[row['date']] = row.get('close', 0)
        return prices
    
    def _check_exit(
        self, 
        pos: Dict, 
        current_price: float,
        current_date: str
    ) -> Tuple[bool, str]:
        """
        检查是否需要平仓
        
        止盈止损逻辑（业界最佳实践）：
        1. 止损：任何时候触发，优先保护本金
        2. 止盈：需满足min_hold_days，避免频繁交易
        3. 到期：达到max_hold_days强制平仓
        """
        pnl_pct = (current_price / pos['entry_price']) - 1
        hold_days = pos['hold_days']
        
        # 1. 止损（最高优先级）
        if pnl_pct <= self.config.stop_loss:
            return True, '止损'
        
        # 2. 止盈（需满足最小持仓天数）
        if hold_days >= self.config.min_hold_days:
            if pnl_pct >= self.config.stop_profit:
                return True, '止盈'
        
        # 3. 到期（最低优先级）
        if hold_days >= self.config.max_hold_days:
            return True, '到期'
        
        return False, ''
    
    def _can_open(self, code: str, positions: Dict) -> bool:
        """检查是否可以开仓"""
        return code not in positions
    
    def _get_candidates(
        self,
        current_date: str,
        current_prices: Dict[str, Dict],
        positions: Dict,
        signal_func: Callable,
        score_func: Callable,
        price_data: Dict[str, pd.DataFrame],
        valid_factors: List[str],
    ) -> List[Tuple[str, float]]:
        """
        获取候选ETF
        
        Returns:
            [(code, score), ...] 按评分降序
        """
        candidates = []
        
        for code in current_prices.keys():
            if code in positions:
                continue
            
            # 信号模式
            if signal_func is not None:
                df = price_data.get(code)
                if df is not None and not df.empty:
                    # 使用current_date直接筛选
                    today_data = df[df['date'] == current_date]
                    if not today_data.empty:
                        signal = signal_func(today_data)
                        if len(signal) > 0 and signal.iloc[-1]:
                            candidates.append((code, 1.0))
            
            # 评分模式（兼容旧接口）
            elif score_func is not None and valid_factors:
                df = price_data.get(code)
                if df is not None and not df.empty:
                    today_data = df[df['date'] == current_date]
                    if not today_data.empty:
                        row = today_data.iloc[-1]
                        score = self._calculate_score(row, valid_factors)
                        if score >= self.config.min_score:
                            candidates.append((code, score))
        
        # 按评分排序
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates
    
    def _calculate_score(self, row: pd.Series, valid_factors: List[str]) -> float:
        """计算评分（兼容旧接口）"""
        total_score = 0
        
        for factor in valid_factors:
            if pd.isna(row.get(factor)):
                continue
            
            value = row[factor]
            direction = self.factor_direction.get(factor, 'neutral')
            if direction == 'neutral':
                continue
            
            weight = self.weights.get(factor, 0)
            
            # 简化评分
            if factor == 'ADX':
                score = min(value / 50, 1) if direction == 'long' else min((50 - value) / 50, 1)
            elif factor == 'BB_percent':
                score = min((50 - value) / 50, 1) if direction == 'long' else min(value / 50, 1)
            elif factor == 'SAR_trend':
                score = value if direction == 'long' else (1 - value)
            elif factor == 'RSI_5':
                score = min((50 - value) / 50, 1) if direction == 'long' else min(value / 50, 1)
            elif factor == 'DMA':
                score = 1 if value > 0 else 0
            elif factor == 'MACD_hist':
                score = 1 if value > 0 else 0
            else:
                score = 0.5
            
            score = max(0, min(1, score))
            total_score += score * weight
        
        return total_score
    
    def _create_trade(
        self,
        pos: Dict,
        code: str,
        entry_date: str,
        exit_date: str,
        entry_price: float,
        exit_price: float,
        reason: str,
    ) -> Dict:
        """创建交易记录"""
        # 扣成本
        commission = entry_price * self.config.commission_rate + exit_price * self.config.commission_rate
        slippage = entry_price * self.config.slippage_rate + exit_price * self.config.slippage_rate
        total_cost = commission + slippage
        
        pnl_pct = (exit_price - entry_price) / entry_price - (total_cost / entry_price)
        
        return {
            'code': code,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'hold_days': pos['hold_days'],
            'exit_reason': reason,
            'entry_score': pos.get('entry_score', 0),
            'concurrent_positions': pos.get('concurrent_positions', 1),
        }
    
    def _calculate_relative_return(
        self,
        trade: Dict,
        benchmark_prices: Dict[str, float],
        etf_df: pd.DataFrame = None,
    ) -> float:
        """计算相对收益"""
        entry_date = trade['entry_date']
        exit_date = trade['exit_date']
        
        entry_bench = benchmark_prices.get(entry_date)
        exit_bench = benchmark_prices.get(exit_date)
        
        if entry_bench and exit_bench and entry_bench > 0:
            benchmark_return = (exit_bench / entry_bench) - 1
            relative_return = trade['pnl_pct'] - benchmark_return
            return relative_return
        
        return 0.0
    
    def _calculate_metrics(
        self,
        trades: List[Dict],
        start_date: str,
        end_date: str,
        benchmark_prices: Dict[str, float] = None,
    ) -> BacktestResult:
        """计算绩效指标"""
        if not trades:
            return BacktestResult()
        
        df = pd.DataFrame(trades)
        df = df.sort_values('exit_date')
        
        # 1. 收益
        total_return = df['pnl_pct'].sum()  # 简单累计
        
        # 2. 相对收益
        if 'relative_return' in df.columns:
            relative_return = df['relative_return'].sum()
        else:
            relative_return = 0.0
        
        # 3. 年化收益
        days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days
        years = max(days / 365, 0.01)
        annual_return = total_return / years if years > 0 else 0
        
        # 4. 最大回撤
        cumulative = df['pnl_pct'].cumsum()
        peak = cumulative.expanding().max()
        drawdown = cumulative - peak
        max_drawdown = abs(drawdown.min()) if drawdown.min() < 0 else 0
        
        # 5. Calmar比率
        calmar_ratio = annual_return / max_drawdown if max_drawdown > 0 else 0
        
        # 6. 日波动率
        daily_volatility = df['pnl_pct'].std() if len(df) > 1 else 0
        
        # 7. 夏普比率（相对）
        if df['pnl_pct'].std() > 0:
            sharpe = df['pnl_pct'].mean() / df['pnl_pct'].std() * np.sqrt(252)
        else:
            sharpe = 0
        
        # 8. 胜率
        wins = df[df['pnl_pct'] > 0]
        win_rate = len(wins) / len(df) if len(df) > 0 else 0
        
        # 9. 盈亏比
        avg_profit = wins['pnl_pct'].mean() if len(wins) > 0 else 0
        losses = df[df['pnl_pct'] < 0]
        avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else 0
        
        # 10. 交易频率
        annual_trades = len(df) / years if years > 0 else 0
        
        return BacktestResult(
            total_return=total_return,
            relative_return=relative_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            daily_volatility=daily_volatility,
            sharpe_relative=sharpe,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            trade_count=len(df),
            annual_trades=annual_trades,
            profit_loss_ratio=profit_loss_ratio,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            trades=trades,
        )


# ============================================================
# 工厂函数
# ============================================================

def create_backtester(config: BacktestConfig = None) -> FactorBacktester:
    """创建回测器（便捷函数）"""
    return FactorBacktester(config=config)


# ============================================================
# 兼容旧接口
# ============================================================

class FactorBacktesterLegacy(FactorBacktester):
    """兼容旧接口的回测器"""
    
    def backtest(self, price_data: Dict, start_date: str, end_date: str, valid_factors: List[str]) -> BacktestResult:
        """旧接口：使用评分模式"""
        # 构造一个默认评分函数
        def default_score_func(df):
            return pd.Series(1.0, index=df.index)
        
        return super().backtest(
            price_data=price_data,
            score_func=default_score_func,
            start_date=start_date,
            end_date=end_date,
            valid_factors=valid_factors,
            benchmark_data=None,
        )