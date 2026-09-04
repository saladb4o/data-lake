import json
import os

data_path = os.path.join('data', 'financial_models.json')
with open(data_path, 'r', encoding='utf-8') as f:
    items = json.load(f)

lines = []
for mtype in ['BALANCESHEET', 'INCOME', 'CASHFLOW']:
    lines.append(f'# Model Type: {mtype}\n')
    forms = set(x.get('companyForm') for x in items if x.get('modelTypeName') == mtype)
    for form in sorted(list(forms), key=lambda x: str(x)):
        lines.append(f'## Company Form: {form}\n')
        sub = [x for x in items if x.get('modelTypeName') == mtype and x.get('companyForm') == form]
        sub.sort(key=lambda x: (x.get('displayOrder', 0), x.get('itemCode', 0)))
        lines.append('| itemCode | Level | Order | itemVnName | itemEnName | formType |')
        lines.append('|---|---|---|---|---|---|')
        for it in sub:
            code = int(it.get('itemCode', 0))
            lvl = it.get('displayLevel', 0)
            ord_ = it.get('displayOrder', 0)
            vn = str(it.get('itemVnName', '')).replace('|', '/')
            en = str(it.get('itemEnName', '')).replace('|', '/')
            ft = it.get('formType', '')
            lines.append(f'| {code} | {lvl} | {ord_} | {vn} | {en} | {ft} |')
        lines.append('\n')

out_path = os.path.join('.agents', 'teamwork_preview_explorer_m1_2', 'financial_models_mapped.md')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('SUCCESS: financial_models_mapped.md written successfully!')
