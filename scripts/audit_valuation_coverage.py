#!/usr/bin/env python3
"""Reports how much of your universe the valuation engine can actually value.

The engine now refuses to value a symbol whose fundamentals were back-solved
from its own market capitalisation, because a fair value derived that way is a
fixed multiple of the price it is supposed to judge. That is the right answer,
but it raises a fair question: how many symbols does it leave with no result?

This answers it from your own screener snapshot rather than in the abstract.
It reads no network and writes nothing. For each symbol it reports the
provenance tier of the inputs, whether the engine produces a valuation, and
when it does not, which drivers were missing or imputed.

    python scripts/audit_valuation_coverage.py
    python scripts/audit_valuation_coverage.py --limit 100 --show-blocked 20
    python scripts/audit_valuation_coverage.py --json coverage.json

Tier meanings, as emitted by services/unified_data_service.py:

    4  audited primary filing (BCTC ground truth)
    3  vendor reported (VNDIRECT / TradingView / TCBS)
    2  triangulated from other reported lines (assets - liabilities)
    1  sector-median stand-in, back-solved from market cap
    0  fabricated / discarded

Tier 2 and above is evidence and is valued. Tier 1 and below is not, and is
refused. If this report says most of your universe is tier 1, the fix is to
populate the fundamentals lake, not to loosen the gate - loosening it does not
create information, it only hides that there is none.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("audit_valuation_coverage")

TRUSTED_TIER = 2
TIER_LABELS = {
    4: "audited filing",
    3: "vendor reported",
    2: "triangulated",
    1: "sector stand-in",
    0: "fabricated",
}


def load_snapshot(path: Optional[str]) -> Tuple[str, List[Dict[str, Any]]]:
    from services.unified_data_service import screener_snapshot_file

    resolved = path or screener_snapshot_file()
    if not os.path.exists(resolved):
        raise SystemExit(
            f"No screener snapshot at {resolved}.\n"
            "Run the universe sync first, or pass --snapshot with the path."
        )
    with open(resolved, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    stocks = payload.get("stocks") if isinstance(payload, dict) else payload
    if isinstance(stocks, dict):
        stocks = list(stocks.values())
    if not isinstance(stocks, list):
        raise SystemExit(f"{resolved} does not contain a list of stocks")
    return resolved, stocks


def worst_tier(record: Dict[str, Any]) -> Optional[int]:
    """The lowest provenance tier among the record's valuation drivers."""
    tiers = record.get("field_provenance")
    if not isinstance(tiers, dict) or not tiers:
        return None
    numeric = [
        int(v) for v in tiers.values()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    return min(numeric) if numeric else None


def evaluate(record: Dict[str, Any]) -> Dict[str, Any]:
    from services.valuation_engine import ValuationEngine

    engine = ValuationEngine()
    symbol = str(record.get("symbol") or record.get("ticker") or "?")
    row: Dict[str, Any] = {
        "symbol": symbol,
        "worst_tier": worst_tier(record),
        "active_models": 0,
        "fair_value": 0.0,
        "blocked_by": [],
        "error": None,
    }
    try:
        models = engine.calculate_all_models(symbol, record)
        row["fair_value"] = engine.calculate_composite_fair_value(
            models, str(record.get("sector_code") or "DEFAULT")
        )
        row["active_models"] = sum(1 for m in models if m.active)
        blocked = collections.Counter()
        for model in models:
            for driver in (model.diagnostics or {}).get("imputed_drivers", []):
                blocked[driver] += 1
        row["blocked_by"] = [d for d, _ in blocked.most_common(5)]
    except Exception as exc:  # a refusal to value is a result, not a crash
        row["error"] = f"{type(exc).__name__}: {exc}"
        logger.debug("%s could not be evaluated", symbol, exc_info=True)
    return row


def report(rows: List[Dict[str, Any]], show_blocked: int) -> None:
    total = len(rows)
    valued = [r for r in rows if r["active_models"] > 0]
    refused = [r for r in rows if r["active_models"] == 0 and not r["error"]]
    errored = [r for r in rows if r["error"]]

    def pct(n: int) -> str:
        return f"{(100.0 * n / total):5.1f}%" if total else "  n/a"

    print(f"\nUniverse: {total} symbols\n")
    print(f"  valued        {len(valued):>6}  {pct(len(valued))}   at least one model produced a fair value")
    print(f"  refused       {len(refused):>6}  {pct(len(refused))}   no driver survived the provenance gate")
    print(f"  errored       {len(errored):>6}  {pct(len(errored))}   could not be evaluated at all")

    tiers = collections.Counter(r["worst_tier"] for r in rows)
    print("\nWeakest driver tier per symbol:")
    for tier in (4, 3, 2, 1, 0):
        count = tiers.get(tier, 0)
        if not count:
            continue
        gate = "valued" if tier >= TRUSTED_TIER else "REFUSED"
        print(f"  tier {tier} {TIER_LABELS[tier]:<16} {count:>6}  {pct(count)}   {gate}")
    if tiers.get(None):
        print(f"  no provenance metadata     {tiers[None]:>6}  {pct(tiers[None])}   valued (nothing says otherwise)")

    if valued:
        counts = sorted(r["active_models"] for r in valued)
        mid = counts[len(counts) // 2]
        print(f"\nActive models among valued symbols: median {mid}, max {max(counts)} of 22")
        print("(Each sector allows only 5-6 of the 22 models by design, so 5-6 is a full house.)")

    drivers = collections.Counter()
    for row in rows:
        for driver in row["blocked_by"]:
            drivers[driver] += 1
    if drivers:
        print("\nMost common blocking drivers:")
        for driver, count in drivers.most_common(12):
            print(f"  {driver:<28} {count:>6} symbols")

    if refused and show_blocked:
        print(f"\nFirst {min(show_blocked, len(refused))} refused symbols:")
        for row in refused[:show_blocked]:
            tier = row["worst_tier"]
            label = TIER_LABELS.get(tier, "no metadata") if tier is not None else "no metadata"
            print(f"  {row['symbol']:<8} tier {tier}  {label:<16} blocked by {row['blocked_by'] or '-'}")

    if errored and show_blocked:
        print(f"\nFirst {min(show_blocked, len(errored))} errors:")
        for row in errored[:show_blocked]:
            print(f"  {row['symbol']:<8} {row['error']}")

    print()
    if total and len(valued) / total < 0.25:
        print(
            "Most of the universe is refused. That is the data saying it was\n"
            "reconstructed from price, not the gate being wrong.\n"
            "\n"
            "Check in this order:\n"
            "  1. Is the snapshot stale? The absolute statement lines (debt,\n"
            "     cash, ebit, equity, revenue) are only published by recent\n"
            "     builds. A snapshot written before that carries ratios alone\n"
            "     and every per-share model will refuse. Re-run the universe\n"
            "     sync and audit again before concluding anything.\n"
            "  2. Do the vendor feeds actually return the balance sheet? If\n"
            "     the weakest tier is 1 across the board, TradingView and\n"
            "     VNDIRECT returned nothing for those lines and the fix is\n"
            "     the feed, not the engine.\n"
            "\n"
            "Note: scripts/build_historical_fundamentals.py fills the\n"
            "point-in-time lake used by the backtest and the sector-weight\n"
            "calibration. It is NOT read by the live screener path, so it\n"
            "will not move the numbers in this report.\n"
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--snapshot", help="Path to screener_snapshot.json")
    parser.add_argument("--limit", type=int, help="Only audit the first N symbols")
    parser.add_argument("--show-blocked", type=int, default=10,
                        help="How many refused symbols to list (default 10)")
    parser.add_argument("--json", dest="json_out", help="Also write the per-symbol rows here")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    path, stocks = load_snapshot(args.snapshot)
    if args.limit:
        stocks = stocks[: args.limit]
    print(f"Reading {path}")

    rows = [evaluate(record) for record in stocks if isinstance(record, dict)]
    report(rows, args.show_blocked)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
        print(f"Per-symbol rows written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
