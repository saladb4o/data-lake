"""Where "now" comes from.

Eighteen call sites across the forecasting and backtesting engines had the
current year written in as the literal 2026 - forecast start years, backtest
end years, ETF review calendars, ``start_yr = 2026 - time_horizon_years``.
They are correct only during 2026. On 1 January 2027 every backtest would
silently stop a year short and every forecast would start in the past, with
nothing failing and nothing logged.

These helpers read the clock instead. They are separate from
``backtest_service`` so the forecasting engines can use them without importing
the backtest stack.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

#: Overrides the clock, for tests and for reproducing a historical run.
#: Set MARKET_YEAR_OVERRIDE=2026 to pin every default to that year.
_YEAR_OVERRIDE_ENV = "MARKET_YEAR_OVERRIDE"

#: The platform's price and quarter timelines begin here.
EARLIEST_DATA_YEAR = 2016


def _override() -> Optional[int]:
    raw = os.environ.get(_YEAR_OVERRIDE_ENV)
    if not raw:
        return None
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return None
    return year if EARLIEST_DATA_YEAR <= year <= 2200 else None


def current_market_year() -> int:
    """The year the platform treats as the present."""
    return _override() or date.today().year


def default_forecast_start_year() -> int:
    """First projected year: the current year."""
    return current_market_year()


def default_backtest_end_year() -> int:
    """Last year a backtest should run through."""
    return current_market_year()


def default_backtest_start_year(horizon_years: int) -> int:
    """Start year for a backtest of the given length, clamped to the data."""
    return max(EARLIEST_DATA_YEAR, default_backtest_end_year() - max(horizon_years, 0))
