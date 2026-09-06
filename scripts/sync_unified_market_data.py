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
import logging

logger = logging.getLogger(__name__)

# Ensure proper encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("Could not switch the console to UTF-8", exc_info=True)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.unified_data_service import sync_unified_screener_universe
from services.stock_service import SECTOR_ICB_REGISTRY, resolve_data_file

#: Below this, the master list did not load. A real Vietnamese equity
#: universe is ~1,500 symbols across HOSE, HNX and UPCOM.
MIN_PLAUSIBLE_UNIVERSE = 100


def load_local_symbols() -> dict:
    # Through the shared resolver. As a hardcoded PROJECT_ROOT/data/... this
    # ignored DATA_LOCAL_DIR and GOOGLE_DRIVE_DATA_DIR, so the list was
    # invisible on a machine that keeps its lake on Drive, and absent
    # entirely on a CI runner - where the sync then reported "Loaded 0
    # valid equity symbols" and cheerfully went on to build an empty
    # snapshot.
    symbols_file = resolve_data_file("all_symbols.json")
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

    # A fresh checkout has no master list: data/*.json is gitignored, so a CI
    # runner starts with nothing. Build it from the live listing rather than
    # syncing an empty universe over a good snapshot.
    if len(symbols_map) < MIN_PLAUSIBLE_UNIVERSE:
        print("📥 Master list missing or too small; fetching the listing from vnstock...")
        try:
            from services.stock_service import sync_universe_from_vnstock
            stats = sync_universe_from_vnstock(force=True)
            print(f"   listing sync reports {stats.get('total_symbols', 0)} symbols")
        except Exception as exc:
            print(f"   listing sync failed: {type(exc).__name__}: {exc}")
        symbols_map = load_local_symbols()
        print(f"📦 Reloaded {len(symbols_map)} valid equity symbols.")

    if len(symbols_map) < MIN_PLAUSIBLE_UNIVERSE:
        # Refuse rather than publish. sync_unified_screener_universe() writes
        # screener_snapshot.json unconditionally, so continuing here would
        # replace a good snapshot with an empty one - which is exactly how a
        # 1,645-symbol snapshot nearly got destroyed once already.
        print(
            f"\n❌ Only {len(symbols_map)} symbols available; refusing to sync.\n"
            f"   Nothing was written. Check that all_symbols.json is reachable\n"
            f"   (DATA_LOCAL_DIR / GOOGLE_DRIVE_DATA_DIR) or that the vnstock\n"
            f"   listing endpoint is responding."
        )
        return 1

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

    return 0

if __name__ == "__main__":
    # Propagate the refusal above as a non-zero exit. Returning 1 from main()
    # without this exits 0, and a CI step that refused to sync would look
    # like a step that succeeded.
    sys.exit(main())
