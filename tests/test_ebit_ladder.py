"""EBIT, the driver blocking most of the refusals that carry good data.

Six of the 22 valuation models take EBIT, and VNIND - the sector of 155 of
the 156 symbols refused despite tier-2-or-better data - offers three of
them. Until now EBIT had exactly one derivation, EBITDA minus D&A, so a
company without a reported EBITDA had no operating line at all.

Its income statement usually states one anyway: pretax income and interest
expense were already being read for net income and then left unused.
"""
import pytest

from services.unified_data_service import normalize_stock_data


def _rec(**tv):
    base = {"close": 20_000.0, "total_equity_fq": 4.0e11}
    base.update(tv)
    return normalize_stock_data("TST", tv_data=base)


class TestTheReportedLineStillWins:
    def test_a_stated_ebit_is_taken_at_vendor_tier(self):
        rec = _rec(ebit_ttm=8.0e10)
        assert rec["ebit"] == pytest.approx(8.0e10)
        assert rec["field_provenance"]["ebit"] == 3

    def test_a_stated_ebit_outranks_the_identity(self):
        # Both available: the reported figure is not second-guessed.
        rec = _rec(ebit_ttm=8.0e10, pretax_income_ttm=5.0e10,
                   interest_expense_on_debt_ttm=1.0e10)
        assert rec["ebit"] == pytest.approx(8.0e10)


class TestTheIdentity:
    """EBIT = pretax income + interest expense."""

    def test_it_fires_when_both_lines_are_reported(self):
        rec = _rec(pretax_income_ttm=5.0e10, interest_expense_on_debt_ttm=1.0e10)
        assert rec["ebit"] == pytest.approx(6.0e10)

    def test_it_is_triangulated_not_reported(self):
        # Two reported lines combined is tier 2. Calling it tier 3 would
        # claim a vendor published a figure that no vendor published.
        rec = _rec(pretax_income_ttm=5.0e10, interest_expense_on_debt_ttm=1.0e10)
        assert rec["field_provenance"]["ebit"] == 2

    def test_a_negative_interest_convention_adds_back_the_same_amount(self):
        # The sign is not fixed across rows; the identity needs the
        # magnitude added back either way.
        pos = _rec(pretax_income_ttm=5.0e10, interest_expense_on_debt_ttm=1.0e10)
        neg = _rec(pretax_income_ttm=5.0e10, interest_expense_on_debt_ttm=-1.0e10)
        assert pos["ebit"] == pytest.approx(neg["ebit"])

    def test_a_loss_making_company_keeps_its_negative_operating_line(self):
        # A real negative EBIT is an answer. Clamping it to zero would turn
        # a loss into missing data.
        rec = _rec(pretax_income_ttm=-8.0e10, interest_expense_on_debt_ttm=1.0e10)
        assert rec["ebit"] < 0

    def test_one_line_alone_does_not_fire_it(self):
        assert _rec(pretax_income_ttm=5.0e10)["field_provenance"].get("ebit", 0) != 2


class TestTheMarginRung:
    def test_revenue_times_a_reported_operating_margin_is_triangulated(self):
        rec = _rec(total_revenue_ttm=1.0e12, operating_margin_ttm=12.0)
        assert rec["ebit"] == pytest.approx(1.2e11)
        assert rec["field_provenance"]["ebit"] == 2

    def test_the_identity_outranks_the_margin(self):
        # Two statement lines beat a line times a ratio.
        rec = _rec(total_revenue_ttm=1.0e12, operating_margin_ttm=12.0,
                   pretax_income_ttm=5.0e10, interest_expense_on_debt_ttm=1.0e10)
        assert rec["ebit"] == pytest.approx(6.0e10)

    def test_a_margin_without_revenue_does_not_fire_it(self):
        rec = _rec(operating_margin_ttm=12.0)
        assert rec["field_provenance"].get("ebit", 0) < 2


class TestItStillRefusesToInvent:
    def test_nothing_to_build_it_from_leaves_it_absent(self):
        # The one thing this must not do is back-solve EBIT from revenue
        # times a sector median: that is the market cap talking, not the
        # company, and it is what the provenance gate exists to catch.
        rec = _rec(total_revenue_ttm=1.0e12)
        assert rec["field_provenance"].get("ebit", 0) < 2
