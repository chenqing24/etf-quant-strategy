# v1 → v2 迁移指南

**归档日期**：2026-06-20
**v1 最终快照**：[`v1-deprecated-v2-refactor`](https://github.com/chenqing24/etf-quant-strategy/releases/tag/v1-deprecated-v2-refactor)
**v2 仓库**：https://github.com/chenqing24/etf-quant-v2 （待创建）

---

## 一、为什么重构

v1（etf_strategy）经过 US-001 ~ US-030 共 30 个迭代后，出现以下结构性瓶颈：

1. **模块耦合严重**：50+ 文件散落在 src/，跨模块引用密集（src.cli → src.data → src.core → src.analysis）
2. **数据层不统一**：etf_data_live/（CSV）+ data/（SQLite）+ src/data/*（自定义）三套并行
3. **因子散落**：因子逻辑分散在 src/indicators/ + scripts/factor_mining/ + src/strategy/ 三处
4. **测试难以维护**：E2E 测试依赖真实网络 + 真实数据库，CI 经常 flaky
5. **触发词不可发现**：v1 skill `etf-quant-decision` 在 QwenPaw workspace 中是单一入口，无法拆分（每日 / 回测 / 个股 / 持仓）

v2 的目标是解决以上问题，并以**业务完整性**为第一标准（不只是接口契约）。

---

## 二、核心差异（v1 vs v2）

| 维度 | v1 (`etf_strategy`) | v2 (`etf_quant_v2`) |
|------|---------------------|---------------------|
| **因子数量** | 7 因子 | 27 因子 + W4 RV 反转因子 |
| **因子实现** | `src/indicators/`（v1 自实现） | `src/etf_quant/alpha/factors/inherited.py`（22 个自重写）+ 4 个新增（b1_boll/v1_volume/t1_macd/w4_rv） |
| **数据层** | etf_data_live/CSV + data/SQLite 多源 | `data/etf.db`（SQLite 唯一）+ DataLoader/DataWriter 统一入口 |
| **业务模块** | 50+ 文件（src/cli/decision.py 等） | 13 模块（alpha/portfolio/risk/notify/data_layer/universe/scheduler/monitor/performance/utils 等） |
| **测试** | E2E 依赖网络 + DB，CI flaky | 217/217 测试全过（unit/integration/regression）+ 5 benchmark，8 维自检 100/100 |
| **触发词** | 1 个 skill（`etf-quant-decision`） | 5 个 skill（etf-daily/etf-research/quant-knowledge/stock-analyze/stock-portfolio） |
| **cron** | cron_etf.txt（macOS 路径） | scheduler 模块 + 4 个默认 jobs |
| **业务完整性** | 接口契约通过 | 业务实现 100%（29/29 US） |

---

## 三、因子演进（7 → 27 + W4 RV）

### v1 的 7 因子
1. MA 趋势
2. 动量
3. RSI
4. MACD
5. 成交量
6. ATR
7. 布林带

### v2 的 27 因子 + W4 RV

**继承（22 个，从 v1 公式重写）**：
- T2 MA 多头, T3 SAR 趋势, T4 ADX 趋势
- M1 动量 3 日, M2 动量 5 日, M3 动量 10 日, M4 RSI, M5 KDJ, M6 MACD 差值
- V2 OBV, V3 MAOBV, V4 量比
- W1 ATR, W2 布林带宽, W3 波动率
- ... (共 22 个，详见 `src/etf_quant/alpha/factors/inherited.py`)

**新增（4 个，v2 独有）**：
- **B1 布林带突破**：突破上轨/跌破下轨（bollinger bands breakout）
- **V1 量价背离**：价涨量缩 / 价跌量增（volume-price divergence）
- **T1 MACD 交叉**：MACD 金叉/死叉（MACD crossover）
- **W4 RV 反转因子**：Realized Variance 反转效应（OOS/IS = 0.90）

**业界公式参考**（按规则 13）：
- Murphy 1999 *Technical Analysis of Financial Markets*
- Bollinger 1980s 布林带
- Wilder 1978 *New Concepts in Technical Trading* (RSI/ADX/SAR/ATR)
- Appel 1970s MACD
- Granville 1963 OBV

---

## 四、模块演进（v1 50+ 文件 → v2 13 模块）

### v1 结构（src/）
```
src/
├── analysis/      (report_generator.py, performance_analyzer.py)
├── backtest/      (engine.py)
├── cli/           (decision.py)
├── config/
├── core/          (selector.py, backtest.py)
├── cross_validation.py
├── data/          (fetcher.py, loader.py, manager.py, monitor.py, router.py, writer.py)
├── data_loader.py
├── dingtalk_sender.py
├── etf_data_live/
├── etf_pool_updater.py
├── evaluation/
├── experiments/
├── factor_analysis.py
├── factor_report.py
├── indicator.py
├── indicators/    (v1 自实现因子)
├── industry_filter.py
├── industry_mapping.py
├── notifier.py
├── notify/
├── performance_analyzer.py
├── report_builder.py
├── report_generator.py
├── risk/
├── scenario_adapter.py
├── sensitivity_analysis.py
├── sensitivity_chart.py
├── strategy/      (macd_strategy.py)
├── trade/
├── trade_tracker.py
├── trend_chart.py
└── utils/
```

### v2 结构（src/etf_quant/）
```
src/etf_quant/
├── alpha/         (27 因子 + W4 RV，factor_base + registry + factors/)
├── portfolio/     (Portfolio + Holding)
├── risk/          (risk_manager)
├── notify/        (dingtalk + notifier + scenario)
├── data_layer/    (DataLoader + DataWriter + DataSourceRouter，SQLite 唯一)
├── universe/      (ETFListLoader + filter + mapper，1486 ETF/14 核心)
├── scheduler/     (cron + config，4 默认 jobs)
├── monitor/       (data_health + system_health + business_alert)
├── performance/   (metrics + report，8 大类 43 指标)
└── utils/
```

---

## 五、数据层演进

### v1（多源并行）
- `etf_data_live/*.csv`：原始 K 线数据
- `etf_data_live/*.json`：缓存
- `data/etf_factors.db`：因子计算结果
- `data/experiments/`：实验数据
- `src/data/fetcher.py`：腾讯 API 拉取
- `src/data/loader.py`：多源加载
- `src/data/manager.py`：数据管理

**问题**：同一只 ETF 可能在 CSV 和 SQLite 各有一份，数据一致性难保证。

### v2（SQLite 唯一）
- `data/etf.db`：唯一数据源（K 线 + 因子 + ETF 元数据 + 池角色）
- `src/etf_quant/data_layer/DataLoader`：统一读取入口
- `src/etf_quant/data_layer/DataWriter`：统一写入入口
- `src/etf_quant/data_layer/DataSourceRouter`：数据源路由

**优势**：
- 一份数据一个位置，避免不一致
- 血缘追踪（哪个数据从哪个 API 来）
- 维护成本低（不用同步多份）

---

## 六、测试演进

| 维度 | v1 | v2 |
|------|----|----|
| 测试总数 | ~50（E2E 为主） | 217/217（unit + integration + regression） |
| 单元测试 | 少（多为 E2E） | 159（核心模块全覆盖） |
| 集成测试 | ~20 | 32 |
| 回归测试 | 无 | 26（W4 RV OOS/IS=0.90 等） |
| E2E | ~30（依赖网络 + DB） | 0（纯本地数据） |
| Benchmark | 无 | 5（pytest-benchmark） |
| 8 维自检 | 无 | 100/100（脚本化） |

---

## 七、SKILL 演进

### v1（1 个 skill）
```
~/.qwenpaw/workspaces/default/skills/etf-quant-decision/
└── SKILL.md   # 单入口，覆盖 daily/eval/trade/history/perf
```

**问题**：单一 skill 无法拆分（每日 vs 回测 vs 个股 vs 持仓的语义不同）

### v2（5 个 skill，按职责拆分）
```
~/.qwenpaw/workspaces/default/skills/
├── etf-daily/         # 每日决策 + 评估 + 历史
├── etf-research/      # 回测 + 验证 + 评分
├── quant-knowledge/   # 策略 + 教训 + 业界参考
├── stock-analyze/     # 个股 vs 板块 vs 大盘
└── stock-portfolio/   # 持仓组合 + 再平衡 + 业绩归因
```

---

## 八、迁移步骤（已完成）

1. ✅ **Sprint-0 ~ Sprint-7** 共 7 个 sprint、29 个 US、217/217 测试全过
2. ✅ **数据迁移**：v1 的 71034 行数据迁移到 v2 `data/etf.db`（脚本 `scripts/migrate_data.py`）
3. ✅ **因子重写**：v1 `src/indicators/` 的 22 个因子在 v2 `src/etf_quant/alpha/factors/inherited.py` 自重写
4. ✅ **业务实现**：5 个模块从接口契约升级到业务完整实现（universe/scheduler/monitor/performance/notify）
5. ✅ **v1 GitHub tag**：`v1-deprecated-v2-refactor`（annotated，sha=b2d3e8b）
6. ✅ **v1 README**：已加 ⚠️ 横幅 + 指向 v2
7. ✅ **v1 备份**：完整版 zip 保存在 `/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy_v1_full_backup_20260620.zip`
8. ✅ **v1 本地仓删除**：`/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy/`
9. ✅ **定时任务暂停**：cron_etf.txt 随 v1 仓删除
10. ✅ **v2 SKILL 注册**：5 skill 软链接到 `~/.qwenpaw/workspaces/default/skills/`

---

## 九、常见问题

### Q1：v1 仓删除后，我还能查 v1 历史数据吗？
**A**：可以。完整版 zip 备份在 `/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy_v1_full_backup_20260620.zip`（含 .db 数据）。如需解压查看：`unzip etf_strategy_v1_full_backup_20260620.zip -d /tmp/v1_review/`。

### Q2：v1 GitHub 还能访问吗？
**A**：可以。https://github.com/chenqing24/etf-quant-strategy 保留全部 548 个 commits + 8 个 tag（含 `v1-deprecated-v2-refactor`）。可作为历史档案查询。

### Q3：v2 如何确保不依赖 v1？
**A**：已验证。临时 `mv etf_strategy _HIDDEN_v1` 后，v2 仓内 `pytest` 217/217 测试 + 5 skill + 11 业务模块全过。v2 是独立 git 仓（不是从 v1 clone），起点 commit `d8b4240` 与 v1 无关。

### Q4：v2 的因子和 v1 完全相同吗？
**A**：公式相同（业界标准），但实现细节有差异：
- v1: 散落在 `src/indicators/`（函数式）
- v2: 集中在 `src/etf_quant/alpha/factors/inherited.py`（类继承 `FactorBase`）
- v2 新增 4 个因子：B1/V1/T1/W4 RV（v1 没有）

### Q5：v1 的 cron 任务还会在 v2 中执行吗？
**A**：不会。v1 的 `cron_etf.txt` 已随 v1 仓删除。v2 有独立的 scheduler 模块（`src/etf_quant/scheduler/cron.py`），需要重新配置。

---

## 十、参考来源

- Sprint-7 业务完整化报告：`docs/MISSION_FINAL_REPORT_20260620.md`
- v2 仓 README：`/home/qwenpaw/.qwenpaw/workspaces/default/etf_quant_v2/README.md`
- v2 PRD：`/home/qwenpaw/.qwenpaw/workspaces/default/etf_quant_v2/docs/PRD.json`
- 审计报告：`/home/qwenpaw/.qwenpaw/workspaces/default/etf_quant_v2/docs/AUDIT_REPORT_20260620.md`
- SKILL 路由审计：`/home/qwenpaw/.qwenpaw/workspaces/default/etf_quant_v2/docs/SKILL_ROUTING_AUDIT_20260620.md`

---

**归档人**：福猫管家 🐱
**归档时间**：2026-06-20