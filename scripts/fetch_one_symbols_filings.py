"""One symbol, its latest filings, and what the parser actually got out.

The BCTC pipeline has existed for a long time and has never been measured
on a document it fetched itself. What exists is `extracted_bctc_lake.json`,
104 MB, built on someone's Windows machine - every `local_path` in it
starts `C:\\Users\\Admin\\` - and carried here as a result with its inputs
left behind. Reading it settles nothing about whether the fetch works.

It also settles less than it appears to. The audit over that file reports
"0.4% usable" by dividing by its 1,769 records, but only 22 of those are
documents: the other 1,747 are catalogue rows, one per symbol, listing
which filings exist. They were never PDFs, so they are not 1,747 failures
and the denominator is wrong. On the 22 documents actually parsed the
split is the interesting part, and it is the opposite of the obvious
guess:

    SCANNED_IMAGE   13 documents    7 produced statements
    NATIVE           9 documents    0 produced statements

The OCR route - slow, hard, image-only - works. The native vector route,
which should be the easy one, produced nothing on nine attempts. That
reads as a bug rather than a limit, and it is worth knowing before any
feature is built on top of either.

So this script does the smallest thing that can produce evidence: take one
symbol, ask CafeF what it has filed, download the most recent filings that
look like financial statements, parse each, and print what came back -
which route ran, what the parser found, and where it stopped. On demand,
one symbol, no lake.

It prints two things nothing else here prints.

The first is the route each document took and what that route returned,
so the NATIVE result above is either reproduced on fresh documents or
contradicted by them.

The second is every accounting code the parser bound to a Vietnamese
label in the cash flow statement. VNDIRECT sends eight keys per statement
row and not one is a label, which is why `capex` is read from item code
32100 on the VAS numbering convention alone, why it has scored 0.3%
against its anchor for three runs, and why Vietcap was asked to name it
and answered for 0 of 200 symbols. A BCTC prints the code and the label
in adjacent columns. If these documents parse, the witness that has been
missing all along is in them.

What the runs have settled
--------------------------

CafeF answers from a runner - it is only the dev container that is refused
- so the question can be asked. The answer is that this endpoint does not
carry financial statements. Twenty pages for FPT returned 600 items over
four years; nine mentioned BCTC and every one of the nine was a document
*about* a statement: an audit engagement, a board resolution naming the
auditor, a memo explaining a profit variance (run 34644785546).

The Type parameter, which looked like the way to reach a different feed,
is decorative. Seven ids returned byte-identical results - 150 items, the
same three mentions, the same two titles (run 35218315632). There is one
feed here and it is news.

That reaches further than this script. REPORT_TYPE_RULES in stock_service
classifies a disclosure as "bctc" if its title contains "kiem toan" or
"giai trinh chenh lech", so those nine FPT announcements appear in the
app's Bao Cao Tai Chinh tab, badged as statements, each with a real PDF
behind it from the detail page. The tab is populated, the PDFs open, and
nothing in the interface says the statements are missing. The batch
processor filters the same way, downloads the same documents, and hands
them to a parser that then finds no balance sheet in an audit contract.

So the 0-of-9 NATIVE result may not be a parser bug at all: the parser may
have been reading documents that contain no financial statements. That is
not yet proven - proving it needs one real BCTC, and no run has obtained
one.

Usage
-----
    python scripts/fetch_one_symbols_filings.py FPT
    python scripts/fetch_one_symbols_filings.py VNM --limit 5 --keep
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("fetch_one_symbols_filings")

#: Title words that mean a disclosure is not a financial statement. Taken
#: from the batch processor rather than rewritten, so both agree on what a
#: BCTC is; a second list would drift from the first without either being
#: wrong on its own.
from services.bctc_batch_processor import BCTC_NEGATIVE_KEYWORDS  # noqa: E402

#: Title words that mean it probably is one. The negative list alone
#: leaves through every announcement that simply avoids those words, and
#: on a page of thirty disclosures most are not statements.
BCTC_POSITIVE_KEYWORDS = (
    "bao cao tai chinh", "báo cáo tài chính", "bctc",
    "bao cao soat xet", "báo cáo soát xét",
    "financial statement", "financial statements",
)


def _fold(text: str) -> str:
    """Accent-insensitive lowercase, for matching titles written either way."""
    from services.bctc_pdf_parser import strip_accents
    return strip_accents(str(text or "")).lower()


def looks_like_a_statement(title: str) -> bool:
    folded = _fold(title)
    if any(_fold(word) in folded for word in BCTC_NEGATIVE_KEYWORDS):
        return False
    return any(_fold(word) in folded for word in BCTC_POSITIVE_KEYWORDS)


#: Title shapes that are a statement itself rather than a document about
#: one. Run 34644785546 is the reason this is separate from the keyword
#: list: nine FPT titles said "BCTC" and all nine were audit engagements,
#: board resolutions and variance memos.
#:
#: Run 35218315632 then caught this list making the same mistake it was
#: written to catch. "bctc nam" matched "ky hop dong voi don vi kiem toan
#: BCTC nam 2026", so it reported two statements where there were none -
#: two for two wrong. A title that announces an engagement, a resolution
#: or an explanation is about a statement whoever wrote it, so those words
#: now disqualify a title outright.
REAL_STATEMENT_DISQUALIFIERS = (
    "hop dong", "ky ket", "ky hop dong", "lua chon", "nghi quyet",
    "giai trinh", "thong bao ve viec", "quyet dinh",
)

REAL_STATEMENT_HINTS = (
    "bao cao tai chinh quy", "bctc quy", "bao cao tai chinh nam",
    "bctc nam", "bao cao tai chinh hop nhat", "bctc hop nhat",
    "bao cao tai chinh rieng", "bao cao tai chinh da duoc kiem toan",
    "bao cao tai chinh ban nien", "bao cao soat xet",
)


def looks_like_the_statement_itself(title: str) -> bool:
    folded = _fold(title)
    if any(_fold(w) in folded for w in REAL_STATEMENT_DISQUALIFIERS):
        return False
    return any(_fold(h) in folded for h in REAL_STATEMENT_HINTS)


def probe_feeds(symbol: str, pages: int, type_ids) -> int:
    """Ask each of CafeF's feeds what it carries, and count filings in it.

    Type=2 is the only feed this repo has ever read, and it does not carry
    statements. Whether any other does is not knowable from here - CafeF is
    refused by the dev container - and guessing has been expensive. So each
    id is asked the same question and the answers are printed side by side.
    """
    from services.stock_service import _fetch_cafef_single_page_raw

    print("| Type | items | say 'BCTC' | ARE a statement |")
    print("|---:|---:|---:|---:|")
    found: Dict[int, List[Dict[str, Any]]] = {}
    for type_id in type_ids:
        rows: List[Dict[str, Any]] = []
        for page in range(1, pages + 1):
            try:
                batch = _fetch_cafef_single_page_raw(symbol, page, type_id=type_id)
            except Exception as exc:
                print(f"| {type_id} | fetch failed: {str(exc)[:40]} | | |")
                rows = []
                break
            if not batch:
                break
            rows.extend(batch)
        mentions = [r for r in rows if "bctc" in _fold(r.get("title", ""))
                    or "bao cao tai chinh" in _fold(r.get("title", ""))]
        real = [r for r in rows if looks_like_the_statement_itself(r.get("title", ""))]
        found[type_id] = real
        print(f"| {type_id} | {len(rows)} | {len(mentions)} | **{len(real)}** |")
    print()

    for type_id, real in found.items():
        if not real:
            continue
        print(f"Type {type_id} - titles that look like the statement itself:")
        print()
        for row in real[:8]:
            print(f"  - {str(row.get('title',''))[:90]}  ({row.get('date','')})")
        print()

    if not any(found.values()):
        print("- **No feed carries statements.** Every id returned either "
              "nothing or the same news. CafeF's disclosure list is then not "
              "reachable through this endpoint at all, and the PDF route has "
              "to find the documents somewhere else or be abandoned.")
        return 1
    return 0


def list_filings(symbol: str, pages: int = 20) -> List[Dict[str, Any]]:
    """Every disclosure CafeF lists for this symbol, newest first."""
    from services.stock_service import _fetch_cafef_single_page_raw

    rows: List[Dict[str, Any]] = []
    for page in range(1, pages + 1):
        try:
            batch = _fetch_cafef_single_page_raw(symbol, page)
        except Exception as exc:
            print(f"  page {page} failed: {exc}")
            continue
        if not batch:
            break
        rows.extend(batch)
    return rows


def report_one_pdf(path: str, symbol: str) -> Dict[str, Any]:
    """Parse one downloaded PDF and say what came out of it."""
    from services.bctc_pdf_parser import BCTCPdfParser

    out: Dict[str, Any] = {"path": path, "size": os.path.getsize(path)}
    try:
        parser = BCTCPdfParser(path, symbol=symbol)
    except Exception as exc:
        out["error"] = f"could not open: {exc}"
        return out

    out["doc_type"] = parser.doc_type
    out["pages"] = parser.total_pages
    out["currency_unit"] = parser.currency_unit
    out["currency_scale"] = parser.currency_scale

    for name, method in (("balance_sheet", "extract_balance_sheet"),
                         ("income_statement", "extract_income_statement"),
                         ("cash_flow", "extract_cash_flow_statement")):
        try:
            block = getattr(parser, method)()
        except Exception as exc:
            out[name] = {"error": str(exc)[:120]}
            continue
        items = (block or {}).get("items") or {}
        out[name] = {"items": len(items), "sample": dict(list(items.items())[:4])}
        if name == "cash_flow":
            # The whole reason for this script: code and label together.
            out["cash_flow_codes"] = dict(list(items.items())[:40])
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--limit", type=int, default=3,
                    help="how many of the newest statement filings to parse")
    ap.add_argument("--pages", type=int, default=20,
                    help="pages of CafeF disclosures to scan")
    ap.add_argument("--probe-types", default="",
                    help="comma-separated CafeF feed ids to survey instead of "
                         "parsing, e.g. 0,1,2,3,4,5")
    ap.add_argument("--keep", action="store_true",
                    help="keep the downloaded PDFs instead of deleting them")
    args = ap.parse_args(argv)

    symbol = args.symbol.upper().strip()
    print(f"# Filings for {symbol}, fetched on demand")
    print()

    if args.probe_types:
        ids = [int(x) for x in args.probe_types.replace(" ", "").split(",") if x != ""]
        print(f"Surveying CafeF feeds {ids}, {args.pages} page(s) each.")
        print()
        return probe_feeds(symbol, args.pages, ids)

    rows = list_filings(symbol, pages=args.pages)
    print(f"- CafeF listed **{len(rows)}** disclosures across {args.pages} page(s)")
    if not rows:
        print()
        print("- **CafeF returned nothing.** That is a fact about the fetch, "
              "not about the company: every symbol has filings. Read it as "
              "the endpoint or the parse of its HTML being wrong.")
        return 1

    statements = [r for r in rows if looks_like_a_statement(r.get("title", ""))]
    print(f"- of those, **{len(statements)}** look like financial statements")
    print()
    print("| # | title | date |")
    print("|---|---|---|")
    for i, row in enumerate(statements[:10], 1):
        title = str(row.get("title", ""))[:70]
        print(f"| {i} | {title} | {row.get('date', '')} |")
    print()

    if not statements:
        # Two different failures look identical here, so they are separated
        # before either is blamed. Either the feed carries statements and the
        # keyword lists rejected them, or the feed carries none at all - it
        # is Type=2, "related news", and on run 34643960323 two pages of it
        # for FPT were thirty news headlines and not one filing.
        print("- **No disclosure matched.** Which of the two it is:")
        print()
        print("| probe | titles containing it |")
        print("|---|---:|")
        for probe in ("tai chinh", "bctc", "kiem toan", "soat xet",
                      "quy ", "nam 202", "giai trinh", "bao cao"):
            hits = sum(1 for r in rows if probe in _fold(r.get("title", "")))
            print(f"| {probe} | {hits} |")
        print()
        rejected = [r for r in rows
                    if any(_fold(w) in _fold(r.get("title", ""))
                           for w in BCTC_POSITIVE_KEYWORDS)]
        print(f"- **{len(rejected)}** titles matched a positive keyword and were "
              "then rejected by the negative list")
        for row in rejected[:10]:
            print(f"  - {str(row.get('title',''))[:90]}")
        print()
        print("- a sample of what the feed did return:")
        for row in rows[:10]:
            print(f"  - {str(row.get('title',''))[:90]}")
        return 1

    from services.bctc_batch_processor import BCTCBatchProcessor
    from services.stock_service import fetch_single_detail_pdf

    workdir = tempfile.mkdtemp(prefix=f"bctc_{symbol}_")
    processor = BCTCBatchProcessor()
    processor.lake_dir = workdir

    parsed = 0
    for i, row in enumerate(statements[:args.limit], 1):
        title = str(row.get("title", ""))[:70]
        print(f"## {i}. {title}")
        print()

        pdf_url = row.get("pdf_url") or ""
        if not pdf_url:
            detail = row.get("detail_url") or row.get("url") or ""
            pdf_url = fetch_single_detail_pdf(detail) if detail else ""
        if not pdf_url:
            print("- no PDF link on the detail page; skipped")
            print()
            continue

        local = processor.download_report_pdf(symbol, pdf_url, f"{symbol}_ondemand_{i}")
        if not local:
            print(f"- download failed for `{pdf_url[:80]}`")
            print()
            continue

        result = report_one_pdf(local, symbol)
        if result.get("error"):
            print(f"- {result['error']}")
            print()
            continue

        parsed += 1
        print(f"- route: **{result['doc_type']}** | pages {result['pages']} | "
              f"unit {result['currency_unit']} (x{result['currency_scale']:g}) | "
              f"{result['size']:,} bytes")
        print()
        print("| statement | items extracted |")
        print("|---|---:|")
        for name in ("balance_sheet", "income_statement", "cash_flow"):
            block = result.get(name) or {}
            if "error" in block:
                print(f"| {name} | error: {block['error'][:50]} |")
            else:
                print(f"| {name} | {block.get('items', 0)} |")
        print()

        codes = result.get("cash_flow_codes") or {}
        if codes:
            # A code next to the label the company printed for it. This is
            # the thing VNDIRECT does not send and Vietcap did not answer.
            print("Cash flow codes bound to labels:")
            print()
            print("| code | value |")
            print("|---|---:|")
            for code, value in list(codes.items())[:25]:
                print(f"| {code} | {value} |")
            print()

    print(f"- parsed **{parsed}** of {min(args.limit, len(statements))} attempted")
    if not args.keep:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    else:
        print(f"- PDFs kept in `{workdir}`")
    return 0 if parsed else 1


if __name__ == "__main__":
    raise SystemExit(main())
