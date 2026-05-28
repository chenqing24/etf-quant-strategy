#!/usr/bin/env python3
"""
每日数据健康检查脚本
收盘后自动运行，检查数据质量和新鲜度
"""
import sys
import os
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.facade import DataFacade
from src.notify.notifier import SignalNotifier


def get_latest_dates_sample(codes, sample_size=10):
    """抽查多只ETF的最新日期"""
    import sqlite3
    
    conn = sqlite3.connect('etf_data_live/etf.db')
    cursor = conn.cursor()
    
    # 随机抽查
    placeholders = ','.join(['?'] * len(codes))
    cursor.execute(f'''
        SELECT code, MAX(date) as max_date 
        FROM daily 
        WHERE code IN ({placeholders})
        GROUP BY code
    ''', codes)
    
    results = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return results


def daily_check() -> dict:
    """
    执行每日数据健康检查
    
    Returns:
        {
            'passed': bool,      # 是否通过
            'issues': list,      # 问题列表
            'stats': dict        # 统计数据
        }
    """
    issues = []
    warnings = []
    stats = {}
    
    try:
        # 1. 检查ETF总数
        import sqlite3
        conn = sqlite3.connect('etf_data_live/etf.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(DISTINCT code) FROM daily')
        etf_count = cursor.fetchone()[0]
        stats['etf_count'] = etf_count
        
        if etf_count < 60:
            issues.append(f"⚠️ ETF数量不足: {etf_count}只 (目标≥60只)")
        else:
            print(f"✅ ETF数量: {etf_count}只")
        
        # 2. 检查数据新鲜度
        cursor.execute('SELECT MAX(date) FROM daily')
        latest_date = cursor.fetchone()[0]
        stats['latest_date'] = latest_date
        
        today = datetime.now()
        if latest_date:
            latest_dt = datetime.strptime(latest_date, '%Y-%m-%d')
            days_ago = (today - latest_dt).days
            
            if days_ago > 2:
                issues.append(f"⚠️ 数据过期: 最新日期{latest_date} ({days_ago}天前)")
            else:
                print(f"✅ 数据新鲜度: 最新{latest_date} ({days_ago}天前)")
        
        # 3. 抽查数据行数
        cursor.execute('''
            SELECT code, COUNT(*) as rows 
            FROM daily 
            GROUP BY code 
            ORDER BY rows
            LIMIT 5
        ''')
        shortest = cursor.fetchall()
        
        stats['shortest_etfs'] = shortest
        if shortest and shortest[0][1] < 300:
            issues.append(f"⚠️ 数据不足: {shortest[0][0]}仅{shortest[0][1]}行 (<300天)")
        
        # 4. 抽查字段约束
        cursor.execute('''
            SELECT code, COUNT(*) 
            FROM daily 
            WHERE high < low OR high < close OR close < low
            GROUP BY code
        ''')
        violations = cursor.fetchall()
        
        if violations:
            issues.append(f"⚠️ 字段约束违规: {len(violations)}只ETF")
            stats['violations'] = violations
        
        conn.close()
        
    except Exception as e:
        issues.append(f"❌ 检查异常: {str(e)}")
    
    # 判断结果
    passed = len(issues) == 0
    
    return {
        'passed': passed,
        'issues': issues,
        'warnings': warnings,
        'stats': stats
    }


def format_report(check_result: dict) -> str:
    """格式化检查报告"""
    lines = []
    lines.append("📊 **每日数据健康检查**")
    lines.append("")
    lines.append(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    
    # 统计信息
    stats = check_result.get('stats', {})
    lines.append("**数据概况**")
    lines.append(f"- ETF数量: {stats.get('etf_count', 'N/A')}只")
    lines.append(f"- 最新日期: {stats.get('latest_date', 'N/A')}")
    
    if stats.get('shortest_etfs'):
        shortest = stats['shortest_etfs'][0]
        lines.append(f"- 最短数据: {shortest[0]} ({shortest[1]}行)")
    
    lines.append("")
    
    # 问题列表
    issues = check_result.get('issues', [])
    if issues:
        lines.append("**⚠️ 发现问题**")
        for issue in issues:
            lines.append(f"- {issue}")
    else:
        lines.append("**✅ 检查通过**")
    
    return "\n".join(lines)


def main():
    """主入口"""
    print("=" * 50)
    print("📊 每日数据健康检查")
    print("=" * 50)
    print()
    
    # 执行检查
    result = daily_check()
    
    # 输出报告
    report = format_report(result)
    print(report)
    
    # 如果有问题，打印告警
    if not result['passed']:
        print()
        print("⚠️ 发现数据问题，请检查！")
    
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())