"""Deciding which vendor is right, on evidence neither vendor controls.

Section 9 counts how often the two disagree. It cannot say who is wrong,
and a larger sample of the same two opinions never will - the census has
been circling that for several runs. What breaks the circle is a third
witness:

  cash   the cash flow statement's closing balance and the balance
         sheet's cash line are filed separately and have to meet
  cfo    the three section totals sum to the net change in cash, and the
         vendor's own three did so for 150 of 150 companies

A figure that breaks an identity the rest of the statement keeps is not a
second opinion about the same number. It is a different number.
"""
import io
import contextlib

import pytest

from scripts import vendor_census as census


def _run(monkeypatch, payloads, held):
    monkeypatch.setattr(census, "fetch_vndirect_financials",
                        lambda sym: payloads.get(sym, {}))
    monkeypatch.setattr(census, "_held_overlay_fields", lambda: held)
    out = {}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        census.third_witness(list(payloads), 1, out)
    return out["third_witness"], buf.getvalue()


def _payload(sheet_cash=100.0, flow_cash=100.0,
             net=10.0, cfo=6.0, cfi=3.0, cff=1.0, cash_fq=100.0):
    return {
        "balance_sheet_fq_by_code": {11100: sheet_cash},
        "cash_flow_fq_by_code": {37000: flow_cash},
        "cash_flow_ttm_by_code": {35000: net, 32000: cfo,
                                  33000: cfi, 34000: cff},
        "cash_fq": cash_fq,
        "ttm_quarter_count": 4,
    }


class TestTheCashWitness:
    def test_a_vendor_whose_statements_meet_is_called_coherent(self,
                                                              monkeypatch):
        report, _ = _run(monkeypatch, {"AAA": _payload()},
                         {"AAA": {"cash": 100.0}})
        assert report["cash"]["coherent"] == 1

    def test_a_vendor_whose_statements_disagree_is_not(self, monkeypatch):
        report, _ = _run(monkeypatch,
                         {"AAA": _payload(sheet_cash=100.0, flow_cash=400.0)},
                         {"AAA": {"cash": 100.0}})
        assert report["cash"]["coherent"] == 0
        assert report["cash"]["pairs"] == 1

    def test_the_balance_sheet_can_back_the_vendor(self, monkeypatch):
        # The record says 500, the vendor says 100, the balance sheet says
        # 100. That is not an opinion poll - it is a check.
        report, _ = _run(monkeypatch,
                         {"AAA": _payload(cash_fq=100.0)},
                         {"AAA": {"cash": 500.0}})
        assert report["cash"]["vendor_wins"] == 1
        assert report["cash"]["record_wins"] == 0

    def test_the_balance_sheet_can_back_the_record(self, monkeypatch):
        report, _ = _run(monkeypatch,
                         {"AAA": _payload(sheet_cash=500.0, flow_cash=500.0,
                                          cash_fq=100.0)},
                         {"AAA": {"cash": 500.0}})
        assert report["cash"]["record_wins"] == 1
        assert report["cash"]["vendor_wins"] == 0

    def test_both_being_wrong_is_its_own_answer(self, monkeypatch):
        # Counting it as a win for either would manufacture a verdict.
        report, _ = _run(monkeypatch,
                         {"AAA": _payload(sheet_cash=7.0, flow_cash=7.0,
                                          cash_fq=100.0)},
                         {"AAA": {"cash": 500.0}})
        assert report["cash"]["neither"] == 1
        assert report["cash"]["record_wins"] == 0
        assert report["cash"]["vendor_wins"] == 0

    def test_agreement_is_not_a_verdict_for_anybody(self, monkeypatch):
        # When both match the witness there is nothing to decide, and
        # counting it would pad whichever side happened to be listed first.
        report, _ = _run(monkeypatch, {"AAA": _payload()},
                         {"AAA": {"cash": 100.0}})
        assert report["cash"]["record_wins"] == 0
        assert report["cash"]["vendor_wins"] == 0

    def test_the_witness_is_not_the_number_being_judged(self, monkeypatch):
        """cash_fq is _latest([11100]) - the balance sheet line itself.

        The first version judged both candidates against the balance
        sheet, so the vendor was right by construction whenever both
        figures existed. It scored 644 to nil with nothing undecided, and
        a perfect score from a measurement is a reason to look at the
        measurement.

        Here the vendor echoes the balance sheet and the record matches
        the cash flow statement instead. Against the balance sheet the
        vendor wins; against the other statement, which is what the
        witness has to be, the record does. The old code fails this.
        """
        payload = _payload(sheet_cash=100.0, flow_cash=500.0,
                           cash_fq=100.0)
        report, _ = _run(monkeypatch, {"AAA": payload},
                         {"AAA": {"cash": 500.0}})
        assert report["cash"]["record_wins"] == 1
        assert report["cash"]["vendor_wins"] == 0

    def test_a_missing_line_is_not_counted(self, monkeypatch):
        payload = _payload()
        del payload["cash_flow_fq_by_code"][37000]
        report, text = _run(monkeypatch, {"AAA": payload},
                            {"AAA": {"cash": 100.0}})
        assert report["cash"]["pairs"] == 0
        assert "NOTHING COMPARED" in text


class TestTheCfoWitness:
    def test_the_vendors_own_triple_is_scored(self, monkeypatch):
        report, _ = _run(monkeypatch, {"AAA": _payload()},
                         {"AAA": {"cfo": 6.0}})
        assert report["cfo"]["vendor_closes"] == 1

    def test_a_record_figure_that_breaks_the_identity_is_caught(self,
                                                               monkeypatch):
        # 6 closes it; 90 does not, and no amount of sampling would have
        # told us that from the two opinions alone.
        report, _ = _run(monkeypatch, {"AAA": _payload()},
                         {"AAA": {"cfo": 90.0}})
        assert report["cfo"]["vendor_closes"] == 1
        assert report["cfo"]["record_closes"] == 0

    def test_a_record_figure_that_fits_is_not_condemned(self, monkeypatch):
        report, _ = _run(monkeypatch, {"AAA": _payload()},
                         {"AAA": {"cfo": 6.0}})
        assert report["cfo"]["record_closes"] == 1

    def test_a_company_missing_a_term_is_not_tested(self, monkeypatch):
        # Absent is not disagreement - the rule this census follows
        # everywhere. Reading a missing term as nil would fail companies
        # for the sparseness of the payload.
        payload = _payload()
        del payload["cash_flow_ttm_by_code"][34000]
        report, _ = _run(monkeypatch, {"AAA": payload},
                         {"AAA": {"cfo": 6.0}})
        assert report["cfo"]["tested"] == 0

    def test_a_company_with_no_record_figure_is_not_tested(self,
                                                          monkeypatch):
        report, _ = _run(monkeypatch, {"AAA": _payload()}, {"AAA": {}})
        assert report["cfo"]["tested"] == 0


class TestTheClosingBalanceIsReadAsABalance:
    def test_the_service_exports_the_statement_as_balances_too(self):
        # Cash at end is a stock. Summing four quarters of it gives four
        # times the balance and cannot be compared with the balance sheet,
        # which is the only independent evidence available here.
        import services.unified_data_service as uds

        source = open(uds.__file__, encoding="utf-8").read()
        assert '"cash_flow_fq_by_code"' in source
        assert "c: _latest([c]) for c in val_lookup if 30000 <= c < 40000" \
            in source

    def test_the_witness_reads_the_balance_export_not_the_flow_one(self):
        import inspect

        source = inspect.getsource(census.third_witness)
        assert '"cash_flow_fq_by_code", _CASH_AT_END' in source
