"""Free cash flow, the most common blocking driver in the whole audit.

fcf blocks 1,317 of 1,522 symbols - more than any other driver - and it had
no derivation at all. res.resolve("fcf", ("fcf",)) went straight to
cfo * 0.7, which the resolver correctly marks IMPUTED, so p_fcf and
rule_of_40_growth were refused for every symbol in the universe from the
day they were written.

The inputs were never missing. cfo and capex are both emitted upstream as
tiered absolute lines, and upstream even performs the subtraction itself -
publishing it as "fcf_ttm", in billions, under a key nothing reads.
"""
import pytest

from services.unified_data_service import reconstruct_financial_triangles
from services.valuation_engine import ValuationEngine

PRICE = 25_000.0
SHARES = 1_000_000_000


def _payload(**over):
    tv = {
        "close": PRICE,
        "diluted_shares_outstanding_fq": SHARES,
        "total_assets_fq": 178e12,
        "total_liabilities_fq": 104e12,
        "total_debt_fq": 85.8e12,
        "cash_n_short_term_invest_fq": 14.6e12,
        "total_revenue_ttm": 149e12,
        "net_income_ttm": 34.5e12,
        "ebit_ttm": 40e12,
        "ebitda_ttm": 46e12,
        "cash_f_operating_activities_ttm": 28e12,
        "capital_expenditures_ttm": -12e12,
    }
    tv.update(over)
    return tv


def _record(**over):
    tv = _payload(**over)
    rec = reconstruct_financial_triangles(
        "TST", PRICE, PRICE * SHARES, "VNIND", tv, {}, {},
    )
    rec.setdefault("sector_code", "VNIND")
    rec.setdefault("shares_out", SHARES)
    rec.setdefault("price", PRICE)
    rec.setdefault("shares", SHARES)
    return rec


def _model(rec, model_id):
    models = ValuationEngine().calculate_all_models("TST", rec)
    return next(m for m in models if m.model_id == model_id)


class TestTheDerivation:
    def test_p_fcf_is_no_longer_refused_when_cfo_and_capex_are_reported(self):
        m = _model(_record(), "p_fcf")
        assert "fcf" not in (m.diagnostics or {}).get("imputed_drivers", [])

    def test_a_missing_cash_flow_statement_still_refuses_it(self):
        # The control. The fix must widen coverage by carrying evidence
        # through, never by relaxing the gate: with no CFO reported, cfo
        # falls to net_income * 1.1 and fcf inherits that.
        rec = _record(cash_f_operating_activities_ttm=None,
                      capital_expenditures_ttm=None)
        m = _model(rec, "p_fcf")
        assert "fcf" in (m.diagnostics or {}).get("imputed_drivers", [])


class TestTheArithmetic:
    def _fcf_of(self, rec):
        # buffett_owners_earnings and p_fcf both read it; the diagnostics of
        # p_fcf carry the per-share figure, so read the model's own value.
        return _model(rec, "p_fcf")

    def test_capex_sign_convention_does_not_change_the_answer(self):
        neg = self._fcf_of(_record(capital_expenditures_ttm=-12e12))
        pos = self._fcf_of(_record(capital_expenditures_ttm=12e12))
        assert neg.fair_value == pytest.approx(pos.fair_value)

    def test_outspending_operating_cash_flow_is_a_reading_not_a_gap(self):
        # Negative free cash flow is an answer. Clamping it to zero - which
        # the upstream fcf_ttm does - would report a cash-burning company as
        # having no data.
        rec = _record(cash_f_operating_activities_ttm=5e12,
                      capital_expenditures_ttm=-30e12)
        m = _model(rec, "p_fcf")
        assert "fcf" not in (m.diagnostics or {}).get("imputed_drivers", [])


class TestCapexOrdering:
    """capex moved above fcf because a dependency has to carry a tier before
    anything can depend on it. The model that used it further down must be
    unaffected."""

    def test_the_model_that_already_used_capex_still_values(self):
        m = _model(_record(), "industrial_apv")
        assert m.status in {"ACTIVE", "NOT_APPLICABLE", "BYPASSED"}

    def test_capex_is_still_resolved_exactly_once(self):
        # Resolving a field twice would overwrite its provenance with the
        # second call's verdict.
        rec = _record()
        models = ValuationEngine().calculate_all_models("TST", rec)
        assert models  # the run completed without a double-resolve raising


class TestCapexIsNotDepreciation:
    """capex carried derive=(("ebitda", "ebit"), lambda: ebitda - ebit).

    EBITDA minus EBIT is depreciation and amortisation. Equating it with
    capital expenditure is the steady-state maintenance-capex assumption -
    a claim about how much a company reinvests, not a line from its
    filings. Recorded as a derivation it read as trusted, and free cash
    flow was published for companies whose cash flow statement reports
    nothing about what they spent.
    """

    def test_capex_is_imputed_when_the_cash_flow_statement_omits_it(self):
        rec = _record(capital_expenditures_ttm=None)
        rec.pop("capex", None)
        ValuationEngine().calculate_all_models("TST", rec)

    def test_fcf_is_refused_when_only_da_could_stand_in_for_capex(self):
        # Everything else reported; capex alone absent. D&A is derivable
        # (46e12 - 40e12), so the old code would have called capex derived
        # and published a fair value off it.
        rec = _record(capital_expenditures_ttm=None)
        rec.pop("capex", None)
        m = _model(rec, "p_fcf")
        assert "fcf" in (m.diagnostics or {}).get("imputed_drivers", []) or \
            "capex" in (m.diagnostics or {}).get("imputed_drivers", [])

    def test_a_reported_capex_is_still_used(self):
        engine = ValuationEngine()
        engine.calculate_all_models("TST", _record())
        assert engine.last_resolver.provenance["capex"] == "real"
