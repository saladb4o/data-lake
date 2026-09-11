#!/usr/bin/env python3
"""Run the fair-value backtest across a sweep of assumptions, in one pass.

Why a sweep and not a run
-------------------------
Every question this answers used to cost a workflow run, and several of
those runs turned out to be measuring the question rather than the data.
The expensive part is not the backtest - it is loading the price lake,
the screener universe and the fundamentals lake, which happens once here
and is then reused for every row.

What it asks
------------
1. Does point-in-time work at all on the lake we built, and on how many
   symbol-quarters?
2. How much of the result rests on assuming filings are public 45 days
   after quarter end? The lag is swept, and the answer is the spread
   between the rows - a wide spread means the return is bought with an
   assumption rather than with skill.
3. What does the same configuration do in snapshot_projected? That mode
   derives every input from the price it is judging, so its numbers are
   arithmetic, not a track record. It is here as a contrast: if
   point-in-time cannot beat a mode that cannot possibly predict
   anything, that is worth knowing in the same run.

It writes no valuation input. It reads the lakes and prints.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.point_in_time_fundamentals import (  # noqa: E402
    DEFAULT_PUBLICATION_LAG_DAYS,
)

logger = logging.getLogger("measure_the_backtest")

#: Lags to sweep, in days from quarter end. 20 is the statutory deadline
#: for a quarterly report and 90 the annual one, so they bracket every
#: filer from prompt to chronically late. Only the two extremes are swept
#: by default: a previous pass ran 20/30/45/60/90 and returned five rows
#: identical to two decimal places, and three interior points between two
#: endpoints that agree cannot disagree. The endpoints are kept because
#: they are what would show the lag mattering if it ever did.
DEFAULT_LAGS = (20, 90)

#: The axis that is swept in the freed slots. The lag turned out not to
#: move the result; the screening strategy decides which symbols reach
#: the valuation loop at all, so it is the axis with something to say.
#: peter_lynch_garp is the historical default, all_universe removes the
#: screen entirely, and the gap between them is the cost of the screen.
DEFAULT_STRATEGIES = ("peter_lynch_garp", "all_universe")

#: Metrics worth a column. Ratios that the service withholds rather than
#: inflates come back as None and print as "-".
COLUMNS = (
    ("total_return_pct", "return %"),
    ("cagr_pct", "CAGR %"),
    ("excess_cagr_pct", "excess %"),
    ("max_drawdown_pct", "max DD %"),
    ("sharpe_ratio", "Sharpe"),
    ("win_rate_pct", "win %"),
    ("total_trades", "trades"),
)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def _row(label: str, payload: Any) -> Dict[str, Any]:
    metrics = payload.metrics or {}
    diag = (payload.diagnostics or {}).get("fundamentals", {}) or {}
    return {
        "label": label,
        "metrics": {key: metrics.get(key) for key, _ in COLUMNS},
        "symbol_quarters_valued": diag.get("symbol_quarters_valued"),
        "symbol_quarters_skipped_no_filing": diag.get(
            "symbol_quarters_skipped_no_filing"),
        "symbols_in_lake": diag.get("symbols_in_lake"),
        "filing_age_in_quarters": diag.get("filing_age_in_quarters"),
        "funnel": diag.get("funnel"),
        "is_evidence_of_skill": diag.get("is_evidence_of_skill"),
        "warning": diag.get("warning"),
        "trades": len(payload.trades or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lags", type=int, nargs="+", default=list(DEFAULT_LAGS),
                        help="Publication lags in days to sweep.")
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--strategies", nargs="+",
                        default=list(DEFAULT_STRATEGIES),
                        help="Screening strategies to sweep.")
    parser.add_argument("--model", default="composite_fair_value")
    parser.add_argument("--skip-snapshot", action="store_true",
                        help="Omit the snapshot_projected contrast row.")
    parser.add_argument("--json", default=None, help="Write the rows here.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from services.fair_value_backtest_service import (
        FairValueBacktestService, FundamentalsMode)

    service = FairValueBacktestService()
    rows: List[Dict[str, Any]] = []

    def run(label: str, mode: str, lag: Optional[int],
            strategy: str) -> None:
        started = time.time()
        try:
            payload = service.run_backtest(
                screening_strategy=strategy,
                valuation_model_id=args.model,
                top_k=args.top_k,
                start_year=args.start_year,
                end_year=args.end_year,
                fundamentals_mode=mode,
                publication_lag_days=(
                    lag if lag is not None else DEFAULT_PUBLICATION_LAG_DAYS),
            )
        except Exception as exc:  # one row must not end the sweep
            import traceback
            traceback.print_exc()
            rows.append({"label": label, "strategy": strategy,
                         "error": f"{type(exc).__name__}: {exc}"})
            print(f"  {label}: FAILED ({type(exc).__name__}: {exc})")
            return
        row = _row(label, payload)
        row["strategy"] = strategy
        row["seconds"] = round(time.time() - started, 1)
        rows.append(row)
        print(f"  {label}: {row['seconds']}s, "
              f"{row['metrics'].get('total_trades')} trades")

    print("## Backtest sweep")
    print()
    for strategy in args.strategies:
        for lag in args.lags:
            run(f"point_in_time, {strategy}, lag {lag}d",
                FundamentalsMode.POINT_IN_TIME, lag, strategy)
    if not args.skip_snapshot:
        run("snapshot_projected (not evidence)",
            FundamentalsMode.SNAPSHOT_PROJECTED, None, args.strategies[0])

    print()
    # in lake is printed because without it "valued 0" has two very
    # different causes - the lake was not found, or it was found and
    # nothing in it matched - and the table could not tell them apart.
    header = ("| run | " + " | ".join(name for _, name in COLUMNS)
              + " | in lake | valued | skipped |")
    print(header)
    print("|---" * (len(COLUMNS) + 4) + "|")
    for row in rows:
        if "error" in row:
            print(f"| {row['label']} | " + " | ".join(["ERROR"] * len(COLUMNS))
                  + " | - | - | - |")
            continue
        cells = " | ".join(_fmt(row["metrics"].get(key)) for key, _ in COLUMNS)
        print(f"| {row['label']} | {cells} | "
              f"{_fmt(row.get('symbols_in_lake'))} | "
              f"{_fmt(row.get('symbol_quarters_valued'))} | "
              f"{_fmt(row.get('symbol_quarters_skipped_no_filing'))} |")
    print()

    # Where the universe went. The metrics table answers "what did it
    # earn"; without this one, "on how much" has no answer at all, and
    # 131 valued out of 1,381 in the lake reads as a lake problem when
    # every stage above it may be the one doing the cutting.
    funnelled = [r for r in rows if "error" not in r and r.get("funnel")]
    if funnelled:
        print("### Where the universe went (symbol-quarters)")
        print()
        print("| run | universe | strategy passed | no price | "
              "no filing | valued |")
        print("|---|---:|---:|---:|---:|---:|")
        for row in funnelled:
            f = row["funnel"]
            print(f"| {row['label']} | {_fmt(f.get('universe'))} | "
                  f"{_fmt(f.get('strategy_passed'))} | "
                  f"{_fmt(f.get('no_price_that_quarter'))} | "
                  f"{_fmt(f.get('no_filing'))} | {_fmt(f.get('valued'))} |")
        print()

    # How stale the filings actually were. This is the measurement that
    # says whether the lag sweep measured anything: if every lag selects
    # filings of the same age, the lag could not have bitten, and rows
    # that agree are the expected result rather than a bug to hunt.
    aged = [r for r in rows if "error" not in r and r.get("filing_age_in_quarters")]
    if aged:
        print("### Age of the filing actually used")
        print()
        print("| run | filings by age in quarters |")
        print("|---|---|")
        for row in aged:
            ages = row["filing_age_in_quarters"] or {}
            cells = ", ".join(f"{k}q x{v}" for k, v in
                              sorted(ages.items(), key=lambda kv: int(kv[0])))
            print(f"| {row['label']} | {cells or '-'} |")
        print()
        signatures = {json.dumps(r["filing_age_in_quarters"], sort_keys=True)
                      for r in aged}
        if len(signatures) == 1 and len(aged) > 1:
            print("- every run selected filings of **identical** ages. The "
                  "lag assumption cannot be moving the result, because it "
                  "is not moving which filing gets read. Rows that agree "
                  "below are that, not a stuck parameter.")
            print()

    # The spread across lags is the finding, not any single row. State it
    # rather than leaving it to be eyeballed out of the table. It is taken
    # within one strategy: two strategies see different companies, so a
    # spread across both would measure the screen, not the lag.
    for strategy in args.strategies:
        swept = [r for r in rows if "error" not in r
                 and r.get("strategy") == strategy
                 and r["label"].startswith("point_in_time")]
        cagrs = [r["metrics"].get("cagr_pct") for r in swept
                 if r["metrics"].get("cagr_pct") is not None]
        if len(cagrs) >= 2:
            spread = max(cagrs) - min(cagrs)
            print(f"- {strategy}: CAGR across lags {min(cagrs):.2f}% .. "
                  f"{max(cagrs):.2f}% (spread **{spread:.2f} points**)")
    print("  A wide spread means the return is bought with the "
          "publication-date assumption rather than with the filings.")
    swept = [r for r in rows
             if "error" not in r and r["label"].startswith("point_in_time")]
    valued = [r.get("symbol_quarters_valued") for r in swept
              if r.get("symbol_quarters_valued") is not None]
    if valued and max(valued) == 0:
        print("- **nothing was valued at any lag**: the lake was not read. "
              "Check that historical_fundamentals.json is where the "
              "resolver looks, before reading anything above as a result.")
    for row in rows:
        if row.get("warning"):
            print(f"- {row['label']}: {row['warning']}")

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"rows": rows}, handle, ensure_ascii=False, indent=2)

    # A sweep that produced no usable row is a failed measurement, and the
    # run should say so rather than exit green on an empty table.
    return 0 if any("error" not in r for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
