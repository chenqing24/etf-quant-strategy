-- ============================================================
-- ETF 因子数据库 schema
-- 文件：data/etf_factors.db
-- 用途：存储因子计算结果、交易记录、回测结果
-- ============================================================

-- 每日行情扩展表（带前复权因子）
CREATE TABLE IF NOT EXISTS daily_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    pre_close REAL,
    volume REAL NOT NULL,
    amount REAL,
    adj_open REAL,
    adj_high REAL,
    adj_low REAL,
    adj_close REAL,
    change REAL,
    pct_change REAL,
    turnover REAL,
    amplitude REAL,
    volatility REAL,
    vwap REAL,
    created_at TEXT NOT NULL,
    UNIQUE(code, date)
);

-- 因子数据表
CREATE TABLE IF NOT EXISTS factor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    -- 趋势指标
    DMA REAL,
    MA_short REAL,
    MA_long REAL,
    SAR REAL,
    SAR_trend INTEGER,
    -- 动量指标
    RSI_5 REAL,
    RSI_10 REAL,
    K REAL,
    D REAL,
    J REAL,
    DIF REAL,
    DEA REAL,
    MACD_hist REAL,
    -- 量价指标
    OBV REAL,
    MAOBV REAL,
    volume_ratio REAL,
    money_flow REAL,
    -- 布林带
    BB_upper REAL,
    BB_middle REAL,
    BB_lower REAL,
    BB_percent REAL,
    -- ATR/ADX
    ATR REAL,
    ADX REAL,
    DI_plus REAL,
    DI_minus REAL,
    -- 收益
    return_1d REAL,
    return_5d REAL,
    return_10d REAL,
    return_20d REAL,
    created_at TEXT NOT NULL,
    UNIQUE(code, date)
);

-- IC分析结果
CREATE TABLE IF NOT EXISTS ic_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    code TEXT,
    period INTEGER,
    ic_mean REAL,
    ic_std REAL,
    ir REAL,
    ic_cum REAL,
    p_value REAL,
    t_stat REAL,
    sample_count INTEGER,
    hit_rate REAL,
    direction TEXT,
    confidence REAL,
    start_date TEXT,
    end_date TEXT,
    created_at TEXT NOT NULL
);

-- 交易记录
CREATE TABLE IF NOT EXISTS trade_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    signal TEXT NOT NULL,
    signal_reason TEXT,
    price REAL NOT NULL,
    quantity INTEGER,
    amount REAL,
    commission REAL,
    position REAL,
    position_qty INTEGER,
    profit REAL,
    profit_pct REAL,
    hold_days INTEGER,
    strategy TEXT,
    factors TEXT,
    created_at TEXT NOT NULL
);

-- 回测结果
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    version TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_return REAL,
    annual_return REAL,
    benchmark_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    max_drawdown_days INTEGER,
    volatility REAL,
    win_rate REAL,
    profit_loss_ratio REAL,
    avg_profit REAL,
    avg_loss REAL,
    trade_count INTEGER,
    stop_profit REAL,
    stop_loss REAL,
    params TEXT,
    factor_weights TEXT,
    created_at TEXT NOT NULL
);

-- ETF池配置
CREATE TABLE IF NOT EXISTS etf_pools (
    code TEXT NOT NULL,
    pool_type TEXT NOT NULL,
    scale_rank INTEGER,
    daily_volume REAL,
    last_fetch_at TEXT,
    fetch_count INTEGER,
    status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(code, pool_type)
);

-- ETF名称表（同步副本）
CREATE TABLE IF NOT EXISTS etf_names (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_sina TEXT,
    verified INTEGER DEFAULT 0,
    verify_count INTEGER DEFAULT 0,
    last_verify_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_daily_price_code_date ON daily_price(code, date);
CREATE INDEX IF NOT EXISTS idx_factor_data_code_date ON factor_data(code, date);
CREATE INDEX IF NOT EXISTS idx_trade_records_code_date ON trade_records(code, date);
CREATE INDEX IF NOT EXISTS idx_ic_results_factor ON ic_results(factor_name);
CREATE INDEX IF NOT EXISTS idx_etf_pools_type ON etf_pools(pool_type);