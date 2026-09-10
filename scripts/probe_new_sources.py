#!/usr/bin/env python3
"""Ask whether a vendor we do not use can be reached, and what it names.

Two repositories were suggested as possible new sources. quantvn turned
out to be a client for Vietcap, DNSE and TCBS - all already used - plus a
reseller backend behind its own API key. vietfin carries one route this
codebase has never touched: FiinGroup, served through SSI's iBoard at
fiin-fundamental.ssi.com.vn, which returns balance sheet, income and cash
flow statements quarterly, as an Excel file, with no API key.

Why that matters is not coverage. It is that FiinGroup NAMES its line
items in words, and VNDIRECT names none of its. This whole audit has been
decoding a numeric scheme by magnitude and by arithmetic identity, and
the first reading of it was wrong in all four parts. A source that spells
out "TOTAL ASSETS" is an independent check on the code map itself.

So this probe does not presume a mapping between the two vendors. For
each field in our lake it asks whether ANY row of the vendor's statement
carries that value for the same quarter, and reports the row's name. The
map is discovered from the data rather than guessed, and a field that
matches nothing is exactly the finding worth having.

Everything here is read-only, bounded, and fails soft: an unreachable
host is a result, not a crash.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Browser headers, as vietfin sends them. X-Fiin-Key is a placeholder
#: there too - whether the endpoint checks it is one of the things this
#: probe is here to find out.
FIIN_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Not A;Brand";v="99", "Chromium";v="98"',
    "DNT": "1",
    "sec-ch-ua-mobile": "?0",
    "X-Fiin-Key": "KEY",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Fiin-User-ID": "ID",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/98.0.4758.102 Safari/537.36"),
    "X-Fiin-Seed": "SEED",
    "sec-ch-ua-platform": "Windows",
    "Origin": "https://iboard.ssi.com.vn",
    "Referer": "https://iboard.ssi.com.vn/",
}

#: Hosts to knock on, with a request cheap enough to be polite.
REACHABILITY = (
    ("fiin-core (SSI organisation list)",
     "https://fiin-core.ssi.com.vn/Master/GetListOrganization?language=vi"),
    ("fiin-market (SSI top movers)",
     "https://fiin-market.ssi.com.vn/TopMover/GetTopGainers"
     "?language=vi&ComGroupCode=VNINDEX"),
    ("cafef",
     "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
     "?Symbol=FPT&StartDate=&EndDate=&PageIndex=1&PageSize=10"),
    ("tcbs public api",
     "https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/FPT/overview"),
)

TOLERANCE = 0.01  # 1%: the same figure from two vendors, not a similar one


def _get(url: str, timeout: float = 20.0, headers: Optional[Dict] = None):
    import requests
    from services.tls_config import tls_verify
    return requests.get(url, headers=headers or FIIN_HEADERS,
                        timeout=timeout, verify=tls_verify())


def knock() -> List[Dict[str, Any]]:
    """Can we reach these at all? A 403 here is the whole answer."""
    rows = []
    for label, url in REACHABILITY:
        row: Dict[str, Any] = {"source": label}
        try:
            response = _get(url)
            row["status"] = response.status_code
            row["bytes"] = len(response.content)
            row["ok"] = response.status_code < 400
        except Exception as exc:
            row["status"] = None
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["ok"] = False
        rows.append(row)
    return rows


def organ_codes() -> Dict[str, str]:
    """symbol -> FiinGroup organCode, needed for a statement request."""
    response = _get(
        "https://fiin-core.ssi.com.vn/Master/GetListOrganization?language=vi")
    payload = response.json()
    items = payload.get("items", payload if isinstance(payload, list) else [])
    out = {}
    for item in items or []:
        ticker = str(item.get("ticker") or "").upper().strip()
        code = item.get("organCode") or item.get("organcode")
        if ticker and code:
            out[ticker] = code
    return out


def statement(organ_code: str, which: str = "BalanceSheet",
              periods: int = 8) -> "Any":
    """One statement as a DataFrame, or raises."""
    import datetime
    import pandas as pd

    url = (f"https://fiin-fundamental.ssi.com.vn/FinancialStatement/"
           f"Download{which}?language=en&OrganCode={organ_code}&Skip=0"
           f"&Frequency=Quarterly&numberOfPeriod={periods}"
           f"&latestYear={datetime.datetime.now().year}")
    response = _get(url, timeout=45.0)
    response.raise_for_status()
    frame = pd.read_excel(io.BytesIO(response.content), skiprows=7)
    return frame.iloc[:-3] if len(frame) > 3 else frame


def _lake_records(path: str, symbol: str) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        lake = json.load(handle)
    entry = (lake.get("symbols", {}) or {}).get(symbol.upper()) or {}
    return entry.get("quarters") or {}


def _column_for(frame, quarter_code: str) -> Optional[str]:
    """FiinGroup labels quarters "Q1 2024"; the lake uses "2024-Q1"."""
    try:
        year, quarter = quarter_code.split("-Q")
    except (ValueError, AttributeError):
        return None
    wanted = {f"Q{int(quarter)} {year}", f"Q{int(quarter):02d} {year}"}
    for column in frame.columns:
        if str(column).strip() in wanted:
            return column
    return None


def name_our_fields(frame, records: Dict[str, Dict[str, Any]],
                    quarter_code: str) -> Tuple[List[Dict[str, Any]], int]:
    """For each of our values, which vendor row carries the same number?

    No mapping is assumed. A field that matches nothing is the finding.
    """
    column = _column_for(frame, quarter_code)
    if column is None:
        return [], 0
    label_column = frame.columns[0]

    vendor_rows: List[Tuple[str, float]] = []
    for _, row in frame.iterrows():
        try:
            value = float(row[column])
        except (TypeError, ValueError):
            continue
        name = str(row[label_column]).strip()
        if name and name.lower() != "nan":
            vendor_rows.append((name, value))

    out = []
    record = records.get(quarter_code) or {}
    for field, ours in sorted(record.items()):
        if not isinstance(ours, (int, float)) or ours == 0:
            continue
        matches = [name for name, value in vendor_rows
                   if abs(value - float(ours)) <= TOLERANCE * max(
                       abs(float(ours)), abs(value), 1.0)]
        out.append({"field": field, "ours": float(ours),
                    "vendor_rows_with_this_value": matches[:3],
                    "matched": bool(matches)})
    return out, len(vendor_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["FPT", "HPG", "VCB"])
    parser.add_argument("--quarter", default=None,
                        help="Quarter to compare, e.g. 2025-Q2.")
    parser.add_argument("--lake", default=None, help="historical_fundamentals.json")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    findings: Dict[str, Any] = {}

    print("## Sources we do not use yet")
    print()
    print("| source | status | bytes |")
    print("|---|---:|---:|")
    reach = knock()
    findings["reachability"] = reach
    for row in reach:
        status = row.get("status")
        print(f"| {row['source']} | "
              f"{status if status is not None else row.get('error', '-')} | "
              f"{row.get('bytes', '-')} |")
    print()

    if not any(r["ok"] for r in reach):
        print("- every host refused or was unreachable from this runner. "
              "Nothing below could be attempted; this is the answer, not a "
              "failure of the probe.")
        if args.json:
            json.dump(findings, open(args.json, "w"), ensure_ascii=False, indent=2)
        return 0

    # --- the part worth the trip -----------------------------------------
    try:
        codes = organ_codes()
        print(f"- FiinGroup lists **{len(codes)}** organisations")
    except Exception as exc:
        print(f"- could not read the organisation list: "
              f"{type(exc).__name__}: {exc}")
        if args.json:
            json.dump(findings, open(args.json, "w"), ensure_ascii=False, indent=2)
        return 0

    findings["organisations"] = len(codes)
    findings["symbols"] = {}

    for symbol in args.symbols:
        symbol = symbol.upper()
        print()
        print(f"### {symbol}")
        code = codes.get(symbol)
        if not code:
            print("- not in the vendor's organisation list")
            continue
        try:
            frame = statement(code)
        except Exception as exc:
            print(f"- statement request failed: {type(exc).__name__}: {exc}")
            continue

        names = [str(v).strip() for v in frame[frame.columns[0]].tolist()
                 if str(v).strip() and str(v).strip().lower() != "nan"]
        print(f"- the vendor names **{len(names)}** rows, for example: "
              + ", ".join(f"`{n}`" for n in names[:6]))

        entry: Dict[str, Any] = {"rows": len(names), "sample_names": names[:40]}

        if args.lake and os.path.exists(args.lake):
            records = _lake_records(args.lake, symbol)
            quarter = args.quarter or (sorted(records)[-1] if records else None)
            if quarter:
                rows, vendor_count = name_our_fields(
                    frame, records, quarter)
                if rows:
                    entry["quarter"] = quarter
                    entry["fields"] = rows
                    print(f"- comparing **{quarter}** against "
                          f"{vendor_count} numeric vendor rows:")
                    print()
                    print("| our field | our value | vendor rows carrying it |")
                    print("|---|---:|---|")
                    for row in rows:
                        found = (", ".join(f"`{n}`" for n in
                                           row["vendor_rows_with_this_value"])
                                 or "**no row carries this number**")
                        print(f"| {row['field']} | {row['ours']:,.0f} | {found} |")
                    missed = [r["field"] for r in rows if not r["matched"]]
                    if missed:
                        print()
                        print("- unmatched: " + ", ".join(f"`{m}`" for m in missed)
                              + ". Either the vendors disagree on these lines "
                                "or our code map reads the wrong one.")
                else:
                    print(f"- the vendor has no column for {quarter}")
        findings["symbols"][symbol] = entry

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(findings, handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
