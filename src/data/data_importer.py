"""
数据导入模块

从CSV文件批量导入数据到SQLite数据库
"""
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional
from src.data.database import Database


class DataImporter:
    """数据导入器"""
    
    def __init__(self, db: Database, data_dir: str = "etf_data_live"):
        """
        初始化数据导入器
        
        Args:
            db: 数据库实例
            data_dir: CSV数据目录
        """
        self.db = db
        self.data_dir = Path(data_dir)
    
    def load_csv(self, code: str) -> Optional[pd.DataFrame]:
        """
        加载单个CSV文件
        
        Args:
            code: ETF代码（可能带sh/sz前缀）
            
        Returns:
            DataFrame
        """
        # 尝试不同文件名格式
        filenames = [
            f"{code}.csv",
            f"sh{code}.csv",
            f"sz{code}.csv",
        ]
        
        for filename in filenames:
            csv_file = self.data_dir / filename
            if csv_file.exists():
                try:
                    df = pd.read_csv(csv_file)
                    return df
                except Exception as e:
                    continue
        
        return None
    
    def import_stock_info(self, code: str, name: str = None) -> bool:
        """
        导入股票基本信息
        
        Args:
            code: ETF代码
            name: ETF名称
            
        Returns:
            是否成功
        """
        exchange = 'SH' if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')) else 'SZ'
        full_code = f"sh.{code}" if exchange == 'SH' else f"sz.{code}"
        
        data = {
            'code': code,
            'name': name or f'ETF_{code}',
            'exchange': exchange,
            'full_code': full_code,
            'data_source': 'tencent',
            'created_at': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            self.db.insert_or_update('stock_info', data, ['code'])
            return True
        except Exception as e:
            print(f"导入股票信息失败 {code}: {e}")
            return False
    
    def import_daily_price(self, code: str, df: pd.DataFrame) -> int:
        """
        批量导入日线数据（使用executemany优化）
        
        Args:
            code: ETF代码
            df: DataFrame (columns: date, open, high, low, close, volume)
            
        Returns:
            成功导入的记录数
        """
        if df.empty:
            return 0
        
        # 标准化列名
        column_map = {
            '日期': 'date',
            'date': 'date',
            '开盘': 'open',
            'open': 'open',
            '最高': 'high',
            'high': 'high',
            '最低': 'low',
            'low': 'low',
            '收盘': 'close',
            'close': 'close',
            '成交量': 'volume',
            'volume': 'volume',
        }
        
        df = df.copy()
        for old_col, new_col in column_map.items():
            if old_col in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)
        
        if 'date' not in df.columns or 'close' not in df.columns:
            return 0
        
        # 批量插入
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        records = []
        now = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for _, row in df.iterrows():
            try:
                if pd.isna(row.get('date')) or row.get('close', 0) <= 0:
                    continue
                
                record = {
                    'code': code,
                    'date': str(row['date']),
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'close': float(row.get('close', 0)),
                    'volume': float(row.get('volume', 0)),
                    'created_at': now
                }
                records.append(record)
            except:
                continue
        
        if not records:
            conn.close()
            return 0
        
        # 使用REPLACE INTO批量插入
        for record in records:
            cursor.execute("""
                INSERT OR REPLACE INTO daily_price 
                (code, date, open, high, low, close, volume, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (record['code'], record['date'], record['open'], record['high'],
                  record['low'], record['close'], record['volume'], record['created_at']))
        
        conn.commit()
        conn.close()
        
        return len(records)
    
    def import_from_csv(self, code: str, name: str = None) -> Dict[str, int]:
        """
        从CSV文件导入数据
        
        Args:
            code: ETF代码
            name: ETF名称
            
        Returns:
            导入结果统计
        """
        result = {'stock_info': 0, 'daily_price': 0}
        
        df = self.load_csv(code)
        if df is None:
            return result
        
        if self.import_stock_info(code, name):
            result['stock_info'] = 1
        
        count = self.import_daily_price(code, df)
        if count > 0:
            result['daily_price'] = count
        
        return result
    
    def batch_import(self, codes: List[str], names: Dict[str, str] = None) -> Dict[str, any]:
        """
        批量导入数据
        
        Args:
            codes: ETF代码列表
            names: ETF名称字典
            
        Returns:
            导入结果统计
        """
        total = len(codes)
        success = 0
        fail_list = []
        total_records = 0
        
        for i, code in enumerate(codes):
            name = names.get(code) if names else None
            result = self.import_from_csv(code, name)
            
            if result['stock_info'] > 0:
                success += 1
                total_records += result['daily_price']
                print(f"[{i+1}/{total}] ✅ {code}: {result['daily_price']}条")
            else:
                fail_list.append(code)
                print(f"[{i+1}/{total}] ❌ {code}")
        
        return {
            'total': total,
            'success': success,
            'failed': len(fail_list),
            'fail_list': fail_list,
            'total_records': total_records
        }
    
    def get_all_csv_codes(self) -> List[str]:
        """获取所有CSV文件中的ETF代码"""
        codes = []
        if not self.data_dir.exists():
            return codes
        
        for f in self.data_dir.glob("*.csv"):
            if f.is_file():
                code = f.stem
                if code.startswith('sh') or code.startswith('sz'):
                    code = code[2:]
                codes.append(code)
        
        return sorted(set(codes))
    
    def verify_import(self, code: str) -> Dict:
        """验证导入结果"""
        stock_info = self.db.query(
            "SELECT * FROM stock_info WHERE code = ?", (code,)
        )
        price_data = self.db.query(
            "SELECT COUNT(*) as cnt FROM daily_price WHERE code = ?", (code,)
        )
        csv_data = self.load_csv(code)
        csv_count = len(csv_data) if csv_data is not None else 0
        
        return {
            'code': code,
            'stock_info_exists': len(stock_info) > 0,
            'db_price_count': price_data[0]['cnt'] if price_data else 0,
            'csv_price_count': csv_count,
            'match': price_data[0]['cnt'] == csv_count if price_data else False
        }


def import_all_etf_data(db_path: str = "data/etf_factors.db", data_dir: str = "etf_data_live"):
    """导入所有ETF数据"""
    db = Database(db_path)
    importer = DataImporter(db, data_dir)
    
    codes = importer.get_all_csv_codes()
    print(f"发现 {len(codes)} 个ETF数据文件")
    
    result = importer.batch_import(codes)
    
    print("\n" + "=" * 50)
    print("导入完成")
    print(f"总计: {result['total']}")
    print(f"成功: {result['success']}")
    print(f"失败: {result['failed']}")
    print(f"总记录数: {result['total_records']}")
    
    if result['fail_list']:
        print(f"失败列表: {result['fail_list']}")
    
    return result


if __name__ == "__main__":
    import_all_etf_data()