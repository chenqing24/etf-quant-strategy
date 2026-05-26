# ETF量化系统 - 接口契约文档

> 规范模块间调用关系，解决参数传递链路长的问题

## 1. 核心原则

### 1.1 单一职责
每个模块只做一件事，接口清晰

### 1.2 依赖注入
通过构造函数注入依赖，而非全局状态

### 1.3 最小暴露
只暴露必要的接口，隐藏内部实现

---

## 2. 模块架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      ETFDecisionEngine                      │
│                    (决策引擎 - 顶层入口)                    │
└─────────────────────┬─────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│ DataLayer  │  │ Strategy   │  │ Notifier  │
│ 数据层     │  │ 策略层     │  │ 通知层    │
└─────┬─────┘  └─────┬─────┘  └─────┬─────┘
      │              │              │
      ▼              ▼              ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│ DataLoader│  │ Selector  │  │ DingTalk  │
│ DataMgr   │  │ Backtest  │  │ Sender    │
└───────────┘  └───────────┘  └───────────┘
```

---

## 3. 数据层接口

### 3.1 DataLoader

```python
class DataLoader:
    """ETF数据加载器"""
    
    def load(self, data_dir: str) -> Dict[str, pd.DataFrame]:
        """加载目录下所有CSV文件
        
        Args:
            data_dir: 数据目录路径
            
        Returns:
            Dict[str, pd.DataFrame]: {code: DataFrame}
            
        Raises:
            DataLoadError: 数据加载失败
        """
        pass
    
    def get(self, code: str) -> Optional[pd.DataFrame]:
        """获取单只ETF数据"""
        pass
```

### 3.2 DataFacade

```python
class DataFacade:
    """数据统一入口（热冷数据统一管理）"""
    
    def __init__(self, data_dir: str):
        self.hot = HotDataLayer(data_dir)
        self.cold = ColdDataLayer(data_dir)
    
    def get_realtime(self, code: str) -> Optional[HotDataRecord]:
        """获取实时数据（优先热数据）"""
        pass
    
    def get_history(self, code: str, days: int = 365) -> Optional[pd.DataFrame]:
        """获取历史数据"""
        pass
```

---

## 4. 策略层接口

### 4.1 Selector

```python
class Selector:
    """ETF选择器（基于训练期收益）"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self._data = None  # 缓存数据
    
    def select(self, data: Dict[str, pd.DataFrame]) -> Set[str]:
        """根据训练期收益选出TopN的ETF
        
        Args:
            data: 原始ETF数据
            
        Returns:
            Set[str]: 选中的ETF代码集合
        """
        pass
    
    def score(self, df: pd.DataFrame, date: str) -> ScoreResult:
        """7因子打分
        
        Args:
            df: ETF数据
            date: 评分日期
            
        Returns:
            ScoreResult: (总分, 理由列表)
        """
        pass
```

### 4.2 ScoreResult

```python
@dataclass
class ScoreResult:
    """评分结果"""
    total: int                    # 总分
    reasons: List[str]             # 选股理由
    factors: Dict[str, int]       # 各因子得分
    timestamp: str                # 评分时间
```

---

## 5. 决策层接口

### 5.1 DecisionEngine

```python
class DecisionEngine:
    """决策引擎（核心业务逻辑）"""
    
    def __init__(self, config: EngineConfig):
        self.data_facade = DataFacade(config.data_dir)
        self.selector = Selector(config.selector_config)
        self.notifier = Notifier(config.notifier_config)
    
    def decide(self, date: str) -> DecisionResult:
        """执行决策
        
        Args:
            date: 决策日期
            
        Returns:
            DecisionResult: 决策结果
            
        Raises:
            InsufficientDataError: 数据不足
            MarketFilterFailedError: 市场过滤失败
        """
        pass
```

### 5.2 DecisionResult

```python
@dataclass
class DecisionResult:
    """决策结果"""
    action: Literal['buy', 'sell', 'hold', 'wait']
    code: Optional[str]
    name: Optional[str]
    price: Optional[float]
    stop_loss: Optional[float]
    stop_gain: Optional[float]
    realtime: Optional[Dict]        # 实时数据校验
    indicators: Optional[Dict]     # 技术指标
    timestamp: str
```

---

## 6. 输出控制接口

### 6.1 OutputController（新增）

```python
from enum import Enum, auto

class OutputLevel(Enum):
    """输出级别"""
    SILENT = auto()    # 完全静默（钉钉场景）
    BRIEF = auto()     # 简版输出
    NORMAL = auto()    # 正常输出（含进度）
    VERBOSE = auto()   # 详细输出（含调试）

class OutputController:
    """统一输出控制器"""
    
    _instance = None  # 单例
    
    def __init__(self, level: OutputLevel = OutputLevel.NORMAL):
        self.level = level
    
    @classmethod
    def get_instance(cls) -> 'OutputController':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_level(self, level: OutputLevel):
        self.level = level
    
    def should_print(self, min_level: OutputLevel) -> bool:
        """判断是否应该打印"""
        levels = list(OutputLevel)
        return levels.index(self.level) >= levels.index(min_level)
    
    def print(self, *args, level: OutputLevel = OutputLevel.NORMAL, **kwargs):
        """条件打印"""
        if self.should_print(level):
            print(*args, **kwargs)
```

### 6.2 使用规范

```python
# ❌ 旧方式（硬编码条件）
if not getattr(self, '_simple_mode', False):
    print(f"加载 {len(self.data)} 只ETF数据")

# ✅ 新方式（统一输出控制）
from src.output_controller import OutputController, OutputLevel

ctrl = OutputController.get_instance()
ctrl.print(f"加载 {len(self.data)} 只ETF数据", level=OutputLevel.NORMAL)
```

---

## 7. 错误处理规范

### 7.1 自定义异常

```python
class ETFError(Exception):
    """ETF系统基础异常"""
    pass

class DataLoadError(ETFError):
    """数据加载失败"""
    pass

class InsufficientDataError(ETFError):
    """数据不足"""
    pass

class StrategyError(ETFError):
    """策略执行错误"""
    pass

class NotificationError(ETFError):
    """通知发送失败"""
    pass
```

### 7.2 错误码规范

| 错误码 | 含义 | 处理建议 |
|--------|------|----------|
| E001 | 数据加载失败 | 检查数据目录 |
| E002 | 数据不足 | 等待数据累积 |
| E003 | 网络请求失败 | 重试或降级 |
| E004 | 通知发送失败 | 记录日志，人工干预 |
| E101 | 市场过滤失败 | 空仓观望 |
| E102 | 无合格标的 | 降低门槛或等待 |

---

## 8. 调用示例

### 8.1 正确调用链

```python
from src.engine import DecisionEngine
from src.config import EngineConfig
from src.output_controller import OutputController, OutputLevel

# 1. 配置输出级别
OutputController.get_instance().set_level(OutputLevel.BRIEF)

# 2. 初始化引擎（依赖注入）
config = EngineConfig(data_dir='etf_data_live')
engine = DecisionEngine(config)

# 3. 执行决策
result = engine.decide('2026-05-26')

# 4. 处理结果
if result.action == 'buy':
    print(f"买入 {result.code}")
```

### 8.2 错误处理

```python
try:
    result = engine.decide('2026-05-26')
except InsufficientDataError as e:
    print(f"数据不足: {e}")
except MarketFilterFailedError:
    print("市场条件不满足，空仓观望")
```

---

## 9. 修订历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-26 | v1.0 | 初始版本 |