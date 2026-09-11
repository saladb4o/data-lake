"""The lake fills what the live fetch could not, and nothing else.

scripts/build_historical_fundamentals.py reads
api-finfo.vndirect.com.vn/v4/financial_statements - the same URL
fetch_vndirect_financials calls, through the same item-code table. So the
lake is not a new source and cannot be sold as one. What it is, is the
same vendor's last successful answer, kept: a live fetch that times out
or is rate limited returns {} and takes every statement line with it,
while the lake still holds the quarter that was fetched before.

Three ways that could go wrong quietly, and a test for each. Publishing a
quarter's flow under a name that promises twelve months. Overwriting a
fresh figure with a stale one. Writing into the dict the live fetcher
caches, so lake figures come back later wearing the live fetch's name.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import services.unified_data_service as uds


def _quarter(revenue=1.0e12, **extra):
    record = {"revenue": revenue, "net_income": 1.0e11, "ebit": 2.0e11,
              "cfo": 3.0e11, "capex": -4.0e11, "depreciation": 5.0e10,
              "total_assets": 9.0e12, "equity": 4.0e12, "debt": 2.0e12,
              "cash": 1.0e12, "gross_ppe": 3.0e12,
              "fiscal_date": "2025-06-30"}
    record.update(extra)
    return record


class _Lake:
    def __init__(self, quarters):
        self._quarters = quarters

    def quarters_for(self, symbol):
        return dict(self._quarters)


@pytest.fixture
def four_quarters(monkeypatch):
    quarters = {code: _quarter() for code in
                ("2025-Q2", "2025-Q1", "2024-Q4", "2024-Q3")}
    monkeypatch.setattr(uds, "_get_fundamentals_lake", lambda: _Lake(quarters))
    return quarters


class TestAQuarterIsNeverPublishedAsAYear:
    def test_four_consecutive_quarters_are_summed(self, four_quarters):
        out = uds.load_lake_symbol_data("FPT")
        assert out["revenue_ttm"] == pytest.approx(4.0e12)

    def test_three_quarters_publish_no_ttm_at_all(self, monkeypatch):
        quarters = {code: _quarter() for code in
                    ("2025-Q2", "2025-Q1", "2024-Q4")}
        monkeypatch.setattr(uds, "_get_fundamentals_lake",
                            lambda: _Lake(quarters))
        out = uds.load_lake_symbol_data("FPT")
        assert "revenue_ttm" not in out
        assert out["total_assets_fq"] == pytest.approx(9.0e12)

    def test_a_gap_in_the_window_publishes_no_ttm(self, monkeypatch):
        quarters = {code: _quarter() for code in
                    ("2025-Q2", "2025-Q1", "2024-Q3", "2024-Q2")}
        monkeypatch.setattr(uds, "_get_fundamentals_lake",
                            lambda: _Lake(quarters))
        assert "revenue_ttm" not in uds.load_lake_symbol_data("FPT")

    def test_one_missing_line_drops_only_that_flow(self, monkeypatch):
        quarters = {code: _quarter() for code in
                    ("2025-Q2", "2025-Q1", "2024-Q4", "2024-Q3")}
        del quarters["2024-Q4"]["cfo"]
        monkeypatch.setattr(uds, "_get_fundamentals_lake",
                            lambda: _Lake(quarters))
        out = uds.load_lake_symbol_data("FPT")
        assert "cfo_ttm" not in out
        assert out["revenue_ttm"] == pytest.approx(4.0e12)

    def test_capex_is_published_as_a_magnitude(self, four_quarters):
        """vnd publishes abs(capex); a sign flip here would invert fcf."""
        assert uds.load_lake_symbol_data("FPT")["capex_ttm"] > 0


class TestTheBalanceSheetComesFromTheLatestQuarter:
    def test_it_reads_the_newest_quarter_not_the_first_key(self, monkeypatch):
        quarters = {"2024-Q3": _quarter(), "2025-Q2": _quarter(),
                    "2025-Q1": _quarter(), "2024-Q4": _quarter()}
        quarters["2025-Q2"]["cash"] = 7.77e12
        monkeypatch.setattr(uds, "_get_fundamentals_lake",
                            lambda: _Lake(quarters))
        assert uds.load_lake_symbol_data("FPT")["cash_fq"] == pytest.approx(7.77e12)

    def test_it_says_which_quarter_it_read(self, four_quarters):
        assert uds.load_lake_symbol_data("FPT")["lake_quarter"] == "2025-Q2"


class TestNoLakeIsNotAnError:
    def test_an_absent_lake_is_an_empty_answer(self, monkeypatch):
        monkeypatch.setattr(uds, "_get_fundamentals_lake", lambda: None)
        assert uds.load_lake_symbol_data("FPT") == {}

    def test_a_symbol_the_lake_never_saw_is_an_empty_answer(self, monkeypatch):
        monkeypatch.setattr(uds, "_get_fundamentals_lake", lambda: _Lake({}))
        assert uds.load_lake_symbol_data("NOPE") == {}


class TestTheMergeFillsGapsAndOnlyGaps:
    """These call normalize_stock_data, which is the seam the screener
    actually goes through. The triangles solver runs for real; only the
    lake and the network are replaced."""

    def _unified(self, monkeypatch, vnd, lake):
        monkeypatch.setattr(uds, "load_lake_symbol_data", lambda s: dict(lake))
        monkeypatch.setattr(uds, "load_source0_symbol_data", lambda s: None)
        return uds.normalize_stock_data(
            symbol="FPT", vndirect_data=vnd, tv_data={"close": 100000.0},
            enable_source0_fallback=False)

    def test_a_line_the_live_fetch_missed_is_filled(self, monkeypatch):
        out = self._unified(monkeypatch, {"revenue_ttm": 5.0e12},
                            {"total_debt_fq": 2.0e12, "lake_quarter": "2025-Q2"})
        assert "total_debt_fq" in out.get("lake_filled_fields", [])

    def test_a_line_the_live_fetch_answered_is_left_alone(self, monkeypatch):
        out = self._unified(monkeypatch, {"total_debt_fq": 9.9e12},
                            {"total_debt_fq": 2.0e12, "lake_quarter": "2025-Q2"})
        assert "total_debt_fq" not in out.get("lake_filled_fields", [])

    def test_it_records_which_quarter_the_stand_in_came_from(self, monkeypatch):
        out = self._unified(monkeypatch, {},
                            {"total_debt_fq": 2.0e12, "lake_quarter": "2025-Q2"})
        assert out.get("lake_quarter") == "2025-Q2"

    def test_it_does_not_write_into_the_callers_dict(self, monkeypatch):
        """fetch_vndirect_financials hands out the object it caches."""
        cached = {"revenue_ttm": 5.0e12}
        self._unified(monkeypatch, cached,
                      {"total_debt_fq": 2.0e12, "lake_quarter": "2025-Q2"})
        assert cached == {"revenue_ttm": 5.0e12}

    def test_no_lake_reads_as_nothing_filled_not_as_absent(self, monkeypatch):
        """The key is always present. A reader counting how much of the
        universe the lake is carrying must not have to tell an empty list
        apart from a missing key."""
        out = self._unified(monkeypatch, {"revenue_ttm": 5.0e12}, {})
        assert out["lake_filled_fields"] == []
        assert out["lake_quarter"] is None
