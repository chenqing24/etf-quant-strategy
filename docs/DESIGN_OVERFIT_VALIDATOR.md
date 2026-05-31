# 过拟合检验系统 - 最终设计文档 v2.0

> 版本: 2.0 | 日期: 2026-06-01 | 状态: 待确认

---

## 一、设计目标

| 目标 | 描述 | 优先级 |
|------|------|:------:|
| **核心** | 准确识别策略是否产生真实alpha | P0 |
| **可靠** | 不被市场状态、交易成本等系统性因素误导 | P0 |
| **泛化** | 验证策略在不同ETF上是否通用 | P0 |
| **可执行** | 在有限数据下给出可信结论 | P1 |

---

## 二、核心架构

### 2.1 模块关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                    ComprehensiveValidator                      │
│                      (综合验证调度器)                           │
└─────────────────────────────────────────────────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│ WalkForwardEngine │ │  MonteCarloEngine │ │ CrossEtfValidator │
│   (滚动窗口)       │ │   (蒙特卡洛)       │ │   (跨ETF泛化)      │
└───────────────────┘ └───────────────────┘ └───────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│ SignalGenerator   │ │ MarketStateFilter │ │ FactorAnalyzer    │
│   (信号生成器)     │ │   (市场状态)       │ │   (因子分析)       │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

### 2.2 数据流

```
输入数据
    │
    ▼
┌──────────────┐
│ 数据预处理   │ ← 交易成本标准化、市场状态标注
└──────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│                   三重验证                       │
├──────────────────────────────────────────────────┤
│ 1. WalkForward: 时序稳健性                        │
│ 2. MonteCarlo: 统计显著性                        │
│ 3. CrossEtf: 跨ETF泛化                          │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│                   综合评分                       │
├──────────────────────────────────────────────────┤
│ 最终结论: 通过/不通过 + 置信区间 + 详细报告       │
└──────────────────────────────────────────────────┘
```

---

## 三、核心模块设计

### 3.1 WalkForwardEngine

#### 职责
在时间维度上验证策略稳健性

#### 接口

```python
class WalkForwardEngine:
    def __init__(self, train_months=6, test_months=3, transaction_cost=0.002):
        """
        参数:
            train_months: 训练窗口月数
            test_months: 测试窗口月数
            transaction_cost: 双边交易成本(默认0.2%)
        """
    
    def validate(self, df, signal_func) -> WalkForwardResult:
        """
        输入: K线数据, 信号生成函数
        输出: 验证结果
        """
```

#### 算法

```python
def validate(self, df, signal_func):
    """
    Walk-Forward验证流程:
    
    时间线:
    [====训练6月====|==测试3月==][====训练6月====|==测试3月==]...
          ↑训练窗口      ↑测试窗口
    
    每个窗口评估:
    1. 训练期: 生成信号并计算收益(调整后)
    2. 测试期: 应用相同策略计算收益(调整后)
    3. 记录: 训练收益, 测试收益, 衰减率, 夏普
    
    通过条件(综合评分≥0.5):
    - 测试收益 > 0
    - 样本外衰减 < 50%
    - 测试夏普 > 0.3
    """
    
    config = self.config
    results = []
    
    train_days = config.train_months * 21
    test_days = config.test_months * 21
    step = test_days  # 非重叠
    
    for start in range(0, len(df) - train_days - test_days, step):
        # 分割窗口
        train_df = df.iloc[start:start + train_days]
        test_df = df.iloc[start + train_days:start + train_days + test_days]
        
        # 生成信号
        train_signal = signal_func(train_df)
        test_signal = signal_func(test_df)
        
        # 计算收益(含成本)
        train_result = self.compute_result(train_df, train_signal)
        test_result = self.compute_result(test_df, test_signal)
        
        # 记录
        results.append({
            'train_return': train_result.total_return,
            'test_return': test_result.total_return,
            'test_sharpe': test_result.sharpe,
            'decay': compute_decay(train_result.total_return, test_result.total_return),
            'pass': self.evaluate(test_result, train_result)
        })
    
    return self.aggregate(results)
```

#### 窗口设计原则

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| 训练期 | 6个月 | 足够数据训练，避免过时 |
| 测试期 | 3个月 | 训练期的1/2 |
| 步长 | 测试期长度 | 非重叠，保证独立性 |
| 最少窗口 | 3个 | 保证统计可信 |

---

### 3.2 MonteCarloEngine

#### 职责
验证策略是否显著优于随机

#### 接口

```python
class MonteCarloEngine:
    def __init__(self, n_simulations=1000, transaction_cost=0.002):
        """
        参数:
            n_simulations: 模拟次数
            transaction_cost: 双边交易成本
        """
    
    def validate(self, df, signal_func, market_state=None) -> MCResult:
        """
        输入: K线数据, 信号生成函数, 市场状态(可选)
        输出: 验证结果
        """
```

#### 算法

```python
def validate(self, df, signal_func, market_state=None):
    """
    条件蒙特卡洛检验流程:
    
    Step 1: 计算真实信号和收益
    Step 2: 生成条件随机信号(匹配市场状态)
    Step 3: 比较真实vs随机
    Step 4: 计算条件p-value
    
    核心改进:
    - 条件随机: 在与真实信号相同的市场状态下生成
    - 成本调整: 所有收益扣除交易成本
    - 分状态计算: 不同市场状态下分别计算
    """
    
    # 1. 真实收益
    real_signal = signal_func(df)
    real_returns = self.calculate_returns(df, real_signal)
    real_mean = np.mean(real_returns)
    
    # 2. 条件随机信号
    if market_state is None:
        market_state = self.infer_market_state(df)
    
    random_means = []
    for _ in range(self.config.n_simulations):
        # 生成匹配条件随机信号
        random_signal = self.generate_conditional_random(
            len(df),
            signal_p=real_signal.mean(),
            market_state=market_state,
            real_signal_market=real_signal.map(lambda x: x if real_signal.iloc[real_signal==x].index else None)
        )
        random_returns = self.calculate_returns(df, random_signal)
        random_means.append(np.mean(random_returns))
    
    # 3. 计算p-value
    p_value = np.mean([1 if m >= real_mean else 0 for m in random_means])
    z_score = (real_mean - np.mean(random_means)) / np.std(random_means)
    
    return {
        'p_value': p_value,
        'z_score': z_score,
        'real_mean': real_mean,
        'random_mean': np.mean(random_means),
        'significant': p_value < 0.05
    }
```

#### 条件随机信号生成

```python
def generate_conditional_random(self, n, signal_p, market_state, real_signal_market):
    """
    生成条件随机信号:
    - 保持与真实信号相同的信号密度
    - 在与真实信号相同的市场状态下生成
    
    目的: 确保比较的公平性
    """
    # 获取真实信号在各市场状态的分布
    state_distribution = self.compute_state_distribution(real_signal_market, market_state)
    
    # 按比例在各市场状态生成随机信号
    random_signal = pd.Series(False, index=range(n))
    
    for state, ratio in state_distribution.items():
        state_indices = [i for i, s in enumerate(market_state) if s == state]
        n_signal = int(len(state_indices) * ratio)
        
        # 在该状态内随机选择信号点
        signal_indices = np.random.choice(state_indices, n_signal, replace=False)
        random_signal.iloc[signal_indices] = True
    
    return random_signal
```

---

### 3.3 CrossEtfValidator

#### 职责
验证策略在不同ETF上的泛化能力

#### 接口

```python
class CrossEtfValidator:
    def __init__(self, min_generalization_gap=0.2):
        """
        参数:
            min_generalization_gap: 最大泛化差距(训练vs测试通过率差)
        """
    
    def validate(self, etf_data_dict, signal_func) -> CrossEtfResult:
        """
        输入: {etf_code: df}字典
        输出: 泛化验证结果
        """
```

#### 算法

```python
def validate(self, etf_data_dict, signal_func):
    """
    跨ETF泛化验证流程:
    
    Step 1: 将ETF分为训练集和测试集
    Step 2: 在训练集上验证策略
    Step 3: 在测试集上验证策略
    Step 4: 比较差距
    
    通过条件:
    - 训练集通过率 > 30%
    - 测试集通过率 > 20%
    - 泛化差距 < 20%
    """
    
    etf_codes = list(etf_data_dict.keys())
    np.random.shuffle(etf_codes)
    
    split = len(etf_codes) // 2
    train_etfs = etf_codes[:split]
    test_etfs = etf_codes[split:]
    
    # 训练集验证
    train_results = []
    for code in train_etfs:
        wf = WalkForwardEngine()
        result = wf.validate(etf_data_dict[code], signal_func)
        train_results.append(result)
    
    # 测试集验证
    test_results = []
    for code in test_etfs:
        wf = WalkForwardEngine()
        result = wf.validate(etf_data_dict[code], signal_func)
        test_results.append(result)
    
    train_pass_rate = np.mean([r['pass_rate'] for r in train_results])
    test_pass_rate = np.mean([r['pass_rate'] for r in test_results])
    gap = train_pass_rate - test_pass_rate
    
    return {
        'train_pass_rate': train_pass_rate,
        'test_pass_rate': test_pass_rate,
        'generalization_gap': gap,
        'train_n': len(train_etfs),
        'test_n': len(test_etfs),
        'pass': (
            train_pass_rate > 0.3 and
            test_pass_rate > 0.2 and
            gap < 0.2
        )
    }
```

---

### 3.4 ComprehensiveValidator

#### 职责
调度三大验证引擎，综合评分

```python
class ComprehensiveValidator:
    """
    综合验证调度器
    """
    
    def __init__(self, config=None):
        if config is None:
            config = {
                'walk_forward': {'train_months': 6, 'test_months': 3},
                'monte_carlo': {'n_simulations': 1000},
                'cross_etf': {'min_gap': 0.2},
                'transaction_cost': 0.002
            }
        self.config = config
    
    def validate(self, etf_data_dict, signal_func) -> ComprehensiveResult:
        """
        综合验证流程:
        
        1. WalkForward: 时序稳健性
        2. MonteCarlo: 统计显著性  
        3. CrossEtf: 跨ETF泛化
        4. 综合评分
        """
        
        results = {}
        
        # 1. WalkForward - 对每个ETF
        wf_engine = WalkForwardEngine(**self.config['walk_forward'])
        results['walk_forward'] = {}
        for code, df in etf_data_dict.items():
            results['walk_forward'][code] = wf_engine.validate(df, signal_func)
        
        # 2. MonteCarlo - 对每个ETF
        mc_engine = MonteCarloEngine(**self.config['monte_carlo'])
        results['monte_carlo'] = {}
        for code, df in etf_data_dict.items():
            results['monte_carlo'][code] = mc_engine.validate(df, signal_func)
        
        # 3. CrossEtf - 跨ETF泛化
        cv_engine = CrossEtfValidator(**self.config['cross_etf'])
        results['cross_etf'] = cv_engine.validate(etf_data_dict, signal_func)
        
        # 4. 综合评分
        results['composite'] = self.compute_composite_score(results)
        
        return results
    
    def compute_composite_score(self, results):
        """
        综合评分计算:
        
        权重:
        - WalkForward通过率: 30%
        - MonteCarlo显著性: 30%
        - CrossEtf泛化通过率: 30%
        - 一致性(跨ETF): 10%
        """
        
        # WalkForward综合通过率
        wf_rates = [r['pass_rate'] for r in results['walk_forward'].values()]
        wf_score = np.mean(wf_rates)
        
        # MonteCarlo显著率
        mc_sig = [r['significant'] for r in results['monte_carlo'].values()]
        mc_score = np.mean(mc_sig)
        
        # CrossEtf
        ce_score = results['cross_etf']['test_pass_rate']
        
        # 一致性
        consistency = 1 - np.std(wf_rates) if len(wf_rates) > 1 else 1.0
        
        composite = (
            0.30 * wf_score +
            0.30 * mc_score +
            0.30 * ce_score +
            0.10 * consistency
        )
        
        return {
            'composite_score': composite,
            'walk_forward_score': wf_score,
            'monte_carlo_score': mc_score,
            'cross_etf_score': ce_score,
            'consistency': consistency,
            'pass': composite >= 0.5
        }
```

---

## 四、输出格式

### 4.1 验证结果JSON

```json
{
  "comprehensive_result": {
    "composite_score": 0.65,
    "pass": true,
    "confidence": "medium"
  },
  
  "walk_forward": {
    "overall_pass_rate": 0.45,
    "by_etf": {
      "512170": {"pass_rate": 0.6, "windows": 3, "details": [...]},
      "588000": {"pass_rate": 0.4, "windows": 3, "details": [...]}
    }
  },
  
  "monte_carlo": {
    "significant_rate": 0.35,
    "by_etf": {
      "512170": {"p_value": 0.02, "z_score": 2.1, "significant": true},
      "588000": {"p_value": 0.15, "z_score": 0.8, "significant": false}
    }
  },
  
  "cross_etf": {
    "train_pass_rate": 0.5,
    "test_pass_rate": 0.35,
    "generalization_gap": 0.15,
    "pass": true
  },
  
  "details": {
    "warnings": ["训练集样本量较小(7个ETF)"],
    "recommendations": ["考虑扩大ETF池以提高泛化验证可信度"]
  }
}
```

### 4.2 决策矩阵

| 综合分 | WF通过率 | MC显著率 | CrossEtf | 结论 | 建议 |
|:------:|:--------:|:--------:|:--------:|------|------|
| ≥0.7 | ≥0.5 | ≥0.5 | ≥0.3 | ✅强烈推荐 | 可考虑实盘 |
| 0.5-0.7 | ≥0.3 | ≥0.3 | ≥0.2 | 🟡谨慎推荐 | 需进一步验证 |
| 0.3-0.5 | ≥0.2 | ≥0.2 | ≥0.1 | ⚠️不推荐 | 需重大改进 |
| <0.3 | <0.2 | <0.2 | <0.1 | ❌拒绝 | 策略无效 |

---

## 五、配置文件

```python
# config/overfit_validation_config.py

OVERFIT_VALIDATION_CONFIG = {
    # WalkForward配置
    'walk_forward': {
        'train_months': 6,      # 训练窗口
        'test_months': 3,         # 测试窗口
        'min_windows': 3,         # 最少窗口数
        'pass_criteria': {
            'min_test_return': 0,           # 测试期正收益
            'max_decay': 0.5,                # 最大衰减50%
            'min_test_sharpe': 0.3          # 测试期夏普
        }
    },
    
    # MonteCarlo配置
    'monte_carlo': {
        'n_simulations': 1000,     # 模拟次数
        'confidence_level': 0.05,   # 显著性水平
    },
    
    # CrossEtf配置
    'cross_etf': {
        'train_ratio': 0.5,        # 训练集比例
        'min_train_etfs': 5,       # 最少训练ETF数
        'min_gap': 0.2,            # 最大泛化差距
    },
    
    # 全局配置
    'transaction_cost': 0.002,     # 双边交易成本0.2%
    'market_benchmark': '510300',  # 市场基准(用于判断市场状态)
    
    # 评分权重
    'weights': {
        'walk_forward': 0.30,
        'monte_carlo': 0.30,
        'cross_etf': 0.30,
        'consistency': 0.10
    },
    
    # 通过阈值
    'pass_threshold': 0.5          # 综合分≥0.5通过
}
```

---

## 六、执行计划

| 阶段 | 任务 | 工时 | 交付物 |
|------|------|:----:|--------|
| **开发** | | | |
| M1 | WalkForwardEngine实现 | 1h | `walk_forward.py` |
| M2 | MonteCarloEngine实现 | 1h | `monte_carlo.py` |
| M3 | CrossEtfValidator实现 | 1h | `cross_etf.py` |
| M4 | ComprehensiveValidator整合 | 0.5h | `validator.py` |
| **测试** | | | |
| T1 | 单元测试(边界、异常) | 0.5h | `test_validator.py` |
| T2 | 回归测试(v8_sop旧数据) | 0.5h | 验证报告 |
| **验证** | | | |
| V1 | 重跑v8_sop实验 | 1h | 新结果JSON |
| V2 | 对比新旧结果 | 0.5h | 对比报告 |
| **交付** | | | |
| D1 | 文档更新 | 0.5h | FIX_PLAN.md |
| D2 | Git提交 | 0.25h | commit |
| D3 | 推送远程 | 0.25h | push |

**总工时: ~6小时**

---

## 七、验收标准

### 7.1 功能验收

| 验收项 | 检查方法 | 预期 |
|--------|----------|------|
| WalkForward非重叠 | 检查窗口边界 | 无重叠 |
| MC条件随机 | 对比信号分布 | 信号密度匹配 |
| CrossEtf划分 | 检查ETF分配 | 训练/测试各半 |
| 综合评分 | 计算加权平均 | 0-1之间 |
| 决策正确 | 按决策矩阵判断 | 与预期一致 |

### 7.2 回归验收

| 验收项 | 检查方法 | 预期 |
|--------|----------|------|
| 旧实验可重跑 | 运行experiment_v8_sop.py | 正常完成 |
| 结果差异 | 对比新旧p-value | 差异显著(新<旧) |
| 通过率合理 | 检查各验证通过率 | 不是100% |

### 7.3 预期结果对比

| 指标 | v8_sop旧结果 | v2.0新结果 |
|------|:------------:|:-----------:|
| WalkForward通过率 | <50% | 30-50% |
| MC p-value | =1.0 | 0.01-0.50 |
| CrossEtf测试通过率 | 未测试 | >20% |
| 综合评分 | 无法计算 | >0.5 |

---

## 八、相关文档

| 文档 | 用途 |
|------|------|
| `docs/ISSUES.md` | 问题清单 |
| `docs/FIX_PLAN.md` | 修复计划 |
| `docs/FIRST_PRINCIPLES_ANALYSIS.md` | 第一性原理分析 |
| `scripts/experiment_v8_sop.py` | 待修复代码 |
| `scripts/validators/` | 新模块目录 |

---

## 九、变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-05-31 | 初稿 |
| 2.0 | 2026-06-01 | 第一性原理分析后重构 |

---

*设计版本: 2.0 | 状态: 待确认*
*执行优先级: P0*