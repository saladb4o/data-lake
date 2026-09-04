"""
Tests for the three data-source fetchers in services/unified_data_service.py
(TradingView batch scanner, vnstock/TCBS ratios, yfinance fallback).

All HTTP traffic is faked via monkeypatching the module-level shared session;
no network access is performed.
"""

import logging

import pytest
import requests

import services.unified_data_service as uds


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, json_data=None, json_exc=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_data


class FakeSession:
    """Replaces uds._HTTP_SESSION. Outcomes are consumed in order; the last
    outcome is reused once the list is exhausted."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        idx = min(len(self.calls) - 1, len(self.outcomes) - 1)
        outcome = self.outcomes[idx]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def no_backoff(monkeypatch):
    """Disable real sleeping and random jitter during retry tests."""
    slept = []
    monkeypatch.setattr(uds.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(uds.random, "uniform", lambda a, b: 0.0)
    return slept


def install_session(monkeypatch, *outcomes):
    fake = FakeSession(list(outcomes))
    monkeypatch.setattr(uds, "_HTTP_SESSION", fake)
    return fake


# ---------------------------------------------------------------------------
# TradingView batch fetcher
# ---------------------------------------------------------------------------

def _tv_payload():
    columns = list(uds.TRADINGVIEW_COLUMNS)
    values = [None] * len(columns)
    values[columns.index("close")] = 125000.0
    values[columns.index("price_earnings_ttm")] = 12.5
    return {"data": [{"s": "HOSE:fpt", "d": values}]}


def test_tradingview_success_maps_columns_and_uppercases(monkeypatch):
    fake = install_session(monkeypatch, FakeResponse(200, _tv_payload()))

    result = uds.fetch_tradingview_batch_by_tickers(["HOSE:FPT"], chunk_size=150)

    assert "FPT" in result
    row = result["FPT"]
    assert row["symbol"] == "FPT"
    assert row["exchange"] == "HOSE"
    assert row["close"] == 125000.0
    assert row["price_earnings_ttm"] == 12.5
    assert fake.calls[0]["method"] == "POST"
    # Session headers must be used (no per-call header dict anymore).
    sent_payload = fake.calls[0]["kwargs"]["json"]
    assert sent_payload["symbols"]["tickers"] == ["HOSE:FPT"]
    assert sent_payload["columns"] == uds.TRADINGVIEW_COLUMNS


def test_tradingview_empty_input_short_circuits(monkeypatch):
    fake = install_session(monkeypatch, FakeResponse(200, {"data": []}))
    assert uds.fetch_tradingview_batch_by_tickers([]) == {}
    assert fake.calls == []


def test_tradingview_retry_then_success(monkeypatch, no_backoff):
    fake = install_session(
        monkeypatch,
        requests.ConnectionError("boom"),
        requests.Timeout("slow"),
        FakeResponse(200, _tv_payload()),
    )

    result = uds.fetch_tradingview_batch_by_tickers(["HOSE:FPT"])

    assert len(fake.calls) == 3
    assert "FPT" in result
    assert len(no_backoff) == 2  # backed off between attempts


def test_tradingview_exhausted_retries_returns_empty_and_logs(monkeypatch, no_backoff, caplog):
    install_session(monkeypatch, requests.ConnectionError("down"))

    with caplog.at_level(logging.WARNING, logger=uds.logger.name):
        result = uds.fetch_tradingview_batch_by_tickers(["HOSE:FPT"], chunk_size=150)

    assert result == {}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("TradingView" in r.getMessage() for r in warnings)
    assert any("%d tickers" in r.getMessage() or "tickers" in r.getMessage() for r in warnings)


def test_tradingview_malformed_json_handled(monkeypatch, caplog):
    install_session(monkeypatch, FakeResponse(200, json_exc=ValueError("<html> not json")))

    with caplog.at_level(logging.WARNING, logger=uds.logger.name):
        result = uds.fetch_tradingview_batch_by_tickers(["HOSE:FPT"])

    assert result == {}
    assert any("malformed JSON" in r.getMessage() for r in caplog.records)


def test_tradingview_wrong_shape_handled(monkeypatch, caplog):
    install_session(monkeypatch, FakeResponse(200, {"unexpected": True}))

    with caplog.at_level(logging.WARNING, logger=uds.logger.name):
        result = uds.fetch_tradingview_batch_by_tickers(["HOSE:FPT"])

    assert result == {}
    assert any("shape" in r.getMessage() for r in caplog.records)


def test_tradingview_http_500_retries_then_gives_up(monkeypatch, no_backoff):
    fake = install_session(monkeypatch, FakeResponse(500), FakeResponse(500), FakeResponse(500))

    result = uds.fetch_tradingview_batch_by_tickers(["HOSE:FPT"])

    assert result == {}
    assert len(fake.calls) == 3


def test_tradingview_non_retryable_404_no_retry(monkeypatch):
    fake = install_session(monkeypatch, FakeResponse(404))

    result = uds.fetch_tradingview_batch_by_tickers(["HOSE:FPT"])

    assert result == {}
    assert len(fake.calls) == 1


def test_tradingview_skips_malformed_items_but_keeps_good_ones(monkeypatch):
    payload = {
        "data": [
            {"s": "", "d": [1]},
            {"s": "HOSE:VCB", "d": []},
            {"not_a_dict": True},
            {"s": "HNX:pvs", "d": [None] * len(uds.TRADINGVIEW_COLUMNS)},
        ]
    }
    install_session(monkeypatch, FakeResponse(200, payload))

    result = uds.fetch_tradingview_batch_by_tickers(["HOSE:VCB", "HNX:PVS"])

    assert set(result.keys()) == {"PVS"}
    assert result["PVS"]["exchange"] == "HNX"


# ---------------------------------------------------------------------------
# vnstock / TCBS fetcher
# ---------------------------------------------------------------------------

TCBS_PAYLOAD = {
    "pe": 15.2, "pb": 2.1, "roe": 18.4, "roa": 8.1,
    "eps": 5250.0, "marketCap": 61300000000000,
}


def test_vnstock_success_extracts_metrics(monkeypatch):
    fake = install_session(monkeypatch, FakeResponse(200, TCBS_PAYLOAD))

    result = uds.fetch_vnstock_financials("fpt")

    assert result == {
        "pe": 15.2,
        "pb": 2.1,
        "roe": 18.4,
        "roa": 8.1,
        "eps": 5250.0,
        "market_cap": 61300000000000,
    }
    assert fake.calls[0]["url"].endswith("/finance/FPT/overview")


def test_vnstock_non_200_returns_empty(monkeypatch, no_backoff, caplog):
    install_session(monkeypatch, FakeResponse(503), FakeResponse(503), FakeResponse(503))

    with caplog.at_level(logging.WARNING, logger=uds.logger.name):
        result = uds.fetch_vnstock_financials("FPT")

    assert result == {}
    assert any("vnstock/TCBS" in r.getMessage() for r in caplog.records)


def test_vnstock_exhausted_connection_errors_returns_empty_and_logs(monkeypatch, no_backoff, caplog):
    install_session(monkeypatch, requests.ConnectionError("dns fail"))

    with caplog.at_level(logging.WARNING, logger=uds.logger.name):
        result = uds.fetch_vnstock_financials("FPT")

    assert result == {}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("FPT" in r.getMessage() for r in warnings)


def test_vnstock_malformed_json_returns_empty(monkeypatch):
    install_session(monkeypatch, FakeResponse(200, json_exc=ValueError("bad")))

    assert uds.fetch_vnstock_financials("FPT") == {}


def test_vnstock_wrong_type_payload_returns_empty(monkeypatch):
    install_session(monkeypatch, FakeResponse(200, ["unexpected", "list"]))

    assert uds.fetch_vnstock_financials("FPT") == {}


# ---------------------------------------------------------------------------
# yfinance fallback fetcher
# ---------------------------------------------------------------------------

def _yf_payload(price=58700.0):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price}}]}}


def test_yfinance_valid_meta_extracts_price(monkeypatch):
    fake = install_session(monkeypatch, FakeResponse(200, _yf_payload(58700.0)))

    result = uds.fetch_yfinance_financials("fpt")

    assert result == {"price": 58700.0}
    assert ".VN" in fake.calls[0]["url"]


def test_yfinance_empty_chart_result_returns_empty(monkeypatch, caplog):
    install_session(monkeypatch, FakeResponse(200, {"chart": {"result": []}}))

    with caplog.at_level(logging.WARNING, logger=uds.logger.name):
        result = uds.fetch_yfinance_financials("FPT")

    assert result == {}
    assert any("empty chart" in r.getMessage() for r in caplog.records)


def test_yfinance_missing_chart_key_returns_empty(monkeypatch):
    install_session(monkeypatch, FakeResponse(200, {}))

    assert uds.fetch_yfinance_financials("FPT") == {}


def test_yfinance_non_200_returns_empty(monkeypatch, no_backoff):
    install_session(monkeypatch, FakeResponse(429), FakeResponse(429), FakeResponse(429))

    assert uds.fetch_yfinance_financials("FPT") == {}


def test_yfinance_retry_then_success(monkeypatch, no_backoff):
    fake = install_session(
        monkeypatch,
        requests.Timeout("t/o"),
        FakeResponse(200, _yf_payload(12345.0)),
    )

    result = uds.fetch_yfinance_financials("FPT")

    assert result == {"price": 12345.0}
    assert len(fake.calls) == 2


def test_yfinance_meta_without_price_returns_empty(monkeypatch):
    install_session(monkeypatch, FakeResponse(200, {"chart": {"result": [{"meta": {}}]}}))

    assert uds.fetch_yfinance_financials("FPT") == {}


# ---------------------------------------------------------------------------
# Shared retry helper semantics
# ---------------------------------------------------------------------------

def test_retry_helper_returns_response_on_success(monkeypatch, no_backoff):
    install_session(monkeypatch, FakeResponse(200, {"ok": 1}))

    resp = uds._request_with_retry("GET", "https://example.test/x")

    assert resp is not None
    assert resp.status_code == 200


def test_retry_helper_never_raises_on_request_exception(monkeypatch, no_backoff):
    install_session(monkeypatch, requests.RequestException("generic"))

    resp = uds._request_with_retry("GET", "https://example.test/x")

    assert resp is None
