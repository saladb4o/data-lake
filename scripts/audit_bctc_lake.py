#!/usr/bin/env python3
"""Report what is actually inside the BCTC PDF lake.

``data/pdf_lake/extracted_bctc_lake.json`` is 104 MB, which reads as a rich
source of financial statements. It is not: of 1,769 records, 22 carry any
extracted data at all and 1,748 have ``year: None``. Nothing surfaced that,
so the file kept being treated as the fundamentals corpus.

This prints the breakdown - how many records parsed, which document types
failed, which symbols and periods are actually covered - so the gap is a
number someone can act on rather than an assumption.

Usage
-----
    python scripts/audit_bctc_lake.py
    python scripts/audit_bctc_lake.py --json-out data/exports/bctc_audit.json
    python scripts/audit_bctc_lake.py --fail-under 50   # for CI
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("audit_bctc_lake")

#: A record counts as usable only if it carries at least one of these
#: statement blocks with content.
STATEMENT_BLOCKS = ("balance_sheet", "income_statement", "cash_flow")


def _has_statements(extracted: Any) -> bool:
    if not isinstance(extracted, dict):
        return False
    for block in STATEMENT_BLOCKS:
        payload = extracted.get(block)
        if isinstance(payload, dict) and payload.get("items"):
            return True
    return False


def audit(lake: Dict[str, Any]) -> Dict[str, Any]:
    total = len(lake)
    usable = 0
    non_empty = 0
    doc_types: collections.Counter = collections.Counter()
    years: collections.Counter = collections.Counter()
    missing_year = 0
    missing_filing_date = 0
    symbols_usable = set()

    for record in lake.values():
        if not isinstance(record, dict):
            continue
        extracted = record.get("extracted_data")
        if isinstance(extracted, dict) and extracted:
            non_empty += 1
            doc_types[str(extracted.get("document_type") or "UNKNOWN")] += 1
        if _has_statements(extracted):
            usable += 1
            if record.get("symbol"):
                symbols_usable.add(str(record["symbol"]).upper())
        year = record.get("year")
        if year in (None, "", "None"):
            missing_year += 1
        else:
            years[str(year)] += 1
        if not record.get("filing_date"):
            missing_filing_date += 1

    return {
        "records": total,
        "records_with_any_extracted_data": non_empty,
        "records_with_statements": usable,
        "usable_pct": round(100.0 * usable / total, 2) if total else 0.0,
        "distinct_symbols_with_statements": len(symbols_usable),
        "records_missing_year": missing_year,
        "records_missing_filing_date": missing_filing_date,
        "document_types": dict(doc_types.most_common()),
        "years": dict(sorted(years.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lake", default=None, help="Path to extracted_bctc_lake.json")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--fail-under", type=float, default=None,
                        help="Exit 1 if the usable percentage falls below this.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    path = args.lake
    if path is None:
        from services.bctc_batch_processor import extracted_lake_file
        path = extracted_lake_file()
    if not os.path.exists(path):
        logger.error("lake not found at %s", path)
        return 1

    with open(path, "r", encoding="utf-8") as handle:
        lake = json.load(handle)
    if not isinstance(lake, dict):
        logger.error("unexpected lake shape: %s", type(lake).__name__)
        return 1

    report = audit(lake)
    size_mb = os.path.getsize(path) / (1024 * 1024)

    print(f"BCTC lake: {path}")
    print(f"  size on disk              {size_mb:,.1f} MB")
    print(f"  records                   {report['records']:,}")
    print(f"  with any extracted data   {report['records_with_any_extracted_data']:,}")
    print(f"  with statement items      {report['records_with_statements']:,} "
          f"({report['usable_pct']}%)")
    print(f"  distinct symbols usable   {report['distinct_symbols_with_statements']:,}")
    print(f"  missing year              {report['records_missing_year']:,}")
    print(f"  missing filing_date       {report['records_missing_filing_date']:,}")
    if report["document_types"]:
        print("  document types:")
        for name, count in report["document_types"].items():
            print(f"    {name:<24} {count:,}")
    if report["years"]:
        print("  years covered:")
        for year, count in report["years"].items():
            print(f"    {year:<24} {count:,}")

    if report["usable_pct"] < 5.0:
        print("\n  The lake is effectively empty. Most records are unparsed PDFs "
              "(document_type SCANNED_IMAGE needs OCR). It is not a usable "
              "fundamentals source in this state - build the point-in-time "
              "lake from an API feed instead: "
              "scripts/build_historical_fundamentals.py")

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        logger.info("wrote %s", args.json_out)

    if args.fail_under is not None and report["usable_pct"] < args.fail_under:
        logger.error("usable %.2f%% is below the --fail-under threshold of %.2f%%",
                     report["usable_pct"], args.fail_under)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
