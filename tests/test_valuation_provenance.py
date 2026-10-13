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


class TestEveryPerShareModelDeclaresItsShareCount:
    """A model that divides by shares must name shares as one of its drivers.

    add_model() suppresses a model only when a driver it *declares* was
    invented, so an undeclared input is never checked. Seven models computed
    ``fair_value = equity_value / shares`` while declaring only the drivers
    above the division line, and the share count is not an incidental input
    there: the output is inversely proportional to it. Worse, the suite floors
    it at ``max(shares_out, 1.0)``, so a company with no reported share count
    was valued at its entire equity value per share and published as ACTIVE.

    The universe reaches these models through the sector map - industrial,
    consumer, telecom, REIT and bank companies - so this was not a corner of
    the engine nobody visits. Six sibling models on the same code path
    (ev_ebitda, dcf_2stage_mckinsey, greenwald_epv, acquirers_multiple_ev_ebit,
    p_affo, rim) already declared it, which is what makes the omission an
    oversight rather than a judgement.
    """

    PER_SHARE_MODELS = (
        "rule_of_40_growth", "buffett_owners_earnings", "bank_equity_cash_flow",
        "reit_affo_dcf", "telecom_unbundled_sotp", "industrial_apv",
        "consumer_eva_mva",
    )

    @staticmethod
    def _no_share_count() -> dict:
        """Full statements, no share count - the one gap under test."""
        return {
            "symbol": "NOSH", "price": 20_000.0, "sector_code": "VNIND",
            "revenue": 5e12, "prev_revenue": 4.5e12, "net_income": 4e11,
            "ebit": 6e11, "ebitda": 8e11, "cfo": 7e11, "capital_expenditures": 2e11,
            "equity": 3e12, "debt": 1e12, "cash": 5e11, "total_assets": 6e12,
            "roe": 13.0, "roic": 9.0,
        }

    def test_no_per_share_model_is_active_without_a_share_count(self):
        result = ValuationEngine().get_comprehensive_valuation(
            "NOSH", self._no_share_count())
        by_id = {m.model_id: m for m in result.models}
        offenders = [
            mid for mid in self.PER_SHARE_MODELS
            if mid in by_id and by_id[mid].active
        ]
        assert offenders == [], (
            "these models published a fair value divided by an invented share "
            f"count: {offenders}"
        )

    def test_they_name_shares_among_their_imputed_drivers(self):
        result = ValuationEngine().get_comprehensive_valuation(
            "NOSH", self._no_share_count())
        for model in result.models:
            if model.model_id not in self.PER_SHARE_MODELS:
                continue
            if model.status != "INSUFFICIENT_DATA":
                continue
            assert "shares" in model.diagnostics.get("imputed_drivers", []), (
                f"{model.model_id} was suppressed without naming shares")

    def test_a_real_share_count_puts_them_back(self):
        """The guard must cost nothing when the share count is reported."""
        payload = dict(self._no_share_count(), shares_out=300e6)
        result = ValuationEngine().get_comprehensive_valuation("NOSH", payload)
        by_id = {m.model_id: m for m in result.models}
        suppressed_on_shares = [
            mid for mid in self.PER_SHARE_MODELS
            if mid in by_id
            and "shares" in (by_id[mid].diagnostics.get("imputed_drivers") or [])
        ]
        assert suppressed_on_shares == []


class TestAnOptionalRefinementIsNotADriver:
    """gross_ppe stays undeclared, and that is deliberate.

    buffett_owners_earnings reads it only inside ``if revenue > 0 and
    gross_ppe > 0``, to refine maintenance capex, and falls back to a ratio
    when it is absent. Declaring it would refuse the whole model over an input
    it does not need - the opposite failure to the one above, and one that
    costs coverage rather than trust. The distinction is whether the output is
    a function of the input or merely improved by it.
    """

    def test_missing_gross_ppe_does_not_suppress_owners_earnings(self):
        payload = {
            "symbol": "NOPPE", "price": 20_000.0, "sector_code": "VNIND",
            "shares_out": 300e6, "revenue": 5e12, "prev_revenue": 4.5e12,
            "net_income": 4e11, "ebit": 6e11, "ebitda": 8e11, "cfo": 7e11,
            "capital_expenditures": 2e11, "equity": 3e12, "debt": 1e12,
            "cash": 5e11, "total_assets": 6e12, "roe": 13.0, "roic": 9.0,
        }
        result = ValuationEngine().get_comprehensive_valuation("NOPPE", payload)
        model = next(
            (m for m in result.models if m.model_id == "buffett_owners_earnings"),
            None)
        assert model is not None
        assert "gross_ppe" not in (model.diagnostics.get("imputed_drivers") or [])
