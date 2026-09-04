import sys
import os
import json

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 1. Inspect screener_snapshot.json sectors
with open('data/screener_snapshot.json', 'r', encoding='utf-8') as f:
    snap = json.load(f)

print("=== SECTOR MEDIANS IN SCREENER SNAPSHOT ===")
sectors = snap.get('sectors', {})
for code, sec in sectors.items():
    print(f"Sector {code:6s}: GM={sec.get('median_gross_margin')}%, OM={sec.get('median_op_margin')}%, ROE={sec.get('median_roe')}%, PE={sec.get('median_pe')}, Count={sec.get('count')}")

# 2. Check VN30 symbols present in screener_snapshot
from services.stock_service import VN30_SYMBOLS, SECTOR_ICB_REGISTRY

print(f"\nTotal VN30 symbols: {len(VN30_SYMBOLS)}")
stocks = snap.get('stocks', {})
present = [s for s in VN30_SYMBOLS if s in stocks]
missing = [s for s in VN30_SYMBOLS if s not in stocks]
print(f"Present in screener_snapshot: {len(present)}/30: {present}")
if missing:
    print(f"Missing from screener_snapshot: {missing}")

# 3. Check sample financials from financial_models.json & stock_service
print("\n=== SAMPLE WORKING CAPITAL DATA FOR VN30 STOCKS ===")
for sym in ["HPG", "VNM", "MWG", "FPT", "GAS", "VHM", "VIC", "MSN", "POW", "SAB"]:
    st = stocks.get(sym, {})
    rev = st.get('revenue', 0.0)
    gm = st.get('gross_margin', 20.0)
    cogs = rev * (1.0 - gm / 100.0) if rev > 0 else 0.0
    cr = st.get('current_ratio', 1.5)
    qr = st.get('quick_ratio', 1.0)
    sec = st.get('sector_code', 'DEFAULT')
    print(f"Symbol {sym:4s} | Sector: {sec:6s} | Rev: {rev:9,.1f}B | GM: {gm:4.1f}% | COGS: {cogs:9,.1f}B | CR: {cr:4.2f} | QR: {qr:4.2f}")

print("\nExploration complete.")
