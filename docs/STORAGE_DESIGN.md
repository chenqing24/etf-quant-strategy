# 8因子模型数据存储设计文档 v2

> 支持200+股票的量化分析系统存储方案

---

## 1. 混合存储架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据层架构                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Parquet   │    │   SQLite    │    │   外部库    │         │
│  │  历史指标   │    │ 查询/索引   │    │  数据获取   │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    数据流转                               │   │
│  │  外部库(tushare/baostock) → SQLite → Parquet → 分析       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据库表结构

### 2.1 ETF/股票基本信息表 (stock_info)

```sql
CREATE TABLE stock_info (
    code TEXT PRIMARY KEY,              -- 股票代码 159806
    name TEXT,                          -- 名称 芯片ETF
    exchange TEXT,                      -- 交易所 SH/SZ
    full_code TEXT,                     -- 完整代码 sz.159806 / sh.510300
    list_date TEXT,                     -- 上市日期
    category TEXT,                      -- 行业分类 芯片/消费/医药
    sub_category TEXT,                  -- 细分 半导体/集成电路
    
    -- 基本面数据（从外部库获取）
    total_shares REAL,                  -- 总股本
    float_shares REAL,                  -- 流通股本
    net_asset REAL,                     -- 每股净资产
    price REAL,                         -- 当前价格
    pe_ratio REAL,                      -- 市盈率PE
    pb_ratio REAL,                      -- 市净率PB
    dividend REAL,                      -- 分红率
    
    -- 数据来源标记
    data_source TEXT,                   -- 数据来源 baostock/tushare
    created_at TEXT,                     -- 记录创建时间
    updated_at TEXT                      -- 更新时间
);
```

### 2.2 日线行情数据表 (daily_price)

```sql
CREATE TABLE daily_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,                          -- 股票代码
    date TEXT,                          -- 交易日期 2024-01-01
    
    -- 价格数据
    open REAL,                           -- 开盘价
    high REAL,                           -- 最高价
    low REAL,                            -- 最低价
    close REAL,                          -- 收盘价
    pre_close REAL,                      -- 昨日收盘价
    volume REAL,                         -- 成交量（股）
    amount REAL,                         -- 成交额（元）
    
    -- 调整价格（复权）
    adj_open REAL,                       -- 复权开盘价
    adj_high REAL,                       -- 复权最高价
    adj_low REAL,                        -- 复权最低价
    adj_close REAL,                      -- 复权收盘价
    
    -- 行情指标
    change REAL,                         -- 涨跌额
    pct_change REAL,                     -- 涨跌幅(%)
    turnover REAL,                       -- 换手率(%)
    amplitude REAL,                      -- 振幅(%)
    
    -- 波动指标
    volatility REAL,                     -- 历史波动率
    vwap REAL,                          -- 均价
    
    created_at TEXT,
    UNIQUE(code, date)
);

CREATE INDEX idx_price_code ON daily_price(code);
CREATE INDEX idx_price_date ON daily_price(date);
CREATE INDEX idx_price_code_date ON daily_price(code, date);
```

### 2.3 因子数据表 (factor_data)

```sql
CREATE TABLE factor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,                          -- 股票代码
    date TEXT,                          -- 日期
    
    -- ===== 8个核心因子 =====
    
    -- 趋势类因子
    DMA REAL,                           -- DMA差值 (MA_short - MA_long)
    MA_short REAL,                      -- 短期均线
    MA_long REAL,                       -- 长期均线
    SAR REAL,                            -- SAR止损值
    SAR_trend INTEGER,                  -- SAR趋势 1多头/-1空头
    
    -- 动量类因子
    RSI_5 REAL,                         -- RSI(5)
    RSI_10 REAL,                        -- RSI(10)
    K REAL,                             -- KDJ K值
    D REAL,                             -- KDJ D值
    J REAL,                             -- KDJ J值
    DIF REAL,                           -- MACD DIF
    DEA REAL,                           -- MACD DEA
    MACD_hist REAL,                     -- MACD柱状图
    
    -- 量能类因子
    OBV REAL,                           -- OBV值
    MAOBV REAL,                         -- OBV均线
    volume_ratio REAL,                  -- 量比
    money_flow REAL,                    -- 资金流向
    
    -- 波动类因子
    BB_upper REAL,                      -- 布林上轨
    BB_middle REAL,                     -- 布林中轨
    BB_lower REAL,                      -- 布林下轨
    BB_percent REAL,                     -- 布林位置%
    ATR REAL,                           -- 平均真实波幅
    
    -- 趋势强度因子
    ADX REAL,                           -- ADX
    DI_plus REAL,                        -- +DI
    DI_minus REAL,                       -- -DI
    
    -- ===== 未来收益（用于IC计算）=====
    return_1d REAL,                     -- 未来1日收益率
    return_5d REAL,                     -- 未来5日收益率
    return_10d REAL,                    -- 未来10日收益率
    return_20d REAL,                    -- 未来20日收益率
    
    created_at TEXT,
    UNIQUE(code, date)
);

CREATE INDEX idx_factor_code ON factor_data(code);
CREATE INDEX idx_factor_date ON factor_data(date);
CREATE INDEX idx_factor_code_date ON factor_data(code, date);
```

### 2.4 IC计算结果表 (ic_results)

```sql
CREATE TABLE ic_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- 基本信息
    factor_name TEXT,                   -- 因子名称 RSI_5/DMA/K
    code TEXT,                          -- 股票代码（'ALL'表示全市场）
    
    -- IC指标
    ic_mean REAL,                      -- IC均值
    ic_std REAL,                       -- IC标准差
    ir REAL,                            -- IR = ic_mean / ic_std
    ic_cum REAL,                        -- 累计IC
    
    -- 显著性
    p_value REAL,                      -- P值
    t_stat REAL,                       -- T统计量
    sample_count INTEGER,              -- 样本数
    hit_rate REAL,                      -- IC>0比例
    
    -- 方向判定
    direction TEXT,                     -- long/short/neutral
    confidence REAL,                     -- 置信度
    
    -- 时间范围
    period INTEGER,                     -- 收益周期 1/5/10/20
    start_date TEXT,                    -- 计算起始日期
    end_date TEXT,                      -- 计算结束日期
    
    created_at TEXT,
    UNIQUE(factor_name, code, period, start_date, end_date)
);

CREATE INDEX idx_ic_factor ON ic_results(factor_name);
CREATE INDEX idx_ic_code ON ic_results(code);
CREATE INDEX idx_ic_period ON ic_results(period);
```

### 2.5 交易记录表 (trade_records)

```sql
CREATE TABLE trade_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- 交易基本信息
    code TEXT,                          -- 股票代码
    date TEXT,                           -- 交易日期
    signal TEXT,                        -- buy/sell
    signal_reason TEXT,                  -- 信号原因 RSI超卖/MACD金叉
    
    -- 成交信息
    price REAL,                         -- 成交价格
    quantity INTEGER,                    -- 成交数量
    amount REAL,                        -- 成交金额
    commission REAL,                     -- 手续费
    
    -- 持仓信息
    position REAL,                       -- 持仓成本
    position_qty INTEGER,               -- 持仓数量
    
    -- 盈亏（平仓后更新）
    profit REAL,                        -- 单笔盈亏
    profit_pct REAL,                    -- 盈亏比例
    hold_days INTEGER,                   -- 持仓天数
    
    -- 策略信息
    strategy TEXT,                      -- 策略名称
    factors TEXT,                       -- 触发因子（JSON）
    
    created_at TEXT
);

CREATE INDEX idx_trade_code ON trade_records(code);
CREATE INDEX idx_trade_date ON trade_records(date);
CREATE INDEX idx_trade_signal ON trade_records(signal);
```

### 2.6 策略回测结果表 (backtest_results)

```sql
CREATE TABLE backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- 策略信息
    strategy_name TEXT,                 -- 策略名称 8因子策略v1
    version TEXT,                        -- 策略版本
    
    -- 回测时间
    start_date TEXT,                    -- 回测起始日期
    end_date TEXT,                      -- 回测结束日期
    
    -- 收益指标
    total_return REAL,                  -- 总收益率
    annual_return REAL,                 -- 年化收益率
    benchmark_return REAL,              -- 基准收益率
    
    -- 风险指标
    sharpe_ratio REAL,                  -- 夏普比率
    max_drawdown REAL,                   -- 最大回撤
    max_drawdown_days INTEGER,           -- 最大回撤天数
    volatility REAL,                     -- 波动率
    
    -- 交易指标
    win_rate REAL,                      -- 胜率
    profit_loss_ratio REAL,              -- 盈亏比
    avg_profit REAL,                    -- 平均盈利
    avg_loss REAL,                      -- 平均亏损
    trade_count INTEGER,                -- 交易次数
    
    -- 止盈止损
    stop_profit REAL,                   -- 止盈点
    stop_loss REAL,                      -- 止损点
    
    -- 参数
    params TEXT,                         -- 策略参数（JSON）
    factor_weights TEXT,                -- 因子权重（JSON）
    
    created_at TEXT,
    UNIQUE(strategy_name, version, start_date, end_date)
);
```

---

## 3. 外部数据源字段映射

### 3.1 BaoStock返回字段

| 源字段 | 目标字段 | 说明 |
|--------|----------|------|
| code | code | 股票代码 |
| date | date | 日期 |
| open | open | 开盘价 |
| high | high | 最高价 |
| low | low | 最低价 |
| close | close | 收盘价 |
| volume | volume | 成交量 |

### 3.2 Tushare返回字段（扩展用）

| 源字段 | 目标字段 | 说明 |
|--------|----------|------|
| ts_code | code | 股票代码 |
| trade_date | date | 交易日期 |
| open | open | 开盘价 |
| high | high | 最高价 |
| low | low | 最低价 |
| close | close | 收盘价 |
| vol | volume | 成交量 |
| amount | amount | 成交额 |
| pct_chg | pct_change | 涨跌幅 |
| pe | pe_ratio | 市盈率 |
| pb | pb_ratio | 市净率 |

---

## 4. 文件目录结构

```
etf_strategy/
├── data/                               # 数据目录
│   ├── etf_factors.db                 # SQLite数据库
│   ├── price_cache/                    # 行情缓存 Parquet
│   │   └── {code}/{date}.parquet
│   └── factor_cache/                   # 因子缓存 Parquet
│       └── {code}/{date}.parquet
├── src/
│   ├── data/
│   │   ├── database.py               # 数据库操作（SQLite）
│   │   ├── parquet_store.py           # Parquet读写
│   │   ├── models.py                  # Pydantic模型定义
│   │   └── data_source.py             # 外部数据源适配
│   └── indicators/
│       └── wrapper.py                 # 指标计算（pandas-ta）
├── scripts/
│   ├── batch_calculate.py             # 批量计算因子
│   ├── batch_ic.py                    # 批量计算IC
│   └── import_from_baostock.py        # 从BaoStock导入数据
└── tests/
    └── test_storage.py                # 存储测试
```

---

## 5. 数据流转

```
┌─────────────────────────────────────────────────────────────────┐
│                      数据流转图                                  │
└─────────────────────────────────────────────────────────────────┘

外部数据源                    数据库                    分析层
───────────────────────────────────────────────────────────────────
     │                        │                         │
     ▼                        ▼                         ▼
┌─────────┐            ┌──────────────┐          ┌──────────┐
│BaoStock │ ──▶ daily_price ──▶ Parquet ──▶ factor_data
│  API    │            │  (原始数据)  │          │ (因子)   │
└─────────┘            └──────────────┘          └──────────┘
                                                     │
                                    ┌────────────────┤
                                    ▼                ▼
                              ┌──────────┐    ┌──────────┐
                              │ic_results    │backtest  │
                              │ (IC分析) │    │(回测)   │
                              └──────────┘    └──────────┘
```

---

## 6. 开发记录

### Phase 1: 数据库初始化 ✅

| 任务 | 文件 | 状态 | 测试 |
|------|------|:----:|------|
| 创建数据库类 | `src/data/database.py` | ✅ | 16 passed |
| 创建表结构 | Database._init_database() | ✅ | - |
| 插入/更新方法 | insert_or_update() | ✅ | - |
| 查询方法 | query(), query_df() | ✅ | - |

### Phase 2: 数据迁移验证 ✅

| 验证项 | 方法 | 结果 |
|--------|------|------|
| 常数价格IC=0 | 数学推导 | ✅ |
| 线性趋势IC | 公式验证 | ✅ |
| 随机序列IC≈0 | 统计验证 | ✅ |
| 完美正相关IC=1 | 公式验证 | ✅ |
| 完美负相关IC=-1 | 公式验证 | ✅ |

### Phase 3: IC计算器 ✅

| 函数 | 说明 | 测试 |
|------|------|------|
| calculate_ic | IC计算 | 16 passed |
| calculate_ir | IR计算 | ✅ |
| calculate_rolling_ic | 滚动IC | ✅ |
| calculate_factor_ic | 单因子IC统计 | ✅ |
| calculate_all_factors_ic | 全因子IC | ✅ |

### Git提交记录

```
6b23f02 feat: 数据库模块和数据存储设计
├── src/data/database.py (数据库类)
├── src/analysis/ic_calculator.py (IC计算器)
├── tests/test_storage.py (16测试)
├── tests/test_ic_calculation.py (16测试)
└── docs/STORAGE_DESIGN.md

ae6d8ba feat: 8因子核心指标计算模块
├── src/indicators/ (6个指标)
├── tests/indicators/ (25测试)
└── docs/8FACTOR_MINING_PLAN.md
```

## 7. 验收标准

- [x] 数据库6张表创建成功 ✅
- [x] 插入/更新/查询功能正常 ✅
- [x] IC计算公式验证通过 ✅
- [x] 所有测试通过 ✅ (286 passed)
- [x] 文档完整更新 ✅

---

## 8. 下一步

- [ ] 数据导入：从现有JSON迁移到SQLite
- [ ] Parquet缓存：因子数据缓存
- [ ] 指标计算：pandas-ta封装
- [ ] 批量IC计算：66只ETF全量计算

---

*文档版本: 2.1*
*创建时间: 2026-05-27*
*更新: 2026-05-27 v2 增加基本面数据、扩展字段*
*更新: 2026-05-27 v2.1 开发记录*