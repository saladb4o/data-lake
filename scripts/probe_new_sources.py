#!/usr/bin/env python3
"""Ask a vendor that names its line items which of our numbers it carries.

VNDIRECT, the only source the fundamentals lake reads, names nothing: a
balance sheet arrives as a numeric VAS code scheme, and this audit has
been decoding it by magnitude and by arithmetic identity. The first
reading of it was wrong in all four parts. Any vendor that spells out
"Depreciation and Amortisation" is therefore an independent check on the
code map itself, which is what this probe is for.

Two such vendors are free, and this probe asks both.
``vnstock.Finance`` accepts exactly VCI (Vietcap) and KBS, and each
serves quarterly statements with named columns.

FiinGroup through SSI would have been a third opinion, and the code for
it lived here for a while, but it is subscription-only: a probe that
cannot get an answer is not a probe. It has been removed rather than
left behind a flag, because a route nobody can take is not a route.

No mapping is presumed in either direction. For each figure in our lake
the probe asks which named column of the vendor's statement carries that
same number in that same quarter, so the map is discovered from the data
rather than guessed - and a field that matches nothing is exactly the
finding worth having.

Everything here is read-only, bounded, and fails soft: an unreachable
host is a result, not a crash.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOLERANCE = 0.01  # 1%: the same figure from two vendors, not a similar one


def _lake_records(path: str, symbol: str) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        lake = json.load(handle)
    entry = (lake.get("symbols", {}) or {}).get(symbol.upper()) or {}
    return entry.get("quarters") or {}


# --- vendors that name their line items, and cost nothing ---------------
#: ``vnstock.Finance`` accepts exactly these two. Vietcap and KBS both
#: return statements whose LINE ITEMS ARE COLUMN NAMES IN WORDS, which
#: is the independent check on the numeric code map that VNDIRECT alone
#: can never provide - and neither costs anything.
VNSTOCK_SOURCES: Tuple[str, ...] = ("VCI", "KBS")

#: Columns that identify the period rather than report a figure.
PERIOD_COLUMNS = ("ticker", "yearreport", "lengthreport", "year", "quarter",
                  "period", "cp", "ky", "nam")


def _match_values(vendor_rows: List[Tuple[str, float]],
                  record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """For each of our numbers, which named vendor line carries it?

    No mapping is assumed in either direction: a field that matches
    nothing is the finding, not an error.
    """
    out = []
    for field, ours in sorted(record.items()):
        if not isinstance(ours, (int, float)) or isinstance(ours, bool):
            continue
        if ours == 0:
            continue
        matches = [name for name, value in vendor_rows
                   if abs(value - float(ours)) <= TOLERANCE * max(
                       abs(float(ours)), abs(value), 1.0)]
        out.append({"field": field, "ours": float(ours),
                    "vendor_rows_with_this_value": matches[:3],
                    "matched": bool(matches)})
    return out


def _quarter_row(frame, quarter_code: str):
    """The row of a vnstock statement for ``2024-Q1``, or None.

    vnstock has shipped several column spellings for the period; rather
    than pick one, look for any pair of columns that carries the year and
    the quarter as numbers.
    """
    try:
        year_text, quarter_text = quarter_code.split("-Q")
        year, quarter = int(year_text), int(quarter_text)
    except (ValueError, AttributeError):
        return None
    lowered = {str(c).strip().lower(): c for c in frame.columns}
    year_column = lowered.get("yearreport") or lowered.get("year") or lowered.get("nam")
    quarter_column = (lowered.get("lengthreport") or lowered.get("quarter")
                      or lowered.get("ky") or lowered.get("cp"))
    if year_column is None or quarter_column is None:
        return None
    for _, row in frame.iterrows():
        try:
            if int(row[year_column]) == year and int(row[quarter_column]) == quarter:
                return row
        except (TypeError, ValueError):
            continue
    return None


def name_our_fields_by_column(frame, records: Dict[str, Dict[str, Any]],
                              quarter_code: str
                              ) -> Tuple[List[Dict[str, Any]], int]:
    """Which named column of this quarter's row carries each of ours."""
    row = _quarter_row(frame, quarter_code)
    if row is None:
        return [], 0
    vendor_rows: List[Tuple[str, float]] = []
    for column in frame.columns:
        if str(column).strip().lower() in PERIOD_COLUMNS:
            continue
        try:
            value = float(row[column])
        except (TypeError, ValueError):
            continue
        vendor_rows.append((str(column).strip(), value))
    return _match_values(vendor_rows, records.get(quarter_code) or {}), len(vendor_rows)


def vnstock_statements(symbol: str, source: str) -> Dict[str, Any]:
    """{statement name: DataFrame} for what this vendor will serve.

    A statement the vendor refuses is recorded as the exception it
    raised, because "KBS has no cash flow" is a result worth keeping.
    """
    from vnstock import Finance
    finance = Finance(source=source, symbol=symbol.upper(), period="quarter")
    out: Dict[str, Any] = {}
    for name in ("cash_flow", "balance_sheet", "income_statement"):
        try:
            out[name] = getattr(finance, name)()
        except Exception as exc:
            out[name] = f"{type(exc).__name__}: {exc}"
    return out

def report_free_vendors(args, findings: Dict[str, Any]) -> None:
    """Ask Vietcap and KBS which of their named lines carry our numbers.

    This is the check the code map has never had, and it costs nothing.
    A vendor that cannot be reached, or a statement it will not serve, is
    recorded as exactly that: the probe reports what happened rather than
    only what worked.
    """
    print("## Vendors that name their line items")
    print()
    findings["named_vendors"] = {}
    records_cache: Dict[str, Dict[str, Any]] = {}

    for symbol in args.symbols:
        symbol = symbol.upper()
        if args.lake and os.path.exists(args.lake):
            records_cache[symbol] = _lake_records(args.lake, symbol)
        records = records_cache.get(symbol) or {}
        quarter = args.quarter or (sorted(records)[-1] if records else None)

        for source in VNSTOCK_SOURCES:
            key = f"{symbol}/{source}"
            print(f"### {key}")
            try:
                statements = vnstock_statements(symbol, source)
            except Exception as exc:
                print(f"- unreachable: {type(exc).__name__}: {exc}")
                findings["named_vendors"][key] = {
                    "error": f"{type(exc).__name__}: {exc}"}
                continue

            entry: Dict[str, Any] = {}
            for name, frame in statements.items():
                if isinstance(frame, str):
                    print(f"- `{name}`: {frame}")
                    entry[name] = {"error": frame}
                    continue
                columns = [str(c) for c in frame.columns]
                print(f"- `{name}` names {len(columns)} columns, "
                      f"for example: "
                      + ", ".join(f"`{c}`" for c in columns[3:9]))
                item: Dict[str, Any] = {"columns": columns[:80]}
                if quarter:
                    rows, count = name_our_fields_by_column(
                        frame, records, quarter)
                    item["quarter"] = quarter
                    item["fields"] = rows
                    if rows:
                        print()
                        print(f"| our field ({quarter}) | our value | "
                              f"vendor columns carrying it |")
                        print("|---|---:|---|")
                        for row in rows:
                            found = (", ".join(
                                f"`{n}`" for n in
                                row["vendor_rows_with_this_value"])
                                or "**no column carries this number**")
                            print(f"| {row['field']} | {row['ours']:,.0f} | "
                                  f"{found} |")
                        print()
                    elif count == 0:
                        print(f"- no row for {quarter}")
                entry[name] = item
            findings["named_vendors"][key] = entry
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["FPT", "HPG", "VCB"])
    parser.add_argument("--quarter", default=None,
                        help="Quarter to compare, e.g. 2025-Q2.")
    parser.add_argument("--lake", default=None, help="historical_fundamentals.json")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    findings: Dict[str, Any] = {}
    report_free_vendors(args, findings)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(findings, handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
