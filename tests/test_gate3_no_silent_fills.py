"""
Gate-3 regression (critic round-3): NO silent fills via internal witnesses.

Live failure: field_provenance carried witness keys ("shares",
"total_equity", "total_debt", "net_income", "revenue") with tier < 3 that
had NO entry in the consumer-facing is_imputed map, because the map was
built over result-dict scalar keys only.

Contract under test:
  1. set(is_imputed.keys()) >= set(field_provenance.keys())  -- superset.
  2. is_imputed[k] == (field_provenance[k] < 3) for EVERY provenance key
     (fail-closed: missing tier -> True).
  3. _metadata.is_imputed on normalized records still covers every
     top-level fundamental scalar AND now also witness names;
     imputed_field_count == number of True entries in the propagated map.

No network access; both engine entry points are pure given dict inputs.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_data_service import (
    normalize_stock_data,
    reconstruct_financial_triangles,
)

WITNESS_KEYS = ["shares", "total_equity", "total_debt", "net_income", "revenue"]


def _full_tv_data() -> dict:
    return {
        "close": 58500.0,
        "market_cap_basic": 366_000_000_000_000.0,
        "change": 1.2,
        "diluted_shares_outstanding_fq": 6_258_000_000.0,
        "total_revenue_ttm": 62_654_000_000_000.0,
        "net_income_ttm": 10_674_000_000_000.0,
        "earnings_per_share_basic_ttm": 1706.0,
        "total_assets_fq": 500_000_000_000_000.0,
        "total_liabilities_fq": 180_000_000_000_000.0,
        "total_equity_fq": 320_000_000_000_000.0,
        "total_debt_fq": 60_000_000_000_000.0,
        "cash_n_cash_equivalents_fq": 25_000_000_000_000.0,
        "debt_to_equity_fq": 0.19,
        "current_ratio_fq": 2.1,
        "gross_margin_ttm": 24.5,
        "operating_margin_ttm": 21.3,
        "return_on_equity_fq": 33.3,
        "price_earnings_ttm": 34.3,
        "dividend_yield_recent": 1.1,
        "free_cash_flow_ttm": 8_000_000_000_000.0,
    }


def _assert_superset_invariant(tri):
    fp = tri["field_provenance"]
    imp = tri["is_imputed"]
    assert isinstance(imp, dict)
    # 1. Superset over ALL provenance-tracked fields.
    missing = [k for k in fp if k not in imp]
    assert not missing, f"is_imputed missing provenance keys: {missing}"
    # 2. Fail-closed flag consistency for every provenance key.
    wrong = {
        k: (imp[k], fp[k])
        for k in fp
        if imp[k] != (fp[k] < 3)
    }
    assert not wrong, f"flags inconsistent with tiers: {wrong}"
    # Witnesses must actually be present and flagged honestly.
    for k in WITNESS_KEYS:
        if k in fp:
            assert imp[k] is (fp[k] < 3), f"witness {k} flagged dishonestly"


def test_gate3_rich_input_witnesses_flagged():
    tri = reconstruct_financial_triangles(
        symbol="FPT",
        price=58500.0,
        raw_mcap=366_000_000_000_000.0,
        sector_code="VNIND",
        tv_data=_full_tv_data(),
        vn_data={},
        yf_data={},
    )
    fp = tri["field_provenance"]
    for k in WITNESS_KEYS:
        assert k in fp, f"witness {k} not even tracked in rich scenario"
    _assert_superset_invariant(tri)


def test_gate3_empty_input_fail_closed():
    tri = reconstruct_financial_triangles(
        symbol="EMPTY",
        price=10000.0,
        raw_mcap=0.0,
        sector_code="VNIND",
        tv_data={},
        vn_data={},
        yf_data={},
    )
    _assert_superset_invariant(tri)


# ---------------------------------------------------------------------------
# Normalizer propagation: _metadata.is_imputed covers scalars + witnesses.
# ---------------------------------------------------------------------------

TOP_LEVEL_SCALARS = {
    "market_cap", "pe", "pb", "ps", "peg", "peg_sales", "eps",
    "dividend_yield", "roe", "roa", "gross_margin", "op_margin",
    "net_margin", "core_pat_ratio", "rev_1y_growth", "rev_3y_cagr",
    "rev_5y_growth", "pat_1y_growth", "pat_3y_cagr", "pat_5y_growth",
    "eps_3y_cagr", "de_ratio", "net_de_ratio", "current_ratio",
    "quick_ratio", "interest_coverage", "cash_to_assets", "rule_of_40",
    "roic", "fcf_ttm", "cfo_to_pat", "share_dilution_3y",
    "ebit_expansion", "operating_leverage", "dilution_spread",
}


def test_gate3_normalized_metadata_covers_scalars_and_witnesses():
    rec = normalize_stock_data("FPT", tv_data=_full_tv_data())
    md = rec["_metadata"]

    imp = md["is_imputed"]
    fp = md["field_provenance"]

    # Every top-level fundamental scalar is still covered...
    missing = [k for k in TOP_LEVEL_SCALARS if k not in imp]
    assert not missing, f"is_imputed lost scalar coverage: {missing}"

    # ...and every provenance key (incl. witnesses) is now covered too,
    # consistent with its tier.
    assert set(imp.keys()) >= set(fp.keys()), (
        f"is_imputed missing provenance/witness keys: "
        f"{sorted(set(fp) - set(imp))}"
    )
    for k in fp:
        assert imp[k] == (fp[k] < 3), f"{k} flag inconsistent with tier"

    # market_cap alias logic intact: record exposes market_cap, engine
    # tracks mcap -- BOTH must be present and honest.
    assert "mcap" in imp and "market_cap" in imp
    assert imp["market_cap"] == imp["mcap"] == (
        fp["market_cap"] < 3
    )

    # imputed_field_count semantics: count of True entries in the map.
    assert md["imputed_field_count"] == sum(1 for v in imp.values() if v)


def test_gate3_normalized_empty_sources_cover_witnesses():
    rec = normalize_stock_data("NOPE")
    md = rec["_metadata"]
    imp = md["is_imputed"]
    fp = md["field_provenance"]

    assert set(imp.keys()) >= set(fp.keys())
    for k in fp:
        assert imp[k] == (fp[k] < 3)
    missing = [k for k in TOP_LEVEL_SCALARS if k not in imp]
    assert not missing, f"is_imputed lost scalar coverage: {missing}"
    assert md["imputed_field_count"] == sum(1 for v in imp.values() if v)
