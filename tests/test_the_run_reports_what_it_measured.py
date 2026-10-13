"""The measurements that only ever reached a JSON file now reach the log.

Artifacts from a workflow run are not readable from this container - the
egress proxy refuses the blob host that serves them - so anything written
only to JSON is written to nobody. Two numbers that would have settled
open questions were lost that way: the histogram of filing ages, which
says whether the publication-lag sweep moved anything at all, and the
funnel, which says at which stage the universe shrank from 1,381 to 131.

These tests pin the printing, not the computing. A measurement that is
computed and not printed is the defect being fixed here.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        capture_output=True, text=True, cwd=str(ROOT), timeout=300)


class TestTheProbeCountsWhoFilesWhatCode:
    """The census that turns a failed candidate into a pointer."""

    def _rows(self):
        # Two codes, filed by a different number of symbols, so a per-row
        # count and a per-symbol count cannot both be right.
        return [
            {"itemCode": 32100, "fiscalDate": "2024-03-31", "numericValue": 5.0,
             "itemName": "Mua sam tai san co dinh"},
            {"itemCode": 32100, "fiscalDate": "2024-06-30", "numericValue": 7.0,
             "itemName": "Mua sam tai san co dinh"},
            {"itemCode": 31110, "fiscalDate": "2024-03-31", "numericValue": 2.0,
             "itemName": "Khau hao tai san co dinh"},
        ]

    def test_a_code_is_counted_once_per_symbol_not_once_per_row(
            self, monkeypatch):
        from scripts import build_historical_fundamentals as builder
        monkeypatch.setattr(builder, "_fetch_raw", lambda *a, **k: self._rows())
        counts: dict = {}
        builder.build_symbol("FPT", code_counts=counts)
        # 32100 arrives on two rows and 31110 on one. Counting rows would
        # make the first code look half again as widely filed as it is,
        # and the census exists to rank codes by how much of the universe
        # reports them.
        assert counts == {32100: 1, 31110: 1}

    def test_two_symbols_filing_the_same_code_count_twice(self, monkeypatch):
        from scripts import build_historical_fundamentals as builder
        monkeypatch.setattr(builder, "_fetch_raw", lambda *a, **k: self._rows())
        counts: dict = {}
        builder.build_symbol("FPT", code_counts=counts)
        builder.build_symbol("VNM", code_counts=counts)
        assert counts[32100] == 2

    def test_counting_is_optional_and_changes_no_output(self, monkeypatch):
        from scripts import build_historical_fundamentals as builder
        monkeypatch.setattr(builder, "_fetch_raw", lambda *a, **k: self._rows())
        assert (builder.build_symbol("FPT")
                == builder.build_symbol("FPT", code_counts={}))

    def test_the_scorer_prints_the_census_with_the_vendor_names(self, tmp_path):
        probe = tmp_path / "probe.json"
        probe.write_text(json.dumps({
            "code_names": {"32100": "Mua sam tai san co dinh",
                           "31110": "Khau hao tai san co dinh"},
            "code_counts": {"32100": 900, "31110": 700},
            "symbols": {"AAA": {}},
        }), encoding="utf-8")
        out = _run("score_code_candidates.py", str(probe))
        assert out.returncode == 0, out.stderr
        assert "Mua sam tai san co dinh" in out.stdout
        assert "900" in out.stdout

    def test_a_probe_without_a_census_says_so_instead_of_printing_nothing(
            self, tmp_path):
        probe = tmp_path / "probe.json"
        probe.write_text(
            json.dumps({"code_names": {"1": "x"}, "symbols": {"AAA": {}}}),
            encoding="utf-8")
        out = _run("score_code_candidates.py", str(probe))
        assert out.returncode == 0, out.stderr
        assert "no per-code census" in out.stdout


class TestTheBacktestPrintsWhereTheUniverseWent:
    def test_the_funnel_travels_in_the_diagnostics(self):
        from services.fair_value_backtest_service import _fundamentals_diagnostics
        info = _fundamentals_diagnostics(
            fundamentals_mode="point_in_time", provider=None, used=131,
            skipped=12, unmatched_custom_symbols=[],
            funnel={"universe": 1381, "strategy_passed": 143,
                    "no_price_that_quarter": 0, "no_filing": 12,
                    "valued": 131})
        assert info["funnel"]["strategy_passed"] == 143

    def test_a_run_without_a_funnel_omits_the_key_rather_than_faking_one(self):
        from services.fair_value_backtest_service import _fundamentals_diagnostics
        info = _fundamentals_diagnostics(
            fundamentals_mode="point_in_time", provider=None, used=0,
            skipped=0, unmatched_custom_symbols=[])
        assert "funnel" not in info

    def test_the_sweep_reaches_past_the_quarter_boundary(self):
        from scripts.measure_the_backtest import (
            DEFAULT_LAGS, DEFAULT_STRATEGIES, QUARTER_DAYS)
        # This used to assert DEFAULT_LAGS == (20, 90), on the reasoning
        # that five lags had returned five identical rows so the interior
        # points had nothing to say. The rows were identical because the
        # simulation stands at quarter end and every lag under a quarter
        # makes the same filing public - not because the assumption does
        # not matter. Run 34616175758 swept past the boundary and
        # peter_lynch_garp went from 9.34% CAGR to -0.05%: a 9.39-point
        # spread that the old sweep could not have seen. So the
        # requirement is the opposite one, and it is about reach rather
        # than about any particular value.
        assert any(lag > QUARTER_DAYS for lag in DEFAULT_LAGS), DEFAULT_LAGS
        assert any(lag <= QUARTER_DAYS for lag in DEFAULT_LAGS), DEFAULT_LAGS
        assert len(DEFAULT_STRATEGIES) >= 2


class TestTheLakeFillMeasurementRefusesToGuess:
    def test_bookkeeping_keys_are_not_counted_as_filled_lines(self):
        from scripts.measure_the_lake_fill import NOT_A_FIELD
        # A symbol whose only entries are these has nothing to contribute,
        # and counting it would report a covered symbol with no data.
        assert "lake_quarter" in NOT_A_FIELD
        assert "ttm_quarters_used" in NOT_A_FIELD

    def test_no_snapshot_is_an_error_not_an_empty_report(self, tmp_path):
        out = _run("measure_the_lake_fill.py", "--snapshot",
                   str(tmp_path / "nope.json"))
        assert out.returncode != 0
        assert "0.0%" not in out.stdout


class TestTheSuiteMayNotTouchTheRealLake:
    def test_the_writer_is_blocked_by_default(self):
        from services import bctc_batch_processor
        with pytest.raises(AssertionError, match="real extracted BCTC lake"):
            bctc_batch_processor._save_lake_data({})

    @pytest.mark.allow_real_lake_writes
    def test_a_test_that_asks_for_it_gets_the_real_function(self):
        from services import bctc_batch_processor
        assert bctc_batch_processor._save_lake_data.__name__ == "_save_lake_data"
