"""
Tests for services/sector_index_service.py.

No network: the TradingView subprocess helper (_tv_fetch_candles) and the
vnstock Quote dependency are both monkeypatched; the cap-weighted fallback
path reads small JSON fixtures written into tmp_path (the service module's
_DATA_DIR is pointed there).
"""

import subprocess
from datetime import date, timedelta

import pytest

import services.sector_index_service as sis


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def tv_style_candles(n=40, start=None, base=1000.0):
    d = start or date(2024, 1, 1)
    price = base
    out = []
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        price *= 1.002
        o = round(price * 0.995, 2)
        h = round(price * 1.008, 2)
        lo = round(price * 0.99, 2)
        c = round(price, 2)
        out.append(
            {"time": d.isoformat(), "open": o, "high": h, "low": lo, "close": c, "volume": 100000 + i}
        )
        d += timedelta(days=1)
    return out


def quarters_for(symbol, closes):
    qkeys = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
    end_dates = ["2024-03-29", "2024-06-28", "2024-09-27", "2024-12-27"]
    quarters = {}
    for i, qk in enumerate(qkeys[: len(closes)]):
        c = float(closes[i])
        quarters[qk] = {
            "end_date": end_dates[i],
            "start_price": round(c * 0.98, 2),
            "high": round(c * 1.05, 2),
            "low": round(c * 0.95, 2),
            "close_price": c,
            "volume": 500000 * (i + 1),
        }
    return {symbol: {"quarters": quarters}}


@pytest.fixture
def lake(tmp_path, monkeypatch):
    """Small on-disk data lake + fully offline service module state."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    industries = [
        {"symbol": "AAA", "icb_level": 2, "icb_code": "8600", "icb_name": "Bất Động Sản", "com_type_code": ""}, 
        {"symbol": "BBB", "icb_level": 2, "icb_code": "8600", "icb_name": "Bất Động Sản Hạ Tầng", "com_type_code": ""},
        {"symbol": "FIN1", "icb_level": 2, "icb_code": "8300", "icb_name": "Ngân hàng", "com_type_code": ""},
        {"symbol": "FIN2", "icb_level": 2, "icb_code": "8700", "icb_name": "Dịch vụ tài chính", "com_type_code": ""},
        {"symbol": "QU1", "icb_level": 2, "icb_code": "8300", "icb_name": "Ngân hàng", "com_type_code": "QU"},
        {"symbol": "LVL1", "icb_level": 1, "icb_code": "8000", "icb_name": "Tài chính", "com_type_code": ""},
    ]

    caps = {"AAA": 200000.0, "BBB": 100000.0, "FIN1": 300000.0, "FIN2": 150000.0}
    screener = {
        "stocks": {
            sym: {
                "market_cap": cap,
                "pe": 12.5,
                "pb": 1.6,
                "roe": 15.0,
                "change_pct": 1.2,
                "sector_code": "VNTST",
            }
            for sym, cap in caps.items()
        }
    }

    historical = {
        "symbols": {
            **quarters_for("AAA", [20.0, 21.0, 22.5, 24.0]),
            **quarters_for("BBB", [50.0, 52.0, 49.0, 55.0]),
            **quarters_for("FIN1", [30.0, 31.5, 33.0, 34.0]),
            **quarters_for("FIN2", [15.0, 14.0, 16.0, 17.0]),
        }
    }

    import json

    (data_dir / "industries.json").write_text(json.dumps(industries), encoding="utf-8")
    (data_dir / "screener_snapshot.json").write_text(json.dumps(screener), encoding="utf-8")
    (data_dir / "historical_prices.json").write_text(json.dumps(historical), encoding="utf-8")

    monkeypatch.setattr(sis, "_DATA_DIR", str(data_dir))
    monkeypatch.setattr(sis, "Quote", None)
    monkeypatch.setattr(sis, "_vnstock_ok", False)
    sis._file_cache.clear()
    sis._cache._store.clear()
    yield data_dir
    sis._file_cache.clear()
    sis._cache._store.clear()


# ---------------------------------------------------------------------------
# TradingView fast path (success)
# ---------------------------------------------------------------------------

class TestTradingViewFastPath:
    def test_success_schema_and_source(self, lake, monkeypatch):
        canned = tv_style_candles(40)
        monkeypatch.setattr(sis, "_tv_fetch_candles", lambda symbol, max_count=1200: list(canned))

        res = sis.build_sector_index("VNREAL", interval="1D", lookback_days=500)

        assert res["source"] == "tradingview"
        assert res["coverage"] == 1.0
        assert isinstance(res["coverage"], float)
        assert 0.0 <= res["coverage"] <= 1.0
        assert isinstance(res["base_point"], float) and res["base_point"] > 0
        assert res["sector_code"] == "VNREAL"

        assert len(res["candles"]) == 40
        for c in res["candles"]:
            assert set(c.keys()) == {"time", "open", "high", "low", "close"}
            assert all(isinstance(v, float) and v > 0 for k, v in c.items() if k != "time")
        for v in res["volumes"]:
            assert set(v.keys()) == {"time", "value"}
            assert isinstance(v["value"], int)

        times = [c["time"] for c in res["candles"]]
        assert all(len(t) == 10 for t in times)
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1))
        assert times == [v["time"] for v in res["volumes"]]

    def test_trimmed_to_lookback(self, lake, monkeypatch):
        canned = tv_style_candles(120)
        monkeypatch.setattr(sis, "_tv_fetch_candles", lambda symbol, max_count=1200: list(canned))

        res = sis.build_sector_index("VNFIN", interval="1D", lookback_days=50)
        assert res["source"] == "tradingview"
        assert len(res["candles"]) == 50
        assert res["candles"][0]["time"] == canned[-50]["time"]
        assert res["candles"][-1]["time"] == canned[-1]["time"]

    def test_resample_weekly_buckets(self, lake, monkeypatch):
        from datetime import datetime

        canned = tv_style_candles(40)
        monkeypatch.setattr(sis, "_tv_fetch_candles", lambda symbol, max_count=1200: list(canned))

        res = sis.build_sector_index("VNREAL", interval="1W", lookback_days=500)

        assert res["source"] == "tradingview"
        times = [c["time"] for c in res["candles"]]
        assert len(set(times)) == len(times)
        assert len(times) < 40
        for t in times:
            dt = datetime.strptime(t, "%Y-%m-%d")
            assert dt.weekday() == 0
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1))
        total_vol_daily = sum(c["volume"] for c in canned)
        total_vol_weekly = sum(v["value"] for v in res["volumes"])
        assert total_vol_weekly == total_vol_daily


# ---------------------------------------------------------------------------
# TradingView failure -> cap-weighted fallback from mocked lake data
# ---------------------------------------------------------------------------

class TestFallbackPath:
    def test_timeout_falls_back_to_quarterly_lake(self, lake, monkeypatch):
        def boom(symbol, max_count=1200):
            raise subprocess.TimeoutExpired(cmd=["node"], timeout=20)

        monkeypatch.setattr(sis, "_tv_fetch_candles", boom)

        res = sis.build_sector_index("VNFIN", interval="1D", lookback_days=500)

        assert res.get("source") != "tradingview"
        assert res["candles"], "fallback must produce candles from lake data"
        assert len(res["candles"]) == 4
        assert res["constituents_count"] >= 2
        assert isinstance(res["coverage"], float)
        assert 0.0 <= res["coverage"] <= 1.0
        assert res["base_point"] > 0

        times = [c["time"] for c in res["candles"]]
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1))
        for c in res["candles"]:
            assert set(c.keys()) == {"time", "open", "high", "low", "close"}

        vol_times = [v["time"] for v in res["volumes"]]
        assert vol_times == times

    def test_tv_none_falls_back_for_unmapped_sector(self, lake, monkeypatch):
        monkeypatch.setattr(sis, "_tv_fetch_candles", lambda s, max_count=1200: None)

        res = sis.build_sector_index("VNTST", interval="1D", lookback_days=500)

        assert res.get("source") != "tradingview"
        assert res["constituents_count"] >= 2
        assert res["coverage"] == pytest.approx(1.0)
        assert len(res["candles"]) == 4

    def test_result_is_cached_but_independent_keys(self, lake, monkeypatch):
        canned = tv_style_candles(30)
        calls = []

        def fake(symbol, max_count=1200):
            calls.append(symbol)
            return list(canned)

        monkeypatch.setattr(sis, "_tv_fetch_candles", fake)

        a = sis.build_sector_index("VNREAL", interval="1D", lookback_days=500)
        b = sis.build_sector_index("VNREAL", interval="1D", lookback_days=500)
        assert calls == ["HOSE:VNREAL"]
        assert a is b

        sis.build_sector_index("VNREAL", interval="1W", lookback_days=500)
        assert len(calls) == 2


# ---------------------------------------------------------------------------
# Constituents resolution
# ---------------------------------------------------------------------------

class TestGetSectorConstituents:
    def test_nonempty_from_industries_dataset(self, lake):
        syms = sis.get_sector_constituents("VNFIN")
        assert isinstance(syms, list)
        assert syms
        assert syms == sorted(syms)
        assert "FIN1" in syms and "FIN2" in syms
        assert "QU1" not in syms
        assert "LVL1" not in syms

    def test_screener_fallback_when_no_icb_match(self, lake):
        syms = sis.get_sector_constituents("VNTST")
        assert set(syms) == {"AAA", "BBB", "FIN1", "FIN2"}


# ---------------------------------------------------------------------------
# Snapshot smoke (fully offline)
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_snapshot_shape(self, lake, monkeypatch):
        monkeypatch.setattr(sis, "_tv_fetch_candles", lambda s, max_count=1200: None)
        snap = sis.get_sector_snapshot("VNFIN")
        assert snap["sector_code"] == "VNFIN"
        assert snap["constituents_count"] >= 2
        assert snap["latest"] > 0
        assert {"advancers", "decliners", "unchanged"} <= set(snap.keys())
