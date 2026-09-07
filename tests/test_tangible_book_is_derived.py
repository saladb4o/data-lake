"""Tangible book value per share, and the ambiguity that governs it.

tbvps blocks 1,177 of 1,522 symbols and had no derivation: it went straight
to bvps * 0.9, which the resolver marks IMPUTED, so p_tbv was refused for
every symbol carrying it.

TBV = equity - goodwill - intangibles is trivial arithmetic. What is not
trivial is that TradingView omits a null column entirely, so an absent
goodwill_fq means either "no goodwill" or "not reported", and the payload
cannot tell them apart. Reading absence as zero inflates tangible book
above the truth, which for a floor valuation is the wrong direction. The
line is therefore published only when the vendor reports at least one of
the two.
"""
import pytest

from services.unified_data_service import reconstruct_financial_triangles
from services.valuation_engine import ValuationEngine

PRICE = 25_000.0
SHARES = 1_000_000_000
EQUITY = 74e12


def _record(**over):
    tv = {
        "close": PRICE,
        "diluted_shares_outstanding_fq": SHARES,
        "total_assets_fq": 178e12,
        "total_liabilities_fq": 104e12,
        "total_equity_fq": EQUITY,
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
    tv = {k: v for k, v in tv.items() if v is not None}
    rec = reconstruct_financial_triangles(
        "TST", PRICE, PRICE * SHARES, "VNFIN", tv, {}, {},
    )
    rec.setdefault("sector_code", "VNFIN")
    rec.setdefault("price", PRICE)
    rec.setdefault("shares", SHARES)
    rec.setdefault("shares_out", SHARES)
    return rec


def _imputed(rec, model_id="p_tbv"):
    models = ValuationEngine().calculate_all_models("TST", rec)
    m = next(x for x in models if x.model_id == model_id)
    return (m.diagnostics or {}).get("imputed_drivers", [])


class TestWhenTheVendorReportsTheLines:
    def test_both_reported_publishes_tangible_equity(self):
        rec = _record(goodwill_fq=4e12, intangibles_net_fq=2e12)
        assert rec["tangible_equity"] == pytest.approx(EQUITY - 6e12)

    def test_a_reported_zero_goodwill_still_counts_as_evidence(self):
        # Zero reported is a reading. It is the *absence* of the column that
        # carries no information, not the value nought.
        rec = _record(goodwill_fq=0.0, intangibles_net_fq=2e12)
        assert rec["tangible_equity"] == pytest.approx(EQUITY - 2e12)

    def test_one_of_the_two_is_enough(self):
        # Reporting either line is evidence that the vendor covers this part
        # of the balance sheet for this company.
        rec = _record(intangibles_net_fq=2e12)
        assert "tangible_equity" in rec

    def test_it_inherits_the_equity_tier(self):
        rec = _record(goodwill_fq=4e12)
        tiers = rec["field_provenance"]
        assert tiers["tangible_equity"] == tiers["total_equity"]

    def test_tbvps_is_no_longer_imputed(self):
        rec = _record(goodwill_fq=4e12, intangibles_net_fq=2e12)
        assert "tbvps" not in _imputed(rec)


class TestWhenNeitherIsReported:
    """The half that matters more. Widening coverage by assuming the absent
    column is zero would be the fabrication this gate exists to catch."""

    def test_nothing_is_published(self):
        assert "tangible_equity" not in _record()

    def test_tbvps_stays_refused(self):
        assert "tbvps" in _imputed(_record())

    def test_equity_itself_is_unaffected(self):
        # Only the tangible line is withheld; the balance sheet is intact.
        rec = _record()
        assert rec["field_provenance"]["total_equity"] >= 2


class TestTheArithmeticIsNotOptimistic:
    def test_tangible_equity_never_exceeds_equity(self):
        rec = _record(goodwill_fq=4e12, intangibles_net_fq=2e12)
        assert rec["tangible_equity"] < rec["equity"]

    def test_a_company_with_no_intangibles_reports_them_equal(self):
        rec = _record(goodwill_fq=0.0, intangibles_net_fq=0.0)
        assert rec["tangible_equity"] == pytest.approx(rec["equity"])
