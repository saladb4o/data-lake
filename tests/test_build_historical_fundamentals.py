"""Transformation from VNDIRECT quarterly rows into the fundamentals lake.

The network fetch itself is not exercised here - only the mapping from raw
itemCode rows to the records the backtest reads, and the publication-date
handling that makes the lake point-in-time.
"""
import importlib.util
import os
from datetime import date

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "build_historical_fundamentals",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "build_historical_fundamentals.py"),
)
build_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_mod)

from services.point_in_time_fundamentals import (  # noqa: E402
    MIN_REQUIRED_FIELDS,
    PointInTimeFundamentals,
)


def _row(code, fiscal, value):
    return {"itemCode": code, "fiscalDate": fiscal, "numericValue": value}


ROWS = [
    # 2021-Q1, non-finance codes
    _row(21001, "2021-03-31", 3.1e13),   # revenue
    _row(23000, "2021-03-31", 4.2e12),   # net income
    _row(21020, "2021-03-31", 5.0e12),   # ebit
    _row(31000, "2021-03-31", 3.8e12),   # cfo
    _row(31110, "2021-03-31", 9.0e11),   # depreciation
    _row(32100, "2021-03-31", -1.2e12),  # capex (reported negative)
    _row(12700, "2021-03-31", 1.7e14),   # total assets
    _row(14000, "2021-03-31", 9.0e13),   # equity
    _row(13000, "2021-03-31", 8.0e13),   # total liabilities
    _row(52001, "2021-03-31", 4.47e9),   # shares outstanding
    # 2021-Q2
    _row(21001, "2021-06-30", 3.5e13),
    _row(23000, "2021-06-30", 4.8e12),
    _row(14000, "2021-06-30", 9.4e13),
    _row(12700, "2021-06-30", 1.8e14),
    _row(52001, "2021-06-30", 4.47e9),
]


@pytest.fixture
def quarters(monkeypatch):
    monkeypatch.setattr(build_mod, "_fetch_raw", lambda symbol, size: ROWS)
    return build_mod.build_symbol("HPG")


class TestQuarterMapping:
    @pytest.mark.parametrize("fiscal,code", [
        ("2021-01-31", "2021-Q1"), ("2021-03-31", "2021-Q1"),
        ("2021-06-30", "2021-Q2"), ("2021-09-30", "2021-Q3"),
        ("2021-12-31", "2021-Q4"),
    ])
    def test_fiscal_date_maps_to_quarter(self, fiscal, code):
        assert build_mod._quarter_code(fiscal) == code

    def test_unparseable_date_is_rejected(self):
        assert build_mod._quarter_code("not-a-date") is None
        assert build_mod._quarter_code(None) is None

    def test_quarter_end_dates(self):
        assert build_mod._quarter_end("2021-Q1") == date(2021, 3, 31)
        assert build_mod._quarter_end("2021-Q4") == date(2021, 12, 31)


class TestRecordConstruction:
    def test_both_quarters_are_produced(self, quarters):
        assert set(quarters) == {"2021-Q1", "2021-Q2"}

    def test_reported_lines_are_carried_through_unchanged(self, quarters):
        q1 = quarters["2021-Q1"]
        assert q1["revenue"] == 3.1e13
        assert q1["net_income"] == 4.2e12
        assert q1["equity"] == 9.0e13

    def test_per_share_figures_are_derived_from_reported_lines(self, quarters):
        q1 = quarters["2021-Q1"]
        assert q1["eps"] == pytest.approx(4.2e12 / 4.47e9)
        assert q1["bvps"] == pytest.approx(9.0e13 / 4.47e9)

    def test_free_cash_flow_subtracts_capex_magnitude(self, quarters):
        """Capex is reported negative; FCF must not add it back."""
        assert quarters["2021-Q1"]["fcf"] == pytest.approx(3.8e12 - 1.2e12)

    def test_ebitda_adds_depreciation_to_ebit(self, quarters):
        assert quarters["2021-Q1"]["ebitda"] == pytest.approx(5.0e12 + 9.0e11)

    def test_absent_lines_are_omitted_not_zero_filled(self, quarters):
        """A quarter that did not report cash flow must not claim cfo = 0."""
        assert "cfo" not in quarters["2021-Q2"]
        assert "fcf" not in quarters["2021-Q2"]

    def test_no_statements_yields_no_quarters(self, monkeypatch):
        monkeypatch.setattr(build_mod, "_fetch_raw", lambda symbol, size: [])
        assert build_mod.build_symbol("XYZ") == {}


class TestPublicationDatesAreExplicit:
    def test_estimated_filing_date_is_recorded_and_labelled(self, quarters):
        q1 = quarters["2021-Q1"]
        assert q1["filing_date"] == "2021-05-15"  # 31 Mar + 45 days
        assert q1["filing_date_is_estimated"] is True

    def test_lag_is_configurable(self, monkeypatch):
        monkeypatch.setattr(build_mod, "_fetch_raw", lambda symbol, size: ROWS)
        built = build_mod.build_symbol("HPG", lag_days=20)
        assert built["2021-Q1"]["filing_date"] == "2021-04-20"


class TestOutputIsReadableByTheBacktest:
    def test_the_reader_accepts_what_the_builder_writes(self, quarters):
        lake = {"symbols": {"HPG": {"quarters": quarters}}}
        pit = PointInTimeFundamentals(lake)
        assert not pit.is_empty
        assert pit.get("HPG", "2021-Q1") is not None

    def test_records_clear_the_reader_s_thinness_threshold(self, quarters):
        from services.point_in_time_fundamentals import _usable_field_count

        assert _usable_field_count(quarters["2021-Q1"]) >= MIN_REQUIRED_FIELDS

    def test_the_estimated_filing_date_is_honoured_as_a_lag(self, quarters):
        pit = PointInTimeFundamentals({"symbols": {"HPG": {"quarters": quarters}}})
        assert pit.get("HPG", "2021-Q1", as_of=date(2021, 3, 31)) is None
        assert pit.get("HPG", "2021-Q1", as_of=date(2021, 5, 15)) is not None
