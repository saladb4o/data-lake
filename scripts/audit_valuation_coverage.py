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


#: The inputs that decide whether a symbol can be valued at all. Every one of
#: them feeds models that most sectors use.
#:
#: The peripheral drivers are deliberately excluded: `affo` (REITs), `rwa`
#: (banks), `landbank` (developers), `regulated_asset_base` (utilities),
#: `tbvps`, `roic`, `invested_capital`. Each is required by one or two
#: sector-specific models and is absent for almost every company, by design,
#: because SECTOR_MODEL_MAP only offers each sector 5-6 of the 22 models.
#:
#: Taking the minimum across *all* provenance keys - which this function used
#: to do - therefore reported tier 0 for every symbol in the universe,
#: including the ones being valued by six models from fully reported filings.
#: A histogram that says "100% fabricated" next to "50% valued, median 4
#: models" is not a measurement, it is a contradiction, and it hid the real
#: distribution behind a driver no sector was ever going to have.
CORE_DRIVERS = (
    "shares", "shares_out", "market_cap", "market_cap_vnd",
    "equity", "debt", "cash", "revenue", "net_income", "ebit",
)


def worst_tier(record: Dict[str, Any]) -> Optional[int]:
    """The lowest provenance tier among the drivers that gate a valuation."""
    tiers = record.get("field_provenance")
    if not isinstance(tiers, dict) or not tiers:
        return None
    numeric = [
        int(tiers[key]) for key in CORE_DRIVERS
        if isinstance(tiers.get(key), (int, float))
        and not isinstance(tiers.get(key), bool)
    ]
    return min(numeric) if numeric else None


#: The tier the resolver insists on. Kept here as a name rather than a bare
#: 2 so that a report and the engine cannot drift apart silently.
TRUSTED = 2


def starved_core(record: Dict[str, Any]) -> List[str]:
    """Which CORE drivers sit below the gate, named.

    worst_tier answers "how bad is the weakest one" and that is what the
    histogram needs. It cannot answer "what would a new vendor have to
    supply", because a minimum names no driver: a universe reported as
    tier 1 says nothing about whether the missing thing is revenue for
    everybody or debt for everybody, and those are different projects.
    """
    tiers = record.get("field_provenance")
    if not isinstance(tiers, dict):
        return []
    out = []
    for key in CORE_DRIVERS:
        value = tiers.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if int(value) < TRUSTED:
            out.append(key)
    return out


def evaluate(record: Dict[str, Any]) -> Dict[str, Any]:
    from services.valuation_engine import ValuationEngine

    engine = ValuationEngine()
    symbol = str(record.get("symbol") or record.get("ticker") or "?")
    row: Dict[str, Any] = {
        "symbol": symbol,
        "worst_tier": worst_tier(record),
        "starved_core": starved_core(record),
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
        # Only count drivers the symbol's own sector actually asks for.
        #
        # add_model() records imputed_drivers before it checks sector
        # applicability, so a model the sector never allows still files a
        # complaint on its way to BYPASSED. That is why every ordinary
        # company appeared blocked by affo, rwa and landbank at once - a
        # REIT model, a bank model and a real-estate model, none of which
        # was ever going to be used for it. The table read as a diagnosis
        # and was an artefact of evaluation order.
        # Filter by the sector's model list, not by status.
        #
        # Filtering on BYPASSED looked right and did nothing: add_model()
        # tests `missing` before `sector_ok`, so a model that is both wrong
        # for the sector and short of drivers is filed INSUFFICIENT_DATA and
        # never reaches BYPASSED. Only a model that is inapplicable *and*
        # fully fed gets that status, which is almost none of them - the
        # blocking table came back byte-identical, affo at 906 and all.
        #
        # The sector's own list is the thing that decides applicability, so
        # read it directly rather than inferring it from an outcome.
        from services.valuation_engine import SECTOR_MODEL_MAP

        sector_code = str(record.get("sector_code") or "DEFAULT").upper()
        prefix = sector_code[:5] if len(sector_code) >= 5 else sector_code
        applicable = SECTOR_MODEL_MAP.get(prefix, SECTOR_MODEL_MAP.get(sector_code))

        def _applies(model) -> bool:
            if applicable is None:
                return True
            return getattr(model, "model_id", None) in applicable

        blocked = collections.Counter()
        for model in models:
            if not _applies(model):
                continue
            for driver in (model.diagnostics or {}).get("imputed_drivers", []):
                blocked[driver] += 1
        # Two lists, because they answer two different questions.
        #
        # blocked_by is capped at five for the per-symbol rows, where a
        # twelve-item list would be unreadable. blocked_all is every driver
        # the applicable models complained about, and it is what the
        # aggregate table counts.
        #
        # Counting the capped list is what the aggregate did, and it made the
        # table lie by omission whenever a driver was fixed. Wiring cash
        # removed it from 150 symbols' complaints, and affo rose 117 -> 124,
        # landbank 113 -> 117, invested_capital 28 -> 30, with roe appearing
        # at 28 where it had not been listed - not because anything new
        # blocked them, but because each symbol's sixth reason was promoted
        # into a top-five that had just lost a member. The table moved in
        # response to a fix elsewhere, which is the one thing a measurement
        # must never do.
        #
        # This table is what the whole prioritisation reads: it is where
        # "wire cash next, it blocks 150" comes from. A ranking that reshuffles
        # itself every time something is fixed cannot be used to decide what
        # to fix. Same defect as the hardcoded REFUSED label - a reporting
        # artefact steering decisions - and found the same way, by a number
        # moving when nothing behind it had.
        row["blocked_by"] = [d for d, _ in blocked.most_common(5)]
        row["blocked_all"] = [d for d, _ in blocked.most_common()]
        # Which sector this symbol was valued as, and whether that sector is
        # one SECTOR_MODEL_MAP knows. A sector it does not know falls through
        # to all 22 models, so the symbol is judged against bank, REIT and
        # real-estate drivers at once - which is how a perfectly ordinary
        # company ends up blocked by affo, rwa and landbank simultaneously.
        row["sector_code"] = str(record.get("sector_code") or "")
        # Not len(models): every one of the 22 is appended regardless of
        # sector and merely marked BYPASSED, so that count is always 22 and
        # says nothing. What matters is how many the sector actually offers.
        row["models_offered"] = sum(1 for m in models if _applies(m))
        # Models that ran on real data and returned nothing positive.
        #
        # A refusal with an empty blocked_by list is not the same failure as
        # one short of drivers, and the two need opposite responses: the
        # first is every applicable model declining to value a company - no
        # earnings, no book equity, equity wiped out by debt - which is an
        # answer, and no amount of new data changes it. AAV and API report
        # exactly that and were indistinguishable from a data gap.
        row["models_declined"] = sum(
            1 for m in models
            if _applies(m) and getattr(m, "status", "") == "NOT_APPLICABLE"
        )
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
    print("\nWeakest CORE driver tier per symbol:")
    print("(core = shares, market cap, equity, debt, cash, revenue, net income,")
    print(" ebit. Sector-specific drivers such as affo/rwa/landbank are excluded:")
    print(" they are absent for almost every company by design.)")
    # The outcome column is counted, not asserted.
    #
    # It used to print a flat "valued"/"REFUSED" derived from the tier alone,
    # which is not a measurement but a restatement of TRUSTED_TIER - and it
    # was wrong. The gate runs per driver per model, so a company whose
    # weakest CORE driver is a tier-1 stand-in is still valued by any model
    # that never asks for that driver. While refusals outnumbered the tier-1
    # count the claim passed unnoticed; at 158 tier-1 symbols against 92
    # refusals in total it became arithmetically impossible, which is the
    # only reason it was caught.
    #
    # Printing the real split matters beyond tidiness: a jump in coverage
    # has exactly two explanations, better data or a looser gate, and this
    # column is where the difference shows. A hardcoded label cannot tell
    # them apart; counted outcomes can.
    by_tier_outcome = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by_tier_outcome[r["worst_tier"]][0 if r["active_models"] > 0 else 1] += 1
    for tier in (4, 3, 2, 1, 0):
        count = tiers.get(tier, 0)
        if not count:
            continue
        ok, no = by_tier_outcome[tier]
        outcome = f"{ok} valued, {no} refused" if no else "all valued"
        print(f"  tier {tier} {TIER_LABELS[tier]:<16} {count:>6}  {pct(count)}   {outcome}")
    if tiers.get(None):
        print(f"  no provenance metadata     {tiers[None]:>6}  {pct(tiers[None])}   valued (nothing says otherwise)")

    if valued:
        counts = sorted(r["active_models"] for r in valued)
        mid = counts[len(counts) // 2]
        print(f"\nActive models among valued symbols: median {mid}, max {max(counts)} of 22")
        print("(Each sector allows only 5-6 of the 22 models by design, so 5-6 is a full house.)")

    drivers = collections.Counter()
    for row in rows:
        for driver in row.get("blocked_all") or row["blocked_by"]:
            drivers[driver] += 1
    if drivers:
        print("\nMost common blocking drivers:")
        for driver, count in drivers.most_common(12):
            print(f"  {driver:<28} {count:>6} symbols")

    # The symbols the provenance gate lets through and the model map still
    # refuses. These are not a data problem: their drivers are vendor
    # reported or triangulated, and they are turned away anyway. Report them
    # by sector, because a sector missing from SECTOR_MODEL_MAP is a
    # one-line fix and a sector whose own models need absent drivers is not.
    from services.valuation_engine import SECTOR_MODEL_MAP

    gated_out = [
        r for r in refused
        if r["worst_tier"] is not None and r["worst_tier"] >= 2
    ]
    if gated_out:
        print(f"\nRefused despite tier-2-or-better data: {len(gated_out)}"
              f" of {len(refused)} refusals")
        declined = [r for r in gated_out if not r["blocked_by"]
                    and (r.get("models_declined") or 0) > 0]
        if declined:
            print(f"  of which {len(declined)} were not short of anything:"
                  f" every model the sector offers ran on real data and"
                  f" declined to value the company.")
            print(f"  {', '.join(r['symbol'] for r in declined[:12])}"
                  + (" ..." if len(declined) > 12 else ""))
            print("  No new vendor changes those; a company with no earnings"
                  " and no book equity has no fair value to publish.")
        by_sector = collections.Counter(
            (r.get("sector_code") or "", (r.get("sector_code") or "") in SECTOR_MODEL_MAP, r.get("models_offered") or 0)
            for r in gated_out
        )
        print("  sector           in map  models offered  symbols")
        for (sector, known, offered), count in by_sector.most_common(15):
            print(f"  {sector or '(none)':<16} {'yes' if known else 'NO':<7}"
                  f" {offered:>14}  {count:>7}")

    # The other half of the refusals, and the half that decides whether the
    # data work is finished. gated_out above is the group whose drivers ARE
    # trusted and are turned away anyway: a model-map problem. This is the
    # complement - the companies refused because a driver the gate needs is
    # a stand-in or a fabrication - and it is the only group any new vendor
    # or any extractor fix can ever move.
    #
    # Reported by driver, not by count, because the count alone has been
    # read as a work queue twice and is not one. "89 refused" says nothing
    # about whether there is anything left to do; "89 refused, all of them
    # short of nothing, or all of them short of revenue" are opposite
    # answers, and only the second is a task.
    starved = [
        r for r in refused
        if r["worst_tier"] is not None and r["worst_tier"] < 2
    ]
    print(f"\nRefused for want of trustworthy data: {len(starved)}"
          f" of {len(refused)} refusals")
    if starved:
        missing = collections.Counter()
        for row in starved:
            for driver in row.get("starved_core") or []:
                missing[driver] += 1
        print("  CORE driver below the gate    symbols   share of the group")
        for driver, count in missing.most_common():
            share = 100.0 * count / len(starved)
            print(f"  {driver:<28} {count:>7}   {share:>16.1f}%")
        # A company short of every core driver at once is one the vendor
        # returned nothing for. A company short of one is a company one
        # extractor away from being valued, and those are worth naming.
        narrow = [r for r in starved if len(r.get("starved_core") or []) == 1]
        if narrow:
            by_driver = collections.Counter(
                (r["starved_core"] or ["?"])[0] for r in narrow)
            print(f"  {len(narrow)} of the {len(starved)} are short of exactly"
                  f" one driver: "
                  + ", ".join(f"{d} x{n}" for d, n in by_driver.most_common()))
            print("  Those are the ones a single extractor fix can reach.")
        blank = [r for r in starved
                 if len(r.get("starved_core") or []) >= len(CORE_DRIVERS) - 1]
        if blank:
            print(f"  {len(blank)} are short of every core driver at once -"
                  f" no vendor on this route returned anything for them.")

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
            "quarterly lake. The live path now reads it, but only to fill\n"
            "lines this request's VNDIRECT fetch did not return - same\n"
            "vendor, same endpoint, same item codes. So a rebuild helps a\n"
            "company whose fetch failed and changes nothing for a company\n"
            "whose fetch succeeded and simply has no such line filed.\n"
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
