"""The probe must discover the mapping, not assume one - and be able to
report that a field matches nothing.

FiinGroup names its line items; VNDIRECT names none of its. That makes
the vendor an independent check on the code map, but only if the probe
refuses to presume which row means what. It matches by value and reports
the row name it found, so "our capex matches no row in the vendor's
statement" is a result the probe can produce rather than one it is built
to rule out.
"""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location(
    "probe_new_sources", os.path.join(ROOT, "scripts", "probe_new_sources.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def frame():
    import pandas as pd
    return pd.DataFrame({
        "ITEMS": ["TOTAL ASSETS", "Cash and cash equivalents",
                  "Short-term borrowings", "Owner's equity"],
        "Q2 2025": [1.7e14, 1.0e13, 5.0e12, 9.0e13],
        "Q1 2025": [1.6e14, 9.0e12, 4.0e12, 8.5e13],
    })


class TestTheMapIsDiscoveredNotAssumed:
    def test_a_matching_value_reports_the_vendors_name_for_it(self, frame):
        rows, _ = probe.name_our_fields(
            frame, {"2025-Q2": {"total_assets": 1.7e14}}, "2025-Q2")
        assert rows[0]["vendor_rows_with_this_value"] == ["TOTAL ASSETS"]

    def test_a_field_matching_nothing_is_reported_as_unmatched(self, frame):
        """The finding worth having, not an error to suppress."""
        rows, _ = probe.name_our_fields(
            frame, {"2025-Q2": {"capex": -777.0}}, "2025-Q2")
        assert rows[0]["matched"] is False
        assert rows[0]["vendor_rows_with_this_value"] == []

    def test_a_near_miss_is_not_a_match(self, frame):
        """1% apart is two different figures, not one figure with noise."""
        rows, _ = probe.name_our_fields(
            frame, {"2025-Q2": {"total_assets": 1.7e14 * 1.05}}, "2025-Q2")
        assert rows[0]["matched"] is False

    def test_zero_and_non_numeric_fields_are_not_compared(self, frame):
        """Zero matches any absent row; a date matches nothing meaningfully."""
        rows, _ = probe.name_our_fields(
            frame, {"2025-Q2": {"capex": 0.0, "fiscal_date": "2025-06-30"}},
            "2025-Q2")
        assert rows == []


class TestTheQuartersAreLinedUpCorrectly:
    def test_the_lakes_code_finds_the_vendors_column(self, frame):
        assert probe._column_for(frame, "2025-Q2") == "Q2 2025"
        assert probe._column_for(frame, "2025-Q1") == "Q1 2025"

    def test_a_quarter_the_vendor_does_not_carry_yields_nothing(self, frame):
        assert probe._column_for(frame, "2019-Q3") is None
        assert probe.name_our_fields(frame, {"2019-Q3": {"x": 1.0}},
                                     "2019-Q3") == ([], 0)

    def test_a_malformed_quarter_code_does_not_raise(self, frame):
        assert probe._column_for(frame, "nonsense") is None


class TestAnUnreachableHostIsAResult:
    def test_knock_records_the_failure_instead_of_raising(self, monkeypatch):
        def boom(*a, **kw):
            raise OSError("CONNECT tunnel failed, response 403")
        monkeypatch.setattr(probe, "_get", boom)
        rows = probe.knock()
        assert rows and all(r["ok"] is False for r in rows)
        assert all("403" in r["error"] for r in rows)

    def test_every_candidate_host_is_knocked_on(self, monkeypatch):
        seen = []

        class Response:
            status_code = 200
            content = b"{}"

        monkeypatch.setattr(probe, "_get",
                            lambda url, **kw: (seen.append(url), Response())[1])
        probe.knock()
        assert len(seen) == len(probe.REACHABILITY)
