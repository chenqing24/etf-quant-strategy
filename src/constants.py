#!/usr/bin/env python3
"""
常量定义模块
所有硬编码值应在此定义，便于维护和修改
"""
from pathlib import Path

# ==================== 目录常量 ====================
# US-008 + 教训 112: DB_PATH 必须是绝对路径（基于 PROJECT_ROOT）
# 修复前: DB_PATH = 'etf_data_live/etf.db'  # 相对路径导致双 db 文件并存
# 修复后: DB_PATH = PROJECT_ROOT / 'etf_data_live' / 'etf.db'  # 唯一真相
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # src/constants.py → etf_strategy/
DATA_DIR = PROJECT_ROOT / 'etf_data_live'   # 数据目录（绝对路径）
REPORTS_DIR = PROJECT_ROOT / 'etf_reports'  # 报告目录
CACHE_DIR = PROJECT_ROOT / 'etf_reports' / 'cache'  # 缓存目录
TRADES_FILE = DATA_DIR / 'etf_trades.json'  # 交易记录文件（US-008 已废弃，保留兼容）
DB_NAME = 'etf.db'              # 数据库文件名
DB_PATH = DATA_DIR / DB_NAME    # 数据库完整路径（US-008 + 教训 112 绝对路径）

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