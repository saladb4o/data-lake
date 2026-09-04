"""
Tests for services/quant_scoring.py (M4 acceptance gates).

Gates under test:
  T1. Anti-tie: a synthetic universe of ~200 stocks with >= 60 copies sharing
      IDENTICAL primary scoring factors (the mass-imputation defect) yields
      largest_tie_cluster < 2% of the universe after score_universe.
  T2. Rank-based quintiles: every band Q1..Q5 has >= floor(n*0.2)-1 members.
  T3. Determinism: scoring twice produces identical composites/quintiles.
  T4. Mid-rank correctness vs hand-computed examples (ties get the AVERAGE
      rank, not the max rank as the old count(x <= val)/n formula gave).
  T5. Percentile bounds and monotonicity sanity.

Plus edge cases: empty universe, n < 5, missing/NaN fields (neutral 50),
published label/color/badge fidelity.

No network access; no third-party deps beyond numpy-free stdlib + pytest.
"""

import math
import random
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.quant_scoring import (
    _apply_dispersion_floor,
    _raw_component_tuple,
    _resolve_fcf_yield,
    empirical_percentile,
    largest_tie_cluster,
    LAST_SCORING_DIAGNOSTICS,
    score_universe,
    TIEBREAK_FIELDS,
)

# The ten PRIMARY scoring factors (identical values caused the production
# collapse of 721 stocks onto one composite).
PRIMARY_FACTOR_KEYS = [
    "rev_5y_growth", "rev_3y_cagr", "pat_3y_cagr",
    "roe", "op_margin", "roa",
    "de_ratio", "current_ratio", "peg", "pe",
]


def make_stock(symbol: str, **overrides) -> dict:
    """Deterministic base record with all fields the scorer may read."""
    stock = {
        "symbol": symbol,
        "rev_5y_growth": 10.0,
        "rev_3y_cagr": 8.0,
        "pat_3y_cagr": 9.0,
        "roe": 14.0,
        "op_margin": 12.0,
        "roa": 6.0,
        "de_ratio": 0.8,
        "current_ratio": 1.5,
        "peg": 1.2,
        "pe": 15.0,
        "dividend_yield": 2.0,
        "roic": 10.0,
        "fcf_ttm": 500.0,
        "market_cap": 10000.0,
        "_metadata": {"data_quality_score": 80.0},
    }
    stock.update(overrides)
    return stock


def build_universe() -> dict:
    """
    200 stocks, fully deterministic (seeded RNG):
      - 140 varied stocks (formulaic + seeded jitter on every field)
      - 60 CLONES sharing IDENTICAL primary factor values (the defect
        scenario: mass imputation collapses the ten scoring inputs), but
        with distinct secondary REAL fields (dividend_yield, roic,
        fcf_ttm, data_quality_score) exactly like real records where the
        imputation engine fills pillars while real market data survives.
    """
    rng = random.Random(42)
    universe: dict = {}

    for i in range(140):
        universe[f"VAR_{i:03d}"] = make_stock(
            f"VAR_{i:03d}",
            rev_5y_growth=round(-5.0 + i * 0.5 + rng.uniform(-1, 1), 4),
            rev_3y_cagr=round(-3.0 + i * 0.35 + rng.uniform(-1, 1), 4),
            pat_3y_cagr=round(-8.0 + i * 0.55 + rng.uniform(-1.5, 1.5), 4),
            roe=round(2.0 + i * 0.25 + rng.uniform(-1, 1), 4),
            op_margin=round(1.0 + i * 0.18 + rng.uniform(-1, 1), 4),
            roa=round(-2.0 + i * 0.09 + rng.uniform(-0.8, 0.8), 4),
            de_ratio=round(2.5 - i * 0.011 + rng.uniform(-0.15, 0.15), 4),
            current_ratio=round(0.5 + i * 0.014 + rng.uniform(-0.1, 0.1), 4),
            peg=round(3.5 - i * 0.016 + rng.uniform(-0.2, 0.2), 4),
            pe=round(40.0 - i * 0.17 + rng.uniform(-1.5, 1.5), 4),
            dividend_yield=round(rng.uniform(0.0, 7.0), 4),
            roic=round(rng.uniform(-5.0, 30.0), 4),
            fcf_ttm=round(rng.uniform(50.0, 2000.0), 4),
            market_cap=float(rng.choice([800.0, 3500.0, 12000.0])),
            _metadata={"data_quality_score": round(rng.uniform(20.0, 100.0), 2)},
        )

    # 60 clones: identical ten primary factors, varying secondaries.
    for j in range(60):
        universe[f"CLONE_{j:02d}"] = make_stock(
            f"CLONE_{j:02d}",
            # Primary factors pinned to one identical value set (defect):
            rev_5y_growth=10.0, rev_3y_cagr=8.0, pat_3y_cagr=9.0,
            roe=14.0, op_margin=12.0, roa=6.0,
            de_ratio=0.8, current_ratio=1.5, peg=1.2, pe=15.0,
            # Secondary REAL fields vary per record:
            dividend_yield=round(0.5 + j * 0.08, 4),
            roic=round(4.0 + j * 0.22, 4),
            fcf_ttm=round(200.0 + j * 45.0, 4),
            market_cap=float(3000 + j * 250),
            _metadata={"data_quality_score": round(35.0 + j * 1.05, 2)},
        )

    return universe


# ---------------------------------------------------------------------------
# T1. Anti-tie
# ---------------------------------------------------------------------------

def test_t1_no_mass_ties_after_scoring():
    universe = build_universe()
    n = len(universe)
    assert n == 200

    # Sanity: before scoring there is no percentiles block to cluster on.
    cluster = largest_tie_cluster(universe)
    assert cluster == 0

    score_universe(universe)

    worst = largest_tie_cluster(universe)
    assert worst < 0.02 * n, (
        f"Largest tie cluster {worst} >= 2% of universe ({n}); "
        "anti-tie composite failed"
    )
    # Explicitly prove the 60 identical-factor clones got separated.
    # The composite is published on a 4-decimal grid while adjacent
    # mid-rank positions differ by ~0.02 * (100/n) = 0.01 points at n=200,
    # so fully distinct clone composites are expected; the binding gate is
    # largest_tie_cluster < 2% above.
    clone_comps = {
        universe[f"CLONE_{j:02d}"]["percentiles"]["composite"] for j in range(60)
    }
    assert len(clone_comps) >= 30, (
        f"60 identical-factor clones produced only {len(clone_comps)} "
        "distinct composites"
    )


# ---------------------------------------------------------------------------
# T2. Quintile bands balanced by rank
# ---------------------------------------------------------------------------

def test_t2_every_quintile_populated_and_balanced():
    universe = build_universe()
    score_universe(universe)

    counts = {q: 0 for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    for s in universe.values():
        counts[s["percentiles"]["quintile"]] += 1

    floor_band = math.floor(len(universe) * 0.2)  # 40
    for q, c in counts.items():
        assert c >= floor_band - 1, f"{q} has only {c} members (< {floor_band - 1})"

    # Sum must cover the whole universe.
    assert sum(counts.values()) == len(universe)


def test_t2b_q1_is_actually_the_top_of_the_ranking():
    universe = build_universe()
    score_universe(universe)
    q1 = [s["percentiles"]["composite"] for s in universe.values()
          if s["percentiles"]["quintile"] == "Q1"]
    q5 = [s["percentiles"]["composite"] for s in universe.values()
          if s["percentiles"]["quintile"] == "Q5"]
    assert min(q1) > max(q5)
    # No non-Q1 composite exceeds the lowest Q1 composite
    others = [s["percentiles"]["composite"] for s in universe.values()
              if s["percentiles"]["quintile"] != "Q1"]
    assert min(q1) >= max(others) - 0.011  # tie-break epsilon tolerance


# ---------------------------------------------------------------------------
# T3. Determinism
# ---------------------------------------------------------------------------

def test_t3_scoring_twice_is_identical():
    u1 = build_universe()
    u2 = build_universe()
    score_universe(u1)
    score_universe(u2)

    for sym in u1:
        p1 = u1[sym]["percentiles"]
        p2 = u2[sym]["percentiles"]
        assert p1 == p2, f"non-deterministic percentiles for {sym}"


# ---------------------------------------------------------------------------
# T4. Mid-rank correctness vs hand-computed examples
# ---------------------------------------------------------------------------

def test_t4_midrank_ties_get_average_rank():
    # values [1, 2, 2, 4]; target 2 -> strictly_less=1, equal=2
    # mid-rank: (1 + 0.5*2)/4*100 = 50.0   (old max-rank method gave 75.0)
    assert empirical_percentile([1, 2, 2, 4], 2) == 50.0


def test_t4_midrank_single_low_value():
    # target 1 in [1, 2, 2, 4]: (0 + 0.5*1)/4*100 = 12.5
    assert empirical_percentile([1, 2, 2, 4], 1) == 12.5


def test_t4_midrank_higher_end():
    # target 4 in [1, 2, 2, 4]: (3 + 0.5*1)/4*100 = 87.5
    assert empirical_percentile([1, 2, 2, 4], 4) == 87.5


def test_t4_lower_is_better_mirror():
    # de_ratio lower is better: target 2 in [1, 2, 2, 4]
    # strictly_greater=1, equal=2 -> (1 + 1)/4*100 = 50.0
    assert empirical_percentile([1, 2, 2, 4], 2, higher_is_better=False) == 50.0
    # target 4 (worst): strictly_greater=0 -> (0 + 0.5)/4*100 = 12.5
    assert empirical_percentile([1, 2, 2, 4], 4, higher_is_better=False) == 12.5


def test_t4_all_tied_population_scores_neutral_midpoint():
    # Everyone tied at 7: strictly_less=0, equal=n -> 0.5*100 = 50.0
    assert empirical_percentile([7, 7, 7, 7, 7], 7) == 50.0


def test_t4_single_observation_is_neutral():
    assert empirical_percentile([42.0], 42.0) == 50.0


# ---------------------------------------------------------------------------
# T5. Bounds and monotonicity
# ---------------------------------------------------------------------------

def test_t5_percentiles_bounded():
    values = [3.0, 7.0, 7.0, 11.0, 19.0]
    for v in [-100.0, 0.0, 3.0, 7.0, 11.0, 19.0, 1000.0]:
        p = empirical_percentile(values, v)
        assert 0.0 <= p <= 100.0


def test_t5_monotonic_higher_is_better():
    values = [float(x) for x in range(1, 21)]
    prev = -1.0
    for v in values:
        p = empirical_percentile(values, v, higher_is_better=True)
        assert p >= prev, f"value {v} got a worse percentile than a smaller value"
        prev = p


def test_t5_monotonic_lower_is_better():
    values = [float(x) for x in range(1, 21)]
    prev = -1.0
    for v in reversed(values):
        p = empirical_percentile(values, v, higher_is_better=False)
        assert p >= prev, f"value {v} got a worse percentile than a larger value"
        prev = p


def test_t5_nan_and_none_filtered_from_population():
    # NaN/None entries must not distort the percentile.
    clean = [1.0, 2.0, 3.0, 4.0]
    dirty = [1.0, float("nan"), None, 2.0, float("inf"), 3.0, 4.0]
    assert empirical_percentile(dirty, 3.0) == empirical_percentile(clean, 3.0)


def test_t5_empty_or_invalid_inputs_are_neutral():
    assert empirical_percentile([], 5.0) == 50.0
    assert empirical_percentile([float("nan")], 5.0) == 50.0
    assert empirical_percentile([1.0, 2.0], float("nan")) == 50.0


# ---------------------------------------------------------------------------
# Edge cases and published-shape fidelity
# ---------------------------------------------------------------------------

def test_empty_universe_is_silent_noop():
    universe = {}
    score_universe(universe)
    assert universe == {}
    assert largest_tie_cluster({}) == 0


def test_small_universe_n_lt_five_does_not_crash():
    universe = {
        f"TINY_{i}": make_stock(f"TINY_{i}", roe=10.0 + i) for i in range(3)
    }
    score_universe(universe)
    for sym, s in universe.items():
        p = s["percentiles"]
        assert 0.0 <= p["composite"] <= 100.0
        assert p["quintile"] in ("Q1", "Q2", "Q3", "Q4", "Q5")
    assert sum(1 for s in universe.values()) == 3


def test_missing_and_nan_fields_contribute_neutral_50():
    lone = {"LONE": make_stock("LONE")}
    # Strip every scoring input: all pillar contributions must be neutral.
    stripped = make_stock("LONE")
    for k in PRIMARY_FACTOR_KEYS:
        stripped[k] = None
    stripped["peg"] = float("nan")
    universe = {"LONE": stripped}
    score_universe(universe)
    p = universe["LONE"]["percentiles"]
    assert p["growth"] == 50.0
    assert p["quality"] == 50.0
    assert p["health"] == 50.0
    assert p["valuation"] == 50.0
    # Composite stays neutral-ish and bounded (no tie-break data available
    # beyond secondaries present on this single record).
    assert 49.0 <= p["composite"] <= 51.0


def test_composite_always_in_unit_interval_bounds():
    universe = build_universe()
    score_universe(universe)
    for sym, s in universe.items():
        comp = s["percentiles"]["composite"]
        assert 0.0 <= comp <= 100.0, f"{sym} composite out of [0,100]: {comp}"


def test_published_percentiles_shape_exact():
    universe = {"A": make_stock("A"), "B": make_stock("B", roe=30.0)}
    score_universe(universe)
    expected_keys = {
        "growth", "quality", "health", "valuation", "composite",
        "quintile", "quintile_label", "quintile_color", "quintile_badge",
    }
    for sym, s in universe.items():
        assert expected_keys == set(s["percentiles"].keys()), (
            f"{sym}: percentiles shape drifted from consumer contract"
        )


def test_quintile_metadata_matches_production_labels():
    universe = build_universe()
    score_universe(universe)
    meta = {
        "Q1": ("Tinh Hoa (Top 20%)", "#10b981", "badge-q1"),
        "Q2": ("Tốt (Khá)", "#3b82f6", "badge-q2"),
        "Q3": ("Trung Bình", "#eab308", "badge-q3"),
        "Q4": ("Yếu", "#f97316", "badge-q4"),
        "Q5": ("Rủi Ro Cao", "#ef4444", "badge-q5"),
    }
    seen = set()
    for s in universe.values():
        p = s["percentiles"]
        q = p["quintile"]
        seen.add(q)
        lbl, clr, bdg = meta[q]
        assert p["quintile_label"] == lbl
        assert p["quintile_color"] == clr
        assert p["quintile_badge"] == bdg
    assert seen == set(meta.keys())


# ---------------------------------------------------------------------------
# T6. Hostile universe regression (critic round-2 gate): 300 records, 150
#     informationally-identical-primary clones with DISTINCT secondaries,
#     plus NaN / None / bool / negative values and mcap=0. The clones MUST
#     separate (largest tie cluster < 6); all quintiles populated;
#     deterministic. Residual ties are tolerated only for records that are
#     fully informationally identical — not the case for this clone set.
# ---------------------------------------------------------------------------

def build_hostile_universe() -> dict:
    rng = random.Random(7)
    universe: dict = {}

    # 150 varied records, some carrying hostile field values.
    for i in range(150):
        overrides = dict(
            rev_5y_growth=round(-8.0 + i * 0.4 + rng.uniform(-2, 2), 4),
            rev_3y_cagr=round(-5.0 + i * 0.3 + rng.uniform(-1.5, 1.5), 4),
            pat_3y_cagr=round(-10.0 + i * 0.5 + rng.uniform(-2, 2), 4),
            roe=round(-4.0 + i * 0.28 + rng.uniform(-1.5, 1.5), 4),
            op_margin=round(-6.0 + i * 0.22 + rng.uniform(-1.5, 1.5), 4),
            roa=round(-6.0 + i * 0.1 + rng.uniform(-1, 1), 4),
            de_ratio=round(3.2 - i * 0.013 + rng.uniform(-0.2, 0.2), 4),
            current_ratio=round(0.3 + i * 0.015 + rng.uniform(-0.12, 0.12), 4),
            peg=round(4.5 - i * 0.019 + rng.uniform(-0.25, 0.25), 4),
            pe=round(55.0 - i * 0.21 + rng.uniform(-2, 2), 4),
            dividend_yield=round(rng.uniform(0.0, 8.0), 4),
            roic=round(rng.uniform(-10.0, 35.0), 4),
            fcf_ttm=round(rng.uniform(-300.0, 2500.0), 4),
            market_cap=float(rng.choice([0.0, 500.0, 2000.0, 9000.0, 40000.0])),
            _metadata={"data_quality_score": round(rng.uniform(10.0, 100.0), 2)},
        )
        # Hostile injections on a deterministic subset.
        if i % 15 == 0:
            overrides["rev_5y_growth"] = float("nan")
        if i % 15 == 3:
            overrides["roe"] = None
        if i % 15 == 6:
            overrides["peg"] = True          # bool must be ignored
        if i % 15 == 9:
            overrides["de_ratio"] = -3.7     # negative leverage
        if i % 15 == 12:
            overrides["current_ratio"] = "garbage"
            overrides["_metadata"] = "corrupt-not-a-dict"
        universe[f"H_{i:03d}"] = make_stock(f"H_{i:03d}", **overrides)

    # 150 clones: IDENTICAL ten primary factors (mass-imputation defect
    # scenario) but DISTINCT secondary REAL fields -> the centered anti-tie
    # component MUST pull them apart.
    for j in range(150):
        universe[f"CLONE_{j:03d}"] = make_stock(
            f"CLONE_{j:03d}",
            rev_5y_growth=10.0, rev_3y_cagr=8.0, pat_3y_cagr=9.0,
            roe=14.0, op_margin=12.0, roa=6.0,
            de_ratio=0.8, current_ratio=1.5, peg=1.2, pe=15.0,
            dividend_yield=round(0.1 + j * 0.05, 4),
            roic=round(2.0 + j * 0.18, 4),
            fcf_ttm=round(120.0 + j * 30.0, 4),
            market_cap=float(1800 + j * 140),
            _metadata={"data_quality_score": round(20.0 + j * 0.53, 2)},
        )
    return universe


def test_t6_hostile_universe_clones_separate():
    import copy
    universe = build_hostile_universe()
    n = len(universe)
    assert n == 300

    score_universe(universe)

    # Critic's binding gate: largest identical-composite cluster < 6.
    worst = largest_tie_cluster(universe)
    assert worst < 6, (
        f"Hostile universe: largest tie cluster {worst} >= 6 "
        "(clones failed to separate)"
    )

    # All five quintiles populated.
    counts = {q: 0 for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    for s in universe.values():
        counts[s["percentiles"]["quintile"]] += 1
    for q, c in counts.items():
        assert c > 0, f"{q} empty on hostile universe"

    # Determinism: a fresh deep-copied scoring pass is bit-identical.
    snapshot = copy.deepcopy(
        {sym: s["percentiles"] for sym, s in universe.items()}
    )
    score_universe(universe)
    for sym, s in universe.items():
        assert s["percentiles"] == snapshot[sym], (
            f"non-deterministic percentiles for {sym}"
        )


def test_t6_hostile_composites_bounded_and_finite():
    universe = build_hostile_universe()
    score_universe(universe)
    for sym, s in universe.items():
        comp = s["percentiles"]["composite"]
        assert isinstance(comp, float) or isinstance(comp, int)
        assert math.isfinite(comp)
        assert 0.0 <= comp <= 100.0


# ---------------------------------------------------------------------------
# T7. Input validation & robustness (critic round-2 Task D)
# ---------------------------------------------------------------------------

def test_t7_non_dict_record_rejected_naming_symbol():
    universe = {
        "GOOD": make_stock("GOOD"),
        "BAD": ["not", "a", "dict"],
    }
    with pytest.raises(ValueError) as excinfo:
        score_universe(universe)
    assert "BAD" in str(excinfo.value), (
        "ValueError must name the offending symbol"
    )


def test_t7_corrupt_metadata_treated_as_missing():
    good_meta = make_stock("META_OK", _metadata={"data_quality_score": 95.0})
    corrupt = [
        make_stock("META_STR", _metadata="corrupt"),
        make_stock("META_LIST", _metadata=[1, 2, 3]),
        make_stock("META_NONE", _metadata=None),
        make_stock("META_MISSING"),
    ]
    universe = {"META_OK": good_meta}
    for s in corrupt:
        universe[s["symbol"]] = s

    score_universe(universe)  # must not raise
    ok = universe["META_OK"]["percentiles"]["composite"]
    assert 49.0 <= ok <= 51.0  # single-record universe stays neutral-ish
    for s in corrupt:
        assert 0.0 <= s["percentiles"]["composite"] <= 100.0


def test_t7_bool_values_are_neutral_not_zero_or_one():
    # bool True would coerce to 1.0 under naive float(); it must be treated
    # as missing data instead.
    a = make_stock("BOOL_A", roe=True)
    b = make_stock("BOOL_B", roe=False)
    c = make_stock("CLEAN", roe=14.0)
    universe = {"BOOL_A": a, "BOOL_B": b, "CLEAN": c}
    score_universe(universe)
    pa, pb = universe["BOOL_A"]["percentiles"], universe["BOOL_B"]["percentiles"]
    pc = universe["CLEAN"]["percentiles"]
    # Both bools neutral => their quality pillar equals each other's.
    qa = (pa["composite"], pb["composite"])
    assert qa[0] == qa[1], "True/False bools must resolve identically (neutral)"
    # And they sit strictly between... just verify finite/bounded.
    assert 0.0 <= pc["composite"] <= 100.0


# ---------------------------------------------------------------------------
# T9. LIVE GATE1 regression: sector-imputed degenerate block (critic round-3).
#     Mirrors the live failure: 120 stocks in ONE sector where every primary
#     factor AND all four original secondary fields are IDENTICAL constants,
#     while real market data (market_cap / price / change_pct) varies. The
#     size/momentum tie-break components must disperse them below 2%.
# ---------------------------------------------------------------------------

def build_sector_degenerate_universe(n: int = 120) -> dict:
    rng = random.Random(99)
    # Realistic tier ladders mirroring the LIVE degenerate cluster
    # (data/screener_snapshot.json @ composite 52.249: 12 distinct mcap
    # tiers x 12 distinct price tiers x ~continuous change_pct).
    mcap_tiers = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0,
                  800.0, 1000.0, 1100.0, 1200.0, 1500.0, 1600.0]
    price_tiers = [2000.0, 4000.0, 6000.0, 8000.0, 10000.0, 12000.0,
                   16000.0, 20000.0, 22000.0, 24000.0, 30000.0, 32000.0]
    universe: dict = {}
    for i in range(n):
        # Real market data varies per record (TradingView-reported):
        mcap = float(rng.choice(mcap_tiers))
        price = float(rng.choice(price_tiers))
        change_pct = round(rng.uniform(-42.86, 25.0), 2)
        universe[f"DEG_{i:03d}"] = {
            "symbol": f"DEG_{i:03d}",
            # ALL primary factors identical (sector-median imputation):
            "rev_5y_growth": 31.7, "rev_3y_cagr": 12.4, "pat_3y_cagr": 15.1,
            "roe": 10.61, "op_margin": 9.5, "roa": 5.3,
            "de_ratio": 0.75, "current_ratio": 1.6,
            "peg": 13.2 / 15.1, "pe": 13.2,
            # ALL four original secondary fields identical too:
            "dividend_yield": 0.0,          # tier-0 constant
            "roic": 6.06,                   # sector-imputed
            # Imputed proportional to mcap with a BIT-EXACT ratio (mcap/32 =
            # 2^-5; power-of-two scaling cannot leak rounding noise), so
            # __fcf_yield__ resolves to EXACTLY ONE distinct value and any
            # dispersion provably comes from mcap/price/change_pct alone.
            "fcf_ttm": mcap / 32.0,
            "market_cap": mcap,
            "_metadata": {"data_quality_score": 17.9},  # identical dq
            # Real reported values that DO vary:
            "price": price,
            "change_pct": change_pct,
        }
    return universe


def test_t9_fcf_yield_resolves_to_exactly_one_distinct_value():
    # Fixture-premise gate: the imputed proportional fill must NOT leak
    # float noise into __fcf_yield__ (the old round(mcap*0.053, 2) produced
    # 2 distinct values, letting the fixture pass by accident).
    universe = build_sector_degenerate_universe()
    yields = {_resolve_fcf_yield(s) for s in universe.values()}
    assert len(yields) == 1, (
        f"__fcf_yield__ resolved to {len(yields)} distinct values "
        f"({sorted(yields)[:4]}...); fixture premise broken"
    )


def test_t9_sector_degenerate_block_disperses_below_two_percent():
    universe = build_sector_degenerate_universe()
    n = len(universe)
    assert n == 120

    score_universe(universe)

    worst = largest_tie_cluster(universe)
    assert worst < 0.02 * n, (
        f"Largest tie cluster {worst} >= 2% of {n}-stock degenerate "
        "sector block; size/momentum tie-break failed (live gate1)"
    )
    # And the block must actually be dispersed, not moved as one lump.
    comps = {s["percentiles"]["composite"] for s in universe.values()}
    assert len(comps) >= n * 0.5, (
        f"only {len(comps)} distinct composites across {n} records"
    )


def test_t9_fully_informationally_identical_records_may_still_tie():
    # Documented residual: with NO varying input anywhere, ties persist.
    base = dict(build_sector_degenerate_universe(10)["DEG_000"])
    base.pop("symbol")
    universe = {f"IDENT_{i}": dict(base, symbol=f"IDENT_{i}") for i in range(10)}
    score_universe(universe)
    assert largest_tie_cluster(universe) == 10


# ---------------------------------------------------------------------------
# T10. Critic round-4 regressions: coupled-component cancellation.
#      P2-prime: a degenerate block where ONLY market_cap varies (unique
#      per record) and fcf_ttm is a FIXED CONSTANT makes __fcf_yield__ the
#      exact mirror of __log10_mcap__ -- under the old unweighted average
#      they cancelled exactly and all 120 records tied (verified 120/120).
# ---------------------------------------------------------------------------

def build_p2_prime_universe(n: int = 120) -> dict:
    """Degenerate block: unique mcap per record, EVERYTHING else constant."""
    universe: dict = {}
    for i in range(n):
        universe[f"P2P_{i:03d}"] = {
            "symbol": f"P2P_{i:03d}",
            # ALL primary factors identical (sector-median imputation):
            "rev_5y_growth": 31.7, "rev_3y_cagr": 12.4, "pat_3y_cagr": 15.1,
            "roe": 10.61, "op_margin": 9.5, "roa": 5.3,
            "de_ratio": 0.75, "current_ratio": 1.6,
            "peg": 13.2 / 15.1, "pe": 13.2,
            # Secondaries: everything fixed EXCEPT market_cap:
            "dividend_yield": 0.0,
            "roic": 6.06,
            "fcf_ttm": 84.8,               # FIXED constant -> fcf_yield = c/m
            "market_cap": float(i + 1),    # UNIQUE value per record
            "_metadata": {"data_quality_score": 17.9},
            # price / change_pct absent -> those components neutral.
        }
    return universe


def test_t10_p2_prime_mirror_block_disperses_below_two_percent():
    universe = build_p2_prime_universe()
    n = len(universe)
    assert n == 120

    score_universe(universe)

    worst = largest_tie_cluster(universe)
    assert worst < 0.02 * n, (
        f"P2-prime: mirror cancellation still collapses {worst}/{n} "
        "records onto one composite"
    )
    # The coupled pair must be detected, not accidentally lucky: one of
    # __fcf_yield__/__log10_mcap__ must be dropped as an exact mirror.
    dropped = LAST_SCORING_DIAGNOSTICS["dropped_components"]
    mirror_drops = [k for k, why in dropped.items() if "mirror" in why]
    assert "__fcf_yield__" in mirror_drops or "__log10_mcap__" in mirror_drops, (
        f"expected an exact-mirror drop among fcf_yield/log10_mcap, got: {dropped}"
    )


def test_t10_mirror_detection_unit_dividend_mirrors_roic():
    # Synthetic exact mirrors: dividend_yield descends exactly as roic
    # ascends -> percentile columns satisfy p_div == 100 - p_roic
    # elementwise. Every other component is constant or absent.
    universe: dict = {}
    for j in range(20):
        universe[f"MIR_{j:02d}"] = make_stock(
            f"MIR_{j:02d}",
            # Identical primaries everywhere:
            rev_5y_growth=10.0, rev_3y_cagr=8.0, pat_3y_cagr=9.0,
            roe=14.0, op_margin=12.0, roa=6.0,
            de_ratio=0.8, current_ratio=1.5, peg=1.2, pe=15.0,
            # Coupled inverse ladders:
            roic=1.0 + j,                # ascending
            dividend_yield=40.0 - j,     # descending -> exact mirror column
            # Everything else constant/absent (make_stock defaults):
            fcf_ttm=500.0, market_cap=10000.0,
            _metadata={"data_quality_score": 80.0},
        )

    score_universe(universe)

    diag = LAST_SCORING_DIAGNOSTICS
    assert diag["kept_components"] == ["dividend_yield"], (
        f"expected only the first ladder component kept, got "
        f"{diag['kept_components']}"
    )
    assert "exact mirror" in diag["dropped_components"]["roic"]
    # Dispersion still achieved despite the dropped mirror twin:
    comps = {s["percentiles"]["composite"] for s in universe.values()}
    assert len(comps) == 20, (
        f"mirror drop failed to preserve dispersion: {len(comps)}/20 distinct"
    )


def test_t10_lexicographic_floor_disperses_differing_raw_tuples():
    names = [n for n, _ in TIEBREAK_FIELDS]
    base = {n: None for n in names}
    tuples = {
        "A": _raw_component_tuple(base, names),
        "B": _raw_component_tuple({**base, "roic": 1.0}, names),
        "C": _raw_component_tuple({**base, "roic": 5.0}, names),
    }
    assert len({tuples["A"], tuples["B"], tuples["C"]}) == 3, (
        "sanity: the three raw tuples must be pairwise distinct"
    )

    composites = {"A": 52.2490, "B": 52.2490, "C": 52.2490}
    dispersed = _apply_dispersion_floor(composites, tuples)
    assert dispersed == 1
    assert len(set(composites.values())) == 3, (
        f"differing raw tuples must disperse: {composites}"
    )
    # Shift stays tiny and centered: max |delta| < 0.01 points.
    assert all(abs(c - 52.2490) < 0.01 for c in composites.values())
    # Determinism: re-running on fresh inputs is bit-identical.
    again = {"A": 52.2490, "B": 52.2490, "C": 52.2490}
    _apply_dispersion_floor(again, tuples)
    assert again == composites


def test_t10_identical_raw_tuples_stay_legitimately_tied():
    t = (7.5,)
    composites = {"X": 60.0, "Y": 60.0, "Z": 60.0}
    tuples = {"X": t, "Y": t, "Z": t}
    dispersed = _apply_dispersion_floor(composites, tuples)
    assert dispersed == 0
    assert composites == {"X": 60.0, "Y": 60.0, "Z": 60.0}, (
        "fully-informationally-identical records must remain tied"
    )


# ---------------------------------------------------------------------------
# T8. Performance regression: full-size universe scores well under 5s
# ---------------------------------------------------------------------------

def build_perf_universe(n: int = 1526) -> dict:
    """Programmatic full-size fixture (matches production universe size)."""
    rng = random.Random(2024)
    universe: dict = {}
    for i in range(n):
        universe[f"P_{i:04d}"] = make_stock(
            f"P_{i:04d}",
            rev_5y_growth=rng.uniform(-10, 40),
            rev_3y_cagr=rng.uniform(-8, 30),
            pat_3y_cagr=rng.uniform(-15, 45),
            roe=rng.uniform(-10, 35),
            op_margin=rng.uniform(-15, 40),
            roa=rng.uniform(-10, 20),
            de_ratio=rng.uniform(0.05, 4.0),
            current_ratio=rng.uniform(0.2, 5.0),
            peg=rng.uniform(0.2, 6.0),
            pe=rng.uniform(3.0, 60.0),
            dividend_yield=rng.uniform(0.0, 8.0),
            roic=rng.uniform(-10, 35),
            fcf_ttm=rng.uniform(-500, 3000),
            market_cap=float(rng.choice([500, 2000, 8000, 50000])),
            _metadata={"data_quality_score": rng.uniform(10, 100)},
        )
    return universe


def test_t8_1526_records_under_five_seconds():
    import time
    universe = build_perf_universe(1526)
    t0 = time.perf_counter()
    score_universe(universe)
    elapsed = time.perf_counter() - t0
    assert len(universe) == 1526
    assert elapsed < 5.0, f"score_universe took {elapsed:.3f}s (> 5s)"
    print(f"\n[perf] 1526 records scored in {elapsed:.4f}s")
