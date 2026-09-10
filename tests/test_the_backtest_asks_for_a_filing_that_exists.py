"""Standing at quarter end, the market has last quarter's report.

The backtest asked the lake for the quarter that was ending on the day it
stood - a filing published weeks later, by definition. The answer was
None for every symbol at every publication lag, so point-in-time valued
nothing at all, and the failure looked like a strict gate doing its job
rather than a question that could never be answered. Five identical rows
of zeros across a lag sweep is what finally showed it: a real gate would
have loosened as the lag shrank.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.point_in_time_fundamentals import (  # noqa: E402
    PointInTimeFundamentals, _quarter_end_from_code, _quarter_order)

Q = {"revenue": 1e12, "net_income": 1e11, "equity": 1e12, "total_assets": 2e12}


def _lake(*quarters):
    return {"symbols": {"HPG": {"quarters": {
        code: dict(Q, fiscal_date=_quarter_end_from_code(code).isoformat(),
                   filing_date_is_estimated=True)
        for code in quarters}}}}


class TestTheNewestPublishedFilingIsFound:
    def test_at_quarter_end_the_answer_is_the_previous_quarter(self):
        pit = PointInTimeFundamentals(_lake("2020-Q4", "2021-Q1"),
                                      publication_lag_days=45)
        code, record = pit.latest_as_of("HPG", datetime.date(2021, 3, 31))
        assert code == "2020-Q4"
        assert record["revenue"] == 1e12

    def test_the_quarter_that_is_ending_is_never_the_answer(self):
        """It has not been filed. That was the whole bug."""
        pit = PointInTimeFundamentals(_lake("2021-Q1"),
                                      publication_lag_days=45)
        assert pit.latest_as_of("HPG", datetime.date(2021, 3, 31)) is None

    def test_a_shorter_lag_can_change_the_answer(self):
        """A real gate loosens as the lag shrinks; the old one never did."""
        lake = _lake("2020-Q4", "2021-Q1")
        on = datetime.date(2021, 4, 25)
        slow = PointInTimeFundamentals(lake, publication_lag_days=45)
        fast = PointInTimeFundamentals(lake, publication_lag_days=20)
        assert slow.latest_as_of("HPG", on)[0] == "2020-Q4"
        assert fast.latest_as_of("HPG", on)[0] == "2021-Q1"

    def test_the_newest_is_chosen_not_the_first_encountered(self):
        pit = PointInTimeFundamentals(
            _lake("2019-Q2", "2021-Q2", "2020-Q3"), publication_lag_days=45)
        assert pit.latest_as_of(
            "HPG", datetime.date(2021, 12, 31))[0] == "2021-Q2"

    def test_an_unknown_symbol_is_none_not_an_error(self):
        pit = PointInTimeFundamentals(_lake("2021-Q1"))
        assert pit.latest_as_of("NOPE", datetime.date(2026, 1, 1)) is None

    def test_a_thin_record_is_not_offered(self):
        """Below the usable-field threshold it would be padded downstream."""
        lake = {"symbols": {"HPG": {"quarters": {
            "2020-Q4": {"revenue": 1e12, "fiscal_date": "2020-12-31"}}}}}
        pit = PointInTimeFundamentals(lake, publication_lag_days=45)
        assert pit.latest_as_of("HPG", datetime.date(2021, 6, 30)) is None

    def test_a_real_filing_date_still_wins_over_the_lag(self):
        lake = _lake("2021-Q1")
        lake["symbols"]["HPG"]["quarters"]["2021-Q1"]["filing_date"] = "2021-04-02"
        pit = PointInTimeFundamentals(lake, publication_lag_days=90)
        assert pit.latest_as_of("HPG", datetime.date(2021, 4, 2))[0] == "2021-Q1"


class TestTheQuarterHelpers:
    def test_quarter_ends_are_the_last_day(self):
        assert _quarter_end_from_code("2021-Q1") == datetime.date(2021, 3, 31)
        assert _quarter_end_from_code("2021-Q2") == datetime.date(2021, 6, 30)
        assert _quarter_end_from_code("2021-Q4") == datetime.date(2021, 12, 31)

    def test_nonsense_codes_do_not_raise(self):
        assert _quarter_end_from_code("2021-Q9") is None
        assert _quarter_end_from_code("rubbish") is None
        assert _quarter_order("rubbish") is None


class TestTheBacktestUsesIt:
    def test_the_call_site_asks_for_the_latest_not_the_quarter(self):
        import inspect
        from services.fair_value_backtest_service import FairValueBacktestService

        source = inspect.getsource(FairValueBacktestService.run_backtest)
        assert "latest_as_of(sym, rebalance_date)" in source
        assert "pit_fundamentals.get(" not in source, (
            "asking for q_code is the bug this replaced")

    def test_the_staleness_of_what_was_used_is_reported(self):
        from services.fair_value_backtest_service import (
            _fundamentals_diagnostics)

        info = _fundamentals_diagnostics(
            fundamentals_mode="point_in_time", provider=None, used=10,
            skipped=1, unmatched_custom_symbols=[], publication_lag_days=45,
            filing_age={1: 90, 2: 8, 5: 2})
        assert info["filing_age_in_quarters"] == {1: 90, 2: 8, 5: 2}

    def test_quarters_between_counts_the_gap(self):
        from services.fair_value_backtest_service import _quarters_between

        assert _quarters_between("2020-Q4", "2021-Q1") == 1
        assert _quarters_between("2020-Q1", "2021-Q1") == 4
        assert _quarters_between("rubbish", "2021-Q1") is None
