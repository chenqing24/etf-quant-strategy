#!/usr/bin/env python3
"""
填充 ETF 元数据表 etf_names

数据来源：
1. AKTools HTTP API /api/public/fund_etf_spot_em - 全市场ETF实时行情（1486条）
2. AKTools HTTP API /api/public/fund_etf_category_sina - ETF分类列表（382条）

用法：
    python scripts/fill_etf_metadata.py [--dry-run]
"""
import argparse
import json
import time
from datetime import datetime
import requests
import sqlite3

# ========== 配置 ==========
AKTOOLS_BASE = "http://127.0.0.1:8080"
DB_PATH = "etf_data_live/etf.db"
REQUEST_TIMEOUT = 60  # 秒
MIN_INTERVAL = 5  # 最小请求间隔（秒）

# ========== 工具函数 ==========
def http_get(endpoint, params=None, timeout=REQUEST_TIMEOUT):
    """发送HTTP GET请求"""
    url = f"{AKTOOLS_BASE}{endpoint}"
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt < 2:
                print(f"  ⚠️ 请求失败，重试 ({attempt+1}/3): {e}")
                time.sleep(2)
            else:
                raise Exception(f"请求失败: {endpoint} - {e}")

def get_etf_spot():
    """获取ETF实时行情（用于提取代码和名称）"""
    print("📡 获取 ETF 实时行情...")
    data = http_get("/api/public/fund_etf_spot_em")
    print(f"  ✅ 获取 {len(data)} 条行情")
    return data

def get_etf_category():
    """获取ETF分类列表"""
    print("📡 获取 ETF 分类列表...")
    data = http_get("/api/public/fund_etf_category_sina")
    print(f"  ✅ 获取 {len(data)} 条分类")
    return data

def get_etf_scale():
    """获取上交所ETF规模数据"""
    print("📡 获取上交所ETF规模...")
    data = http_get("/api/public/fund_etf_scale_sse")
    print(f"  ✅ 获取 {len(data)} 条规模数据")
    return data

def init_db(conn):
    """初始化数据库表"""
    cursor = conn.cursor()
    
    # 检查现有表结构
    cursor.execute("PRAGMA table_info(etf_names)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    # 添加缺失的列
    new_cols = {
        'exchange': 'TEXT',
        'category': 'TEXT',
        'tracking_index': 'TEXT',
        'aum': 'REAL'
    }
    
    for col_name, col_type in new_cols.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE etf_names ADD COLUMN {col_name} {col_type}")
            print(f"  ➕ 新增列: {col_name}")
    
    conn.commit()

def fill_etf_names(conn, etf_list, dry_run=False):
    """填充 ETF 名称表"""
    cursor = conn.cursor()
    
    # 获取现有代码
    cursor.execute("SELECT code FROM etf_names")
    existing = set(row[0] for row in cursor.fetchall())
    
    # 准备插入数据
    now = datetime.now().isoformat()
    records = []
    
    for etf in etf_list:
        code = etf.get('代码') or etf.get('code')
        name = etf.get('名称') or etf.get('name')
        exchange = None
        
        # 判断交易所
        if code:
            if code.startswith('sh') or code.startswith('51'):
                exchange = 'SH'
            elif code.startswith('sz') or code.startswith('15') or code.startswith('16'):
                exchange = 'SZ'
            else:
                # 根据代码范围判断
                try:
                    code_num = int(code[:4])
                    if 500000 <= code_num <= 599999:
                        exchange = 'SH'
                    else:
                        exchange = 'SZ'
                except:
                    exchange = 'SZ'
        
        if code and code not in existing:
            records.append((
                code,
                name,
                None,  # name_sina
                exchange,
                None,  # category
                None,  # tracking_index
                None,  # aum
                1,     # verified
                1,     # verify_count
                now,
                now,
                now
            ))
    
    if dry_run:
        print(f"\n🧪 模拟模式：准备插入 {len(records)} 条记录")
        print(f"  现有记录: {len(existing)} 条")
        print(f"  将新增: {len(records)} 条")
        return len(records)
    
    # 批量插入
    if records:
        cursor.executemany("""
            INSERT OR REPLACE INTO etf_names 
            (code, name, name_sina, exchange, category, tracking_index, aum,
             verified, verify_count, last_verify_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        
        conn.commit()
        print(f"\n✅ 插入 {len(records)} 条 ETF 元数据")
    else:
        print("\n📊 无新记录需要插入")
    
    return len(records)

def fill_etf_category(conn, category_list, dry_run=False):
    """填充 ETF 分类信息"""
    cursor = conn.cursor()
    
    updated = 0
    for cat in category_list:
        name = cat.get('name') or cat.get('名称')
        if not name:
            continue
            
        # 根据名称查找对应ETF并更新分类
        cursor.execute("""
            UPDATE etf_names 
            SET category = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name LIKE ?
        """, (name, f'%{name}%'))
        
        updated += cursor.rowcount
    
    conn.commit()
    print(f"  ✅ 更新 {updated} 条分类信息")
    return updated

def fill_etf_scale(conn, scale_list, dry_run=False):
    """填充 ETF 规模信息（上交所）"""
    cursor = conn.cursor()
    
    updated = 0
    for item in scale_list:
        fund_code = item.get('基金代码')
        scale = item.get('基金份额')
        etf_type = item.get('ETF类型')
        
        if fund_code and scale:
            # 转换代码格式（6位数字 → 带交易所前缀）
            fund_code = fund_code.strip()
            if fund_code.startswith('5'):
                full_code = f"sh{fund_code}"
            else:
                full_code = f"sz{fund_code}"
            
            cursor.execute("""
                UPDATE etf_names 
                SET aum = ?, updated_at = CURRENT_TIMESTAMP
                WHERE code = ? OR code = ?
            """, (scale, full_code, fund_code))
            
            if cursor.rowcount > 0:
                updated += 1
    
    conn.commit()
    print(f"  ✅ 更新 {updated} 条规模信息（上交所ETF）")
    return updated

def show_stats(conn):
    """显示统计信息"""
    cursor = conn.cursor()
    
    # 总记录数
    cursor.execute("SELECT COUNT(*) FROM etf_names")
    total = cursor.fetchone()[0]
    
    # 各交易所分布
    cursor.execute("SELECT exchange, COUNT(*) FROM etf_names GROUP BY exchange")
    exchange_dist = cursor.fetchall()
    
    # 已验证统计
    cursor.execute("SELECT verified, COUNT(*) FROM etf_names GROUP BY verified")
    verified_dist = cursor.fetchall()
    
    print("\n" + "="*60)
    print("📊 ETF 元数据统计")
    print("="*60)
    print(f"  总记录数: {total}")
    print(f"  交易所分布:")
    for ex, cnt in exchange_dist:
        print(f"    - {ex or '未知'}: {cnt}")
    print(f"  验证状态:")
    for v, cnt in verified_dist:
        status = "✅ 已验证" if v else "❌ 未验证"
        print(f"    - {status}: {cnt}")
    
    # 样本数据
    print("\n  样本数据:")
    cursor.execute("SELECT code, name, exchange FROM etf_names LIMIT 5")
    for row in cursor.fetchall():
        print(f"    - {row[0]}: {row[1]} ({row[2]})")
    
    print("="*60)

def main():
    parser = argparse.ArgumentParser(description="填充 ETF 元数据表")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不写入数据库")
    parser.add_argument("--skip-scale", action="store_true", help="跳过规模数据获取")
    args = parser.parse_args()
    
    print("="*60)
    print("ETF 元数据填充工具")
    print("="*60)
    print(f"数据源: {AKTOOLS_BASE}")
    print(f"数据库: {DB_PATH}")
    print(f"模式: {'🧪 模拟' if args.dry_run else '📝 写入'}")
    print("="*60)
    
    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    
    # 获取实时行情数据
    print("\n📥 开始获取数据...")
    etf_spot = get_etf_spot()
    
    # 填充基本元数据
    print("\n📝 填充基本元数据...")
    count = fill_etf_names(conn, etf_spot, dry_run=args.dry_run)
    
    if not args.dry_run:
        # 获取并填充上交所ETF规模
        if not args.skip_scale:
            time.sleep(MIN_INTERVAL)
            print("\n📥 获取上交所ETF规模...")
            try:
                etf_scale = get_etf_scale()
                fill_etf_scale(conn, etf_scale)
            except Exception as e:
                print(f"  ⚠️ 获取规模数据失败: {e}")
        
        show_stats(conn)
    
    conn.close()
    
    print("\n✅ 完成！")
    return 0

if __name__ == "__main__":
    exit(main())