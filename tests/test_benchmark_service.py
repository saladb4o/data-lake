"""
Tests for services/benchmark_service.py.

Zero network: the TradingView subprocess helper (_tv_fetch_candles) and the
vnstock chain (_fetch_from_source) are both monkeypatched. Failure paths must
return a clean error dict, never raise.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

import services.benchmark_service as bs


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_cache():
    """Keep every test isolated from the module-level TTL cache."""
    bs._cache._store.clear()
    yield
    bs._cache._store.clear()


def tv_style_candles(n=30, base=1000.0):
    d = date(2024, 1, 2)
    price = base
    out = []
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        price *= 1.003
        out.append(
            {
                "time": d.isoformat(),
                "open": round(price * 0.995, 2),
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "close": round(price, 2),
                "volume": 1000 + i,
            }
        )
        d += timedelta(days=1)
    return out


def fake_history_df(n=80, base=1200.0):
    d = date(2024, 1, 2)
    rows = []
    price = base
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        price *= 1.001
        rows.append(
            {
                "time": d.isoformat(),
                "open": round(price * 0.998, 2),
                "high": round(price * 1.005, 2),
                "low": round(price * 0.995, 2),
                "close": round(price, 2),
                "volume": 500 + i,
            }
        )
        d += timedelta(days=1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# TradingView fast path
# ---------------------------------------------------------------------------

class TestTradingViewFastPath:
    def test_success_source_tradingview_schema(self, monkeypatch):
        canned = tv_style_candles(40)
        seen = {}

        def fake_tv(symbol, max_count=1200):
            seen["symbol"] = symbol
            return list(canned)

        monkeypatch.setattr(bs, "_tv_fetch_candles", fake_tv)

        res = bs.get_benchmark_history("VNINDEX", interval="1D", lookback_days=500)

        assert seen["symbol"] == "HOSE:VNINDEX"
        assert res["symbol"] == "VNINDEX"
        assert res["source"] == "tradingview"
        assert "error" not in res
        assert len(res["candles"]) == 40
        for c in res["candles"]:
            assert set(c.keys()) == {"time", "open", "high", "low", "close"}
            assert all(isinstance(v, float) for v in c.values() if isinstance(v, float))
        times = [c["time"] for c in res["candles"]]
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1))
        assert times == [v["time"] for v in res["volumes"]]
        for v in res["volumes"]:
            assert set(v.keys()) == {"time", "value"}

    def test_trim_to_lookback_days(self, monkeypatch):
        canned = tv_style_candles(100)
        monkeypatch.setattr(bs, "_tv_fetch_candles", lambda s, max_count=1200: list(canned))

        res = bs.get_benchmark_history("VN30", interval="1D", lookback_days=25)

        assert res["source"] == "tradingview"
        assert len(res["candles"]) == 25
        assert res["candles"][0]["time"] == canned[-25]["time"]
        assert res["candles"][-1]["time"] == canned[-1]["time"]

    def test_tv_only_used_for_daily_interval(self, monkeypatch):
        def fail(s, max_count=1200):
            raise AssertionError("TV fast path must not be used for non-1D intervals")

        monkeypatch.setattr(bs, "_tv_fetch_candles", fail)
        monkeypatch.setattr(bs, "_fetch_from_source", lambda src, sym, ivl, lb: fake_history_df())

        res = bs.get_benchmark_history("VNINDEX", interval="1W", lookback_days=500)

        assert res["source"] == "VCI"
        assert "error" not in res


# ---------------------------------------------------------------------------
# Fallback to vnstock chain
# ---------------------------------------------------------------------------

class TestVnstockFallback:
    def test_tv_failure_falls_back_to_vci(self, monkeypatch):
        def boom(symbol, max_count=1200):
            raise RuntimeError("node exploded")

        monkeypatch.setattr(bs, "_tv_fetch_candles", boom)
        calls = []

        def fake_fetch(source, symbol, interval, lookback_days):
            calls.append((source, symbol, interval))
            return fake_history_df()

        monkeypatch.setattr(bs, "_fetch_from_source", fake_fetch)

        res = bs.get_benchmark_history("VNINDEX", interval="1D", lookback_days=500)

        assert calls[0][0] == "VCI"
        assert res["source"] == "VCI"
        assert res["candles"]
        assert "error" not in res
        times = [c["time"] for c in res["candles"]]
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1))

    def test_all_sources_fail_returns_clean_error_dict(self, monkeypatch):
        monkeypatch.setattr(bs, "_tv_fetch_candles", lambda s, max_count=1200: None)
        monkeypatch.setattr(bs, "_fetch_from_source", lambda src, sym, ivl, lb: None)

        res = bs.get_benchmark_history("HNXINDEX", interval="1D", lookback_days=500)

        assert res["candles"] == []
        assert res["volumes"] == []
        assert "error" in res
        assert "HNXINDEX" in res["error"]

    def test_raising_sources_never_raise_out(self, monkeypatch):
        monkeypatch.setattr(bs, "_tv_fetch_candles", lambda s, max_count=1200: None)

        def explode(*a, **k):
            raise ConnectionError("dns dead")

        monkeypatch.setattr(bs, "_fetch_from_source", explode)

        res = bs.get_benchmark_history("UPCOM", interval="1D", lookback_days=200)

        assert isinstance(res, dict)
        assert res["candles"] == []
        assert "error" in res


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestValidation:
    @pytest.mark.parametrize("bad_symbol", ["", "   ", "NOTREAL", "fpt"])
    def test_unsupported_symbol_error(self, bad_symbol, monkeypatch):
        monkeypatch.setattr(bs, "_tv_fetch_candles", lambda s, max_count=1200: None)
        res = bs.get_benchmark_history(bad_symbol)
        assert "error" in res
        assert res["candles"] == []
        assert res.get("source", "") == "" or res["source"] == ""

    def test_error_lists_supported_symbols(self):
        res = bs.get_benchmark_history("BOGUS")
        for sym in bs.SUPPORTED_BENCHMARKS:
            assert sym in res["error"]

    @pytest.mark.parametrize("bad_interval", ["2H", "weekly", "", "5m"])
    def test_unsupported_interval_error(self, bad_interval):
        res = bs.get_benchmark_history("VNINDEX", interval=bad_interval)
        assert "error" in res
        assert "interval" in res["error"].lower()

    @pytest.mark.parametrize("bad_lookback", [0, -5, "abc", None])
    def test_invalid_lookback_error(self, bad_lookback, monkeypatch):
        monkeypatch.setattr(bs, "_tv_fetch_candles",
                            lambda s, max_count=1200: (_ for _ in ()).throw(AssertionError("no TV call")))
        res = bs.get_benchmark_history("VNINDEX", interval="1D", lookback_days=bad_lookback)
        assert "error" in res

    def test_lowercase_symbol_and_interval_accepted(self, monkeypatch):
        canned = tv_style_candles(15)
        monkeypatch.setattr(bs, "_tv_fetch_candles", lambda s, max_count=1200: list(canned))

        res = bs.get_benchmark_history("vnindex", interval="1d")

        assert res["symbol"] == "VNINDEX"
        assert res["source"] == "tradingview"

    def test_result_is_cached(self, monkeypatch):
        calls = []

        def fake(symbol, max_count=1200):
            calls.append(symbol)
            return tv_style_candles(15)

        monkeypatch.setattr(bs, "_tv_fetch_candles", fake)
        a = bs.get_benchmark_history("VNINDEX", interval="1D", lookback_days=10)
        b = bs.get_benchmark_history("VNINDEX", interval="1D", lookback_days=10)
        assert a is b
        assert len(calls) == 1
