"""The probe must discover the mapping, not assume one - and be able to
report that a field matches nothing.

Vietcap and KBS name their line items in words; VNDIRECT, the only source
the lake reads, names none of its. That makes these two vendors an
independent check on the numeric code map, but only if the probe refuses
to presume which column means what. It matches by value and reports the
column name it found, so "our capex matches no column in the vendor's
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
def wide():
    """A vnstock statement: one row per quarter, one column per line."""
    import pandas as pd
    return pd.DataFrame({
        "ticker": ["FPT", "FPT"],
        "yearReport": [2025, 2025],
        "lengthReport": [2, 1],
        "Depreciation and Amortisation": [4.0e11, 3.6e11],
        "Purchase of fixed assets": [-9.0e11, -7.0e11],
        "Net profit": [2.0e12, 1.8e12],
    })


class TestTheMapIsDiscoveredNotAssumed:
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

    def test_a_near_miss_is_not_a_match(self, wide):
        """Two vendors agreeing means the same figure, not a similar one."""
        rows, _ = probe.name_our_fields_by_column(
            wide, {"2025-Q2": {"da": 4.0e11 * 1.05}}, "2025-Q2")
        assert rows[0]["matched"] is False

    def test_zero_and_non_numeric_fields_are_not_compared(self, wide):
        rows, _ = probe.name_our_fields_by_column(
            wide, {"2025-Q2": {"da": 0, "source": "vndirect",
                               "estimated": True}}, "2025-Q2")
        assert rows == []

    def test_the_period_columns_are_not_offered_as_line_items(self, wide):
        rows, _ = probe.name_our_fields_by_column(
            wide, {"2025-Q2": {"whatever": 2025.0}}, "2025-Q2")
        assert rows[0]["matched"] is False


class TestTheQuartersAreLinedUpCorrectly:
    def test_it_reads_the_row_for_the_quarter_asked_for(self, wide):
        rows, _ = probe.name_our_fields_by_column(
            wide, {"2025-Q1": {"da": 3.6e11}}, "2025-Q1")
        assert rows[0]["matched"] is True

    def test_a_quarter_the_vendor_does_not_carry_is_empty_not_wrong(self, wide):
        rows, count = probe.name_our_fields_by_column(
            wide, {"2024-Q4": {"da": 1.0}}, "2024-Q4")
        assert rows == [] and count == 0

    def test_a_malformed_quarter_code_does_not_raise(self, wide):
        assert probe.name_our_fields_by_column(wide, {}, "rubbish") == ([], 0)

    def test_a_frame_without_period_columns_yields_nothing(self):
        import pandas as pd
        rows, count = probe.name_our_fields_by_column(
            pd.DataFrame({"Net profit": [1.0]}), {"2025-Q2": {"a": 1.0}},
            "2025-Q2")
        assert rows == [] and count == 0


class TestAnUnreachableVendorIsAResult:
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


class TestNoRouteNobodyCanTake:
    """FiinGroup was subscription-only, so it was removed rather than
    left behind a flag. A probe that cannot get an answer is not a probe,
    and code kept "in case" is code nobody maintains."""

    def test_the_paid_vendor_is_gone_entirely(self):
        source = open(os.path.join(ROOT, "scripts", "probe_new_sources.py"),
                      encoding="utf-8").read()
        code = source.split('"""', 2)[-1]
        for trace in ("fiin", "ssi.com.vn", "organCode", "include-fiin"):
            assert trace.lower() not in code.lower(), (
                f"{trace} still in the probe")

    def test_the_pass_does_not_gate_the_probe(self):
        script = open(os.path.join(ROOT, "scripts",
                                   "run_the_measurement_pass.sh"),
                      encoding="utf-8").read()
        assert "PROBE_SOURCES" not in script
