"""
Tests for normalize_stock_data metadata honesty (M3 acceptance gate).

Guarantees under test:
  1. Full TV data -> _metadata.is_imputed covers every scalar field; core
     reported fields are flagged False.
  2. Empty sources -> is_real_data False, provenance_tier "Tier 0...",
     imputed_field_count > 0.
  3. Mixed sources -> honest flags; top-level keys unchanged vs golden list
     (downstream compatibility: screener UI, stock_service, backtest_service).

No network access: normalize_stock_data is pure given dict inputs.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_data_service import normalize_stock_data

# Golden top-level key list of the normalized record (order-insensitive set).
GOLDEN_KEYS = {
    "symbol", "name", "exchange", "price", "change_pct", "market_cap",
    "sector_code", "sector_name", "industry",
    "pe", "pb", "ps", "peg", "peg_sales", "eps", "dividend_yield",
    "roe", "roa", "gross_margin", "op_margin", "net_margin", "core_pat_ratio",
    "rev_1y_growth", "rev_3y_cagr", "rev_5y_growth",
    "pat_1y_growth", "pat_3y_cagr", "pat_5y_growth", "eps_3y_cagr",
    "de_ratio", "net_de_ratio", "current_ratio", "quick_ratio",
    "interest_coverage", "cash_to_assets", "rule_of_40", "roic", "fcf_ttm",
    "cfo_to_pat", "share_dilution_3y", "ebit_expansion", "operating_leverage",
    "dilution_spread", "is_cyclical", "size_category", "size_damper",
    "_metadata",
}

# Identity / classification keys that are NOT fundamental scalars and thus
# carry no entry in the is_imputed map. "price" is merged from raw sources
# before the engine runs, so the engine tracks no provenance for it.
NON_SCALAR_KEYS = {
    "symbol", "name", "exchange", "price", "change_pct", "sector_code",
    "sector_name", "industry", "is_cyclical", "size_category", "size_damper",
    "_metadata",
}

CORE_REPORTED_FIELDS = ["market_cap", "pe", "pb", "eps", "roe"]


def _full_tv_data() -> dict:
    """Realistic fully-populated TradingView scanner payload."""
    return {
        "description": "FPT Corp",
        "exchange": "HOSE",
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
        "quick_ratio_fq": 1.7,
        "gross_margin_ttm": 24.5,
        "operating_margin_ttm": 21.3,
        "net_margin_ttm": 17.0,
        "return_on_equity_fq": 33.3,
        "price_earnings_ttm": 34.3,
        "price_book_fq": 11.4,
        "dividend_yield_recent": 1.1,
    }


def test_full_tv_is_imputed_map_and_core_fields_false():
    rec = normalize_stock_data("FPT", tv_data=_full_tv_data())
    md = rec["_metadata"]

    imp = md["is_imputed"]
    assert isinstance(imp, dict) and len(imp) > 0

    # Every fundamental scalar exposed at the top level must be covered.
    scalars = GOLDEN_KEYS - NON_SCALAR_KEYS
    missing = [k for k in scalars if k not in imp]
    assert not missing, f"is_imputed missing scalar fields: {missing}"

    # Core reported fields must NOT be flagged as imputed.
    for k in CORE_REPORTED_FIELDS:
        assert imp[k] is False, f"{k} should be reported (is_imputed=False)"

    assert md["imputed_field_count"] == sum(1 for v in imp.values() if v)
    assert md["imputed_field_count"] < len(imp), (
        "full TV payload should leave most fields un-imputed"
    )
    assert md["is_real_data"] is True


def test_empty_sources_honest_discard():
    rec = normalize_stock_data("NOPE", tv_data=None, vnstock_data=None, yf_data=None)
    md = rec["_metadata"]

    assert md["sources_used"] == ["fallback"]
    assert md["is_real_data"] is False
    assert md["provenance_tier"].startswith("Tier 0")
    assert md["is_valid_fundamental"] is False
    assert md["imputed_field_count"] > 0

    imp = md["is_imputed"]
    scalars = GOLDEN_KEYS - NON_SCALAR_KEYS
    missing = [k for k in scalars if k not in imp]
    assert not missing, f"is_imputed missing scalar fields: {missing}"


def test_mixed_sources_honest_flags_and_golden_keys():
    tv = {
        "close": 25000.0,
        "change": -0.4,
        "diluted_shares_outstanding_fq": 100_000_000.0,
        "total_assets_fq": 50_000_000_000_000.0,
        "total_liabilities_fq": 30_000_000_000_000.0,
    }
    vn = {"pe": 12.5, "pb": 2.2, "roe": 18.0, "eps": 3500.0, "market_cap": 8_500_000_000_000.0}

    rec = normalize_stock_data("MIX", tv_data=tv, vnstock_data=vn, yf_data=None)

    # Downstream compatibility: exact golden top-level key set.
    assert set(rec.keys()) == GOLDEN_KEYS, (
        f"top-level key drift: "
        f"extra={set(rec.keys()) - GOLDEN_KEYS}, missing={GOLDEN_KEYS - set(rec.keys())}"
    )

    md = rec["_metadata"]
    assert set(md.keys()) >= {
        "sources_used", "is_real_data", "data_quality_score", "provenance_tier",
        "is_valid_fundamental", "field_provenance", "is_imputed",
        "imputed_field_count", "synced_at",
    }

    # Real sources contributed AND fundamentals valid -> honest True.
    assert "tradingview" in md["sources_used"]
    assert "vnstock" in md["sources_used"]
    assert md["is_real_data"] is bool(md["is_valid_fundamental"])
    assert md["is_real_data"] is True

    imp = md["is_imputed"]
    scalars = GOLDEN_KEYS - NON_SCALAR_KEYS
    assert not [k for k in scalars if k not in imp]

    # Mixed payload: some triangulated/filled, some reported.
    assert md["imputed_field_count"] > 0
    assert md["imputed_field_count"] < len(imp)


def test_price_only_source_honest_flag_consistency():
    # Price-only TV snapshot: source present; the engine's firebreak counts
    # "close" as real TV data, so is_real_data must simply mirror
    # is_valid_fundamental honestly (never hardcoded).
    rec = normalize_stock_data("PRC", tv_data={"close": 20000.0})
    md = rec["_metadata"]

    assert "tradingview" in md["sources_used"]
    assert md["is_real_data"] is bool(md["is_valid_fundamental"])
    assert isinstance(md["imputed_field_count"], int)
    assert md["imputed_field_count"] == sum(1 for v in md["is_imputed"].values() if v)
