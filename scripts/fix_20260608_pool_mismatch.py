#!/usr/bin/env python3
"""
US-095 修复脚本：池分类与持仓不一致
- 515050 通信ETF华夏：excluded → core, tradable=1
  根因：migrate_pool_roles.py 第 70 行误认为 515050 是"养老产业ETF"，
       实际是 通信ETF华夏（fundgz.1234567.com.cn 验证）
- 510300 沪深300：删除 paper 仓位（is_real=0）
  根因：record_buy/sell 未守卫 is_real，纸面交易污染 positions 表
- 510300 池分类：保持 reference（不做交易，仅作大盘参考）

执行：python scripts/fix_20260608_pool_mismatch.py
"""
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = Path('etf_data_live/etf.db')
ARCHIVE_DIR = Path('.archive/fix-20260608-pool-mismatch')


def backup_db():
    """DB 已在外层备份，此处跳过"""
    if not ARCHIVE_DIR.exists():
        shutil.copy2(DB_PATH, ARCHIVE_DIR / 'etf.db')
    print(f"✅ DB 已备份: {ARCHIVE_DIR / 'etf.db'}")


def fix_515050(conn):
    """修复 515050: excluded → core, tradable=1"""
    c = conn.cursor()

    # 1. 查现状
    c.execute("SELECT code, name, pool_role, tradable FROM etf_names WHERE code='515050'")
    before = c.fetchone()
    print(f"\n=== 515050 修复前 ===")
    print(f"  {before}")

    # 2. 更新
    c.execute("""
        UPDATE etf_names
        SET pool_role='core', tradable=1, updated_at=?
        WHERE code='515050'
    """, (datetime.now().isoformat(),))
    print(f"  ✅ UPDATE: pool_role='excluded'→'core', tradable=0→1")

    # 3. 写 audit_log
    detail = (
        '{"reason": "US-095 修复: 515050 实际是通信ETF华夏(fundgz验证), '
        'migrate_pool_roles.py 误认为养老产业ETF", '
        '"fix": "excluded->core, tradable=1", '
        '"user_position": "2600股 @ 1.197 (6/2 买入, 实盘)"}'
    )
    c.execute("""
        INSERT INTO audit_log (timestamp, action, code, from_state, to_state, detail)
        VALUES (?, 'role_change', '515050', 'excluded', 'core', ?)
    """, (datetime.now().isoformat(), detail))
    print(f"  ✅ audit_log: role_change 已记录")

    # 4. 查修复后
    c.execute("SELECT code, name, pool_role, tradable FROM etf_names WHERE code='515050'")
    after = c.fetchone()
    print(f"  修复后: {after}")


def fix_510300_position(conn):
    """修复 510300: 删除 paper 仓位（is_real=0）"""
    c = conn.cursor()

    # 1. 查现状
    c.execute("""
        SELECT code, name, status, quantity, current_price, pnl_pct, is_real, is_reference
        FROM positions WHERE code='510300'
    """)
    before = c.fetchall()
    print(f"\n=== 510300 持仓修复前 ===")
    for r in before:
        print(f"  {r}")

    if not before:
        print("  无 510300 持仓，跳过")
        return

    # 2. 写 audit_log
    pos = before[0]
    detail = (
        f'{{"reason": "US-095 修复: 510300 paper 仓位污染 positions 表", '
        f'"is_real": {pos[6]}, "is_reference": {pos[7]}, '
        f'"quantity": {pos[3]}, "entry_price": 4.0}}'
    )
    c.execute("""
        INSERT INTO audit_log (timestamp, action, code, from_state, to_state, detail)
        VALUES (?, 'paper_position_removed', '510300', 'HOLDING', 'EMPTY', ?)
    """, (datetime.now().isoformat(), detail))
    print(f"  ✅ audit_log: paper_position_removed 已记录")

    # 3. 删 position
    c.execute("DELETE FROM positions WHERE code='510300' AND is_real=0")
    deleted = c.rowcount
    print(f"  ✅ DELETE positions: {deleted} 条")

    # 4. trade_history 保留（标注 is_paper=1 防止后续误处理）
    c.execute("""
        UPDATE trade_history
        SET is_paper=1, note='US-095: 510300 paper 仓位已清理（reference 池不入 positions）'
        WHERE code='510300' AND is_real=0
    """)
    print(f"  ✅ trade_history 已标记 is_paper=1（保留可追溯性）")

    # 5. 查修复后
    c.execute("SELECT * FROM positions WHERE code='510300'")
    after = c.fetchall()
    print(f"  修复后 510300 positions: {len(after)} 条")


def verify(conn):
    """验证修复结果"""
    c = conn.cursor()
    print(f"\n=== 验证 ===")

    # 1. 515050 状态
    c.execute("SELECT code, name, pool_role, tradable FROM etf_names WHERE code='515050'")
    r = c.fetchone()
    assert r[2] == 'core' and r[3] == 1, f"515050 修复失败: {r}"
    print(f"  ✅ 515050: pool={r[2]}, tradable={r[3]}")

    # 2. 510300 positions 为空
    c.execute("SELECT * FROM positions WHERE code='510300'")
    r = c.fetchall()
    assert len(r) == 0, f"510300 仍有持仓: {r}"
    print(f"  ✅ 510300: 无持仓")

    # 3. 池分布
    c.execute("SELECT pool_role, COUNT(*) FROM etf_names GROUP BY pool_role")
    print(f"  池分布:")
    for r in c.fetchall():
        print(f"    {r[0]}: {r[1]}")

    # 4. 池总数
    c.execute("SELECT COUNT(*) FROM etf_names")
    total = c.fetchone()[0]
    print(f"  总数: {total}")


def main():
    print("=" * 60)
    print("US-095 修复：池分类与持仓不一致")
    print("=" * 60)

    backup_db()

    conn = sqlite3.connect(DB_PATH)
    try:
        fix_515050(conn)
        fix_510300_position(conn)
        conn.commit()
        print(f"\n✅ 提交成功")
        verify(conn)
    except Exception as e:
        conn.rollback()
        print(f"\n❌ 失败: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
