-- ============================================================
-- ETF 行情数据库 schema
-- 文件：etf_data_live/etf.db
-- 用途：存储ETF每日行情和元数据
-- ============================================================

-- 每日行情（来源：腾讯API v2）
CREATE TABLE IF NOT EXISTS daily (
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (code, date)
);

-- ETF基础信息（来源：AKTools fund_etf_spot_em）
CREATE TABLE IF NOT EXISTS etf_names (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_sina TEXT,
    verified INTEGER DEFAULT 0,
    verify_count INTEGER DEFAULT 0,
    last_verify_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    exchange TEXT,
    category TEXT,
    tracking_index TEXT,
    aum REAL
);

-- ETF名称重试队列
CREATE TABLE IF NOT EXISTS etf_name_retry_queue (
    code TEXT PRIMARY KEY,
    attempt_count INTEGER DEFAULT 0,
    last_error TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    next_retry_at TEXT,
    finished_at TEXT
);

-- ETF名称验证指标
CREATE TABLE IF NOT EXISTS etf_name_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    success INTEGER NOT NULL,
    verified INTEGER NOT NULL,
    duration_ms INTEGER,
    sources_tried TEXT,
    created_at TEXT NOT NULL
);

-- 股票/ETF基本信息（来源：AKTools）
CREATE TABLE IF NOT EXISTS stock_info (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    exchange TEXT,
    full_code TEXT,
    list_date TEXT,
    updated_at TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_daily_code_date ON daily(code, date);
CREATE INDEX IF NOT EXISTS idx_etf_names_category ON etf_names(category);
CREATE INDEX IF NOT EXISTS idx_etf_names_aum ON etf_names(aum);