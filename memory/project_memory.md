# ETF量化策略项目 - 项目专属记忆

> 版本: 1.0 | 更新: 2026-05-31

---

## 实验记录

| 版本 | 日期 | 核心发现 | 状态 |
|------|------|----------|------|
| v8.0_sop | 2026-05-31 | MC p-value=1.0, 策略过拟合, Top10集中在512200 | ⚠️失败 |

### v8_sop实验总结

**SOP-03完整执行结果：**

| Phase | 内容 | 状态 |
|-------|------|:-----:|
| Phase 1 | 实验设计 | ✅ |
| Phase 2 | 数据准备 | ✅ |
| Phase 3 | 单因子测试+IC/IR | ✅ |
| Phase 4 | 组合测试(4125条) | ✅ |
| Phase 4.5 | 2因子过拟合检验 | ✅ |
| Phase 4.7 | 3因子过拟合检验 | ✅ |
| Phase 5-7 | 报告+归档 | ✅ |

**关键发现：**

1. **单因子IC/IR排名**：
   - B1_布林上轨突破: IC=0.0484, IR=0.99 ✅最优
   - V1_放量: IC=0.0369, IR=0.84 ✅
   - T1_MACD红柱: IC=0.0423, IR=1.44 ✅
   - T3_SAR趋势: IC=0.0252, IR=1.02 ✅
   - T4_ADX趋势: IC=0.0248, IR=0.77 ✅
   - M2_动量5日: IC=0.0186, IR=0.89 ✅

2. **过拟合检验失败**：
   - 核心通过: 90个
   - 过拟合通过: 0个
   - MC p-value=1.0说明随机信号优于真实因子

3. **Top10模型异常**：
   - 全部集中在512200（有色金属ETF）
   - 策略不具备跨ETF通用性

**核心结论：v8策略过拟合，无样本外有效性**

---

## 核心工具索引

| 工具 | 文件 | 用途 |
|------|------|------|
| DataLoader | `src/data/loader.py` | ETF历史数据加载 |
| IndicatorCalculator | `src/indicators/wrapper.py` | 技术指标计算 |
| FactorBacktester | `src/backtest/engine.py` | 策略回测验证 |
| experiment_v8_sop.py | `scripts/experiment_v8_sop.py` | v8 SOP实验脚本 |

---

## SOP文档索引

| SOP | 文件 | 用途 |
|-----|------|------|
| SOP-01 | `docs/SOP_01_DATA_MINING.md` | 因子挖掘完整流程 |
| SOP-02 | `docs/SOP_02_REFACTOR_DEV.md` | 重构与修复开发流程 |
| SOP-03 | `docs/SOP_03_EXPERIMENT.md` | 实验执行标准流程 |
| SOP-04 | `docs/SOP_04_DATA_SOURCE.md` | 数据源接入与验证标准流程 |
| SOP-INDEX | `docs/SOP_INDEX.md` | SOP文档索引 |

---

## 实验数据位置

| 目录 | 内容 |
|------|------|
| `data/experiments/` | 历史实验结果（v1-v10） |
| `data/experiments_v8_sop/` | v8_sop实验结果 |
| `memory/` | 实验笔记归档 |

---

*最后更新: 2026-05-31 23:30*