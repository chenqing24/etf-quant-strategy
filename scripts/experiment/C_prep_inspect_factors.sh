#!/bin/bash
# C 准备工作：调研 28 因子结构（按用户"先调研，不要写新代码"）
cd etf_strategy
for f in V4 V5 V6 V7 V8 V9 T5 T6 T7 T8 T9 T10 M5 M6 M7 M8 M9 M10 N4 N5 N6 B2 B3 B4 C1 C2 C3 C4 C5 C6; do
  file=$(ls scripts/experiment/${f}*.py 2>/dev/null | head -1)
  if [ -n "$file" ]; then
    sig=$(grep -nE "signal.*=.*\(|return.*signal|def.*signal|signal.*=.*>|signal.*=.*<|signal\s*=" "$file" 2>/dev/null | head -3)
    [ -n "$sig" ] && echo "=== $f ===" && echo "$sig"
  fi
done
