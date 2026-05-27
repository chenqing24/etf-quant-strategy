"""
数据采集路由器 - 统一外部API入口
所有外部请求必须经过此模块，随机等待+缓存+重试
"""

import time
import random
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import requests

from src.constants import (
    SINA_REALTIME_URL, SINA_KLINE_URL, SINA_REFERER,
    TENCENT_BASE_URL
)

# 默认HTTP头
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ETFQuant/1.0)",
    "Referer": SINA_REFERER
}


@dataclass
class FetchResult:
    """采集结果"""
    success: bool
    data: Any = None
    error: str = ""
    source: str = ""


class RateLimiter:
    """限速器：随机2-5秒等待"""
    def __init__(self, min_wait: float = 2.0, max_wait: float = 5.0):
        self.min_wait = min_wait
        self.max_wait = max_wait
        self._last_call = 0.0

    def wait(self):
        """等待随机时间"""
        elapsed = time.time() - self._last_call
        wait_time = random.uniform(self.min_wait, self.max_wait)
        if elapsed < self.min_wait:
            wait_time = random.uniform(self.min_wait - elapsed, self.max_wait - elapsed)
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_call = time.time()


class DataSourceRouter:
    """
    统一数据采集路由器
    
    职责：
    1. 所有外部API请求的唯一入口
    2. 随机等待2-5秒（RateLimiter）
    3. 5分钟TTL内存缓存
    4. 自动重试3次
    """
    
    # 数据源路由表
    ROUTES = {
        'realtime': {'primary': 'sina', 'backup': 'tencent'},
        'daily': {'primary': 'tencent', 'backup': 'tushare'},
        'hourly': {'primary': 'sina', 'backup': None},  # 无备源
        'stock_daily': {'primary': 'baostock', 'backup': 'tushare'},
    }

    def __init__(self, cache_ttl: int = 300):
        self._cache: Dict[str, tuple] = {}  # {key: (data, timestamp)}
        self._cache_ttl = cache_ttl  # 5分钟TTL
        self._limiter = RateLimiter(2.0, 5.0)
        self._max_retries = 3

    # ========== 公共接口 ==========
    
    def fetch(self, data_type: str, codes: List[str], **kwargs) -> Dict[str, Any]:
        """
        统一采集接口
        
        Args:
            data_type: 数据类型（realtime/daily/hourly/stock_daily）
            codes: 代码列表
            **kwargs: 额外参数（days、count等）
        
        Returns:
            {code: data, ...}
        """
        route = self.ROUTES.get(data_type, {})
        primary = route.get('primary')
        backup = route.get('backup')

        # 尝试主源
        if primary:
            result = self._try_fetch(primary, data_type, codes, **kwargs)
            if result:
                return result
        
        # 降级备源
        if backup:
            result = self._try_fetch(backup, data_type, codes, **kwargs)
            if result:
                return result

        return {code: None for code in codes}

    def fetch_realtime(self, codes: List[str]) -> Dict[str, Dict]:
        """获取实时价格（新浪主源）"""
        return self._fetch_sina(codes)

    def fetch_daily(self, codes: List[str], **kwargs) -> Dict[str, List]:
        """获取日线数据（腾讯主源）"""
        return self._fetch_tencent(codes, **kwargs)

    def fetch_hourly(self, codes: List[str], **kwargs) -> Dict[str, List]:
        """获取小时线数据（新浪scale=30）"""
        return self._fetch_sina_hourly(codes, **kwargs)

    # ========== 内部方法 ==========

    def _try_fetch(self, source: str, data_type: str, codes: List[str], **kwargs) -> Optional[Dict]:
        """尝试从指定源获取数据"""
        try:
            if source == 'sina':
                return self._fetch_sina(codes)
            elif source == 'tencent':
                return self._fetch_tencent(codes, **kwargs)
            elif source == 'baostock':
                return self._fetch_baostock(codes, **kwargs)
        except Exception as e:
            print(f"  ⚠️ {source} fetch failed: {e}")
        return None

    def _fetch_with_retry(self, url: str, headers: dict = None, timeout: int = 15) -> Optional[str]:
        """带重试的请求"""
        for attempt in range(self._max_retries):
            try:
                self._limiter.wait()
                resp = requests.get(url, headers=headers or DEFAULT_HEADERS, timeout=timeout)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                if attempt < self._max_retries - 1:
                    print(f"  重试 {attempt+1}/{self._max_retries}: {e}")
                    time.sleep(2)
                else:
                    print(f"  ❌ 请求失败: {e}")
        return None

    def _get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (data, time.time())

    def _cache_key(self, source: str, data_type: str, codes: List[str]) -> str:
        """生成缓存key"""
        code_str = ','.join(sorted(codes))
        return f"{source}:{data_type}:{code_str}"

    # ========== Sina 实时价格 ==========

    def _fetch_sina(self, codes: List[str]) -> Dict[str, Dict]:
        """
        获取新浪实时价格
        URL: https://hq.sinajs.cn/list=sh510300,sz159919
        """
        if not codes:
            return {}
        
        cache_key = self._cache_key('sina', 'realtime', codes)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        url = f"{SINA_REALTIME_URL}={','.join(codes)}"
        text = self._fetch_with_retry(url)
        if not text:
            return {code: None for code in codes}

        result = self._parse_sina_realtime(text, codes)
        self._set_cache(cache_key, result)
        return result

    def _parse_sina_realtime(self, text: str, codes: List[str]) -> Dict[str, Dict]:
        """解析新浪实时行情"""
        results = {}
        lines = text.strip().split('\n')
        for i, line in enumerate(lines):
            if i >= len(codes):
                break
            code = codes[i]
            try:
                # var hq_str_sh510300="name,price,prev_close,open,high,low,volume,..."
                content = line.split('="')[1].rstrip('";')
                parts = content.split(',')
                if len(parts) > 6:
                    results[code] = {
                        'code': code,
                        'name': parts[0],
                        'price': float(parts[1]),
                        'prev_close': float(parts[2]),
                        'open': float(parts[3]),
                        'high': float(parts[4]),
                        'low': float(parts[5]),
                        'volume': int(float(parts[6])),
                        'source': 'sina'
                    }
                else:
                    results[code] = None
            except Exception as e:
                results[code] = None
        return results

    # ========== Sina 小时线 ==========

    def _fetch_sina_hourly(self, codes: List[str], count: int = 1800) -> Dict[str, List]:
        """
        获取新浪小时线数据（scale=30）
        URL: https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData
        """
        results = {}
        for code in codes:
            cache_key = self._cache_key('sina', 'hourly', [code])
            cached = self._get_cache(cache_key)
            if cached is not None:
                results[code] = cached
                continue

            url = f"{SINA_KLINE_URL}?symbol={code}&scale=30&ma=no&datalen={count}"
            text = self._fetch_with_retry(url)
            if text:
                import json
                try:
                    data = json.loads(text)
                    results[code] = data
                    self._set_cache(cache_key, data)
                except:
                    results[code] = []
            else:
                results[code] = []
        return results

    # ========== 腾讯日线 ==========

    def _fetch_tencent(self, codes: List[str], **kwargs) -> Dict[str, List]:
        """
        获取腾讯日线数据
        URL: https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param=sh510300,day,,,320,qfq
        """
        results = {}
        days = kwargs.get('days', 300)
        for code in codes:
            cache_key = self._cache_key('tencent', 'daily', [code])
            cached = self._get_cache(cache_key)
            if cached is not None:
                results[code] = cached
                continue

            # 腾讯API需要带sh/sz前缀
            prefix = 'sh' if code.startswith(('51', '15')) else 'sz'
            full_code = f"{prefix}{code}"
            url = f"{TENCENT_BASE_URL}?_var=kline_dayqfq&param={full_code},day,,,{days},qfq"
            text = self._fetch_with_retry(url)
            if text:
                data = self._parse_tencent_daily(text)
                results[code] = data
                self._set_cache(cache_key, data)
            else:
                results[code] = []
        return results

    def _parse_tencent_daily(self, text: str) -> List[Dict]:
        """解析腾讯日线数据"""
        import json
        # 格式: kline_dayqfq={...}
        try:
            # 去掉变量名前缀
            json_str = text.split('=', 1)[1] if '=' in text else text
            obj = json.loads(json_str)
            # 提取qfq日线数据（结构: data.sh510300.qfqday）
            data = obj.get('data', {})
            # 取第一个code的qfqday
            code_key = list(data.keys())[0]
            day_data = data.get(code_key, {}).get('qfqday', [])
            result = []
            for item in day_data:
                if len(item) >= 6:
                    result.append({
                        'date': item[0],
                        'open': float(item[1]),
                        'close': float(item[2]),
                        'high': float(item[3]),
                        'low': float(item[4]),
                        'volume': int(float(item[5]))
                    })
            return result
        except Exception as e:
            print(f"  ⚠️ 腾讯日线解析失败: {e}")
            return []

    # ========== BaoStock 日线 ==========

    def _fetch_baostock(self, codes: List[str], **kwargs) -> Dict[str, List]:
        """
        获取BaoStock日线数据（股票用）
        暂不实现，需要 baostock 库
        """
        return {code: [] for code in codes}