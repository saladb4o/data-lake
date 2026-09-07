"""The Vietcap insight route, which carries the one field 565 symbols lack.

Every cheaper source is measured and closed: the two listing payloads that
build the universe hold no share count, VNDIRECT reports none, and all four
TCBS routes return 404. This route is what the vnstock package itself reads
for company details.

None of these tests assert that the URL is correct - that cannot be checked
from a sandbox with no egress to it. They pin the parsing, the unit
discriminant, and the wiring, so that when the run does reach it, a wrong
answer is distinguishable from a wrong hookup.
"""
import pytest

from services import unified_data_service as uds
from services.unified_data_service import (
    _vietcap_record,
    _first_alias,
    _VIETCAP_SHARE_ALIASES,
    fetch_vietcap_company_details,
    normalize_stock_data,
)


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        if self._payload is _MALFORMED:
            raise ValueError("not json")
        return self._payload


_MALFORMED = object()


class TestEnvelope:
    def test_the_document_is_unwrapped_from_data(self):
        assert _vietcap_record({"data": {"ticker": "FPT"}}) == {"ticker": "FPT"}

    def test_a_list_under_data_yields_its_first_real_row(self):
        assert _vietcap_record({"data": [{}, {"ticker": "FPT"}]}) == {"ticker": "FPT"}

    def test_a_bare_document_is_taken_as_is(self):
        assert _vietcap_record({"ticker": "FPT"}) == {"ticker": "FPT"}

    def test_a_null_data_key_falls_back_to_the_outer_document(self):
        # An envelope whose data is null still carries the outer fields; the
        # alternative is discarding a payload we could read.
        assert _vietcap_record({"data": None, "ticker": "FPT"})["ticker"] == "FPT"

    @pytest.mark.parametrize("payload", [None, [], {}, "text", 7])
    def test_nothing_usable_yields_an_empty_document(self, payload):
        assert _vietcap_record(payload) == {}


class TestAliases:
    def test_the_vnstock_field_name_is_recognised(self):
        rec = {"numberOfSharesMktCap": 1234.0}
        assert _first_alias(rec, _VIETCAP_SHARE_ALIASES) == 1234.0

    def test_the_snake_case_rename_is_recognised(self):
        rec = {"number_of_shares_mkt_cap": 1234.0}
        assert _first_alias(rec, _VIETCAP_SHARE_ALIASES) == 1234.0

    def test_an_unknown_name_is_not_guessed_at(self):
        assert _first_alias({"sharesTotal": 5.0}, _VIETCAP_SHARE_ALIASES) is None

    def test_the_earliest_alias_wins_when_several_are_present(self):
        rec = {"issueShare": 2.0, "numberOfSharesMktCap": 1.0}
        assert _first_alias(rec, _VIETCAP_SHARE_ALIASES) == 1.0


class TestUnits:
    """vnstock labels this column "(mil)" but the payload is not guaranteed
    to honour that, so the unit is read from the magnitude."""

    def test_a_count_in_millions_is_scaled_to_whole_shares(self):
        out = _fetch(uds, {"data": {"numberOfSharesMktCap": 1471.0}})
        assert out["shares_outstanding"] == pytest.approx(1_471_000_000.0)

    def test_a_count_already_in_whole_shares_is_left_alone(self):
        out = _fetch(uds, {"data": {"numberOfSharesMktCap": 1_471_000_000.0}})
        assert out["shares_outstanding"] == pytest.approx(1_471_000_000.0)

    def test_a_value_between_the_two_ranges_is_discarded_not_guessed(self):
        # 60,000 is too many to be millions and too few to be a real count.
        # Guessing either way invents a market cap; refusing does not.
        out = _fetch(uds, {"data": {"numberOfSharesMktCap": 60_000.0}})
        assert out == {}

    @pytest.mark.parametrize("bad", [0, -5, None, "n/a"])
    def test_a_nonsense_count_is_not_carried(self, bad):
        out = _fetch(uds, {"data": {"numberOfSharesMktCap": bad}})
        assert out.get("shares_outstanding") is None


class TestFailureSemantics:
    def test_no_response_yields_an_empty_dict_and_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(uds, "_request_with_retry", lambda *a, **k: None)
        assert fetch_vietcap_company_details("FPT") == {}

    def test_malformed_json_yields_an_empty_dict(self, monkeypatch):
        monkeypatch.setattr(
            uds, "_request_with_retry", lambda *a, **k: _Resp(_MALFORMED)
        )
        assert fetch_vietcap_company_details("FPT") == {}

    def test_a_payload_with_neither_field_is_not_stored(self):
        assert _fetch(uds, {"data": {"ticker": "FPT", "sector": "IT"}}) == {}

    def test_a_market_cap_alone_is_still_worth_carrying(self):
        # Market cap over price pins the count just as well.
        out = _fetch(uds, {"data": {"marketCap": 1.2e14}})
        assert out["market_cap"] == 1.2e14
        assert out["shares_outstanding"] is None


class TestItReachesTheValuation:
    """The wiring, which is where the last five defects of this shape lived:
    a source fetched, tiered and reachable, connected to a branch its users
    never take."""

    _TV = {"close": 20_000.0, "total_equity_fq": 4.0e11, "net_income_ttm": 5.0e10}

    def test_a_vietcap_share_count_is_used_and_tiered_as_reported(self):
        rec = normalize_stock_data(
            "TST", tv_data=dict(self._TV),
            vnstock_data={"shares_outstanding": 1_471_000_000.0, "market_cap": None},
        )
        assert rec["shares_out"] == pytest.approx(1_471_000_000.0)
        assert rec["field_provenance"]["shares"] == 3

    def test_without_it_the_same_row_is_refused(self):
        # The control. Same TradingView row, no vendor payload: the count is
        # the 50,000,000 fallback at tier 0 and the valuation is refused.
        rec = normalize_stock_data("TST", tv_data=dict(self._TV))
        assert rec["field_provenance"]["shares"] == 0


def _fetch(module, payload):
    """Runs fetch_vietcap_company_details against a canned payload."""
    import unittest.mock as mock

    with mock.patch.object(module, "_request_with_retry", return_value=_Resp(payload)):
        return module.fetch_vietcap_company_details("FPT")


class TestHtmlReconnaissance:
    """The Cophieu68 / Vietstock probe. It parses nothing on purpose: both
    sites serve HTML whose shape has not been seen, and writing a parser
    against a guessed structure is exactly how the dead TCBS route survived
    in this file for the life of the project."""

    def test_it_reports_a_label_and_the_text_around_it(self, capsys, monkeypatch):
        html = (
            "<table><tr><td>KLCP đang lưu hành</td>"
            "<td class='v'>1,471,000,000</td></tr></table>"
        )
        monkeypatch.setattr(
            uds._HTTP_SESSION, "get",
            lambda *a, **k: _Resp2(html, {"Content-Type": "text/html; charset=utf-8"}),
        )
        uds.probe_html_share_sources("FPT")
        out = capsys.readouterr().out
        assert "klcp đang lưu hành" in out
        assert "1,471,000,000" in out
        # The tags are stripped so the number is legible in a CI log.
        assert "<td" not in out

    def test_a_page_without_the_label_says_so_rather_than_staying_silent(
        self, capsys, monkeypatch
    ):
        # A client-rendered page matches nothing, and that is the finding:
        # it means the figure sits behind an XHR still to be found.
        monkeypatch.setattr(
            uds._HTTP_SESSION, "get",
            lambda *a, **k: _Resp2("<div id='app'></div>", {"Content-Type": "text/html"}),
        )
        uds.probe_html_share_sources("FPT")
        assert "no share-count label" in capsys.readouterr().out

    def test_a_dead_host_is_named_not_swallowed(self, capsys, monkeypatch):
        def _boom(*a, **k):
            raise ConnectionError("nope")

        monkeypatch.setattr(uds._HTTP_SESSION, "get", _boom)
        uds.probe_html_share_sources("FPT")
        out = capsys.readouterr().out
        assert "ConnectionError" in out
        # One line per candidate, so a wholly dead list cannot look like one
        # dead entry.
        assert out.count("ConnectionError") == len(uds._HTML_SHARE_SOURCES)

    def test_an_http_error_skips_the_body_scan(self, capsys, monkeypatch):
        monkeypatch.setattr(
            uds._HTTP_SESSION, "get",
            lambda *a, **k: _Resp2("KLCP đang lưu hành", {"Content-Type": "text/html"}, 404),
        )
        uds.probe_html_share_sources("FPT")
        out = capsys.readouterr().out
        assert "HTTP 404" in out
        assert "matched" not in out

    def test_it_returns_nothing_and_never_raises(self, monkeypatch):
        # Reconnaissance only. If this ever starts returning data, it has
        # become a source and needs the provenance tiering that goes with one.
        monkeypatch.setattr(
            uds._HTTP_SESSION, "get",
            lambda *a, **k: _Resp2("x", {"Content-Type": "text/html"}),
        )
        assert uds.probe_html_share_sources("FPT") is None


class _Resp2:
    def __init__(self, text, headers, status=200):
        self.text = text
        self.headers = headers
        self.status_code = status
