
测试覆盖度报告
============================================

更新时间: 2025-05-24

## 测试覆盖度

### 按模块统计

| 模块 | 测试用例 | 覆盖功能 |
|------|----------|----------|
| config | test_01_config | 参数配置、默认值 |
| data_loader | test_02_data_loader | 数据加载、数据过滤 |
| indicator | test_03_indicator | MA/RSI/MACD/量比计算 |
| selector | test_04_selector | 7因子打分、选股逻辑 |
| market_filter | test_05_market_filter | 市场涨跌判断 |
| trade | test_06_trade_executor | 基础交易执行 |
| trade (trailing) | test_06b_trailing_stop | 移动止盈逻辑 |
| metrics | test_07_metrics | 指标计算 |
| integration | test_08_integration | 完整回测流程 |
| factor_analysis | test_09_factor_analysis | IC/IR计算 |
| regression | test_regression.py | 回归验证 + 数据验证 |

### 测试统计

- 单元测试: 10个
- 回归测试: 1个 (含3个测试场景)
- 数据验证: 1项

### 功能覆盖

| 功能 | 测试状态 |
|------|----------|
| 参数配置 | ✅ 完整 |
| 数据加载 | ✅ 完整 |
| 指标计算 | ✅ 完整 |
| 7因子打分 | ✅ 完整 |
| 市场过滤 | ✅ 完整 |
| 基础交易 | ✅ 完整 |
| 移动止盈 | ✅ 完整 |
| 因子IC/IR | ✅ 完整 |
| 完整回测 | ✅ 完整 |
| 回归验证 | ✅ 完整 |

### 代码覆盖估计

| 文件 | 行数 | 测试覆盖 |
|------|------|----------|
| config.py | ~140 | 80% |
| data_loader.py | ~80 | 70% |
| indicator.py | ~50 | 90% |
| selector.py | ~110 | 70% |
| market_filter.py | ~70 | 80% |
| trade.py | ~230 | 75% |
| metrics.py | ~130 | 85% |
| factor_analysis.py | ~260 | 60% |
| backtest.py | ~110 | 60% |

---
