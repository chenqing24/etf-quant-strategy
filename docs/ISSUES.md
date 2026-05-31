# 量化策略问题跟踪

> 版本: 1.0 | 创建: 2026-05-31 | 状态: 进行中

---

## 一、问题列表

### 问题1: 交叉验证逻辑异常 ⚠️⚠️⚠️

| 字段 | 值 |
|------|-----|
| **ID** | Q-001 |
| **严重性** | P0 - 阻塞 |
| **发现时间** | 2026-05-31 |
| **来源** | v8_sop实验 |
| **状态** | 🔴 待修复 |

#### 问题描述

交叉验证通过率100%，而滚动窗口通过率<50%、MC p-value=1.0，检验结果互相矛盾。

#### 异常现象

```
滚动窗口通过率: <50%
蒙特卡洛 p-value: =1.0
交叉验证通过率: =100%  ← 异常！
```

#### 可能原因

1. **验证窗口重叠**：CV使用了重叠窗口，导致结果失真
2. **检验标准错误**：三个检验使用的指标不一致
3. **实现bug**：CV逻辑可能没有正确分割训练/验证期

#### 影响

- 无法判断策略是否真正有效
- 所有模型都被判定为"通过"，实际上全部过拟合失败

#### 参考解决方案

见章节二

---

### 问题2: 蒙特卡洛检验逻辑问题

| 字段 | 值 |
|------|-----|
| **ID** | Q-002 |
| **严重性** | P0 - 阻塞 |
| **发现时间** | 2026-05-31 |
| **来源** | v8_sop实验 |
| **状态** | 🔴 待修复 |

#### 问题描述

MC p-value=1.0，说明随机信号100%优于真实因子，但这是不合理的（除非随机信号构造有误）。

#### 异常现象

```
MC检验结果: p-value = 1.0
含义: 在500次随机模拟中，随机信号的表现总是优于真实因子
```

#### 可能原因

1. **随机信号过于宽松**：随机生成的信号可能过于简单/宽松
2. **比较指标错误**：比较的是单笔收益、夏普还是其他？
3. **样本量不足**：500次模拟可能不够

#### 参考解决方案

见章节二

---

### 问题3: 策略设计过于简单

| 字段 | 值 |
|------|-----|
| **ID** | Q-003 |
| **严重性** | P1 - 改进 |
| **发现时间** | 2026-05-31 |
| **来源** | v8_sop实验 |
| **状态** | 🟡 待优化 |

#### 问题描述

当前因子使用二值判断（非0即1），阈值固定，无法捕捉精细变化。

#### 当前实现

```python
# 二值判断
signal = df['close'] > df['BB_upper']  # True/False

# 固定阈值
MIN_SINGLE_TRADE = 0.008  # 0.8%
MIN_SHARPE = 0.5
MIN_WIN_RATE = 0.50
```

#### 改进方向

1. **连续值因子**：从0-1连续值代替二值判断
2. **动态阈值**：根据ETF历史波动率调整
3. **市场状态过滤**：添加趋势判断避免逆势交易

#### 参考解决方案

见章节二

---

### 问题4: ETF集中分布

| 字段 | 值 |
|------|-----|
| **ID** | Q-004 |
| **严重性** | P1 - 改进 |
| **发现时间** | 2026-05-31 |
| **来源** | v8_sop实验 |
| **状态** | 🟡 待优化 |

#### 问题描述

核心通过模型集中在512170(医疗)、588000(科创50)、512200(房地产)，策略缺乏通用性。

#### 分布数据

| ETF | 主题 | 通过数 |
|-----|------|:------:|
| 512170 | 医疗ETF华宝 | 30 |
| 588000 | 科创50ETF | 18 |
| 512200 | 房地产ETF | 11 |

#### 影响

- 策略只在特定行业ETF上有效
- 换到其他行业可能亏损
- 暴露于特定行业风险

#### 参考解决方案

见章节二

---

### 问题5: 验证期太短

| 字段 | 值 |
|------|-----|
| **ID** | Q-005 |
| **严重性** | P2 - 计划 |
| **发现时间** | 2026-05-31 |
| **来源** | v8_sop实验 |
| **状态** | 🟡 计划中 |

#### 问题描述

验证期从2025-06至今不足1年，样本外验证统计效力不足。

#### 当前配置

```
训练期: 2023-06-01 ~ 2025-05-31 (2年)
验证期: 2025-06-01 ~ 2026-05-31 (1年)
```

#### 改进方向

- 扩大验证期到至少2年
- 使用滚动窗口验证

---

## 二、参考解决方案（调研中）

### 2.1 交叉验证实现参考

**参考来源**：QuantConnect Lean Framework + sklearn + 学术文献

#### QuantConnect Walk-Forward 实现

```python
# 参考: QuantConnect Lean Framework
# 来源: https://github.com/quantconnect/Lean

class WalkForwardAlphaModel:
    """
    Walk-Forward Optimization:
    1. 在训练窗口上优化参数
    2. 在测试窗口上验证
    3. 滚动移动到下一个窗口
    """
    
    def GenerateAlpha(self, algorithm, date):
        # 使用前N天数据训练
        training_window = self.GetTrainingData(algorithm.Time, self.train_days)
        
        # 优化参数
        best_params = self.Optimize(training_window)
        
        # 在当前窗口应用
        return self.CreateAlpha(best_params)
```

**关键要点**：
- **非重叠窗口**：训练窗口和测试窗口必须不重叠
- **固定窗口大小**：每次移动固定步长
- **样本外验证**：只在测试窗口评估性能

#### sklearn TimeSeriesSplit

```python
# 参考: sklearn.model_selection.TimeSeriesSplit
# 来源: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

from sklearn.model_selection import TimeSeriesSplit

# 时间序列交叉验证
tscv = TimeSeriesSplit(n_splits=5, test_size=100)

for train_idx, test_idx in tscv.split(X):
    # train_idx: 训练集索引
    # test_idx: 测试集索引
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    
    # 训练和验证
    model.fit(X_train, y_train)
    score = model.score(X_test, y_test)
```

**关键要点**：
- 不打乱数据顺序
- 训练集始终在测试集之前
- 窗口逐步扩大

### 2.2 蒙特卡洛检验参考

**参考来源**：Michael L. Kirk's paper + 学术文献

#### Monte Carlo Permutation Test

```python
# 参考: 量化策略蒙特卡洛检验
# 来源: "Monte Carlo Statistical Tests for Strategy Evaluation"

def monte_carlo_permutation_test(real_returns, n_simulations=500):
    """
    置换检验:
    1. 计算真实策略的平均收益
    2. 随机打乱收益顺序n次
    3. 比较真实收益与随机收益分布
    """
    real_mean = np.mean(real_returns)
    
    random_means = []
    for _ in range(n_simulations):
        shuffled = np.random.permutation(real_returns)
        random_means.append(np.mean(shuffled))
    
    # p_value: 随机收益 >= 真实收益的比例
    p_value = np.mean([1 if m >= real_mean else 0 for m in random_means])
    
    return {
        'p_value': p_value,
        'real_mean': real_mean,
        'random_mean': np.mean(random_means),
        'significant': p_value < 0.05
    }
```

**问题诊断**：当前实现可能的问题：

| 问题 | 描述 | 修复方向 |
|------|------|----------|
| 随机信号构造错误 | 当前只是打乱收益顺序，没有生成真正的随机信号 | 生成独立的随机买入/卖出信号 |
| 比较指标错误 | 比较的是单笔收益，可能不够全面 | 同时比较夏普、最大回撤等 |
| 样本量不足 | 500次模拟可能不够 | 增加到1000次以上 |

#### 改进的MC检验实现

```python
def improved_monte_carlo_test(indicators_data, factors, etf_code, n_simulations=1000):
    """
    改进的蒙特卡洛检验:
    1. 获取真实信号和收益
    2. 生成n个随机信号（在随机日期生成买入信号）
    3. 比较真实策略与随机策略的性能
    """
    df = indicators_data[etf_code].copy()
    
    # 真实策略收益
    real_signal = get_combined_signal(df, factors)
    real_returns = calculate_strategy_returns(df, real_signal)
    
    random_returns_list = []
    
    for _ in range(n_simulations):
        # 随机生成信号（与真实信号长度相同）
        random_signal = generate_random_signal(len(df), p=real_signal.mean())
        
        # 计算随机策略收益
        random_returns = calculate_strategy_returns(df, random_signal)
        random_returns_list.append(np.mean(random_returns))
    
    # 计算p_value
    p_value = np.mean([1 if m >= np.mean(real_returns) else 0 
                       for m in random_returns_list])
    
    return {
        'p_value': p_value,
        'real_mean': np.mean(real_returns),
        'random_mean': np.mean(random_returns_list),
        'random_std': np.std(random_returns_list),
        'z_score': (np.mean(real_returns) - np.mean(random_returns_list)) / np.std(random_returns_list)
    }


def generate_random_signal(n_periods, p=0.1):
    """生成随机买入信号"""
    return np.random.random(n_periods) < p
```

### 2.3 因子精细化参考

**参考来源**：QuantConnect Alpha Framework + Zipline

#### 连续值因子 vs 二值判断

```python
# 当前实现（二值判断）
signal = df['close'] > df['BB_upper']  # True/False

# 改进实现（连续值 - 标准化到0-1）
def continuous_bollinger_factor(df, lookback=20):
    """
    布林带位置因子（连续值）
    返回价格在布林带中的相对位置: 0-1
    """
    bb_position = (df['close'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower'])
    return bb_position.clip(0, 1)  # 限制在0-1范围


def continuous_macd_factor(df):
    """
    MACD强度因子（连续值）
    返回MACD柱状图的标准化值
    """
    macd_hist = df['MACD_hist']
    macd_mean = macd_hist.rolling(20).mean()
    macd_std = macd_hist.rolling(20).std()
    return ((macd_hist - macd_mean) / (macd_std + 1e-8)).clip(-3, 3)
```

#### 动态阈值实现

```python
# 参考: Zipline Custom Factor
# 来源: https://github.com/quantopian/zipline

class DynamicThreshold:
    """根据历史波动率动态调整阈值"""
    
    def __init__(self, base_threshold, volatility_adjust=True):
        self.base_threshold = base_threshold
        self.volatility_adjust = volatility_adjust
    
    def get_threshold(self, df, lookback=60):
        if not self.volatility_adjust:
            return self.base_threshold
        
        # 计算历史波动率
        returns = df['close'].pct_change()
        volatility = returns.rolling(lookback).std()
        
        # 动态调整：如果波动率高，降低阈值（更严格）
        avg_vol = volatility.mean()
        current_vol = volatility.iloc[-1]
        
        adjustment = avg_vol / (current_vol + 1e-8)
        adjusted_threshold = self.base_threshold * adjustment
        
        # 限制调整范围
        return max(0.5 * self.base_threshold, min(1.5 * self.base_threshold, adjusted_threshold))
```

### 2.4 业界最佳实践总结

| 领域 | 最佳实践 | 来源 |
|------|----------|------|
| 交叉验证 | Walk-Forward + 非重叠窗口 | QuantConnect |
| MC检验 | 置换检验 + 多指标比较 | 学术文献 |
| 因子设计 | 连续值 + 标准化 | Zipline |
| 参数优化 | 滚动窗口 + 样本外验证 | 业界通用 |
| 过拟合检测 | 三层验证（滚动+MC+样本外） | Bailey et al. |

---

## 三、解决进度

| ID | 问题 | 状态 | 负责人 | 完成日期 |
|----|------|:----:|--------|----------|
| Q-001 | 交叉验证逻辑 | 🔴 待修复 | - | - |
| Q-002 | MC检验逻辑 | 🔴 待修复 | - | - |
| Q-003 | 策略设计 | 🟡 待优化 | - | - |
| Q-004 | ETF集中分布 | 🟡 待优化 | - | - |
| Q-005 | 验证期太短 | 🟡 计划中 | - | - |

---

## 四、相关文档

- `memory/experiment_20260531.md` - v8_sop实验报告
- `memory/retro_20260531.md` - v8_sop复盘反思
- `docs/SOP_03_EXPERIMENT.md` - SOP-03实验执行标准流程

---

*最后更新: 2026-05-31 23:50*