"""
ETF代码映射器

统一管理各数据源ETF代码格式转换

支持的格式：
- 标准码：6位数字 (159806, 510300)
- 腾讯：同标准码
- BaoStock：sz.159806, sh.510300 (加点号)
- 东方财富：sz159806, sh510300
- 新浪：sz159806, sh510300
"""
import re
from typing import Literal


class ETFCodeMapper:
    """
    ETF代码映射器
    
    功能：
    1. 任意格式 → 标准6位码
    2. 标准码 → 目标数据源格式
    3. 判断市场 (SH/SZ)
    
    市场判断规则：
    - 上交所：510xxx, 511xxx, 512xxx, 513xxx, 515xxx, 516xxx, 518xxx, 588xxx
    - 深交所：159xxx, 161xxx 等
    """
    
    # 上交所ETF前缀
    PREFIX_SH = ('510', '511', '512', '513', '515', '516', '518', '588')
    
    # 数据源标识
    SOURCE_TENCENT = 'tencent'
    SOURCE_BAOSTOCK = 'baostock'
    SOURCE_EASTMONEY = 'eastmoney'
    SOURCE_SINA = 'sina'
    SOURCE_STANDARD = 'standard'
    
    @staticmethod
    def to_standard(code: str) -> str:
        """
        任意格式 → 标准6位码
        
        去除所有非数字字符，只保留6位数字
        
        Args:
            code: 任意格式的ETF代码
            
        Returns:
            标准6位数字码
            
        Examples:
            'sz.159806' → '159806'
            'sh510300' → '510300'
            '159806' → '159806'
        """
        if not code:
            return ''
        
        # 提取所有数字
        digits = re.sub(r'\D', '', code)
        
        # 只保留6位数字（ETF代码固定长度）
        return digits[:6] if len(digits) >= 6 else digits
    
    @staticmethod
    def to_source(code: str, source: str) -> str:
        """
        标准码 → 目标数据源格式
        
        Args:
            code: 标准6位ETF代码
            source: 数据源名称
                - tencent: 腾讯财经
                - baostock: BaoStock
                - eastmoney: 东方财富
                - sina: 新浪财经
                - standard: 标准格式
            
        Returns:
            目标数据源格式的代码
            
        Raises:
            ValueError: 如果代码不是有效的6位数字
        """
        if not code:
            return ''
        
        # 先转为标准码
        std_code = ETFCodeMapper.to_standard(code)
        
        if not std_code or len(std_code) != 6:
            # 无效代码，返回原始值
            return code
        
        # 判断市场
        market = ETFCodeMapper.get_market(std_code)
        
        # 根据数据源转换
        if source == ETFCodeMapper.SOURCE_BAOSTOCK:
            # BaoStock 格式：sz.159806, sh.510300 (加点号)
            return f"{'sh' if market == 'SH' else 'sz'}.{std_code}"
        
        elif source in (ETFCodeMapper.SOURCE_EASTMONEY, ETFCodeMapper.SOURCE_SINA):
            # 东方财富/新浪格式：sz159806, sh510300 (无点号)
            return f"{'sh' if market == 'SH' else 'sz'}{std_code}"
        
        elif source == ETFCodeMapper.SOURCE_TENCENT or source == ETFCodeMapper.SOURCE_STANDARD:
            # 腾讯/标准格式：直接返回标准码
            return std_code
        
        else:
            # 未知数据源，返回标准码
            return std_code
    
    @staticmethod
    def get_market(code: str) -> Literal['SH', 'SZ']:
        """
        判断ETF所属市场
        
        Args:
            code: 标准6位ETF代码
            
        Returns:
            'SH' (上海证券交易所) 或 'SZ' (深圳证券交易所)
        """
        if not code:
            return 'SZ'  # 默认为深圳
        
        # 判断是否以上交所说前缀开头
        for prefix in ETFCodeMapper.PREFIX_SH:
            if code.startswith(prefix):
                return 'SH'
        
        # 其他默认为深圳
        return 'SZ'
    
    @staticmethod
    def adapt(code: str, source: str) -> str:
        """
        适配器入口函数 (别名方法)
        
        相当于 to_source(to_standard(code), source)
        
        Args:
            code: 任意格式的ETF代码
            source: 目标数据源
            
        Returns:
            适配后的代码
        """
        return ETFCodeMapper.to_source(code, source)