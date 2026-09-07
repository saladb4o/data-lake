"""EBIT is the largest blocking driver (755 symbols) and the only one the
valuation engine cannot derive: the operating line comes out of the upstream
ladder or it does not exist. The census showed all four of its rungs empty
for those symbols - TradingView serves the EBIT family to about 760 symbols
and thin coverage to the rest.

Vietcap answered 564 of 564 when asked for share counts, and its
statistics-financial route carries an EBIT margin. These tests pin why it is
the *margin* that is read and not the "ebit" field sitting beside it.
"""

import pytest

from services import unified_data_service as uds


class TestTheUnitTrap:
    """The payload carries "ebit" outright and nothing in it states a unit.

    This vendor already publishes share counts in millions under a name that
    says nothing of the sort. An absolute EBIT read at the wrong scale is
    wrong by a factor of a billion and would not surface as an error - it
    would surface as a valuation.
    """

    def test_the_absolute_ebit_field_is_never_read(self):
        aliases = uds._VIETCAP_EBIT_MARGIN_ALIASES
        assert "ebit" not in aliases
        assert "ebitda" not in aliases
        assert all("argin" in a or "_margin" in a for a in aliases)

    @pytest.mark.parametrize("margin", [-500.0, 101.0, -100.5, 1e9])
    def test_a_value_outside_the_percentage_band_is_discarded(self, margin, monkeypatch):
        """Not reinterpreted, not rescaled - discarded. A number that is not
        a percentage is not evidence about one."""
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebitMargin": margin}}))
        assert uds.fetch_vietcap_ebit_margin("TST") is None

    @pytest.mark.parametrize("margin", [-100.0, -12.5, 0.0, 8.4, 100.0])
    def test_a_plausible_percentage_is_kept(self, margin, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebitMargin": margin}}))
        assert uds.fetch_vietcap_ebit_margin("TST") == margin

    def test_a_negative_margin_survives(self, monkeypatch):
        """A loss-making company has a negative operating margin. Clamping it
        at zero would publish a profit nobody earned."""
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebitMargin": -31.0}}))
        assert uds.fetch_vietcap_ebit_margin("TST") == -31.0


class _Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


class TestTheEnvelope:
    """vnstock reads this route into a frame keyed years/quarters, so the
    document is a series. The shape is not pinned by any contract available
    here, so every plausible arrangement is accepted and anything else
    yields nothing rather than a guess."""

    def test_quarters_series(self):
        body = {"data": {"quarters": [{"ebitMargin": 9.1}, {"ebitMargin": 2.0}]}}
        assert uds._vietcap_latest_period(body)["ebitMargin"] == 9.1

    def test_years_series_when_there_are_no_quarters(self):
        body = {"data": {"years": [{"ebitMargin": 7.7}]}}
        assert uds._vietcap_latest_period(body)["ebitMargin"] == 7.7

    def test_quarters_win_over_years(self):
        body = {"data": {"quarters": [{"ebitMargin": 1.0}],
                         "years": [{"ebitMargin": 2.0}]}}
        assert uds._vietcap_latest_period(body)["ebitMargin"] == 1.0

    def test_a_bare_list(self):
        assert uds._vietcap_latest_period({"data": [{"ebitMargin": 3.0}]})["ebitMargin"] == 3.0

    def test_a_flat_record(self):
        assert uds._vietcap_latest_period({"data": {"ebitMargin": 4.0}})["ebitMargin"] == 4.0

    def test_an_unrecognised_shape_yields_nothing(self):
        assert uds._vietcap_latest_period({"data": "surprise"}) == {}
        assert uds._vietcap_latest_period(None) == {}


class TestFailureIsSilentAndTotal:
    def test_transport_failure(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: None)
        assert uds.fetch_vietcap_ebit_margin("TST") is None

    def test_malformed_json(self, monkeypatch):
        class Bad:
            status_code = 200

            def json(self):
                raise ValueError("not json")

        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: Bad())
        assert uds.fetch_vietcap_ebit_margin("TST") is None

    def test_no_margin_in_the_body(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebit": 4.2e12}}))
        assert uds.fetch_vietcap_ebit_margin("TST") is None


class TestWhichSymbolsAreAsked:
    """Only symbols with no rung at all, and only those that have the revenue
    the margin has to multiply. Asking for the rest spends requests to learn
    nothing."""

    @pytest.mark.parametrize("entry", [
        {"ebit_ttm": 1.0},
        {"ebit_fq": 1.0},
        {"pretax_income_ttm": 1.0, "interest_expense_on_debt_ttm": 2.0},
        {"ebitda_ttm": 1.0, "depreciation_and_amortization_ttm": 2.0},
        {"operating_margin_ttm": 8.0},
        {"operating_margin_fq": 8.0},
    ])
    def test_a_symbol_with_a_rung_is_not_asked(self, entry):
        assert uds._has_no_ebit_rung(entry) is False

    @pytest.mark.parametrize("entry", [
        None,
        {},
        {"net_income_ttm": 5.0},
        {"pretax_income_ttm": 1.0},          # half of rung 2 is not rung 2
        {"interest_expense_on_debt_ttm": 1.0},
        {"ebitda_ttm": 1.0},                 # D&A absent, so no subtraction
        {"depreciation_and_amortization_ttm": 1.0},
    ])
    def test_a_symbol_with_no_rung_is_asked(self, entry):
        assert uds._has_no_ebit_rung(entry) is True
