#!/usr/bin/env python3
"""
数据质量监控模块

功能：
- 检查数据新鲜度
- 检查数据完整性
- 检查存储健康度
- 生成监控报告

使用方式：
    # 检查并输出报告
    python -m src.data.monitor
    
    # 检查并输出JSON
    python -m src.data.monitor --json
    
    # 发送到钉钉
    python -m src.data.monitor --dingtalk
"""
import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.constants import DATA_DIR, DB_NAME


class DataQualityMonitor:
    """数据质量监控器"""
    
    # 告警阈值
    THRESHOLDS = {
        'max_delay_days': 3,          # 数据延迟超过3天告警
        'min_active_etfs': 30,        # 活跃ETF少于30个告警
        'max_missing_pct': 0.15,      # 缺失超过15%告警
        'max_db_size_mb': 100,        # 数据库超过100MB提示
    }
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(DATA_DIR, DB_NAME)
        self.alerts: List[Dict] = []
        self.report: Dict[str, Any] = {}
    
    def check_all(self) -> Dict[str, Any]:
        """执行所有检查"""
        self.alerts = []
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'freshness': self.check_data_freshness(),
            'completeness': self.check_data_completeness(),
            'storage': self.check_storage_health(),
            'alerts': []
        }
        
        self.report = report
        return report
    
    def check_data_freshness(self) -> Dict[str, Any]:
        """检查数据新鲜度"""
        if not Path(self.db_path).exists():
            return {
                'status': 'ERROR',
                'message': '数据库文件不存在',
                'latest_date': None,
                'delay_days': None
            }
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 获取最新日期
            cur = conn.execute('SELECT MAX(date) FROM daily')
            latest_date = cur.fetchone()[0]
            
            conn.close()
            
            if latest_date is None:
                return {
                    'status': 'WARNING',
                    'message': '无数据',
                    'latest_date': None,
                    'delay_days': None
                }
            
            # 计算延迟天数
            today = datetime.now().date()
            latest = datetime.strptime(latest_date, '%Y-%m-%d').date()
            delay_days = (today - latest).days
            
            # 判断状态
            if delay_days > self.THRESHOLDS['max_delay_days']:
                status = 'ERROR'
                self.alerts.append({
                    'type': 'freshness',
                    'level': 'ERROR',
                    'message': f'数据延迟 {delay_days} 天',
                    'detail': f'最新数据日期: {latest_date}'
                })
            elif delay_days > 1:
                status = 'WARNING'
                self.alerts.append({
                    'type': 'freshness',
                    'level': 'WARNING',
                    'message': f'数据延迟 {delay_days} 天',
                    'detail': f'最新数据日期: {latest_date}'
                })
            else:
                status = 'OK'
            
            return {
                'status': status,
                'latest_date': latest_date,
                'delay_days': delay_days,
                'message': f'数据延迟 {delay_days} 天' if delay_days > 0 else '数据最新'
            }
            
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': str(e),
                'latest_date': None,
                'delay_days': None
            }
    
    def check_data_completeness(self) -> Dict[str, Any]:
        """检查数据完整性"""
        if not Path(self.db_path).exists():
            return {'status': 'ERROR', 'message': '数据库文件不存在'}
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 获取ETF总数和数据行数
            cur = conn.execute('SELECT COUNT(DISTINCT code) FROM daily')
            total_etfs = cur.fetchone()[0]
            
            # 获取各ETF数据行数
            cur = conn.execute('''
                SELECT code, COUNT(*) as cnt 
                FROM daily 
                GROUP BY code 
                ORDER BY cnt DESC
            ''')
            etf_counts = {row[0]: row[1] for row in cur.fetchall()}
            
            # 获取配置中的ETF池数量
            try:
                from src.config.etf_pools import ETF_POOLS
                expected_etfs = len(ETF_POOLS.get('core', [])) + len(ETF_POOLS.get('extended', []))
            except:
                expected_etfs = total_etfs
            
            conn.close()
            
            # 计算缺失率
            missing_count = max(0, expected_etfs - len(etf_counts))
            missing_pct = missing_count / expected_etfs if expected_etfs > 0 else 0
            
            # 判断状态
            if missing_pct > self.THRESHOLDS['max_missing_pct']:
                status = 'ERROR'
                self.alerts.append({
                    'type': 'completeness',
                    'level': 'ERROR',
                    'message': f'缺失 {missing_count} 只ETF ({missing_pct:.1%})',
                    'detail': f'配置 {expected_etfs} 只, 实际 {total_etfs} 只'
                })
            elif missing_count > 0:
                status = 'WARNING'
                self.alerts.append({
                    'type': 'completeness',
                    'level': 'WARNING',
                    'message': f'缺失 {missing_count} 只ETF ({missing_pct:.1%})',
                    'detail': f'配置 {expected_etfs} 只, 实际 {total_etfs} 只'
                })
            else:
                status = 'OK'
            
            # 找出数据不足的ETF（少于100行）
            insufficient = [code for code, cnt in etf_counts.items() if cnt < 100]
            
            return {
                'status': status,
                'total_etfs': total_etfs,
                'expected_etfs': expected_etfs,
                'missing_count': missing_count,
                'missing_pct': round(missing_pct * 100, 1),
                'avg_rows': round(sum(etf_counts.values()) / len(etf_counts), 0) if etf_counts else 0,
                'insufficient_etfs': len(insufficient),
                'top_etfs': list(etf_counts.items())[:5]
            }
            
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def check_storage_health(self) -> Dict[str, Any]:
        """检查存储健康度"""
        if not Path(self.db_path).exists():
            return {'status': 'ERROR', 'message': '数据库文件不存在'}
        
        try:
            stat = Path(self.db_path).stat()
            db_size_mb = stat.st_size / 1024 / 1024
            
            conn = sqlite3.connect(self.db_path)
            
            # 获取总记录数
            cur = conn.execute('SELECT COUNT(*) FROM daily')
            total_records = cur.fetchone()[0]
            
            # 获取各表记录数
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cur.fetchall()]
            
            table_stats = {}
            for table in tables:
                try:
                    cur = conn.execute(f'SELECT COUNT(*) FROM {table}')
                    table_stats[table] = cur.fetchone()[0]
                except:
                    table_stats[table] = 0
            
            # 检查索引
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [row[0] for row in cur.fetchall()]
            
            conn.close()
            
            # 判断状态
            if db_size_mb > self.THRESHOLDS['max_db_size_mb']:
                status = 'WARNING'
                self.alerts.append({
                    'type': 'storage',
                    'level': 'WARNING',
                    'message': f'数据库较大 ({db_size_mb:.1f} MB)',
                    'detail': '建议执行 VACUUM 优化'
                })
            else:
                status = 'OK'
            
            return {
                'status': status,
                'db_size_mb': round(db_size_mb, 2),
                'total_records': total_records,
                'tables': table_stats,
                'indexes': len(indexes),
                'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
            
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def format_report(self) -> str:
        """格式化报告为可读字符串"""
        if not self.report:
            self.check_all()
        
        r = self.report
        alerts = r.get('alerts', [])
        
        lines = [
            "=" * 50,
            "📊 数据质量监控报告",
            "=" * 50,
            f"时间: {r['timestamp']}",
            "",
            "【新鲜度】",
            f"  状态: {r['freshness'].get('status', 'N/A')}",
            f"  最新日期: {r['freshness'].get('latest_date', 'N/A')}",
            f"  延迟天数: {r['freshness'].get('delay_days', 'N/A')}",
            "",
            "【完整性】",
            f"  状态: {r['completeness'].get('status', 'N/A')}",
            f"  ETF数量: {r['completeness'].get('total_etfs', 0)}/{r['completeness'].get('expected_etfs', 0)}",
            f"  缺失: {r['completeness'].get('missing_count', 0)} 只",
            "",
            "【存储】",
            f"  状态: {r['storage'].get('status', 'N/A')}",
            f"  数据库大小: {r['storage'].get('db_size_mb', 0)} MB",
            f"  总记录数: {r['storage'].get('total_records', 0)}",
            "",
        ]
        
        if alerts:
            lines.append("【告警】")
            for a in alerts:
                level_icon = "🔴" if a['level'] == 'ERROR' else "⚠️"
                lines.append(f"  {level_icon} {a['message']}")
                if a.get('detail'):
                    lines.append(f"      {a['detail']}")
        else:
            lines.append("【告警】无")
        
        lines.append("=" * 50)
        
        return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='数据质量监控')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    parser.add_argument('--dingtalk', action='store_true', help='发送到钉钉')
    parser.add_argument('--db-path', type=str, help='数据库路径')
    
    args = parser.parse_args()
    
    monitor = DataQualityMonitor(db_path=args.db_path)
    report = monitor.check_all()
    
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(monitor.format_report())
    
    # 告警时发送到钉钉
    if args.dingtalk and report.get('alerts'):
        try:
            from src.notify.dingtalk import DingTalkSender
            sender = DingTalkSender(mode='qwenpaw')
            message = monitor.format_report()
            sender.send(message)
            print("\n📨 已发送钉钉通知")
        except Exception as e:
            print(f"\n⚠️ 钉钉发送失败: {e}")


if __name__ == '__main__':
    main()