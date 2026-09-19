#!/usr/bin/env python3
"""Pour a real filing out of the BCTC lake into the VAS template.

    fill_from_lake.py SYMBOL TEMPLATE.xlsx OUT.xlsx [--col G] [--doc ID]

This is the path a real company takes into the model. It does not invent
anything: a TT200 code the filing does not carry is left empty, and the
run prints which ones those were, because an empty line in a statement
is a line nobody extracted, not a line worth zero. The template's own
identity checks then say whether what did arrive adds up.

The lake stores dong. The template works in millions of dong, and that
conversion happens in exactly one place here - VND_PER_MILLION - because
a units error in a valuation is invisible: every number stays plausible
and only the answer is wrong by a factor of a million.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vas_layout as V                          # noqa: E402
from xlsx_patch import WorkbookPatch            # noqa: E402

LAKE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "pdf_lake", "extracted_bctc_lake.json")

VND_PER_MILLION = 1_000_000.0

SECTIONS = (
    ("balance_sheet", V.BS_ROW),
    ("income_statement", V.IS_ROW),
    ("cash_flow", V.CF_ROW),
)


def in_millions(vnd: float, scale: float) -> float:
    """Dong as the filing states them -> millions of dong."""
    return vnd * scale / VND_PER_MILLION


def load_lake(path: str = LAKE) -> Dict:
    with open(path, encoding="utf8") as fh:
        return json.load(fh)


def filings_for(lake: Dict, symbol: str) -> List[Tuple[str, Dict]]:
    """Every filing for a symbol that carries at least one statement line."""
    out = []
    for doc_id, rec in lake.items():
        if (rec.get("symbol") or "").upper() != symbol.upper():
            continue
        extracted = rec.get("extracted_data") or {}
        if any((extracted.get(name) or {}).get("items")
               for name, _ in SECTIONS):
            out.append((doc_id, rec))
    out.sort(key=lambda kv: kv[1].get("filing_timestamp") or 0, reverse=True)
    return out


def codes_from(rec: Dict) -> Dict[str, Dict[str, float]]:
    """{section: {code: value in millions}} for the codes the template has."""
    extracted = rec.get("extracted_data") or {}
    found: Dict[str, Dict[str, float]] = {}
    for name, rows in SECTIONS:
        section = extracted.get(name) or {}
        items = section.get("items") or {}
        scale = section.get("scale_multiplier")
        scale = 1.0 if scale is None else float(scale)
        here: Dict[str, float] = {}
        for raw_code, entry in items.items():
            code = str(raw_code).lstrip("0") or "0"
            # the layout writes single-digit statement codes with a
            # leading zero ("01"), the lake does not
            for candidate in (code, code.zfill(2)):
                if candidate in rows:
                    value = entry.get("current_val")
                    if value is None:
                        continue
                    here[candidate] = in_millions(float(value), scale)
                    break
        found[name] = here
    return found


def write(w: WorkbookPatch, found: Dict[str, Dict[str, float]],
          col: str) -> Tuple[int, Dict[str, List[str]]]:
    sheet = V.SHEET_NAMES["Raw Data"]
    placed = 0
    missing: Dict[str, List[str]] = {}
    for name, rows in SECTIONS:
        here = found.get(name, {})
        for code, row in rows.items():
            if code in here:
                w.set_value(sheet, f"{col}{row}", round(here[code], 6))
                placed += 1
        missing[name] = sorted(set(rows) - set(here), key=lambda c: int(c))
    return placed, missing


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbol")
    ap.add_argument("template")
    ap.add_argument("out")
    ap.add_argument("--col", default=V.LAST_HIST_COL,
                    help="historical column to fill (default the latest)")
    ap.add_argument("--doc", default=None, help="a specific doc_id")
    args = ap.parse_args(argv)

    lake = load_lake()
    candidates = filings_for(lake, args.symbol)
    if args.doc:
        candidates = [(d, r) for d, r in candidates if d == args.doc]
    if not candidates:
        print(f"{args.symbol}: không có bản nào trong kho có dòng báo cáo")
        return 1

    doc_id, rec = candidates[0]
    found = codes_from(rec)
    total = sum(len(v) for v in found.values())
    print(f"{args.symbol}: dùng {doc_id}")
    print(f"  kỳ {rec.get('period_label')} | đã kiểm toán: "
          f"{rec.get('is_audited')} | trích xuất: "
          f"{(rec.get('extracted_data') or {}).get('document_type')}")
    if total == 0:
        print("  không có mã nào khớp với các dòng của mẫu")
        return 1

    w = WorkbookPatch(args.template)
    placed, missing = write(w, found, args.col)
    w.save(args.out)

    for name, rows in SECTIONS:
        have = len(found.get(name, {}))
        print(f"  {name}: {have}/{len(rows)} mã")
        if missing[name]:
            print(f"      thiếu: {', '.join(missing[name])}")
    print(f"  đã ghi {placed} ô vào cột {args.col} -> {args.out}")
    print("  Các mã thiếu để trống, không điền 0: dòng kiểm của mẫu sẽ "
          "chỉ ra chỗ nào chưa khép.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
