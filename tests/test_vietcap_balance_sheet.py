"""The Vietcap balance sheet, read under the vendor's own names.

bsa2 is not a guess. The census printed Vietcap's own label beside all 122
codes in this statement, and bsa2 reads "Tien va tuong duong tien" / "Cash
and cash equivalents". These tests hold that reading in place - and hold the
line on the two the route deliberately does NOT read.
"""
import pytest

import services.unified_data_service as uds


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        if self._payload is _BAD:
            raise ValueError("not json")
        return self._payload


_BAD = object()


def _body(rows):
    return {"data": {"quarters": rows}}


class TestFetchVietcapBalanceSheet:
    def test_cash_is_read(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "bsa2": 4.7e10}])))
        assert uds.fetch_vietcap_balance_sheet("TST") == {
            "cash": pytest.approx(4.7e10)}

    def test_the_newest_period_wins(self, monkeypatch):
        """The route does not serve newest-first; the census proved it."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([
                {"yearReport": 2018, "lengthReport": 4, "bsa2": 1.0e10},
                {"yearReport": 2025, "lengthReport": 2, "bsa2": 4.7e10},
                {"yearReport": 2024, "lengthReport": 4, "bsa2": 3.0e10},
            ])))
        assert uds.fetch_vietcap_balance_sheet("TST")["cash"] == pytest.approx(4.7e10)

    def test_a_figure_below_a_million_is_another_unit(self, monkeypatch):
        """Not merely a small company: a VN balance sheet is in dong."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "bsa2": 47.0}])))
        assert uds.fetch_vietcap_balance_sheet("TST") == {}

    @pytest.mark.parametrize("payload", [None, _BAD, {}, {"data": {}},
                                         _body([]), _body([{"bsa2": None}])])
    def test_every_failure_shape_yields_empty(self, monkeypatch, payload):
        monkeypatch.setattr(
            uds, "_request_with_retry",
            lambda *a, **k: None if payload is None else _Resp(payload))
        assert uds.fetch_vietcap_balance_sheet("TST") == {}

    def test_it_asks_for_the_balance_sheet_section(self, monkeypatch):
        seen = {}

        def _spy(method, url, **kw):
            seen.update(kw.get("params") or {})
            return _Resp(_body([{"yearReport": 2025, "lengthReport": 2,
                                 "bsa2": 4.7e10}]))

        monkeypatch.setattr(uds, "_request_with_retry", _spy)
        uds.fetch_vietcap_balance_sheet("TST")
        assert seen.get("section") == "BALANCE_SHEET"

    def test_the_symbol_is_normalised(self, monkeypatch):
        seen = {}

        def _spy(method, url, **kw):
            seen["url"] = url
            return _Resp(_body([{"yearReport": 2025, "lengthReport": 2,
                                 "bsa2": 4.7e10}]))

        monkeypatch.setattr(uds, "_request_with_retry", _spy)
        uds.fetch_vietcap_balance_sheet(" tst ")
        assert "/TST/" in seen["url"]


class TestDebtStaysUnwired:
    """A missing name was never the obstacle; missing data was.

    The route was held back for two runs on the grounds that debt could not
    be defined without the vendor's names for the borrowing lines. The names
    arrived and did not help: bsa56 "Vay ngan han" carries a figure for 25 of
    73 companies and bsa71 "Vay dai han" for 17. Summing them yields a real
    debt for a third of the group and a zero for the rest, and a zero here
    means "not stated", not "no borrowings" - a distinction that vanishes
    downstream, where zero is a valid number that passes the provenance gate
    and lowers enterprise value.

    These tests exist so that wiring debt later has to be a decision rather
    than an accident.
    """

    def test_borrowing_lines_are_not_returned(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "bsa2": 4.7e10,
                    "bsa56": 2.0e10, "bsa71": 9.0e9}])))
        out = uds.fetch_vietcap_balance_sheet("TST")
        assert out == {"cash": pytest.approx(4.7e10)}
        assert "debt" not in out

    def test_total_liabilities_is_not_sold_as_debt(self, monkeypatch):
        """bsa54 is near-complete and is still the wrong number.

        It is TOTAL liabilities - trade payables, taxes and wages included -
        and the models spend debt as market_cap + debt - cash. Substituting
        it would overstate enterprise value for every company that buys on
        credit.
        """
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "bsa2": 4.7e10,
                    "bsa54": 2.78e10}])))
        out = uds.fetch_vietcap_balance_sheet("TST")
        assert "debt" not in out
        assert out["cash"] == pytest.approx(4.7e10)

    def test_a_company_reporting_no_borrowings_yields_no_zero(self, monkeypatch):
        """The failure mode this route is shaped to avoid."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "bsa2": 4.7e10}])))
        out = uds.fetch_vietcap_balance_sheet("TST")
        assert out.get("debt") is None


class TestTheNarrowColumnActuallyReaches:
    """Writing to the fallback column is only useful if the fallback is read.

    normalize_stock_data reads cash_n_short_term_invest_fq first and
    cash_n_cash_equivalents_fq second. This route fills the second on
    purpose - the two are different quantities, and the vendor states
    short-term investments separately as bsa5 - so the whole wiring turns on
    that fallback existing. It already did, for TradingView, so this is a
    regression guard rather than evidence for the new code.
    """

    def test_the_fallback_column_produces_a_cash_figure(self):
        out = uds.normalize_stock_data(
            symbol="TST", exchange="HOSE", name="Test",
            sector_code="VNIND", sector_name="Cong Nghiep",
            tv_data={"close": 20_000.0, "total_shares_outstanding_fq": 3e8,
                     "cash_n_cash_equivalents_fq": 4.7e10},
        )
        assert uds._safe_float(out.get("cash")) == pytest.approx(4.7e10)

    def test_the_wide_column_still_wins_when_present(self):
        """Nothing already held is displaced by the narrower figure."""
        out = uds.normalize_stock_data(
            symbol="TST", exchange="HOSE", name="Test",
            sector_code="VNIND", sector_name="Cong Nghiep",
            tv_data={"close": 20_000.0, "total_shares_outstanding_fq": 3e8,
                     "cash_n_short_term_invest_fq": 6.0e10,
                     "cash_n_cash_equivalents_fq": 4.7e10},
        )
        assert uds._safe_float(out.get("cash")) == pytest.approx(6.0e10)
