"""TCBS was connected to the one branch its users never take.

fetch_vnstock_financials() returns marketCap, pe, pb and eps from the TCBS
public feed, and any one of those pins down a share count. It was called
only from _fallback_worker - the path for symbols TradingView omits
entirely. The 565 symbols with no share witness are not on that path:
TradingView returns a row for them, near-empty but present, so they take
the main loop and never reach TCBS.

These tests pin the wiring, the selection rule that decides who gets a
request, and the unit discriminant that keeps a market cap from being read
in the wrong scale.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_data_service import (
    _market_cap_to_vnd,
    _needs_share_count,
    normalize_stock_data,
)


class TestWhoGetsARequest:
    def test_an_empty_row_needs_one(self):
        assert _needs_share_count({}) is True
        assert _needs_share_count(None) is True

    def test_a_price_only_row_needs_one(self):
        """The shape that was being refused: a row exists, and carries
        nothing that yields a share count."""
        assert _needs_share_count({"close": 20_000.0}) is True

    @pytest.mark.parametrize("witness", [
        "diluted_shares_outstanding_fq",
        "total_shares_outstanding_fq",
        "market_cap_basic",
    ])
    def test_any_share_witness_spends_no_request(self, witness):
        assert _needs_share_count({"close": 20_000.0, witness: 1.0}) is False

    def test_a_reported_total_and_its_per_share_twin_are_enough(self):
        assert _needs_share_count({
            "net_income_ttm": 2e11,
            "earnings_per_share_basic_ttm": 2_000.0,
        }) is False

    def test_half_of_that_pair_is_not_enough(self):
        assert _needs_share_count({"net_income_ttm": 2e11}) is True


class TestMarketCapUnits:
    """A VN listed company is worth 1e10..5e14 VND, i.e. 10..5e5 billions.
    Five orders of magnitude separate the ranges, so the unit is readable
    from the value - and the gap between them is not guessed at."""

    def test_raw_vnd_passes_through(self):
        assert _market_cap_to_vnd(366_000_000_000_000.0) == 366_000_000_000_000.0

    def test_billions_are_scaled_up(self):
        assert _market_cap_to_vnd(366_000.0) == 366_000 * 1e9

    def test_a_tiny_upcom_cap_in_billions_still_scales(self):
        assert _market_cap_to_vnd(12.0) == 12 * 1e9

    def test_the_ambiguous_gap_is_discarded_not_guessed(self):
        assert _market_cap_to_vnd(5e8) is None

    @pytest.mark.parametrize("bad", [None, 0, -1, "", "n/a"])
    def test_nothing_is_not_something(self, bad):
        assert _market_cap_to_vnd(bad) is None


def test_tcbs_market_cap_rescues_a_price_only_row():
    """End to end: TradingView carries a price and nothing else, VNDIRECT
    carries the statements, TCBS carries the market cap. That is enough."""
    vnd = {
        "revenue_ttm": 900_000_000_000.0,
        "net_income_ttm": 200_000_000_000.0,
        "total_assets_fq": 2_000_000_000_000.0,
        "total_equity_fq": 1_000_000_000_000.0,
        "total_debt_fq": 400_000_000_000.0,
        "cash_fq": 150_000_000_000.0,
    }
    tcbs = {"market_cap": 2_000_000_000_000.0, "pe": 10.0, "pb": 2.0, "eps": 2_000.0}

    rec = normalize_stock_data(
        "TST", tv_data={"close": 20_000.0}, vnstock_data=tcbs, vndirect_data=vnd,
    )
    prov = rec["field_provenance"]
    assert prov["shares"] >= 2, "TCBS market cap should pin the share count"
    assert prov["market_cap"] >= 2
    assert rec["shares_out"] == 100_000_000


def test_without_tcbs_the_same_row_is_still_refused():
    """The control. Same payload, no TCBS: the count stays fabricated, and
    the record must keep saying so rather than inventing one."""
    vnd = {
        "revenue_ttm": 900_000_000_000.0,
        "net_income_ttm": 200_000_000_000.0,
        "total_equity_fq": 1_000_000_000_000.0,
    }
    rec = normalize_stock_data("TST", tv_data={"close": 20_000.0}, vndirect_data=vnd)
    assert rec["field_provenance"]["shares"] == 0
