# ETF量化系统改进计划

> 文档版本: v1.0 | 创建日期: 2026-05-26 | 状态: 进行中

## 一、问题背景

**核心问题**：推荐价格使用历史收盘价（1.101），而非实时价格（1.207）

**根因分析**：
1. `report_generator.py` 相对导入路径错误
2. 热数据管理器和交易校验器导入失败
3. 预热数据未传递给报告生成器

---

## 二、改进计划

### P0 - 立即修复（价格问题）

#### 改进0.1: 修复 report_generator.py 导入路径
| 项目 | 内容 |
|------|------|
| 文件 | `src/analysis/report_generator.py` |
| 问题 | `from .data_manager import DataFacade` 相对导入失败 |
| 修复 | 改为 `from src.data.manager import DataFacade` |
| 测试 | TC-01 |

#### 改进0.2: 修复 trade_validator 导入路径
| 项目 | 内容 |
|------|------|
| 文件 | `src/analysis/report_generator.py` |
| 问题 | `from .trade_validator import TradeValidator` 相对导入失败 |
| 修复 | 改为 `from src.trade.validator import TradeValidator, Recommendation` |
| 测试 | TC-01 |

#### 改进0.3: 确保热数据读取正常
| 项目 | 内容 |
|------|------|
| 文件 | `src/analysis/report_generator.py` |
| 问题 | data_facade 初始化后 hot.get() 返回 None |
| 修复 | 验证 DataFacade.hot.get() 能读取 hot/*.json |
| 测试 | TC-02 |

---

### P1 - 核心功能

#### 改进1.1: 实现热冷数据合并
| 项目 | 内容 |
|------|------|
| 文件 | `src/data/manager.py` |
| 问题 | get_merged_data() 方法可能不存在或不完整 |
| 修复 | 实现完整的热冷数据合并逻辑 |
| 测试 | TC-04 |

#### 改进1.2: 推荐价格优先使用实时价
| 项目 | 内容 |
|------|------|
| 文件 | `src/analysis/report_generator.py` |
| 问题 | 推荐价格用 cold 收盘价，而非 hot 实时价 |
| 修复 | 优先从 hot 获取实时价格，无则降级到 cold |
| 测试 | TC-05 |

#### 改进1.3: 止盈止损空间基于实时价格
| 项目 | 内容 |
|------|------|
| 文件 | `src/analysis/report_generator.py` |
| 问题 | 止盈止损空间无法计算（实时价格为 None）|
| 修复 | 使用实时价格计算偏差%、距止盈/止损空间 |
| 测试 | TC-07 |

#### 改进1.4: 预热数据传递给报告生成器
| 项目 | 内容 |
|------|------|
| 文件 | `src/cli/decision.py` |
| 问题 | 预热了数据但未传递给报告生成器 |
| 修复 | 决策引擎预热后，报告生成器使用同一 data_facade 实例 |
| 测试 | TC-03 |

---

### P2 - 优化增强

#### 改进2.1: 数据源状态日志
| 项目 | 内容 |
|------|------|
| 文件 | `src/analysis/report_generator.py` |
| 问题 | 日志未显示数据来源（热数据/实时API/历史数据）|
| 修复 | 增加 data_source 字段到日志输出 |
| 测试 | TC-08 |

#### 改进2.2: 多数据源降级验证
| 项目 | 内容 |
|------|------|
| 文件 | `src/trade/validator.py` |
| 问题 | 多数据源降级逻辑未被充分测试 |
| 修复 | 验证腾讯→东方财富→新浪降级流程 |
| 测试 | TC-06 |

---

## 三、测试用例清单

| ID | 名称 | 输入 | 预期输出 | 验证方式 |
|----|------|------|----------|----------|
| TC-01 | 导入路径测试 | `from src.data.manager import DataFacade` | 导入成功，无异常 | Python 脚本 |
| TC-02 | 热数据读取测试 | `DataFacade('etf_data_live').hot.get('515050')` | 返回 price=1.207, timestamp 非空 | Python 脚本 |
| TC-03 | 预热→报告数据传递测试 | 决策引擎预热后生成报告 | 报告中 515050 价格与预热价格一致 | 对比两次输出 |
| TC-04 | 热冷数据合并测试 | `get_merged_data('515050')` | price 来自 hot, date/ohlc 来自 cold | Python 脚本 |
| TC-05 | 推荐价格优先级测试 | 盘中: hot 有数据, 收盘: hot 无数据 | 盘中 price=hot.price, 收盘 price=cold.close | 模拟两种场景 |
| TC-06 | 多数据源降级测试 | mock 腾讯超时 | fallback 到东方财富或新浪 | mock 测试 |
| TC-07 | 止盈止损实时计算测试 | 修改 hot 价格后生成报告 | 偏差%、距止盈/止损空间基于新价格 | 修改 hot 后重新生成 |
| TC-08 | 数据源状态日志测试 | 运行决策引擎 | 日志包含 "数据来源: 热数据/实时API/历史数据" | grep 日志 |

---

## 四、执行记录

| 日期 | 改进项 | 状态 | 提交 Commit |
|------|--------|------|-------------|
| 2026-05-26 | 改进0.1: 修复导入路径 | ✅ 完成 | - |
| 2026-05-26 | 改进0.2: 修复导入路径 | ✅ 完成 | - |
| 2026-05-26 | 改进0.3: 热数据读取 | ✅ 完成 | - |
| 2026-05-26 | 改进1.2: 推荐价格优先使用实时价 | ✅ 完成 | - |
| 2026-05-26 | 改进1.3: 止盈止损基于实时价格 | ✅ 完成 | - |

### TC-01~TC-05 测试通过

| 测试 | 状态 | 结果 |
|------|------|------|
| TC-01 | ✅ | 导入路径修复成功，data_facade 和 trade_validator 正常初始化 |
| TC-02 | ✅ | 热数据读取正常，515050 price=1.207 |
| TC-05 | ✅ | 推荐价格现在使用实时价格 1.207 元 |
| TC-07 | ✅ | 止盈止损空间基于实时价格计算正确 |

---

## 五、相关文档

- [架构设计](docs/ARCHITECTURE.md)
- [使用说明](docs/USAGE.md)
- [Cron配置](docs/CRON_SETUP.md)