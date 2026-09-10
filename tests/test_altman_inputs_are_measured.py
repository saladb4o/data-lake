"""Altman Z'' must stand on reported lines, not on fractions of the balance sheet.

Three inputs the score needs were unavailable for the whole life of the
engine, each for a different reason, and all three failures were silent:

  working_capital   - current assets and current liabilities are both
                      reconstructed and tiered upstream, and neither was
                      ever published, so the subtraction had nowhere to
                      happen and the impute (assets - liabilities) * 0.25
                      stood in for it.
  current_liabilities - worse: the vendor's own total_current_liabilities_fq
                      was read into a local and never given a tier at all
                      except on the Source-0 path, so a reported figure was
                      indistinguishable from a missing one.
  retained_earnings - requested in TV_COLUMNS and read by no line of code in
                      the repository, while the score asserted that retained
                      earnings are 20% of book equity for every company.

prev_revenue belongs to the same family and is pinned here too. Its impute
was revenue * (1 - g) using the engine's own FORECAST growth, which makes
the historical base a function of the forecast and lets the forecast read as
confirmed by history. The reported year-on-year growth rate breaks the loop.

The tests below pin both directions, as every provenance test in this suite
must: the lines arrive when the vendor reports them, and nothing is invented
when the vendor is silent.
"""

import pytest

from services.unified_data_service import normalize_stock_data
from services.valuation_engine import InputResolver
from tests.test_absolute_lines_reach_the_engine import reported_payload

CURRENT_ASSETS = 60e12
CURRENT_LIABILITIES = 40e12
RETAINED = 30e12
REVENUE = 149e12
GROWTH_PCT = 10.0


def payload(**overrides):
    tv = reported_payload()
    tv["total_current_assets_fq"] = CURRENT_ASSETS
    tv["total_current_liabilities_fq"] = CURRENT_LIABILITIES
    tv["retained_earnings_fq"] = RETAINED
    tv["total_revenue_yoy_growth_fq"] = GROWTH_PCT
    tv.update(overrides)
    return {k: v for k, v in tv.items() if v is not None}


def record(**overrides):
    return normalize_stock_data("TEST", tv_data=payload(**overrides))


def without(key):
    tv = payload()
    tv.pop(key, None)
    return normalize_stock_data("TEST", tv_data=tv)


class TestTheCurrentHalvesAreEvidence:
    def test_a_reported_current_liability_earns_a_tier(self):
        rec = record()
        assert rec["field_provenance"].get("current_liabilities") == 3, (
            "the vendor reported this line; leaving it untiered made a "
            "reported figure read as a missing one"
        )

    @pytest.mark.parametrize("line,expected", [
        ("current_assets", CURRENT_ASSETS),
        ("current_liabilities", CURRENT_LIABILITIES),
    ])
    def test_the_half_reaches_the_record(self, line, expected):
        assert record()[line] == expected


class TestWorkingCapitalIsASubtraction:
    def test_it_is_the_difference_of_the_two_halves(self):
        assert record()["working_capital"] == CURRENT_ASSETS - CURRENT_LIABILITIES

    def test_it_clears_the_gate_when_both_halves_are_reported(self):
        tier = record()["field_provenance"]["working_capital"]
        assert tier >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER

    def test_a_guessed_current_asset_drags_it_below_the_gate(self):
        # With no reported current assets the ladder falls to 40% of total
        # assets at tier 1. A working capital subtracted from that must not
        # read as observed.
        rec = without("total_current_assets_fq")
        assert rec["field_provenance"]["current_assets"] == 1
        assert rec["field_provenance"]["working_capital"] < \
            InputResolver.MIN_TRUSTED_UPSTREAM_TIER

    def test_it_is_not_published_when_a_half_is_missing(self):
        rec = without("total_current_liabilities_fq")
        assert rec.get("working_capital") is None, (
            "a missing half must leave the line unpublished; publishing a "
            "stand-in here is what the impute already does, and the impute "
            "at least admits to being one"
        )


class TestRetainedEarningsIsReportedOrAbsent:
    def test_it_arrives_when_the_vendor_reports_it(self):
        rec = record()
        assert rec["retained_earnings"] == RETAINED
        assert rec["field_provenance"]["retained_earnings"] == 3

    def test_there_is_no_second_rung(self):
        # Accumulated profit cannot be inferred from the rest of the balance
        # sheet without assuming what the score is being asked to measure.
        assert without("retained_earnings_fq").get("retained_earnings") is None


class TestTheScoreStopsRestingOnConstants:
    def test_every_altman_input_clears_the_gate(self):
        res = InputResolver(record())
        for field in ("working_capital", "retained_earnings", "ebit",
                      "total_assets", "total_liabilities"):
            res.resolve(field, (field,), impute=lambda: 0.0)
        assert res.trustworthy("working_capital", "retained_earnings", "ebit",
                               "total_assets", "total_liabilities")

    def test_a_silent_vendor_still_makes_it_unreliable(self):
        tv = payload()
        tv.pop("retained_earnings_fq")
        tv.pop("total_current_liabilities_fq")
        res = InputResolver(normalize_stock_data("TEST", tv_data=tv))
        for field in ("working_capital", "retained_earnings", "ebit",
                      "total_assets", "total_liabilities"):
            res.resolve(field, (field,), impute=lambda: 0.0)
        assert not res.trustworthy("working_capital", "retained_earnings")


class TestPrevRevenueComesFromReportedGrowth:
    def test_it_inverts_the_reported_growth_rate(self):
        rec = record()
        assert rec["prev_revenue"] == pytest.approx(
            REVENUE / (1.0 + GROWTH_PCT / 100.0), rel=1e-6)

    def test_it_clears_the_gate_when_the_growth_was_reported(self):
        assert record()["field_provenance"]["prev_revenue"] >= \
            InputResolver.MIN_TRUSTED_UPSTREAM_TIER

    def test_a_filled_growth_rate_poisons_it(self):
        # With no growth column the ladder fills 10.0 at tier 1; a prior year
        # recovered from a constant is not a measurement of anything.
        rec = without("total_revenue_yoy_growth_fq")
        assert rec["field_provenance"]["rev_1y_growth"] == 1
        assert rec["field_provenance"]["prev_revenue"] < \
            InputResolver.MIN_TRUSTED_UPSTREAM_TIER

    def test_a_total_collapse_is_not_divided_by_zero(self):
        rec = record(total_revenue_yoy_growth_fq=-100.0)
        assert rec.get("prev_revenue") is None
