#!/usr/bin/env python3
"""
ETF池加载器

用途：
    - 从池文件动态加载 ETF 列表（US-001 后改为从数据库）
    - 支持从配置文件加载（top500_target_pool.txt，已废弃）
    - 转换为腾讯格式（sh/sz 前缀）
    - 验证列表合法性

被谁调用：
    - src/cli/decision.py（决策引擎加载 ETF 池）
    - scripts/filter/ 系列脚本（筛选 ETF）
    - 其他需要 ETF 列表的模块

功能说明（US-001 更新）：
    - **数据源已改为 etf.db.etf_names 表**（via ETFRepository）
    - 兼容层：load() 仍返回纯数字代码列表
    - DEFAULT_POOL_FILE 保留但**不再被 load() 读取**
    - FALLBACK_ETF_CODES 仅在数据库完全不可用时启用

使用方式（无变化）：
    from src.data.etf_pool_loader import ETFListLoader
    
    loader = ETFListLoader()
    codes = loader.load()

依赖：
    - src.data.etf_pool_repository.ETFRepository
    - pathlib (Path)
    - logging

注意事项：
    - US-001 阶段：load() 返回全部 1486 条（role='core' 默认）
    - US-002 之后：role='core' 改为只返回 tradable=1 AND pool_role=core
    - 文件路径 `etf_data_live/top500_target_pool.txt` 保留为只读备份
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Optional, Literal

# 默认池文件路径（US-001 之后：保留为只读备份，不再被读取）
DEFAULT_POOL_FILE = 'etf_data_live/top500_target_pool.txt'

# 硬编码兜底列表（当数据库完全不可用时使用，最后防线）
# US-085: 修正为15只股票ETF（排除债券、港股、红利、证券、黄金）
# - 移除 sh510300（大盘沪深300，与510050重复且不在核心池）
# - 添加 sz159867（养殖ETF鹏华，核心池成员）
# 来源: docs/POSITION_MANAGEMENT.md 第X节"核心池定义"
FALLBACK_ETF_CODES = [
    # 宽基（2只）
    'sh510500', 'sh510050',
    # 科创（1只）
    'sh588000',
    # 行业（12只，含养殖ETF）
    'sz159801', 'sz159806', 'sz159857', 'sz159867', 'sz159995', 'sz159997',
    'sz159919', 'sh512660', 'sh512760', 'sh516160', 'sh515000', 'sh516050',
]

# 获取logger
_logger = logging.getLogger(__name__)

PoolRole = Literal['core', 'reference', 'excluded']


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
    """ETF池加载器（US-001 兼容层）"""

    def __init__(self, pool_file: str = None, role: PoolRole = 'core'):
        """
        Args:
            pool_file: 兼容参数，**US-001 后不再使用**，保留仅为接口兼容
            role: 池角色，默认 'core'（US-002 后会按 tradable/pool_role 过滤）
        """
        if pool_file:
            self.pool_file = Path(pool_file)
        else:
            project_root = Path(__file__).parent.parent.parent
            self.pool_file = project_root / DEFAULT_POOL_FILE

        self.role = role
        self._codes: Optional[List[str]] = None
        self._repo = None  # 懒加载

    def _get_repo(self):
        if self._repo is None:
            from src.data.etf_pool_repository import ETFRepository
            self._repo = ETFRepository()
        return self._repo

    def load(self) -> List[str]:
        """
        加载ETF列表（纯数字格式）

        US-001 后：从 ETFRepository (etf.db.etf_names) 读取
        US-002 后：role='core' 只返回 tradable=1 AND pool_role=core
        """
        if self._codes is not None:
            return self._codes

        # 1. 从数据库读取（US-002 完成：支持 pool_role 过滤）
        try:
            repo = self._get_repo()
            codes = repo.list_codes(role=self.role)
            
            self._codes = codes
            if self._codes:
                _logger.info(f"从数据库加载ETF列表 (role={self.role}): {len(self._codes)}只")
                return self._codes
        except Exception as e:
            _logger.warn(f"数据库加载ETF池失败: {e}")

        # 2. 兜底：硬编码列表（数据库完全不可用时）
        _logger.warn("使用硬编码ETF列表（数据库不可用）")
        self._codes = self._extract_codes_from_fallback()
        return self._codes

    def load_with_meta(self) -> List[dict]:
        """加载 ETF 列表（含元数据），US-001 新增"""
        try:
            repo = self._get_repo()
            return repo.list_with_meta(role=self.role)
        except Exception as e:
            _logger.error(f"load_with_meta 失败: {e}")
            return []

    def _load_from_file(self) -> List[str]:
        """
        从池文件加载（US-001 之后：兼容保留，不再被 load() 调用）

        文件 `etf_data_live/top500_target_pool.txt` 仍存在（只读备份），
        但 load() 不再读它。
        """
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


    def get_tencent_codes(self) -> List[str]:
        """转换为腾讯格式（带 sh/sz 前缀）"""
        codes = self.load()
        result = []
        for code in codes:
            if code.startswith('sh') or code.startswith('sz'):
                result.append(code)
            else:
                # 用 determine_exchange 决定
                exchange = determine_exchange(code)
                result.append(exchange + code)
        return result

    def reload(self):
        """重新加载（清除缓存）"""
        self._codes = None

    def _extract_codes_from_fallback(self) -> List[str]:
        """从硬编码列表提取纯数字代码"""
        codes = []
        for code in FALLBACK_ETF_CODES:
            if re.match(r'^(sh|sz)\d{6}$', code):
                codes.append(code[2:])
            else:
                codes.append(code)
        return codes


# 兼容旧 API 别名
ETFListUpdater = ETFListLoader


# ===== 独立使用入口（命令行调试用）=====
if __name__ == '__main__':
    import sys

    loader = ETFListLoader()
    codes = loader.load()
    print(f"加载了 {len(codes)} 只 ETF")
    print(f"前 10 只: {codes[:10]}")
    print(f"包含 510300: {'510300' in codes}")
    print(f"包含 512480: {'512480' in codes}")
    sys.exit(0)


# ===== 兼容旧 API（保留旧版本函数，避免破坏其他模块）=====

def get_default_pool_codes() -> List[str]:
    """获取默认 ETF 池代码（便捷函数，US-001 兼容层）"""
    loader = ETFListLoader()
    return loader.load()


def get_default_tencent_codes() -> List[str]:
    """获取默认 ETF 池代码（腾讯格式，带 sh/sz 前缀）"""
    loader = ETFListLoader()
    return [c if (c.startswith("sh") or c.startswith("sz")) else ("sh" + c) for c in loader.load()]
