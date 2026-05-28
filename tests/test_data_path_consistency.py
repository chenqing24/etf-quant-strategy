"""
数据路径一致性测试
确保所有模块使用相同的数据目录配置
"""
import pytest
import inspect
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDataPathConsistency:
    """数据路径一致性测试"""

    # 标准数据目录
    STANDARD_DATA_DIR = 'etf_data_live'
    
    # 应该使用标准路径的模块
    MODULES_TO_CHECK = [
        'src.data.loader',
        'src.data.fetcher',
        'src.analysis.report_generator',
        'src.utils.config',
        'src.cli.decision',
        'src.cross_validation',
        'src.sensitivity_analysis',
        'src.factor_report',
    ]

    def test_loader_uses_standard_path(self):
        """验证DataLoader使用标准数据路径"""
        from src.data.loader import DataLoader
        
        sig = inspect.signature(DataLoader.load)
        default = sig.parameters['data_dir'].default
        
        assert default == self.STANDARD_DATA_DIR, \
            f"DataLoader.load默认路径应为'{self.STANDARD_DATA_DIR}', 实际为'{default}'"

    def test_fetcher_uses_standard_path(self):
        """验证TencentETFetcher使用标准数据路径"""
        from src.data.fetcher import TencentETFetcher
        
        sig = inspect.signature(TencentETFetcher.__init__)
        default = sig.parameters['data_dir'].default
        
        assert default == self.STANDARD_DATA_DIR, \
            f"TencentETFetcher默认路径应为'{self.STANDARD_DATA_DIR}', 实际为'{default}'"

    def test_report_generator_uses_standard_path(self):
        """验证ETFReportGenerator使用标准数据路径"""
        from src.analysis.report_generator import ETFReportGenerator
        
        sig = inspect.signature(ETFReportGenerator.__init__)
        default = sig.parameters['data_dir'].default
        
        assert default == self.STANDARD_DATA_DIR, \
            f"ETFReportGenerator默认路径应为'{self.STANDARD_DATA_DIR}', 实际为'{default}'"

    def test_no_hardcoded_legacy_paths(self):
        """验证没有硬编码废弃的路径"""
        # 废弃的路径模式（完整匹配）
        legacy_patterns = ['etf_data_50', '../etf_data_50']
        
        for module_name in self.MODULES_TO_CHECK:
            try:
                module = __import__(module_name, fromlist=[''])
                source = inspect.getsource(module)
                
                for pattern in legacy_patterns:
                    for line in source.split('\n'):
                        stripped = line.strip()
                        if stripped.startswith('#'):
                            continue
                        if f"'{pattern}'" in line or f'"{pattern}"' in line:
                            pytest.fail(
                                f"{module_name} 中发现硬编码路径 '{pattern}': {line.strip()[:80]}"
                            )
            except Exception:
                pass

    def test_data_dir_constant_exists(self):
        """验证存在统一的数据目录常量"""
        # 尝试从config获取
        try:
            from src.utils.config import DATA_DIR
            assert DATA_DIR == self.STANDARD_DATA_DIR, \
                f"config.DATA_DIR应为'{self.STANDARD_DATA_DIR}'"
        except ImportError:
            pytest.fail("应定义 src.utils.config.DATA_DIR 常量")


class TestDataLoaderFunctionality:
    """DataLoader功能测试（与路径无关）"""

    def test_loader_loads_from_correct_path(self):
        """验证DataLoader能从实际数据目录加载"""
        from src.data.loader import DataLoader
        
        loader = DataLoader()
        # 使用标准路径加载
        data = loader.load('etf_data_live')
        
        assert len(data) > 0, "应能加载到ETF数据"
        
        # 验证数据完整性
        for code, df in list(data.items())[:5]:
            assert 'date' in df.columns, f"{code}缺少date列"
            assert 'close' in df.columns, f"{code}缺少close列"
            assert len(df) > 100, f"{code}数据量太少: {len(df)}"

    def test_loader_warns_on_missing_path(self):
        """验证DataLoader对不存在的路径有警告"""
        from src.data.loader import DataLoader
        
        loader = DataLoader()
        data = loader.load('non_existent_data_dir')
        
        assert data == {}, "不存在的路径应返回空字典"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])