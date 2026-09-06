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
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.point_in_time_fundamentals import (  # noqa: E402
    DEFAULT_PUBLICATION_LAG_DAYS,
    FUNDAMENTALS_LAKE_FILE,
)

logger = logging.getLogger("build_historical_fundamentals")

# itemCode candidates per output field, in entity-form order:
# non-finance, banking, securities, insurance.
FLOW_CODES: Dict[str, List[int]] = {
    "revenue": [21001, 421900, 21000, 21010],
    "net_income": [23000, 23800, 23001],
    "ebit": [21020, 22000],
    "cfo": [31000, 31100],
    "depreciation": [31110, 31010],
    "capex": [32100, 32110, 32010],
}
STOCK_CODES: Dict[str, List[int]] = {
    "total_assets": [12700, 10000, 11000],
    "equity": [14000, 14100],
    "total_liabilities": [13000, 13100],
    "cash": [11100],
    "gross_ppe": [12110, 12100],
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
                 lag_days: int = DEFAULT_PUBLICATION_LAG_DAYS) -> Dict[str, Any]:
    """Returns {quarter_code: record} for one symbol; empty when unavailable."""
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

        def first(candidates: Iterable[int]) -> Optional[float]:
            for item_code in candidates:
                value = by_code.get(item_code, {}).get(fiscal)
                if value is not None:
                    return value
            return None

        record: Dict[str, Any] = {}
        for field, codes in {**FLOW_CODES, **STOCK_CODES}.items():
            value = first(codes)
            if value is not None:
                record[field] = value

        shares = shares_by_date.get(fiscal)
        if shares:
            record["shares_out"] = shares
            if record.get("net_income") is not None:
                record["eps"] = record["net_income"] / shares
            if record.get("equity") is not None:
                record["bvps"] = record["equity"] / shares

        if record.get("equity") is not None and record.get("total_liabilities") is not None:
            record.setdefault("debt", record["total_liabilities"])
        if record.get("cfo") is not None and record.get("capex") is not None:
            record["fcf"] = record["cfo"] - abs(record["capex"])
        if record.get("ebit") is not None and record.get("depreciation") is not None:
            record["ebitda"] = record["ebit"] + abs(record["depreciation"])

        if not record:
            continue

        # VNDIRECT does not expose the filing date on this endpoint, so record
        # the assumed publication date explicitly rather than letting the
        # reader silently apply a default it cannot see.
        quarter_end = _quarter_end(code)
        if quarter_end is not None:
            record["filing_date"] = (quarter_end + timedelta(days=lag_days)).isoformat()
            record["filing_date_is_estimated"] = True
        record["fiscal_date"] = fiscal
        quarters[code] = record

    return quarters


def _universe_symbols(limit: Optional[int]) -> List[str]:
    from services.stock_service import ALL_SYMBOLS_MAP

    symbols = sorted(ALL_SYMBOLS_MAP.keys()) if ALL_SYMBOLS_MAP else []
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

    ok = 0
    for index, symbol in enumerate(symbols, start=1):
        symbol = symbol.upper().strip()
        try:
            quarters = build_symbol(symbol, lag_days=args.lag_days)
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

    logger.info("wrote %s: %d symbols (%d fetched this pass)",
                out_path, len(lake["symbols"]), ok)
    if ok == 0:
        logger.error("nothing was fetched; the lake is unchanged in substance")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
