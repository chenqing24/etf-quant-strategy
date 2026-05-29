"""
数据层异常定义
统一管理数据层可能出现的异常
"""
from typing import List, Dict


class DataValidationError(Exception):
    """数据校验异常
    
    当写入数据格式校验失败时抛出
    """
    
    def __init__(self, message: str, errors: List[Dict] = None):
        super().__init__(message)
        self.errors = errors or []
    
    def __str__(self):
        if self.errors:
            error_summary = ', '.join([
                f"{e.get('code', '?')}.{e.get('field', '?')}" 
                for e in self.errors[:5]
            ])
            return f"{super().__str__()}: {error_summary}"
        return super().__str__()


class DataSourceError(Exception):
    """数据源异常
    
    当所有数据源都失败时抛出
    """
    
    def __init__(self, message: str, sources_tried: List[str] = None):
        super().__init__(message)
        self.sources_tried = sources_tried or []
    
    def __str__(self):
        tried = ', '.join(filter(None, self.sources_tried))
        return f"{super().__str__()} (tried: {tried})"


class DataNotFoundError(Exception):
    """数据不存在异常"""
    
    def __init__(self, code: str, data_type: str = 'daily'):
        super().__init__(f"未找到 {data_type} 数据: {code}")
        self.code = code
        self.data_type = data_type


class DatabaseConnectionError(Exception):
    """数据库连接异常"""
    
    def __init__(self, message: str, db_path: str = None):
        super().__init__(message)
        self.db_path = db_path