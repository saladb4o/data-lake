"""
API contract tests for GET /api/sectors/rrg in server.py.

server.py is imported wholesale (verified safe offline: no network happens at
import time; the news poller thread is only started via the FastAPI startup
event, which a bare TestClient never triggers because we do not enter its
context manager). The handler lazy-imports build_sector_index /
get_benchmark_history / build_rrg_matrix from their source modules on every
request, so we monkeypatch them AT THE SOURCE MODULES and feed small
deterministic fixtures. services.stock_service's response cache is cleared
around each test so responses are always freshly computed.
"""

import re
from datetime import datetime

import pytest

try:
    import server  # noqa: F401
except Exception as exc:  # pragma: no cover - only if env is broken
    pytest.skip(f"cannot import server module safely: {exc}", allow_module_level=True)

from fastapi.testclient import TestClient

import services.benchmark_service as benchmark_service
import services.rrg_service as rrg_service
import services.sector_index_service as sector_index_service
import services.stock_service as stock_service


QUADRANTS = ("Leading", "Weakening", "Improving", "Lagging")
QUADRANT_SET = set(QUADRANTS)

RRG_URL = "/api/sectors/rrg"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with all three RRG dependencies patched at source modules."""
    stock_service.cache._store.clear()
    # Isolate the stale-while-revalidate disk cache so tests always exercise
    # the full compute path instead of serving a leftover real payload.
    import server as _server_mod
    _disk_tmp = str(tmp_path / "rrg_disk_cache.json")
    monkeypatch.setattr(_server_mod, "_rrg_disk_path", lambda: _disk_tmp, raising=False)

    bench_candles = [
        {"time": f"2024-01-{d:02d}", "open": 1000.0, "high": 1010.0, "low": 990.0, "close": 1000.0 + d}
        for d in range(1, 29)
    ]
    sector_candles = [
        {"time": c["time"], "open": 500.0, "high": 505.0, "low": 495.0, "close": 500.0 + d}
        for d, c in enumerate(bench_candles)
    ]

    monkeypatch.setattr(
        benchmark_service,
        "get_benchmark_history",
        lambda symbol, interval, lookback_days: {
            "symbol": symbol,
            "candles": [dict(c) for c in bench_candles],
            "volumes": [{"time": c["time"], "value": 1} for c in bench_candles],
            "source": "tradingview",
        },
    )
    monkeypatch.setattr(
        sector_index_service,
        "build_sector_index",
        lambda code, interval="1D", lookback_days=500: {
            "sector_code": code,
            "candles": [dict(c) for c in sector_candles],
            "volumes": [{"time": c["time"], "value": 1} for c in sector_candles],
            "coverage": 1.0,
            "constituents_count": 5,
            "base_point": 1000.0,
            "source": "tradingview",
        },
    )

    captured = {}

    def fake_build_rrg_matrix(sectors_hist, bench, tail=8, method="jdk", sector_names=None):
        captured["n_sectors"] = len(sectors_hist)
        captured["tail"] = tail
        captured["method"] = method
        points = []
        for i, code in enumerate(sorted(sectors_hist)):
            base_x = 100.0 + i * 2.0
            base_y = -10.0 + i * 3.0
            points.append(
                {
                    "sector_code": code,
                    "sector_name": (sector_names or {}).get(code, code),
                    "rs_ratio": base_x,
                    "rs_momentum": base_y,
                    "quadrant": QUADRANTS[i % len(QUADRANTS)],
                    "tail": [
                        {"time": f"2024-01-{j + 20:02d}", "x": base_x + j, "y": base_y - j}
                        for j in range(tail)
                    ],
                }
            )
        return {"method": method, "points": points}

    monkeypatch.setattr(rrg_service, "build_rrg_matrix", fake_build_rrg_matrix)

    yield TestClient(server.app), captured
    stock_service.cache._store.clear()


def _payload(resp):
    body = resp.json()
    assert resp.status_code == 200, body
    assert body.get("status") == "success"
    return body["data"]


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------

class TestResponseSchema:
    def test_top_level_keys_and_defaults(self, client):
        tc, captured = client
        data = _payload(tc.get(RRG_URL))

        assert set(data.keys()) == {"benchmark", "interval", "method", "generated_at", "points"}
        assert data["benchmark"] == "VNINDEX"
        assert data["interval"] == "1W"
        assert data["method"] == "jdk"
        datetime.strptime(data["generated_at"], "%Y-%m-%dT%H:%M:%S")
        assert isinstance(data["points"], list) and data["points"]
        assert captured["n_sectors"] == len(data["points"])

    def test_explicit_params_echoed(self, client):
        tc, _ = client
        data = _payload(tc.get(RRG_URL, params={"benchmark": "VN30", "interval": "1M"}))
        assert data["benchmark"] == "VN30"
        assert data["interval"] == "1M"

    def test_invalid_interval_coerced_to_1W(self, client):
        tc, _ = client
        data = _payload(tc.get(RRG_URL, params={"interval": "13h"}))
        assert data["interval"] == "1W"

    def test_invalid_method_coerced_to_jdk(self, client):
        tc, _ = client
        data = _payload(tc.get(RRG_URL, params={"method": "bogus"}))
        assert data["method"] == "jdk"

    def test_enhanced_method_passes_through(self, client):
        tc, captured = client
        data = _payload(tc.get(RRG_URL, params={"method": "enhanced"}))
        assert data["method"] == "enhanced"
        assert captured["method"] == "enhanced"


class TestPointsContract:
    def test_point_schema_quadrant_enum_tail(self, client):
        tc, _ = client
        data = _payload(tc.get(RRG_URL, params={"tail": 5}))

        for p in data["points"]:
            core = {k for k in p if k != "tail"}
            assert core == {"sector_code", "sector_name", "rs_ratio", "rs_momentum", "quadrant"}
            assert p["quadrant"] in QUADRANT_SET
            assert isinstance(p["rs_ratio"], float)
            assert isinstance(p["rs_momentum"], float)

            tail = p["tail"]
            assert len(tail) == 5
            times = [t["time"] for t in tail]
            assert times == sorted(times)
            for t in tail:
                assert set(t.keys()) == {"time", "x", "y"}
                assert isinstance(t["time"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["time"])
                assert isinstance(t["x"], float)
                assert isinstance(t["y"], float)

    def test_tail_clamped_to_max_60(self, client):
        tc, captured = client
        _payload(tc.get(RRG_URL, params={"tail": 999}))
        assert captured["tail"] == 60

    def test_tail_clamped_to_min_1(self, client):
        tc, captured = client
        _payload(tc.get(RRG_URL, params={"tail": 0}))
        assert captured["tail"] == 1

    def test_sector_names_wired_from_registry(self, client):
        tc, _ = client
        data = _payload(tc.get(RRG_URL))

        codes = {p["sector_code"] for p in data["points"]}
        expected_codes = set(stock_service.SECTOR_ICB_REGISTRY.keys())
        assert codes == expected_codes
        for p in data["points"]:
            name = stock_service.SECTOR_ICB_REGISTRY[p["sector_code"]].get("name") or p["sector_code"]
            assert p["sector_name"] == name


class TestCaching:
    def test_second_hit_served_from_cache_without_recompute(self, client, monkeypatch):
        tc, _ = client
        first = _payload(tc.get(RRG_URL, params={"tail": 6}))

        calls = []
        monkeypatch.setattr(
            benchmark_service,
            "get_benchmark_history",
            lambda symbol, interval, lookback_days: calls.append(symbol) or {},
        )

        second = _payload(tc.get(RRG_URL, params={"tail": 6}))
        assert second == first
        assert calls == []
