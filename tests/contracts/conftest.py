"""契约测试 fixtures"""
import pytest
import tempfile
import sqlite3
from pathlib import Path
import pandas as pd


@pytest.fixture
def temp_db():
    """创建临时数据库 fixture"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / 'test.db'
        conn = sqlite3.connect(db_path)
        
        conn.execute('''
            CREATE TABLE daily (
                code TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER
            )
        ''')
        
        conn.execute('''
            CREATE TABLE stock_info (
                code TEXT PRIMARY KEY,
                name TEXT
            )
        ''')
        
        # 插入测试数据：510300
        test_data = [
            ('510300', '2024-01-02', 4.0, 4.1, 3.9, 4.0, 1000000),
            ('510300', '2024-01-03', 4.0, 4.2, 3.9, 4.1, 1100000),
            ('510300', '2024-01-04', 4.1, 4.3, 4.0, 4.2, 1200000),
            ('510300', '2024-01-05', 4.2, 4.4, 4.1, 4.3, 1300000),
            ('510300', '2024-01-08', 4.3, 4.5, 4.2, 4.4, 1400000),
        ]
        conn.executemany(
            'INSERT INTO daily VALUES (?, ?, ?, ?, ?, ?, ?)',
            test_data
        )
        conn.commit()
        conn.close()
        
        yield str(db_path)


@pytest.fixture
def temp_db_multi_codes(temp_db):
    """多 ETF 代码的临时数据库"""
    # 复用 temp_db，然后添加更多数据
    import sqlite3
    conn = sqlite3.connect(temp_db)
    
    more_data = [
        ('510500', '2024-01-02', 8.0, 8.2, 7.8, 8.0, 2000000),
        ('510500', '2024-01-03', 8.0, 8.3, 7.9, 8.1, 2100000),
        ('510500', '2024-01-04', 8.1, 8.4, 8.0, 8.2, 2200000),
    ]
    conn.executemany(
        'INSERT INTO daily VALUES (?, ?, ?, ?, ?, ?, ?)',
        more_data
    )
    conn.commit()
    conn.close()
    
    yield temp_db


@pytest.fixture
def valid_ohlcv_df():
    """符合契约的 OHLCV DataFrame fixture"""
    return pd.DataFrame({
        'code': ['510300'] * 5,
        'date': ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08'],
        'open': [4.0, 4.0, 4.1, 4.2, 4.3],
        'high': [4.1, 4.2, 4.3, 4.4, 4.5],
        'low': [3.9, 3.9, 4.0, 4.1, 4.2],
        'close': [4.0, 4.1, 4.2, 4.3, 4.4],
        'volume': [1000000, 1100000, 1200000, 1300000, 1400000],
    })


@pytest.fixture
def invalid_ohlcv_df():
    """违反契约的 OHLCV DataFrame fixture"""
    return pd.DataFrame({
        'code': ['510300'] * 5,
        'date': ['2024-01-02', 'invalid', '2024-01-04', '2024-01-05', '2024-01-08'],
        'open': [4.0, 4.0, 4.1, 4.2, 4.3],
        'high': [4.1, 3.8, 4.3, 4.4, 4.5],   # 第2条 high < low
        'low': [3.9, 4.2, 4.0, 4.1, 4.2],
        'close': [4.0, 4.1, 4.2, 4.3, 4.4],
        'volume': [1000000, 1100000, 1200000, 1300000, 1400000],
    })


@pytest.fixture
def large_ohlcv_df():
    """足够大的 OHLCV DataFrame（用于指标计算测试）"""
    dates = pd.date_range('2023-01-01', periods=200).strftime('%Y-%m-%d')
    base_price = 4.0
    return pd.DataFrame({
        'code': ['510300'] * 200,
        'date': dates,
        'open': [base_price] * 200,
        'high': [base_price + 0.1] * 200,
        'low': [base_price - 0.1] * 200,
        'close': [base_price] * 200,
        'volume': [1000000] * 200,
    })