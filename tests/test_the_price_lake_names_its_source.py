"""Prices come from a source that is tried, not from a source that is claimed.

The price stage advertised TradingView in two places - the module header
and the `source` field of the saved lake - while fetching from yfinance
with a vnstock fallback and never contacting TradingView at all. A label
nobody can check was read as evidence that TradingView already carried
the lake.

It is now DNSE, then yfinance, then vnstock, and the lake records which
one answered for each symbol. SSI and TCBS were tried on a full pass,
answered for nobody, and were deleted rather than left flagged off.
These tests pin the parser's refusals and the ordering; whether the
endpoint answers at all is a question only a runner can settle, and the
tally exists to settle it.
"""
from __future__ import annotations

import inspect

import pytest

from services.broker_prices import fetch_dnse, parse_udf


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class TestTheUdfParserRefusesWhatItCannotTrust:
    def test_a_well_formed_payload_becomes_rows(self):
        rows = parse_udf({"s": "ok", "t": [1451606400, 1451692800],
                          "o": [1.0, 2.0], "h": [3.0, 4.0], "l": [0.5, 1.5],
                          "c": [2.5, 3.5], "v": [100, 200]})
        assert rows is not None and len(rows) == 2
        assert rows[0]["time"] == "2016-01-01"
        assert rows[1]["close"] == 3.5

    def test_a_short_column_is_refused_rather_than_zipped(self):
        # Truncated response. Zipping unequal arrays pairs one day's close
        # with another day's open - silently, across years of history.
        assert parse_udf({"s": "ok", "t": [1, 2, 3], "o": [1.0, 2.0, 3.0],
                          "h": [1.0, 2.0, 3.0], "l": [1.0, 2.0, 3.0],
                          "c": [1.0, 2.0], "v": [1, 2, 3]}) is None

    def test_no_data_is_none_not_an_empty_frame(self):
        assert parse_udf({"s": "no_data"}) is None
        assert parse_udf({"s": "ok", "t": []}) is None
        assert parse_udf("not a dict") is None


class TestTheFetcherKeepsItsPromises:
    def test_the_whole_window_is_asked_for_in_one_request(self, monkeypatch):
        asked = []

        def _get(url, params=None, **kwargs):
            asked.append(params)
            return _Resp({"s": "ok", "t": [1451606400], "o": [1.0],
                          "h": [1.0], "l": [1.0], "c": [1.0], "v": [1]})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        assert fetch_dnse("FPT")
        assert len(asked) == 1
        assert asked[0]["symbol"] == "FPT"
        # Not an intraday resolution: the 90-day ceiling vietfin documents
        # is a property of those, and asking for one would inherit a limit
        # that does not apply to daily bars.
        assert asked[0]["resolution"] == "1D"

    def test_a_symbol_with_nothing_is_none_not_an_empty_frame(
            self, monkeypatch):
        monkeypatch.setattr("services.broker_prices.requests.get",
                            lambda *a, **k: _Resp({"s": "no_data"}))
        # None, not [], so the caller can tell "this source has nothing"
        # from "this source returned no candles" and fall through.
        assert fetch_dnse("ZZZ") is None

    def test_a_non_200_falls_through_instead_of_raising(self, monkeypatch):
        monkeypatch.setattr("services.broker_prices.requests.get",
                            lambda *a, **k: _Resp({}, status=503))
        assert fetch_dnse("FPT") is None

    def test_verification_is_never_switched_off(self, monkeypatch):
        seen = {}

        def _get(url, params=None, **kwargs):
            seen.update(kwargs)
            return _Resp({"s": "no_data"})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        fetch_dnse("FPT")
        # scripts/fetch_tradingview.js opens with
        # NODE_TLS_REJECT_UNAUTHORIZED = '0'. Not inheriting that was the
        # whole reason for going to the broker over HTTPS directly.
        assert seen.get("verify") is not False


class TestTheLakeRecordsWhoAnswered:
    def _body(self):
        import scripts.sync_historical_prices as sync
        return inspect.getsource(sync.sync_all_symbols)

    def test_the_saved_source_is_a_tally_not_a_slogan(self):
        body = self._body()
        assert "TradingView & Yahoo Finance Live Data Feeds" not in body
        assert "by_source" in body

    def test_the_broker_is_tried_before_yfinance_and_vnstock(self):
        body = self._body()
        assert body.index("_fetch_from_broker") < body.index("yf.download")

    def test_a_source_measured_at_zero_is_gone_not_flagged_off(self):
        import services.broker_prices as bp
        import scripts.sync_historical_prices as sync
        # SSI and TCBS answered for nobody on a full pass. Code kept "in
        # case it works again" is code nobody measures again, and its
        # circuit breaker would spend eighty requests a pass re-deriving
        # a result already in the log.
        assert not hasattr(bp, "fetch_ssi")
        assert not hasattr(bp, "fetch_tcbs")
        assert sync.BROKER_SOURCES == ("dnse",)

    def test_the_tally_is_written_where_a_reader_can_reach_it(self):
        # The job log is not readable from where these results get read:
        # the artifact host is refused and the log API serves only the
        # tail. A table printed mid-stage is a table nobody sees.
        assert "price_sources.md" in self._body()

    def test_a_dead_endpoint_is_dropped_rather_than_asked_1500_times(self):
        import scripts.sync_historical_prices as sync
        assert sync.PROBE_BEFORE_GIVING_UP > 0
        assert "PROBE_BEFORE_GIVING_UP" in self._body()

    def test_every_named_source_can_actually_be_dispatched(self):
        # A name in BROKER_SOURCES with no fetcher behind it would raise
        # KeyError once per symbol and be swallowed as a failed fetch -
        # the source would report zero and look dead rather than absent.
        import scripts.sync_historical_prices as sync
        for source in sync.BROKER_SOURCES:
            assert sync._fetch_from_broker.__module__
            import services.broker_prices as bp
            assert hasattr(bp, f"fetch_{source}")
