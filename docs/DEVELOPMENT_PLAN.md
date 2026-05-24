# ETF量化策略 - 开发计划

## 1. 概述

本计划将BUILD_REVIEW中的改进建议转化为可执行的任务清单，按优先级排序。

**排除项**: 实盘对接(券商API) - 复杂度高，需单独立项

---

## 2. 优先级 P1 - 高优先级

### P1.1 因子有效性分析 (IC/IR)

| 项目 | 内容 |
|------|------|
| 目标 | 量化7因子的预测能力，过滤无效因子 |
| 产出 | 因子IC/IR分析报告，优化因子权重 |

**技术方案**:
```python
# 因子IC计算
def calculate_ic(factor_values, forward_returns):
    """计算因子IC值"""
    return np.corrcoef(factor_values, forward_returns)[0, 1]

# 滚动IC
rolling_ic = returns.rolling(20).apply(lambda x: calculate_ic(factor, x))
ic_mean = rolling_ic.mean()
ic_ir = ic_mean / rolling_ic.std()  # 信息比
```

**任务拆解**:
- [ ] 1.1.1 实现因子IC计算函数
- [ ] 1.1.2 实现滚动IC统计 (20日/60日)
- [ ] 1.1.3 生成因子有效性报告
- [ ] 1.1.4 根据IC加权因子分数

---

### P1.2 行业集中度限制

| 项目 | 内容 |
|------|------|
| 目标 | 避免持仓过于集中在单一行业 |
| 约束 | 单行业持仓 <= 40% |

**技术方案**:
```python
# ETF行业映射（预先定义）
INDUSTRY_MAPPING = {
    '510300': '沪深300',  # 宽基
    '512880': '证券',     # 金融
    '512880': '新能源',   # 行业
    # ...
}

def check_industry_limit(positions, max_ratio=0.4):
    """检查行业集中度"""
    for industry, ratio in get_industry_ratio(positions).items():
        if ratio > max_ratio:
            return False
    return True
```

**任务拆解**:
- [ ] 1.2.1 建立ETF行业映射表 (54只)
- [ ] 1.2.2 实现行业占比计算
- [ ] 1.2.3 调仓时行业过滤
- [ ] 1.2.4 单元测试

---

### P1.3 移动止盈

| 项目 | 内容 |
|------|------|
| 目标 | 保护利润，让利润奔跑 |
| 规则 | 盈利超过10%后，启动移动止盈 |

**技术方案**:
```python
def check_trailing_stop(position, current_price):
    """移动止盈检查"""
    pnl = (current_price - position['cost']) / position['cost']
    
    if pnl > 0.10:  # 盈利超过10%
        # 移动止盈线 = 最高价回撤8%
        peak = position.get('peak_price', position['cost'])
        new_peak = max(peak, current_price)
        position['peak_price'] = new_peak
        
        # 回撤8%止盈
        if (current_price - new_peak) / new_peak <= -0.08:
            return 'trailing_stop'
    
    return None
```

**任务拆解**:
- [ ] 1.3.1 实现移动止盈逻辑
- [ ] 1.3.2 添加peak_price状态追踪
- [ ] 1.3.3 回测对比 (固定止盈 vs 移动止盈)
- [ ] 1.3.4 单元测试

---

### P1.4 交叉验证

| 项目 | 内容 |
|------|------|
| 目标 | 验证策略在不同时间段的稳定性 |
| 方法 | 多训练期窗口滚动验证 |

**技术方案**:
```python
# 滚动验证
windows = [
    ('2022-01-01~2024-12-31', '2025-01-01~2026-05-22'),  # 基准
    ('2022-01-01~2023-12-31', '2024-01-01~2025-01-01'),
    ('2023-01-01~2024-12-31', '2025-01-01~2026-01-01'),
]

def cross_validate(data, windows):
    results = []
    for train_start, train_end, test_start, test_end in windows:
        # 训练
        selected = train_model(data, train_start, train_end)
        # 测试
        result = backtest(data, selected, test_start, test_end)
        results.append(result)
    
    return analyze_stability(results)
```

**任务拆解**:
- [ ] 1.4.1 定义验证窗口
- [ ] 1.4.2 实现滚动验证框架
- [ ] 1.4.3 生成稳定性报告
- [ ] 1.4.4 可视化结果

---

## 3. 优先级 P2 - 中优先级

### P2.1 数据缓存机制

| 项目 | 内容 |
|------|------|
| 目标 | 避免每次运行重算指标，提升效率 |
| 方案 | 本地Pickle/Parquet缓存 |

**技术方案**:
```python
# 缓存管理器
class CacheManager:
    def __init__(self, cache_dir='.cache'):
        self.cache_dir = cache_dir
    
    def get_indicator(self, code, date):
        """获取缓存的指标数据"""
        cache_file = f"{self.cache_dir}/{code}_indicator.pkl"
        if os.path.exists(cache_file):
            cached = pd.read_pickle(cache_file)
            if date in cached:
                return cached[date]
        return None
    
    def save_indicator(self, code, df):
        """保存指标数据到缓存"""
        cache_file = f"{self.cache_dir}/{code}_indicator.pkl"
        df.to_pickle(cache_file)
```

**任务拆解**:
- [ ] 2.1.1 实现缓存管理器
- [ ] 2.1.2 数据加载时优先读缓存
- [ ] 2.1.3 缓存过期机制 (数据更新时刷新)
- [ ] 2.1.4 清理脚本

---

### P2.2 滑点/流动性模拟

| 项目 | 内容 |
|------|------|
| 目标 | 更真实的回测成本 |
| 参数 | 滑点0.1%, 大单冲击成本 |

**技术方案**:
```python
def apply_slippage(price, volume, side='buy'):
    """应用滑点和流动性成本"""
    base_slippage = 0.001  # 基础滑点万一
    
    # 大单冲击成本 (假设超过10万手有冲击)
    if volume > 100000:
        impact = 0.002  # 额外0.2%
    else:
        impact = 0
    
    total_cost = base_slippage + impact
    
    if side == 'buy':
        return price * (1 + total_cost)
    else:
        return price * (1 - total_cost)
```

**任务拆解**:
- [ ] 2.2.1 实现滑点计算函数
- [ ] 2.2.2 回测时应用滑点
- [ ] 2.2.3 对比有无滑点的结果差异

---

### P2.3 参数敏感性分析

| 项目 | 内容 |
|------|------|
| 目标 | 了解参数边界，避免过拟合 |
| 方法 | 参数网格搜索 + 敏感性图表 |

**技术方案**:
```python
def parameter_sensitivity():
    """参数敏感性分析"""
    params = {
        'rebalance_days': range(3, 16, 1),
        'score_threshold': range(4, 10, 1),
        'stop_loss': [-0.05, -0.08, -0.10, -0.15],
        'stop_gain': [0.10, 0.15, 0.20],
    }
    
    results = grid_search(params)
    plot_sensitivity(results)
    
    return find_robust_params(results)
```

**任务拆解**:
- [ ] 2.3.1 定义参数网格
- [ ] 2.3.2 实现网格搜索
- [ ] 2.3.3 生成敏感性图表
- [ ] 2.3.4 输出稳健参数区间

---

## 4. 优先级 P3 - 低优先级

### P3.1 信号推送

| 项目 | 内容 |
|------|------|
| 目标 | 实盘信号推送到钉钉/微信 |
| 触发 | 调仓、止盈止损时推送 |

**任务拆解**:
- [ ] 3.1.1 配置推送服务 (钉钉Bot)
- [ ] 3.1.2 封装消息模板
- [ ] 3.1.3 集成到回测结果

> 注: 实盘对接暂不开发

---

## 5. 开发顺序

```
阶段1 (第1-2周)
├── P1.1 因子有效性分析
├── P1.3 移动止盈
└── 代码review和优化

阶段2 (第3-4周)
├── P1.2 行业集中度限制
└── P1.4 交叉验证

阶段3 (第5-6周)
├── P2.1 数据缓存机制
├── P2.2 滑点/流动性模拟
└── 回归测试

阶段4 (第7-8周)
├── P2.3 参数敏感性分析
├── P3.1 信号推送
└── 最终优化
```

---

## 6. 验收标准

| 任务 | 验收条件 |
|------|----------|
| P1.1 | IC分析报告 + 加权打分 |
| P1.2 | 单行业<=40%约束生效 |
| P1.3 | 移动止盈逻辑通过测试 |
| P1.4 | 3个时间窗口验证通过 |
| P2.1 | 缓存命中时提速>50% |
| P2.2 | 滑点成本记录在案 |
| P2.3 | 敏感性图表生成 |
| P3.1 | 推送消息格式正确 |

---

## 7. 文件变更追踪

| 任务 | 修改文件 |
|------|----------|
| P1.1 | src/selector.py, docs/因子分析.md |
| P1.2 | src/config.py, src/trade.py, data/industry_mapping.json |
| P1.3 | src/trade.py |
| P1.4 | tests/test_cross_validation.py |
| P2.1 | src/cache.py, src/data_loader.py |
| P2.2 | src/trade.py |
| P2.3 | scripts/sensitivity_analysis.py |
| P3.1 | src/notification.py |

---

*计划版本: 1.0*
*创建时间: 2025-05-24*
*预计周期: 8周*