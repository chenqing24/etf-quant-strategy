#!/usr/bin/env python3
"""
ETF生命周期管理
==============
处理ETF的增删改查

功能：
- 发现新ETF自动加入
- 检测退市ETF
- 记录名称变更历史
- 管理ETF池
"""

from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.database import Database
from src.data.etf_name_collector import ETFNameCollector
from src.config.etf_pools import get_all_codes, get_codes_by_pool, ETF_POOLS
from src.utils.logger import get_logger

logger = get_logger()


class ETFLifecycleManager:
    """ETF生命周期管理器"""
    
    def __init__(self, db_path: str = "data/etf_factors.db"):
        self.db = Database(db_path)
        self.collector = ETFNameCollector(db_path)
    
    def sync_pool_config(self):
        """同步ETF池配置到数据库"""
        logger.info("同步ETF池配置...")
        
        conn = self.db._get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for pool_type, pool_config in ETF_POOLS.items():
            for rank, code in enumerate(pool_config['codes'], 1):
                cursor.execute("""
                    INSERT OR REPLACE INTO etf_pools 
                    (code, pool_type, scale_rank, status, updated_at)
                    VALUES (?, ?, ?, 'active', ?)
                """, (code, pool_type, rank, now))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ 同步完成: {len(get_all_codes())} 只ETF")
    
    def detect_new_listing(self) -> List[str]:
        """检测新上市ETF
        
        Returns:
            新增ETF代码列表
        """
        # 读取配置文件中的所有ETF
        config_codes = set(get_all_codes())
        
        # 查询数据库中的ETF
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM etf_names")
        db_codes = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        # 找出新增的
        new_codes = config_codes - db_codes
        
        if new_codes:
            logger.info(f"发现 {len(new_codes)} 只新ETF: {new_codes}")
            
            # 触发采集
            for code in new_codes:
                self.collector.fetch_with_retry(code)
        
        return list(new_codes)
    
    def detect_delisted(self) -> List[str]:
        """检测退市ETF
        
        Returns:
            退市ETF代码列表
        """
        # 读取配置文件中的所有ETF
        config_codes = set(get_all_codes())
        
        # 查询数据库中的ETF
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT code, name FROM etf_names")
        db_records = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        
        # 找出可能退市的（数据库有但配置没有）
        delisted_codes = []
        
        for code, name in db_records.items():
            if code not in config_codes:
                # 标记为 inactive
                conn = self.db._get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE etf_pools SET status = 'inactive', updated_at = ?
                    WHERE code = ?
                """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), code))
                conn.commit()
                conn.close()
                
                delisted_codes.append(code)
                logger.info(f"ETF可能退市: {code} ({name})")
        
        return delisted_codes
    
    def detect_name_change(self, code: str, new_name: str) -> bool:
        """检测名称变更
        
        Args:
            code: ETF代码
            new_name: 新名称
            
        Returns:
            True 名称变更，False 无变化
        """
        record = self.db.get_etf_name_full(code)
        
        if not record:
            return False
        
        old_name = record.get('name')
        
        if old_name and old_name != new_name:
            logger.info(f"ETF名称变更: {code}\n  旧: {old_name}\n  新: {new_name}")
            return True
        
        return False
    
    def get_pool_summary(self) -> Dict:
        """获取池摘要"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pool_type, COUNT(*), 
                   SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status = 'inactive' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
            FROM etf_pools
            GROUP BY pool_type
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        summary = {}
        for row in rows:
            pool_type = row[0]
            summary[pool_type] = {
                'total': row[1],
                'active': row[2],
                'inactive': row[3],
                'failed': row[4],
            }
        
        return summary
    
    def get_etf_status(self, code: str) -> Optional[dict]:
        """获取ETF状态"""
        # 名称信息
        name_info = self.db.get_etf_name_full(code)
        
        # 池信息
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT pool_type, scale_rank, status FROM etf_pools WHERE code = ?", (code,))
        pool_row = cursor.fetchone()
        conn.close()
        
        if not name_info and not pool_row:
            return None
        
        result = {
            'code': code,
            'pool_type': pool_row[0] if pool_row else None,
            'scale_rank': pool_row[1] if pool_row else None,
            'status': pool_row[2] if pool_row else None,
            'name': name_info.get('name') if name_info else None,
            'verified': name_info.get('verified') if name_info else False,
            'last_verify_at': name_info.get('last_verify_at') if name_info else None,
        }
        
        return result
    
    def cleanup_inactive(self, days: int = 30) -> int:
        """清理长期不活跃的ETF
        
        Args:
            days: 超过N天不活跃则清理
            
        Returns:
            清理数量
        """
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM etf_pools 
            WHERE status = 'inactive' 
            AND updated_at < datetime('now', '-{} days')
        """.format(days))
        
        count = cursor.rowcount
        conn.commit()
        conn.close()
        
        if count > 0:
            logger.info(f"清理了 {count} 只长期不活跃ETF")
        
        return count


# ========== 命令行入口 ==========

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='ETF生命周期管理')
    parser.add_argument('--sync', action='store_true', help='同步池配置')
    parser.add_argument('--detect-new', action='store_true', help='检测新ETF')
    parser.add_argument('--detect-delist', action='store_true', help='检测退市')
    parser.add_argument('--summary', action='store_true', help='池摘要')
    args = parser.parse_args()
    
    manager = ETFLifecycleManager()
    
    if args.sync:
        manager.sync_pool_config()
    
    if args.detect_new:
        new_codes = manager.detect_new_listing()
        print(f"新ETF: {new_codes if new_codes else '无'}")
    
    if args.detect_delist:
        delisted = manager.detect_delisted()
        print(f"退市ETF: {delisted if delisted else '无'}")
    
    if args.summary:
        summary = manager.get_pool_summary()
        print("\n池摘要:")
        for pool_type, stats in summary.items():
            print(f"  {pool_type}: {stats['total']}只 (活跃:{stats['active']}, 停牌:{stats['inactive']}, 失败:{stats['failed']})")


if __name__ == '__main__':
    main()