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

    # These three were rewritten, not adjusted. As first written they
    # asserted that this route sends a percentage and that the value passes
    # through untouched - and they passed, which is why the hundred-fold
    # error survived a green suite. They encoded the assumption instead of
    # the measurement, because they were written before the census measured
    # the unit at all.
    #
    # What the census established: ebit/revenue on this same record is
    # 0.0405 while the record's own ebitMargin reads 0.04. A ratio of two
    # dong figures is a fraction, so the field beside it is a fraction. The
    # consumer divides by 100, so the fetch multiplies by 100.

    @pytest.mark.parametrize("margin", [-5.0, 1.01, -1.005, 1e9])
    def test_a_fraction_outside_the_band_is_discarded(self, margin, monkeypatch):
        """Not reinterpreted, not rescaled twice - discarded. A company does
        not earn more operating profit than revenue."""
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebitMargin": margin}}))
        assert uds.fetch_vietcap_ebit_margin("TST") is None

    @pytest.mark.parametrize("fraction,percent", [
        (-1.0, -100.0), (-0.125, -12.5), (0.0, 0.0), (0.084, 8.4), (1.0, 100.0),
    ])
    def test_a_fraction_is_returned_as_a_percentage(self, fraction, percent,
                                                    monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebitMargin": fraction}}))
        assert uds.fetch_vietcap_ebit_margin("TST") == pytest.approx(percent)

    def test_a_negative_margin_survives(self, monkeypatch):
        """A loss-making company has a negative operating margin. Clamping it
        at zero would publish a profit nobody earned."""
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebitMargin": -0.31}}))
        assert uds.fetch_vietcap_ebit_margin("TST") == pytest.approx(-31.0)

    def test_both_routes_agree_on_the_unit(self, monkeypatch):
        """The bug in one sentence: two fetches fed one column two units.

        statistics-financial states 0.04; the GraphQL route computes
        ebit/revenue*100 and states 4.0. Whichever answers, the consumer
        must receive the same number for the same company."""
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"ebitMargin": 0.04}}))
        from_stats = uds.fetch_vietcap_ebit_margin("TST")
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            {"data": {"CompanyFinancialRatio": {"ratio": [
                {"yearReport": 2025, "lengthReport": 2,
                 "ebit": 4.0e9, "revenue": 1.0e11}]}}}))
        from_graphql = uds.fetch_vietcap_ebit_margin_graphql("TST")
        assert from_stats == pytest.approx(from_graphql)


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


class TestTheGraphqlRoute:
    """Vietcap's GraphQL ratio service reports EBIT and revenue side by side.

    That adjacency is the whole point. Whatever unit the vendor keeps them
    in, it is the same unit for both, so their ratio carries no unit at all
    and the scale question that makes a bare EBIT unusable never arises.
    """

    @staticmethod
    def _body(rows):
        return {"data": {"CompanyFinancialRatio": {"ratio": rows}}}

    def test_the_margin_is_the_ratio_of_two_fields_in_one_record(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            self._body([{"yearReport": 2025, "lengthReport": 2,
                         "ebit": 8.0e11, "revenue": 1.0e13}])))
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") == pytest.approx(8.0)

    def test_the_unit_cancels(self, monkeypatch):
        """The same company reported in billions must give the same margin."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            self._body([{"yearReport": 2025, "lengthReport": 2,
                         "ebit": 800.0, "revenue": 10000.0}])))
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") == pytest.approx(8.0)

    def test_the_newest_period_wins(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            self._body([
                {"yearReport": 2023, "lengthReport": 4, "ebit": 1.0, "revenue": 100.0},
                {"yearReport": 2025, "lengthReport": 2, "ebit": 9.0, "revenue": 100.0},
                {"yearReport": 2025, "lengthReport": 1, "ebit": 5.0, "revenue": 100.0},
            ])))
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") == pytest.approx(9.0)

    def test_a_loss_is_carried_through(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            self._body([{"yearReport": 2025, "lengthReport": 2,
                         "ebit": -2.5e11, "revenue": 1.0e12}])))
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") == pytest.approx(-25.0)

    def test_an_impossible_ratio_is_discarded(self, monkeypatch):
        """A company does not earn more operating profit than revenue. Such a
        pair is not what it is labelled, so it is dropped - not rescaled."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            self._body([{"yearReport": 2025, "lengthReport": 2,
                         "ebit": 5.0e12, "revenue": 1.0e9}])))
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") is None

    def test_a_later_usable_row_is_taken_when_the_newest_is_not(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            self._body([
                {"yearReport": 2025, "lengthReport": 2, "ebit": None, "revenue": 100.0},
                {"yearReport": 2024, "lengthReport": 4, "ebit": 7.0, "revenue": 100.0},
            ])))
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") == pytest.approx(7.0)

    @pytest.mark.parametrize("revenue", [0.0, -5.0, None])
    def test_a_revenue_that_cannot_divide_is_skipped(self, revenue, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            self._body([{"yearReport": 2025, "lengthReport": 2,
                         "ebit": 5.0, "revenue": revenue}])))
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") is None

    @pytest.mark.parametrize("body", [
        {}, {"data": {}}, {"data": {"CompanyFinancialRatio": {}}},
        {"data": {"CompanyFinancialRatio": {"ratio": "nope"}}},
        {"errors": [{"message": "boom"}]},
        None, [1, 2, 3],
    ])
    def test_an_unrecognised_body_yields_nothing(self, body):
        assert uds._vietcap_ratio_rows(body) == []

    def test_transport_failure(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: None)
        assert uds.fetch_vietcap_ebit_margin_graphql("TST") is None

    def test_the_query_asks_for_both_halves_of_the_ratio(self):
        for field in ("ebit", "revenue", "roic", "yearReport", "lengthReport"):
            assert field in uds._VIETCAP_RATIO_QUERY


class TestRoic:
    """roic: the largest blocking driver, and never once asked for.

    The ladder read only TradingView's return_on_invested_capital_fq while
    this route reports roic for 629 of 720 measured companies, named, at a
    median of 0.06. Four of the first twenty refusals are blocked by roic
    alone - tier-3 companies refused over one derived ratio.
    """

    def test_a_fraction_is_returned_as_a_percentage(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"roic": 0.084}}))
        assert uds.fetch_vietcap_roic("TST") == pytest.approx(8.4)

    def test_precision_survives_the_scaling(self, monkeypatch):
        """_safe_float rounds to two decimals. Scaling after the conversion
        would turn 0.084 into 0.08 and a 0.4% return into nothing; its own
        `scale` multiplies first."""
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"roic": 0.004}}))
        assert uds.fetch_vietcap_roic("TST") == pytest.approx(0.4)

    def test_a_negative_return_survives(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"roic": -0.15}}))
        assert uds.fetch_vietcap_roic("TST") == pytest.approx(-15.0)

    @pytest.mark.parametrize("value", [0.0, 5.0, -3.0, None, "n/a"])
    def test_an_unusable_roic_is_dropped(self, value, monkeypatch):
        """Zero is this vendor's padding for "not stated", and a fraction
        above 1 is not a return on capital it measured."""
        monkeypatch.setattr(uds, "_request_with_retry",
                            lambda *a, **k: _Resp({"data": {"roic": value}}))
        assert uds.fetch_vietcap_roic("TST") is None

    def test_transport_failure(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: None)
        assert uds.fetch_vietcap_roic("TST") is None

    def test_it_rides_along_on_the_operating_line_request(self, monkeypatch):
        """One request already fetches this record; taking roic from it
        spares those symbols a second call."""
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: _Resp(
            {"data": {"ebit": 8.12e9, "ebitda": 1.55e10, "roic": 0.06}}))
        out = uds.fetch_vietcap_operating_lines("TST")
        assert out["roic"] == pytest.approx(6.0)
        assert out["ebit"] == pytest.approx(8.12e9)
