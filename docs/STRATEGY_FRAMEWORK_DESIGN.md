# 配置驱动执行框架 - 设计文档

## 1. 概述

### 1.1 设计目标

实现**策略配置与执行引擎完全分离**的架构：
- 挖掘系统输出配置
- 统一引擎执行配置
- 结果统一存储

### 1.2 核心价值

| 价值 | 说明 |
|------|------|
| 可复现 | 同一配置可多次执行，结果一致 |
| 可对比 | 不同配置的结果可直接对比 |
| 易迭代 | 换个配置就是新实验 |
| 职责清 | 挖掘专注找参数，引擎专注执行 |

---

## 2. 架构设计

### 2.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        策略执行框架                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐               │
│  │  挖掘系统   │    │   配置层    │    │   执行层    │               │
│  │             │    │             │    │             │               │
│  │ Experimenter│───▶│ Experiment │───▶│  Universal │               │
│  │             │    │   Config   │    │  Executor  │               │
│  └─────────────┘    └─────────────┘    └─────────────┘               │
│         │                │                   │                        │
│         │                │                   ▼                        │
│         │                │           ┌─────────────┐                 │
│         │                │           │   结果层    │                 │
│         │                │           │BacktestResult│                 │
│         │                │           └─────────────┘                 │
│         │                │                   │                        │
│         ▼                ▼                   ▼                        │
│  ┌─────────────────────────────────────────────┐                   │
│  │              实验存储 (experiments.json)      │                   │
│  └─────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块关系

```
Experimenter (挖掘)
      │
      │ 生成配置
      ▼
ExperimentConfig (配置)
      │
      ├── FactorStrategy (因子策略)
      │         │
      │         ├── factors: List[str]
      │         ├── weights: Dict[str, float]
      │         ├── direction: Dict[str, str]
      │         └── score_config: ScoreConfig
      │
      ├── BacktestConfig (回测配置)
      │         │
      │         ├── stop_loss/stop_profit
      │         ├── hold_days/max_positions
      │         └── commission/slippage
      │
      └── DataConfig (数据配置)
                │
                ├── train_start/train_end
                └── test_start/test_end
      │
      ▼
UniversalExecutor (执行)
      │
      ├── FactorScorer (评分器)
      ├── PositionExecutor (执行器)
      └── MetricsCalculator (指标计算)
      │
      ▼
BacktestResult (结果)
      │
      ├── total_return/annual_return
      ├── sharpe_ratio/max_drawdown
      ├── win_rate/profit_loss_ratio
      └── trades: List[Trade]
```

---

## 3. 数据结构

### 3.1 配置结构 (ExperimentConfig)

```python
@dataclass
class ScoreConfig:
    """评分配置"""
    threshold: float = 0.6         # 分数阈值
    min_active_factors: int = 2     # 最少有效因子数


@dataclass
class FactorStrategy:
    """因子策略配置"""
    name: str                       # 策略名称
    factors: List[str]              # 因子列表
    weights: Dict[str, float]        # 因子权重
    direction: Dict[str, str]       # 因子方向 (long/short/neutral)
    score_config: ScoreConfig = None # 评分配置
    
    def __post_init__(self):
        if self.score_config is None:
            self.score_config = ScoreConfig()
    
    def get_valid_factors(self) -> List[str]:
        """获取有效因子（方向非neutral）"""
        return [f for f, d in self.direction.items() if d != 'neutral']
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'name': self.name,
            'factors': self.factors,
            'weights': self.weights,
            'direction': self.direction,
            'score_config': {
                'threshold': self.score_config.threshold,
                'min_active_factors': self.score_config.min_active_factors
            } if self.score_config else {}
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'FactorStrategy':
        """从字典反序列化"""
        score_config = None
        if 'score_config' in d:
            sc = d['score_config']
            score_config = ScoreConfig(
                threshold=sc.get('threshold', 0.6),
                min_active_factors=sc.get('min_active_factors', 2)
            )
        
        return cls(
            name=d['name'],
            factors=d['factors'],
            weights=d['weights'],
            direction=d['direction'],
            score_config=score_config
        )


@dataclass
class BacktestConfig:
    """回测配置"""
    stop_loss: float = -0.05        # 止损比例
    stop_profit: float = 0.10      # 止盈比例
    hold_days: int = 5              # 最大持仓天数
    max_positions: int = 2          # 最大持仓数
    commission: float = 0.0003       # 手续费
    slippage: float = 0.001         # 滑点


@dataclass
class DataConfig:
    """数据配置"""
    train_start: str = "2022-01-01"
    train_end: str = "2024-12-31"
    test_start: str = "2025-01-01"
    test_end: str = "2026-05-27"


@dataclass
class ExperimentConfig:
    """实验完整配置"""
    id: int = 0
    name: str = ""
    version: str = "v0.1.0"
    factor_strategy: FactorStrategy = None
    backtest: BacktestConfig = None
    data: DataConfig = None
    
    def __post_init__(self):
        if self.factor_strategy is None:
            self.factor_strategy = FactorStrategy(
                name="default",
                factors=[],
                weights={},
                direction={}
            )
        if self.backtest is None:
            self.backtest = BacktestConfig()
        if self.data is None:
            self.data = DataConfig()
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'factor_strategy': self.factor_strategy.to_dict(),
            'backtest': {
                'stop_loss': self.backtest.stop_loss,
                'stop_profit': self.backtest.stop_profit,
                'hold_days': self.backtest.hold_days,
                'max_positions': self.backtest.max_positions,
                'commission': self.backtest.commission,
                'slippage': self.backtest.slippage
            },
            'data': {
                'train_start': self.data.train_start,
                'train_end': self.data.train_end,
                'test_start': self.data.test_start,
                'test_end': self.data.test_end
            }
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'ExperimentConfig':
        """从字典反序列化"""
        fs_data = d.get('factor_strategy', {})
        factor_strategy = FactorStrategy.from_dict(fs_data)
        
        bt_data = d.get('backtest', {})
        backtest = BacktestConfig(
            stop_loss=bt_data.get('stop_loss', -0.05),
            stop_profit=bt_data.get('stop_profit', 0.10),
            hold_days=bt_data.get('hold_days', 5),
            max_positions=bt_data.get('max_positions', 2),
            commission=bt_data.get('commission', 0.0003),
            slippage=bt_data.get('slippage', 0.001)
        )
        
        data_data = d.get('data', {})
        data = DataConfig(
            train_start=data_data.get('train_start', '2022-01-01'),
            train_end=data_data.get('train_end', '2024-12-31'),
            test_start=data_data.get('test_start', '2025-01-01'),
            test_end=data_data.get('test_end', '2026-05-27')
        )
        
        return cls(
            id=d.get('id', 0),
            name=d.get('name', ''),
            version=d.get('version', 'v0.1.0'),
            factor_strategy=factor_strategy,
            backtest=backtest,
            data=data
        )
    
    @classmethod
    def from_experiment(cls, exp: Dict) -> 'ExperimentConfig':
        """从实验日志创建"""
        # 从现有的 experiments.json 格式转换
        return cls(
            id=exp.get('id', 0),
            name=exp.get('name', ''),
            version='v0.1.0',
            factor_strategy=FactorStrategy(
                name=exp.get('name', ''),
                factors=exp.get('factors', []),
                weights=exp.get('weights', {}),
                direction=exp.get('factor_direction', {})
            ),
            backtest=BacktestConfig(),
            data=DataConfig()
        )
```

### 3.2 回测结果结构 (BacktestResult)

```python
@dataclass
class Trade:
    """交易记录"""
    code: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    hold_days: int
    exit_reason: str  # 止损/止盈/到期/期末平仓
    entry_score: float


@dataclass
class BacktestResult:
    """回测结果"""
    config_id: int                  # 对应配置ID
    period: str                    # train/test
    total_return: float            # 总收益
    annual_return: float          # 年化收益
    sharpe_ratio: float            # 夏普比率
    max_drawdown: float            # 最大回撤
    max_drawdown_days: int        # 最大回撤天数
    win_rate: float                # 胜率
    profit_loss_ratio: float       # 盈亏比
    avg_profit: float              # 平均盈利
    avg_loss: float                # 平均亏损
    trade_count: int              # 交易次数
    trades: List[Trade]            # 交易列表
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'config_id': self.config_id,
            'period': self.period,
            'total_return': self.total_return,
            'annual_return': self.annual_return,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_days': self.max_drawdown_days,
            'win_rate': self.win_rate,
            'profit_loss_ratio': self.profit_loss_ratio,
            'avg_profit': self.avg_profit,
            'avg_loss': self.avg_loss,
            'trade_count': self.trade_count
        }
```

---

## 4. 模块设计

### 4.1 FactorScorer (评分器)

```python
class FactorScorer:
    """多因子评分器"""
    
    def __init__(self, factor_strategy: FactorStrategy):
        """
        初始化
        
        Args:
            factor_strategy: 因子策略配置
        """
        self.strategy = factor_strategy
        self.factors = factor_strategy.factors
        self.weights = factor_strategy.weights
        self.direction = factor_strategy.direction
        self.valid_factors = factor_strategy.get_valid_factors()
    
    def calculate(self, row: pd.Series) -> Tuple[float, Dict[str, float]]:
        """
        计算综合评分
        
        Args:
            row: 数据行 (包含因子值)
            
        Returns:
            (综合评分, 各因子得分字典)
        """
        total_score = 0.0
        factor_scores = {}
        
        for factor in self.valid_factors:
            if pd.isna(row.get(factor)):
                continue
            
            value = row[factor]
            direction = self.direction[factor]
            weight = self.weights.get(factor, 0)
            
            # 计算因子得分 (0~1)
            score = self._calculate_factor_score(factor, value, direction)
            factor_scores[factor] = score
            
            # 加权累加
            total_score += score * weight
        
        return total_score, factor_scores
    
    def _calculate_factor_score(
        self, 
        factor: str, 
        value: float, 
        direction: str
    ) -> float:
        """计算单个因子得分"""
        score = 0.5  # 默认中性
        
        if factor == 'ADX':
            # ADX高 → 强趋势
            score = min(value / 50, 1.0) if direction == 'long' else min((50 - value) / 50, 1.0)
        
        elif factor == 'BB_percent':
            # BB低 → 低位
            score = min((50 - value) / 50, 1.0) if direction == 'long' else min(value / 50, 1.0)
        
        elif factor == 'SAR_trend':
            # SAR趋势值
            score = value if direction == 'long' else (1 - value)
        
        elif factor == 'RSI_5':
            score = min((50 - value) / 50, 1.0) if direction == 'long' else min(value / 50, 1.0)
        
        elif factor == 'K':
            score = min((100 - value) / 100, 1.0) if direction == 'short' else min(value / 100, 1.0)
        
        elif factor == 'DIF':
            # DIF标准化到0~1
            score = min((value + 1) / 2, 1.0) if direction == 'short' else min((1 - value) / 2, 1.0)
        
        elif factor == 'OBV_diff':
            score = 0.5 - value / 2000 if direction == 'short' else 0.5 + value / 2000
        
        elif factor == 'DMA':
            score = min((value + 1) / 2, 1.0) if value >= 0 else min((1 - value) / 2, 1.0)
        
        return max(0, min(1, score))
```

### 4.2 PositionExecutor (执行器)

```python
class PositionExecutor:
    """持仓执行器"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.positions = {}  # {code: Position}
        self.trades = []
        self.equity = 1.0
    
    @dataclass
    class Position:
        """持仓"""
        code: str
        entry_price: float
        entry_date: str
        entry_score: float
        shares: float
        hold_days: int = 0
    
    def can_open(self) -> bool:
        """是否可以开仓"""
        return len(self.positions) < self.config.max_positions
    
    def open_position(
        self, 
        code: str, 
        price: float, 
        date: str, 
        score: float
    ) -> bool:
        """开仓"""
        if not self.can_open():
            return False
        
        position_value = self.equity / (self.config.max_positions - len(self.positions))
        shares = position_value / price
        shares = int(shares)  # 取整
        
        if shares <= 0:
            return False
        
        self.positions[code] = self.Position(
            code=code,
            entry_price=price,
            entry_date=date,
            entry_score=score,
            shares=shares
        )
        
        self.trades.append({
            'code': code,
            'action': 'buy',
            'date': date,
            'price': price,
            'shares': shares,
            'score': score
        })
        
        return True
    
    def check_and_close(
        self, 
        code: str, 
        current_price: float, 
        date: str
    ) -> Optional[Dict]:
        """检查是否需要平仓"""
        if code not in self.positions:
            return None
        
        pos = self.positions[code]
        pos.hold_days += 1
        
        pnl_pct = (current_price - pos.entry_price) / pos.entry_price
        
        # 止盈止损检查
        if pnl_pct <= self.config.stop_loss:
            return self._close_position(pos, current_price, date, '止损')
        
        if pnl_pct >= self.config.stop_profit:
            return self._close_position(pos, current_price, date, '止盈')
        
        if pos.hold_days >= self.config.hold_days:
            return self._close_position(pos, current_price, date, '到期')
        
        return None
    
    def _close_position(
        self, 
        pos: Position, 
        exit_price: float, 
        date: str, 
        reason: str
    ) -> Dict:
        """平仓"""
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        
        trade = {
            'code': pos.code,
            'entry_date': pos.entry_date,
            'exit_date': date,
            'entry_price': pos.entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'hold_days': pos.hold_days,
            'exit_reason': reason,
            'entry_score': pos.entry_score
        }
        
        self.trades.append({
            'code': pos.code,
            'action': 'sell',
            'date': date,
            'price': exit_price,
            'pnl_pct': pnl_pct,
            'reason': reason
        })
        
        del self.positions[pos.code]
        return trade
    
    def close_all(self, current_prices: Dict[str, float], date: str):
        """期末平仓"""
        for code, pos in list(self.positions.items()):
            price = current_prices.get(code, pos.entry_price)
            self._close_position(pos, price, date, '期末平仓')
```

### 4.3 MetricsCalculator (指标计算)

```python
class MetricsCalculator:
    """绩效指标计算"""
    
    @staticmethod
    def calculate(
        trades: List[Dict], 
        start_date: str, 
        end_date: str
    ) -> BacktestResult:
        """计算绩效指标"""
        if not trades:
            return BacktestResult(
                config_id=0, period='test',
                total_return=0, annual_return=0,
                sharpe_ratio=0, max_drawdown=0,
                max_drawdown_days=0, win_rate=0,
                profit_loss_ratio=0, avg_profit=0,
                avg_loss=0, trade_count=0, trades=[]
            )
        
        df = pd.DataFrame(trades)
        df = df.sort_values('exit_date')
        
        # 累计收益
        cumulative = (1 + df['pnl_pct']).cumprod()
        total_return = cumulative.iloc[-1] - 1
        
        # 年化收益
        days = (datetime.strptime(end_date, '%Y-%m-%d') - 
                datetime.strptime(start_date, '%Y-%m-%d')).days
        years = max(days / 365, 0.01)
        annual_return = (1 + total_return) ** (1 / years) - 1
        
        # 夏普比率
        if df['pnl_pct'].std() > 0:
            sharpe = df['pnl_pct'].mean() / df['pnl_pct'].std() * np.sqrt(252)
        else:
            sharpe = 0
        
        # 最大回撤
        peak = cumulative.expanding().max()
        drawdown = (cumulative - peak) / peak
        max_drawdown = abs(drawdown.min()) if drawdown.min() < 0 else 0
        
        # 胜率
        wins = df[df['pnl_pct'] > 0]
        win_rate = len(wins) / len(df) if len(df) > 0 else 0
        avg_profit = wins['pnl_pct'].mean() if len(wins) > 0 else 0
        
        losses = df[df['pnl_pct'] < 0]
        avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else 0
        
        return BacktestResult(
            config_id=0,
            period='test',
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            max_drawdown_days=0,
            win_rate=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            trade_count=len(trades),
            trades=[Trade(**t) for t in trades]
        )
```

### 4.4 UniversalExecutor (统一执行引擎)

```python
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
        self.executor = PositionExecutor(config.backtest)
        self.metrics = MetricsCalculator()
    
    def load_data(self, db_path: str = "data/etf_factors.db") -> Dict[str, pd.DataFrame]:
        """加载数据"""
        from src.data.database import Database
        from src.indicators.wrapper import IndicatorCalculator, calculate_returns
        
        db = Database(db_path)
        calculator = IndicatorCalculator()
        
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
            
            df = calculator.calculate_all(df)
            df = calculate_returns(df)
            price_data[code] = df
        
        return price_data
    
    def run(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, BacktestResult]:
        """
        执行回测
        
        Args:
            price_data: 价格数据
            
        Returns:
            {period: result}
        """
        results = {}
        
        for period_name, start, end in [
            ('train', self.config.data.train_start, self.config.data.train_end),
            ('test', self.config.data.test_start, self.config.data.test_end)
        ]:
            result = self._run_period(price_data, start, end, period_name)
            results[period_name] = result
        
        return results
    
    def _run_period(
        self, 
        price_data: Dict[str, pd.DataFrame],
        start_date: str,
        end_date: str,
        period: str
    ) -> BacktestResult:
        """执行单个周期"""
        # 重置执行器
        self.executor = PositionExecutor(self.config.backtest)
        
        # 获取交易日
        all_dates = set()
        for df in price_data.values():
            all_dates.update(df['date'].tolist())
        sorted_dates = sorted([d for d in all_dates if start_date <= d <= end_date])
        
        for current_date in sorted_dates:
            # 获取当日数据
            current_prices = {}
            for code, df in price_data.items():
                day_data = df[df['date'] == current_date]
                if not day_data.empty:
                    current_prices[code] = day_data.iloc[0].to_dict()
            
            if not current_prices:
                continue
            
            # 平仓检查
            for code in list(self.executor.positions.keys()):
                pos_data = self.executor.positions[code]
                current_price = current_prices.get(code, {}).get('close', pos_data.entry_price)
                self.executor.check_and_close(code, current_price, current_date)
            
            # 开仓
            if self.executor.can_open():
                scores = []
                for code, row in current_prices.items():
                    if code in self.executor.positions:
                        continue
                    
                    score, factor_scores = self.scorer.calculate(pd.Series(row))
                    active_count = sum(1 for s in factor_scores.values() if s > 0.3)
                    
                    if (score >= self.config.factor_strategy.score_config.threshold and 
                        active_count >= self.config.factor_strategy.score_config.min_active_factors):
                        scores.append((code, score, row['close']))
                
                # 按分数排序
                scores.sort(key=lambda x: x[1], reverse=True)
                
                for code, score, price in scores:
                    if self.executor.open_position(code, price, current_date, score):
                        break
        
        # 期末平仓
        final_prices = {}
        for code, df in price_data.items():
            last_row = df[df['date'] == sorted_dates[-1]]
            if not last_row.empty:
                final_prices[code] = last_row.iloc[0]['close']
        
        self.executor.close_all(final_prices, sorted_dates[-1])
        
        # 计算指标
        result = self.metrics.calculate(
            self.executor.trades,
            start_date,
            end_date
        )
        result.config_id = self.config.id
        result.period = period
        
        return result
```

---

## 5. 文件结构

```
src/
├── strategy/                    # 策略执行框架
│   ├── __init__.py
│   ├── config.py               # 配置类 (ExperimentConfig等)
│   ├── scorer.py               # 评分器 (FactorScorer)
│   ├── executor.py             # 执行器 (PositionExecutor)
│   ├── metrics.py              # 指标计算 (MetricsCalculator)
│   ├── engine.py               # 统一引擎 (UniversalExecutor)
│   └── store.py                # 配置存储 (ExperimentStore)
│
├── experiments/                # 实验脚本
│   ├── run_experiments.py      # 实验主脚本
│   └── exp_*.py                # 各实验
│
└── backtest/                    # (待废弃)
    └── engine.py
```

---

## 6. 接口规范

### 6.1 JSON配置格式

```json
{
  "id": 1,
  "name": "Exp6: 优化止盈止损",
  "version": "v0.1.0",
  "factor_strategy": {
    "name": "ADX优先",
    "factors": ["ADX", "BB_percent", "SAR_trend", "RSI_5", "K", "DIF", "OBV_diff", "DMA"],
    "weights": {
      "ADX": 0.5,
      "BB_percent": 0.3,
      "SAR_trend": 0.2
    },
    "direction": {
      "ADX": "long",
      "BB_percent": "long",
      "SAR_trend": "long",
      "RSI_5": "neutral",
      "K": "neutral",
      "DIF": "short",
      "OBV_diff": "short",
      "DMA": "neutral"
    },
    "score_config": {
      "threshold": 0.55,
      "min_active_factors": 2
    }
  },
  "backtest": {
    "stop_loss": -0.03,
    "stop_profit": 0.08,
    "hold_days": 5,
    "max_positions": 2,
    "commission": 0.0003,
    "slippage": 0.001
  },
  "data": {
    "train_start": "2022-01-01",
    "train_end": "2024-12-31",
    "test_start": "2025-01-01",
    "test_end": "2026-05-27"
  }
}
```

### 6.2 执行示例

```python
from src.strategy.config import ExperimentConfig, FactorStrategy, BacktestConfig
from src.strategy.engine import UniversalExecutor

# 方式1: 从配置执行
config = ExperimentConfig.from_json("exp_config.json")
executor = UniversalExecutor(config)
results = executor.run(price_data)

# 方式2: 从实验ID执行
executor = UniversalExecutor.from_experiment(1)  # 从experiments.json加载
results = executor.run()

# 方式3: 快速实验
config = ExperimentConfig(
    name="Quick Test",
    factor_strategy=FactorStrategy(...),
    backtest=BacktestConfig(...)
)
executor = UniversalExecutor(config)
results = executor.run()
```

---

## 7. 验收标准

| AC-ID | 标准 | 测试 |
|-------|------|------|
| AC10-1 | scorer/executor/metrics 三个模块独立 | 模块间无import |
| AC10-2 | 新引擎可复用原 TradeExecutor | 继承测试 |
| AC10-3 | 实验和生产共用 scorer | scorer可互换 |
| AC10-4 | 现有实验结果可复现 | 对比Exp1-5 |
| AC10-5 | 任意配置可通过JSON执行 | 执行10个不同配置 |
| AC10-6 | 结果与配置完全对应 | 每个参数都体现在结果 |
| AC10-7 | 可从experiments.json加载执行 | 加载并重跑Exp3 |
| AC10-8 | 不同配置结果可直接对比 | 导出CSV对比 |

---

## 8. 实施计划

| 阶段 | 任务 | 交付物 |
|------|------|--------|
| 1 | 创建config.py | 配置类 |
| 2 | 创建scorer.py | 评分器 |
| 3 | 创建executor.py | 执行器 |
| 4 | 创建metrics.py | 指标计算 |
| 5 | 创建engine.py | 统一引擎 |
| 6 | 集成测试 | 复现Exp1 |
| 7 | 回归测试 | 所有Exp1-5 |
| 8 | 文档更新 | 使用文档 |

---

*最后更新：2025-05-27*
*更新人：福猫管家*