#!/usr/bin/env python3
"""
ETF池加载器

用途：
    - 从池文件动态加载 ETF 列表
    - 支持从配置文件加载（top500_target_pool.txt）
    - 转换为腾讯格式（sh/sz 前缀）
    - 验证列表合法性

被谁调用：
    - src/cli/decision.py（决策引擎加载 ETF 池）
    - scripts/filter/ 系列脚本（筛选 ETF）
    - 其他需要 ETF 列表的模块

功能说明：
    - 支持配置优先，文件不存在时回退到硬编码
    - 硬编码兜底列表（当池文件不存在时使用）
    - 默认池文件路径：etf_data_live/top500_target_pool.txt

使用方式：
    from src.data.etf_pool_loader import ETFListLoader
    
    loader = ETFListLoader()
    codes = loader.load()

依赖：
    - pathlib (Path)
    - logging

注意事项：
    - 返回的代码带 sh/sz 前缀（如 'sh510300'）
    - 文件不存在时使用硬编码兜底
    - 支持自定义池文件路径
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Optional

# 默认池文件路径
DEFAULT_POOL_FILE = 'etf_data_live/top500_target_pool.txt'

# 硬编码兜底列表（当池文件不存在时使用）
FALLBACK_ETF_CODES = [
    'sh510300', 'sh510500', 'sz159919', 'sh159915',
    'sh512880', 'sh512170', 'sh512200',
    'sh159928', 'sh159825',
    'sh512010', 'sh512500', 'sh159952',
    'sh159997', 'sh159995', 'sh512760', 'sh159801',
    'sh159823', 'sh515050',
    'sh159857', 'sh516160', 'sh159806',
    'sh159942', 'sh510050',
    'sh512660',
    'sh159920', 'sh159867',
    'sh518880', 'sh159934',
    'sh511010',
    'sh516050', 'sh159577', 'sh515000', 'sh513100',
]

# 获取logger
_logger = logging.getLogger(__name__)


def validate_etf_pool(codes: List[str]) -> bool:
    """
    验证ETF池合法性
    """
    if not codes:
        return False
    
    for code in codes:
        if not isinstance(code, str):
            return False
        if code.isdigit():
            if len(code) != 6:
                return False
        elif re.match(r'^(sh|sz)\d{6}$', code):
            pass
        else:
            return False
    
    if len(codes) != len(set(codes)):
        _logger.warn("ETF池包含重复代码，已自动去重")
    
    return True


def determine_exchange(code: str) -> str:
    """判断ETF交易所"""
    if code.startswith('sh') or code.startswith('sz'):
        return code[:2]
    
    if code.startswith('51') or code.startswith('50'):
        return 'sh'
    elif code.startswith('15') or code.startswith('13'):
        return 'sz'
    elif code.startswith('56') or code.startswith('52'):
        return 'sh'
    else:
        return 'sh'


class ETFListLoader:
    """ETF池加载器"""
    
    def __init__(self, pool_file: str = None):
        if pool_file:
            self.pool_file = Path(pool_file)
        else:
            project_root = Path(__file__).parent.parent.parent
            self.pool_file = project_root / DEFAULT_POOL_FILE
        
        self._codes: Optional[List[str]] = None
    
    def load(self) -> List[str]:
        """加载ETF列表（纯数字格式）"""
        if self._codes is not None:
            return self._codes
        
        if self.pool_file.exists():
            try:
                self._codes = self._load_from_file()
                if self._codes:
                    _logger.info(f"从池文件加载ETF列表: {len(self._codes)}只")
                    return self._codes
            except Exception as e:
                _logger.warn(f"加载池文件失败: {e}")
        
        _logger.warn("使用硬编码ETF列表（池文件不存在或加载失败）")
        self._codes = self._extract_codes_from_fallback()
        return self._codes
    
    def _load_from_file(self) -> List[str]:
        """从池文件加载"""
        content = self.pool_file.read_text()
        
        match = re.search(r'ETF_POOL\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if not match:
            raise ValueError("无法从池文件提取ETF_POOL列表")
        
        codes_str = match.group(1)
        
        # 按行分割，处理跨行注释
        codes = []
        for line in codes_str.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 移除行内注释
            if '#' in line:
                line = line.split('#')[0].strip()
            if not line:
                continue
            # 提取代码
            code_match = re.search(r'["\']?(\d{6})["\']?', line)
            if code_match:
                codes.append(code_match.group(1))
        
        return codes
    
    def _extract_codes_from_fallback(self) -> List[str]:
        """从硬编码列表提取纯数字代码"""
        codes = []
        for code in FALLBACK_ETF_CODES:
            if re.match(r'^(sh|sz)\d{6}$', code):
                codes.append(code[2:])
            else:
                codes.append(code)
        return codes
    
    def to_tencent_codes(self, codes: List[str] = None) -> List[str]:
        """转换为腾讯格式（加 sh/sz 前缀）"""
        if codes is None:
            codes = self.load()
        
        result = []
        for code in codes:
            if code.startswith('sh') or code.startswith('sz'):
                result.append(code)
            else:
                exchange = determine_exchange(code)
                result.append(f"{exchange}{code}")
        
        return result
    
    def get_tencent_codes(self) -> List[str]:
        """获取腾讯格式的ETF代码列表"""
        return self.to_tencent_codes()
    
    def load_tencent_format(self) -> List[str]:
        """获取腾讯格式的ETF代码列表"""
        return self.get_tencent_codes()
    
    def reload(self):
        """重新加载（清除缓存）"""
        self._codes = None


def get_default_pool_codes() -> List[str]:
    """获取默认ETF池代码（便捷函数）"""
    loader = ETFListLoader()
    return loader.load()


def get_default_tencent_codes() -> List[str]:
    """获取默认ETF池代码（腾讯格式）"""
    loader = ETFListLoader()
    return loader.get_tencent_codes()


# 兼容性别名
ETFListUpdater = ETFListLoader


if __name__ == '__main__':
    loader = ETFListLoader()
    
    print("=" * 60)
    print("ETF池加载器测试")
    print("=" * 60)
    
    codes = loader.load()
    print(f"\n纯数字格式: {len(codes)}只")
    print(codes[:5], "...")
    
    tencent_codes = loader.get_tencent_codes()
    print(f"\n腾讯格式: {len(tencent_codes)}只")
    print(tencent_codes[:5], "...")
    
    print(f"\n验证结果: {validate_etf_pool(codes)}")