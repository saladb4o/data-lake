"""Does the BCTC agree with itself, and does it agree with VNDIRECT?

Run 35220475916 got a cash flow statement out of a real filing for the
first time. What it printed looked like the thing this repo has needed all
along - accounting codes with Vietnamese labels beside them - and it is
not. The labels come from `TT200_CASH_FLOW_CODES`, a dict in the parser.
The parser reads the *code* off the page and prints its own label for it.
So the output asserts exactly the convention that was in question, which
makes it worth no more than VNDIRECT's `32100` is worth: both are a guess
about VAS numbering, one of them just looks like evidence.

What that run did produce, unnoticed, is better than a label. The numbers
tie:

    CFO + CFI + CFF          = NCF   exact, to the dong
    21+22+23+24+25+27        = CFI   exact, to the dong

The second identity is the useful one. Whatever the row at code 21 is, it
is a component of the investing section and the section sums without it
left over. A mislabelled row would have to be off by zero to survive that.
A label is an assertion; a sum that closes is a measurement.

The same run also shows the parser getting rows wrong, and the identities
are what reveal it:

    60 + 50 + 61 = 70,186,070,214   but 70 = 1,905,249,672,046

The implied opening balance, 1,877,791,791,943, is sitting in code 1 and
in code 70's previous_val. Codes 1, 2, 3 and 60 are misbound; 20, 30, 40,
50, 70 and the whole investing block are not. Counting extracted items
could never have told those apart - all of them count as "extracted".

So this script stops counting items and starts checking arithmetic. Every
statement is run against the identities TT200 guarantees, and a statement
is reported by which identities closed, not by how many rows came back.

The vendor comparison, and why it carries a control
---------------------------------------------------

The open question is whether VNDIRECT's itemCode 32100 is VAS 21, capex.
`unified_data_service` reads it on the numbering convention alone and says
so in a comment; the census gives reason to doubt it, because 32100 was
non-zero for 8 of 152 companies in one run and 0 of 144 in the next.

A BCTC gives VAS 21 directly. So: take the consolidated Q4 filing, whose
cash flow is cumulative and therefore covers the full year, and compare it
against VNDIRECT's ANNUAL rows for the same year.

That comparison has three ways to be wrong before it says anything about
32100 - the scope could be mismatched (a parent-only filing against a
consolidated feed), the period could be mismatched (if Q4 turns out not to
be cumulative), or the units could differ. All three would show up as a
disagreement and all three would look like "32100 is not capex".

So the comparison runs a control first. CFO is read from the BCTC at code
20 and from the vendor at 32000, a code the census already established as
non-zero for 153 of 153 companies. If the control disagrees, the scope,
period or unit is wrong and the capex number that run produces means
nothing - the script says so and refuses the verdict rather than reporting
a mismatch it cannot attribute. Only when the control ties is the capex
comparison interpretable.

The control also sets the scale the capex line is judged on, and that
took a wrong answer to get right. The first version compared each side
against a flat 1%, which passed the control at 0.522% and failed capex at
1.037%, printing "32100 is NOT VAS 21" for FPT. The absolute residuals
say the opposite:

    CFO    10,189,002,966,546 vs 10,136,043,915,911   diff 52,959,050,635
    capex  -5,150,805,120,441 vs -5,097,919,349,856   diff 52,885,770,585

The same ~52.9bn arrives twice, the two residuals 0.14% apart from each
other. That is one reconciling item between two sources showing up in
both lines. A code that meant something else could not agree to 98.96%
and then leave the control's own residual behind.

A percentage fixed in advance cannot see that, because it asks each line
to agree with the vendor better than the vendor agrees with the filing.
So the control's residual is the noise floor and capex is read against
it, with three outcomes rather than two: supported when the residual is
within what the control licenses, refuted when the two figures are grossly
apart whatever the control did, and unclear in between. The residuals are
printed next to the verdict so the judgement can be disputed from the log
without paying for another run.

Scope is matched rather than assumed: filings are classified consolidated
or separate from their own file names, and only consolidated ones are put
against the vendor.

What else one pass settles
--------------------------

Every symbol here is a question, not a sample. FPT is the known baseline.
A bank is the form this parser was never written for - credit institutions
file under a different circular and their statements have no code 100 or
270 at all - so it establishes whether the pipeline degrades or lies. The
rest spread across exchange and size, where CafeF's coverage is the thing
in doubt.

Per document the route is reported too. Of the 22 documents in the old
lake, the 9 that took the native vector route produced nothing, and the
spacing fix only touched the OCR pass. If native documents appear here and
still produce nothing, that failure is untouched and separate.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.fetch_one_symbols_filings import (  # noqa: E402
    list_statement_pdfs, report_one_pdf, _fold,
)


def _words(text: str) -> str:
    """Fold a filing's name to spaced words.

    CafeF names files with underscores - `BCTC_cong_ty_me_Quy_4_2025.pdf` -
    so a hint list written with spaces matches nothing and every document
    classifies as unknown, which would send parent-only filings into the
    vendor comparison. This is the same failure as the OCR spacing bug in
    the parser, arriving through a different separator.
    """
    return re.sub(r"[\W_]+", " ", _fold(text)).strip()

# Identities TT200 guarantees. Each is (label, [codes added], [codes
# subtracted], code_that_should_equal_it). They are written from the
# statement forms, not from what the parser happens to produce.
CASH_FLOW_IDENTITIES = [
    ("CFO+CFI+CFF = NCF", [20, 30, 40], [], 50),
    ("opening+NCF+FX = closing", [60, 50, 61], [], 70),
    ("investing lines sum to CFI", [21, 22, 23, 24, 25, 26, 27], [], 30),
    ("financing lines sum to CFF", [31, 32, 33, 34, 35, 36], [], 40),
]

BALANCE_SHEET_IDENTITIES = [
    ("current+non-current = total assets", [100, 200], [], 270),
    ("liabilities+equity = total capital", [300, 400], [], 440),
    ("total assets = total capital", [270], [], 440),
]

INCOME_IDENTITIES = [
    ("revenue-deductions = net revenue", [1], [2], 10),
    ("net revenue-COGS = gross profit", [10], [11], 20),
    ("other income-other cost = other profit", [31], [32], 40),
    ("operating+other = pre-tax profit", [30, 40], [], 50),
    ("pre-tax-tax = post-tax profit", [50], [51, 52], 60),
]

# A dong or two of rounding is not a failure; a misbound row is never this
# close. The tolerance is absolute because these are raw dong, and relative
# because a large statement rounds larger.
ABS_TOLERANCE = 2.0
REL_TOLERANCE = 1e-6

# How much more than the control a single line may disagree and still be
# called the same line. One component can reconcile a little worse than
# the aggregate it sits inside, so this is above 1 - but it is a judgement
# and the raw residuals are printed beside the verdict so it can be
# disputed without rerunning anything.
RESIDUAL_FACTOR = 3.0

# Past this the control is irrelevant: two figures a quarter apart are not
# the same line reconciling, they are different quantities.
GROSS_DISAGREEMENT = 0.25


def _val(items: Dict[Any, Any], code: int, field: str = "current_val") -> Optional[float]:
    """The value at one code, or None when the parser never bound that row."""
    row = items.get(code)
    if row is None:
        row = items.get(str(code))
    if not isinstance(row, dict):
        return None
    v = row.get(field)
    return float(v) if isinstance(v, (int, float)) else None


def check_identities(items: Dict[Any, Any],
                     identities: List[Tuple[str, List[int], List[int], int]],
                     ) -> List[Dict[str, Any]]:
    """Run each identity and say whether it closed, or why it could not.

    An absent component line is treated as zero rather than voiding the
    check, because in these filings a line the parser did not bind is
    usually a line the company did not report - it had no such flow that
    period. Refusing to check would have thrown away the strongest result
    the last run produced: 21+22+23+24+25+27 closes on CFI exactly, and
    code 26 is absent. Requiring 26 turns that into "n/a".

    But zero-filling can only be trusted in one direction, so the outcome
    has three states rather than two:

        ok        it closed. If an absent line were really non-zero the
                  sum could not have closed, so the absence is confirmed
                  and so are the rows that did bind.
        BROKEN    it did not close and every line was present. The parser
                  bound something wrong; no other reading is available.
        unclear   it did not close and some line was absent. The gap may
                  be the missing line or may be a misbinding, and nothing
                  here separates them.

    The target itself is never zero-filled: without it there is no
    identity to check at all.
    """
    out = []
    for label, plus, minus, target in identities:
        got = _val(items, target)
        if got is None:
            out.append({"label": label, "status": "n/a", "missing": [target]})
            continue
        absent = [c for c in plus + minus if _val(items, c) is None]
        lhs = sum(_val(items, c) or 0.0 for c in plus) - sum(
            _val(items, c) or 0.0 for c in minus)
        diff = lhs - got
        closed = abs(diff) <= max(ABS_TOLERANCE, abs(got) * REL_TOLERANCE)
        if closed:
            status = "ok"
        elif absent:
            status = "unclear"
        else:
            status = "BROKEN"
        out.append({"label": label, "status": status, "lhs": lhs,
                    "rhs": got, "diff": diff, "absent": absent})
    return out


CONSOLIDATED_HINTS = ("hop nhat", "hopnhat", "consolidated")

SEPARATE_HINTS = ("cong ty me", "congtyme", "rieng", "separate", " m pdf", " m ")


def classify_scope(title: str) -> str:
    """Consolidated or parent-only, read off the filing's own file name.

    This decides whether a document may be compared with a vendor feed at
    all. A parent-only filing put against a consolidated feed disagrees for
    a reason that has nothing to do with which code means what.
    """
    folded = _words(title)
    if any(h in folded for h in CONSOLIDATED_HINTS):
        return "consolidated"
    if any(h in folded for h in SEPARATE_HINTS):
        return "separate"
    return "unknown"


def classify_period(title: str) -> str:
    """Q1..Q4, annual, or interim - as the file name states it."""
    folded = _words(title)
    for q in (1, 2, 3, 4):
        if f"quy {q}" in folded or f"q{q} " in folded or f"{q}q" in folded:
            return f"Q{q}"
    if "ban nien" in folded or "soat xet" in folded:
        return "H1"
    if "nam" in folded:
        return "FY"
    return "?"


def vendor_rows(symbol: str, report_type: str) -> List[Dict[str, Any]]:
    """VNDIRECT's raw statement rows, or an empty list if it would not say."""
    try:
        from services.stock_service import fetch_vndirect_raw_statements
        return fetch_vndirect_raw_statements(symbol, report_type=report_type,
                                             target_quarters=8) or []
    except Exception as exc:
        print(f"- vendor fetch failed for {symbol}: "
              f"{type(exc).__name__}: {str(exc)[:90]}")
        return []


def vendor_value(rows: List[Dict[str, Any]], item_code: int,
                 year: int) -> Optional[float]:
    """One itemCode for one fiscal year, if the vendor carries it."""
    for r in rows:
        try:
            if int(r.get("itemCode") or 0) != item_code:
                continue
        except (TypeError, ValueError):
            continue
        if str(r.get("fiscalDate") or "").startswith(str(year)):
            v = r.get("numericValue")
            if isinstance(v, (int, float)):
                return float(v)
    return None


def compare_to_vendor(symbol: str, year: int, cf_items: Dict[Any, Any]
                      ) -> Dict[str, Any]:
    """Put the BCTC's own CFO and capex against the vendor's.

    The control runs first and decides whether the capex line is readable
    at all. See the module docstring.
    """
    rows = vendor_rows(symbol, "ANNUAL")
    if not rows:
        return {"verdict": "vendor silent"}

    bctc_cfo = _val(cf_items, 20)
    bctc_capex = _val(cf_items, 21)
    v_cfo = vendor_value(rows, 32000, year)
    out: Dict[str, Any] = {
        "bctc_cfo": bctc_cfo, "vendor_cfo": v_cfo,
        "bctc_capex": bctc_capex,
    }
    for code in (32100, 32110, 32010):
        out[f"vendor_{code}"] = vendor_value(rows, code, year)

    if bctc_cfo is None or v_cfo is None:
        out["verdict"] = "control unavailable - capex comparison not readable"
        return out

    denom = max(abs(bctc_cfo), abs(v_cfo), 1.0)
    control_ok = abs(bctc_cfo - v_cfo) / denom < 0.01
    out["control_ok"] = control_ok
    if not control_ok:
        # Scope, period or unit is off. Whatever capex does here, it cannot
        # be attributed to the numbering, so no verdict is issued.
        out["verdict"] = ("control BROKEN - scope/period/unit mismatch, "
                          "capex comparison withheld")
        return out

    v_capex = out.get("vendor_32100")
    if bctc_capex is None or v_capex is None:
        out["verdict"] = "control ok, but one side has no capex row"
        return out

    # The capex line is judged against what the control licenses, not
    # against a percentage picked in advance. Run 35222930322 is why.
    #
    # There the control was 0.522% apart and capex 1.037% apart, so a flat
    # 1% threshold on each passed the first and failed the second, and the
    # script printed "32100 is NOT VAS 21". The absolute residuals say the
    # opposite: 52,959,050,635 on CFO and 52,885,770,585 on capex, the same
    # ~52.9bn arriving twice, 0.14% apart from each other. Two sources that
    # disagree by one reconciling item look exactly like that. A code that
    # meant something else could not agree to 98.96% and then leave behind
    # the same absolute residual as the control line.
    #
    # So the control sets the noise floor and the capex residual is read
    # against it. Which way that floor scales is not known - source
    # disagreement may be a fixed amount or proportional to the line - so
    # both readings are allowed and the larger wins, rather than assuming
    # the one that happens to be convenient.
    control_abs = abs(bctc_cfo - v_cfo)
    control_rel = control_abs / max(abs(v_cfo), 1.0)
    licensed = max(control_abs, abs(v_capex) * control_rel)
    capex_abs = abs(abs(bctc_capex) - abs(v_capex))
    capex_rel = capex_abs / max(abs(v_capex), 1.0)

    out["control_residual"] = control_abs
    out["capex_residual"] = capex_abs
    out["residual_ratio"] = capex_abs / max(licensed, 1.0)
    out["capex_rel_error"] = capex_rel

    if capex_rel > GROSS_DISAGREEMENT:
        # A quarter of the line apart is not two sources reconciling; it is
        # two different quantities, whatever the control did.
        out["verdict"] = "32100 is NOT VAS 21"
    elif capex_abs <= licensed * RESIDUAL_FACTOR:
        out["verdict"] = "32100 IS VAS 21"
    else:
        # Too close to be a different line, too far for the control to
        # vouch for. Saying which would be inventing a result.
        out["verdict"] = "32100 vs VAS 21 unclear - residual exceeds control"
    out["capex_match"] = out["verdict"].endswith("IS VAS 21")
    return out


def render_identities(name: str, checks: List[Dict[str, Any]]) -> None:
    print(f"| {name} | result | lhs | rhs | diff |")
    print("|---|---|---:|---:|---:|")
    for c in checks:
        if c["status"] == "n/a":
            print(f"| {c['label']} | n/a | | | no code {c['missing']} |")
        else:
            note = f" (absent {c['absent']})" if c.get("absent") else ""
            print(f"| {c['label']} | **{c['status']}**{note} | {c['lhs']:,.0f} | "
                  f"{c['rhs']:,.0f} | {c['diff']:,.0f} |")
    print()


def run_symbol(symbol: str, year: int, limit: int,
               verdicts: List[Dict[str, Any]]) -> None:
    from services.bctc_batch_processor import BCTCBatchProcessor

    print(f"# {symbol}")
    print()
    try:
        pdfs = list_statement_pdfs(symbol, year=year)
    except Exception as exc:
        print(f"- listing failed: {type(exc).__name__}: {str(exc)[:90]}")
        print()
        verdicts.append({"symbol": symbol, "note": "listing failed"})
        return

    print(f"- CafeF lists **{len(pdfs)}** statement PDFs for {year}")
    for p in pdfs[:12]:
        t = p.get("title", "")
        print(f"  - [{classify_scope(t)}/{classify_period(t)}] {t[:78]}")
    print()
    if not pdfs:
        verdicts.append({"symbol": symbol, "note": "no PDFs listed"})
        return

    # Consolidated filings first: they are the only ones the vendor feed can
    # be compared with, and a run that spends its budget on parent-only
    # documents answers the identities but not the vendor question.
    ordered = sorted(pdfs, key=lambda p: 0 if classify_scope(
        p.get("title", "")) == "consolidated" else 1)

    workdir = tempfile.mkdtemp(prefix=f"rec_{symbol}_")
    processor = BCTCBatchProcessor()
    processor.lake_dir = workdir
    done = 0

    for i, row in enumerate(ordered, 1):
        if done >= limit:
            break
        title = row.get("title", "")
        scope, period = classify_scope(title), classify_period(title)
        print(f"## {symbol} - {title[:70]}")
        print(f"- scope **{scope}**, period **{period}**")
        print()
        local = processor.download_report_pdf(symbol, row["pdf_url"],
                                              f"{symbol}_rec_{i}")
        if not local:
            print(f"- download failed: `{row['pdf_url'][-60:]}`")
            print()
            verdicts.append({"symbol": symbol, "scope": scope,
                             "period": period, "note": "download failed"})
            continue

        result = report_one_pdf(local, symbol)
        if result.get("error"):
            print(f"- {result['error']}")
            print()
            continue
        done += 1

        print(f"- route **{result['doc_type']}** | pages {result['pages']} | "
              f"unit {result['currency_unit']} (x{result['currency_scale']:g})")
        counts = {n: (result.get(n) or {}).get("items", 0)
                  for n in ("balance_sheet", "income_statement", "cash_flow")}
        print(f"- items: {counts}")
        print()

        entry: Dict[str, Any] = {"symbol": symbol, "scope": scope,
                                 "period": period, "route": result["doc_type"],
                                 "items": counts}

        # The identities are run over the full extracted item maps, which
        # report_one_pdf truncates for display only.
        from services.bctc_pdf_parser import BCTCPdfParser
        try:
            p = BCTCPdfParser(local, symbol=symbol)
            blocks = {
                "balance_sheet": (p.extract_balance_sheet(), BALANCE_SHEET_IDENTITIES),
                "income_statement": (p.extract_income_statement(), INCOME_IDENTITIES),
                "cash_flow": (p.extract_cash_flow_statement(), CASH_FLOW_IDENTITIES),
            }
        except Exception as exc:
            print(f"- re-parse for identities failed: {str(exc)[:90]}")
            print()
            verdicts.append(entry)
            continue

        cf_items: Dict[Any, Any] = {}
        for name, (block, identities) in blocks.items():
            items = (block or {}).get("items") or {}
            if name == "cash_flow":
                cf_items = items
            checks = check_identities(items, identities)
            render_identities(name, checks)
            entry[f"{name}_ok"] = sum(1 for c in checks if c["status"] == "ok")
            entry[f"{name}_broken"] = sum(1 for c in checks
                                          if c["status"] == "BROKEN")
            entry[f"{name}_unclear"] = sum(1 for c in checks
                                           if c["status"] == "unclear")

        if scope == "consolidated" and period in ("Q4", "FY") and cf_items:
            print(f"### {symbol}: BCTC against VNDIRECT for {year}")
            print()
            cmp_out = compare_to_vendor(symbol, year, cf_items)
            for k, v in cmp_out.items():
                shown = f"{v:,.0f}" if isinstance(v, float) else v
                print(f"- {k}: **{shown}**")
            print()
            entry["vendor"] = cmp_out.get("verdict")
            entry["control_ok"] = cmp_out.get("control_ok")

        verdicts.append(entry)

    import shutil
    shutil.rmtree(workdir, ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", help="comma-separated, e.g. FPT,VCB,VNM")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--limit", type=int, default=1,
                    help="documents parsed per symbol")
    args = ap.parse_args(argv)

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    verdicts: List[Dict[str, Any]] = []
    for s in syms:
        try:
            run_symbol(s, args.year, args.limit, verdicts)
        except Exception as exc:
            print(f"- {s} raised {type(exc).__name__}: {str(exc)[:110]}")
            print()
            verdicts.append({"symbol": s, "note": f"raised {type(exc).__name__}"})

    # The verdict goes last because that is where a long log gets read from.
    print("# Verdict")
    print()
    print("| symbol | scope | period | route | BS ok/bad | IS ok/bad | "
          "CF ok/bad | vendor |")
    print("|---|---|---|---|---|---|---|---|")
    for v in verdicts:
        if v.get("note"):
            print(f"| {v['symbol']} | {v.get('scope','')} | "
                  f"{v.get('period','')} | | | | | {v['note']} |")
            continue
        print(f"| {v['symbol']} | {v.get('scope')} | {v.get('period')} | "
              f"{v.get('route')} | "
              f"{v.get('balance_sheet_ok',0)}/{v.get('balance_sheet_broken',0)} | "
              f"{v.get('income_statement_ok',0)}/{v.get('income_statement_broken',0)} | "
              f"{v.get('cash_flow_ok',0)}/{v.get('cash_flow_broken',0)} | "
              f"{v.get('vendor','')} |")
    print()
    parsed = [v for v in verdicts if not v.get("note")]
    print(f"- parsed **{len(parsed)}** documents across {len(syms)} symbols")
    by_route: Dict[str, int] = {}
    for v in parsed:
        by_route[v.get("route", "?")] = by_route.get(v.get("route", "?"), 0) + 1
    print(f"- by route: {by_route}")
    return 0 if parsed else 1


if __name__ == "__main__":
    raise SystemExit(main())
