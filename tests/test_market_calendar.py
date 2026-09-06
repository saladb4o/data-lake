"""The current year must come from the clock, not from a literal.

Eighteen call sites had 2026 written in as "now" - forecast start years,
backtest end years, `start_yr = 2026 - time_horizon_years`, the ETF review
calendar. Correct during 2026 and silently wrong every year after, with
nothing failing and nothing logged.
"""
import ast
import pathlib

import pytest

from services.market_calendar import (
    EARLIEST_DATA_YEAR,
    current_market_year,
    default_backtest_end_year,
    default_backtest_start_year,
    default_forecast_start_year,
)

SERVICES = pathlib.Path(__file__).resolve().parent.parent / "services"


class TestClockDrivenDefaults:
    def test_current_year_tracks_the_clock(self):
        from datetime import date
        assert current_market_year() == date.today().year

    def test_override_is_honoured(self, monkeypatch):
        monkeypatch.setenv("MARKET_YEAR_OVERRIDE", "2031")
        assert current_market_year() == 2031
        assert default_forecast_start_year() == 2031
        assert default_backtest_end_year() == 2031

    @pytest.mark.parametrize("bad", ["", "abc", "1800", "9999999"])
    def test_a_nonsense_override_falls_back_to_the_clock(self, monkeypatch, bad):
        from datetime import date
        monkeypatch.setenv("MARKET_YEAR_OVERRIDE", bad)
        assert current_market_year() == date.today().year

    def test_backtest_window_follows_the_horizon(self, monkeypatch):
        monkeypatch.setenv("MARKET_YEAR_OVERRIDE", "2030")
        assert default_backtest_start_year(5) == 2025
        assert default_backtest_end_year() == 2030

    def test_start_year_never_precedes_the_data(self, monkeypatch):
        monkeypatch.setenv("MARKET_YEAR_OVERRIDE", "2030")
        assert default_backtest_start_year(100) == EARLIEST_DATA_YEAR


class TestNoHardcodedYearRemains:
    """Guards against a literal creeping back into a default."""

    ENGINES = [
        "three_statement_engine.py",
        "working_capital_engine.py",
        "debt_capital_schedule_engine.py",
        "institutional_backtest_service.py",
        "fair_value_backtest_service.py",
        "etf_rebalance_service.py",
    ]

    @pytest.mark.parametrize("filename", ENGINES)
    def test_no_year_literal_as_a_parameter_default(self, filename):
        tree = ast.parse((SERVICES / filename).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args
            params = args.args + args.kwonlyargs
            defaults = ([None] * (len(args.args) - len(args.defaults))) + list(args.defaults)
            defaults += list(args.kw_defaults)
            for param, default in zip(params, defaults):
                if not isinstance(default, ast.Constant):
                    continue
                if not isinstance(default.value, int) or isinstance(default.value, bool):
                    continue
                # A fixed historical anchor (start_year=2021, where the price
                # timeline begins) is legitimate. What must not be written in
                # is "now": a default at or after the current year, which is
                # right for one year and quietly wrong afterwards.
                is_now_literal = (
                    "year" in param.arg
                    and isinstance(default.value, int)
                    and default.value >= current_market_year()
                )
                if is_now_literal:
                    offenders.append(f"{node.name}({param.arg}={default.value})")
        assert not offenders, (
            f"{filename} hardcodes the current year as a default: {offenders}. "
            "Use services.market_calendar instead."
        )
