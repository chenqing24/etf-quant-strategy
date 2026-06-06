#!/usr/bin/env python3
"""
常量定义模块
所有硬编码值应在此定义，便于维护和修改
"""
from pathlib import Path

# ==================== 目录常量 ====================
DATA_DIR = 'etf_data_live'      # 数据目录
REPORTS_DIR = 'etf_reports'     # 报告目录
CACHE_DIR = 'etf_reports/cache' # 缓存目录
TRADES_FILE = 'etf_trades.json' # 交易记录文件（US-008: 已废弃，迁移到 trade_history 表）
DB_NAME = 'etf.db'              # 数据库文件名
DB_PATH = 'etf_data_live/etf.db'  # 数据库完整路径（US-008: TradeTracker 主存储）

# ==================== API地址 ====================
# 腾讯行情API
TENCENT_BASE_URL = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
TENCENT_QT_URL = 'https://qt.gtimg.cn/q='
TENCENT_REALTIME_URL = 'https://qt.gtimg.cn/q={code}'  # 实时价格，含ETF名称

# 新浪API
SINA_REALTIME_URL = 'https://hq.sinajs.cn/list='
SINA_KLINE_URL = 'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData'
SINA_REFERER = 'https://finance.sina.com.cn/'

# 东方财富API
EMF_BASE_URL = 'https://push2.eastmoney.com/api/qt/ulist.np/get'

# ==================== 超时配置 ====================
# HTTP请求超时（秒）
HTTP_TIMEOUT_SHORT = 10   # 短请求（实时价格）
HTTP_TIMEOUT_MEDIUM = 15  # 中等请求（日线数据）
HTTP_TIMEOUT_LONG = 30    # 长请求（批量操作）

# 进程超时（秒）
THREAD_JOIN_TIMEOUT = 30
SUBPROCESS_TIMEOUT = 15
SUBPROCESS_TIMEOUT_LONG = 20

# ==================== 缓存配置 ====================
# 缓存TTL（秒）
CACHE_TTL_REALTIME = 300     # 5分钟
CACHE_TTL_DAILY = 3600       # 1小时
CACHE_TTL_HOURLY = 300       # 5分钟

# ==================== 数据验证 ====================
MIN_DATA_ROWS = 300          # 最小数据行数（~1年交易日）
MIN_PRICE = 0.001            # 最小价格
MAX_DAILY_CHANGE = 0.20      # 最大日涨跌幅（20%）

# ==================== 策略参数（US-018 单一真相源）====================
# 止损止盈（持仓段、风控段、实时校验、报告头部统一引用）
STOP_LOSS_PCT = 0.06           # -6% 止损
TAKE_PROFIT_PCT = 0.10         # +10% 止盈
STOP_LOSS_PRICE_RATIO = 1 - STOP_LOSS_PCT      # 0.94 (entry * ratio = 止损价)
TAKE_PROFIT_PRICE_RATIO = 1 + TAKE_PROFIT_PCT  # 1.10 (entry * ratio = 止盈价)

# 移动止盈
TRAILING_THRESHOLD_PCT = 0.06  # 盈利 > 6% 启用移动止盈
TRAILING_STOP_PCT = 0.04       # 回撤 4% 触发平仓

# 持仓
MAX_HOLD_DAYS = 15             # 强制平仓天数

# 总风险
MAX_TOTAL_STOP_LOSS = -0.10    # -10% 全仓清仓线
MAX_POSITION_RATIO = 0.90      # 90% 仓位上限（预留 10% 现金）

# ==================== 数据采集配置（多源分时段）====================
# AKTools 配置（按 SOUL 规则 16 限速 5 秒）
AKTOOLS_BASE_URL = 'http://127.0.0.1:8080'
AKTOOLS_FETCH_INTERVAL = 5     # 秒

# 5 年分时段采集（按 SOP-04 + 规则 13 分层）
DEFAULT_FETCH_YEARS = 5
FETCH_RANGE_SEGMENTS = [
    ('2018-01-01', '2020-12-31'),  # 段 1: 2 年（aktools 优势段）
    ('2021-01-01', '2022-12-31'),  # 段 2: 2 年（中段）
    ('2023-01-01', '2026-06-30'),  # 段 3: 3.5 年（tencent 优势段）
]

# 核心 ETF 池（14 core + 1 reference = 15 只）
# 与 etf_names 表 pool_role='core' 对齐
CORE_ETF_POOL_15 = [
    '510300',  # 沪深300ETF华泰柏瑞 (reference)
    '512170',  # 医疗ETF华宝
    '512200',  # 房地产ETF南方
    '512400',  # 有色金属ETF南方
    '512480',  # 半导体ETF国联安
    '512660',  # 军工ETF国泰
    '512800',  # 银行ETF华宝
    '512880',  # 证券ETF国泰
    '512980',  # 传媒ETF广发
    '515050',  # 通信ETF华夏
    '515070',  # 人工智能ETF华夏
    '515650',  # 消费50ETF富国
    '515790',  # 光伏ETF华泰柏瑞
    '520900',  # 港股通红利ETF广发
    '588000',  # 科创50ETF华夏
]