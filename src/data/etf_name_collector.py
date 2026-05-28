#!/usr/bin/env python3
"""
ETF名称采集器
============
多渠道获取ETF名称，支持失败重试、监控告警

功能：
- 多渠道（腾讯+新浪）交叉验证
- 随机间隔 1~3秒
- 分批处理
- 持久化重试队列
- 采集监控
"""

import random
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from dataclasses import field

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.database import Database
from src.utils.logger import get_logger

logger = get_logger()

# 配置
MIN_INTERVAL = 1.0    # 最小间隔秒
MAX_INTERVAL = 2.0    # 最大间隔秒
MAX_RETRIES = 3       # 最大重试次数
RETRY_DELAYS = [60, 300, 1800]  # 重试延迟：1分钟、5分钟、30分钟

# 渠道配置
CHANNELS = {
    'tencent': {
        'url': 'https://qt.gtimg.cn/q={code}',
        'headers': {},
        'parse': lambda text: _parse_tencent(text),
    },
    'sina': {
        'url': 'https://hq.sinajs.cn/list={code}',
        'headers': {'Referer': 'https://finance.sina.com.cn'},
        'parse': lambda text: _parse_sina(text),
    },
}

# 告警配置
ALERT_THRESHOLDS = {
    'success_rate_below': 0.9,     # 成功率低于90%告警
    'failed_count_above': 10,       # 失败超过10只告警
    'avg_duration_above': 5000,    # 平均响应超过5秒告警
}


def _parse_tencent(text: str) -> Optional[str]:
    """解析腾讯API响应"""
    try:
        if '~' not in text:
            return None
        parts = text.split('~')
        return parts[1].strip() if len(parts) > 1 and parts[1] else None
    except:
        return None


def _parse_sina(text: str) -> Optional[str]:
    """解析新浪API响应"""
    try:
        if '"' not in text:
            return None
        name = text.split('"')[1].split(',')[0]
        return name.strip() if name else None
    except:
        return None


def _get_prefix(code: str) -> str:
    """获取交易所前缀"""
    return 'sh' if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')) else 'sz'


def _random_interval(min_val: float = MIN_INTERVAL, max_val: float = MAX_INTERVAL) -> float:
    """随机间隔"""
    return random.uniform(min_val, max_val)


@dataclass
class ETFNameResult:
    """采集结果"""
    code: str
    name_tencent: Optional[str] = None
    name_sina: Optional[str] = None
    verified: bool = False
    duration_ms: int = 0
    sources_tried: List[str] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return asdict(self)


class ETFNameCollector:
    """ETF名称采集器"""
    
    def __init__(self, db_path: str = "data/etf_factors.db"):
        self.db = Database(db_path)
        self._init_tables()
    
    def _init_tables(self):
        """初始化表"""
        self.db.init_etf_name_tables()
    
    def _fetch_from_channel(self, code: str, channel: str) -> Optional[str]:
        """从单个渠道获取名称"""
        prefix = _get_prefix(code)
        full_code = f"{prefix}{code}"
        
        config = CHANNELS[channel]
        
        for retry in range(2):  # 最多重试1次
            try:
                url = config['url'].format(code=full_code)
                headers = config.get('headers', {})
                
                start = time.time()
                resp = requests.get(url, headers=headers, timeout=5)
                duration = int((time.time() - start) * 1000)
                
                if resp.status_code != 200:
                    time.sleep(1)  # 等待后重试
                    continue
                
                text = resp.content.decode('gbk', errors='replace')
                name = config['parse'](text)
                
                return name
                
            except Exception as e:
                if retry == 0:
                    time.sleep(2)  # 等待后重试
                else:
                    logger.info(f"{channel} 获取失败 {code}: {e}")
        
        return None
    
    def fetch_name(self, code: str) -> ETFNameResult:
        """获取单个ETF名称（多渠道）"""
        start_time = time.time()
        
        result = ETFNameResult(code=code)
        sources_tried = []
        
        # 获取腾讯名称
        name_tencent = self._fetch_from_channel(code, 'tencent')
        result.name_tencent = name_tencent
        sources_tried.append('tencent')
        
        if name_tencent:
            time.sleep(_random_interval())
        
        # 获取新浪名称
        name_sina = self._fetch_from_channel(code, 'sina')
        result.name_sina = name_sina
        sources_tried.append('sina')
        
        if name_sina:
            time.sleep(_random_interval())
        
        # 计算耗时
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.sources_tried = sources_tried
        
        # 交叉验证
        if name_tencent and name_sina:
            result.verified = (name_tencent == name_sina)
            if not result.verified:
                logger.info(f"验证不一致 {code}: 腾讯={name_tencent}, 新浪={name_sina}")
        
        # 成功标记
        result.success = (name_tencent is not None)
        
        return result
    
    def fetch_with_retry(self, code: str) -> ETFNameResult:
        """获取单个ETF名称（带失败重试）"""
        
        for attempt in range(MAX_RETRIES):
            result = self.fetch_name(code)
            
            if result.success:  # 成功
                self._save_result(result)
                return result
            
            # 失败，记录并重试
            error_msg = f"tencent={result.name_tencent}, sina={result.name_sina}"
            self.db.add_retry_task(code, error_msg, priority=MAX_RETRIES - attempt)
            
            logger.info(f"获取失败 {code}，{RETRY_DELAYS[attempt]}秒后重试 ({attempt+1}/{MAX_RETRIES})")
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
        
        # 全部失败
        result.error = "重试3次全部失败"
        self._save_result(result)
        self.db.fail_retry_task(code, result.error)
        
        logger.error(f"获取失败 {code}，已重试 {MAX_RETRIES} 次")
        return result
    
    def _save_result(self, result: ETFNameResult):
        """保存采集结果"""
        # 保存到数据库
        if result.name_tencent:
            self.db.save_etf_name_full(
                code=result.code,
                name=result.name_tencent,
                name_sina=result.name_sina,
                verified=result.verified,
            )
        
        # 保存监控指标
        self.db.save_metrics(
            code=result.code,
            success=result.success,
            verified=result.verified,
            duration_ms=result.duration_ms,
            sources=result.sources_tried,
        )
    
    def fetch_batch(self, codes: List[str], pool_type: str = 'core') -> Dict[str, ETFNameResult]:
        """分批采集ETF
        
        Args:
            codes: ETF代码列表
            pool_type: 池类型（core/extended），影响间隔
            
        Returns:
            {code: ETFNameResult}
        """
        # 根据池类型确定间隔
        if pool_type == 'core':
            min_int, max_int = 1.0, 2.0
        else:
            min_int, max_int = 1.5, 3.0
        
        results = {}
        total = len(codes)
        
        logger.info(f"[{pool_type}] 开始采集 {total} 只ETF...")
        
        for idx, code in enumerate(codes, 1):
            result = self.fetch_with_retry(code)
            results[code] = result
            
            # 日志
            if result.success:
                status = '✅' if result.verified else '⚠️'
                name = result.name_tencent or result.name_sina or '未知'
                logger.info(f"  [{idx}/{total}] {status} {code}: {name} ({result.duration_ms}ms)")
            else:
                logger.error(f"  [{idx}/{total}] ❌ {code}: 获取失败")
        
        # 统计
        success_count = sum(1 for r in results.values() if r.success)
        failed_count = total - success_count
        success_rate = success_count / total if total else 0
        
        logger.info(f"[{pool_type}] 完成: 成功={success_count}, 失败={failed_count}, 成功率={success_rate:.1%}")
        
        # 检查告警
        self._check_alerts(results, pool_type)
        
        return results
    
    def fetch_all_by_pool(self, pool_type: str = 'core') -> Dict[str, ETFNameResult]:
        """采集指定池的所有ETF"""
        from src.config.etf_pools import get_codes_by_pool, get_pool_config
        
        codes = get_codes_by_pool(pool_type)
        config = get_pool_config(pool_type)
        
        return self.fetch_batch(codes, pool_type)
    
    def _check_alerts(self, results: Dict[str, ETFNameResult], pool_type: str):
        """检查告警条件"""
        total = len(results)
        success = sum(1 for r in results.values() if r.success)
        success_rate = success / total if total else 0
        
        avg_duration = sum(r.duration_ms for r in results.values()) / total if total else 0
        failed_codes = [r.code for r in results.values() if not r.success]
        
        alerts = []
        
        if success_rate < ALERT_THRESHOLDS['success_rate_below']:
            alerts.append(f"⚠️ 成功率 {success_rate:.1%} < {ALERT_THRESHOLDS['success_rate_below']:.0%}")
        
        if len(failed_codes) > ALERT_THRESHOLDS['failed_count_above']:
            alerts.append(f"🔴 失败 {len(failed_codes)} 只 > {ALERT_THRESHOLDS['failed_count_above']}")
        
        if avg_duration > ALERT_THRESHOLDS['avg_duration_above']:
            alerts.append(f"⚠️ 平均响应 {avg_duration:.0f}ms > {ALERT_THRESHOLDS['avg_duration_above']}ms")
        
        if alerts:
            message = f"📊 ETF名称采集告警 [{pool_type}]\n"
            message += f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            message += f"总数: {total}\n"
            message += f"成功: {success}\n"
            message += f"失败: {len(failed_codes)}\n"
            message += f"成功率: {success_rate:.1%}\n"
            message += f"平均耗时: {avg_duration:.0f}ms\n"
            if failed_codes:
                message += f"失败列表: {', '.join(failed_codes[:10])}"
                if len(failed_codes) > 10:
                    message += f" ... 等{len(failed_codes)}只"
            
            logger.info(message)
            # TODO: 发送到钉钉
    
    def fetch_failed_only(self) -> Dict[str, ETFNameResult]:
        """只采集失败的ETF（用于恢复）"""
        tasks = self.db.get_retry_tasks(limit=20)
        
        if not tasks:
            logger.info("无待处理的重试任务")
            return {}
        
        logger.info(f"恢复采集 {len(tasks)} 只失败ETF")
        
        results = {}
        for task in tasks:
            code = task['code']
            logger.info(f"  重试 {code} (第{task['attempt_count']}次)")
            result = self.fetch_with_retry(code)
            results[code] = result
        
        return results


# ========== 命令行入口 ==========

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='ETF名称采集器')
    parser.add_argument('--pool', choices=['core', 'extended', 'all'], default='core',
                        help='采集池类型')
    parser.add_argument('--dry', action='store_true', help='只打印，不保存')
    args = parser.parse_args()
    
    collector = ETFNameCollector()
    
    if args.pool == 'all':
        # 采集所有池
        for pool_type in ['core', 'extended']:
            collector.fetch_all_by_pool(pool_type)
            time.sleep(60)  # 池间休息
    else:
        # 采集指定池
        results = collector.fetch_all_by_pool(args.pool)
        
        # 打印摘要
        print("\n" + "="*50)
        print("采集结果")
        print("="*50)
        for code, result in results.items():
            status = '✅' if result.success else '❌'
            name = result.name_tencent or result.name_sina or '-'
            print(f"  {status} {code}: {name}")


if __name__ == '__main__':
    main()