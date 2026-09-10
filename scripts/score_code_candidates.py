#!/usr/bin/env python3
"""Judge capex and depreciation codes by the filing's own arithmetic.

The two fields the extractor reads whose correctness has never been
established. capex disagrees with the other vendor for 70.8% of companies
and its first code is near-always zero; depreciation is missing for a
fifth of the lake.

The yardstick is deliberately not another figure this extractor produced.
Three measurements in one day returned a perfect score because they
compared something with itself - a vendor against a copy of its own
number, a code against the witness built from that same code. So the
scoring here uses the balance sheet, which no cash-flow code under
judgement feeds:

    capex        should move gross fixed assets    |capex| ~ d(gross_ppe)
    depreciation should move accumulated depn      |depn|  ~ d(accum_dep)

Both hold only for a company that neither revalued nor disposed of fixed
assets that quarter, so no candidate will score near 100% and one that
does is a reason to distrust the test. What separates a right code from a
wrong one is the gap between them, and a code that is null or zero
everywhere needs no identity to be dismissed.

Reads the probe written by build_historical_fundamentals.py
--diagnostics-out. Fetches nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

#: candidate field -> the balance-sheet delta it should reproduce
UNDER_JUDGEMENT: Dict[str, Tuple[str, ...]] = {
    "gross_ppe": ("capex_32100", "capex_32110", "capex_32010"),
    "accumulated_depreciation": ("da_31110", "da_31010"),
}

TOLERANCE = 0.25  # a quarter's fixed-asset movement is noisy; be generous


def _quarter_order(code: str) -> Tuple[int, int]:
    try:
        year, quarter = code.split("-Q")
        return int(year), int(quarter)
    except (ValueError, AttributeError):
        return (0, 0)


def _consecutive(a: str, b: str) -> bool:
    """True when b is the quarter immediately after a."""
    ya, qa = _quarter_order(a)
    yb, qb = _quarter_order(b)
    if not ya or not yb:
        return False
    return (yb * 4 + qb) - (ya * 4 + qa) == 1


def score(probe: Dict[str, Any]) -> Dict[str, Any]:
    symbols = probe.get("symbols", {})
    results: Dict[str, Any] = {}

    for anchor, candidates in UNDER_JUDGEMENT.items():
        tallies = {name: {"present": 0, "nonzero": 0, "held": 0, "tested": 0}
                   for name in candidates}
        deltas_available = 0

        for _symbol, quarters in symbols.items():
            ordered = sorted(quarters, key=_quarter_order)
            for previous, current in zip(ordered, ordered[1:]):
                if not _consecutive(previous, current):
                    continue
                before = quarters[previous].get(anchor)
                after = quarters[current].get(anchor)
                if before is None or after is None:
                    continue
                delta = after - before
                deltas_available += 1
                for name in candidates:
                    value = quarters[current].get(name)
                    tally = tallies[name]
                    if value is None:
                        continue
                    tally["present"] += 1
                    if abs(value) < 1.0:
                        continue
                    tally["nonzero"] += 1
                    # A negative capex line and a positive asset increase
                    # describe the same event; compare magnitudes.
                    scale = max(abs(delta), abs(value), 1.0)
                    tally["tested"] += 1
                    if abs(abs(value) - abs(delta)) / scale <= TOLERANCE:
                        tally["held"] += 1

        results[anchor] = {"deltas_available": deltas_available,
                           "candidates": tallies}
    return results


def report(results: Dict[str, Any]) -> None:
    for anchor, block in results.items():
        print(f"### candidates against d({anchor})")
        print()
        print(f"- consecutive-quarter deltas available: "
              f"**{block['deltas_available']:,}**")
        print()
        print("| code | present | non-zero | matches the delta | rate |")
        print("|---|---:|---:|---:|---:|")
        for name, tally in block["candidates"].items():
            rate = (100.0 * tally["held"] / tally["tested"]
                    if tally["tested"] else None)
            print(f"| {name} | {tally['present']:,} | {tally['nonzero']:,} | "
                  f"{tally['held']:,}/{tally['tested']:,} | "
                  + (f"{rate:.1f}% |" if rate is not None else "- |"))
        print()

        live = [(n, t) for n, t in block["candidates"].items()
                if t["tested"] and t["nonzero"]]
        if not live:
            print("- every candidate is absent or zero throughout; the "
                  "identity decided nothing and the codes are wrong or the "
                  "line is not filed here.")
            print()
            continue
        best = max(live, key=lambda kv: kv[1]["held"] / max(kv[1]["tested"], 1))
        rates = sorted(t["held"] / max(t["tested"], 1) for _, t in live)
        gap = (rates[-1] - rates[-2]) if len(rates) >= 2 else None
        print(f"- best: **{best[0]}**"
              + (f", ahead of the next by {100.0 * gap:.1f} points"
                 if gap is not None else " (only one candidate answered)"))
        if gap is not None and gap < 0.05:
            print("  The candidates are within five points of each other, "
                  "which does not separate them. Treat this as undecided "
                  "rather than as a ranking.")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", help="JSON written by --diagnostics-out")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    with open(args.probe, "r", encoding="utf-8") as handle:
        probe = json.load(handle)

    if not probe.get("symbols"):
        print("the probe is empty; nothing to score")
        return 1

    print("## Code candidates, judged by the balance sheet")
    print()
    results = score(probe)
    report(results)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
