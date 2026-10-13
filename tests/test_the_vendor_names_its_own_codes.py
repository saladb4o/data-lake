"""The numeric scheme was never anonymous, and the lake must record that.

This audit spent a long time decoding VNDIRECT's item codes by magnitude
and by arithmetic identity, on the premise that the vendor names nothing.
It does: every row it returns carries itemName, and
unified_data_service.fetch_vndirect_financials has been reading that
label all along. The lake builder downloads those same rows and used to
throw the names away, which is why "is 32100 capex?" was an inference
rather than a reading.

These tests hold three things. The builder keeps the label. The scorer
shows it beside the arithmetic. And a scorer given no labels says so,
instead of printing a table that looks complete.
"""
import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load("build_historical_fundamentals")
scorer = _load("score_code_candidates")


def _rows():
    """Two quarters of one code, as the vendor actually sends them."""
    return [
        {"itemCode": 32100, "fiscalDate": "2025-06-30", "numericValue": -9.0e11,
         "itemName": "Tiền chi mua sắm TSCĐ và các tài sản dài hạn khác"},
        {"itemCode": 32100, "fiscalDate": "2025-03-31", "numericValue": -7.0e11,
         "itemName": "Tiền chi mua sắm TSCĐ và các tài sản dài hạn khác"},
    ]


class TestTheBuilderKeepsTheLabel:
    def test_it_records_the_name_the_vendor_sent(self, monkeypatch):
        monkeypatch.setattr(builder, "_fetch_raw", lambda *a, **k: _rows())
        names = {}
        builder.build_symbol("FPT", code_names=names)
        assert names[32100].startswith("Tiền chi mua sắm")

    def test_it_falls_back_to_the_other_keys_the_vendor_uses(self, monkeypatch):
        rows = _rows()
        del rows[0]["itemName"]
        rows[0]["itemEnName"] = "Purchase of fixed assets"
        del rows[1]["itemName"]
        rows[1]["itemEnName"] = "Purchase of fixed assets"
        monkeypatch.setattr(builder, "_fetch_raw", lambda *a, **k: rows)
        names = {}
        builder.build_symbol("FPT", code_names=names)
        assert names[32100] == "Purchase of fixed assets"

    def test_a_row_with_no_label_leaves_the_code_unnamed(self, monkeypatch):
        rows = _rows()
        for row in rows:
            row["itemName"] = "   "
        monkeypatch.setattr(builder, "_fetch_raw", lambda *a, **k: rows)
        names = {}
        builder.build_symbol("FPT", code_names=names)
        assert names == {}

    def test_collecting_names_is_optional(self, monkeypatch):
        """The lake itself must be unchanged by whether names are kept."""
        monkeypatch.setattr(builder, "_fetch_raw", lambda *a, **k: _rows())
        assert (builder.build_symbol("FPT")
                == builder.build_symbol("FPT", code_names={}))


class TestTheScorerShowsTheLabel:
    @pytest.fixture
    def results(self):
        return {"gross_ppe": {"deltas_available": 10, "candidates": {
            "capex_32100": {"present": 10, "nonzero": 10,
                            "held": 9, "tested": 10}}}}

    def _render(self, results, names=None):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            scorer.report(results, names)
        return buffer.getvalue()

    def test_the_vendors_name_appears_beside_the_code(self, results):
        out = self._render(results, {"32100": "Purchase of fixed assets"})
        assert "Purchase of fixed assets" in out

    def test_a_code_the_vendor_never_named_shows_no_name(self, results):
        assert "Purchase" not in self._render(results, {})

    def test_it_does_not_invent_a_name_from_a_neighbouring_code(self, results):
        out = self._render(results, {"32110": "Proceeds from disposal"})
        assert "Proceeds from disposal" not in out

    def test_a_column_that_is_not_code_shaped_has_no_label(self):
        assert scorer._label("gross_ppe", {"ppe": "x"}) == ""


class TestAnUnlabelledProbeSaysSo:
    def test_it_asks_for_a_rebuild_rather_than_looking_complete(self, tmp_path,
                                                                monkeypatch):
        probe = tmp_path / "probe.json"
        probe.write_text(json.dumps({
            "codes": {"capex_32100": [32100]},
            "symbols": {"FPT": {"2025-Q2": {"capex_32100": 1.0,
                                            "gross_ppe": 2.0}}},
        }), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["score", str(probe)])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            scorer.main()
        assert "Rebuild the lake" in buffer.getvalue() or \
               "rebuild the lake" in buffer.getvalue().lower()
