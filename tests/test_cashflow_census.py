"""The census that locates operating cash flow, capex and borrowings.

Two questions over one population, because the same payloads answer both.

fcf blocks more symbols than any other driver. An earlier measurement
concluded the vendor carries neither cfo nor capex for those companies - on
the same kind of evidence that concluded the land bank was absent, which
turned out to be a pair of item codes read wrong.

And under the numbering that census recovered - itemCode is 1 + the
three-digit VAS code + 0 - the debt extractor reads 13000 and 13100, which
are VAS 300 (NO PHAI TRA, total liabilities) and VAS 310 (current
liabilities). Neither is borrowings. That is a wrong number published
rather than a refusal, and it inflates net_de_ratio for every company
TradingView leaves out.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.unified_data_service as uds
from scripts import vendor_census as census


#: Four quarters, because that is what a TTM sum is built from. With
#: fewer, _sum_ttm annualises by 4/len - correct, and a trap for anyone
#: reading a census table as raw quarterly figures, so it is pinned below.
_QUARTERS = ("2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30")


def _raw(rows, dates=_QUARTERS):
    return [{"itemCode": c, "fiscalDate": d, "numericValue": v,
             "itemName": ""} for c, v in rows for d in dates]


class TestTheCashFlowIsExportedByCode:
    @staticmethod
    @pytest.fixture
    def stub(monkeypatch):
        def _install(rows):
            import services.stock_service as ss
            monkeypatch.setattr(
                ss, "fetch_vndirect_raw_statements",
                lambda symbol, report_type="ANNUAL", target_quarters=16:
                    _raw(rows),
                raising=False)
            monkeypatch.setattr(ss.cache, "get", lambda *a, **k: None)
            monkeypatch.setattr(ss.cache, "set", lambda *a, **k: None)
        return _install

    def test_a_cash_flow_code_is_exported(self, stub):
        stub([(31000, 2.0e11), (32100, -8.0e10)])
        out = uds.fetch_vndirect_financials("AAA")
        assert out["cash_flow_ttm_by_code"][31000] == 8.0e11  # four quarters

    def test_a_short_history_is_annualised_not_summed(self, stub):
        # _sum_ttm scales by 4/len when the vendor sent fewer than four
        # quarters. The export carries that through, so a census table
        # shows an annual rate and not the quarter - worth stating,
        # because reading it as a quarter understates by up to fourfold.
        stub([(31000, 2.0e11)])
        import services.stock_service as ss
        ss.fetch_vndirect_raw_statements = (
            lambda symbol, report_type="ANNUAL", target_quarters=16:
            _raw([(31000, 2.0e11)], dates=("2025-06-30",)))
        out = uds.fetch_vndirect_financials("AAB")
        assert out["cash_flow_ttm_by_code"][31000] == 8.0e11

    def test_the_other_statements_stay_out_of_it(self, stub):
        stub([(31000, 2.0e11), (12700, 5.0e12), (21001, 1.0e12)])
        codes = uds.fetch_vndirect_financials("AAA")["cash_flow_ttm_by_code"]
        assert set(codes) == {31000}


class TestItReportsWhatIsThere:
    @staticmethod
    def _run(monkeypatch, payload):
        monkeypatch.setattr(census, "fetch_vndirect_financials",
                            lambda sym: payload)
        out = {}
        census.cash_flows_and_borrowings(["AAA"], 1, out)
        return out["cash_flows_and_borrowings"]

    PAYLOAD = {
        "revenue_ttm": 1.0e12,
        "cash_flow_ttm_by_code": {31000: 2.0e11, 32100: -8.0e10, 31999: 0.0},
        "balance_sheet_fq_by_code": {12700: 5.0e12, 13000: 2.5e12,
                                     13200: 9.0e11},
        "item_code_names": {},
    }

    def test_the_lines_the_service_reads_are_counted(self, monkeypatch):
        report = self._run(monkeypatch, self.PAYLOAD)
        assert report["per_line"] == {"cfo": 1, "capex": 1}

    def test_cash_flow_is_sized_against_revenue(self, monkeypatch):
        # Against revenue, not assets: operating cash flow and capex are
        # both fractions of sales, and that is what makes a code legible.
        report = self._run(monkeypatch, self.PAYLOAD)
        assert report["cash_flow_codes"][31000]["median_share"] == 0.2

    def test_a_zero_line_is_reported_as_zero_not_as_present(self, monkeypatch):
        report = self._run(monkeypatch, self.PAYLOAD)
        assert report["cash_flow_codes"][31999]["nonzero"] == 0

    def test_only_liability_codes_appear_in_the_borrowings_table(
            self, monkeypatch):
        # 13xxx is VAS 3xx, the liabilities side. Total assets sitting in
        # that table would be the largest row and would read as the answer.
        report = self._run(monkeypatch, self.PAYLOAD)
        assert 13200 in report["liability_codes"]
        assert 12700 not in report["liability_codes"]

    def test_no_cash_flow_statement_is_said_so_rather_than_shown_empty(
            self, monkeypatch, capsys):
        self._run(monkeypatch, {"revenue_ttm": 1.0e12,
                                "balance_sheet_fq_by_code": {12700: 5.0e12},
                                "item_code_names": {}})
        assert "does not serve one" in capsys.readouterr().out


class TestItCensusesTheCodesInForce:
    def test_the_cash_flow_codes_match_the_service(self):
        source = open(uds.__file__, encoding="utf-8").read()
        assert "_sum_ttm([31000, 31100])" in source
        assert "_sum_ttm([32100, 32110, 32010])" in source
        assert census.CASH_FLOW_CODES["cfo"] == (31000, 31100)
        assert census.CASH_FLOW_CODES["capex"] == (32100, 32110, 32010)

    def test_the_debt_codes_match_the_service(self):
        # When debt is retargeted at real borrowings this must be updated
        # with it, or the census goes on measuring a question nobody asks.
        source = open(uds.__file__, encoding="utf-8").read()
        assert f"_latest({list(census.DEBT_CODES)})" in source

    @staticmethod
    def _snapshot(tmp_path, monkeypatch, body):
        snapshot = tmp_path / "screener_snapshot.json"
        snapshot.write_text(body, encoding="utf-8")
        monkeypatch.setattr(uds, "screener_snapshot_file",
                            lambda: str(snapshot))

    def test_the_population_is_chosen_by_tier_not_by_presence(
            self, tmp_path, monkeypatch):
        """A value that is present but untrustworthy is what blocks fcf.

        The first version of this picker asked whether cfo and capex were
        None and found three companies in 1,523: both ladders end in a
        fallback - capex at tier 1 from D&A, then tier 0 - so the record
        always carries a number. Selecting on presence measured a
        population that had nothing to do with the driver being censused.
        """
        self._snapshot(tmp_path, monkeypatch,
                       '{"stocks": {'
                       '"AAA": {"symbol": "AAA", "cfo": 1.0, "capex": 2.0,'
                       ' "field_provenance": {"cfo": 3, "capex": 3}},'
                       '"BBB": {"symbol": "BBB", "cfo": 1.0, "capex": 2.0,'
                       ' "field_provenance": {"cfo": 3, "capex": 1}},'
                       '"CCC": {"symbol": "CCC", "cfo": 1.0, "capex": 2.0,'
                       ' "field_provenance": {"cfo": 0, "capex": 0}}}}')
        # BBB and CCC hold a number for both lines and are still refused.
        assert census.pick_cashflow_symbols(None) == ["BBB", "CCC"]

    def test_a_company_with_no_tiers_at_all_is_included(self, tmp_path,
                                                        monkeypatch):
        self._snapshot(tmp_path, monkeypatch,
                       '{"stocks": {"DDD": {"symbol": "DDD"}}}')
        assert census.pick_cashflow_symbols(None) == ["DDD"]

    def test_the_gate_has_not_drifted_from_the_engines(self):
        # _TRUSTED is a copy, kept so the census need not import the
        # valuation engine to ask a question about a vendor.
        from services.valuation_engine import InputResolver
        assert census._TRUSTED == InputResolver.MIN_TRUSTED_UPSTREAM_TIER

class TestTheDecodingIsConfirmedByArithmetic:
    """The vendor names no code, so an identity is the only real evidence.

    A label can be guessed wrong and a magnitude can be a coincidence. An
    identity that reproduces on hundreds of separate companies is the
    statement's own arithmetic and cannot be talked into holding.

    itemCode on the cash flow statement reads as 3 + the two-digit VAS B03
    code + 00, which puts net cash from operations at 32000 - not at the
    31000/31100 the extractor reads. On three companies the medians of
    36000, 35000 and 37000 closed to four decimals. Three companies and a
    median is not evidence, which is what these tests exist to enforce.
    """

    GOOD = {"cash_flow_ttm_by_code": {
        37000: 300.0, 36000: 500.0, 35000: -200.0,
        32000: -260.0, 33000: 40.0, 34000: 20.0}}
    BAD = {"cash_flow_ttm_by_code": {
        37000: 300.0, 36000: 500.0, 35000: 99.0,
        32000: 1.0, 33000: 1.0, 34000: 1.0}}

    def test_a_statement_that_closes_is_counted(self):
        r = census._check_identities([self.GOOD], "cash_flow_ttm_by_code",
                                     census.CASH_FLOW_IDENTITIES)
        assert all(v["held"] == 1 and v["tested"] == 1 for v in r.values())

    def test_a_statement_that_does_not_close_is_counted_against(self):
        r = census._check_identities([self.GOOD, self.GOOD, self.BAD],
                                     "cash_flow_ttm_by_code",
                                     census.CASH_FLOW_IDENTITIES)
        assert all(v["held"] == 2 and v["tested"] == 3 for v in r.values())

    def test_a_company_missing_a_term_is_not_tested_rather_than_failed(self):
        # Absent is not disagreement. Counting a missing line as a broken
        # identity would make a sparse payload look like a wrong decoding.
        r = census._check_identities(
            [{"cash_flow_ttm_by_code": {37000: 300.0}}],
            "cash_flow_ttm_by_code", census.CASH_FLOW_IDENTITIES)
        assert all(v["tested"] == 0 and v["rate"] is None
                   for v in r.values())

    def test_it_is_checked_per_company_and_not_on_the_medians(self):
        # A median satisfies an identity whenever one company happens to
        # be the median of every term - likely at n=3, and meaningless.
        # Two companies whose medians would close but neither of which
        # closes on its own must score zero.
        left = {"cash_flow_ttm_by_code": {37000: 300.0, 36000: 500.0,
                                          35000: 0.0}}
        right = {"cash_flow_ttm_by_code": {37000: 0.0, 36000: 0.0,
                                           35000: -200.0}}
        r = census._check_identities([left, right], "cash_flow_ttm_by_code",
                                     census.CASH_FLOW_IDENTITIES)
        assert r["cash at end = cash at start + net change"]["held"] == 0

    def test_the_identity_the_extractor_contradicts_is_the_one_checked(self):
        # cfo reads 31000/31100; the identity places net operating cash at
        # 32000. If the identity is dropped the disagreement goes unnoticed.
        targets = {t for _, _, terms in census.CASH_FLOW_IDENTITIES
                   for t in terms}
        assert 32000 in targets
        assert 32000 not in census.CASH_FLOW_CODES["cfo"]
