#!/usr/bin/env python3
"""
CLI 路径兼容性测试（Q-011）

测试 src/ 和 tests/ 中的 from scripts.X.Y import 是否对应真实文件
"""
import os
import re
import sys
import unittest
from pathlib import Path


class TestScriptsImportPaths(unittest.TestCase):
    """scripts/ 路径 import 兼容性测试"""

    def setUp(self):
        """设置项目根目录"""
        self.project_root = Path(__file__).parent.parent.parent
        self.scripts_dir = self.project_root / 'scripts'

    def test_all_script_imports_valid(self):
        """所有 from scripts.X.Y import Z 中的路径都应有效"""
        invalid_imports = []

        # 扫描 src/ 和 tests/ 中所有 .py
        for root in [self.project_root / 'src', self.project_root / 'tests']:
            for py_file in root.rglob('*.py'):
                if '__pycache__' in str(py_file):
                    continue
                # 跳过本测试文件自身（避免匹配 docstring 中的示例）
                if py_file.name == 'test_cli_paths.py':
                    continue
                content = py_file.read_text(encoding='utf-8', errors='ignore')

                # 匹配 from scripts.X.Y import Z
                pattern = r'from\s+(scripts\.[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s+import'
                for match in re.finditer(pattern, content):
                    import_path = match.group(1)
                    # 转换为文件路径
                    rel_path = import_path.replace('.', '/') + '.py'
                    full_path = self.project_root / rel_path

                    if not full_path.exists():
                        # 兼容 __init__.py
                        if not (self.project_root / import_path.replace('.', '/')).is_dir():
                            invalid_imports.append(
                                f"{py_file.relative_to(self.project_root)}: {import_path} → {rel_path} 不存在"
                            )

        if invalid_imports:
            self.fail("以下 import 路径无效:\n" + "\n".join(invalid_imports))

    def test_decision_cli_paths(self):
        """decision.py 中的 scripts. 路径必须有效（Q-008 修复）"""
        decision_py = self.project_root / 'src' / 'cli' / 'decision.py'
        if not decision_py.exists():
            self.skipTest("decision.py 不存在")

        content = decision_py.read_text(encoding='utf-8')
        pattern = r'from\s+(scripts\.[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s+import'
        scripts_imports = re.findall(pattern, content)

        self.assertGreater(len(scripts_imports), 0, "decision.py 中应有 scripts 引用")

        for imp in scripts_imports:
            rel_path = imp.replace('.', '/') + '.py'
            full_path = self.project_root / rel_path
            self.assertTrue(
                full_path.exists(),
                f"decision.py 引用 {imp} 但文件 {rel_path} 不存在"
            )

    def test_no_old_style_imports(self):
        """不应有 scripts.X（无子目录）的过时引用"""
        old_style_pattern = re.compile(r'from\s+scripts\.([a-zA-Z0-9_]+)\s+import')

        violations = []
        for root in [self.project_root / 'src', self.project_root / 'tests']:
            for py_file in root.rglob('*.py'):
                if '__pycache__' in str(py_file):
                    continue
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                for match in old_style_pattern.finditer(content):
                    module_name = match.group(1)
                    # 检查 scripts/ 根目录下是否有此 .py 文件
                    potential_path = self.scripts_dir / f"{module_name}.py"
                    if potential_path.exists():
                        violations.append(
                            f"{py_file.relative_to(self.project_root)}: "
                            f"from scripts.{module_name} 应改为 scripts.<subdir>.{module_name}"
                        )

        if violations:
            self.fail("发现过时路径引用（scripts/ 已分类）:\n" + "\n".join(violations))


if __name__ == '__main__':
    unittest.main()
