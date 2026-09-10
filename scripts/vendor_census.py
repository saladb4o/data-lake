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
  7. The land bank and the loan book, by item code, over the two sectors
     whose models need them. Presence of the codes the service reads, the
     count that actually reaches the record, and - for the companies that
     carry none of them - what their balance sheet does carry, named by
     the vendor and sized against total assets. Three faults look
     identical from the blocking table (the vendor has no such line, the
     item codes are wrong, the number is fetched and never wired) and this
     is what tells them apart. --only landbank runs it alone.

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

#: The two sectors split apart. The service keeps one frozenset because it
#: only asks "does this symbol need a VNDIRECT call at all"; here the two
#: halves need different item codes, so they are named separately. A test
#: asserts their union is still the service's set, because a sector added
#: there and not here would be censused for the wrong line in silence.
_LANDBANK_SECTORS = frozenset({"VNREAL", "VNREA", "8600"})
_LOANBOOK_SECTORS = frozenset({"VNFIN", "VNBNK", "VNINS", "8300", "8500"})

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
def collect_field_catalogue(cookies: Dict[str, str],
                            out: Dict[str, Any]) -> Dict[str, str]:
    """Fetch the vendor's own field names. Returns {field: "vi | en"}.

    Collected before the survey because the survey prints field codes -
    cfa18, bsa2, iss47 - that mean nothing on their own, and the vendor has
    been willing to name every one of them all along. Printed after the
    survey, by print_field_catalogue, because it runs to fourteen hundred
    lines and would push everything worth acting on out of the tail of the
    log, which is the only part of a job log that can be read back.
    """
    catalogue: Dict[str, Any] = {}
    names: Dict[str, str] = {}
    for symbol, form in REFERENCE_SYMBOLS:
        url = f"{VIETCAP_BASE}/{symbol}/financial-statement/metrics"
        status, body = _get_json(url, cookies=cookies)
        if status != 200 or not isinstance(body, dict):
            catalogue[symbol] = {"error": f"HTTP {status}, {_shape(body)}"}
            continue
        data = body.get("data")
        if not isinstance(data, dict):
            catalogue[symbol] = {"error": f"no data block, {_shape(body)}"}
            continue
        per_symbol: Dict[str, List[Dict[str, str]]] = {}
        for report, fields in data.items():
            if not isinstance(fields, list):
                continue
            rows = []
            for f in fields:
                if not isinstance(f, dict):
                    continue
                row = {
                    "field": str(f.get("field") or ""),
                    "vi": str(f.get("titleVi") or f.get("fullTitleVi") or ""),
                    "en": str(f.get("titleEn") or f.get("fullTitleEn") or ""),
                }
                rows.append(row)
                # First name wins. The four reference symbols are four
                # charts of accounts and a code can repeat across them; the
                # non-financial company is asked first and is the form most
                # of the exchange uses.
                if row["field"] and row["field"] not in names:
                    names[row["field"]] = f"{row['vi']} | {row['en']}".strip(" |")
            per_symbol[report] = rows
        catalogue[symbol] = per_symbol
    out["vietcap_catalogue"] = catalogue
    return names


def print_field_catalogue(out: Dict[str, Any]) -> None:
    """The full catalogue, last, because of its size."""
    catalogue = out.get("vietcap_catalogue") or {}
    print("\n" + "=" * 74)
    print(" 7. VIETCAP FIELD CATALOGUE  (/financial-statement/metrics)")
    print("=" * 74)
    print("Counts only. The full catalogue - every field, Vietnamese and")
    print("English - is in the JSON, and every field the survey actually")
    print("saw is named inline in the table above.\n")
    print("Dumping all fourteen hundred rows here was the mistake this")
    print("replaces. A job log can only be read from its tail, so a dump")
    print("that size does not add information to the log - it removes it,")
    print("by pushing everything above it out of reach. Printing it first")
    print("hid the survey; printing it last hid the survey and the coverage")
    print("headline both. The fix is not to reorder a wall of text but to")
    print("stop emitting it where it cannot be read.\n")
    for symbol, form in REFERENCE_SYMBOLS:
        per_symbol = catalogue.get(symbol)
        if not isinstance(per_symbol, dict):
            print(f"  {symbol} ({form}): not collected")
            continue
        if "error" in per_symbol:
            print(f"  {symbol} ({form}): {per_symbol['error']}")
            continue
        total = sum(len(v) for v in per_symbol.values()
                    if isinstance(v, list))
        print(f"  {symbol} ({form}): {total} fields across "
              f"{len(per_symbol)} reports")
        for report, rows in per_symbol.items():
            if not isinstance(rows, list):
                continue
            print(f"     {report}: {len(rows)} fields")


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
    # The cash-flow statement, because the blockers changed shape. Reading
    # the operating line Vietcap reports moved ebitda from 632 blocked
    # symbols to 148 and ebit from 715 to 200; fcf at 306 and cfo at 166
    # are now the two largest, and no route measured so far serves either.
    # statistics-financial carries priceToCashFlow for 661 companies, which
    # with a market cap whose unit is confirmed would imply a cash flow -
    # but "price to cash flow" does not say which cash flow, and a guess
    # about which line a ratio refers to is exactly the kind of assumption
    # this census exists to replace. So ask the statement itself.
    "vietcap cash-flow": lambda s, c: _vietcap_statement_rows(
        s, "CASH_FLOW", c),
    # The balance sheet, measured but not yet acted on. cash blocks 121
    # symbols and debt 120, and both live here. No code reads this route
    # yet and none will until this census prints the vendor's own name
    # beside each bsa code - the income statement is being wired in the
    # same change precisely because its names were already read, and
    # guessing which bsa code is debt would undo the reason that worked.
    "vietcap balance-sheet": lambda s, c: _vietcap_statement_rows(
        s, "BALANCE_SHEET", c),
    "kbs finance-info KQKD": lambda s, c: _kbs_rows(s),
}


#: Room for the largest statement any route serves. Vietcap's balance
#: sheet has 122 fields and its securities-form income statement 80; a cap
#: below those drops real lines from the one table that exists to say which
#: lines are real.
_SURVEY_FIELD_CAP = 130


def survey(symbols: List[str], revenue_by_symbol: Dict[str, float],
           cookies: Dict[str, str], workers: int,
           out: Dict[str, Any],
           names: Optional[Dict[str, str]] = None) -> None:
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
              f"{'median value':>18}{'x revenue':>14}  what the vendor calls it")
        summary = {}
        # The cap was 60, and it truncated in silence. Vietcap's balance
        # sheet carries 122 fields; the survey printed the first 60, the
        # table simply stopped at bsa58, and nothing said so - which is how
        # a run that was asked for total equity and long-term borrowings
        # came back without either, looking complete. A limit that hides
        # what it dropped is worse than no limit, because it answers a
        # question it did not answer.
        #
        # So: enough room for the largest statement, and a line stating
        # exactly what was left out whenever anything is.
        shown = field_counts.most_common(_SURVEY_FIELD_CAP)
        if len(field_counts) > len(shown):
            print(f"  ({len(shown)} of {len(field_counts)} fields shown;"
                  f" the rest are in the JSON)")
        for key, count in shown:
            raw = sorted(raw_values.get(key) or [])
            med_raw = raw[len(raw) // 2] if raw else None
            nonzero = sum(1 for v in raw if v != 0.0)
            series = sorted(ratios.get(key) or [])
            med = series[len(series) // 2] if series else None
            # The vendor's own name for the field, inline. A table of
            # cfa18 / bsa2 / iss47 forces the reader to guess which line is
            # which from its magnitude, and guessing which line a number is
            # has been the single most expensive mistake in this audit.
            # Vietcap names every one of these codes and always has.
            label = (names or {}).get(key, "")
            print(f"  {key:<30}{count:>6}{nonzero:>9}"
                  f"{(f'{med_raw:+.6g}' if med_raw is not None else '-'):>18}"
                  f"{(f'{med:+.6f}' if med is not None else '-'):>14}"
                  f"  {label[:60]}")
            summary[key] = {
                "n": count, "nonzero": nonzero,
                "median_value": med_raw, "median_ratio": med,
                "vendor_name": label or None,
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
# 7. The land bank and the loan book, by item code
# --------------------------------------------------------------------------
#: The codes the service reads for the two lines TradingView has no column
#: for, and the sectors whose models need them. Kept next to the census
#: rather than imported so that a run says which codes it tested even if
#: the service has moved on since.
LINE_CODES = {
    # 11400/11410 are VAS 140/141, inventory - where a Vietnamese developer
    # holds its pipeline. The pair read before, 11420 and 12510, were VAS
    # 142 (a line the standard form does not have) and VAS 251 (long-term
    # work in progress, zero for all 112 companies censused).
    "landbank": (11400, 11410),
    "bank_loans": (112000,),
}

#: Total assets, tried in order, so a code can be reported as a share of
#: the balance sheet rather than as a bare magnitude nobody can place.
_TOTAL_ASSET_CODES = (12700, 10000, 11000, 100000, 130000)

#: How many unmatched codes to name per group. A balance sheet runs to a
#: hundred-odd lines; the ones worth reading are the large ones.
_CODE_REPORT_CAP = 40


def _cell(entry: Dict[str, Any], code: int) -> Optional[float]:
    """One balance-sheet figure, whichever way the keys were serialised.

    A payload read back from JSON has string keys and one straight off the
    fetch has integer keys; a lookup that assumed either would report the
    line absent for half the runs.
    """
    sheet = entry.get("balance_sheet_fq_by_code") or {}
    value = sheet.get(code)
    if value is None:
        value = sheet.get(str(code))
    return value


def pick_line_symbols(limit: Optional[int]) -> Dict[str, List[str]]:
    """The companies whose valuation needs a land bank or a loan book.

    Picked by sector, not by what is missing, and that distinction is the
    point. A symbol refused for want of a land bank and a symbol whose land
    bank arrived are the same question here - "does the vendor carry this
    line for this kind of company" - and selecting only the refused ones
    would throw away every case where the answer is yes, leaving no
    baseline to read the failures against.
    """
    from services.unified_data_service import screener_snapshot_file

    path = screener_snapshot_file()
    if not os.path.exists(path):
        raise SystemExit(
            f"No snapshot at {path}. Run the universe sync first - the "
            "population is taken from the snapshot's sector codes."
        )
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    stocks = payload.get("stocks") if isinstance(payload, dict) else payload
    if isinstance(stocks, dict):
        stocks = list(stocks.values())

    groups: Dict[str, List[str]] = {"landbank": [], "bank_loans": []}
    for rec in stocks:
        if not isinstance(rec, dict):
            continue
        sym = str(rec.get("symbol") or "").upper().strip()
        if not sym:
            continue
        code = str(rec.get("sector_code") or "").strip().upper()
        if code in _LANDBANK_SECTORS:
            groups["landbank"].append(sym)
        elif code in _LOANBOOK_SECTORS:
            groups["bank_loans"].append(sym)
    for name in groups:
        groups[name].sort()
        if limit:
            groups[name] = groups[name][:limit]
    return groups


def landbank_and_loanbook(groups: Dict[str, List[str]], workers: int,
                          out: Dict[str, Any],
                          held: Optional[Dict[str, Dict[str, Any]]] = None,
                          ) -> None:
    """Whether VNDIRECT carries the two lines, and under which codes.

    Two runs have now reported `landbank` blocking 123 symbols and `rwa`
    blocking 41, unchanged, after the request for them was wired and the
    sector gate widened to ask. An unchanged count cannot tell a vendor
    that does not carry the line from a pair of item codes read wrong, and
    those need opposite fixes: the first is the end of the matter, the
    second is a one-line change. Nothing short of looking at which codes
    the payloads actually contain separates them, so that is what this
    does - presence of the codes asked for, and, for the companies that
    have none of them, what the balance sheet does carry, named by the
    vendor and sized against total assets.

    It proposes no code. It prints what is there.
    """
    print("\n" + "=" * 74)
    print(" 7. THE LAND BANK AND THE LOAN BOOK, BY ITEM CODE")
    print("=" * 74)

    every = sorted({s for syms in groups.values() for s in syms})
    print(f"  {len(every)} companies in the two sectors "
          f"({len(groups['landbank'])} real estate, "
          f"{len(groups['bank_loans'])} banks and insurers)\n")

    fetched: Dict[str, Dict[str, Any]] = {}

    def work(sym: str) -> Tuple[str, Dict[str, Any]]:
        try:
            return sym, (fetch_vndirect_financials(sym) or {})
        except Exception:
            return sym, {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(work, s) for s in every]):
            sym, entry = fut.result()
            fetched[sym] = entry

    report: Dict[str, Any] = {}
    for group, symbols in groups.items():
        codes = LINE_CODES[group]
        print("-" * 74)
        print(f"  {group}: codes {', '.join(str(c) for c in codes)}"
              f", {len(symbols)} companies")
        print("-" * 74)

        answered = [s for s in symbols if fetched.get(s, {}).get(
            "balance_sheet_fq_by_code")]
        print(f"  {len(answered):>5} of {len(symbols)} returned a coded "
              f"balance sheet at all")
        if not answered:
            # No payloads means the route failed for this sector, which is
            # a different finding from an absent line and must not be
            # reported as one.
            print("        so nothing here says anything about the line;"
                  " the route is what failed")
            report[group] = {"answered": 0, "of": len(symbols)}
            continue

        # Present and non-zero, separately, because they answer different
        # questions and the first run conflated them: 12510 came back
        # present for 112 of 112 developers and the section reported "the
        # codes are right", while every value was zero and not one land
        # bank reached the record. A line item the vendor emits for every
        # company and populates for none is not the line. The survey in
        # section 5 already learned this - "the non-zero count separates a
        # field genuinely populated from one padded with zeros" - and this
        # section was written without it.
        per_code = {}
        for code in codes:
            have = [s for s in answered if _cell(fetched[s], code) is not None]
            live = [s for s in have if _cell(fetched[s], code) != 0.0]
            per_code[code] = {"present": len(have), "nonzero": len(live)}
            print(f"  {len(have):>5} of {len(answered)} carry {code}, "
                  f"{len(live)} of those non-zero")

        # Missing means no code carries a usable figure. A zero is not a
        # land bank, and the service will not publish one either - it
        # requires `> 0` - so a company whose only answer is zero belongs
        # in the group whose balance sheet gets examined.
        missing = [
            s for s in answered
            if not any(_cell(fetched[s], c) for c in codes)
        ]
        # The count the sync publishes, for the same companies. If the
        # vendor carries the code and the record still has no line, the
        # fault is downstream of the fetch and the codes are not the
        # problem at all - a third possibility neither run could see.
        if held is not None:
            key = "landbank_fq" if group == "landbank" else "bank_loans_fq"
            reached = sum(1 for s in answered
                          if (held.get(s) or {}).get(key) is not None)
            print(f"  {reached:>5} of {len(answered)} reach the snapshot "
                  f"as {key}")

        print(f"  {len(missing):>5} of {len(answered)} carry none of them\n")
        report[group] = {
            "answered": len(answered), "of": len(symbols),
            "per_code": per_code, "missing": len(missing),
        }
        if not missing:
            print("  Every company that answered carries one of the codes"
                  " with a non-zero value, so the codes are right\n")
            continue

        # What those companies do have. Frequency says which lines exist
        # for this company form; the share of total assets says which of
        # them could be a land bank or a loan book, since a loan book is
        # most of a bank's balance sheet and a land bank is a large
        # fraction of a developer's. The vendor's own name settles it.
        freq: "collections.Counter[int]" = collections.Counter()
        shares: Dict[int, List[float]] = {}
        raw_values: Dict[int, List[float]] = {}
        names: Dict[int, str] = {}
        for sym in missing:
            sheet = fetched[sym]["balance_sheet_fq_by_code"]
            sheet = {int(k): v for k, v in sheet.items()}
            labels = fetched[sym].get("item_code_names") or {}
            total = next((sheet[c] for c in _TOTAL_ASSET_CODES
                          if sheet.get(c)), None)
            for code, value in sheet.items():
                if value is None:
                    continue
                freq[code] += 1
                raw_values.setdefault(code, []).append(value)
                if total:
                    shares.setdefault(code, []).append(value / total)
                if code not in names:
                    label = labels.get(code) or labels.get(str(code))
                    if label:
                        names[code] = str(label)

        # Ranked by size on the balance sheet, not by how many companies
        # carry the code. The first run ranked by frequency, every code was
        # carried by all 41 banks, and the forty that got printed were an
        # arbitrary slice in which the largest asset line - the one that
        # would be the loan book - did not appear at all. The vendor names
        # none of these codes, so magnitude is the only handle there is,
        # and a table sorted by anything else throws it away.
        def _median(code):
            series = sorted(shares.get(code) or [])
            return series[len(series) // 2] if series else None

        ranked = sorted(
            freq,
            key=lambda c: (-abs(_median(c) or 0.0), -freq[c]),
        )
        shown = ranked[:_CODE_REPORT_CAP]
        if len(freq) > len(shown):
            print(f"  ({len(shown)} of {len(freq)} codes shown, largest"
                  f" first; the rest are in the JSON)")
        print(f"  {'code':<10}{'n':>6}{'nonzero':>9}{'median x assets':>18}"
              f"  what the vendor calls it")
        rows = {}
        for code in shown:
            count = freq[code]
            med = _median(code)
            live = sum(1 for v in (raw_values.get(code) or []) if v != 0.0)
            print(f"  {code:<10}{count:>6}{live:>9}"
                  f"{(f'{med:+.4f}' if med is not None else '-'):>18}"
                  f"  {names.get(code, '')[:38]}")
            rows[code] = {"n": count, "nonzero": live, "median_share": med,
                          "vendor_name": names.get(code)}
        report[group]["codes_present"] = rows
        print()

    out["landbank_and_loanbook"] = report


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


def _held_lines() -> Dict[str, Dict[str, Any]]:
    """The two lines as the snapshot currently holds them, per symbol.

    Read so the census can distinguish a third case from the two it was
    written for: the vendor carries the code, and the number still does not
    reach the record. That is a wiring fault, not a vendor one, and it
    looks identical from the blocking table.
    """
    from services.unified_data_service import screener_snapshot_file

    path = screener_snapshot_file()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    stocks = payload.get("stocks") if isinstance(payload, dict) else payload
    if isinstance(stocks, dict):
        stocks = list(stocks.values())
    held = {}
    for rec in stocks:
        if isinstance(rec, dict) and rec.get("symbol"):
            held[str(rec["symbol"]).upper().strip()] = {
                "landbank_fq": rec.get("landbank_fq"),
                "bank_loans_fq": rec.get("bank_loans_fq"),
            }
    return held


def _write(out: Dict[str, Any], path: Optional[str]) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2, default=str)
    print(f"\nwrote {path}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=250,
                        help="symbols to survey per route (0 = all)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--json", help="write the whole census to this path")
    parser.add_argument("--skip-survey", action="store_true",
                        help="catalogue and reachability only, no sampling")
    # The full census prints well over a thousand lines and a job log can
    # only be read from its tail, so a run that asks one question should
    # print one answer. "landbank" runs section 7 alone: two sectors, a few
    # hundred requests, and a table short enough to survive the tail.
    parser.add_argument("--only", choices=("all", "landbank"), default="all",
                        help="run one section instead of the whole census")
    args = parser.parse_args(argv)

    out: Dict[str, Any] = {}

    if args.only == "landbank":
        groups = pick_line_symbols(args.limit or None)
        landbank_and_loanbook(groups, args.workers, out,
                              held=_held_lines())
        _write(out, args.json)
        return 0

    cookies = _handshake_cookies()
    print(f"handshake returned {len(cookies)} cookies")

    # The catalogue is collected first because the survey needs its names,
    # but printed last because it is 1400 lines long. GitHub serves only the
    # tail of a job log, so anything upstream of a dump that size cannot be
    # read at all - three separate reads were spent this afternoon
    # discovering that the answer was in a part of the log the API will not
    # return. Ordering the output by how much it is worth reading is not
    # cosmetic; it decides whether a measurement can be acted on.
    names = collect_field_catalogue(cookies, out)
    probe_routes(cookies, out)

    if not args.skip_survey:
        symbols, revenue = pick_symbols(args.limit or None)
        print(f"\n{len(symbols)} symbols have no trustworthy operating line;"
              f" revenue known for {len(revenue)} of them")
        survey(symbols, revenue, cookies, args.workers, out, names)
        vndirect_relations(symbols, args.workers, out)

    print_field_catalogue(out)

    # After the catalogue, deliberately. The catalogue is 1400 lines and
    # whatever follows it is the only part of the log guaranteed to be
    # readable; this section is the one that answers a question a run is
    # currently waiting on.
    groups = pick_line_symbols(args.limit or None)
    landbank_and_loanbook(groups, args.workers, out, held=_held_lines())

    _write(out, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
