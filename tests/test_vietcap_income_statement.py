"""The Vietcap income statement, read under the vendor's own names.

The census printed Vietcap's label beside every code in this statement:
isa3 "Doanh thu thuan" / "Net sales", isa20 "Lai/(lo) thuan sau thue",
isa23 "Lai co ban tren co phieu (VND)" / "EPS basic", isa11 operating
profit and isa8 interest expense. These tests hold that reading in place,
and pin the one line that is reconstructed rather than read.
"""
import pytest

import services.unified_data_service as uds


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _body(**row):
    row.setdefault("yearReport", 2025)
    row.setdefault("lengthReport", 2)
    return {"data": {"quarters": [row]}}


def _fetch(monkeypatch, **row):
    monkeypatch.setattr(uds, "_request_with_retry",
                        lambda *a, **k: _Resp(_body(**row)))
    return uds.fetch_vietcap_income_statement("TST")


class TestLinesThatAreRead:
    def test_net_sales_is_revenue(self, monkeypatch):
        assert _fetch(monkeypatch, isa3=1.54e11)["revenue"] == pytest.approx(1.54e11)

    def test_net_profit_after_tax_is_net_income(self, monkeypatch):
        assert _fetch(monkeypatch, isa20=5.7e9)["net_income"] == pytest.approx(5.7e9)

    def test_a_loss_survives(self, monkeypatch):
        assert _fetch(monkeypatch, isa20=-5.7e9)["net_income"] == pytest.approx(-5.7e9)

    def test_the_newest_period_wins(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            {"data": {"quarters": [
                {"yearReport": 2018, "lengthReport": 5, "isa3": 1.0e9},
                {"yearReport": 2025, "lengthReport": 2, "isa3": 9.0e9},
            ]}}))
        out = uds.fetch_vietcap_income_statement("TST")
        assert out["revenue"] == pytest.approx(9.0e9)


class TestReportedEps:
    def test_an_eps_in_dong_per_share_is_read(self, monkeypatch):
        assert _fetch(monkeypatch, isa23=1033.0)["eps"] == pytest.approx(1033.0)

    def test_a_negative_eps_survives(self, monkeypatch):
        assert _fetch(monkeypatch, isa23=-450.0)["eps"] == pytest.approx(-450.0)

    def test_a_padded_zero_is_not_an_eps(self, monkeypatch):
        """The census found this column zero-padded for non-reporters. A zero
        here says "not stated", not "earned nothing"."""
        assert "eps" not in _fetch(monkeypatch, isa23=0.0)

    @pytest.mark.parametrize("value", [0.4, 1e7, None, "n/a"])
    def test_an_implausible_eps_is_dropped(self, value, monkeypatch):
        assert "eps" not in _fetch(monkeypatch, isa23=value)

    def test_eps_is_not_measured_against_the_operating_line_bound(self, monkeypatch):
        """1033 dong is a normal EPS and far below the 1e6 floor that applies
        to a line stated in dong. Sharing one bound would discard every EPS."""
        assert _fetch(monkeypatch, isa23=1033.0, isa3=1.5e11)["eps"] == 1033.0


class TestEbitIsReconstructed:
    def test_interest_is_added_back_to_operating_profit(self, monkeypatch):
        """VAS publishes no EBIT. isa11 is operating profit after financial
        expense, so isa8 - which the statement states, and states negative -
        goes back on."""
        out = _fetch(monkeypatch, isa11=6.45e9, isa8=-6.11e8)
        assert out["ebit"] == pytest.approx(6.45e9 + 6.11e8)

    def test_the_sign_of_interest_does_not_matter(self, monkeypatch):
        a = _fetch(monkeypatch, isa11=6.45e9, isa8=-6.11e8)["ebit"]
        b = _fetch(monkeypatch, isa11=6.45e9, isa8=6.11e8)["ebit"]
        assert a == pytest.approx(b)

    def test_half_a_reconstruction_is_not_offered(self, monkeypatch):
        assert "ebit" not in _fetch(monkeypatch, isa11=6.45e9)
        assert "ebit" not in _fetch(monkeypatch, isa8=-6.11e8)

    def test_operating_profit_is_still_reported_on_its_own(self, monkeypatch):
        out = _fetch(monkeypatch, isa11=6.45e9)
        assert out["operating_profit"] == pytest.approx(6.45e9)


class TestFailureShapes:
    @pytest.mark.parametrize("payload", [
        {}, {"data": {}}, {"data": {"quarters": []}}, None,
    ])
    def test_an_unusable_body_yields_nothing(self, payload, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp(payload))
        assert uds.fetch_vietcap_income_statement("TST") == {}

    def test_transport_failure(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: None)
        assert uds.fetch_vietcap_income_statement("TST") == {}

    def test_the_income_statement_section_is_asked_for(self, monkeypatch):
        seen = {}

        def _spy(method, url, **kwargs):
            seen.update(url=url, params=kwargs.get("params"))
            return None

        monkeypatch.setattr(uds, "_request_with_retry", _spy)
        uds.fetch_vietcap_income_statement("tst")
        assert seen["params"] == {"section": "INCOME_STATEMENT"}
        assert seen["url"].endswith("/TST/financial-statement")
