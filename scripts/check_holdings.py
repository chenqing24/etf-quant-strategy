#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from src.trade.tracker import TradeTracker
t = TradeTracker()
print('持仓数:', len(t.get_holdings()))
for h in t.get_holdings(): print(f'  {h.code} qty={h.quantity}')
