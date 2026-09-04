"""
=============================================================================
UNIFIED MULTI-SOURCE MARKET DATA LAKE SYNC SCRIPT
=============================================================================
Runs unified multi-tier data ingestion from TradingView, vnstock, and yfinance.
Updates data/screener_snapshot.json with 100% normalized real fundamentals
using the Quant Imputation Engine (Accounting Triangles & 4-Tier Provenance).
"""

import os
import sys
import json
import time

# Ensure proper encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.unified_data_service import sync_unified_screener_universe
from services.stock_service import SECTOR_ICB_REGISTRY

def load_local_symbols() -> dict:
    symbols_file = os.path.join(PROJECT_ROOT, "data", "all_symbols.json")
    master = {}

    # Build reverse lookup from representative stocks
    rep_map = {}
    for code, s_meta in SECTOR_ICB_REGISTRY.items():
        for sym in s_meta.get("representative_stocks", []):
            rep_map[sym.upper()] = (code, s_meta.get("name"))

    if os.path.exists(symbols_file):
        with open(symbols_file, "r", encoding="utf-8") as f:
            arr = json.load(f)
            for r in arr:
                sym = r.get("symbol", "").upper().strip()
                stype = (r.get("type") or "STOCK").upper()
                ex = (r.get("exchange") or "HOSE").upper()
                if stype in ["STOCK", "CO_PHIEU"] and ex in ["HOSE", "HNX", "UPCOM"]:
                    sec_code, sec_name = rep_map.get(sym, ("VNIND", r.get("industry") or "Công Nghiệp"))
                    master[sym] = {
                        "symbol": sym,
                        "name": r.get("organ_name", f"Công ty Cổ phần {sym}"),
                        "exchange": ex,
                        "sector_code": sec_code,
                        "sector_name": sec_name
                    }
    return master

def main():
    print("=====================================================================")
    print(" 🌐 QUANT IMPUTATION DATA LAKE SYNC (TradingView + vnstock + yfinance)")
    print("=====================================================================")
    symbols_map = load_local_symbols()
    print(f"📦 Loaded {len(symbols_map)} valid equity symbols from local master list.")
    
    payload = sync_unified_screener_universe(symbols_map)
    
    # Verification Sample
    sample_syms = ["FPT", "HPG", "VNM", "VCB", "MWG", "DGC", "SSI", "GAS", "PNJ", "MSN"]
    print("\n📊 Verification Sample (Normalized Real Financials with Imputation Quality):")
    stocks = payload.get("stocks", {})
    for sym in sample_syms:
        s = stocks.get(sym)
        if s:
            meta = s.get("_metadata", {})
            sources = ",".join(meta.get("sources_used", ["unknown"]))
            q_score = meta.get("data_quality_score", 0.0)
            tier = meta.get("provenance_tier", "")
            print(f"  • {sym:4s} | Price: {s['price']:>8,.0f} | P/E: {s['pe']:>5.1f} | P/B: {s['pb']:>4.2f} | ROE: {s['roe']:>5.1f}% | Net D/E: {s['net_de_ratio']:>4.2f} | Quality: {q_score:>5.1f}% [{tier}] | Sources: [{sources}]")

if __name__ == "__main__":
    main()
