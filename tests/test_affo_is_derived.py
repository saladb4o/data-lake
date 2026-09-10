"""AFFO, derived from the cash flows rather than left to an impute.

res.resolve("affo", ("affo",)) asks by one name with no aliases and no
derivation, and nothing in this repository writes the key. So the ask has
never once been answered: every company fell to the impute, was marked
imputed, and both models that declare affo as a driver - p_affo and
reit_affo_dcf - were suppressed for the whole universe. The same shape as
dividend_per_share, which was the fifteenth instance of it.

The formula is the part worth pinning. AFFO is FFO less the capex needed to
keep the portfolio earning; net income + D&A is FFO, and publishing FFO
under the name AFFO overstates it by exactly the figure the name exists to
subtract. Cash from operations less capital spending is the cash-basis
proxy and errs the other way.
"""
import pytest

from services.valuation_engine import ValuationEngine


def _models(**fundamentals):
    base = {
        "price": 20_000.0, "shares": 3e8, "market_cap_vnd": 6e12,
        "net_income": 5e11, "revenue": 3e12, "equity": 4e12,
        "field_provenance": {
            "price": 3, "shares": 3, "market_cap": 3, "net_income": 3,
            "revenue": 3, "equity": 3,
        },
    }
    tiers = fundamentals.pop("_tiers", {})
    base.update(fundamentals)
    base["field_provenance"].update(tiers)
    return ValuationEngine().calculate_all_models("TST", base)


def _driver(models, model_id, name):
    model = next(m for m in models if m.model_id == model_id)
    return model, model.diagnostics.get("imputed_drivers", []) or []


class TestTheFormulaIsAffoAndNotFfo:
    def test_it_is_operating_cash_flow_less_capex(self):
        models = _models(cfo=9e11, capex=2e11,
                         _tiers={"cfo": 3, "capex": 3})
        model, imputed = _driver(models, "p_affo", "affo")
        assert "affo" not in imputed

    def test_it_is_not_net_income_plus_da(self):
        # The overstating version. With D&A present and the cash flows
        # absent, an NI + D&A derivation would answer; this one must not,
        # because that number is FFO and would be published as AFFO.
        models = _models(da=4e11, _tiers={"da": 3})
        model, imputed = _driver(models, "p_affo", "affo")
        assert "affo" in imputed

    def test_capex_sign_does_not_change_the_answer(self):
        # Vendors disagree on whether capital spending is negative.
        positive = _models(cfo=9e11, capex=2e11, _tiers={"cfo": 3, "capex": 3})
        negative = _models(cfo=9e11, capex=-2e11, _tiers={"cfo": 3, "capex": 3})
        a = next(m for m in positive if m.model_id == "p_affo")
        b = next(m for m in negative if m.model_id == "p_affo")
        assert a.fair_value == pytest.approx(b.fair_value)


class TestItStaysFailClosed:
    """A company without the cash flows keeps the impute and stays refused.

    That is today's behaviour and the change must not widen it: the point
    is to answer the ask where the lines exist, not to manufacture an AFFO
    where they do not.
    """

    def test_no_cash_flows_leaves_the_model_refused(self):
        models = _models()
        model, imputed = _driver(models, "p_affo", "affo")
        assert not model.active
        assert "affo" in imputed

    def test_cfo_without_capex_is_not_enough(self):
        models = _models(cfo=9e11, _tiers={"cfo": 3})
        model, imputed = _driver(models, "p_affo", "affo")
        assert "affo" in imputed

    def test_an_imputed_cfo_does_not_produce_a_real_affo(self):
        # A derivation whose input was invented is an assumption wearing a
        # formula. cfo carries its own impute (net_income * 1.1), and affo
        # is derived from cfo and capex rather than from fcf precisely so
        # that an invented cash flow cannot be laundered into a driver.
        models = _models(cfo=9e11, capex=2e11,
                         _tiers={"cfo": 1, "capex": 3})
        model, imputed = _driver(models, "p_affo", "affo")
        assert "affo" in imputed
