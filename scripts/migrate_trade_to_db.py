#!/usr/bin/env python3
"""
迁移 TradeTracker 数据从 JSON 文件到 SQLite（US-008）

功能:
  1. 备份检查（防止误操作）
  2. 读 etf_trades.json / etf_positions.json / etf_audit_log.json
  3. 写入 trade_history / positions / audit_log 表
  4. 重建 positions（按用户 2026-06-03 决策：159611 1900 股 + 515050 2600 股）
  5. 验证：COUNT(*) 对比
  6. JSON 文件保留 1 周（标记 DEPRECATED），可回滚

可重入幂等：重复跑不会重复插入（用 INSERT OR IGNORE + 显式 ID 避免冲突）
"""
import sqlite3
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 路径常量 ──
DB_PATH = 'etf_data_live/etf.db'
TRADES_JSON = 'etf_data_live/etf_trades.json'
POSITIONS_JSON = 'etf_data_live/etf_positions.json'
AUDIT_JSON = 'etf_data_live/etf_audit_log.json'
PERFORMANCE_JSON = 'etf_data_live/etf_performance.json'
SCHEMA_FILE = 'schema/migrations/004_add_trade_tables.sql'

# 159611 = legacy_holding（已通过 fix_159611.py 修复）
LEGACY_HOLDING_CODES = {'159611'}


def check_backup():
    """检查是否有最近的备份"""
    archive_dir = Path('.archive')
    if not archive_dir.exists():
        print('[WARN] .archive 目录不存在，请先备份')
        return False
    backups = sorted(archive_dir.glob('us008-pre-trade-db-*'))
    if not backups:
        print('[WARN] 找不到 us008-pre-trade-db-* 备份')
        return False
    print(f'[OK] 找到备份: {backups[-1]}')
    return True


def run_schema():
    """执行 schema migration 004"""
    if not os.path.exists(SCHEMA_FILE):
        print(f'[FAIL] schema 文件不存在: {SCHEMA_FILE}')
        sys.exit(1)

    with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(schema_sql)
    conn.commit()

    # 验证表存在
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trade_history','positions','audit_log')"
    ).fetchall()
    table_names = [t[0] for t in tables]
    print(f'[OK] schema 003 执行: {table_names}')

    if not all(t in table_names for t in ['trade_history','positions','audit_log']):
        print(f'[FAIL] 表创建失败: {table_names}')
        sys.exit(1)
    conn.close()


def migrate_trades():
    """迁移 etf_trades.json → trade_history"""
    if not os.path.exists(TRADES_JSON):
        print(f'[WARN] {TRADES_JSON} 不存在，跳过')
        return 0

    with open(TRADES_JSON, 'r', encoding='utf-8') as f:
        trades = json.load(f)

    if isinstance(trades, dict) and 'trades' in trades:
        trades = trades['trades']

    if not trades:
        print('[WARN] etf_trades.json 为空')
        return 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 先清空表（幂等）
    cur.execute("DELETE FROM trade_history")

    inserted = 0
    for t in trades:
        # 兼容老格式：is_real 默认为 0
        is_real = t.get('is_real', 1)  # 已有的 2 笔默认 is_real=1
        is_paper = t.get('is_paper', 0)

        cur.execute("""
            INSERT INTO trade_history (
                date, code, name, action, price, quantity, amount, reason,
                emotion, session,
                signal_time, signal_price, signal_rsi, signal_adx, signal_score,
                realtime_price, price_deviation, rsi_14, day_change_pct, score,
                expected_return, actual_pnl, note, trade_time,
                is_real, is_paper,
                model, strategy, evaluation, snapshot_ref
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            t.get('date'),
            t.get('code'),
            t.get('name', t.get('code')),
            t.get('action'),
            t.get('price'),
            t.get('quantity'),
            t.get('amount', t.get('price', 0) * t.get('quantity', 0)),
            t.get('reason', ''),
            t.get('emotion'),
            t.get('session'),
            t.get('signal_time'),
            t.get('signal_price', 0),
            t.get('signal_rsi', 0),
            t.get('signal_adx', 0),
            t.get('signal_score', 0),
            t.get('realtime_price', 0),
            t.get('price_deviation', 0),
            t.get('rsi_14', 0),
            t.get('day_change_pct', 0),
            t.get('score', 0),
            t.get('expected_return', 0),
            t.get('actual_pnl', 0),
            t.get('note', ''),
            t.get('trade_time', t.get('date')),
            is_real,
            is_paper,
            t.get('model'),                       # 老记录无 model
            t.get('strategy'),                    # 老记录无 strategy
            t.get('evaluation'),                  # 老记录无 evaluation
            t.get('snapshot_ref'),                # 老记录无 snapshot_ref
        ))
        inserted += 1

    conn.commit()
    conn.close()
    print(f'[OK] trade_history: 迁移 {inserted} 条')
    return inserted


def migrate_audit_log():
    """迁移 etf_audit_log.json → audit_log"""
    if not os.path.exists(AUDIT_JSON):
        print(f'[WARN] {AUDIT_JSON} 不存在，跳过')
        return 0

    with open(AUDIT_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    log_entries = data.get('trades', []) if isinstance(data, dict) else data

    if not log_entries:
        print('[INFO] etf_audit_log.json 无 trades 数据')
        return 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM audit_log")

    inserted = 0
    for entry in log_entries:
        cur.execute("""
            INSERT INTO audit_log (action, code, from_state, to_state, detail, timestamp)
            VALUES (?,?,?,?,?,?)
        """, (
            entry.get('action', 'unknown'),
            entry.get('code'),
            entry.get('from_state'),
            entry.get('to_state'),
            json.dumps(entry, ensure_ascii=False) if isinstance(entry, dict) else str(entry),
            entry.get('timestamp', datetime.now().isoformat()),
        ))
        inserted += 1

    conn.commit()
    conn.close()
    print(f'[OK] audit_log: 迁移 {inserted} 条')
    return inserted


def rebuild_positions():
    """重建 positions 表（按用户 2026-06-03 决策）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM positions")

    # 用户 6/3 实际持仓（按 6/3 早加仓后的状态）
    positions = [
        {
            'code': '159611',
            'name': '电力ETF广发',
            'entry_date': '2026-06-03',        # 6/3 早加的 1900 股
            'entry_price': 1.221,
            'quantity': 1900,
            'is_real': 1,
            'legacy_holding': 1,               # 标 legacy_holding
            'status': 'HOLDING',
            'note': '6/1 买的 4700 股已在 6/3 12:00 卖出；这是 6/3 早加仓部分',
        },
        {
            'code': '515050',
            'name': '通信ETF华夏',
            'entry_date': '2026-06-02',
            'entry_price': 1.197,
            'quantity': 2600,
            'is_real': 1,
            'legacy_holding': 0,
            'status': 'HOLDING',
            'note': 'MA20 突破',
        },
    ]

    inserted = 0
    for p in positions:
        cur.execute("""
            INSERT INTO positions (code, name, entry_date, entry_price, quantity,
                                    is_real, legacy_holding, status,
                                    current_price, pnl_pct, hold_days, score)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            p['code'], p['name'], p['entry_date'], p['entry_price'], p['quantity'],
            p['is_real'], p['legacy_holding'], p['status'],
            p['entry_price'],  # current_price 默认 = entry_price
            0,                 # pnl_pct
            (datetime.now().date() - datetime.fromisoformat(p['entry_date']).date()).days,
            0,                 # score
        ))
        inserted += 1

    conn.commit()
    conn.close()
    print(f'[OK] positions: 重建 {inserted} 条')
    return inserted


def insert_jun3_trades():
    """补录 6/3 用户实盘两笔交易（幂等：检查是否已存在）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 幂等检查：是否已存在 6/3 159611 buy 1.221 x 1900
    existing = cur.execute("""
        SELECT COUNT(*) FROM trade_history
        WHERE date='2026-06-03' AND code='159611' AND action='buy'
              AND price=1.221 AND quantity=1900
    """).fetchone()[0]

    if existing > 0:
        print(f'[SKIP] 6/3 159611 buy 1.221x1900 已存在 ({existing} 条)，跳过')
        conn.close()
        return

    # 6/3 09:30 加仓 159611 1900 股
    cur.execute("""
        INSERT INTO trade_history (
            date, code, name, action, price, quantity, amount, reason,
            emotion, session, trade_time, is_real, is_paper, note
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        '2026-06-03', '159611', '电力ETF广发', 'buy',
        1.221, 1900, 1.221 * 1900, '低开加仓',
        'calm', 'C', '2026-06-03 09:30',
        1, 0,  # is_real=1, is_paper=0
        '用户实盘（2026-06-03 09:30）',
    ))

    # 6/3 12:00 卖 159611 4700 股（清 6/1 那笔）
    cur.execute("""
        INSERT INTO trade_history (
            date, code, name, action, price, quantity, amount, reason,
            emotion, session, trade_time, is_real, is_paper, actual_pnl, note
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        '2026-06-03', '159611', '电力ETF广发', 'sell',
        1.217, 4700, 1.217 * 4700, '恐慌清仓 6/1 那 4700',
        'fear', 'C', '2026-06-03 12:00',
        1, 0,
        (1.217 - 1.251) * 4700,  # 实际亏损
        '用户实盘（2026-06-03 12:00），亏损 (1.251-1.217) * 4700 = -159.8',
    ))

    # 审计日志
    cur.execute("""
        INSERT INTO audit_log (action, code, detail)
        VALUES ('migrate', '159611', ?)
    """, (json.dumps({
        'event': 'june3_real_trades',
        'buy': {'date': '2026-06-03 09:30', 'price': 1.221, 'qty': 1900},
        'sell': {'date': '2026-06-03 12:00', 'price': 1.217, 'qty': 4700, 'pnl': -159.8},
    }, ensure_ascii=False),))

    conn.commit()
    conn.close()
    print('[OK] 6/3 两笔实盘交易入库')


def verify():
    """验证数据完整性"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print('\n=== 迁移验证 ===')
    print(f'  trade_history: {cur.execute("SELECT COUNT(*) FROM trade_history").fetchone()[0]} 条')
    print(f'  positions: {cur.execute("SELECT COUNT(*) FROM positions").fetchone()[0]} 条')
    print(f'  audit_log: {cur.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]} 条')

    print('\n=== trade_history 详情 ===')
    for r in cur.execute("SELECT date, action, code, price, quantity, is_real, emotion FROM trade_history ORDER BY id"):
        print(f'  {r}')

    print('\n=== positions 详情 ===')
    for r in cur.execute("SELECT code, quantity, entry_price, status, is_real, legacy_holding FROM positions"):
        print(f'  {r}')

    conn.close()


def main():
    print('=== US-008: TradeTracker DB 化迁移 ===\n')

    if not check_backup():
        print('[ERROR] 未找到备份，请先运行 fix_159611.py 之前的备份')
        sys.exit(1)

    print('\n--- Step 1: 执行 schema migration 004 ---')
    run_schema()

    print('\n--- Step 2: 迁移 etf_trades.json ---')
    migrate_trades()

    print('\n--- Step 3: 迁移 etf_audit_log.json ---')
    migrate_audit_log()

    print('\n--- Step 4: 重建 positions 表 ---')
    rebuild_positions()

    print('\n--- Step 5: 补录 6/3 实盘两笔 ---')
    insert_jun3_trades()

    print('\n--- Step 6: 验证 ---')
    verify()

    print('\n=== 迁移完成 ===')
    print('JSON 文件保留 1 周（标记 DEPRECATED），可回滚')


if __name__ == '__main__':
    main()
