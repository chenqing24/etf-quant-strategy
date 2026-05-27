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
TRADES_FILE = 'etf_trades.json' # 交易记录文件
DB_NAME = 'etf.db'              # 数据库文件名

# ==================== API地址 ====================
# 腾讯行情API
TENCENT_BASE_URL = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
TENCENT_QT_URL = 'https://qt.gtimg.cn/q='

# 新浪API
SINA_REALTIME_URL = 'https://hq.sinajs.cn/list='
SINA_KLINE_URL = 'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData'
SINA_REFERER = 'https://finance.sina.com.cn/'

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