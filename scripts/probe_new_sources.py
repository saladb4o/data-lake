#!/usr/bin/env python3
"""Ask a vendor that names its line items which of our numbers it carries.

VNDIRECT, the only source the fundamentals lake reads, names nothing: a
balance sheet arrives as a numeric VAS code scheme, and this audit has
been decoding it by magnitude and by arithmetic identity. The first
reading of it was wrong in all four parts. Any vendor that spells out
"Depreciation and Amortisation" is therefore an independent check on the
code map itself, which is what this probe is for.

Two such vendors are free. ``vnstock.Finance`` accepts exactly VCI
(Vietcap) and KBS, and both serve quarterly statements with named
columns. Those run every pass.

A third, FiinGroup through SSI, is behind a paid plan, so it is opt-in
(``--include-fiin``); the code is kept because if a plan is ever bought
it answers the same question against a fourth opinion.

This probe presumes no mapping in either direction. For
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

    return (_match_values(vendor_rows, records.get(quarter_code) or {}),
            len(vendor_rows))


# --- vendors that name their line items, and cost nothing ---------------
#: ``vnstock.Finance`` accepts exactly these two. Vietcap and KBS both
#: return statements whose LINE ITEMS ARE COLUMN NAMES IN WORDS, which is
#: the same independent check on the numeric code map that FiinGroup
#: would have been, without a subscription. The shape is transposed
#: relative to FiinGroup's Excel: there a quarter is a column and a line
#: item a row; here a quarter is a row and a line item a column. So the
#: value matching below is shared and only the extraction differs.
VNSTOCK_SOURCES: Tuple[str, ...] = ("VCI", "KBS")

#: Columns that identify the period rather than report a figure.
PERIOD_COLUMNS = ("ticker", "yearreport", "lengthreport", "year", "quarter",
                  "period", "cp", "ky", "nam")


def _match_values(vendor_rows: List[Tuple[str, float]],
                  record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """For each of our numbers, which named vendor line carries it?

    Shared by both vendor shapes. No mapping is assumed in either
    direction: a field that matches nothing is the finding.
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
    """Same question as ``name_our_fields``, for a quarter-per-row frame."""
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

    This is the check the code map has never had. It costs nothing and
    needs no plan, so unlike the FiinGroup section below it runs every
    pass. A vendor that cannot be reached, or a statement it will not
    serve, is recorded as that - the probe reports what happened rather
    than only what worked.
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
    parser.add_argument(
        "--include-fiin", action="store_true",
        help="Also knock on FiinGroup and the other paid/unused hosts.")
    args = parser.parse_args()

    findings: Dict[str, Any] = {}
    report_free_vendors(args, findings)

    if not args.include_fiin:
        if args.json:
            with open(args.json, "w", encoding="utf-8") as handle:
                json.dump(findings, handle, ensure_ascii=False, indent=2)
        return 0

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
