#!/usr/bin/env python3
"""US-019 单元测试: pre-commit hook 拦截硬编码策略参数

US-018 教训: 17 处硬编码散落无单一真相源。
US-019 修复: 在 commit 阶段自动拦截硬编码模式。

设计文档: docs/US-019-DESIGN.md
测试策略: TDD 红 → 绿
"""
import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────
# 测试数据
# ─────────────────────────────────────────────────────────────

# US-019 硬编码模式（5 数字字面量 + 5 字符串）
HARDCODED_NUM_PATTERN = r'(^|[^0-9.])0\.06([^0-9]|$)|(^|[^0-9.])0\.10([^0-9]|$)|(^|[^0-9.])0\.94([^0-9]|$)|(^|[^0-9.])1\.10([^0-9]|$)|(^|[^0-9.])0\.04([^0-9]|$)'

HARDCODED_STR_PATTERNS = [
    '"-6%"',
    '"+10%"',
    '"回撤4%"',
    '"最长15天"',
    '"仓位90%"',
]


# ─────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────

def _init_temp_repo(temp_dir):
    """初始化临时 git repo + 复制真实 pre-commit hook"""
    os.makedirs(temp_dir, exist_ok=True)
    subprocess.run(['git', 'init', '-q'], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 't@t.c'],
                  cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 't'],
                  cwd=temp_dir, check=True, capture_output=True)
    src_hook = ROOT / '.git' / 'hooks' / 'pre-commit'
    dst_hook = Path(temp_dir) / '.git' / 'hooks' / 'pre-commit'
    dst_hook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_hook, dst_hook)
    os.chmod(dst_hook, 0o755)


def _try_commit(temp_dir, rel_file, content):
    """写入文件, git add, git commit, 返回 (exit, output)"""
    file_path = Path(temp_dir) / rel_file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    subprocess.run(['git', 'add', rel_file], cwd=temp_dir, check=True, capture_output=True)
    result = subprocess.run(['git', 'commit', '-m', 't', '-q'],
                           cwd=temp_dir, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout + result.stderr


# ─────────────────────────────────────────────────────────────
# 测试: 拦截硬编码
# ─────────────────────────────────────────────────────────────

class TestPrecommitHookInterception:
    """US-019: pre-commit hook 拦截硬编码"""

    def test_intercept_hardcoded_stop_loss(self):
        """拦截: -0.06 数字字面量"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _init_temp_repo(temp_dir)
            exit_code, output = _try_commit(temp_dir, 'src/bad.py', 'x = -0.06\n')
            assert exit_code != 0, f"应拦截, exit={exit_code}, out={output}"
            assert 'US-019' in output, f"应提示 US-019, out={output}"

    def test_intercept_hardcoded_take_profit(self):
        """拦截: 0.10 数字字面量"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _init_temp_repo(temp_dir)
            exit_code, output = _try_commit(temp_dir, 'src/bad.py', 'x = trade_price * 0.10\n')
            assert exit_code != 0, f"应拦截, exit={exit_code}, out={output}"

    def test_intercept_hardcoded_string(self):
        """拦截: '-6%' 字符串"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _init_temp_repo(temp_dir)
            exit_code, output = _try_commit(temp_dir, 'src/bad.py', 'label = "-6%"\n')
            assert exit_code != 0, f"应拦截字符串硬编码, exit={exit_code}, out={output}"

    def test_allow_constants_py(self):
        """豁免: src/constants.py 允许硬编码（真相源）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _init_temp_repo(temp_dir)
            exit_code, output = _try_commit(
                temp_dir, 'src/constants.py', 'STOP_LOSS_PCT = 0.06\n'
            )
            assert exit_code == 0, f"constants.py 应豁免, exit={exit_code}, out={output}"

    def test_allow_no_hardcode(self):
        """通过: 无硬编码"""
        with tempfile.TemporaryDirectory() as temp_dir:
            _init_temp_repo(temp_dir)
            exit_code, output = _try_commit(
                temp_dir, 'src/good.py', 'from src.constants import STOP_LOSS_PCT\nx = -STOP_LOSS_PCT\n'
            )
            assert exit_code == 0, f"无硬编码应通过, exit={exit_code}, out={output}"
