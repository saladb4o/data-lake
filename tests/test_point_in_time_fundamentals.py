"""Point-in-time discipline: a filing may only be used once it was published.

Using a Q1 report on 31 March - when it is typically filed in late April - is
the standard way a backtest manufactures skill it does not have.
"""
from datetime import date

import pytest

from services.fair_value_backtest_service import (
    FORWARD_ERROR_HORIZON_QUARTERS,
    FundamentalsMode,
    _quarter_ordinal,
    _score_model_history,
)
from services.point_in_time_fundamentals import (
    MIN_REQUIRED_FIELDS,
    PointInTimeFundamentals,
)


def _lake(**quarters):
    return {"symbols": {"HPG": {"quarters": quarters}}}


FULL_FILING = {
    "eps": 1200.0, "bvps": 15_000.0, "revenue": 3.1e13,
    "net_income": 4.2e12, "ebit": 5.0e12, "shares_out": 6.0e9,
}


class TestPublicationLag:
    def test_filing_is_invisible_before_its_filing_date(self):
        lake = _lake(**{"2021-Q1": dict(FULL_FILING, filing_date="2021-04-28")})
        pit = PointInTimeFundamentals(lake)
        assert pit.get("HPG", "2021-Q1", as_of=date(2021, 3, 31)) is None

    def test_filing_is_visible_on_and_after_its_filing_date(self):
        lake = _lake(**{"2021-Q1": dict(FULL_FILING, filing_date="2021-04-28")})
        pit = PointInTimeFundamentals(lake)
        assert pit.get("HPG", "2021-Q1", as_of=date(2021, 4, 28)) is not None
        assert pit.get("HPG", "2021-Q1", as_of=date(2021, 6, 30)) is not None

    def test_missing_filing_date_falls_back_to_a_lag_from_quarter_end(self):
        pit = PointInTimeFundamentals(_lake(**{"2021-Q1": dict(FULL_FILING)}),
                                      publication_lag_days=45)
        q_end = date(2021, 3, 31)
        assert pit.get("HPG", "2021-Q1", as_of=q_end, quarter_end=q_end) is None
        assert pit.get("HPG", "2021-Q1", as_of=date(2021, 5, 20), quarter_end=q_end) is not None

    def test_no_as_of_means_no_lag_check(self):
        pit = PointInTimeFundamentals(_lake(**{"2021-Q1": dict(FULL_FILING)}))
        assert pit.get("HPG", "2021-Q1") is not None


class TestNothingIsInvented:
    def test_unknown_symbol_returns_none(self):
        assert PointInTimeFundamentals(_lake()).get("XYZ", "2021-Q1") is None

    def test_absent_quarter_returns_none(self):
        pit = PointInTimeFundamentals(_lake(**{"2021-Q1": dict(FULL_FILING)}))
        assert pit.get("HPG", "2022-Q3") is None

    def test_a_filing_too_thin_to_value_on_is_refused(self):
        thin = {"eps": 1200.0}
        assert len(thin) < MIN_REQUIRED_FIELDS
        pit = PointInTimeFundamentals(_lake(**{"2021-Q1": thin}))
        assert pit.get("HPG", "2021-Q1") is None

    def test_non_numeric_values_do_not_count_toward_the_threshold(self):
        junk = {"eps": "n/a", "bvps": None, "revenue": "", "net_income": "-"}
        pit = PointInTimeFundamentals(_lake(**{"2021-Q1": junk}))
        assert pit.get("HPG", "2021-Q1") is None

    def test_absent_lake_reports_itself_rather_than_faking_data(self):
        pit = PointInTimeFundamentals({})
        assert pit.is_empty
        assert pit.get("HPG", "2021-Q1") is None

    def test_returned_record_is_a_copy(self):
        pit = PointInTimeFundamentals(_lake(**{"2021-Q1": dict(FULL_FILING)}))
        got = pit.get("HPG", "2021-Q1")
        got["eps"] = 0.0
        assert pit.get("HPG", "2021-Q1")["eps"] == 1200.0


class TestForwardLookingErrorScoring:
    """A model must be scored against where the price went, not where it was."""

    def test_quarter_ordinal_round_trips(self):
        assert _quarter_ordinal("2021-Q3") - _quarter_ordinal("2021-Q1") == 2
        assert _quarter_ordinal("2022-Q1") - _quarter_ordinal("2021-Q1") == 4
        assert _quarter_ordinal("garbage") is None

    def test_error_is_measured_against_the_future_price(self):
        # A model called 30,000 in 2021-Q1 while the price was 20,000. Four
        # quarters later the price reached 30,000: the model was right.
        history = {"dcf_2stage_mckinsey": [(30_000.0, "2021-Q1", 20_000.0),
                                           (31_000.0, "2021-Q2", 21_000.0)]}
        prices = {"2021-Q1": 20_000.0, "2021-Q2": 21_000.0,
                  "2022-Q1": 30_000.0, "2022-Q2": 31_000.0}
        scored = _score_model_history(history, prices)
        assert scored["dcf_2stage_mckinsey"]["smape"] == pytest.approx(0.0, abs=1e-6)

    def test_a_model_that_merely_echoes_the_market_scores_badly(self):
        """The inverse of the old behaviour, which rewarded exactly this."""
        history = {"echo": [(20_000.0, "2021-Q1", 20_000.0),
                            (21_000.0, "2021-Q2", 21_000.0)]}
        prices = {"2021-Q1": 20_000.0, "2021-Q2": 21_000.0,
                  "2022-Q1": 30_000.0, "2022-Q2": 31_000.0}
        scored = _score_model_history(history, prices)
        assert scored["echo"]["smape"] > 30.0

    def test_unobserved_future_is_not_scored(self):
        """No lookahead: a horizon that has not happened yet is skipped."""
        history = {"m": [(30_000.0, "2021-Q1", 20_000.0)]}
        assert _score_model_history(history, {"2021-Q1": 20_000.0}) == {}

    def test_horizon_is_four_quarters(self):
        assert FORWARD_ERROR_HORIZON_QUARTERS == 4


class TestModes:
    def test_point_in_time_is_the_default_mode(self):
        import inspect

        from services.fair_value_backtest_service import FairValueBacktestService

        sig = inspect.signature(FairValueBacktestService.run_backtest)
        assert sig.parameters["fundamentals_mode"].default == FundamentalsMode.POINT_IN_TIME
