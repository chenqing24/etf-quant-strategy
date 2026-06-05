#!/usr/bin/env python3
"""US-024 选项 C：补全 515070 audit_log

US-024 bug 真相：
- 6/5 用户手工 record_buy('515070', is_real=1) 入库 trade_history
- 但 can_buy 拒绝（持仓数=2 已达 max=2）
- trade_history 入库 + return None → 跳过 audit_log
- 现在 trade_history 有 515070 但 audit_log 缺 515070 的 state_change

US-024 选项 C：补 audit_log 让审计一致
"""
import sys
import os
import sqlite3

sys.path.insert(0, '.')
os.chdir('/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')


def main():
    conn = sqlite3.connect('etf_data_live/etf.db')
    cur = conn.cursor()

    # 1. 检查现状
    print("=== 检查 515070 audit_log 现状 ===")
    rows = cur.execute(
        "SELECT id, code, from_state, to_state, detail, timestamp FROM audit_log WHERE code='515070'"
    ).fetchall()
    print(f"audit_log 中 515070 记录数 = {len(rows)}")

    if rows:
        print("已存在记录，跳过补全")
        conn.close()
        return

    # 2. 补 audit_log
    # US-024: 515070 6/5 13:50 用户实盘买入 1500 @ 2.574
    # 状态：EMPTY → HOLDING（虽然 can_buy 拒绝，但用户实盘确实买了）
    detail = '{"reason": "实盘买入 1500股 @ 2.574 (US-024 补 audit_log)"}'
    cur.execute("""
        INSERT INTO audit_log (action, code, from_state, to_state, detail, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('state_change', '515070', 'EMPTY', 'HOLDING', detail, '2026-06-05 14:32:00'))
    new_id = cur.lastrowid
    conn.commit()
    print(f"✅ INSERT audit_log id={new_id}")

    # 3. 验证
    rows = cur.execute(
        "SELECT id, code, from_state, to_state, detail, timestamp FROM audit_log WHERE code='515070'"
    ).fetchall()
    print(f"补后 515070 audit_log 记录数 = {len(rows)}")
    for r in rows:
        print(f"  {r}")

    conn.close()
    print("\n✅ 515070 audit_log 补全完成（US-024 选项 C）")


if __name__ == '__main__':
    main()
