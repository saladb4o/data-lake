#!/usr/bin/env python3
"""Four questions about data already on disk. Fetches nothing.

Each of these has been answered by guessing at least once, and guessing
is what the last several runs were spent unlearning. They are grouped
into one script because they share the two files a completed measurement
pass already publishes - the screener snapshot and the price lake - so
asking all four costs the same as asking one.

1. Is the price lake on the same scale as the screener?
   `discount_to_fv_pct` compares the lake price *absolutely* against a
   fair value built from VND fundamentals, so a source quoting thousands
   reads as a 99.9% discount on every symbol rather than as an error.
   Nothing in the code checks; `compute_stock_quarterly_returns` used to
   claim it did.

2. Are the prices adjusted for splits and bonus issues?
   An unadjusted series shows a company halving in value the day its
   shares double in number. The lake stores quarters, not sessions, so
   this can only be coarse - but a split still leaves a quarter return
   sitting on -50%, -66% or -75% far more often than chance.

3. `fcf` blocks 141 symbols. It is derived as cfo - |capex| and imputed
   as cfo * 0.7. This entry used to say it could therefore only be
   missing when *cfo* is missing; the first run of the section showed
   cfo present at tier 3 for 1,514 of 1,524 symbols while capex sits
   below the gate for 193, and the impute is itself below the gate. So
   capex is what blocks it, and the answer arrived by contradicting the
   question.

4. Four symbols are short of exactly one core driver, revenue. The audit
   says those are "the ones a single extractor fix can reach" and has
   never named them.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Ratios a split or bonus issue leaves behind, as the quarter return it
#: would produce if the series were never adjusted. 1:2 halves the price,
#: 1:3 cuts it to a third, and so on.
SPLIT_RETURNS = {"1:2 (-50%)": -50.0, "2:3 (-33%)": -33.3,
                 "1:3 (-67%)": -66.7, "1:4 (-75%)": -75.0,
                 "1:5 (-80%)": -80.0}
#: How close a quarter return has to sit to one of those to be counted.
#: Wide enough to survive ordinary drift inside the quarter, narrow
#: enough that an ordinary bad quarter does not land in it by accident.
SPLIT_TOLERANCE = 2.5


def _f(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def section_scale(stocks, lake) -> bool:
    """True when the lake and the screener agree on a scale."""
    print("## 1. Is the price lake on the screener's scale?")
    print()
    ratios, missing, zero = [], 0, 0
    for rec in stocks:
        sym = str(rec.get("symbol") or "").upper()
        entry = lake.get(sym) or {}
        quarters = entry.get("quarters") or {}
        if not quarters:
            missing += 1
            continue
        latest = quarters[sorted(quarters)[-1]]
        lake_close = _f(latest.get("close_price"))
        snap = _f(rec.get("price"))
        if not lake_close or not snap:
            zero += 1
            continue
        ratios.append((snap / lake_close, sym, snap, lake_close))

    print(f"- symbols compared: **{len(ratios)}** "
          f"(no lake entry: {missing}; a price missing or zero: {zero})")
    if not ratios:
        print("\n- nothing to compare.\n")
        return True

    # Buckets, not a mean: one symbol off by a thousand would drag an
    # average into a range no symbol actually occupies, and the whole
    # question is whether the population sits on one scale or two.
    buckets = collections.Counter()
    for ratio, *_ in ratios:
        if ratio < 0.01:
            buckets["lake is >100x the screener"] += 1
        elif ratio < 0.5:
            buckets["lake is 2x-100x the screener"] += 1
        elif ratio <= 2.0:
            buckets["same scale (0.5x - 2x)"] += 1
        elif ratio <= 100.0:
            buckets["screener is 2x-100x the lake"] += 1
        else:
            buckets["screener is >100x the lake"] += 1
    print()
    print("| screener price / lake close | symbols |")
    print("|---|---:|")
    for name, count in buckets.most_common():
        print(f"| {name} | {count:,} |")
    print()

    ordered = sorted(ratios)
    mid = ordered[len(ordered) // 2]
    print(f"- median ratio **{mid[0]:.3f}** ({mid[1]}: screener "
          f"{mid[2]:,.0f} vs lake {mid[3]:,.2f})")
    # The screener falls back to a hardcoded 10,000 when no vendor gives
    # it a price, so a cluster of exactly that is a fabricated price
    # rather than a scale problem, and would otherwise be read as one.
    flat = sum(1 for _, _, snap, _ in ratios if abs(snap - 10000.0) < 0.5)
    print(f"- screener price is exactly 10,000 (its no-vendor fallback) "
          f"for **{flat}** of them")
    worst = sorted(ratios, key=lambda r: -abs(1.0 - r[0]))[:12]
    print()
    print("| symbol | screener | lake close | ratio |")
    print("|---|---:|---:|---:|")
    for ratio, sym, snap, close in worst:
        print(f"| {sym} | {snap:,.0f} | {close:,.2f} | {ratio:.4f} |")
    print()

    # The verdict, and it is a gate rather than a note. A price on the
    # wrong scale does not announce itself anywhere downstream: the
    # backtest still runs, still prints a return, and simply stops using
    # the filings. Run 34605559771 found every one of 1,367 symbols off
    # by ~941 and nothing in the repository had noticed.
    #
    # Judged on the population, not on outliers: a genuinely mispriced
    # symbol is a data point, a whole lake an order of magnitude out is
    # a unit error. A tenth of the universe is far past either.
    off = sum(count for name, count in buckets.items()
              if not name.startswith("same scale"))
    share = off / len(ratios)
    if share > 0.10:
        print(f"- **The lake is not on the screener's scale.** "
              f"{off:,} of {len(ratios):,} symbols ({share:.1%}) sit more "
              f"than a factor of two away, median ratio {mid[0]:.3f}. "
              "Prices are compared absolutely against a fair value built "
              "from dong fundamentals, so this is not cosmetic: it reads "
              "as a ~100% discount on every symbol and the eps/bvps "
              "floors win against every real figure.")
        print()
        return False
    print(f"- Lake and screener agree on a scale: "
          f"{len(ratios) - off:,} of {len(ratios):,} within a factor of two.")
    print()
    return True


def section_splits(lake) -> None:
    print("## 2. Are the prices adjusted for splits?")
    print()
    total_q, hits = 0, collections.Counter()
    examples = collections.defaultdict(list)
    for sym, entry in lake.items():
        for code, rec in sorted((entry.get("quarters") or {}).items()):
            ret = _f(rec.get("return_pct"))
            if ret is None:
                continue
            total_q += 1
            for name, target in SPLIT_RETURNS.items():
                if abs(ret - target) <= SPLIT_TOLERANCE:
                    hits[name] += 1
                    if len(examples[name]) < 6:
                        examples[name].append(f"{sym} {code} {ret:.1f}%")
                    break

    print(f"- quarter returns examined: **{total_q:,}**")
    print()
    print("| would be left by | quarters within "
          f"{SPLIT_TOLERANCE:.1f} points | examples |")
    print("|---|---:|---|")
    for name in SPLIT_RETURNS:
        print(f"| {name} | {hits.get(name, 0):,} | "
              f"{', '.join(examples.get(name, [])) or '-'} |")
    print()
    # A quarter is three months of trading, so a drop of exactly this
    # size can be an ordinary collapse. The reading is in the ratio: if
    # the series were adjusted these bands would hold roughly what any
    # other 5-point band holds, and if it were not they hold far more.
    band = sum(1 for entry in lake.values()
               for rec in (entry.get("quarters") or {}).values()
               if (_f(rec.get("return_pct")) or 0.0) <= -20.0
               and (_f(rec.get("return_pct")) or 0.0) > -90.0)
    print(f"- quarters anywhere in -20% .. -90%: **{band:,}**, of which "
          f"**{sum(hits.values()):,}** sit on a split ratio")
    print("- A series adjusted for splits should show no excess here. "
          "This is a signal, not a proof: three months is long enough "
          "for an honest collapse of the same size.")
    print()


def section_fcf(rows_source) -> None:
    print("## 3. What actually blocks `fcf`")
    print()
    # This line used to end "so capex alone can never block it", which the
    # first run of this very section disproved: cfo is tier 3 for 1,514 of
    # 1,524 while capex is below the gate for 193, and 141 symbols are
    # blocked by fcf. Falling back to the impute is not the same as
    # resolving - an imputed driver is a formula standing in for a figure,
    # and the gate counts it as blocked. The claim was mine, it was written
    # as an aside rather than measured, and the table under it was the
    # thing that refuted it.
    print("`fcf` resolves as cfo - |capex| and otherwise imputes as "
          "cfo * 0.7. The impute is not a resolution: it is below the "
          "provenance gate, so capex under the gate blocks `fcf` even "
          "though cfo is present.")
    print()
    tiers = collections.Counter()
    pairs = collections.Counter()
    for rec in rows_source:
        prov = rec.get("field_provenance")
        if not isinstance(prov, dict):
            continue
        cfo, capex = prov.get("cfo"), prov.get("capex")
        tiers[("cfo", cfo)] += 1
        tiers[("capex", capex)] += 1
        pairs[(cfo, capex)] += 1
    print("| driver | tier | symbols |")
    print("|---|---|---:|")
    for (name, tier), count in sorted(tiers.items(),
                                      key=lambda kv: (kv[0][0], str(kv[0][1]))):
        print(f"| {name} | {tier if tier is not None else 'absent'} | {count:,} |")
    print()
    print("| cfo tier | capex tier | symbols |")
    print("|---|---|---:|")
    for (cfo, capex), count in pairs.most_common(12):
        print(f"| {cfo if cfo is not None else 'absent'} | "
              f"{capex if capex is not None else 'absent'} | {count:,} |")
    print()


def section_one_driver_short(stocks) -> None:
    from scripts.audit_valuation_coverage import starved_core

    print("## 4. The symbols short of exactly one core driver")
    print()
    by_driver = collections.defaultdict(list)
    for rec in stocks:
        starved = starved_core(rec)
        if len(starved) == 1:
            by_driver[starved[0]].append(
                str(rec.get("symbol") or "?").upper())
    if not by_driver:
        print("- none.\n")
        return
    print("| the one driver below the gate | symbols | which |")
    print("|---|---:|---|")
    for driver, syms in sorted(by_driver.items(), key=lambda kv: -len(kv[1])):
        shown = ", ".join(sorted(syms)[:30])
        if len(syms) > 30:
            shown += f", ... (+{len(syms) - 30})"
        print(f"| {driver} | {len(syms)} | {shown} |")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--prices", default=None)
    args = parser.parse_args()

    from scripts.audit_valuation_coverage import load_snapshot
    from services.unified_data_service import data_dir

    _, stocks = load_snapshot(args.snapshot)
    prices_path = args.prices or os.path.join(
        data_dir(), "historical_prices.json")
    lake = {}
    if os.path.exists(prices_path):
        with open(prices_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        lake = payload.get("symbols") if isinstance(payload, dict) else {}
        lake = {str(k).upper(): v for k, v in (lake or {}).items()}
    print(f"# Four questions, no fetches")
    print()
    print(f"- screener universe: **{len(stocks):,}** symbols")
    print(f"- price lake: **{len(lake):,}** symbols "
          f"({'found' if lake else 'MISSING'} at {prices_path})")
    print()

    on_scale = section_scale(stocks, lake)
    section_splits(lake)
    section_fcf(stocks)
    section_one_driver_short(stocks)
    # Non-zero, so the stage goes red and the pass names it. Everything
    # above still printed: a gate that swallows its own evidence is the
    # reason this took four runs to find.
    return 0 if on_scale else 1


if __name__ == "__main__":
    raise SystemExit(main())
