#!/usr/bin/env python3
"""Build data/historical_fundamentals.json from real quarterly filings.

The fair-value backtest defaults to ``fundamentals_mode=point_in_time``, which
values a symbol-quarter only when a published filing exists for it. Without
this lake the default mode has nothing to work with, and the alternative
(``snapshot_projected``) reconstructs fundamentals from the price it is meant
to be judging, which makes the whole exercise circular.

Source: VNDIRECT Finfo (``api-finfo.vndirect.com.vn``), the same feed
``services/unified_data_service.py`` already uses, queried per symbol with
``reportType=QUARTER``. Each fiscal date becomes one quarter record.

Item codes follow the VAS chart of accounts and vary by entity form, so each
field lists the codes for non-finance, banking, securities and insurance
filers in that order and takes the first that is present.

Usage
-----
    python scripts/build_historical_fundamentals.py --symbols HPG FPT VCB
    python scripts/build_historical_fundamentals.py --universe --limit 300
    python scripts/build_historical_fundamentals.py --universe --merge

Requires network access. Requests are rate limited through the shared
``vnstock``/``http`` token buckets, so a full universe pass takes a while;
``--merge`` keeps what is already in the lake so the build can be resumed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.point_in_time_fundamentals import (  # noqa: E402
    DEFAULT_PUBLICATION_LAG_DAYS,
    FUNDAMENTALS_LAKE_FILE,
)
from services.unified_data_service import VNDIRECT_ITEM_CODES  # noqa: E402

logger = logging.getLogger("build_historical_fundamentals")

# The item codes are NOT declared here. They live in
# services.unified_data_service.VNDIRECT_ITEM_CODES, and this reads them
# from there.
#
# They used to be declared here, as a copy, and the copy is the reason
# this note is long. Two of those fields were corrected in the service on
# measured evidence and the copy never heard about it:
#
#   cfo   read 31000 and 31100, adjustment lines inside the operating
#         section, where the section total is 32000. The lake would have
#         carried a figure that breaks the statement's own arithmetic -
#         net change = operating + investing + financing held for 99.8%
#         of companies with the total and 3.7% with those lines.
#
#   debt  was derived from total_liabilities, VAS 300 and VAS 310. Trade
#         payables and customer deposits are not borrowings.
#
# So the backtest would have valued a company against quarterly
# fundamentals that disagree with the screener's figures for the same
# company, with nothing in either file to say which was right - and
# because the lake is the point-in-time source, the disagreement would
# have looked like the market being wrong rather than the extractor.
#
# The mapping carries a combining rule per field as well as the codes,
# and honouring it is the point: "first" is a fallback chain, "sum" is
# two lines added. Reading a "sum" field as a chain publishes the first
# half as the whole, which is what borrowings would do - short-term debt
# reported as total debt, smaller than the truth and unremarkable enough
# to survive review.
#: Fields this lake takes from the shared mapping. The service reads
#: more lines than these; a field is listed here because the backtest
#: uses it, not because the vendor has it.
LAKE_FIELDS: Tuple[str, ...] = (
    "revenue", "net_income", "ebit", "cfo", "da", "capex",
    "total_assets", "equity", "debt", "total_liabilities", "cash",
    "gross_ppe",
)

#: The lake's own name for a field where it differs from the service's.
#: Kept explicit rather than renamed silently: "depreciation" is what the
#: backtest reads, and changing that would be a separate change to a
#: separate consumer.
LAKE_FIELD_NAMES: Dict[str, str] = {"da": "depreciation"}

#: Fields whose value is a balance at a date rather than a flow over the
#: quarter. Both are read at the same fiscal date here - the lake stores
#: each quarter as filed - so this exists only to document which is
#: which for anyone summing them later.
STOCK_FIELDS = frozenset({"total_assets", "equity", "debt",
                          "total_liabilities", "cash", "gross_ppe"})


#: Item codes to record alongside the lake so the two unresolved fields
#: can be judged without a second pass over the universe.
#:
#: capex and depreciation are the only lines the extractor reads whose
#: correctness has never been established. capex differs from the other
#: vendor for 70.8% of companies and its first code is near-always zero;
#: depreciation is the one field still missing for a fifth of the lake.
#:
#: The point is NOT to read these into the lake. It is that a filing
#: contains its own arithmetic: capex should move gross fixed assets, and
#: the period's depreciation should move accumulated depreciation. Those
#: deltas are an independent yardstick - independent because they come
#: from the balance sheet, which no cash-flow code we are judging feeds.
#: Scoring a candidate against a figure the same extractor produced is
#: how three measurements today returned a perfect score for nothing.
DIAGNOSTIC_CODES: Dict[str, Tuple[int, ...]] = {
    # Balance-sheet anchors, differenced quarter over quarter.
    "gross_ppe": (12110, 12100),
    "accumulated_depreciation": (12120,),
    # The candidates themselves, each read on its own rather than as a
    # chain, so a code that never answers is visible as a column of nulls
    # instead of hiding behind the one before it.
    "capex_32100": (32100,),
    "capex_32110": (32110,),
    "capex_32010": (32010,),
    "da_31110": (31110,),
    "da_31010": (31010,),
}


def _quarter_code(fiscal_date: str) -> Optional[str]:
    """Maps a fiscal date to the "2021-Q1" code the backtest indexes by."""
    try:
        parsed = datetime.strptime(fiscal_date[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return f"{parsed.year}-Q{(parsed.month - 1) // 3 + 1}"


def _quarter_end(quarter_code: str) -> Optional[date]:
    try:
        year_text, quarter_text = quarter_code.split("-Q")
        year, quarter = int(year_text), int(quarter_text)
    except (ValueError, AttributeError):
        return None
    month = quarter * 3
    last = {3: 31, 6: 30, 9: 30, 12: 31}[month]
    return date(year, month, last)


def _fetch_raw(symbol: str, size: int) -> List[Dict[str, Any]]:
    """Fetches raw statement rows for one symbol, via the app's own client."""
    from services.unified_data_service import _request_with_retry

    url = (
        "https://api-finfo.vndirect.com.vn/v4/financial_statements"
        f"?q=code:{symbol}~reportType:QUARTER&size={size}&sort=fiscalDate:desc"
    )
    response = _request_with_retry(
        "GET", url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=15,
    )
    if response is None:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    return payload.get("data", []) if isinstance(payload, dict) else []


def build_symbol(symbol: str, size: int = 4000,
                 lag_days: int = DEFAULT_PUBLICATION_LAG_DAYS,
                 diagnostics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Returns {quarter_code: record} for one symbol; empty when unavailable.

    When ``diagnostics`` is given, the raw values of DIAGNOSTIC_CODES are
    recorded into it per quarter as well. They are deliberately kept out
    of the lake: they exist to judge two of its fields, and a yardstick
    that lives in the thing it measures stops being one.
    """
    rows = _fetch_raw(symbol.upper().strip(), size)
    if not rows:
        return {}

    # itemCode -> fiscalDate -> value
    by_code: Dict[int, Dict[str, float]] = defaultdict(dict)
    for row in rows:
        fiscal = row.get("fiscalDate")
        value = row.get("numericValue")
        if not fiscal or value is None:
            continue
        try:
            by_code[int(row.get("itemCode", 0))][fiscal] = float(value)
        except (TypeError, ValueError):
            continue

    shares_by_date = by_code.get(52001) or by_code.get(52002) or {}

    quarters: Dict[str, Any] = {}
    fiscal_dates = sorted({r.get("fiscalDate") for r in rows if r.get("fiscalDate")})
    for fiscal in fiscal_dates:
        code = _quarter_code(fiscal)
        if code is None:
            continue

        def read(field: str) -> Optional[float]:
            """One field at this fiscal date, by the shared table's rule.

            The rule is honoured rather than assumed: a "sum" field read
            as a chain would publish its first code as the whole figure.
            An unknown rule raises instead of falling back to chaining,
            because falling back is exactly how that bug would arrive.
            """
            codes, how = VNDIRECT_ITEM_CODES[field]
            values = [by_code.get(code, {}).get(fiscal) for code in codes]
            if how == "sum":
                present = [v for v in values if v is not None]
                return sum(present) if present else None
            if how != "first":
                raise ValueError(f"{field!r}: unknown rule {how!r}")
            for value in values:
                if value is not None:
                    return value
            return None

        record: Dict[str, Any] = {}
        for field in LAKE_FIELDS:
            value = read(field)
            if value is not None:
                record[LAKE_FIELD_NAMES.get(field, field)] = value

        shares = shares_by_date.get(fiscal)
        if shares:
            record["shares_out"] = shares
            if record.get("net_income") is not None:
                record["eps"] = record["net_income"] / shares
            if record.get("equity") is not None:
                record["bvps"] = record["equity"] / shares

        # debt is read from the shared table now, as borrowings. It used
        # to be assigned from total_liabilities here, which is what made
        # the copy above dangerous rather than merely redundant.
        if record.get("cfo") is not None and record.get("capex") is not None:
            record["fcf"] = record["cfo"] - abs(record["capex"])
        if record.get("ebit") is not None and record.get("depreciation") is not None:
            record["ebitda"] = record["ebit"] + abs(record["depreciation"])

        if not record:
            continue

        # VNDIRECT does not expose the filing date on this endpoint. The
        # estimate is NOT written as filing_date, and that is deliberate.
        #
        # PointInTimeFundamentals.publication_date takes a record's
        # filing_date as fact and only falls back to quarter end + its own
        # lag when there is none. Writing an estimate into that field
        # therefore overrides the reader's parameter with a guess it
        # cannot see or vary - the lag becomes frozen into the file, and
        # asking "how much of the backtest's return comes from assuming
        # 45 days?" costs one full rebuild per value tried.
        #
        # So the file states that the date is unknown and says what a
        # reader would have to assume, and the reader keeps the knob.
        # When a real filing date becomes available it belongs in
        # filing_date, and then it should override the lag - because
        # then it is not an assumption.
        record["filing_date_is_estimated"] = True
        record["assumed_publication_lag_days"] = lag_days
        record["fiscal_date"] = fiscal
        quarters[code] = record

        if diagnostics is not None:
            probe = {}
            for name, codes in DIAGNOSTIC_CODES.items():
                for item in codes:
                    value = by_code.get(item, {}).get(fiscal)
                    if value is not None:
                        probe[name] = value
                        break
            if probe:
                diagnostics.setdefault(symbol.upper(), {})[code] = probe

    return quarters


def _universe_symbols(limit: Optional[int]) -> List[str]:
    """The listed equity universe, by the screener's own definition.

    This used to read ALL_SYMBOLS_MAP directly and filter nothing, so
    "--universe" meant every instrument the listing carries - covered
    warrants, ETFs and funds included, some five thousand codes. Most of
    them have no quarterly financial statements at all, so the pass spent
    its time asking a filings endpoint about warrants; the ones that do
    answer are not companies the backtest values.

    So the population comes from load_local_symbols(), which is what the
    screener uses: STOCK on HOSE, HNX or UPCOM, roughly 1,523 codes. The
    two must agree - a lake built over a different population than the
    screener values makes every coverage figure a comparison between two
    different denominators.

    It also removes the VN30 trap. ALL_SYMBOLS_MAP falls back to a
    hardcoded thirty when no listing is on disk; load_local_symbols reads
    the file and returns nothing, so a missing listing is fetched and
    then refused rather than silently valued.
    """
    from scripts.sync_unified_market_data import (
        MIN_PLAUSIBLE_UNIVERSE, load_local_symbols)

    master = load_local_symbols()
    if len(master) < MIN_PLAUSIBLE_UNIVERSE:
        logger.info("only %d equities on hand; fetching the listing...",
                    len(master))
        try:
            from services.stock_service import sync_universe_from_vnstock
            stats = sync_universe_from_vnstock(force=True)
            logger.info("listing sync reports %s symbols",
                        stats.get("total_symbols", 0))
        except Exception as exc:
            import traceback
            logger.warning("listing sync failed: %s: %s",
                           type(exc).__name__, exc)
            traceback.print_exc()
        master = load_local_symbols()
        logger.info("reloaded %d equities", len(master))

    if len(master) < MIN_PLAUSIBLE_UNIVERSE:
        # A thin lake is worse than no lake: it is indistinguishable
        # from a full one once it is a file on disk, and the backtest
        # reads it as the population it had to choose from.
        logger.error("only %d equities available; refusing to build a lake "
                     "that would look like the universe and is not",
                     len(master))
        return []

    symbols = sorted(master)
    logger.info("universe: %d listed equities", len(symbols))
    return symbols[:limit] if limit else symbols


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--symbols", nargs="+", help="Explicit symbols to fetch.")
    source.add_argument("--universe", action="store_true",
                        help="Fetch every symbol in ALL_SYMBOLS_MAP.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the universe pass (useful for a first run).")
    parser.add_argument("--merge", action="store_true",
                        help="Keep existing lake entries; add and overwrite per symbol.")
    parser.add_argument("--lag-days", type=int, default=DEFAULT_PUBLICATION_LAG_DAYS,
                        help="Assumed days from quarter end to publication.")
    parser.add_argument("--out", default=None, help="Output path.")
    parser.add_argument("--diagnostics-out", default=None,
                        help="Also write the code-candidate probe here.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = args.out or os.path.join(base, "data", FUNDAMENTALS_LAKE_FILE)

    lake: Dict[str, Any] = {"symbols": {}}
    if args.merge and os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as handle:
                existing = json.load(handle)
            lake["symbols"] = existing.get("symbols", existing) or {}
            logger.info("merging into %d existing symbols", len(lake["symbols"]))
        except (OSError, ValueError) as exc:
            logger.warning("could not read existing lake (%s); starting fresh", exc)

    symbols = args.symbols or _universe_symbols(args.limit)
    if not symbols:
        logger.error("no symbols to fetch")
        return 1

    diagnostics: Optional[Dict[str, Any]] = (
        {} if args.diagnostics_out else None)

    ok = 0
    for index, symbol in enumerate(symbols, start=1):
        symbol = symbol.upper().strip()
        try:
            quarters = build_symbol(symbol, lag_days=args.lag_days,
                                    diagnostics=diagnostics)
        except Exception as exc:  # one bad symbol must not end the pass
            logger.warning("[%d/%d] %s failed: %s", index, len(symbols), symbol, exc)
            continue
        if not quarters:
            logger.info("[%d/%d] %s: no quarterly statements", index, len(symbols), symbol)
            continue
        lake["symbols"][symbol] = {"quarters": quarters}
        ok += 1
        logger.info("[%d/%d] %s: %d quarters", index, len(symbols), symbol, len(quarters))

    lake["generated_at"] = datetime.now().isoformat(timespec="seconds")
    lake["source"] = "vndirect_finfo_quarterly"
    lake["filing_dates_estimated"] = True
    lake["publication_lag_days"] = args.lag_days

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(lake, handle, ensure_ascii=False)
    os.replace(tmp_path, out_path)

    if diagnostics is not None:
        os.makedirs(os.path.dirname(args.diagnostics_out) or ".", exist_ok=True)
        with open(args.diagnostics_out, "w", encoding="utf-8") as handle:
            json.dump({"codes": {k: list(v) for k, v in
                                 DIAGNOSTIC_CODES.items()},
                       "symbols": diagnostics}, handle, ensure_ascii=False)
        logger.info("wrote %s: %d symbols probed",
                    args.diagnostics_out, len(diagnostics))

    logger.info("wrote %s: %d symbols (%d fetched this pass)",
                out_path, len(lake["symbols"]), ok)
    if ok == 0:
        logger.error("nothing was fetched; the lake is unchanged in substance")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
