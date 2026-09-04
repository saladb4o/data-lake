import sys
import os
import json

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from services.stock_service import get_company_financial_statements, VN30_SYMBOLS

def clean_val(v):
    if v is None or v == '--':
        return 0.0
    try:
        return float(str(v).replace(',', '').replace('%', '').strip())
    except Exception:
        return 0.0

def analyze_stock(symbol):
    try:
        bs = get_company_financial_statements(symbol, statement_type="balance", period="year", periods_count=4)
        inc = get_company_financial_statements(symbol, statement_type="income", period="year", periods_count=4)
        
        periods = bs.get('periods', [])
        cform = bs.get('company_form', 'NON_FINANCE')
        
        def extract(stmt, codes, names):
            for r in stmt.get('rows', []):
                c = int(r.get('item_code', 0)) if r.get('item_code') else 0
                n = r.get('item_name', '').lower()
                if c in codes or any(k in n for k in names):
                    return [clean_val(v) for v in r.get('values', [])]
            return [0.0] * len(periods)
        
        rev = extract(inc, [21001, 21000, 421100, 21400], ["doanh thu thuần", "thu nhập lãi"])
        cogs = extract(inc, [22100, 422100, 400540], ["giá vốn", "chi phí lãi"])
        ar = extract(bs, [11300, 11310, 412510], ["phải thu ngắn hạn", "phải thu khách hàng"])
        inv = extract(bs, [11400, 11410], ["hàng tồn kho"])
        ap = extract(bs, [13120, 13110, 413700], ["phải trả người bán", "phải trả ngắn hạn"])
        
        if periods and len(periods) >= 1:
            r0 = rev[0] if rev else 0.0
            c0 = cogs[0] if cogs else 0.0
            ar0 = ar[0] if ar else 0.0
            inv0 = inv[0] if inv else 0.0
            ap0 = ap[0] if ap else 0.0
            
            dso = (ar0 / r0 * 365.0) if r0 > 0 else 0.0
            dio = (inv0 / c0 * 365.0) if c0 > 0 else 0.0
            dpo = (ap0 / c0 * 365.0) if c0 > 0 else 0.0
            ccc = dso + dio - dpo
            
            return {
                "symbol": symbol,
                "form": cform,
                "period": periods[0],
                "rev": r0,
                "cogs": c0,
                "ar": ar0,
                "inv": inv0,
                "ap": ap0,
                "dso": round(dso, 1),
                "dio": round(dio, 1),
                "dpo": round(dpo, 1),
                "ccc": round(ccc, 1),
                "status": "OK"
            }
    except Exception as e:
        return {"symbol": symbol, "status": f"ERROR: {e}"}

print(f"{'Symbol':<6} | {'Form':<12} | {'Year':<4} | {'Rev (B)':<10} | {'COGS (B)':<10} | {'DSO':<6} | {'DIO':<6} | {'DPO':<6} | {'CCC':<6}")
print("-" * 80)

for s in VN30_SYMBOLS[:12]:
    res = analyze_stock(s)
    if res.get("status") == "OK":
        print(f"{res['symbol']:<6} | {res['form']:<12} | {res['period']:<4} | {res['rev']:>10,.0f} | {res['cogs']:>10,.0f} | {res['dso']:>6.1f} | {res['dio']:>6.1f} | {res['dpo']:>6.1f} | {res['ccc']:>6.1f}")
    else:
        print(f"{s:<6} | {res.get('status')}")
