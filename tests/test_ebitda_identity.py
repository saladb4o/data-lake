"""EBITDA = EBIT + D&A, and what it replaces.

The engine derived EBITDA as ebit * 1.25 - an assertion that depreciation
is exactly a quarter of operating profit for every company - and declared
it through the resolver's `derive` argument, so it was recorded as DERIVED
and therefore trusted. The resolver's own docstring calls that an
assumption wearing a formula.

D&A was tiered upstream from the beginning and never published, so the
identity was unavailable and the multiplier stood in for it.

These tests pin the narrower, correct behaviour: a reported D&A gives the
identity, an absent one is refused rather than guessed. That values fewer
companies than the multiplier did, which is the point.
"""
import pytest

from services.unified_data_service import reconstruct_financial_triangles
from services.valuation_engine import ValuationEngine

PRICE = 25_000.0
SHARES = 1_000_000_000


def _record(**over):
    tv = {
        "close": PRICE,
        "diluted_shares_outstanding_fq": SHARES,
        "total_assets_fq": 178e12,
        "total_liabilities_fq": 104e12,
        "total_equity_fq": 74e12,
        "total_debt_fq": 85.8e12,
        "cash_n_short_term_invest_fq": 14.6e12,
        "total_revenue_ttm": 149e12,
        "net_income_ttm": 34.5e12,
        "ebit_ttm": 40e12,
        "cash_f_operating_activities_ttm": 28e12,
        "capital_expenditures_ttm": -12e12,
        "depreciation_and_amortization_ttm": 6e12,
    }
    tv.update(over)
    tv = {k: v for k, v in tv.items() if v is not None}
    rec = reconstruct_financial_triangles(
        "TST", PRICE, PRICE * SHARES, "VNIND", tv, {}, {},
    )
    rec.setdefault("sector_code", "VNIND")
    rec.setdefault("price", PRICE)
    rec.setdefault("shares", SHARES)
    rec.setdefault("shares_out", SHARES)
    return rec


def _imputed(rec, model_id="ev_ebitda"):
    models = ValuationEngine().calculate_all_models("TST", rec)
    m = next(x for x in models if x.model_id == model_id)
    return (m.diagnostics or {}).get("imputed_drivers", [])


class TestDAReachesTheEngine:
    def test_the_line_is_published(self):
        # Tiered upstream since the beginning, never emitted, so the engine
        # could not see it.
        assert "da" in _record()

    def test_it_carries_its_own_tier(self):
        tiers = _record()["field_provenance"]
        assert tiers["da"] == tiers["da"]
        assert tiers["da"] >= 2


class TestTheIdentity:
    def test_a_reported_da_lets_ebitda_clear_the_gate(self):
        assert "ebitda" not in _imputed(_record())

    def test_an_absent_da_is_refused_rather_than_multiplied(self):
        # The multiplier survives as an impute, where it is marked imputed.
        # Previously this same company was valued on ebit * 1.25 and the
        # result was recorded as derived.
        rec = _record(depreciation_and_amortization_ttm=None,
                      cash_flow_depreciation_n_amortization_ttm=None)
        if rec["field_provenance"].get("da", 0) >= 2:
            pytest.skip("D&A was reconstructed from another witness")
        assert "ebitda" in _imputed(rec)

    def test_an_imputed_ebit_still_blocks_ebitda(self):
        # EBITDA is never better than the operating line it is built on.
        rec = _record(ebit_ttm=None, pretax_income_ttm=None,
                      operating_margin_ttm=None,
                      depreciation_and_amortization_ttm=None)
        assert "ebitda" in _imputed(rec)


class TestItIsNarrowerOnPurpose:
    def test_a_reported_da_is_used_rather_than_the_multiplier(self):
        # ebit 40e12, D&A 6e12. The identity gives 46e12; the old multiplier
        # would give 50e12 regardless of what the company reported. Grepping
        # the source for the old expression would only match the comment
        # explaining it, so check the arithmetic instead.
        rec = _record(ebit_ttm=40e12, depreciation_and_amortization_ttm=6e12)
        models = ValuationEngine().calculate_all_models("TST", rec)
        m = next(x for x in models if x.model_id == "ev_ebitda")
        assert "ebitda" not in (m.diagnostics or {}).get("imputed_drivers", [])
        assert rec["ebitda"] == pytest.approx(46e12, rel=0.02)
