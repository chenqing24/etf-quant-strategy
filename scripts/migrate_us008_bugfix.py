#!/usr/bin/env python3
"""
US-014 R3: 迁移脚本 - 修复 US-008 漏改的 current_capital

功能：
- 备份 performance.json 到 .archive/
- 根据 trade_history 重算 current_capital
- dry_run 模式默认（不写库）

公式：
  current_capital = initial_capital - SUM(buy amount) + SUM(sell amount)
  (只算 is_real=1 的实盘交易)

用法：
  python scripts/migrate_us008_bugfix.py --dry-run  # 预览
  python scripts/migrate_us008_bugfix.py --apply    # 实际执行

教训（按 SOUL 规则）：
- 教训 70: 迁移脚本必须幂等
- 规则 18: json.dump + 立即验证
- 规则 8: 关键操作前必须备份
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.constants import DB_PATH, TRADES_FILE  # noqa: E402


def backup_performance(data_dir: str = '.') -> str:
    """
    备份 performance.json（SOUL 规则 8: 关键操作前必须备份）

    Returns:
        备份文件路径
    """
    src = os.path.join(data_dir, 'etf_performance.json')
    if not os.path.exists(src):
        return ''
    archive_dir = os.path.join(data_dir, '.archive', 'us014-bugfix')
    os.makedirs(archive_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(archive_dir, f'etf_performance_{ts}.json')
    shutil.copy2(src, dst)
    return dst


def compute_current_capital(db_path: str, is_real_only: bool = True) -> dict:
    """
    根据 trade_history 重算 current_capital

    Args:
        db_path: SQLite 数据库路径
        is_real_only: 只算实盘交易（is_real=1），默认 True

    Returns:
        {
            'initial_capital': float,
            'total_buy': float,
            'total_sell': float,
            'new_capital': float,
            'trades_count': int,
        }
    """
    conn = sqlite3.connect(db_path)
    try:
        # 1. 读 initial_capital（来自 performance.json 而非 DB）
        #    因为 performance.json 是主存储，DB 不存
        perf_file = os.path.join(os.path.dirname(db_path), 'etf_performance.json')
        if os.path.exists(perf_file):
            with open(perf_file) as f:
                perf = json.load(f).get('performance', {})
                initial = float(perf.get('initial_capital', 20000))
        else:
            initial = 20000.0

        # 2. 算实盘 buy/sell 总额
        where = "WHERE action='buy'"
        if is_real_only:
            where += " AND is_real=1"
        total_buy = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM trade_history {where}"
        ).fetchone()[0]

        where = "WHERE action='sell'"
        if is_real_only:
            where += " AND is_real=1"
        total_sell = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM trade_history {where}"
        ).fetchone()[0]

        # 3. 算交易笔数
        where = "WHERE 1=1"
        if is_real_only:
            where += " AND is_real=1"
        trades_count = conn.execute(
            f"SELECT COUNT(*) FROM trade_history {where}"
        ).fetchone()[0]

        new_capital = initial - total_buy + total_sell

        return {
            'initial_capital': initial,
            'total_buy': round(total_buy, 2),
            'total_sell': round(total_sell, 2),
            'new_capital': round(new_capital, 2),
            'trades_count': trades_count,
        }
    finally:
        conn.close()


def apply_capital(data_dir: str, new_capital: float) -> bool:
    """
    应用新的 current_capital（按 SOUL 规则 18: json.dump + 立即验证）

    Returns:
        True 成功, False 失败
    """
    perf_file = os.path.join(data_dir, 'etf_performance.json')
    if not os.path.exists(perf_file):
        return False
    try:
        with open(perf_file, 'r') as f:
            data = json.load(f)
        old = data.get('performance', {}).get('current_capital', 20000)
        data['performance']['current_capital'] = new_capital
        data['performance']['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(perf_file, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 立即验证
        with open(perf_file, 'r') as f:
            json.load(f)
        print(f"✅ current_capital: {old} → {new_capital}")
        return True
    except Exception as e:
        print(f"❌ 写入失败: {e}")
        return False


def run(dry_run: bool = True, data_dir: str = '.') -> dict:
    """
    主流程

    Args:
        dry_run: True=只报告不写，False=实际执行
        data_dir: 数据目录（默认 '.'）

    Returns:
        计算结果 dict
    """
    # US-014: DB_PATH 来自 src/constants.py（US-008 默认）
    from src.constants import DB_PATH
    db_path = DB_PATH if data_dir == '.' else os.path.join(data_dir, 'etf.db')
    if not os.path.exists(db_path):
        print(f"❌ DB 不存在: {db_path}")
        return {}

    result = compute_current_capital(db_path, is_real_only=True)
    print(f"\n{'='*60}")
    print(f"US-014 R3: current_capital 重算 {'(DRY RUN)' if dry_run else '(APPLY)'}")
    print(f"{'='*60}")
    print(f"DB 路径: {db_path}")
    print(f"initial_capital: {result['initial_capital']}")
    print(f"实盘 buy 总和: {result['total_buy']}（{result['trades_count']} 笔交易）")
    print(f"实盘 sell 总和: {result['total_sell']}")
    print(f"新 current_capital: {result['new_capital']}")
    print(f"  公式: {result['initial_capital']} - {result['total_buy']} + {result['total_sell']} = {result['new_capital']}")

    if not dry_run:
        backup_path = backup_performance(data_dir)
        if backup_path:
            print(f"\n📦 备份: {backup_path}")
        if apply_capital(data_dir, result['new_capital']):
            print(f"✅ 已应用")
        else:
            print(f"❌ 应用失败")
    else:
        print(f"\n⚠️ DRY RUN - 未写库（加 --apply 执行）")

    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='US-014 R3 迁移脚本')
    parser.add_argument('--apply', action='store_true', help='实际执行（默认 dry-run）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览不写（默认行为）')
    parser.add_argument('--data-dir', default='.', help='数据目录（默认 .）')
    args = parser.parse_args()
    dry_run = not args.apply
    run(dry_run=dry_run, data_dir=args.data_dir)
