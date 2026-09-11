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


class TestTheFreeVendorsThatNameTheirLines:
    """Vietcap and KBS name their line items and cost nothing.

    Their statements are transposed relative to FiinGroup's - a quarter is
    a row, a line item is a column - so the extraction differs while the
    question asked of the numbers must not.
    """

    @pytest.fixture
    def wide(self):
        import pandas as pd
        return pd.DataFrame({
            "ticker": ["FPT", "FPT"],
            "yearReport": [2025, 2025],
            "lengthReport": [2, 1],
            "Depreciation and Amortisation": [4.0e11, 3.6e11],
            "Purchase of fixed assets": [-9.0e11, -7.0e11],
            "Net profit": [2.0e12, 1.8e12],
        })

    def test_it_names_the_vendor_column_carrying_our_number(self, wide):
        rows, count = probe.name_our_fields_by_column(
            wide, {"2025-Q2": {"da": 4.0e11}}, "2025-Q2")
        assert count == 3
        assert rows[0]["vendor_rows_with_this_value"] == [
            "Depreciation and Amortisation"]

    def test_a_number_no_column_carries_is_reported_unmatched(self, wide):
        rows, _ = probe.name_our_fields_by_column(
            wide, {"2025-Q2": {"capex": 5.5e11}}, "2025-Q2")
        assert rows[0]["matched"] is False
        assert rows[0]["vendor_rows_with_this_value"] == []

    def test_the_period_columns_are_not_offered_as_line_items(self, wide):
        rows, _ = probe.name_our_fields_by_column(
            wide, {"2025-Q2": {"whatever": 2025.0}}, "2025-Q2")
        assert rows[0]["matched"] is False

    def test_it_reads_the_row_for_the_quarter_asked_for(self, wide):
        rows, _ = probe.name_our_fields_by_column(
            wide, {"2025-Q1": {"da": 3.6e11}}, "2025-Q1")
        assert rows[0]["matched"] is True

    def test_a_quarter_the_vendor_does_not_carry_is_empty_not_wrong(self, wide):
        rows, count = probe.name_our_fields_by_column(
            wide, {"2024-Q4": {"da": 1.0}}, "2024-Q4")
        assert rows == [] and count == 0

    def test_a_frame_without_period_columns_yields_nothing(self):
        import pandas as pd
        rows, count = probe.name_our_fields_by_column(
            pd.DataFrame({"Net profit": [1.0]}), {"2025-Q2": {"a": 1.0}},
            "2025-Q2")
        assert rows == [] and count == 0

    def test_both_free_vendors_are_asked(self):
        assert set(probe.VNSTOCK_SOURCES) == {"VCI", "KBS"}

    def test_a_statement_the_vendor_refuses_is_kept_as_the_result(self,
                                                                  monkeypatch):
        class Refuses:
            def __init__(self, **kwargs):
                pass

            def cash_flow(self):
                raise RuntimeError("no cash flow here")

            def balance_sheet(self):
                return "frame"

            def income_statement(self):
                return "frame"

        import types
        module = types.ModuleType("vnstock")
        module.Finance = lambda **kw: Refuses(**kw)
        monkeypatch.setitem(sys.modules, "vnstock", module)
        out = probe.vnstock_statements("FPT", "VCI")
        assert out["cash_flow"].startswith("RuntimeError")
        assert out["balance_sheet"] == "frame"

    def test_the_two_shapes_answer_the_same_question(self, wide, frame):
        """Value matching is shared, so neither shape can drift."""
        import inspect
        source = inspect.getsource(probe)
        assert source.count("vendor_rows_with_this_value\":") == 1
