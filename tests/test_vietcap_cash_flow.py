"""The Vietcap cash-flow statement, read under the vendor's own names.

cfa18 and cfa19 are not guesses. The vendor census printed Vietcap's own
label beside every code in this statement, and those two read "Luu chuyen
tien te rong tu cac hoat dong san xuat kinh doanh" / "Net cash inflows from
operating activities" and "Tien chi de mua sam, xay dung TSCD" / "Purchase
of fixed assets". These tests hold that reading in place.
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


class TestFetchVietcapCashFlow:
    def test_both_lines_are_read(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2,
                    "cfa18": 8.3e9, "cfa19": -2.4e9}])))
        assert uds.fetch_vietcap_cash_flow("TST") == {
            "cfo": pytest.approx(8.3e9), "capex": pytest.approx(-2.4e9)}

    def test_the_newest_period_wins(self, monkeypatch):
        """The route does not serve newest-first; the census proved it."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([
                {"yearReport": 2018, "lengthReport": 5, "cfa18": 1.0e9},
                {"yearReport": 2025, "lengthReport": 2, "cfa18": 9.0e9},
            ])))
        assert uds.fetch_vietcap_cash_flow("TST")["cfo"] == pytest.approx(9.0e9)

    def test_a_negative_operating_cash_flow_survives(self, monkeypatch):
        """Burning cash is a fact about a company, not missing data."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "cfa18": -4.0e9}])))
        assert uds.fetch_vietcap_cash_flow("TST")["cfo"] == pytest.approx(-4.0e9)

    @pytest.mark.parametrize("value", [0.0, 12.5, 1e16, None, "n/a"])
    def test_an_implausible_line_is_dropped(self, value, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "cfa18": value}])))
        assert "cfo" not in uds.fetch_vietcap_cash_flow("TST")

    def test_one_line_present_and_one_absent(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            _body([{"yearReport": 2025, "lengthReport": 2, "cfa18": 8.3e9}])))
        assert uds.fetch_vietcap_cash_flow("TST") == {"cfo": pytest.approx(8.3e9)}

    @pytest.mark.parametrize("payload", [
        {}, {"data": {}}, {"data": {"quarters": []}}, None, _BAD,
    ])
    def test_an_unusable_body_yields_nothing(self, payload, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp(payload))
        assert uds.fetch_vietcap_cash_flow("TST") == {}

    def test_transport_failure(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: None)
        assert uds.fetch_vietcap_cash_flow("TST") == {}

    def test_the_cash_flow_section_is_asked_for(self, monkeypatch):
        """The statement route serves four sections; asking for the wrong one
        returns a well-formed body with no cash flow in it."""
        seen = {}

        def _spy(method, url, **kwargs):
            seen["url"] = url
            seen["params"] = kwargs.get("params")
            return None

        monkeypatch.setattr(uds, "_request_with_retry", _spy)
        uds.fetch_vietcap_cash_flow("tst")
        assert seen["params"] == {"section": "CASH_FLOW"}
        assert seen["url"].endswith("/TST/financial-statement")
