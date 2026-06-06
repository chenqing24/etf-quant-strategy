#!/bin/bash
cd /home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy
echo "=== 本地 main 最近 8 commit ==="
git log --pretty=format:"%h %s" -8
echo
echo
echo "=== 远程 main 最近 8 commit ==="
git log --pretty=format:"%h %s" github/main -8
echo
echo
echo "=== 推送后必查（规则 21）==="
git fetch github 2>&1 | head -3
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse github/main)
echo "本地 main: $LOCAL"
echo "远程 main: $REMOTE"
if [ "$LOCAL" = "$REMOTE" ]; then
  echo "✅ 一致"
else
  echo "❌ 不一致"
fi
echo
echo "=== 远程 tags ==="
git ls-remote --tags github 2>&1 | tail -8
