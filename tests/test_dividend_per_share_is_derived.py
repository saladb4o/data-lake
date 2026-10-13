"""dividend_per_share, derived from the yield that was already here.

It was the largest blocking driver at 162 symbols, and nothing in the
codebase ever wrote the key. The resolver asks
res.resolve("dividend_per_share", ("dividend_per_share",)) - one name, no
aliases - so the ask had never once been answered and utilities_3stage_ddm
was suppressed for every company in the universe.

The ingredient was never missing. dividend_yield is measured, carries a
provenance tier, and is normalised to a percentage; the dividend is
price * yield / 100.
"""
import pytest

import services.unified_data_service as uds
from services.valuation_engine import ValuationEngine


def _record(**tv):
    base = {"close": 20_000.0, "total_shares_outstanding_fq": 3e8}
    base.update(tv)
    return uds.normalize_stock_data(
        symbol="TST", exchange="HOSE", name="Test",
        sector_code="7500", sector_name="Tien ich", tv_data=base)


class TestTheDividendIsDerived:
    def test_a_percentage_yield_gives_dong_per_share(self):
        r = _record(dividend_yield_recent=5.0)
        assert r["dividend_per_share"] == pytest.approx(1000.0)

    def test_a_fractional_yield_gives_the_same_answer(self):
        """The vendor sends 5.0 or 0.05 for the same 5%; both must agree.

        This is the unit trap that produced a hundred-fold EBIT error
        earlier in this audit, asked of a different field before it can do
        it again.
        """
        assert (_record(dividend_yield_recent=0.05)["dividend_per_share"]
                == _record(dividend_yield_recent=5.0)["dividend_per_share"])

    def test_the_fallback_column_is_read_too(self):
        r = _record(dividends_yield_current=5.0)
        assert r["dividend_per_share"] == pytest.approx(1000.0)


class TestAZeroDividendIsNeverInvented:
    """A yield the vendor did not report is not a yield of zero.

    normalize's else-branch sets dividend_yield to 0.0 at tier 0. Emitting a
    0.0 dividend from it would hand the DDM a number and turn a refusal into
    an answer - the exact failure the provenance gate exists to prevent.
    Absent, the resolver imputes it and the model stays suppressed.
    """

    def test_no_yield_means_no_key(self):
        assert "dividend_per_share" not in _record()

    def test_a_zero_yield_means_no_key(self):
        assert "dividend_per_share" not in _record(dividend_yield_recent=0.0)

    def test_the_model_stays_suppressed_without_a_yield(self):
        models = ValuationEngine().calculate_all_models("TST", _record())
        ddm = next(m for m in models if m.model_id == "utilities_3stage_ddm")
        assert not ddm.active
        assert "dividend_per_share" in ddm.diagnostics.get("imputed_drivers", [])


class TestProvenanceIsCarried:
    def test_a_derived_dividend_is_tier_2(self):
        r = _record(dividend_yield_recent=5.0)
        assert r["field_provenance"]["dividend_per_share"] == 2

    def test_an_invented_price_poisons_it(self):
        """price is an input, so the 10000.0 fallback must drag it to 0."""
        r = uds.normalize_stock_data(
            symbol="TST", exchange="HOSE", name="Test",
            sector_code="7500", sector_name="Tien ich",
            tv_data={"total_shares_outstanding_fq": 3e8,
                     "dividend_yield_recent": 5.0})
        if "dividend_per_share" in r:
            assert r["field_provenance"]["dividend_per_share"] == 0


class TestTheModelFinallyRuns:
    """The whole point: the ask is answered and the model publishes.

    It also proves the value survives the copy out of the triangles into the
    record, which is where the first attempt at this silently lost it - the
    comment above that copy says a line published upstream "arrives here on
    its own", and the code under it is a hand-written key list.
    """

    def test_the_ddm_is_active_with_a_reported_yield(self):
        models = ValuationEngine().calculate_all_models(
            "TST", _record(dividend_yield_recent=5.0))
        ddm = next(m for m in models if m.model_id == "utilities_3stage_ddm")
        assert ddm.active
        assert ddm.fair_value > 0
