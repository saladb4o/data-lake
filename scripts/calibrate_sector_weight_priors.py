#!/usr/bin/env python3
"""Derive SECTOR_WEIGHT_PRIORS from measured forward errors.

``SECTOR_WEIGHT_PRIORS`` in ``services/valuation_engine.py`` was labelled
"Pre-calibrated ... IVW", implying it came from measured model variances. It
did not - nothing in the repository derives it, and the values are judgement
about which model suits which sector. That is a defensible prior, but it should
not wear the name of a measurement.

This script produces the real thing. For every sector it walks the historical
quarters, values each symbol with the 22-model suite on its point-in-time
filing, and scores each model against the price four quarters later - the same
forward horizon the backtest uses, and for the same reason: a model scored
against the price of its own quarter is rewarded for agreeing with the market
it is supposed to be judging.

Weights are inverse-variance over those forward errors, which is what "IVW"
should have meant all along, shrunk toward equal weight in proportion to how
little evidence a sector has.

Usage
-----
    python scripts/calibrate_sector_weight_priors.py --start-year 2021
    python scripts/calibrate_sector_weight_priors.py --min-observations 20

Requires ``data/historical_fundamentals.json`` (see
``scripts/build_historical_fundamentals.py``) and ``data/historical_prices.json``.
Prints a drop-in Python table; it does not edit source.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("calibrate_sector_weight_priors")

FORWARD_HORIZON_QUARTERS = 4
#: Below this many scored observations a sector keeps equal weights; between
#: this and CONFIDENT_OBSERVATIONS the measured weights are shrunk toward them.
MIN_OBSERVATIONS = 12
CONFIDENT_OBSERVATIONS = 60
#: No single model may carry more than this share, so one lucky sector-quarter
#: cannot dominate a table meant to describe a whole sector.
MAX_MODEL_WEIGHT = 0.45


def _quarter_ordinal(code: str) -> Optional[int]:
    try:
        year_text, quarter_text = code.split("-Q")
        return int(year_text) * 4 + (int(quarter_text) - 1)
    except (ValueError, AttributeError):
        return None


def _quarter_code(ordinal: int) -> str:
    return f"{ordinal // 4}-Q{(ordinal % 4) + 1}"


def _price_at(price_db: Dict[str, Any], symbol: str, quarter: str) -> Optional[float]:
    entry = price_db.get(symbol)
    if not isinstance(entry, dict):
        return None
    row = (entry.get("quarters") or {}).get(quarter)
    if not isinstance(row, dict):
        return None
    for key in ("start_price", "open", "close_price", "close"):
        try:
            value = float(row.get(key) or 0.0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def collect_errors(
    start_year: int,
    end_year: int,
    horizon: int = FORWARD_HORIZON_QUARTERS,
) -> Dict[str, Dict[str, List[float]]]:
    """Returns {sector_code: {model_id: [squared relative error, ...]}}."""
    from services.backtest_service import QUARTERS_TIMELINE, _load_real_price_database
    from services.point_in_time_fundamentals import PointInTimeFundamentals
    from services.stock_service import ALL_SYMBOLS_MAP
    from services.valuation_engine import ValuationEngine

    pit = PointInTimeFundamentals.from_lake()
    if pit.is_empty:
        raise SystemExit(
            "No point-in-time fundamentals available. Build them first with "
            "scripts/build_historical_fundamentals.py; calibrating against "
            "price-derived inputs would just re-measure the price."
        )

    price_db = _load_real_price_database()
    if not price_db:
        raise SystemExit("historical_prices.json is empty; nothing to score against.")

    engine = ValuationEngine()
    errors: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    quarters = [q for q in QUARTERS_TIMELINE if start_year <= q["year"] <= end_year]

    for q_info in quarters:
        code = q_info["code"]
        origin = _quarter_ordinal(code)
        if origin is None:
            continue
        future_code = _quarter_code(origin + horizon)

        for symbol, master in ALL_SYMBOLS_MAP.items():
            sector = str(master.get("sector_code") or "").upper()
            if not sector:
                continue
            price_now = _price_at(price_db, symbol, code)
            price_future = _price_at(price_db, symbol, future_code)
            if not price_now or not price_future:
                continue
            filing = pit.get(symbol, code)
            if filing is None:
                continue

            payload = dict(filing)
            payload["symbol"] = symbol
            payload["price"] = price_now
            payload["sector_code"] = sector
            try:
                result = engine.get_comprehensive_valuation(symbol, payload)
            except ValueError:
                continue  # engine refused: not enough real data

            for model in result.models:
                if not model.active or model.fair_value <= 0:
                    continue
                relative = (model.fair_value - price_future) / price_future
                errors[sector][model.model_id].append(relative ** 2)

    return errors


def weights_from_errors(
    per_model: Dict[str, List[float]],
    min_observations: int,
    max_weight: float = MAX_MODEL_WEIGHT,
) -> Tuple[Dict[str, float], int]:
    """Inverse-variance weights, shrunk toward equal weight on thin evidence."""
    usable = {m: e for m, e in per_model.items() if len(e) >= min_observations}
    if not usable:
        return {}, 0

    observations = sum(len(e) for e in usable.values())
    inverse = {m: 1.0 / max(sum(e) / len(e), 1e-6) for m, e in usable.items()}
    total = sum(inverse.values())
    measured = {m: v / total for m, v in inverse.items()}

    equal = 1.0 / len(usable)
    confidence = min(1.0, observations / CONFIDENT_OBSERVATIONS)
    blended = {m: confidence * w + (1.0 - confidence) * equal for m, w in measured.items()}

    return _cap_and_redistribute(blended, max_weight), observations


def _cap_and_redistribute(weights: Dict[str, float], max_weight: float) -> Dict[str, float]:
    """Caps each weight at ``max_weight``, giving the excess to the rest.

    Capping and then renormalising does not work: if one model holds
    essentially all the weight, scaling the capped vector back to 1.0 hands it
    straight back. The excess has to go to the models that are still under the
    cap, repeatedly, until nothing is over it.
    """
    if not weights:
        return {}
    # With few enough models the cap cannot be satisfied at all - two models
    # must sum to 1.0, so one of them exceeds any cap below 0.5. Forcing equal
    # weights there would throw away the measurement to honour a constraint
    # that was only ever meant to stop one model dominating a wide field, so
    # the cap simply does not apply.
    total_raw = sum(weights.values())
    if max_weight * len(weights) <= 1.0:
        return {m: round(w / total_raw, 3) for m, w in weights.items()}

    current = dict(weights)
    for _ in range(len(current) + 1):
        over = {m: w for m, w in current.items() if w > max_weight}
        if not over:
            break
        excess = sum(w - max_weight for w in over.values())
        under = [m for m in current if m not in over]
        if not under:
            break
        headroom = sum(max_weight - current[m] for m in under)
        for m in over:
            current[m] = max_weight
        for m in under:
            share = ((max_weight - current[m]) / headroom) if headroom > 0 else 1.0 / len(under)
            current[m] += excess * share

    total = sum(current.values())
    return {m: round(w / total, 3) for m, w in current.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--min-observations", type=int, default=MIN_OBSERVATIONS,
                        help="Per-model observations required before a model is weighted.")
    parser.add_argument("--json-out", default=None, help="Also write the table as JSON.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from services.market_calendar import default_backtest_end_year

    end_year = args.end_year or default_backtest_end_year()
    errors = collect_errors(args.start_year, end_year)
    if not errors:
        logger.error("no sector produced a single scored observation")
        return 1

    table: Dict[str, Dict[str, float]] = {}
    print("SECTOR_WEIGHT_PRIORS: Dict[str, Dict[str, float]] = {")
    for sector in sorted(errors):
        weights, observations = weights_from_errors(errors[sector], args.min_observations)
        if not weights:
            logger.info("  # %s skipped: fewer than %d observations per model",
                        sector, args.min_observations)
            continue
        table[sector] = weights
        body = ", ".join(f'"{m}": {w}' for m, w in
                         sorted(weights.items(), key=lambda kv: -kv[1]))
        print(f'    "{sector}": {{{body}}},  # n={observations}')
    print("}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(table, handle, ensure_ascii=False, indent=2)
        logger.info("wrote %s", args.json_out)
    return 0 if table else 1


if __name__ == "__main__":
    raise SystemExit(main())
