"""
=============================================================================
BCTC & BCTN DISTRIBUTED WORKER CRAWLER (GITHUB ACTIONS ENGINE)
=============================================================================
Leverages the battle-tested BCTCBatchProcessor to download and parse
real BCTC PDFs across HOSE, HNX, and UPCOM in parallel worker shards.
"""

import os
import sys
import json
import time
import argparse
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

# Ensure root dir is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.bctc_batch_processor import BCTCBatchProcessor
from services.stock_service import ALL_SYMBOLS_MAP


def main():
    parser = argparse.ArgumentParser(description="Distributed BCTC & BCTN Worker")
    parser.add_argument("--worker-id", type=int, default=0, help="Worker index (0 to total-1)")
    parser.add_argument("--total-workers", type=int, default=5, help="Total number of workers")
    parser.add_argument("--output-dir", type=str, default="./output", help="Directory to save shard output")
    parser.add_argument("--symbols-file", type=str, default="", help="Optional JSON path to all_symbols")
    parser.add_argument("--max-bctc", type=int, default=4, help="Max BCTC PDFs per symbol")
    parser.add_argument("--crawl-10y-annual", action="store_true", default=False, help="Deep scan and parse 10 years of Audited Annual BCTC PDFs")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # 1. Load symbols
    all_symbols = []
    if args.symbols_file and os.path.exists(args.symbols_file):
        try:
            with open(args.symbols_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            s = item.get("symbol") or item.get("ticker")
                            if s: all_symbols.append(s)
                        elif isinstance(item, str):
                            all_symbols.append(item)
        except Exception:
            logger.debug("main: swallowed Exception", exc_info=True)

    if not all_symbols:
        try:
            from vnstock import Listing
            lst = Listing()
            df = lst.all_symbols()
            if df is not None and not df.empty:
                col = 'symbol' if 'symbol' in df.columns else 'ticker'
                all_symbols = df[col].dropna().unique().tolist()
        except Exception:
            logger.debug("main: swallowed Exception", exc_info=True)

    if not all_symbols and ALL_SYMBOLS_MAP:
        all_symbols = list(ALL_SYMBOLS_MAP.keys())

    if not all_symbols:
        all_symbols = ["FPT", "HPG", "VNM", "MWG", "DGC", "SSI", "VHM", "VIC", "TCB", "MBB"]

    all_symbols = sorted(list(set([str(s).strip().upper() for s in all_symbols if s and len(str(s).strip()) == 3 and str(s).strip().isalnum()])))
    my_symbols = [s for i, s in enumerate(all_symbols) if i % args.total_workers == args.worker_id]

    shard_file = os.path.join(args.output_dir, f"bctc_shard_{args.worker_id}.json")
    corp_shard_file = os.path.join(args.output_dir, f"corporate_shard_{args.worker_id}.json")
    print(f"🚀 Worker {args.worker_id}/{args.total_workers} assigned {len(my_symbols)} symbols.")
    print(f"💾 Target BCTC Shard: {shard_file}")
    print(f"💾 Target Corporate Shard: {corp_shard_file}")

    processor = BCTCBatchProcessor()
    shard_data = {}
    corp_shard_data = {}

    if os.path.exists(shard_file):
        try:
            with open(shard_file, "r", encoding="utf-8") as f:
                shard_data = json.load(f)
            print(f"🔄 Resumed {len(shard_data)} BCTC symbols from checkpoint.")
        except Exception:
            shard_data = {}

    if os.path.exists(corp_shard_file):
        try:
            with open(corp_shard_file, "r", encoding="utf-8") as f:
                corp_shard_data = json.load(f)
            print(f"🔄 Resumed {len(corp_shard_data)} Corporate symbols from checkpoint.")
        except Exception:
            corp_shard_data = {}

    symbols_to_run = [s for s in my_symbols if s not in shard_data or s not in corp_shard_data]
    print(f"⚡ Processing {len(symbols_to_run)} symbols...")

    for idx, sym in enumerate(symbols_to_run, 1):
        # 1. BCTC & Sector Footnotes Processing
        if sym not in shard_data:
            try:
                res = processor.process_single_company(
                    symbol=sym,
                    max_reports=args.max_bctc,
                    fetch_10y_annual=args.crawl_10y_annual
                )
                filings = [
                    p for p in res.get("results", [])
                    if p.get("extracted_data", {}).get("total_pages", 0) >= 8
                    or len(p.get("extracted_data", {}).get("balance_sheet", {}).get("items", {})) > 0
                ]
                shard_data[sym] = {
                    "symbol": sym,
                    "periods": filings,
                    "count": len(filings),
                    "updated_at": int(time.time())
                }
                extracted_count = len(filings)
                total_bs = sum(len(p.get("extracted_data", {}).get("balance_sheet", {}).get("items", {})) for p in filings)
                total_is = sum(len(p.get("extracted_data", {}).get("income_statement", {}).get("items", {})) for p in filings)
                total_cf = sum(len(p.get("extracted_data", {}).get("cash_flow", {}).get("items", {})) for p in filings)
                total_notes = sum(len(p.get("extracted_data", {}).get("debt_schedule_footnotes", [])) for p in filings)
                print(f"  [{idx}/{len(symbols_to_run)}] {sym} BCTC: {extracted_count} filings (BS: {total_bs} items, IS: {total_is} items, CF: {total_cf} items, Notes: {total_notes})")
            except Exception as err:
                print(f"  [{idx}/{len(symbols_to_run)}] {sym} BCTC Error: {err}")
                shard_data[sym] = {"symbol": sym, "periods": [], "count": 0, "error": str(err), "updated_at": int(time.time())}

        # 2. Corporate Disclosures (TT96 Governance & AGM Resolutions)
        if sym not in corp_shard_data:
            try:
                c_res = processor.process_corporate_disclosures(
                    symbol=sym,
                    report_types=["governance", "resolution", "dividend", "annual"],
                    limit_per_type=3
                )
                corp_shard_data[sym] = {
                    "symbol": sym,
                    "records": c_res.get("results", []),
                    "count": len(c_res.get("results", [])),
                    "updated_at": int(time.time())
                }
                corp_count = len(c_res.get("results", []))
                print(f"  [{idx}/{len(symbols_to_run)}] {sym} Corporate Disclosures: Extracted {corp_count} filings (Gov/AGM/Div/Annual)")
            except Exception as err:
                print(f"  [{idx}/{len(symbols_to_run)}] {sym} Corporate Disclosures Error: {err}")
                corp_shard_data[sym] = {"symbol": sym, "records": [], "count": 0, "error": str(err), "updated_at": int(time.time())}

        # Periodic atomic checkpoint
        if idx % 5 == 0 or idx == len(symbols_to_run):
            tmp_shard = shard_file + ".tmp"
            with open(tmp_shard, "w", encoding="utf-8") as f:
                json.dump(shard_data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_shard, shard_file)

            tmp_corp = corp_shard_file + ".tmp"
            with open(tmp_corp, "w", encoding="utf-8") as f:
                json.dump(corp_shard_data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_corp, corp_shard_file)

        time.sleep(0.3)

    print(f"🎉 Worker {args.worker_id} successfully completed all {len(my_symbols)} symbols (BCTC + Corporate Actions)!")


if __name__ == "__main__":
    main()
