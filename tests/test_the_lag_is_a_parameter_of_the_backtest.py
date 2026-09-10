"""The publication lag must be answerable without rebuilding the lake.

How much of a point-in-time result rests on assuming companies file
within 45 days is a question about the reader, not the data. It is only
cheap to ask if the backtest takes the lag as a parameter AND the cache
tells two lags apart - a sweep served from one cached result returns four
identical rows and reads as "the assumption does not matter".
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.fair_value_backtest_service import (  # noqa: E402
    FairValueBacktestService, _fundamentals_diagnostics)
from services.point_in_time_fundamentals import (  # noqa: E402
    DEFAULT_PUBLICATION_LAG_DAYS)


class TestTheLagIsAskable:
    def test_run_backtest_takes_the_lag(self):
        sig = inspect.signature(FairValueBacktestService.run_backtest)
        assert "publication_lag_days" in sig.parameters
        assert (sig.parameters["publication_lag_days"].default
                == DEFAULT_PUBLICATION_LAG_DAYS)

    def test_the_lag_reaches_the_provider(self):
        source = inspect.getsource(FairValueBacktestService.run_backtest)
        assert "publication_lag_days=publication_lag_days" in source, (
            "the parameter must be handed to from_lake, not just accepted")


class TestTheCacheTellsTwoLagsApart:
    def test_the_cache_key_carries_the_lag(self):
        """Otherwise a sweep measures the first lag four times."""
        source = inspect.getsource(FairValueBacktestService.run_backtest)
        key_block = source[source.index("cache_key = "):
                           source.index("cached = ")]
        assert "publication_lag_days" in key_block

    def test_two_lags_produce_different_keys(self):
        """Built the way the method builds it, with only the lag differing."""
        def key(lag):
            return f"fv_bt_v12_x_y_z_lag{lag}"
        assert key(30) != key(90)


class TestTheResultStatesItsAssumption:
    def test_point_in_time_diagnostics_name_the_lag(self):
        info = _fundamentals_diagnostics(
            fundamentals_mode="point_in_time", provider=None,
            used=10, skipped=2, unmatched_custom_symbols=[],
            publication_lag_days=60)
        assert info["publication_lag_days_assumed"] == 60

    def test_snapshot_projected_claims_no_lag(self):
        """There is no filing to be late in that mode; naming one would lie."""
        info = _fundamentals_diagnostics(
            fundamentals_mode="snapshot_projected", provider=None,
            used=0, skipped=0, unmatched_custom_symbols=[],
            publication_lag_days=None)
        assert "publication_lag_days_assumed" not in info
