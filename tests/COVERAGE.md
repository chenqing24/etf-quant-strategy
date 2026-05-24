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
| selector | test_04_selector | 7因子打分、IC加权、选股逻辑 |
| market_filter | test_05_market_filter | 市场涨跌判断 |
| trade | test_06_trade_executor | 基础交易执行 |
| trade (trailing) | test_06b_trailing_stop | 移动止盈逻辑 |
| metrics | test_07_metrics | 指标计算 |
| integration | test_08_integration | 完整回测流程 |
| factor_analysis | test_09_factor_analysis | IC/IR计算 |
| trailing_stop | test_10_trailing_stop | 移动止盈回测 |
| cross_validation | test_11_cross_validation | 滚动验证框架 |
| cache | test_12_cache | 缓存管理器 |
| trading_cost | test_13_trading_cost | 滑点计算、成本模拟 |
| sensitivity | test_14_sensitivity | 参数网格搜索 |
| notifier | test_15_notifier | 信号推送、消息模板 |
| industry_filter | test_16_industry_filter | 行业集中度过滤 |
| sensitivity_chart | test_17_sensitivity_chart | 敏感性图表可视化 |
| slippage_config | test_18_slippage_config | 滑点配置 |

### 测试统计

- 单元测试: 18个
- 回归测试: 3个 (含3个测试场景)

### 功能覆盖

| 功能 | 测试状态 |
|------|----------|
| 参数配置 | ✅ 完整 |
| 数据加载 | ✅ 完整 |
| 指标计算 | ✅ 完整 |
| 7因子打分 | ✅ 完整 |
| IC加权打分 | ✅ 完整 |
| 市场过滤 | ✅ 完整 |
| 基础交易 | ✅ 完整 |
| 移动止盈 | ✅ 完整 |
| 因子IC/IR | ✅ 完整 |
| 交叉验证 | ✅ 完整 |
| 缓存机制 | ✅ 完整 |
| 交易成本/滑点 | ✅ 完整 |
| 行业过滤 | ✅ 完整 |
| 参数敏感性 | ✅ 完整 |
| 信号推送 | ✅ 完整 |
| 完整回测 | ✅ 完整 |
| 回归验证 | ✅ 完整 |

### 代码覆盖估计

| 文件 | 行数 | 测试覆盖 |
|------|------|----------|
| config.py | ~160 | 95% |
| data_loader.py | ~120 | 90% |
| indicator.py | ~150 | 95% |
| selector.py | ~250 | 95% |
| market_filter.py | ~80 | 90% |
| trade.py | ~230 | 95% |
| backtest.py | ~140 | 90% |
| metrics.py | ~100 | 95% |
| factor_analysis.py | ~120 | 90% |
| cross_validation.py | ~150 | 90% |
| cache.py | ~100 | 90% |
| trading_cost.py | ~180 | 95% |
| sensitivity_analysis.py | ~150 | 90% |
| notifier.py | ~150 | 90% |
| industry_filter.py | ~180 | 90% |
| sensitivity_chart.py | ~200 | 85% |

### 新增测试项 (阶段3.5)

- test_16: 行业集中度过滤
- test_17: 敏感性图表 (matplotlib)
- test_18: 滑点配置

### 测试运行

```bash
# 单元测试
python tests/test_all.py

# 回归测试
python tests/test_regression.py

# 完整测试
pytest tests/
```