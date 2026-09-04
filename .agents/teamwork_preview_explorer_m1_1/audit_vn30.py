import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

VN30_SYMBOLS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
]

snap_path = "data/screener_snapshot.json"
with open(snap_path, "r", encoding="utf-8") as f:
    snap = json.load(f)

stocks = snap.get("stocks", {})
print(f"Total stocks in snapshot: {len(stocks)}")

tested = 0
found = 0
results = {}

for sym in VN30_SYMBOLS:
    tested += 1
    st = stocks.get(sym)
    if st:
        found += 1
        sec = st.get("sector_code", "DEFAULT")
        mcap = st.get("market_cap", 0.0)
        pe = st.get("pe", 0.0)
        pb = st.get("pb", 0.0)
        gross_margin = st.get("gross_margin", 0.0)
        rev_growth = st.get("rev_1y_growth", 0.0)
        results[sym] = {
            "name": st.get("name", ""),
            "sector": sec,
            "market_cap": mcap,
            "pe": pe,
            "pb": pb,
            "gross_margin": gross_margin,
            "rev_growth": rev_growth,
        }
    else:
        results[sym] = {"status": "missing_in_screener"}

out_file = ".agents/teamwork_preview_explorer_m1_1/vn30_wc_audit.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Tested: {tested}, Found: {found}, Output saved to {out_file}")
