#!/bin/bash
# 安装 Git 钩子（pre-commit）
# 用途：将仓库内的 .githooks/pre-commit 配置为本仓库的本地钩子
# 用法：bash scripts/maintenance/install_git_hooks.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOKS_DIR="${REPO_ROOT}/.githooks"

if [ ! -f "${HOOKS_DIR}/pre-commit" ]; then
    echo "❌ 找不到 ${HOOKS_DIR}/pre-commit"
    exit 1
fi

# 配置 git 使用仓库内的 hooks 目录
git config core.hooksPath "${HOOKS_DIR}"

echo "✅ Git 钩子已配置：core.hooksPath = ${HOOKS_DIR}"
echo "下次 commit 时会自动运行 pre-commit 检查"
