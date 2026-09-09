#!/usr/bin/env python3
"""One large measurement of every vendor route this project could use.

Why one big run rather than five small ones. Every cycle of this audit has
cost a workflow run to learn one fact, and several of those facts turned
out to be about the question rather than about the data: columns requested
at a period that does not exist, item codes that appear in no payload, a
reading of a numbering scheme that was wrong in all four parts. The cost
of asking is a few hundred requests; the cost of asking one thing at a
time is a week.

So this asks everything at once, and answers nothing on its own. It
fetches, counts and prints. It writes no valuation input, mutates no
record, and touches no provenance tier. What it produces is a description
of what each vendor actually serves, for which companies, under which
names, in which units - the thing that has been missing every time a guess
went wrong.

Sections, in order:

  1. Vietcap's own field catalogue. /financial-statement/metrics returns
     the name of every field of all four statements, in Vietnamese and
     English, for one request. If this route covers the universe it ends
     the item-code archaeology outright.
  2. Reachability of each route, one request each, with the shape it
     returns. A 404 here is worth more than a hundred silent Nones - the
     TCBS route this project called for its whole life returned 404 for
     every ticker and the failure was swallowed into an empty dict.
  3. Per-route coverage over a sample of the companies that have no
     operating line: how many answer, and which fields they carry.
  4. Where the operating line is, per route, located by each field's
     median ratio to revenue rather than by its name.
  5. Units, determined and not assumed: each route's revenue-like field
     against revenue already held in dong, as a distribution of implied
     scale factors.
  6. VNDIRECT item-code relations across all three statements, by the
     matching pursuit in unified_data_service.

Nothing here is a valuation. Read the output, then change the service.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_data_service import (  # noqa: E402
    _request_with_retry,
    _safe_float,
    fetch_vndirect_financials,
    recover_item_code_relations,
)

# --------------------------------------------------------------------------
# Routes. Every URL here is confirmed against a client that uses it, not
# guessed: the Vietcap ones from vnstock/explorer/vci, the KBS one from
# vnstock/explorer/kbs. A route nobody has been observed calling is not
# worth a thousand requests to discover is a 404.
# --------------------------------------------------------------------------
VIETCAP_BASE = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company"
VIETCAP_HANDSHAKE = "https://trading.vietcap.com.vn/priceboard"
KBS_FINANCE = (
    "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/finance-info"
)

#: One reference symbol per company form. Vietcap serves a different chart of
#: accounts to each, so a catalogue taken from one non-financial company
#: would describe a quarter of the exchange and read as if it described all
#: of it.
REFERENCE_SYMBOLS = (
    ("FPT", "CT - non-financial company"),
    ("VCB", "NH - bank"),
    ("SSI", "CK - securities"),
    ("BVH", "BH - insurance"),
)

SECTION_NAMES = ("INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW")


def _handshake_cookies() -> Dict[str, str]:
    """Vietcap's IQ service wants a session from the price board first."""
    resp = _request_with_retry("GET", VIETCAP_HANDSHAKE, timeout=10)
    if resp is None:
        return {}
    try:
        return dict(resp.cookies)
    except Exception:
        return {}


def _get_json(url: str, params: Optional[Dict[str, Any]] = None,
              cookies: Optional[Dict[str, str]] = None) -> Tuple[Optional[int], Any]:
    resp = _request_with_retry("GET", url, params=params, cookies=cookies,
                               timeout=15)
    if resp is None:
        return None, None
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, None


def _shape(payload: Any, depth: int = 0) -> str:
    """A one-line description of a JSON body, so the log says what came back
    rather than only whether something did."""
    if isinstance(payload, dict):
        keys = list(payload.keys())[:12]
        inner = ""
        if depth < 2 and keys:
            first = payload[keys[0]]
            inner = f" -> {_shape(first, depth + 1)}"
        return f"dict({len(payload)}){keys}{inner}"
    if isinstance(payload, list):
        return (f"list({len(payload)})"
                + (f" of {_shape(payload[0], depth + 1)}" if payload else ""))
    return type(payload).__name__


# --------------------------------------------------------------------------
# 1. The field catalogue
# --------------------------------------------------------------------------
def dump_field_catalogue(cookies: Dict[str, str], out: Dict[str, Any]) -> None:
    print("\n" + "=" * 74)
    print(" 1. VIETCAP FIELD CATALOGUE  (/financial-statement/metrics)")
    print("=" * 74)
    print("This is the thing that has been missing all along: the vendor")
    print("naming its own fields. One request per company form.\n")
    catalogue: Dict[str, Any] = {}
    for symbol, form in REFERENCE_SYMBOLS:
        url = f"{VIETCAP_BASE}/{symbol}/financial-statement/metrics"
        status, body = _get_json(url, cookies=cookies)
        if status != 200 or not isinstance(body, dict):
            print(f"  {symbol} ({form}): HTTP {status}, {_shape(body)}")
            continue
        data = body.get("data")
        if not isinstance(data, dict):
            print(f"  {symbol} ({form}): no data block, {_shape(body)}")
            continue
        total = sum(len(v) for v in data.values() if isinstance(v, list))
        print(f"  {symbol} ({form}): {total} fields across {len(data)} reports")
        per_symbol: Dict[str, List[Dict[str, str]]] = {}
        for report, fields in data.items():
            if not isinstance(fields, list):
                continue
            rows = []
            for f in fields:
                if not isinstance(f, dict):
                    continue
                rows.append({
                    "field": str(f.get("field") or ""),
                    "vi": str(f.get("titleVi") or f.get("fullTitleVi") or ""),
                    "en": str(f.get("titleEn") or f.get("fullTitleEn") or ""),
                })
            per_symbol[report] = rows
            print(f"     {report}: {len(rows)} fields")
            for row in rows:
                print(f"       {row['field']:<28} {row['vi'][:38]:<38}"
                      f" {row['en'][:34]}")
        catalogue[symbol] = per_symbol
    out["vietcap_catalogue"] = catalogue


# --------------------------------------------------------------------------
# 2. Reachability
# --------------------------------------------------------------------------
def probe_routes(cookies: Dict[str, str], out: Dict[str, Any]) -> None:
    print("\n" + "=" * 74)
    print(" 2. ROUTE REACHABILITY  (one request each)")
    print("=" * 74)
    probes = [
        ("vietcap statistics-financial",
         f"{VIETCAP_BASE}/FPT/statistics-financial", None),
        ("vietcap financial-statement INCOME",
         f"{VIETCAP_BASE}/FPT/financial-statement", {"section": "INCOME_STATEMENT"}),
        ("vietcap financial-statement BALANCE",
         f"{VIETCAP_BASE}/FPT/financial-statement", {"section": "BALANCE_SHEET"}),
        ("vietcap financial-statement CASHFLOW",
         f"{VIETCAP_BASE}/FPT/financial-statement", {"section": "CASH_FLOW"}),
        ("kbs finance-info KQKD year",
         f"{KBS_FINANCE}/FPT",
         {"page": 1, "pageSize": 4, "type": "KQKD", "unit": 1000,
          "termtype": 1, "languageid": 1}),
        ("kbs finance-info KQKD quarter",
         f"{KBS_FINANCE}/FPT",
         {"page": 1, "pageSize": 4, "type": "KQKD", "unit": 1000,
          "termtype": 2, "languageid": 1}),
        ("kbs finance-info CDKT",
         f"{KBS_FINANCE}/FPT",
         {"page": 1, "pageSize": 4, "type": "CDKT", "unit": 1000,
          "termtype": 1, "languageid": 1}),
    ]
    results = {}
    for label, url, params in probes:
        status, body = _get_json(url, params=params, cookies=cookies)
        print(f"  {label:<38} HTTP {status}  {_shape(body)}")
        results[label] = {"status": status, "shape": _shape(body)}
    out["reachability"] = results


# --------------------------------------------------------------------------
# 3 + 4 + 5. Coverage, the operating line, and units
# --------------------------------------------------------------------------
def _vietcap_statement_rows(symbol: str, section: str,
                            cookies: Dict[str, str]) -> List[Dict[str, Any]]:
    status, body = _get_json(
        f"{VIETCAP_BASE}/{symbol}/financial-statement",
        params={"section": section}, cookies=cookies,
    )
    if status != 200 or not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    for key in ("quarters", "years"):
        rows = data.get(key)
        if isinstance(rows, list) and rows:
            return [r for r in rows if isinstance(r, dict)]
    return []


def _vietcap_stats_rows(symbol: str,
                        cookies: Dict[str, str]) -> List[Dict[str, Any]]:
    status, body = _get_json(f"{VIETCAP_BASE}/{symbol}/statistics-financial",
                             cookies=cookies)
    if status != 200 or not isinstance(body, dict):
        return []
    data = body.get("data")
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict) and r]
    if isinstance(data, dict):
        # A record, not an envelope. {"years": []} is a body that answered
        # with nothing; counting it as a row would report the route as
        # covering a company it said nothing about, which is the single
        # most misleading thing a coverage census can do.
        scalars = {
            k: v for k, v in data.items()
            if not isinstance(v, (list, dict))
        }
        return [data] if scalars else []
    return []


def _kbs_rows(symbol: str) -> List[Dict[str, Any]]:
    status, body = _get_json(
        f"{KBS_FINANCE}/{symbol}",
        params={"page": 1, "pageSize": 4, "type": "KQKD", "unit": 1000,
                "termtype": 1, "languageid": 1},
    )
    if status != 200:
        return []
    data = body.get("data") if isinstance(body, dict) else body
    if isinstance(data, dict):
        for key in ("items", "data", "list", "rows"):
            inner = data.get(key)
            if isinstance(inner, list):
                data = inner
                break
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


ROUTES = {
    "vietcap income-statement": lambda s, c: _vietcap_statement_rows(
        s, "INCOME_STATEMENT", c),
    "vietcap statistics-financial": lambda s, c: _vietcap_stats_rows(s, c),
    "kbs finance-info KQKD": lambda s, c: _kbs_rows(s),
}


def survey(symbols: List[str], revenue_by_symbol: Dict[str, float],
           cookies: Dict[str, str], workers: int,
           out: Dict[str, Any]) -> None:
    print("\n" + "=" * 74)
    print(f" 3-5. PER-ROUTE SURVEY OVER {len(symbols)} SYMBOLS WITH NO"
          " OPERATING LINE")
    print("=" * 74)

    for route_name, fetch in ROUTES.items():
        answered = 0
        field_counts: "collections.Counter[str]" = collections.Counter()
        ratios: Dict[str, List[float]] = {}
        raw_values: Dict[str, List[float]] = {}
        raw_first: Dict[str, Any] = {}

        def work(sym: str):
            try:
                return sym, fetch(sym, cookies)
            except Exception:
                return sym, []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, s) for s in symbols]
            for fut in as_completed(futures):
                sym, rows = fut.result()
                if not rows:
                    continue
                answered += 1
                row = rows[0]
                if not raw_first:
                    raw_first = dict(list(row.items())[:40])
                known_rev = revenue_by_symbol.get(sym)
                for key, value in row.items():
                    num = _safe_float(value)
                    if num is None:
                        continue
                    field_counts[key] += 1
                    raw_values.setdefault(key, []).append(num)
                    if known_rev and known_rev > 0:
                        ratios.setdefault(key, []).append(num / known_rev)

        print(f"\n  --- {route_name} ---")
        print(f"  answered for {answered}/{len(symbols)}")
        if not answered:
            print("  nothing to describe.")
            out.setdefault("routes", {})[route_name] = {"answered": 0}
            continue
        print(f"  first row keys: {sorted(raw_first)[:24]}")
        # Three numbers per field, because the ratio to revenue alone
        # cannot answer the question this survey exists to answer.
        #
        # The first run made that plain. Vietcap answered for 688 of the
        # 720 companies with no operating line, and every ratio field -
        # ebitMargin and roic among them, the two blocking drivers - was
        # printed as +0.000000. That is arithmetic, not data: a margin of
        # 0.12 divided by a revenue of 1e11 is 1e-12, and so is a margin of
        # zero. The route that might close most of the coverage gap was
        # indistinguishable from a route sending nothing but zeros.
        #
        # So: the median of the raw value says what the vendor actually
        # sends and in what unit; the non-zero count separates a field
        # genuinely populated for n companies from one padded with zeros
        # for all of them - the bank-only fields came back at the same 688
        # as the rest, which is exactly that padding; and the ratio to
        # revenue stays, because it is what locates an absolute line.
        print(f"  {'field':<30}{'n':>6}{'nonzero':>9}"
              f"{'median value':>18}{'x revenue':>14}")
        summary = {}
        for key, count in field_counts.most_common(60):
            raw = sorted(raw_values.get(key) or [])
            med_raw = raw[len(raw) // 2] if raw else None
            nonzero = sum(1 for v in raw if v != 0.0)
            series = sorted(ratios.get(key) or [])
            med = series[len(series) // 2] if series else None
            print(f"  {key:<30}{count:>6}{nonzero:>9}"
                  f"{(f'{med_raw:+.6g}' if med_raw is not None else '-'):>18}"
                  f"{(f'{med:+.6f}' if med is not None else '-'):>14}")
            summary[key] = {
                "n": count, "nonzero": nonzero,
                "median_value": med_raw, "median_ratio": med,
            }
        out.setdefault("routes", {})[route_name] = {
            "answered": answered, "of": len(symbols), "fields": summary,
            # One real row, verbatim. The aggregates say how often a field
            # answers and roughly how big it is; they cannot show what the
            # vendor actually sends. Every wrong turn in this audit came
            # from reasoning about a payload nobody had looked at.
            "sample_row": {
                k: (v if isinstance(v, (int, float, str, bool, type(None)))
                    else str(v)[:200])
                for k, v in raw_first.items()
            },
        }


# --------------------------------------------------------------------------
# 6. VNDIRECT item-code relations, all three statements
# --------------------------------------------------------------------------
def vndirect_relations(symbols: List[str], workers: int,
                       out: Dict[str, Any]) -> None:
    print("\n" + "=" * 74)
    print(" 6. VNDIRECT ITEM-CODE RELATIONS, ALL THREE STATEMENTS")
    print("=" * 74)
    print("The vendor names none of its codes. An income statement is a set")
    print("of exact arithmetic relations, so they are recovered from the")
    print("numbers instead. Nothing here is proposed.\n")

    payloads: List[Dict[str, Any]] = []

    def work(sym: str):
        try:
            return fetch_vndirect_financials(sym) or {}
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(work, s) for s in symbols]):
            entry = fut.result()
            by_code = entry.get("income_statement_ttm_by_code")
            if isinstance(by_code, dict) and by_code:
                payloads.append({int(k): v for k, v in by_code.items()})

    print(f"  {len(payloads)} companies returned a coded income statement")
    if not payloads:
        out["vndirect_relations"] = {}
        return
    codes = sorted({c for row in payloads for c in row})
    print(f"  {len(codes)} distinct income-statement codes\n")

    # Ratio to revenue first: it proposes nothing and it is what identified
    # cost of goods (0.859) and gross profit (0.144) in the last run.
    rev_codes = (21001, 21000, 21010)
    print(f"  {'code':<10}{'n':>6}   median x revenue")
    shape: Dict[int, List[float]] = {}
    for row in payloads:
        rev = next((row[c] for c in rev_codes
                    if row.get(c) is not None and row[c] > 0), None)
        if not rev:
            continue
        for code, val in row.items():
            if val is not None:
                shape.setdefault(code, []).append(val / rev)
    for code in sorted(shape, key=lambda c: -len(shape[c])):
        series = sorted(shape[code])
        print(f"  {code:<10}{len(series):>6}   "
              f"{series[len(series) // 2]:>+12.4f}")

    print("\n  Relations recovered by orthogonal matching pursuit:")
    relations = recover_item_code_relations(payloads, codes)
    found = {}
    for target, terms, rate, n in relations:
        if not terms:
            print(f"    {target:<8}   nothing reproduces it")
            continue
        expr = " ".join(
            f"{'+' if b > 0 else '-'} "
            f"{'' if abs(abs(b) - 1.0) < 0.02 else f'{abs(b):.3f}*'}{c}"
            for c, b in terms
        ).lstrip("+ ")
        print(f"    {target:<8} = {expr}")
        print(f"               {rate:5.1f}%  (n={n})")
        found[target] = {"terms": [[c, b] for c, b in terms],
                         "rate": rate, "n": n}
    out["vndirect_relations"] = found


# --------------------------------------------------------------------------
def pick_symbols(limit: Optional[int]) -> Tuple[List[str], Dict[str, float]]:
    """Companies with no trustworthy operating line, and their revenue.

    Those are the ones the whole exercise is about; measuring a route
    against companies that are already valued would say nothing about
    whether it closes the gap.
    """
    from services.unified_data_service import screener_snapshot_file

    path = screener_snapshot_file()
    if not os.path.exists(path):
        raise SystemExit(
            f"No snapshot at {path}. Run the universe sync first - this "
            "measures the gap that sync reports, so it needs the report."
        )
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    stocks = payload.get("stocks") if isinstance(payload, dict) else payload
    if isinstance(stocks, dict):
        stocks = list(stocks.values())

    symbols: List[str] = []
    revenue: Dict[str, float] = {}
    for rec in stocks:
        if not isinstance(rec, dict):
            continue
        sym = str(rec.get("symbol") or "").upper().strip()
        if not sym:
            continue
        tiers = rec.get("field_provenance") or {}
        if int(tiers.get("ebit", 0) or 0) >= 2:
            continue
        symbols.append(sym)
        rev = _safe_float(rec.get("revenue"))
        if rev and rev > 0:
            revenue[sym] = rev
    symbols.sort()
    if limit:
        symbols = symbols[:limit]
    return symbols, revenue


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=250,
                        help="symbols to survey per route (0 = all)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--json", help="write the whole census to this path")
    parser.add_argument("--skip-survey", action="store_true",
                        help="catalogue and reachability only, no sampling")
    args = parser.parse_args(argv)

    out: Dict[str, Any] = {}
    cookies = _handshake_cookies()
    print(f"handshake returned {len(cookies)} cookies")

    dump_field_catalogue(cookies, out)
    probe_routes(cookies, out)

    if not args.skip_survey:
        symbols, revenue = pick_symbols(args.limit or None)
        print(f"\n{len(symbols)} symbols have no trustworthy operating line;"
              f" revenue known for {len(revenue)} of them")
        survey(symbols, revenue, cookies, args.workers, out)
        vndirect_relations(symbols, args.workers, out)

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(out, handle, ensure_ascii=False, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
