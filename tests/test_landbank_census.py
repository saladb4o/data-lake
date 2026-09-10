"""The census that separates an absent line from a mis-read item code.

Two runs reported `landbank` blocking 123 symbols and `rwa` blocking 41,
unchanged, after the fetch was wired and the sector gate widened. An
unchanged count is compatible with three different faults - the vendor does
not carry the line, the item codes are wrong, or the number is fetched and
never reaches the record - and they need different fixes. These tests hold
the census to the property that makes it able to tell them apart: it must
report what the payloads contain, for the right companies, under the codes
actually in force.
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.unified_data_service as uds
from scripts import vendor_census as census


class TestTheCensusAsksAboutTheRightCompanies:
    def test_the_two_sector_halves_still_cover_the_services_gate(self):
        # The service keeps one frozenset; the census splits it in two
        # because each half needs different item codes. A sector added to
        # the service and not here would be censused for the wrong line, or
        # for no line at all, and nothing would say so.
        assert (census._LANDBANK_SECTORS | census._LOANBOOK_SECTORS
                == uds._SECTORS_NEEDING_A_LINE_TRADINGVIEW_LACKS)

    def test_the_two_halves_do_not_overlap(self):
        assert not (census._LANDBANK_SECTORS & census._LOANBOOK_SECTORS)

    def test_it_censuses_the_codes_the_service_actually_reads(self):
        # If the service is retargeted at different codes and the census is
        # not, the census measures a question nobody is asking.
        source = open(uds.__file__, encoding="utf-8").read()
        for code in census.LINE_CODES["landbank"]:
            assert f"{code}" in source
        assert "_latest([11400, 11410])" in source
        assert "_latest([112000])" in source

    def test_population_is_grouped_by_sector(self, tmp_path, monkeypatch):
        snapshot = tmp_path / "screener_snapshot.json"
        snapshot.write_text(
            '{"stocks": {'
            '"NLG": {"symbol": "NLG", "sector_code": "8600"},'
            '"VCB": {"symbol": "VCB", "sector_code": "8300"},'
            '"FPT": {"symbol": "FPT", "sector_code": "VNIND"}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(uds, "screener_snapshot_file",
                            lambda: str(snapshot))
        groups = census.pick_line_symbols(None)
        assert groups["landbank"] == ["NLG"]
        assert groups["bank_loans"] == ["VCB"]

    def test_it_includes_companies_that_already_have_the_line(self, tmp_path,
                                                             monkeypatch):
        # Selecting only the refused ones would leave no baseline: with no
        # successful case in the sample, "0 carry the code" and "the vendor
        # has nothing" are again indistinguishable.
        snapshot = tmp_path / "screener_snapshot.json"
        snapshot.write_text(
            '{"stocks": {'
            '"NLG": {"symbol": "NLG", "sector_code": "8600",'
            ' "landbank_fq": 1.0e12}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(uds, "screener_snapshot_file",
                            lambda: str(snapshot))
        assert census.pick_line_symbols(None)["landbank"] == ["NLG"]


def _raw(rows):
    return [
        {"itemCode": code, "fiscalDate": "2025-06-30",
         "numericValue": value, "itemName": name}
        for code, value, name in rows
    ]


class TestTheBalanceSheetIsExportedByCode:
    @staticmethod
    @pytest.fixture
    def stub(monkeypatch):
        def _install(rows):
            import services.stock_service as ss
            monkeypatch.setattr(
                ss, "fetch_vndirect_raw_statements",
                lambda symbol, report_type="ANNUAL", target_quarters=16:
                    _raw(rows),
                raising=False,
            )
            monkeypatch.setattr(ss.cache, "get", lambda *a, **k: None)
            monkeypatch.setattr(ss.cache, "set", lambda *a, **k: None)
        return _install

    def test_a_non_financial_balance_sheet_code_is_exported(self, stub):
        stub([(12700, 5.0e12, "Tổng cộng tài sản"),
              (11420, 2.0e12, "Chi phí xây dựng cơ bản dở dang")])
        out = uds.fetch_vndirect_financials("NLG")
        assert out["balance_sheet_fq_by_code"][11420] == 2.0e12

    def test_a_bank_balance_sheet_code_is_exported(self, stub):
        # 112000 is six digits. A range of 10000-19999 would have declared
        # the loan book absent for every bank by construction, which is
        # precisely the false answer this census exists to avoid.
        stub([(112000, 8.0e14, "Cho vay khách hàng"),
              (130000, 1.0e15, "Tổng tài sản")])
        out = uds.fetch_vndirect_financials("VCB")
        assert out["balance_sheet_fq_by_code"][112000] == 8.0e14

    def test_income_statement_codes_are_not_in_the_balance_sheet(self, stub):
        stub([(21001, 1.0e12, "Doanh thu"), (12700, 5.0e12, "Tổng tài sản")])
        out = uds.fetch_vndirect_financials("FPT")
        assert 21001 not in out["balance_sheet_fq_by_code"]
        assert 12700 in out["balance_sheet_fq_by_code"]

    def test_absent_codes_are_absent_rather_than_zero(self, stub):
        # A zero would be read as "the company has no land bank"; a missing
        # key is read as "the vendor did not say". The census turns on that
        # difference.
        stub([(12700, 5.0e12, "Tổng tài sản")])
        out = uds.fetch_vndirect_financials("KDH")
        assert 11420 not in out["balance_sheet_fq_by_code"]

    def test_the_vendor_names_are_kept(self, stub):
        stub([(11420, 2.0e12, "Chi phí xây dựng cơ bản dở dang")])
        out = uds.fetch_vndirect_financials("NLG")
        assert out["item_code_names"][11420].startswith("Chi phí")


class TestTheReportSeparatesTheThreeFaults:
    @staticmethod
    def _run(monkeypatch, payloads, groups, held=None):
        monkeypatch.setattr(
            census, "fetch_vndirect_financials",
            lambda sym: payloads.get(sym, {}),
        )
        out = {}
        census.landbank_and_loanbook(groups, 2, out, held=held or {})
        return out["landbank_and_loanbook"]

    def test_a_carried_code_is_counted_as_carried(self, monkeypatch):
        report = self._run(
            monkeypatch,
            {"NLG": {"balance_sheet_fq_by_code": {11400: 2.0e12},
                     "item_code_names": {}}},
            {"landbank": ["NLG"], "bank_loans": []},
        )
        assert report["landbank"]["per_code"][11400]["present"] == 1
        assert report["landbank"]["per_code"][11400]["nonzero"] == 1
        assert report["landbank"]["missing"] == 0

    def test_a_route_that_answered_nothing_is_not_reported_as_an_absent_line(
            self, monkeypatch):
        # No payload at all says the fetch failed. Reporting that as "0 of
        # n carry the code" would blame the vendor for a broken request.
        report = self._run(
            monkeypatch, {"NLG": {}},
            {"landbank": ["NLG"], "bank_loans": []},
        )
        assert report["landbank"]["answered"] == 0
        assert "per_code" not in report["landbank"]

    def test_a_missing_code_is_reported_with_what_is_there_instead(
            self, monkeypatch):
        report = self._run(
            monkeypatch,
            {"KDH": {"balance_sheet_fq_by_code": {12700: 5.0e12,
                                                  11430: 3.0e12},
                     "item_code_names": {11430: "Bất động sản dở dang"}}},
            {"landbank": ["KDH"], "bank_loans": []},
        )
        assert report["landbank"]["missing"] == 1
        codes = report["landbank"]["codes_present"]
        assert codes[11430]["vendor_name"] == "Bất động sản dở dang"
        # Sized against total assets, so a candidate for the line can be
        # recognised by magnitude rather than by guessing from the code.
        assert codes[11430]["median_share"] == pytest.approx(0.6)

    def test_the_bank_group_is_asked_for_the_bank_code(self, monkeypatch):
        report = self._run(
            monkeypatch,
            {"VCB": {"balance_sheet_fq_by_code": {112000: 8.0e14},
                     "item_code_names": {}}},
            {"landbank": [], "bank_loans": ["VCB"]},
        )
        assert report["bank_loans"]["per_code"][112000]["present"] == 1

    def test_a_code_present_but_always_zero_is_not_called_right(self,
                                                                monkeypatch):
        # The first run's actual result: 12510 present for every developer,
        # every value zero, no land bank anywhere. Counting presence alone
        # reported "the codes are right" and closed a question that was
        # still open. A line the vendor emits for everyone and populates
        # for no one is not the line.
        report = self._run(
            monkeypatch,
            {"KDH": {"balance_sheet_fq_by_code": {11400: 0.0,
                                                  12700: 5.0e12,
                                                  11300: 3.5e12},
                     "item_code_names": {}}},
            {"landbank": ["KDH"], "bank_loans": []},
        )
        assert report["landbank"]["per_code"][11400]["present"] == 1
        assert report["landbank"]["per_code"][11400]["nonzero"] == 0
        # and it is examined rather than declared solved
        assert report["landbank"]["missing"] == 1
        assert 11300 in report["landbank"]["codes_present"]

    def test_the_codes_present_are_ranked_by_size_not_by_frequency(
            self, monkeypatch, capsys):
        # Every bank carried every code in the first run, so ranking by
        # frequency printed an arbitrary forty in which the largest asset
        # line - the loan book, the whole point - did not appear. The
        # vendor names none of these codes; magnitude is the only handle.
        # The large line goes in LAST, so a frequency ranking - every code
        # here is carried by the one company - leaves it outside the cap
        # and the test fails against the ordering that actually shipped.
        sheet = {12700: 100.0}
        sheet.update({20000 + i: 0.01 for i in range(60)})
        sheet[19001] = 70.0
        self._run(
            monkeypatch,
            {"VCB": {"balance_sheet_fq_by_code": sheet, "item_code_names": {}}},
            {"landbank": [], "bank_loans": ["VCB"]},
        )
        printed = capsys.readouterr().out
        lines = [ln for ln in printed.splitlines() if ln.strip().startswith("19001")]
        assert lines, "the largest line was not printed"

    def test_a_fetched_line_that_never_reaches_the_record_is_visible(
            self, monkeypatch, capsys):
        # The third fault. The vendor carries 11420, the census sees it,
        # and the snapshot has no landbank_fq - so the fix is downstream of
        # the fetch and neither of the two obvious explanations is right.
        self._run(
            monkeypatch,
            {"NLG": {"balance_sheet_fq_by_code": {11420: 2.0e12},
                     "item_code_names": {}}},
            {"landbank": ["NLG"], "bank_loans": []},
            held={"NLG": {"landbank_fq": None}},
        )
        printed = capsys.readouterr().out
        assert "0 of 1 reach the snapshot as landbank_fq" in printed


class TestTheFocusedRunStaysFocused:
    def test_each_section_can_be_run_on_its_own(self):
        # A run that asks one question should print one answer: a job log
        # is readable only from its tail, and the full census buries it.
        # Every focused section needs a mode, or it can only be reached by
        # running the whole thing.
        import inspect
        source = inspect.getsource(census.main)
        for mode in ("landbank", "cashflow"):
            assert f'"{mode}"' in source, mode
            assert f'args.only == "{mode}"' in source, mode

    def test_the_workflow_can_reach_every_mode(self):
        """The workflow must not carry a second, shorter list of sections.

        It did. The step condition named 'true' and 'landbank' while the
        script had grown a third mode, so a run dispatched with 'cashflow'
        skipped the census entirely and still reported success - a
        measurement that silently did not happen, which is worse than one
        that fails.

        Now the workflow gates on "not false" and passes the value straight
        to --only, which rejects a name it does not have. This pins that:
        no list of section names in the workflow at all.
        """
        import inspect
        import pathlib
        import re

        workflow = pathlib.Path(__file__).resolve().parents[1] / (
            ".github/workflows/screener_sync.yml")
        text = workflow.read_text(encoding="utf-8")
        step = text[text.index("Census the vendor routes"):
                    text.index("Audit valuation coverage")]
        # Comments explain the trap by naming it; only what the runner
        # executes can fall out of step with the script.
        step = "\n".join(line for line in step.splitlines()
                         if not line.lstrip().startswith("#"))
        modes = set(re.findall(r'choices=\(([^)]*)\)',
                               inspect.getsource(census.main))[0]
                    .replace('"', "").replace(" ", "").split(","))
        assert "cashflow" in modes and "landbank" in modes
        for mode in modes - {"all"}:
            # A section name hard-coded in the workflow is the thing that
            # went wrong; the value is forwarded, never matched.
            assert f"'{mode}'" not in step, (
                f"the workflow names {mode!r}; it will fall behind the "
                f"script again"
            )
        assert 'ONLY="${{ github.event.inputs.vendor_census }}"' in step

    def test_the_section_runs_after_the_catalogue_in_a_full_census(self):
        source = open(census.__file__, encoding="utf-8").read()
        assert (source.index("print_field_catalogue(out)\n\n    # After")
                < source.index("landbank_and_loanbook(groups, args.workers,"
                               " out, held=_held_lines())"))
