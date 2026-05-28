#!/bin/bash
# 运行ETF量化策略 - 使用鱼身实验Top1配置 (Cfg4: 止损-6%, 止盈10%, 持仓20天)
cd /home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy
python -m src.cli.decision --mode eval --silent 2>&1