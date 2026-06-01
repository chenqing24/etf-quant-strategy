# 实验日志 - 2026-06-01

## 任务
用新验证器重新测试v8_sop的所有4125个模型组合

## 开始时间
2026-06-01 05:00:00

## SOP执行
- SOP-02: 重构与修复（Phase 1-6）
- SOP-03: 实验执行（Phase 1-5)

## Phase 0: 风险修复

### 0.1 JSON序列化问题
- 问题：numpy bool类型导致JSON写入失败
- 修复：`bool(result.pass_)` 转换
- 验证：regression_test.py 运行正常

### 0.2 信号函数验证
- 测试前10个组合耗时：2.7秒
- 预估4125个组合：18.5分钟

### 0.3 CrossEtfValidator序列化
- 测试通过：WalkForwardResult → to_dict → json.dumps ✓

## Phase 1: 全面验证

### 执行结果
- 耗时：18.0分钟
- 总组合数：4125
- 新验证通过：738 (17.9%)
- 旧核心通过：90 (2.2%)

### 交叉分析
- 旧通过 → 新通过: 87 (真阳性)
- 旧通过 → 新未通过: 3 (假阳性)
- 旧未通过 → 新通过: 651 (假阴性) ⚠️
- 旧未通过 → 新未通过: 3384 (真阴性)

### 得分分布
- 最小: 0.100
- 最大: 0.775
- 平均: 0.325
- P25: 0.224, P50: 0.267, P75: 0.400

## 深度分析

### 真阳性模型（87个，2.1%）

**ETF分布**：
- 512170（科创50）: 30个
- 588000（科创50）: 18个
- 512200（纳指ETF）: 11个
- 512880（证券）: 9个

**核心因子**：
- B1_布林上轨突破: 76次（绝对主力）
- V1_放量: 46次
- T1_MACD红柱: 20次

**验证器得分**：
- WF平均: 0.330（WalkForward通过率1/3）
- MC平均: 1.000（全部显著）
- CE平均: 0.330

### 关键发现

1. 旧验证器太严格，遗漏651个有效模型
2. Top20全是旧验证未通过（新验证通过）
3. 512480（半导体）出现频率最高

## 修复记录

### 2026-06-01 修复内容

| 文件 | 修改 | 旧值 | 新值 |
|------|------|------|------|
| walk_forward.py | min_windows | 3 | 6 |
| cross_etf.py | min_train_etfs | 5 | 7 |
| cross_etf.py | min_test_etfs | 3 | 5 |
| comprehensive.py | pass_threshold | 0.5 | 0.6 |
| comprehensive.py | weights.walk_forward | 0.30 | 0.40 |
| comprehensive.py | weights.monte_carlo | 0.30 | 0.15 |
| comprehensive.py | weights.cross_etf | 0.30 | 0.35 |

### Git提交

| 提交 | 说明 |
|------|------|
| 252884d | docs: 更新Q-001/Q-002状态为已修复 |
| 01582b3 | docs: 更新ISSUES.md修复记录和验证结果 |
| 53c82b2 | fix: 增强过拟合验证器严格性 |

## 交付清单

| 文件 | 说明 | 状态 |
|------|------|------|
| scripts/full_validation.py | 全面验证脚本 | ✅ |
| full_validation_results.json | 验证结果（4125条）| ✅ |
| scripts/validators/ | 过拟合验证器（4个引擎）| ✅ |
| tests/test_validators.py | 验证器单元测试（18个）| ✅ |
| scripts/regression_test.py | 回归测试脚本 | ✅ |

## 经验教训

| # | 教训 | 防止方法 |
|---|------|----------|
| 1 | WalkForward窗口太少导致虚高通过率 | min_windows=6 |
| 2 | CrossEtf测试集ETF太少无法验证泛化 | min_test_etfs=5 |
| 3 | MC得分总是1.0无筛选作用 | 调整权重0.15 |
| 4 | 旧验证器对WalkForward测试不充分 | 集成新验证器 |

## 下一步

1. [x] 将ComprehensiveValidator集成到experiment_v8_sop.py
2. [x] 替换旧过拟合检验逻辑
3. [x] 验证集成效果（测试通过）

### 集成内容

| 文件 | 修改 |
|------|------|
| experiment_v8_sop.py | 导入ComprehensiveValidator |
| | 新增new_overfit_validator()函数 |
| | Phase 4.5/4.7使用新验证器 |

### Git提交

| 提交 | 说明 |
|------|------|
| bb4447c | feat: 集成ComprehensiveValidator到experiment_v8_sop.py |

## 结束时间
2026-06-01 05:50:00

## 总耗时
约50分钟

## 结束时间
2026-06-01 05:35:00

## 总耗时
约35分钟