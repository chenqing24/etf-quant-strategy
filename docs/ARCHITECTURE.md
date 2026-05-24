# ETF量化策略 - 技术规范

## 1. 代码架构

```
etf_strategy/
├── src/                    # 源代码
│   ├── __init__.py
│   ├── config.py           # 配置层
│   ├── data_loader.py      # 数据层
│   ├── indicator.py        # 指标计算
│   ├── selector.py         # 选股层
│   ├── market_filter.py    # 市场过滤
│   ├── backtest.py         # 回测引擎
│   └── main.py             # 入口
├── tests/                  # 测试用例
│   ├── test_indicator.py
│   ├── test_selector.py
│   ├── test_backtest.py
│   └── test_integration.py
├── data/                   # 数据目录
│   └── etf_data_50/        # 原始数据CSV
├── scripts/                # 脚本
│   └── run_test.py
├── docs/                   # 文档
│   ├── PRD.md
│   └── ARCHITECTURE.md
└── README.md
```

## 2. 模块设计

### 2.1 配置层 (config.py)

```python
@dataclass
class StrategyConfig:
    """策略参数"""
    train_start: str = '2022-01-01'
    train_end: str = '2024-12-31'
    score_threshold: int = 6
    rebalance_days: int = 10
    stop_loss: float = -0.10
    stop_gain: float = 0.15
    max_hold_days: int = 15
    market_ma: int = 60
    fee_rate: float = 0.0003
    
    # 排除代码
    exclude_codes: set = None
    
    def __post_init__(self):
        if self.exclude_codes is None:
            self.exclude_codes = {...}
```

### 2.2 数据层 (data_loader.py)

```python
class DataLoader:
    """数据加载"""
    
    def load(self, data_dir: str) -> Dict[str, pd.DataFrame]:
        """加载所有ETF的CSV数据"""
        
    def get(self, code: str) -> pd.DataFrame:
        """获取单只ETF数据"""
        
    def get_etfs(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """批量获取ETF数据"""
```

### 2.3 指标层 (indicator.py)

```python
class Indicator:
    """技术指标计算"""
    
    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        """计算所有技术指标
        - MA5, MA10, MA20, MA60, MA120
        - MA_VOL_20 (成交量均线)
        - VOL_RATIO (量比)
        - RSI_5, RSI_14
        """
```

### 2.4 选股层 (selector.py)

```python
class Selector:
    """选股器"""
    
    def select_etfs(self, data: Dict[str, pd.DataFrame], 
                    config: StrategyConfig) -> set:
        """根据训练期收益选出TopN"""

    def score(self, df: pd.DataFrame, date: str) -> Tuple[int, List[str]]:
        """7因子打分，返回(分数, 选股理由)"""
```

### 2.5 市场过滤层 (market_filter.py)

```python
class MarketFilter:
    """市场环境过滤"""
    
    def __init__(self, hs300: pd.DataFrame, ma: int = 60):
        self.data = hs300.copy()
        self.data[f'ma{ma}'] = self.data['close'].rolling(ma).mean()
    
    def is_bullish(self, date: str) -> bool:
        """判断市场是否上涨趋势"""
```

### 2.6 回测层 (backtest.py)

```python
def run_backtest(
    data: Dict[str, pd.DataFrame],
    config: StrategyConfig,
    test_start: str,
    test_end: str,
) -> BacktestResult:
    """运行回测
    
    Returns:
        BacktestResult:
            - return: 总收益率(%)
            - drawdown: 最大回撤(%)
            - winrate: 胜率(%)
            - trades: 交易次数
            - equity_curve: 净值曲线
    """
```

## 3. 数据格式

### 3.1 ETF数据CSV

```csv
date,open,high,low,close,volume
2022-01-04,3.512,3.540,3.510,3.528,85436700
```

### 3.2 输出格式

```python
{
    'return': 81.8,      # 收益率(%)
    'drawdown': -55.5,   # 回撤(%)
    'winrate': 60.0,     # 胜率(%)
    'trades': 28,        # 交易次数
}
```

## 4. 接口设计

### 4.1 主入口

```python
from etf_strategy import run_strategy

# 运行完整策略
result = run_strategy(
    test_start='2025-05-06',
    test_end='2026-05-22',
    rebalance_days=10,
    score_threshold=6,
)
print(f"收益: {result['return']:+.1f}%")
```

### 4.2 参数化调用

```python
from etf_strategy.config import StrategyConfig
from etf_strategy.backtest import run_backtest
from etf_strategy.data_loader import DataLoader
from etf_strategy.selector import Selector
from etf_strategy.indicator import Indicator

# 1. 加载数据
loader = DataLoader()
data = loader.load('etf_data_50')

# 2. 配置
config = StrategyConfig(rebalance_days=10, score_threshold=6)

# 3. 选ETF
selector = Selector()
selected = selector.select_etfs(data, config)

# 4. 计算指标
data = Indicator.calculate_all(data, selected)

# 5. 回测
result = run_backtest(data, config, '2025-05-06', '2026-05-22')
```

## 5. 测试设计

### 5.1 单元测试

| 测试文件 | 测试内容 |
|----------|----------|
| test_indicator.py | MA计算、RSI计算、成交量比 |
| test_selector.py | 选股过滤、打分逻辑 |
| test_market_filter.py | 沪深300趋势判断 |

### 5.2 集成测试

| 测试文件 | 测试内容 |
|----------|----------|
| test_backtest.py | 完整回测流程 |
| test_regression.py | 确保修改不破坏已有功能 |

### 5.3 回归测试

```bash
# 确保回测结果一致
python -m pytest tests/ -v
# 预期：所有测试通过，结果与基准一致
```

## 6. Git提交规范

### 6.1 提交信息格式

```
<type>(<scope>): <description>

[optional body]
```

**Type**:
- feat: 新功能
- fix: 修复bug
- refactor: 重构
- docs: 文档
- test: 测试
- chore: 维护

### 6.2 提交历史（从历史对话提取）

| 提交 | 描述 |
|------|------|
| feat: 初始化项目结构 | 创建目录、配置文件 |
| feat: 实现数据加载层 | load_data, add_indicators |
| feat: 实现选股层 | select_etfs, score_etf |
| feat: 实现市场过滤 | MarketFilter类 |
| feat: 实现回测引擎 | run_backtest函数 |
| feat: 增加参数配置 | rebalance_days, score_threshold |
| docs: 添加PRD | 产品需求文档 |

---

*最后更新：2025-05-24*