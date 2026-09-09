"""The vendor census measures and does not act.

It exists because every cycle of this audit has cost a workflow run to
learn one fact, and several of those facts turned out to be about the
question rather than the data. It asks everything at once. The invariant
that makes that safe is that it can only look: no route it probes has been
proven, no field it counts has a known unit, and a diagnostic that started
writing into the snapshot would be publishing valuations from routes
nobody has verified.
"""

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.vendor_census as census


ROOT = Path(census.__file__).parent.parent


class TestItOnlyMeasures:
    def test_no_function_writes_a_valuation_input(self):
        src = Path(census.__file__).read_text()
        for forbidden in ("normalize_stock_data", "reconstruct_financial_triangles",
                          "ValuationEngine", "field_provenance[",
                          "screener_snapshot.json\", \"w\""):
            assert forbidden not in src, (
                f"{forbidden} in the census - it may read the snapshot, "
                "never compute or rewrite one"
            )

    def test_it_writes_only_where_asked(self):
        """The single write is the --json dump, to a path the caller names
        and the workflow uploads as an artifact."""
        src = Path(census.__file__).read_text()
        assert src.count('"w", encoding="utf-8"') == 1
        assert 'if args.json:' in src

    def test_the_snapshot_is_opened_read_only(self):
        src = inspect.getsource(census.pick_symbols)
        assert '"r", encoding="utf-8"' in src
        assert '"w"' not in src


class TestItDescribesWhatCameBack:
    """A route that answers nothing and a route that does not exist look
    identical unless the log says which. The TCBS route this project called
    for its whole life returned 404 for every ticker and the failure was
    swallowed into an empty dict."""

    def test_shape_names_a_dict_and_its_keys(self):
        out = census._shape({"data": {"years": [1, 2]}})
        assert "dict" in out and "data" in out

    def test_shape_names_a_list_and_its_length(self):
        assert "list(3)" in census._shape([{"a": 1}, {}, {}])

    def test_shape_survives_an_empty_body(self):
        assert census._shape([]) == "list(0)"
        assert census._shape(None) == "NoneType"

    def test_shape_does_not_recurse_without_bound(self):
        deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        assert len(census._shape(deep)) < 400


class TestItSurveysTheRightCompanies:
    def test_the_reference_symbols_cover_every_company_form(self):
        """Vietcap serves a different chart of accounts to each form. A
        catalogue taken from one non-financial company would describe a
        quarter of the exchange and read as if it described all of it."""
        forms = {desc.split(" - ")[0] for _sym, desc in census.REFERENCE_SYMBOLS}
        assert forms == {"CT", "NH", "CK", "BH"}

    def test_every_route_is_named_and_callable(self):
        assert census.ROUTES
        for name, fetch in census.ROUTES.items():
            assert callable(fetch)
            assert name.strip() == name

    @pytest.mark.parametrize("status,body", [
        (None, None), (404, None), (500, {"error": "x"}),
        (200, {}), (200, {"data": None}), (200, {"data": {"years": []}}),
    ])
    def test_a_route_returning_nothing_is_not_an_error(self, monkeypatch,
                                                       status, body):
        """Egress is blocked from some environments and a vendor can be
        down. The census reports the zero; it does not raise."""
        monkeypatch.setattr(census, "_get_json", lambda *a, **k: (status, body))
        assert census._vietcap_statement_rows("ZZZZ", "INCOME_STATEMENT", {}) == []
        assert census._kbs_rows("ZZZZ") == []
        assert census._vietcap_stats_rows("ZZZZ", {}) == []

    def test_a_route_that_answers_is_read(self, monkeypatch):
        monkeypatch.setattr(
            census, "_get_json",
            lambda *a, **k: (200, {"data": {"quarters": [{"revenue": 1.0}]}}),
        )
        rows = census._vietcap_statement_rows("FPT", "INCOME_STATEMENT", {})
        assert rows == [{"revenue": 1.0}]

    def test_an_envelope_is_not_counted_as_a_row(self, monkeypatch):
        """A body that answered with nothing must not be reported as a
        company the route covers. That is the most misleading thing a
        coverage census can do, and it is what this test caught."""
        monkeypatch.setattr(
            census, "_get_json", lambda *a, **k: (200, {"data": {"years": []}}))
        assert census._vietcap_stats_rows("FPT", {}) == []

    def test_a_real_statistics_record_is_kept(self, monkeypatch):
        monkeypatch.setattr(census, "_get_json", lambda *a, **k: (
            200, {"data": {"ebit": 1.0, "roic": 2.0, "history": []}}))
        rows = census._vietcap_stats_rows("FPT", {})
        assert rows and rows[0]["ebit"] == 1.0

    def test_quarters_are_preferred_over_years(self, monkeypatch):
        """The most recent period is what a TTM figure has to come from."""
        monkeypatch.setattr(census, "_get_json", lambda *a, **k: (200, {
            "data": {"years": [{"y": 1}], "quarters": [{"q": 1}]}}))
        assert census._vietcap_statement_rows("FPT", "INCOME_STATEMENT", {}) \
            == [{"q": 1}]


class TestItRunsWithoutANetwork:
    def test_help_works(self):
        out = subprocess.run(
            [sys.executable, str(census.__file__), "--help"],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        assert out.returncode == 0
        assert "--limit" in out.stdout

    def test_it_refuses_clearly_when_there_is_no_snapshot(self, tmp_path,
                                                          monkeypatch):
        """It measures the gap the sync reports, so it needs the report.
        Saying so beats surveying an empty list and printing zeroes."""
        import services.unified_data_service as uds
        monkeypatch.setattr(
            uds, "screener_snapshot_file",
            lambda *a, **k: str(tmp_path / "nope.json"),
        )
        with pytest.raises(SystemExit) as excinfo:
            census.pick_symbols(None)
        assert "sync" in str(excinfo.value).lower()


class TestItPicksTheCompaniesThatAreBlocked:
    def _snapshot(self, tmp_path, monkeypatch, stocks):
        path = tmp_path / "screener_snapshot.json"
        path.write_text(json.dumps({"stocks": stocks}), encoding="utf-8")
        import services.unified_data_service as uds
        monkeypatch.setattr(
            uds, "screener_snapshot_file", lambda *a, **k: str(path))
        return path

    def test_a_symbol_with_a_trusted_ebit_is_skipped(self, tmp_path, monkeypatch):
        """Measuring a route against companies that are already valued
        would say nothing about whether it closes the gap."""
        self._snapshot(tmp_path, monkeypatch, [
            {"symbol": "AAA", "field_provenance": {"ebit": 3}, "revenue": 1e12},
            {"symbol": "BBB", "field_provenance": {"ebit": 1}, "revenue": 2e12},
        ])
        symbols, revenue = census.pick_symbols(None)
        assert symbols == ["BBB"]
        assert revenue == {"BBB": 2e12}

    def test_a_symbol_with_no_provenance_at_all_is_included(self, tmp_path,
                                                            monkeypatch):
        self._snapshot(tmp_path, monkeypatch, [{"symbol": "CCC"}])
        symbols, _revenue = census.pick_symbols(None)
        assert symbols == ["CCC"]

    def test_revenue_is_carried_so_the_ratios_state_the_unit(self, tmp_path,
                                                             monkeypatch):
        """Every field is reported as a ratio to revenue held in dong, so
        the same number that locates the operating line also states the
        route's unit."""
        self._snapshot(tmp_path, monkeypatch, [
            {"symbol": "DDD", "field_provenance": {"ebit": 0}, "revenue": 5e12},
            {"symbol": "EEE", "field_provenance": {"ebit": 0}, "revenue": 0},
        ])
        _symbols, revenue = census.pick_symbols(None)
        assert revenue == {"DDD": 5e12}

    def test_the_limit_is_honoured(self, tmp_path, monkeypatch):
        self._snapshot(tmp_path, monkeypatch, [
            {"symbol": s, "field_provenance": {"ebit": 0}}
            for s in ("FFF", "GGG", "HHH")
        ])
        assert census.pick_symbols(2)[0] == ["FFF", "GGG"]


def test_a_field_of_zeros_is_distinguishable_from_a_populated_one():
    """The defect the first census run hid.

    Vietcap answered for 688 of 720 companies and every ratio field was
    printed as +0.000000, because a margin of 0.12 over a revenue of 1e11
    is 1e-12 and so is a margin of zero. The two cases must be told apart
    in the output, or the survey cannot say whether the route that might
    close the coverage gap sends data or padding.
    """
    import collections

    populated = [0.12, 0.09, 0.15, 0.0, 0.11]
    padded = [0.0] * 5

    for series, expect_nonzero in ((populated, 4), (padded, 0)):
        raw = sorted(series)
        assert sum(1 for v in raw if v != 0.0) == expect_nonzero
        # The ratio against a revenue in dong collapses both to zero at
        # six decimal places; only the raw median and the non-zero count
        # separate them.
        ratios = sorted(v / 1e11 for v in series)
        assert f"{ratios[len(ratios) // 2]:+.6f}" == "+0.000000"

    assert f"{sorted(populated)[len(populated) // 2]:+.6g}" != "+0"
