import sys
import os
import json

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from services.stock_service import get_company_financial_statements, disk_lake

print("Checking financial_statements disk lake files...")
data_dir = disk_lake.get_data_dir()
print(f"Data dir: {data_dir}")

# Let's test get_company_financial_statements for HPG
print("\nFetching Balance Sheet for HPG...")
bs = get_company_financial_statements("HPG", statement_type="balance", period="year", periods_count=5)
print(f"HPG Balance Sheet keys: {list(bs.keys())}")
print(f"HPG periods: {bs.get('periods')}")
print(f"Total rows: {len(bs.get('rows', []))}")
for r in bs.get('rows', [])[:10]:
    print(f"Item: {r.get('item_name')} | Code: {r.get('item_code')} | Values: {r.get('values')}")

print("\nFetching Income Statement for HPG...")
inc = get_company_financial_statements("HPG", statement_type="income", period="year", periods_count=5)
print(f"HPG periods: {inc.get('periods')}")
for r in inc.get('rows', [])[:8]:
    print(f"Item: {r.get('item_name')} | Code: {r.get('item_code')} | Values: {r.get('values')}")

print("\nFetching Cash Flow Statement for HPG...")
cf = get_company_financial_statements("HPG", statement_type="cashflow", period="year", periods_count=5)
print(f"HPG periods: {cf.get('periods')}")
for r in cf.get('rows', [])[:8]:
    print(f"Item: {r.get('item_name')} | Code: {r.get('item_code')} | Values: {r.get('values')}")
