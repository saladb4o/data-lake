"""The valuation engine must not manufacture fundamentals from the price.

Before the provenance layer, every missing input was replaced with a fraction
of market cap (debt = 40%, revenue = 80%, equity = 60%) and every model floored
its output at 10% of market cap. Because market cap is price x shares, a
payload carrying nothing but a price produced 22 confident fair values, all of
them fixed multiples of that price. These tests pin the behaviour that replaced
it: no data means no valuation.
"""
import math

import pytest

from services.valuation_engine import (
    DERIVED,
    IMPUTED,
    REAL,
    InputResolver,
    ValuationEngine,
    ValuationModelsSuite,
)


def _bare(price: float) -> dict:
    """A payload with a price and a share count and no financial statements."""
    return {"symbol": "BARE", "price": price, "shares_out": 300e6, "sector_code": "VNIND"}


class TestNoValuationWithoutData:
    def test_price_only_payload_yields_no_composite(self):
        result = ValuationEngine().get_comprehensive_valuation("BARE", _bare(40_000.0))
        assert result.composite_fair_value == 0.0
        assert [m.model_id for m in result.models if m.active] == []

    def test_every_model_reports_insufficient_data(self):
        result = ValuationEngine().get_comprehensive_valuation("BARE", _bare(40_000.0))
        assert {m.status for m in result.models} == {"INSUFFICIENT_DATA"}
        for model in result.models:
            assert model.diagnostics["imputed_drivers"], model.model_id

    def test_composite_does_not_track_price(self):
        """The regression this whole layer exists to prevent."""
        engine = ValuationEngine()
        values = [
            engine.get_comprehensive_valuation("BARE", _bare(p)).composite_fair_value
            for p in (10_000.0, 20_000.0, 40_000.0, 80_000.0)
        ]
        assert values == [0.0, 0.0, 0.0, 0.0]


class TestProvenancePropagates:
    def test_payload_value_is_real(self):
        r = InputResolver({"revenue": 5e11})
        assert r.resolve("revenue", ("revenue",)) == 5e11
        assert r.provenance["revenue"] == REAL

    def test_derivation_from_real_inputs_is_derived(self):
        r = InputResolver({"net_income": 1e11, "shares_out": 1e8})
        r.resolve("shares", ("shares_out",))
        r.resolve("net_income", ("net_income",))
        r.resolve("eps", ("eps",), derive=(("net_income", "shares"), lambda: 1000.0))
        assert r.provenance["eps"] == DERIVED
        assert r.trustworthy("eps")

    def test_derivation_from_an_imputed_input_is_imputed(self):
        """A formula fed invented numbers is still an invention."""
        r = InputResolver({"shares_out": 1e8})
        r.resolve("shares", ("shares_out",))
        r.resolve("net_income", ("net_income",), impute=lambda: 1e11)
        r.resolve("eps", ("eps",), derive=(("net_income", "shares"), lambda: 1000.0))
        assert r.provenance["net_income"] == IMPUTED
        assert r.provenance["eps"] == IMPUTED
        assert r.is_imputed("eps")

    def test_unknown_field_counts_as_imputed(self):
        assert InputResolver({}).is_imputed("never_resolved")


class TestModelsDeclineRatherThanInvent:
    """Each model returns 0.0 when its driver is unusable, instead of
    substituting a fraction of the market price."""

    PRICE = 25_000.0

    def test_loss_maker_gets_no_pe_valuation(self):
        suite = ValuationModelsSuite()
        assert suite.model_1_blended_pe(
            eps_ttm=-500.0, historical_eps=[-400.0, -450.0, -500.0],
            current_price=self.PRICE,
        ) == 0.0

    def test_negative_book_equity_gets_no_pb_valuation(self):
        assert ValuationModelsSuite().model_4_pb_rhodes_kropf(
            bvps=-1200.0, roe=0.05, ke=0.14, current_price=self.PRICE,
        ) == 0.0

    def test_cash_burner_gets_no_pfcf_valuation(self):
        assert ValuationModelsSuite().model_3_p_fcf(
            fcf_per_share=-800.0, sales_per_share=12_000.0, current_price=self.PRICE,
        ) == 0.0

    def test_non_payer_gets_no_ddm_valuation(self):
        assert ValuationModelsSuite().model_22_utilities_3stage_ddm(
            dividend_per_share=0.0, ke=0.13, current_price=self.PRICE,
        ) == 0.0

    def test_negative_ebitda_gets_no_ev_ebitda_valuation(self):
        assert ValuationModelsSuite().model_6_ev_ebitda(
            ebitda=-2e10, total_debt=1e11, cash_and_equiv=1e9,
            shares_out=1e8, current_price=self.PRICE,
        ) == 0.0

    def test_equity_wiped_out_by_debt_is_reported_as_zero(self):
        """Not floored at 10% of market cap."""
        assert ValuationModelsSuite().model_6_ev_ebitda(
            ebitda=1e9, total_debt=1e13, cash_and_equiv=0.0,
            shares_out=1e8, current_price=self.PRICE,
        ) == 0.0


class TestPriceIsRequiredByEveryModel:
    def test_models_reject_the_old_default_price(self):
        """The 10,000 VND default is gone from all 22 signatures."""
        suite = ValuationModelsSuite()
        with pytest.raises(ValueError, match="requires a positive current_price"):
            suite.model_1_blended_pe(eps_ttm=2000.0, historical_eps=[2000.0])

    def test_models_reject_a_non_finite_price(self):
        with pytest.raises(ValueError):
            ValuationModelsSuite().model_7_p_cf(
                cfo_per_share=1500.0, pat_per_share=1200.0,
                current_price=float("nan"),
            )
