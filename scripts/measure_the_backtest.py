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

#: Lags to sweep, in days from quarter end. 20 and 30 are the statutory
#: deadlines for quarterly and consolidated quarterly reports; 45 is what
#: the lake assumes; 90 is the annual deadline and stands in for a filer
#: who is late every time. A result that survives 90 is not resting on
#: the assumption.
DEFAULT_LAGS = (20, 30, 45, 60, 90)

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
    parser.add_argument("--strategy", default="peter_lynch_garp")
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

    def run(label: str, mode: str, lag: Optional[int]) -> None:
        started = time.time()
        try:
            payload = service.run_backtest(
                screening_strategy=args.strategy,
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
            rows.append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  {label}: FAILED ({type(exc).__name__}: {exc})")
            return
        row = _row(label, payload)
        row["seconds"] = round(time.time() - started, 1)
        rows.append(row)
        print(f"  {label}: {row['seconds']}s, "
              f"{row['metrics'].get('total_trades')} trades")

    print("## Backtest sweep")
    print()
    for lag in args.lags:
        run(f"point_in_time, lag {lag}d", FundamentalsMode.POINT_IN_TIME, lag)
    if not args.skip_snapshot:
        run("snapshot_projected (not evidence)",
            FundamentalsMode.SNAPSHOT_PROJECTED, None)

    print()
    header = "| run | " + " | ".join(name for _, name in COLUMNS) + " | valued | skipped |"
    print(header)
    print("|---" * (len(COLUMNS) + 3) + "|")
    for row in rows:
        if "error" in row:
            print(f"| {row['label']} | " + " | ".join(["ERROR"] * len(COLUMNS))
                  + f" | - | - |")
            continue
        cells = " | ".join(_fmt(row["metrics"].get(key)) for key, _ in COLUMNS)
        print(f"| {row['label']} | {cells} | "
              f"{_fmt(row.get('symbol_quarters_valued'))} | "
              f"{_fmt(row.get('symbol_quarters_skipped_no_filing'))} |")
    print()

    # The spread across lags is the finding, not any single row. State it
    # rather than leaving it to be eyeballed out of the table.
    swept = [r for r in rows
             if "error" not in r and r["label"].startswith("point_in_time")]
    cagrs = [r["metrics"].get("cagr_pct") for r in swept
             if r["metrics"].get("cagr_pct") is not None]
    if len(cagrs) >= 2:
        spread = max(cagrs) - min(cagrs)
        print(f"- CAGR across lags {min(cagrs):.2f}% .. {max(cagrs):.2f}% "
              f"(spread **{spread:.2f} points**)")
        print("  A wide spread means the return is bought with the "
              "publication-date assumption rather than with the filings.")
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
