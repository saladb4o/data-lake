import sys
import os
import json

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from services.stock_service import get_company_financial_statements

def clean_val(v):
    if v is None or v == '--':
        return 0.0
    try:
        return float(str(v).replace(',', '').replace('%', '').strip())
    except Exception:
        return 0.0

bs = get_company_financial_statements("HPG", statement_type="balance", period="year", periods_count=5)
inc = get_company_financial_statements("HPG", statement_type="income", period="year", periods_count=5)
cf = get_company_financial_statements("HPG", statement_type="cashflow", period="year", periods_count=5)

periods = bs.get('periods', [])
print(f"Periods: {periods}")

def extract_row(statement, codes, names):
    for r in statement.get('rows', []):
        c = int(r.get('item_code', 0)) if r.get('item_code') else 0
        n = r.get('item_name', '').lower()
        if c in codes or any(k in n for k in names):
            return [clean_val(v) for v in r.get('values', [])]
    return [0.0] * len(periods)

# Balance sheet rows
ca = extract_row(bs, [11000], ["tài sản ngắn hạn"])
cash = extract_row(bs, [11100], ["tiền và các khoản tương đương tiền"])
st_inv = extract_row(bs, [11200, 412320], ["đầu tư tài chính ngắn hạn"])
ar = extract_row(bs, [11300, 11310], ["các khoản phải thu ngắn hạn", "phải thu khách hàng"])
inv = extract_row(bs, [11400, 11410], ["hàng tồn kho"])
other_ca = extract_row(bs, [11500], ["tài sản ngắn hạn khác"])

cl = extract_row(bs, [13100], ["nợ ngắn hạn"])
st_debt = extract_row(bs, [13110], ["vay và nợ ngắn hạn", "vay và nợ thuê tài chính ngắn hạn"])
ap = extract_row(bs, [13120], ["phải trả người bán", "phải trả người bán ngắn hạn"])
adv_cust = extract_row(bs, [13130], ["người mua trả tiền trước"])
other_cl = extract_row(bs, [13190, 13160], ["các khoản phải trả ngắn hạn khác", "chi phí phải trả"])

# Income statement rows
rev = extract_row(inc, [21001], ["doanh thu thuần"])
cogs = extract_row(inc, [22100], ["giá vốn hàng bán"])
ebit = extract_row(inc, [23110], ["lợi nhuận thuần từ hoạt động kinh doanh"])
npat = extract_row(inc, [23003, 23000], ["lợi nhuận sau thuế"])

print("\n=== EXTRACTED BALANCE SHEET & INCOME STATEMENT (HPG, Tỷ VNĐ) ===")
print(f"{'Metric':<25} | " + " | ".join([f"{p:>10}" for p in periods]))
print("-" * 80)
print(f"{'Revenue (21001)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in rev]))
print(f"{'COGS (22100)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in cogs]))
print(f"{'Current Assets (11000)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in ca]))
print(f"{'Cash & Equiv (11100)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in cash]))
print(f"{'Accounts Rec (11300)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in ar]))
print(f"{'Inventory (11400)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in inv]))
print(f"{'Current Liab (13100)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in cl]))
print(f"{'Short-term Debt (13110)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in st_debt]))
print(f"{'Accounts Pay (13120)':<25} | " + " | ".join([f"{v:>10,.0f}" for v in ap]))

print("\n=== WORKING CAPITAL DAYS (HPG) ===")
# Note: periods are descending: 2025, 2024, 2023, 2022
for i, p in enumerate(periods):
    r_val = rev[i]
    c_val = cogs[i]
    ar_val = ar[i]
    inv_val = inv[i]
    ap_val = ap[i]
    
    dso = (ar_val / r_val * 365.0) if r_val > 0 else 0.0
    dio = (inv_val / c_val * 365.0) if c_val > 0 else 0.0
    dpo = (ap_val / c_val * 365.0) if c_val > 0 else 0.0
    ccc = dso + dio - dpo
    nwc_core = ar_val + inv_val - ap_val
    nwc_total = (ar_val + inv_val + other_ca[i]) - (ap_val + other_cl[i])
    print(f"Year {p}: DSO={dso:5.1f} d | DIO={dio:5.1f} d | DPO={dpo:5.1f} d | CCC={ccc:5.1f} d | Core NWC={nwc_core:9,.0f} B | Total NWC={nwc_total:9,.0f} B")

print("\n=== DIRECT CASH FLOW COMPARISON ===")
# Comparing 2024 to 2025 (indices 1 to 0)
# 2025 values: index 0; 2024 values: index 1
d_ar = ar[0] - ar[1]
d_inv = inv[0] - inv[1]
d_ap = ap[0] - ap[1]
d_nwc = (ar[0] + inv[0] - ap[0]) - (ar[1] + inv[1] - ap[1])

cash_rec_model = rev[0] - d_ar
cash_paid_supp_model = cogs[0] + d_inv - d_ap

print(f"2024->2025 Changes: Delta AR={d_ar:,.0f} B, Delta Inv={d_inv:,.0f} B, Delta AP={d_ap:,.0f} B, Delta NWC={d_nwc:,.0f} B")
print(f"Model Projected Cash Receipts (Rev - Delta AR): {cash_rec_model:,.0f} B (Revenue: {rev[0]:,.0f} B)")
print(f"Model Projected Cash Paid to Suppliers (COGS + Delta Inv - Delta AP): {cash_paid_supp_model:,.0f} B (COGS: {cogs[0]:,.0f} B)")

# Let's check CFS reported direct items if available
cf_rec = extract_row(cf, [30100], ["tiền thu từ bán hàng"])
cf_supp = extract_row(cf, [30200], ["tiền chi trả cho người cung cấp"])
print(f"Reported CFS Row 30100 (Receipts): {cf_rec[0]:,.0f} B")
print(f"Reported CFS Row 30200 (Suppliers): {cf_supp[0]:,.0f} B")
