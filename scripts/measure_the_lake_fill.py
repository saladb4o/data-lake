#!/usr/bin/env python3
"""How much of the universe the fundamentals lake can answer for.

Why this is a measurement and not an assumption
-----------------------------------------------
The lake was wired into the payload on the argument that it covers a live
fetch that timed out. That argument is plausible and was never tested. It
has two failure modes that look identical from the outside: the lake holds
nothing for the symbol, or it holds quarters that are too few or too
broken to publish - a TTM needs four consecutive quarters and is withheld
otherwise, so a symbol with three quarters contributes balance-sheet
lines and no flows at all.

This walks the screener universe, asks the lake for each symbol exactly
as the live path does, and counts what came back. It fetches nothing.

It is not a coverage measurement. The lake is VNDIRECT read from the same
endpoint the live path uses, so a line missing here is a line the live
fetch would also not have got. What it measures is how much of the payload
the lake could carry if the live fetch failed.
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("measure_the_lake_fill")

#: Bookkeeping the lake attaches alongside the figures. Counting these as
#: filled fields would report a symbol with no usable line as covered.
NOT_A_FIELD = ("latest_fiscal_date", "lake_quarter", "ttm_quarters_used")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    from scripts.audit_valuation_coverage import load_snapshot
    from services import unified_data_service as uds

    path, stocks = load_snapshot(args.snapshot)
    if args.limit:
        stocks = stocks[: args.limit]

    symbols = [str(r.get("symbol") or "").upper()
               for r in stocks if isinstance(r, dict) and r.get("symbol")]

    per_field: "collections.Counter[str]" = collections.Counter()
    quarters: "collections.Counter[str]" = collections.Counter()
    with_any = 0
    with_ttm = 0
    for symbol in symbols:
        lake = uds.load_lake_symbol_data(symbol)
        if not lake:
            continue
        fields = [k for k, v in lake.items()
                  if v is not None and k not in NOT_A_FIELD]
        if not fields:
            continue
        with_any += 1
        per_field.update(fields)
        if any(k.endswith("_ttm") for k in fields):
            with_ttm += 1
        if lake.get("lake_quarter"):
            quarters[str(lake["lake_quarter"])] += 1

    total = len(symbols)

    def pct(n: int) -> str:
        return f"{(100.0 * n / total):.1f}%" if total else "n/a"

    print("## What the lake could answer for")
    print()
    print(f"- universe read from `{os.path.basename(path)}`: {total:,} symbols")
    print(f"- lake returns at least one line: **{with_any:,}** ({pct(with_any)})")
    # Stated separately because the two are bought at very different
    # prices: a balance-sheet line needs one quarter, a TTM flow needs
    # four consecutive ones, and a lake that is wide but shallow fills
    # the first and none of the second.
    print(f"- of those, carrying TTM flows: **{with_ttm:,}** "
          f"({pct(with_ttm)} of the universe)")
    print()
    if per_field:
        print("| field | symbols the lake could fill |")
        print("|---|---:|")
        for field, count in sorted(per_field.items(),
                                   key=lambda kv: (-kv[1], kv[0])):
            print(f"| {field} | {count:,} |")
        print()
    if quarters:
        print("| newest quarter in the lake | symbols |")
        print("|---|---:|")
        for quarter, count in sorted(quarters.items(), reverse=True)[:8]:
            print(f"| {quarter} | {count:,} |")
        print()
    if with_any == 0:
        print("- **the lake filled nothing.** Either it is not where the "
              "resolver looks, or every symbol in it is outside the "
              "universe. Read no conclusion about resilience from a run "
              "that could not read the file.")
        print()

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        payload: Dict[str, Any] = {
            "universe": total,
            "symbols_with_any_line": with_any,
            "symbols_with_ttm": with_ttm,
            "per_field": dict(per_field),
            "newest_quarter": dict(quarters),
        }
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
