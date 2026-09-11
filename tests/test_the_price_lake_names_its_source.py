"""Prices come from a source that is tried, not from a source that is claimed.

The price stage advertised TradingView in two places - the module header
and the `source` field of the saved lake - while fetching from yfinance
with a vnstock fallback and never contacting TradingView at all. A label
nobody can check was read as evidence that TradingView already carried
the lake.

It is now DNSE, then SSI, then TCBS, then yfinance, then vnstock, and
the lake records which one answered for each symbol. These tests pin the parsers'
refusals and the ordering; whether the endpoints answer at all is a
question only a runner can settle, and the tally exists to settle it.
"""
from __future__ import annotations

import inspect

import pytest

from services.broker_prices import (
    TCBS_MAX_POINTS, fetch_dnse, fetch_ssi, fetch_tcbs, parse_tcbs_bars,
    parse_udf)


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


class TestTheTcbsParser:
    def test_rows_come_back_dated_by_trading_day(self):
        rows = parse_tcbs_bars({"data": [
            {"tradingDate": "2024-03-28T00:00:00.000Z", "open": 1.0,
             "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10},
        ]})
        assert rows == [{"time": "2024-03-28", "open": 1.0, "high": 2.0,
                         "low": 0.5, "close": 1.5, "volume": 10.0}]

    def test_a_row_missing_a_price_is_dropped_not_defaulted(self):
        # A bar with no close is not a bar. Defaulting it to zero would
        # put a 100% loss into a quarter that merely had a gap.
        assert parse_tcbs_bars({"data": [
            {"tradingDate": "2024-03-28T00:00:00Z", "open": 1.0,
             "high": 2.0, "low": 0.5, "volume": 10}]}) is None

    def test_an_empty_payload_is_none(self):
        assert parse_tcbs_bars({"data": []}) is None
        assert parse_tcbs_bars({}) is None


class TestTheFetchersKeepTheirPromises:
    def test_dnse_asks_once_at_the_daily_resolution(self, monkeypatch):
        asked = []

        def _get(url, params=None, **kwargs):
            asked.append((url, params))
            return _Resp({"s": "ok", "t": [1451606400], "o": [1.0],
                          "h": [1.0], "l": [1.0], "c": [1.0], "v": [1]})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        assert fetch_dnse("FPT")
        assert len(asked) == 1
        # The 90-day ceiling DNSE documents belongs to the intraday
        # resolutions. Asking for one of those here would inherit a limit
        # that does not apply to daily bars and silently truncate the lake
        # to one quarter.
        assert asked[0][1]["resolution"] == "1D"
        assert "entrade" in asked[0][0]

    def test_dnse_and_ssi_share_one_parser(self):
        # Both answer in UDF shape, so a refusal rule fixed in one is
        # fixed in both. A second parser would be a second place for the
        # unequal-column bug to come back.
        import services.broker_prices as bp
        assert "parse_udf" in inspect.getsource(bp.fetch_dnse)
        assert "parse_udf" in inspect.getsource(bp.fetch_ssi)

    def test_ssi_asks_once_for_the_whole_window(self, monkeypatch):
        asked = []

        def _get(url, params=None, **kwargs):
            asked.append((url, params))
            return _Resp({"s": "ok", "t": [1451606400], "o": [1.0],
                          "h": [1.0], "l": [1.0], "c": [1.0], "v": [1]})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        assert fetch_ssi("FPT")
        assert len(asked) == 1
        assert asked[0][1]["symbol"] == "FPT"
        assert asked[0][1]["resolution"] == "1D"

    def test_tcbs_chunks_and_never_asks_for_more_than_it_can_get(
            self, monkeypatch):
        spans = []

        def _get(url, params=None, **kwargs):
            spans.append(params["countBack"])
            return _Resp({"data": []})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        fetch_tcbs("FPT", start="2016-01-01", end="2020-01-01")
        # A countBack above the cap is silently truncated by TCBS, which
        # would read as a symbol that stopped trading mid-history.
        assert spans and max(spans) <= TCBS_MAX_POINTS

    def test_a_late_listing_is_not_abandoned_at_its_first_empty_chunk(
            self, monkeypatch):
        # vietfin's own loop breaks on the first empty chunk. A company
        # that listed in 2019 has nothing in 2016, so that rule drops it
        # entirely rather than starting it late.
        calls = {"n": 0}

        def _get(url, params=None, **kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                return _Resp({"data": []})
            return _Resp({"data": [
                {"tradingDate": "2019-06-03T00:00:00Z", "open": 1.0,
                 "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}]})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        rows = fetch_tcbs("XYZ", start="2016-01-01", end="2020-01-01")
        assert rows and rows[0]["time"] == "2019-06-03"

    def test_overlapping_chunks_do_not_duplicate_a_trading_day(
            self, monkeypatch):
        def _get(url, params=None, **kwargs):
            return _Resp({"data": [
                {"tradingDate": "2019-06-03T00:00:00Z", "open": 1.0,
                 "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}]})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        rows = fetch_tcbs("XYZ", start="2016-01-01", end="2020-01-01")
        assert [r["time"] for r in rows] == ["2019-06-03"]

    def test_verification_is_never_switched_off(self, monkeypatch):
        seen = {}

        def _get(url, params=None, **kwargs):
            seen.update(kwargs)
            return _Resp({"s": "no_data"})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        fetch_ssi("FPT")
        # scripts/fetch_tradingview.js opens with
        # NODE_TLS_REJECT_UNAUTHORIZED = '0'. Not inheriting that was the
        # whole reason for going to the brokers over HTTPS directly.
        assert seen.get("verify") is not False


class TestTheLakeRecordsWhoAnswered:
    def _body(self):
        import scripts.sync_historical_prices as sync
        return inspect.getsource(sync.sync_all_symbols)

    def test_the_saved_source_is_a_tally_not_a_slogan(self):
        body = self._body()
        assert "TradingView & Yahoo Finance Live Data Feeds" not in body
        assert "by_source" in body

    def test_the_brokers_are_tried_before_yfinance_and_vnstock(self):
        body = self._body()
        assert body.index("_fetch_from_broker") < body.index("yf.download")

    def test_a_dead_endpoint_is_dropped_rather_than_asked_1500_times(self):
        import scripts.sync_historical_prices as sync
        assert sync.PROBE_BEFORE_GIVING_UP > 0
        assert "PROBE_BEFORE_GIVING_UP" in self._body()

    def test_the_cheap_sources_are_asked_before_the_expensive_one(self):
        # TCBS costs ten requests per symbol against one for the others,
        # and is reported to have closed its unauthenticated endpoints.
        # Either reason alone puts it last.
        import scripts.sync_historical_prices as sync
        assert sync.BROKER_SOURCES == ("dnse", "ssi", "tcbs")

    def test_every_named_source_can_actually_be_dispatched(self):
        # A name in BROKER_SOURCES with no fetcher behind it would raise
        # KeyError once per symbol and be swallowed as a failed fetch -
        # the source would report zero and look dead rather than absent.
        import scripts.sync_historical_prices as sync
        for source in sync.BROKER_SOURCES:
            assert sync._fetch_from_broker.__module__
            import services.broker_prices as bp
            assert hasattr(bp, f"fetch_{source}")
