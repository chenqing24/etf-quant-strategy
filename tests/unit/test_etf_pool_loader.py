#!/usr/bin/env python3
"""
ETF池加载器 - 单元测试
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import (
    ETFListLoader,
    validate_etf_pool,
    determine_exchange,
    get_default_pool_codes,
    get_default_tencent_codes,
    FALLBACK_ETF_CODES
)


class TestValidateETF(TestCase):
    """测试ETF池验证"""
    
    def test_validate_valid_pool(self):
        """测试合法池"""
        codes = ['510300', '588000', '512880']
        self.assertTrue(validate_etf_pool(codes))
    
    def test_validate_empty_pool(self):
        """测试空池"""
        self.assertFalse(validate_etf_pool([]))
    
    def test_validate_invalid_code(self):
        """测试无效代码（长度不对）"""
        codes = ['123', '12345', '1234567']
        self.assertFalse(validate_etf_pool(codes))
    
    def test_validate_tencent_format(self):
        """测试腾讯格式"""
        codes = ['sh510300', 'sz159919']
        self.assertTrue(validate_etf_pool(codes))
    
    def test_validate_mixed_format(self):
        """测试混合格式"""
        codes = ['510300', 'sh588000', 'sz159919']
        self.assertTrue(validate_etf_pool(codes))


class TestDetermineExchange(TestCase):
    """测试交易所判断"""
    
    def test_shanghai_codes(self):
        """上交所代码"""
        self.assertEqual(determine_exchange('510300'), 'sh')
        self.assertEqual(determine_exchange('510500'), 'sh')
        self.assertEqual(determine_exchange('588000'), 'sh')
        self.assertEqual(determine_exchange('515050'), 'sh')
    
    def test_shenzhen_codes(self):
        """深交所代码"""
        self.assertEqual(determine_exchange('159919'), 'sz')
        self.assertEqual(determine_exchange('159915'), 'sz')
        self.assertEqual(determine_exchange('159952'), 'sz')
    
    def test_with_prefix(self):
        """带前缀"""
        self.assertEqual(determine_exchange('sh510300'), 'sh')
        self.assertEqual(determine_exchange('sz159919'), 'sz')


class TestETFListLoader(TestCase):
    """测试ETFListLoader"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def test_load_from_file(self):
        """测试从文件加载

        SOP-13 后：load() 优先从 DB 读取（pool_role='core'）
        池文件仅作为导出产物/兼容层，不再是输入。
        这里只验证 _load_from_file 私有方法本身的行为。
        """
        # 创建测试文件
        pool_file = Path(self.test_dir) / 'test_pool.txt'
        pool_file.write_text('''
# 测试池
ETF_POOL = [
    '510300',  # 沪深300
    '588000',  # 科创50
    '512880',  # 证券
]
''')

        loader = ETFListLoader(pool_file=str(pool_file))
        # SOP-13：直接调私有方法测文件解析（不再通过 load()）
        codes = loader._load_from_file()

        self.assertEqual(len(codes), 3)
        self.assertIn('510300', codes)
        self.assertIn('588000', codes)
        self.assertIn('512880', codes)

    def test_load_with_comments(self):
        """测试带注释的文件（SOP-13 后用 _load_from_file 直接测）"""
        pool_file = Path(self.test_dir) / 'test_pool.txt'
        pool_file.write_text('''# ETF池
ETF_POOL = [
    '510300',  # 沪深300ETF华泰柏瑞
    '588000',  # 科创50ETF华夏
    '512170',  # 医疗ETF华宝
]
''')

        loader = ETFListLoader(pool_file=str(pool_file))
        codes = loader._load_from_file()

        self.assertEqual(len(codes), 3)
    
    def test_to_tencent_codes(self):
        """测试转换为腾讯格式

        SOP-13 后：to_tencent_codes 直接接收 codes 参数（不走 DB）
        验证纯转换逻辑（510300 → sh510300, 159919 → sz159919）
        """
        loader = ETFListLoader()
        tencent_codes = loader.to_tencent_codes(['510300', '588000', '159919'])

        self.assertIn('sh510300', tencent_codes)
        self.assertIn('sh588000', tencent_codes)
        self.assertIn('sz159919', tencent_codes)
    
    def test_fallback_to_hardcode(self):
        """测试回退到硬编码"""
        loader = ETFListLoader(pool_file='/nonexistent/pool.txt')
        codes = loader.load()
        
        self.assertGreater(len(codes), 0)
        self.assertTrue(validate_etf_pool(codes))
    
    def test_caching(self):
        """测试缓存"""
        loader = ETFListLoader()
        codes1 = loader.load()
        codes2 = loader.load()
        
        self.assertEqual(codes1, codes2)
        self.assertIs(codes1, codes2)  # 同一对象
    
    def test_reload(self):
        """测试重新加载

        SOP-13 后：load() 优先从 DB 读取
        文件池仅作导出产物，reload() 也只刷缓存不刷 DB
        这里只验证：reload 后重新读 DB，长度仍 = 14
        """
        loader = ETFListLoader()
        codes1 = loader.load()
        self.assertEqual(len(codes1), 14)  # SOP-13: DB CORE 池 14 只

        # reload
        loader.reload()
        codes2 = loader.load()
        self.assertEqual(len(codes2), 14)


class TestConvenienceFunctions(TestCase):
    """测试便捷函数"""
    
    def test_get_default_pool_codes(self):
        """测试获取默认池"""
        codes = get_default_pool_codes()
        self.assertGreater(len(codes), 0)
        self.assertTrue(validate_etf_pool(codes))
    
    def test_get_default_tencent_codes(self):
        """测试获取默认池（腾讯格式）"""
        codes = get_default_tencent_codes()
        self.assertGreater(len(codes), 0)
        
        # 检查格式
        for code in codes:
            self.assertTrue(
                code.startswith('sh') or code.startswith('sz'),
                f"无效格式: {code}"
            )


class TestIntegration(TestCase):
    """集成测试"""
    
    def test_load_real_pool(self):
        """测试加载真实池

        SOP-13 后：load() 优先从 DB 读取，池文件只是导出产物
        DB CORE 池 = 14 只（510300 已剔除为 reference）
        验证：load() 返回 14 只且不含 510300
        """
        loader = ETFListLoader()
        codes = loader.load()

        # SOP-13: CORE 池 = 14 只（动态池 15 - 510300）
        self.assertEqual(len(codes), 14)

        # 510300 必须在 reference 池（不删数据）
        self.assertNotIn('510300', codes, '510300 应在 reference 池，不在 core')

        # 验证格式
        for code in codes:
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())


if __name__ == '__main__':
    main()