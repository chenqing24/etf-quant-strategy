# ETF量化系统 - 完整架构文档 v3.0

> 更新: 2026-05-28 | 基于实际代码结构梳理

---

## 一、整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户交互层                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ CLI命令行    │  │ Skill技能   │  │ Cron定时    │  │ 钉钉通知    │    │
│  │ decision.py │  │ etf_quant   │  │ 每日2:30   │  │ 渠道推送    │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
└─────────┼────────────────┼────────────────┼────────────────┼───────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           决策引擎层                                      │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    ETFDecisionEngine                              │ │
│  │              (每日检查 / 完整评估 / 调仓决策)                      │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    数据层        │  │    策略层        │  │    通知层        │
│  DataLayer      │  │  StrategyLayer  │  │  NotifyLayer    │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   DataFacade    │  │  BacktestEngine │  │  SignalNotifier │
│   (统一入口)    │  │  (回测引擎)     │  │  (信号通知)     │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ DataSourceRouter│  │   FactorScorer  │  │  ScenarioAdapter│
│ (采集路由器)    │  │   (因子评分)    │  │  (场景适配)     │
└────────┬────────┘  └────────┬────────┘  └─────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│  外部API        │  │   TradeExecutor │
│ (腾讯/新浪/东财)│  │   (交易执行)   │
└─────────────────┘  └─────────────────┘
```

---

## 二、目录结构

```
etf_strategy/
├── src/
│   ├── cli/
│   │   └── decision.py          # CLI命令行入口
│   │
│   ├── data/                    # 数据层
│   │   ├── manager.py           # DataFacade + HotDataManager + ColdDataManager
│   │   ├── fetcher.py           # DataSourceRouter (采集路由)
│   │   ├── loader.py            # DataLoader (旧接口)
│   │   ├── facade.py            # DataFacade (别名)
│   │   ├── database.py          # 数据库操作
│   │   ├── cache.py             # 缓存管理
│   │   ├── router.py            # 路由(别名)
│   │   ├── code_mapper.py       # 代码映射
│   │   └── data_importer.py     # 数据导入
│   │
│   ├── strategy/                # 策略层
│   │   ├── engine.py            # BacktestEngine (回测引擎)
│   │   ├── config.py            # BacktestConfig (配置)
│   │   ├── scorer.py            # FactorScorer (因子评分)
│   │   ├── executor.py          # TradeExecutor (交易执行)
│   │   ├── store.py             # quick_run (便捷函数)
│   │   └── metrics.py           # 绩效指标计算
│   │
│   ├── indicators/              # 指标计算
│   │   ├── base.py              # 基础类
│   │   ├── adx.py               # ADX指标
│   │   ├── bollinger.py         # 布林带指标
│   │   ├── sar.py               # SAR指标
│   │   ├── macd.py              # MACD指标
│   │   ├── kdj.py               # KDJ指标
│   │   ├── rsi.py               # RSI指标
│   │   ├── obv.py               # OBV指标
│   │   ├── dma.py               # DMA指标
│   │   └── wrapper.py           # 指标包装器
│   │
│   ├── notify/                  # 通知层
│   │   ├── notifier.py          # SignalNotifier (信号通知)
│   │   ├── dingtalk.py          # 钉钉发送
│   │   └── scenario.py          # ScenarioAdapter (场景适配)
│   │
│   ├── trade/                   # 交易记录
│   │   └── tracker.py           # TradeTracker (交易追踪)
│   │
│   ├── analysis/                # 分析模块
│   │   ├── report_generator.py  # 决策报告生成
│   │   ├── performance_analyzer.py  # 绩效分析
│   │   └── ...
│   │
│   ├── utils/                   # 工具模块
│   │   ├── logger.py            # 日志
│   │   ├── config.py            # 配置
│   │   └── industry.py          # 行业
│   │
│   ├── constants.py             # 常量定义
│   ├── etf_pool_updater.py     # ETF池更新
│   ├── factor_analysis.py      # 因子分析
│   ├── cross_validation.py     # 交叉验证
│   └── sensitivity_analysis.py # 敏感性分析
│
├── scripts/                     # 数据脚本
│   ├── daily_data_check.py     # 每日数据检查
│   ├── repair_data.py          # 数据修复
│   ├── prefetch_data.py        # 数据预获取
│   ├── migrate_csv_to_sqlite.py # CSV迁移
│   └── ...
│
├── tests/                       # 测试
├── docs/                        # 文档
├── data/
│   ├── experiments/             # 实验结果
│   ├── etf_pool.json            # ETF股票池
│   └── etf_data_live/           # 数据目录
│       ├── hot/                 # 热数据(JSON)
│       ├── etf.db               # SQLite数据库
│       └── ...
└── etf_quant_decision_skill.md  # Skill定义
```

---

## 三、模块依赖关系

### 3.1 数据流依赖

```
用户请求
    │
    ▼
cli/decision.py (CLI入口)
    │
    ▼
ETFDecisionEngine.run_daily_check()
    │
    ├──────────────────────────────┐
    │                              │
    ▼                              ▼
DataFacade                  BacktestEngine
    │                              │
    ├──────────────────────────────┤
    │                              │
    ▼                              ▼
HotDataManager ──────────▶ FactorScorer
    │                              │
    ▼                              ▼
ColdDataManager ◀──────── TradeExecutor
    │                              │
    ▼                              ▼
DataSourceRouter                   │
    │                              │
    ▼                              ▼
External APIs (腾讯/新浪/东财/BaoStock)
```

### 3.2 模块间调用

| 调用方 | 被调用模块 | 方法 | 说明 |
|--------|-----------|------|------|
| CLI (decision.py) | ETFDecisionEngine | `run_daily_check()` | 每日检查 |
| ETFDecisionEngine | DataFacade | `get_merged_data()` | 获取数据 |
| ETFDecisionEngine | BacktestEngine | `run()` | 回测评估 |
| ETFDecisionEngine | SignalNotifier | `notify()` | 发送通知 |
| DataFacade | HotDataManager | `get()/set()` | 热数据 |
| DataFacade | ColdDataManager | `get()` | 冷数据 |
| DataFacade | DataSourceRouter | `fetch_*()` | 采集数据 |
| BacktestEngine | FactorScorer | `calculate()` | 计算评分 |
| BacktestEngine | TradeExecutor | `buy()/sell()` | 执行交易 |
| SignalNotifier | ScenarioAdapter | `adapt()` | 场景适配 |

---

## 四、核心类说明

### 4.1 数据层

| 类名 | 文件 | 职责 |
|------|------|------|
| `DataFacade` | manager.py | 数据层唯一统一入口，封装热/冷数据切换 |
| `HotDataManager` | manager.py | 热数据管理（内存JSON，实时价格） |
| `ColdDataManager` | manager.py | 冷数据管理（SQLite，历史数据） |
| `DataSourceRouter` | fetcher.py | 采集路由器，统一外部API入口 |

### 4.2 策略层

| 类名 | 文件 | 职责 |
|------|------|------|
| `BacktestEngine` | engine.py | 回测引擎，执行策略逻辑 |
| `BacktestConfig` | config.py | 回测配置（阈值/止损/止盈/持仓） |
| `FactorScorer` | scorer.py | 因子综合评分计算 |
| `TradeExecutor` | executor.py | 交易执行和持仓管理 |
| `quick_run()` | store.py | 快速运行单个实验（便捷函数） |

### 4.3 指标层

| 类名 | 文件 | 职责 |
|------|------|------|
| `ADXIndicator` | adx.py | ADX趋势指标 |
| `BollingerIndicator` | bollinger.py | 布林带指标 |
| `SARIndicator` | sar.py | SAR抛物线指标 |
| `OBVIndicator` | obv.py | OBV能量潮指标 |
| `DMAIndicator` | dma.py | DMA差分移动平均 |
| `RSIIndicator` | rsi.py | RSI相对强弱 |

### 4.4 通知层

| 类名 | 文件 | 职责 |
|------|------|------|
| `SignalNotifier` | notifier.py | 信号通知 |
| `ScenarioAdapter` | scenario.py | 钉钉场景适配 |
| `DingTalkSender` | dingtalk.py | 钉钉发送 |

---

## 五、数据层架构

### 5.1 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     热数据层 (Hot)                          │
│  位置: etf_data_live/hot/*.json                            │
│  内容: 实时价格缓存                                         │
│  管理: HotDataManager                                       │
│  TTL: 盘中实时更新，收盘后迁移                               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼  migrate()
┌─────────────────────────────────────────────────────────────┐
│                     冷数据层 (Cold)                          │
│  位置: etf_data_live/etf.db (SQLite)                       │
│  内容: 历史日线、小时线、元数据                               │
│  管理: ColdDataManager                                      │
│  访问: 只读，可多进程并发                                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼  采集
┌─────────────────────────────────────────────────────────────┐
│                     采集层 (Fetch)                           │
│  入口: DataSourceRouter                                     │
│  源: 腾讯API / 新浪API / BaoStock / 东方财富EMF            │
│  约束: RateLimiter(2-5秒) + 缓存5分钟TTL                    │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 数据源优先级

| 数据类型 | 优先级1 | 优先级2 | 优先级3 |
|----------|--------|--------|--------|
| ETF日线(上交所) | 腾讯API | Tushare | - |
| ETF日线(深交所) | BaoStock | Tushare | - |
| ETF实时价格 | 腾讯API | 东方财富EMF | 新浪 |
| 小时线 | 新浪scale=30 | - | - |

---

## 六、策略层架构

### 6.1 回测流程

```
┌─────────────────────────────────────────────────────────────┐
│                    BacktestEngine.run()                     │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │ 数据加载  │       │ 评分计算  │       │ 交易执行 │
    │ load()   │       │ scorer   │       │ executor │
    └────┬─────┘       └────┬─────┘       └────┬─────┘
         │                  │                  │
         ▼                  ▼                  ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │ 日线数据  │       │ 综合评分  │       │ 买入/卖出│
    │ + 热数据  │  ───▶ │ >阈值?    │  ───▶ │ + 止损止盈│
    └──────────┘       └──────────┘       └──────────┘
                              │                  │
                              ▼                  ▼
                       ┌──────────┐       ┌──────────┐
                       │ 交易信号  │       │ 绩效计算  │
                       │ buy/sell │       │ metrics  │
                       └──────────┘       └──────────┘
```

### 6.2 评分模型

```
输入: 日线数据 (open/high/low/close/volume)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FactorScorer.calculate()                 │
├─────────────────────────────────────────────────────────────┤
│  因子1: ADX (权重0.5, 方向long)   → 归一化评分              │
│  因子2: BB_percent (权重0.2)      → 归一化评分              │
│  因子3: SAR_trend (权重0.15)      → 归一化评分              │
│  因子4: OBV_diff (权重0.15, 方向short) → 归一化评分         │
├─────────────────────────────────────────────────────────────┤
│  综合评分 = Σ(因子评分 × 权重)                               │
│  信号: buy(>阈值) / hold / sell(<阈值)                      │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
    输出: score + details
```

---

## 七、约束规则

### 7.1 数据约束
- 所有外部API请求必须经过 DataSourceRouter
- 禁止裸 `requests.get()`
- 所有请求带随机2-5秒等待
- 统一缓存5分钟TTL

### 7.2 策略约束
- 单一持仓（同时最多1只ETF）
- 止损/止盈触发后立即执行
- 持仓天数到达上限强制平仓

### 7.3 接口约束
- 禁止跨层直接调用
- 必须通过统一入口

---

## 八、关键配置文件

| 配置 | 位置 | 说明 |
|------|------|------|
| ETF股票池 | `data/etf_pool.json` | 33只ETF清单 |
| 实验结果 | `data/experiments/round*.json` | 历史实验数据 |
| 热数据目录 | `etf_data_live/hot/` | 实时价格JSON |
| SQLite数据库 | `etf_data_live/etf.db` | 历史数据主库 |
| 常量定义 | `src/constants.py` | API地址、超时等 |

---

## 九、文档索引

| 文档 | 内容 |
|------|------|
| `docs/ARCHITECTURE.md` | 数据层架构（三层分离） |
| `docs/MODULES.md` | 模块职责和接口 |
| `docs/TOOLS.md` | 工具清单 |
| `docs/INDEX.md` | 场景索引 |
| `docs/INTERFACE_CONTRACT.md` | 接口契约 |

---

*文档版本: v3.0 | 更新: 2026-05-28*