#!/bin/bash
# C 准备工作 2：深入调研 D 类型（grep 未匹配）的 16 个因子
cd etf_strategy
for f in V6 V7 V8 V9 T5 T6 T9 T10 M5 M6 M7 M8 M9 C3 C4 C5 N6; do
  file=$(ls scripts/experiment/${f}*.py 2>/dev/null | head -1)
  if [ -n "$file" ]; then
    # 看 main 函数体
    echo "=== $f ==="
    grep -nE "def main|return signal|signal.*=|signal_func|threshold|iloc\[-1\]" "$file" 2>/dev/null | head -8
    echo ""
  fi
done
