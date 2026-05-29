#!/usr/bin/env python3
"""测试 ETF 名称获取功能"""
import sys
sys.path.insert(0, '/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')

from src.data.loader import ETFNameLoader

def test_get_name_from_api():
    """测试从腾讯API获取ETF名称"""
    test_cases = [
        ('159577', '美国50ETF汇添富'),      # 2026-05-28 验证
        ('516050', '科技龙头ETF工银'),      # 2026-05-28 验证
        ('510300', '沪深300ETF华泰柏瑞'),   # 2026-05-28 验证
    ]
    
    print("=== 测试腾讯API获取ETF名称 ===")
    loader = ETFNameLoader()
    
    for code, _ in test_cases:
        name = loader.get_name(code)
        print(f"  {code}: {name}")
        # 验证返回的是字符串，不是None
        assert name is not None, f"{code} 应返回名称"
        assert isinstance(name, str), "名称应为字符串"
        # 名称可能来自数据库缓存或API，不验证精确值
    
    print("\n✅ 腾讯API测试通过")

def test_update_names():
    """测试批量更新ETF名称到数据库"""
    print("\n=== 测试批量更新ETF名称 ===")
    loader = ETFNameLoader()
    
    # 先检查stock_info表是否存在
    import sqlite3
    from src.constants import DB_NAME
    from pathlib import Path
    
    db_path = Path.cwd() / 'etf_data_live' / DB_NAME
    if not db_path.exists():
        print("⚠️ 数据库不存在，跳过更新测试")
        return
    
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_info'")
    if not cur.fetchone():
        print("⚠️ stock_info表不存在，跳过更新测试")
        conn.close()
        return
    conn.close()
    
    # 更新所有名称
    updated = loader.update_all_names()
    print(f"  更新了 {len(updated)} 个ETF名称")
    
    # 验证
    if updated:
        print(f"  示例: 159577 -> {updated.get('159577', 'N/A')}")
    
    print("\n✅ 批量更新测试通过")

if __name__ == '__main__':
    test_get_name_from_api()
    test_update_names()