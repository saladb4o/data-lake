import re
import os

with open('services/stock_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

output = []
for i, line in enumerate(lines):
    if re.match(r'^(def |class )\w+', line):
        name = line.strip()
        if any(w in name.lower() for w in ['finan', 'ratio', 'balance', 'income', 'cash', 'report', 'statement', 'lake', 'fundam', 'screener', 'model']):
            output.append(f'Line {i+1}: {name}')

with open('.agents/teamwork_preview_explorer_m1_2/stock_service_funcs.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print(f'Wrote {len(output)} matching functions to stock_service_funcs.txt')
