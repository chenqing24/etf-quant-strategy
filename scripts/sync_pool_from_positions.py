#!/usr/bin/env python3
"""
US-095 同步脚本: 池角色反向同步（positions → etf_names）

目的: 防止"用户开了实盘持仓但 ETF 仍在 excluded/untracked"的不一致
逻辑:
  1. 遍历 positions 表，is_real=1 的持仓
  2. 对每个持仓 code，确保 etf_names.pool_role='core', tradable=1
  3. 跳过 reference 池的持仓（如 510300，仅作大盘跟踪，不入 core）
  4. 写 audit_log 记录变更

用法:
  python scripts/sync_pool_from_positions.py
  python scripts/sync_pool_from_positions.py --dry-run  # 只打印不修改
"""
import sys
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

DB_PATH = Path('etf_data_live/etf.db')
REFERENCE_CODES = {'510300'}  # 大盘参考，不进 core


def get_open_real_positions(conn) -> list:
    """获取所有 is_real=1 的开放持仓"""
    return conn.execute("""
        SELECT code, name, quantity, entry_price
        FROM positions
        WHERE status='HOLDING' AND is_real=1
    """).fetchall()


def get_etf_pool_role(conn, code: str) -> tuple:
    """获取 ETF 的 pool_role 和 tradable"""
    row = conn.execute(
        "SELECT pool_role, tradable FROM etf_names WHERE code=?", (code,)
    ).fetchone()
    return row if row else (None, None)


def sync(conn, dry_run: bool = False) -> dict:
    """主同步逻辑"""
    positions = get_open_real_positions(conn)
    print(f"📊 找到 {len(positions)} 条实盘持仓 (is_real=1)")

    changes = {'upgraded': [], 'skipped': [], 'errors': []}

    for code, name, qty, price in positions:
        if code in REFERENCE_CODES:
            print(f"  ⏭ {code} {name} - reference 池（大盘参考）跳过")
            changes['skipped'].append((code, 'reference'))
            continue

        pool_role, tradable = get_etf_pool_role(conn, code)

        if pool_role == 'core' and tradable == 1:
            print(f"  ✓ {code} {name} - 已在 core 池")
            continue

        if pool_role is None:
            print(f"  ⚠ {code} {name} - 不在 etf_names 表（无元数据）")
            changes['errors'].append((code, 'no_metadata'))
            continue

        # 需要升级到 core
        old_state = f"{pool_role}/tradable={tradable}"
        new_state = "core/tradable=1"
        print(f"  🔄 {code} {name} - {old_state} → {new_state}")

        if dry_run:
            print(f"    [DRY-RUN] 跳过实际修改")
            continue

        conn.execute("""
            UPDATE etf_names
            SET pool_role='core', tradable=1, updated_at=?
            WHERE code=?
        """, (datetime.now().isoformat(), code))

        # 写 audit_log
        detail = (
            f'{{"reason": "US-095 sync_pool_from_positions: user real position", '
            f'"quantity": {qty}, "entry_price": {price}, '
            f'"from": "{old_state}", "to": "{new_state}"}}'
        )
        conn.execute("""
            INSERT INTO audit_log (timestamp, action, code, from_state, to_state, detail)
            VALUES (?, 'sync_from_position', ?, ?, 'core', ?)
        """, (datetime.now().isoformat(), code, pool_role, detail))

        changes['upgraded'].append((code, old_state, new_state))

    return changes


def main():
    parser = argparse.ArgumentParser(description='池角色反向同步（positions → etf_names）')
    parser.add_argument('--dry-run', action='store_true', help='只打印不修改')
    args = parser.parse_args()

    print("=" * 60)
    print("US-095 sync_pool_from_positions")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"❌ DB 不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        changes = sync(conn, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()
        print(f"\n=== 汇总 ===")
        print(f"  升级: {len(changes['upgraded'])} 条")
        print(f"  跳过: {len(changes['skipped'])} 条 (reference)")
        print(f"  错误: {len(changes['errors'])} 条 (无元数据)")
        if changes['upgraded']:
            print(f"\n升级明细:")
            for code, old, new in changes['upgraded']:
                print(f"  {code}: {old} → {new}")
        if not args.dry_run and changes['upgraded']:
            print(f"\n✅ 已提交")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
