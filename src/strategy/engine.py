"""
统一执行引擎

基于ExperimentConfig配置执行回测
"""
import pandas as pd
from typing import Dict, Optional, Set
from src.strategy.config import ExperimentConfig, FactorStrategy, BacktestConfig
from src.strategy.scorer import FactorScorer
from src.strategy.executor import PositionExecutor
from src.strategy.metrics import BacktestResult, MetricsCalculator


# 排除的非ETF代码
EXCLUDE_CODES = {
    'behavior_log', 'etf_performance', 'etf_positions', 
    'etf_trades', 'realtime_cache', 'test_code'
}


class UniversalExecutor:
    """统一执行引擎"""
    
    def __init__(self, config: ExperimentConfig):
        """
        初始化
        
        Args:
            config: 实验配置
        """
        self.config = config
        self.scorer = FactorScorer(config.factor_strategy)
        self.metrics = MetricsCalculator()
    
    @classmethod
    def from_config(cls, config: ExperimentConfig) -> 'UniversalExecutor':
        """从配置创建"""
        return cls(config)
    
    @classmethod
    def from_dict(cls, config_dict: Dict) -> 'UniversalExecutor':
        """从字典创建"""
        config = ExperimentConfig.from_dict(config_dict)
        return cls(config)
    
    @classmethod
    def from_experiment(cls, exp: Dict) -> 'UniversalExecutor':
        """从实验日志创建"""
        config = ExperimentConfig.from_experiment(exp)
        return cls(config)
    
    def load_data(self, db_path: str = "data/etf_factors.db") -> Dict[str, pd.DataFrame]:
        """
        加载数据
        
        Args:
            db_path: 数据库路径
            
        Returns:
            {code: df} 价格数据
        """
        from src.data.database import Database
        from src.indicators.wrapper import IndicatorCalculator, calculate_returns
        
        db = Database(db_path)
        calculator = IndicatorCalculator()
        
        # 获取ETF列表
        stock_info = db.query("SELECT code FROM stock_info")
        codes = [row['code'] for row in stock_info 
                 if row['code'] not in EXCLUDE_CODES]
        
        price_data = {}
        for code in codes:
            df = db.query_df(
                "SELECT code, date, open, high, low, close, volume FROM daily_price WHERE code = ? ORDER BY date",
                (code,)
            )
            if df.empty or len(df) < 60:
                continue
            
            # 计算指标
            df = calculator.calculate_all(df)
            df = calculate_returns(df)
            price_data[code] = df
        
        return price_data
    
    def select_top_etfs(self, price_data: Dict[str, pd.DataFrame], top_n: int = 30) -> Set[str]:
        """
        根据训练期收益选出TopN的ETF
        
        Args:
            price_data: 价格数据
            top_n: 选出数量
            
        Returns:
            选中的ETF代码集合
        """
        results = []
        
        for code, df in price_data.items():
            # 检查训练期数据是否足够完整 (>200天)
            d = df[(df['date'] >= self.config.data.train_start) & 
                   (df['date'] <= self.config.data.train_end)]
            
            if len(d) < 200:
                continue
            
            # 计算训练期收益率
            ret = (d.iloc[-1]['close'] / d.iloc[0]['close']) - 1
            results.append({'code': code, 'return': ret})
        
        results.sort(key=lambda x: -x['return'])
        return {r['code'] for r in results[:top_n]}
    
    def run(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, BacktestResult]:
        """
        执行回测
        
        Args:
            price_data: 价格数据
            
        Returns:
            {period: result}
        """
        # 先选出训练期表现最好的ETF
        top_etfs = self.select_top_etfs(price_data, top_n=30)
        
        results = {}
        for period_name, start, end in [
            ('train', self.config.data.train_start, self.config.data.train_end),
            ('test', self.config.data.test_start, self.config.data.test_end)
        ]:
            result = self._run_period(price_data, start, end, period_name, top_etfs)
            results[period_name] = result
        
        return results
    
    def _run_period(
        self, 
        price_data: Dict[str, pd.DataFrame],
        start_date: str,
        end_date: str,
        period: str,
        top_etfs: Optional[Set[str]] = None
    ) -> BacktestResult:
        """执行单个周期"""
        # 重置执行器
        executor = PositionExecutor(self.config.backtest)
        
        # 获取交易日
        all_dates = set()
        for df in price_data.values():
            all_dates.update(df['date'].tolist())
        sorted_dates = sorted([d for d in all_dates if start_date <= d <= end_date])
        
        if not sorted_dates:
            return self.metrics.calculate([], start_date, end_date, 
                                         self.config.id, period)
        
        # 主循环
        for current_date in sorted_dates:
            # 获取当日数据
            current_prices = {}
            current_rows = {}
            for code, df in price_data.items():
                # 过滤不在top_etfs中的ETF
                if top_etfs and code not in top_etfs:
                    continue
                    
                day_data = df[df['date'] == current_date]
                if not day_data.empty:
                    row = day_data.iloc[0]
                    current_prices[code] = row['close']
                    current_rows[code] = row
            
            if not current_prices:
                continue
            
            # 平仓检查
            for code in list(executor.positions.keys()):
                current_price = current_prices.get(code, executor.positions[code].entry_price)
                
                # 持仓评分检查 - 低分时平仓
                if code in current_rows:
                    pos_score, _ = self.scorer.calculate(current_rows[code])
                    # 更激进的平仓 - 低于阈值一半就平
                    if pos_score < self.config.factor_strategy.score_config.threshold * 0.5:
                        executor.check_and_close(code, current_price, current_date)
                        continue
                
                # 止盈止损/到期检查
                executor.check_and_close(code, current_price, current_date)
            
            # 开仓
            if executor.can_open():
                scores = []
                for code, row in current_rows.items():
                    if code in executor.positions:
                        continue
                    
                    score, factor_scores = self.scorer.calculate(row)
                    active_count = sum(1 for s in factor_scores.values() if s > 0.3)
                    
                    threshold = self.config.factor_strategy.score_config.threshold
                    min_factors = self.config.factor_strategy.score_config.min_active_factors
                    
                    if score >= threshold and active_count >= min_factors:
                        scores.append((code, score, current_prices[code]))
                
                # 按分数排序
                scores.sort(key=lambda x: x[1], reverse=True)
                
                # 开仓分数最高的
                for code, score, price in scores:
                    if executor.open_position(code, price, current_date, score):
                        break
            
            # 调仓：如果有持仓的ETF评分太低，用更高分的替换
            elif executor.positions:
                # 找持仓中最差的
                worst_pos = None
                worst_score = 1.0
                for code in executor.positions:
                    if code in current_rows:
                        pos_score, _ = self.scorer.calculate(current_rows[code])
                        if pos_score < worst_score:
                            worst_score = pos_score
                            worst_pos = code
                
                # 找未持仓中最好的
                best_new = None
                best_score = 0
                for code, row in current_rows.items():
                    if code in executor.positions:
                        continue
                    new_score, _ = self.scorer.calculate(row)
                    if new_score > best_score:
                        best_score = new_score
                        best_new = (code, new_score, current_prices[code])
                
                # 如果新标的比持仓好超过阈值，调仓
                if (worst_pos and best_new and 
                    best_score > worst_score + 0.1 and
                    best_score >= self.config.factor_strategy.score_config.threshold):
                    # 平仓差的
                    worst_price = current_prices.get(worst_pos, executor.positions[worst_pos].entry_price)
                    executor.check_and_close(worst_pos, worst_price, current_date)
                    # 开仓好的
                    if executor.can_open():
                        executor.open_position(best_new[0], best_new[2], current_date, best_new[1])
        
        # 期末平仓
        final_prices = {}
        for code in executor.positions.keys():
            if code in price_data:
                last_row = price_data[code][price_data[code]['date'] == sorted_dates[-1]]
                if not last_row.empty:
                    final_prices[code] = last_row.iloc[0]['close']
        
        executor.close_all(final_prices, sorted_dates[-1])
        
        # 计算指标
        result = self.metrics.calculate(
            executor.trades,
            start_date,
            end_date,
            self.config.id,
            period
        )
        
        return result
    
    def run_single(self, db_path: str = "data/etf_factors.db") -> Dict[str, BacktestResult]:
        """
        执行回测（加载数据+执行）
        
        Args:
            db_path: 数据库路径
            
        Returns:
            {period: result}
        """
        price_data = self.load_data(db_path)
        return self.run(price_data)


def create_config(
    name: str,
    factors: list,
    weights: dict,
    direction: dict,
    stop_loss: float = -0.05,
    stop_profit: float = 0.10,
    threshold: float = 0.6,
    hold_days: int = 5
) -> ExperimentConfig:
    """
    快速创建配置
    
    Args:
        name: 实验名称
        factors: 因子列表
        weights: 因子权重
        direction: 因子方向
        stop_loss: 止损
        stop_profit: 止盈
        threshold: 分数阈值
        hold_days: 持仓天数
        
    Returns:
        ExperimentConfig
    """
    from src.strategy.config import ScoreConfig
    
    strategy = FactorStrategy(
        name=name,
        factors=factors,
        weights=weights,
        direction=direction,
        score_config=ScoreConfig(threshold=threshold, min_active_factors=2)
    )
    
    backtest = BacktestConfig(
        stop_loss=stop_loss,
        stop_profit=stop_profit,
        hold_days=hold_days
    )
    
    return ExperimentConfig(
        name=name,
        factor_strategy=strategy,
        backtest=backtest
    )