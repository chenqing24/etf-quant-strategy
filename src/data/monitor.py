#!/usr/bin/env python3
"""
数据质量监控模块

用途：
    - 检查数据新鲜度（分钟级告警，阈值80分钟）
    - 检查数据完整性（交易日<50条=ERROR，缺失>20%=WARNING）
    - 检查存储健康度
    - 生成监控报告并发送到钉钉

被谁调用：
    - QwenPaw cron 定时任务（每日 09:00 工作日）
    - 入口：`python -m src.data.monitor`

功能说明：
    - 替代已删除的 scripts/daily_data_check.py（功能重复）
    - 是数据质量监控的唯一入口
    - 包含分钟级新鲜度检查 + 完整性检查

使用方式：
    # 检查并输出报告
    python -m src.data.monitor
    
    # 检查并输出JSON
    python -m src.data.monitor --json
    
    # 发送到钉钉
    python -m src.data.monitor --dingtalk

依赖：
    - src.constants (DATA_DIR, DB_NAME)
    - src.notify.notifier (钉钉告警)
    - sqlite3 (数据查询)

注意事项：
    - 数据新鲜度阈值：80分钟（80分钟内无更新=告警）
    - 完整性阈值：50条（<50条=ERROR），缺失>20%（WARNING）
    - 仅工作日运行（周一至周五）
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
from src.utils.execution_source import (
    ExecutionSource,
    add_source_argument,
    get_source_from_argv,
)
from src.utils.safety_gate import (
    require_force,
    add_force_argument,
    add_dry_run_argument,
    SafetyGateError,
)


# 工作日判断（A股周一至周五）
WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def is_trading_day(dt: datetime = None) -> bool:
    """
    判断是否为A股交易日（周一至周五）
    
    注意：节假日需要外部补充，这里只做基础判断
    """
    if dt is None:
        dt = datetime.now()
    return dt.weekday() < 5  # 0-4 是周一到周五


class DataQualityMonitor:
    """数据质量监控器"""
    
    # 告警阈值（分钟级）
    THRESHOLDS = {
        'max_delay_minutes': 80,       # 数据延迟超过80分钟告警
        'min_active_etfs': 30,        # 活跃ETF少于30个告警
        'max_missing_pct': 0.15,      # 缺失超过15%告警
        'max_db_size_mb': 100,        # 数据库超过100MB提示
        # 交易日完整性检查
        'max_day_missing_pct': 0.20,  # 交易日数据缺失超过20%告警
        # B1 修复: min_day_count 改为动态方法 get_min_day_count()，跟随核心池大小
    }

    def get_min_day_count(self) -> int:
        """
        动态获取交易日最小数据量阈值
        
        来源: v9 交易池大小（etf_data_live/top500_target_pool.txt）
        下限: 10（避免过小阈值失效）
        
        为什么不写死 50: 历史 monitor 假设完整扩展池（~80 只），
        实际 v9 池只 15 只，硬编码 50 会误报。
        """
        try:
            from src.data.etf_pool_loader import ETFListLoader
            loader = ETFListLoader()
            codes = loader.load()
            return max(len(codes), 10)  # 下限保护
        except Exception as e:
            # ETFListLoader 失败时回退到 v9 默认值
            return 15  # v9 默认值（核心池 14 + 510300 大盘参考 = 15）
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(DATA_DIR, DB_NAME)
        self.alerts: List[Dict] = []  # ERROR级别
        self.warnings: List[Dict] = []  # WARNING级别
        self.report: Dict[str, Any] = {}
    
    def check_all(self) -> Dict[str, Any]:
        """执行所有检查"""
        self.alerts = []  # ERROR级别
        self.warnings = []  # WARNING级别
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'freshness': self.check_data_freshness(),
            'completeness': self.check_data_completeness(),
            'storage': self.check_storage_health(),
            'alerts': self.alerts,    # ERROR only
            'warnings': self.warnings  # WARNING only
        }
        
        self.report = report
        return report
    
    def check_data_freshness(self) -> Dict[str, Any]:
        """检查数据新鲜度（分钟级）
        
        逻辑：
        1. 获取上一个交易日（周末往前推）
        2. 检查是否有所需的交易日数据
        3. 如果有，计算入库时间与当前时间的延迟分钟数
        4. 超过阈值告警
        """
        if not Path(self.db_path).exists():
            return {
                'status': 'ERROR',
                'message': '数据库文件不存在',
                'latest_date': None,
                'delay_minutes': None
            }
        
        try:
            now = datetime.now()
            is_trade_day = is_trading_day(now)
            
            # 计算上一个交易日
            weekday = now.weekday()
            if weekday == 0:  # 周一
                last_trading_day = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            elif weekday == 6:  # 周日
                last_trading_day = (now - timedelta(days=2)).strftime('%Y-%m-%d')
            else:
                last_trading_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            conn = sqlite3.connect(self.db_path)
            
            # 获取最新日期和对应的入库时间
            cur = conn.execute('''
                SELECT date, MAX(updated_at) as last_update
                FROM daily
                GROUP BY date
                ORDER BY date DESC
                LIMIT 1
            ''')
            row = cur.fetchone()
            
            # 获取上一交易日的记录数
            cur2 = conn.execute(
                'SELECT COUNT(*) FROM daily WHERE date = ?',
                (last_trading_day,)
            )
            last_trading_day_count = cur2.fetchone()[0]
            
            conn.close()
            
            if row is None or row[0] is None:
                return {
                    'status': 'ERROR',
                    'message': '无数据',
                    'latest_date': None,
                    'delay_minutes': None
                }
            
            latest_date = row[0]
            last_update_str = row[1]
            
            # 计算延迟分钟数
            if last_update_str:
                try:
                    last_update = datetime.fromisoformat(last_update_str)
                    delay_minutes = (now - last_update).total_seconds() / 60
                except:
                    delay_minutes = None
            else:
                delay_minutes = None
            
            # 判断状态
            if not is_trade_day:
                # 非交易日（周末）：OK，不需要告警
                return {
                    'status': 'OK',
                    'message': '非交易日，数据正常',
                    'latest_date': latest_date,
                    'last_update': last_update_str,
                    'delay_minutes': delay_minutes,
                    'is_trading_day': False,
                    'last_trading_day': last_trading_day,
                    'last_trading_day_count': last_trading_day_count
                }
            
            # 工作日 09:00 检查：必须有上一个交易日的数据
            if latest_date < last_trading_day:
                # 数据缺失：期望last_trading_day，但实际最新是latest_date
                status = 'ERROR'
                self.alerts.append({
                    'type': 'freshness',
                    'level': 'ERROR',
                    'message': f'数据缺失: 期望{last_trading_day}，实际{latest_date}',
                    'detail': f"延迟{(now - datetime.strptime(latest_date, '%Y-%m-%d')).days}天"
                })
            elif delay_minutes is not None and delay_minutes > self.THRESHOLDS['max_delay_minutes']:
                # 数据延迟超过80分钟
                status = 'WARNING'
                self.warnings.append({
                    'type': 'freshness',
                    'level': 'WARNING',
                    'message': f'数据延迟 {delay_minutes:.0f} 分钟（阈值{self.THRESHOLDS["max_delay_minutes"]}分钟）',
                    'detail': f'最新入库: {last_update_str}'
                })
            else:
                # 数据正常
                status = 'OK'
            
            return {
                'status': status,
                'latest_date': latest_date,
                'last_update': last_update_str,
                'delay_minutes': delay_minutes,
                'is_trading_day': True,
                'last_trading_day': last_trading_day,
                'last_trading_day_count': last_trading_day_count
            }
            
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': str(e),
                'latest_date': None,
                'delay_minutes': None
            }
    
    def check_data_completeness(self) -> Dict[str, Any]:
        """检查数据完整性
        
        包含两部分：
        1. 历史完整性：ETF数量和历史数据行数
        2. 交易日完整性：上一交易日的数据条数是否正常
        """
        if not Path(self.db_path).exists():
            return {'status': 'ERROR', 'message': '数据库文件不存在'}
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            # === 1. 历史完整性检查 ===
            cur = conn.execute('SELECT COUNT(DISTINCT code) FROM daily')
            total_etfs = cur.fetchone()[0]
            
            cur = conn.execute('''
                SELECT code, COUNT(*) as cnt 
                FROM daily 
                GROUP BY code 
                ORDER BY cnt DESC
            ''')
            etf_counts = {row[0]: row[1] for row in cur.fetchall()}
            
            try:
                from src.data.etf_pool_loader import ETFListLoader
                # B2 修复: 使用 v9 交易池（top500_target_pool.txt）作为 expected_etfs
                # 历史 ETF_POOLS.core+extended=71 是 v3.0 时代的数据采集池，
                # v9 已迁移到 15 只核心交易池（2026-06-02 启用）
                loader = ETFListLoader()
                expected_etfs = len(loader.load())
            except:
                expected_etfs = total_etfs
            
            missing_count = max(0, expected_etfs - len(etf_counts))
            missing_pct = missing_count / expected_etfs if expected_etfs > 0 else 0
            
            # === 2. 交易日完整性检查 ===
            now = datetime.now()
            is_trade_day = is_trading_day(now)
            
            # 计算上一交易日
            weekday = now.weekday()
            if weekday == 0:  # 周一
                last_trading_day = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            elif weekday == 6:  # 周日
                last_trading_day = (now - timedelta(days=2)).strftime('%Y-%m-%d')
            else:
                last_trading_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            # 获取上一交易日记录数
            cur = conn.execute(
                'SELECT COUNT(*) FROM daily WHERE date = ?',
                (last_trading_day,)
            )
            last_day_count = cur.fetchone()[0]
            
            conn.close()
            
            # === 判断状态 ===
            # 初始化状态
            status = 'OK'
            trade_day_status = 'OK'
            
            # 1. 历史完整性
            if missing_pct > self.THRESHOLDS['max_missing_pct']:
                status = 'ERROR'
                self.alerts.append({
                    'type': 'completeness',
                    'level': 'ERROR',
                    'message': f'缺失 {missing_count} 只ETF ({missing_pct:.1%})',
                    'detail': f'配置 {expected_etfs} 只, 实际 {total_etfs} 只'
                })
            elif missing_count > 0:
                if status != 'ERROR':
                    status = 'WARNING'
                self.warnings.append({
                    'type': 'completeness',
                    'level': 'WARNING',
                    'message': f'缺失 {missing_count} 只ETF ({missing_pct:.1%})',
                    'detail': f'配置 {expected_etfs} 只, 实际 {total_etfs} 只'
                })
            
            # 2. 交易日完整性（仅交易时段检查）
            if is_trade_day:
                # B3 修复: 基准改为配置池大小（不再用前一日历史）
                baseline_count = self.get_min_day_count()
                
                if last_day_count == 0:
                    # 没有数据
                    trade_day_status = 'ERROR'
                    self.alerts.append({
                        'type': 'trade_day_completeness',
                        'level': 'ERROR',
                        'message': f'交易日 {last_trading_day} 无数据',
                        'detail': f'基准: {baseline_count}条'
                    })
                elif last_day_count < self.get_min_day_count():
                    # 数据太少
                    trade_day_status = 'ERROR'
                    self.alerts.append({
                        'type': 'trade_day_completeness',
                        'level': 'ERROR',
                        'message': f'交易日 {last_trading_day} 数据不足 ({last_day_count}条)',
                        'detail': f'基准: {baseline_count}条, 阈值: {self.get_min_day_count()}条'
                    })
                elif last_day_count < baseline_count * (1 - self.THRESHOLDS['max_day_missing_pct']):
                    # 数据缺失超过阈值
                    day_missing_pct = (baseline_count - last_day_count) / baseline_count
                    trade_day_status = 'WARNING'
                    self.warnings.append({
                        'type': 'trade_day_completeness',
                        'level': 'WARNING',
                        'message': f'交易日 {last_trading_day} 数据缺失 {day_missing_pct:.1%}',
                        'detail': f'实际: {last_day_count}条, 基准: {baseline_count}条'
                    })
                
                if trade_day_status == 'ERROR':
                    status = 'ERROR'
                elif trade_day_status == 'WARNING' and status != 'ERROR':
                    status = 'WARNING'
            
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
                'top_etfs': list(etf_counts.items())[:5],
                # 交易日完整性
                'last_trading_day': last_trading_day,
                'last_day_count': last_day_count,
                # B3 修复: 移除 prev_day_count 字段，基准来自配置池（get_min_day_count）
                'baseline_count': self.get_min_day_count(),
                'is_trading_day': is_trade_day,
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
                self.warnings.append({
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
        warnings = r.get('warnings', [])
        freshness = r.get('freshness', {})
        
        # 计算显示的延迟信息
        delay_info = ""
        if freshness.get('delay_minutes') is not None:
            mins = freshness['delay_minutes']
            if mins >= 60:
                delay_info = f"{mins/60:.1f} 小时"
            else:
                delay_info = f"{mins:.0f} 分钟"
        elif freshness.get('delay_days') is not None:
            delay_info = f"{freshness['delay_days']} 天"
        
        lines = [
            "=" * 50,
            "📊 数据质量监控报告",
            "=" * 50,
            f"时间: {r['timestamp']}",
            f"类型: {'📈 交易日' if freshness.get('is_trading_day', False) else '📅 非交易日'}",
            "",
            "【新鲜度】",
            f"  状态: {freshness.get('status', 'N/A')}",
            f"  最新日期: {freshness.get('latest_date', 'N/A')}",
            f"  延迟: {delay_info if delay_info else 'N/A'}",
            f"  入库时间: {freshness.get('last_update', 'N/A')}",
            "",
            "【完整性】",
            f"  状态: {r['completeness'].get('status', 'N/A')}",
            f"  ETF数量: {r['completeness'].get('total_etfs', 0)}/{r['completeness'].get('expected_etfs', 0)}",
            f"  缺失: {r['completeness'].get('missing_count', 0)} 只",
            f"  交易日: {r['completeness'].get('last_trading_day', 'N/A')} ({r['completeness'].get('last_day_count', 0)}条)",
            f"  配置池: {r['completeness'].get('baseline_count', 0)}只",
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
                lines.append(f"  🔴 {a['message']}")
                if a.get('detail'):
                    lines.append(f"      {a['detail']}")
        else:
            lines.append("【告警】无")
        
        if warnings:
            lines.append("")
            lines.append("【警告】")
            for w in warnings:
                lines.append(f"  ⚠️ {w['message']}")
                if w.get('detail'):
                    lines.append(f"      {w['detail']}")
        
        lines.append("=" * 50)
        
        return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='数据质量监控')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    parser.add_argument('--dingtalk', action='store_true', help='发送到钉钉')
    # ── US-002: Safety Gate ───────────────────────────────────
    add_force_argument(parser)  # 钉钉推送是 Moderate 操作
    add_dry_run_argument(parser)
    # ─────────────────────────────────────────────────────────────
    parser.add_argument('--db-path', type=str, help='数据库路径')

    # ── US-001: 执行源标识（audit / 未来门禁） ──────────────────
    add_source_argument(parser)
    # ─────────────────────────────────────────────────────────────

    args = parser.parse_args()

    # US-001: 解析执行源（argv 缺省 → 走 get_source_from_argv 默认 MANUAL）
    execution_source = get_source_from_argv() if args.source is None else ExecutionSource(args.source)
    print(f"🔖 execution_source = {execution_source.value}")

    monitor = DataQualityMonitor(db_path=args.db_path)
    report = monitor.check_all()
    
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(monitor.format_report())
    
    # 告警或警告时发送到钉钉
    if args.dingtalk and (report.get('alerts') or report.get('warnings')):
        # US-002: 钉钉推送是 Moderate 破坏性操作（dingtalk_send）
        try:
            require_force(
                "dingtalk_send",
                source=execution_source,
                force=args.force,
                dry_run=args.dry_run,
                target=None,
            )
        except SafetyGateError as e:
            print(str(e))
            sys.exit(2)

        if args.dry_run:
            print("\n[dry-run] 将发送钉钉通知，未实际执行")
            sys.exit(0)

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