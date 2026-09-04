"""
Tests for the Accounting-Triangles imputation engine (M2 acceptance gate).

Guarantees under test:
  1. Every scalar output field carries a provenance entry (no silent fills).
  2. `is_imputed` flags every field whose provenance tier < 3.
  3. Placeholder constants (core_pat_ratio, share_dilution_3y, dilution_spread,
     eps fallback) are tier 0 / imputed=True.
  4. Firebreak (no real fundamentals) -> Tier 0 + is_valid_fundamental=False.

No network access is performed: reconstruct_financial_triangles is pure.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_data_service import (
    reconstruct_financial_triangles,
    DEFAULT_SECTOR_MEDIANS,
)

METADATA_KEYS = {
    "field_provenance",
    "data_quality_score",
    "provenance_tier",
    "is_valid_fundamental",
    "is_imputed",
}


def _full_tv_data() -> dict:
    """Realistic fully-populated TradingView scanner payload."""
    return {
        "close": 58500.0,
        "market_cap_basic": 366_000_000_000_000.0,
        "change": 1.2,
        "diluted_shares_outstanding_fq": 6_258_000_000.0,
        "total_revenue_ttm": 62_654_000_000_000.0,
        "net_income_ttm": 10_674_000_000_000.0,
        "net_income_fy": 9_900_000_000_000.0,
        "earnings_per_share_basic_ttm": 1706.0,
        "total_assets_fq": 500_000_000_000_000.0,
        "total_liabilities_fq": 180_000_000_000_000.0,
        "total_equity_fq": 320_000_000_000_000.0,
        "total_debt_fq": 60_000_000_000_000.0,
        "cash_n_cash_equivalents_fq": 25_000_000_000_000.0,
        "debt_to_equity_fq": 0.19,
        "current_ratio_fq": 2.1,
        "quick_ratio_fq": 1.7,
        "gross_margin_ttm": 24.5,
        "operating_margin_ttm": 21.3,
        "net_margin_ttm": 17.0,
        "ebit_ttm": 13_300_000_000_000.0,
        "ebitda_ttm": 15_800_000_000_000.0,
        "return_on_equity_fq": 33.3,
        "return_on_assets_fq": 21.3,
        "price_earnings_ttm": 34.3,
        "price_book_fq": 11.4,
        "price_sales_current": 5.8,
        "dividend_yield_recent": 1.1,
        "free_cash_flow_ttm": 8_000_000_000_000.0,
        "cash_f_operating_activities_ttm": 14_000_000_000_000.0,
        "total_revenue_yoy_growth_fq": 21.4,
        "net_income_yoy_growth_fq": 28.9,
        "total_revenue_cagr_3y": 18.2,
        "total_revenue_cagr_5y": 16.5,
    }


def _run(tv=None, vn=None, yf=None, price=10000.0, raw_mcap=0.0, sector="VNIND"):
    return reconstruct_financial_triangles(
        symbol="FPT",
        price=price,
        raw_mcap=raw_mcap,
        sector_code=sector,
        tv_data=tv if tv is not None else {},
        vn_data=vn if vn is not None else {},
        yf_data=yf if yf is not None else {},
    )


# ---------------------------------------------------------------------------
# 1. Full TradingView data -> core fields reported (tier 3, not imputed)
# ---------------------------------------------------------------------------

def test_full_tv_core_fields_reported():
    tri = _run(tv=_full_tv_data(), price=58500.0, raw_mcap=366_000_000_000_000.0)

    core_fields = [
        "mcap", "shares_out", "pe", "pb", "ps", "eps", "dividend_yield",
        "roe", "roa", "gross_margin", "op_margin", "net_margin",
        "rev_1y_growth", "pat_1y_growth", "rev_3y_cagr", "rev_5y_growth",
        "de_ratio", "current_ratio", "quick_ratio", "fcf_ttm",
    ]
    for f in core_fields:
        assert tri["field_provenance"][f] == 3, f"{f} expected tier 3"
        assert tri["is_imputed"][f] is False, f"{f} must not be imputed"

    assert tri["provenance_tier"] == "Tier 3 (Reported / Audited)"
    assert tri["is_valid_fundamental"] is True


def test_full_tv_derived_fields_flagged_as_triangulated():
    tri = _run(tv=_full_tv_data(), price=58500.0, raw_mcap=366_000_000_000_000.0)

    # Derived via identities from two+ real inputs -> tier 2, still imputed flag
    for f in ["peg", "peg_sales", "rule_of_40", "interest_coverage", "roic"]:
        assert tri["field_provenance"][f] == 2, f"{f} expected tier 2"
        assert tri["is_imputed"][f] is True


def test_placeholder_constants_always_tier_zero():
    for tv, kw in [(_full_tv_data(), {"price": 58500.0}), ({}, {})]:
        tri = _run(tv=tv, **kw)
        for f, val in [
            ("core_pat_ratio", 94.0),
            ("share_dilution_3y", 2.0),
            ("dilution_spread", 1.2),
        ]:
            assert tri[f] == val  # value unchanged (backward compat)
            assert tri["field_provenance"][f] == 0
            assert tri["is_imputed"][f] is True


# ---------------------------------------------------------------------------
# 2. Sparse data -> Price-Tautology Firebreak triggers
# ---------------------------------------------------------------------------

def test_sparse_data_firebreak():
    tri = _run(tv={}, vn={}, yf={}, price=10000.0, raw_mcap=0.0)

    assert "Tier 0" in tri["provenance_tier"]
    assert tri["is_valid_fundamental"] is False
    assert tri["data_quality_score"] == 15.0

    # Fabricated placeholders must be visible to consumers
    assert tri["field_provenance"]["shares_out"] == 0
    assert tri["shares_out"] == 50_000_000
    assert tri["is_imputed"]["shares_out"] is True
    assert tri["field_provenance"]["core_pat_ratio"] == 0
    assert tri["is_imputed"]["core_pat_ratio"] is True
    assert tri["field_provenance"]["share_dilution_3y"] == 0
    assert tri["field_provenance"]["dilution_spread"] == 0
    assert tri["field_provenance"]["dividend_yield"] == 0
    assert tri["dividend_yield"] == 0.0
    assert tri["is_imputed"]["dividend_yield"] is True


# ---------------------------------------------------------------------------
# 3. Sector-median / constant fills -> tier 1 and is_imputed True
# ---------------------------------------------------------------------------

def test_sector_median_fills_flagged():
    tv = {"close": 20000.0}  # just enough to pass the firebreak
    tri = _run(tv=tv, price=20000.0, sector="VNIND")
    sec_med = DEFAULT_SECTOR_MEDIANS["VNIND"]

    # Missing ratios fall back to sector medians...
    assert tri["gross_margin"] == sec_med["gross_margin"]
    assert tri["field_provenance"]["gross_margin"] == 1
    assert tri["is_imputed"]["gross_margin"] is True

    assert tri["current_ratio"] == sec_med["cur_ratio"]
    assert tri["field_provenance"]["current_ratio"] == 1
    assert tri["is_imputed"]["current_ratio"] is True

    # ...and growth constants keep their legacy values but are flagged
    assert tri["rev_1y_growth"] == 10.0
    assert tri["field_provenance"]["rev_1y_growth"] == 1
    assert tri["is_imputed"]["rev_1y_growth"] is True

    assert tri["pat_1y_growth"] == 12.0
    assert tri["field_provenance"]["pat_1y_growth"] == 1
    assert tri["is_imputed"]["pat_1y_growth"] is True

    assert tri["field_provenance"]["rev_5y_growth"] == 1
    assert tri["field_provenance"]["rev_3y_cagr"] == 1
    assert tri["field_provenance"]["pat_3y_cagr"] == 1
    assert tri["field_provenance"]["pat_5y_growth"] == 1
    for f in ("rev_5y_growth", "rev_3y_cagr", "pat_3y_cagr", "pat_5y_growth"):
        assert tri["is_imputed"][f] is True


# ---------------------------------------------------------------------------
# 4. Triangulation path: Assets - Liabilities = Equity (tier 2)
# ---------------------------------------------------------------------------

def test_equity_triangulated_from_assets_and_liabilities():
    tv = _full_tv_data()
    del tv["total_equity_fq"]
    del tv["debt_to_equity_fq"]
    tri = _run(tv=tv, price=58500.0, raw_mcap=366_000_000_000_000.0)

    assert tri["field_provenance"]["total_equity"] == 2
    assert tri["field_provenance"]["de_ratio"] == 2  # recomputed from debt/equity
    assert tri["is_imputed"]["de_ratio"] is True
    # Downstream outputs derived from the solved triangle stay flagged too
    assert tri["is_imputed"]["net_de_ratio"] is True


# ---------------------------------------------------------------------------
# 5. Key-set invariant: is_imputed covers EVERY scalar output field
# ---------------------------------------------------------------------------

def _assert_key_set_invariant(tri):
    scalars = {k for k in tri.keys() if k not in METADATA_KEYS}
    assert scalars, "result must expose scalar fields"
    assert set(tri["is_imputed"].keys()) >= scalars, (
        "is_imputed must cover every scalar output field"
    )
    # Gate 3 superset contract: every provenance-tracked field -- including
    # internal witness names that never surface as output scalars
    # ("shares", "total_equity", "total_debt", "net_income", "revenue") --
    # must be flagged, fail-closed consistent with its tier.
    for k, tier in tri["field_provenance"].items():
        assert k in tri["is_imputed"], (
            f"provenance-tracked field {k!r} missing from is_imputed "
            "(silent fill!)"
        )
        assert tri["is_imputed"][k] == (tier < 3), (
            f"{k} flag inconsistent with tier {tier}"
        )


def test_key_set_invariant_full_data():
    tri = _run(tv=_full_tv_data(), price=58500.0, raw_mcap=366_000_000_000_000.0)
    _assert_key_set_invariant(tri)


def test_key_set_invariant_sparse_data():
    tri = _run(tv={}, vn={}, yf={}, price=10000.0, raw_mcap=0.0)
    _assert_key_set_invariant(tri)


def test_no_silent_fills_across_paths():
    """Any field lacking a provenance entry defaults fail-closed to imputed."""
    for tv, kw in [
        (_full_tv_data(), {"price": 58500.0, "raw_mcap": 366_000_000_000_000.0}),
        ({}, {}),
        ({"close": 15000.0}, {"price": 15000.0}),
    ]:
        tri = _run(tv=tv, **kw)
        for k in tri:
            if k in METADATA_KEYS:
                continue
            assert k in tri["field_provenance"], (
                f"{k} returned without provenance in scenario {sorted(tv)[:3]}"
            )


# ---------------------------------------------------------------------------
# 6. Backward compatibility of the return contract
# ---------------------------------------------------------------------------

LEGACY_KEYS = {
    "mcap", "shares_out", "pe", "pb", "ps", "peg", "peg_sales", "eps",
    "dividend_yield", "roe", "roa", "gross_margin", "op_margin", "net_margin",
    "core_pat_ratio", "rev_1y_growth", "rev_3y_cagr", "rev_5y_growth",
    "pat_1y_growth", "pat_3y_cagr", "pat_5y_growth", "eps_3y_cagr",
    "de_ratio", "net_de_ratio", "current_ratio", "quick_ratio",
    "interest_coverage", "cash_to_assets", "rule_of_40", "roic", "fcf_ttm",
    "cfo_to_pat", "share_dilution_3y", "ebit_expansion", "operating_leverage",
    "dilution_spread", "field_provenance", "data_quality_score",
    "provenance_tier", "is_valid_fundamental",
}


def test_legacy_return_keys_preserved():
    tri = _run(tv=_full_tv_data(), price=58500.0, raw_mcap=366_000_000_000_000.0)
    missing = LEGACY_KEYS - set(tri.keys())
    assert not missing, f"legacy keys removed: {missing}"
    assert "is_imputed" in tri
    assert isinstance(tri["is_imputed"], dict)
    assert all(isinstance(v, bool) for v in tri["is_imputed"].values())


# ---------------------------------------------------------------------------
# 7. Provenance propagation (M2R2): worst-case tier inheritance.
#    A derived field's tier must be min(own rule tier, tiers of ALL upstream
#    inputs). Chained fabrication through a tier-0 witness is forbidden:
#    on all-empty inputs the scalar provenance histogram must contain NO 2s.
# ---------------------------------------------------------------------------

def _scalar_provenance(tri):
    """field_provenance restricted to scalar output fields."""
    scalars = {k for k in tri.keys() if k not in METADATA_KEYS}
    return {k: tri["field_provenance"][k] for k in scalars}


def test_all_empty_inputs_have_no_triangulated_tiers():
    """Zero real inputs -> zero tier-2 'Triangulated' claims anywhere."""
    tri = _run(tv={}, vn={}, yf={}, price=10000.0, raw_mcap=0.0)

    hist = {}
    for field, tier in _scalar_provenance(tri).items():
        hist[tier] = hist.get(tier, 0) + 1

    assert 2 not in hist, (
        "tier inflation through chained fabrication: tier-2 fields found "
        f"on all-empty inputs: "
        f"{[k for k, t in _scalar_provenance(tri).items() if t == 2]}"
    )
    # Firebreak behavior stays intact
    assert "Tier 0" in tri["provenance_tier"]
    assert tri["data_quality_score"] == 15.0
    assert tri["is_valid_fundamental"] is False


def test_min_propagation_mixed_real_synthetic():
    """Real balance-sheet triangle stays honest; synthetic mcap->NI chain is
    capped at its weakest upstream tier, never stamped Triangulated."""
    tv = {
        "close": 58500.0,
        "market_cap_basic": 366_000_000_000_000.0,
        "total_assets_fq": 500_000_000_000_000.0,
        "total_liabilities_fq": 180_000_000_000_000.0,
    }
    tri = _run(tv=tv, price=58500.0, raw_mcap=366_000_000_000_000.0)
    fp = tri["field_provenance"]

    # Real inputs -> reported / legitimately triangulated
    assert fp["market_cap"] == 3
    assert fp["total_equity"] == 2      # Assets - Liabilities triangle
    assert fp["total_debt"] == 2        # Liabilities * 0.70 heuristic off a real input
    assert fp["de_ratio"] == 2          # min(2, debt=2, equity=2): never inflated to 3

    # Synthetic income path (no NI/rev/eps anywhere) -> capped at fabricated witness
    assert fp["shares_out"] == 2        # derived from REAL mcap/price -> ok
    assert fp["net_income"] <= 1        # mcap/PE-median fallback inherits mcap cap
    downstream = ["pe", "ps", "roe", "roic", "cfo_to_pat",
                  "interest_coverage", "net_margin", "fcf_ttm"]
    for f in downstream:
        assert fp[f] <= 1, f"{f} inherited tier {fp[f]} > 1 through a synthetic chain"


def test_min_propagation_fabricated_witness_caps_market_cap():
    """No real shares/mcap -> price * 50M placeholder witness must yield
    market_cap tier <= 1, and every downstream consumer inherits that cap."""
    tv = {"close": 20000.0}  # just enough to pass the firebreak
    tri = _run(tv=tv, vn={}, yf={}, price=20000.0, raw_mcap=0.0)
    fp = tri["field_provenance"]

    assert fp["shares_out"] == 0                      # fabricated witness
    assert fp["market_cap"] <= 1                      # never tier 2 off tier 0
    for f in ("pe", "pb", "ps", "roe", "net_margin", "de_ratio",
              "interest_coverage", "roic", "cfo_to_pat"):
        assert fp[f] <= fp.get("market_cap", 3) + 1 and fp[f] < 2, (
            f"{f} reached tier {fp[f]} via a fabricated-witness market_cap"
        )
    hist = set(_scalar_provenance(tri).values())
    assert 2 not in hist, f"tier-2 leaked into sparse histogram: {_scalar_provenance(tri)}"
