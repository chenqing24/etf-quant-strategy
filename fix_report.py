#!/usr/bin/env python
with open('src/analysis/report_generator.py', 'r') as f:
    content = f.read()

content = content.replace("【止损】-5% ({stop_loss_price:.3f}元)", "【止损】-6% ({stop_loss_price:.3f}元)")
content = content.replace("【止盈】+8% ({take_profit_price:.3f}元)", "【止盈】+10% ({take_profit_price:.3f}元)")

with open('src/analysis/report_generator.py', 'w') as f:
    f.write(content)

print("Done")