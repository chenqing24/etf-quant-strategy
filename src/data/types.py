"""
数据类型定义
定义数据层使用的数据结构
"""
from dataclasses import dataclass, asdict
from typing import Dict, Optional, List
from datetime import datetime


@dataclass
class RealtimeQuote:
    """实时报价数据结构
    
    用于存储从API获取的实时行情数据
    """
    code: str           # 证券代码（无前缀）
    name: str           # 证券名称
    price: float        # 当前价格
    change: float       # 涨跌额
    change_pct: float   # 涨跌幅%
    volume: float       # 成交量
    amount: float       # 成交额
    timestamp: str      # 数据时间戳 ISO格式
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_tencent(cls, text: str) -> 'RealtimeQuote':
        """
        从腾讯API响应解析
        
        格式: v_sz159577="51~名称~代码~价格~涨跌~涨跌幅~成交量~成交额~..."
        
        Example:
            >>> text = 'v_sz159577="51~美国50ETF汇添富~159577~1.583~0.032~2.06~11300000~17890000"'
            >>> quote = RealtimeQuote.from_tencent(text)
            >>> print(quote.price)
            1.583
        """
        try:
            # 解析: v_sz159577="51~名称~..."
            match = text.split('="')
            if len(match) < 2:
                raise ValueError(f"无法解析腾讯API响应: {text}")
            
            parts = match[1].rstrip('"').split('~')
            
            return cls(
                code=parts[2] if len(parts) > 2 else '',
                name=parts[1] if len(parts) > 1 else '',
                price=float(parts[3]) if len(parts) > 3 else 0,
                change=float(parts[4]) if len(parts) > 4 else 0,
                change_pct=float(parts[5]) if len(parts) > 5 else 0,
                volume=float(parts[6]) if len(parts) > 6 else 0,
                amount=float(parts[7]) if len(parts) > 7 else 0,
                timestamp=datetime.now().isoformat()
            )
        except (IndexError, ValueError) as e:
            raise ValueError(f"解析实时报价失败: {text}, error: {e}")
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RealtimeQuote':
        """从字典创建"""
        return cls(**data)


@dataclass
class DailyRecord:
    """日线记录数据结构
    
    用于单条日线数据
    """
    code: str
    date: str           # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: Optional[float] = None
    source: Optional[str] = 'tencent'
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def validate(self) -> List[Dict]:
        """验证数据，返回错误列表"""
        errors = []
        
        if self.close <= 0:
            errors.append({'field': 'close', 'value': self.close, 'error': 'must be > 0'})
        if self.open <= 0:
            errors.append({'field': 'open', 'value': self.open, 'error': 'must be > 0'})
        if self.high < self.close or self.high < self.open:
            errors.append({'field': 'high', 'error': 'must be >= max(open, close)'})
        if self.low > self.close or self.low > self.open:
            errors.append({'field': 'low', 'error': 'must be <= min(open, close)'})
        if self.volume < 0:
            errors.append({'field': 'volume', 'value': self.volume, 'error': 'must be >= 0'})
        
        return errors


@dataclass
class StockInfo:
    """证券基本信息"""
    code: str
    name: str
    exchange: str       # SH/SZ/BJ
    category: str = 'ETF'
    status: str = 'active'
    list_date: Optional[str] = None
    delist_date: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)