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

#: candidate prefix -> the balance-sheet delta it should reproduce
ANCHORS: Dict[str, str] = {
    "capex": "gross_ppe",
    "da": "accumulated_depreciation",
}


def under_judgement(probe: Dict[str, Any]) -> Dict[str, Tuple[str, ...]]:
    """Which columns to judge, read from the probe rather than restated.

    The probe derives its columns from the shared code table, so naming
    them again here would drift the moment that table changed - and the
    drift is silent: this would go on scoring codes the extractor no
    longer reads, and report a winner among them.
    """
    columns = list(probe.get("codes") or {})
    if not columns:
        # An older probe without the header; fall back to whatever the
        # records carry, so the scorer still works on what it is given.
        for quarters in (probe.get("symbols") or {}).values():
            for record in quarters.values():
                columns = list(record)
                break
            break
    out: Dict[str, Tuple[str, ...]] = {}
    for prefix, anchor in ANCHORS.items():
        found = tuple(sorted(c for c in columns
                             if c.startswith(f"{prefix}_")))
        if found:
            out[anchor] = found
    return out

TOLERANCE = 0.25  # a quarter's fixed-asset movement is noisy; be generous

#: Below this, no candidate is named. Leading a field that all fails says
#: nothing about which code is right.
FLOOR = 0.20


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

    for anchor, candidates in under_judgement(probe).items():
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


def _label(column: str, code_names: Dict[str, str]) -> str:
    """The vendor's own name for the code a probe column stands on.

    Columns are named ``field_code`` by the builder's diagnostic probe,
    so the code is the part after the last underscore. A column that is
    not code-shaped, or a code the vendor never labelled, simply has no
    name to show - that is a blank cell, not a guess.
    """
    code = column.rsplit("_", 1)[-1]
    return code_names.get(code, "") if code.isdigit() else ""


def report(results: Dict[str, Any],
           code_names: Optional[Dict[str, str]] = None) -> None:
    """Print the tally, with the vendor's label beside each candidate.

    VNDIRECT sends itemName on every row, so the question this script
    was written to settle by arithmetic - which code is capex - has a
    reading next to it now. When the arithmetic and the label disagree,
    that disagreement is the finding; the label is not authority to
    overrule the identity, and the identity is not reason to ignore a
    label that says the code means something else entirely.
    """
    code_names = code_names or {}
    for anchor, block in results.items():
        print(f"### candidates against d({anchor})")
        print()
        print(f"- consecutive-quarter deltas available: "
              f"**{block['deltas_available']:,}**")
        print()
        print("| code | the vendor calls it | present | non-zero | "
              "matches the delta | rate |")
        print("|---|---|---:|---:|---:|---:|")
        for name, tally in block["candidates"].items():
            rate = (100.0 * tally["held"] / tally["tested"]
                    if tally["tested"] else None)
            label = _label(name, code_names)
            print(f"| {name} | {label or '-'} | {tally['present']:,} | "
                  f"{tally['nonzero']:,} | "
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

        # A floor, because the first real run produced 0.3% and this
        # called it "best". Leading a field that all fails is not
        # evidence for a code; it is evidence against the anchor, or
        # against every candidate. Naming a winner there would have sent
        # the next change chasing the wrong thing.
        if rates[-1] < FLOOR:
            print(f"- **no candidate reproduces d({anchor})** - the best "
                  f"manages {100.0 * rates[-1]:.1f}%, under the "
                  f"{100.0 * FLOOR:.0f}% floor. Either these codes are all "
                  "wrong, or the anchor does not mean what this test "
                  "assumes. Check the anchor before changing the codes - "
                  "and read what the vendor calls each one above, which "
                  "is a direct answer where the arithmetic is not.")
            print()
            continue

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
    code_names = probe.get("code_names") or {}
    report(results, code_names)
    if not code_names:
        print("- the probe carries no vendor labels. Rebuild the lake: the "
              "builder records itemName now, and without it every row above "
              "is arithmetic with nothing to check it against.")
        print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"anchors": results, "code_names": code_names},
                      handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
