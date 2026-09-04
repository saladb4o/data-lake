"""
Empirical Performance & Latency Benchmark Test Suite
=====================================================
Measures and verifies latency characteristics across all key cached backend endpoints:
1. /api/valuation/comprehensive/{symbol} (HPG, FPT, VCB, VHM, SSI)
2. /api/backtest/fair_value/run (Mode 1: valuation_only, Mode 2: screening_only, Mode 3: hybrid_funnel)
3. /api/data-lake-status
4. /api/alerts
5. /api/screener/quant/export.csv

Verifies threshold requirement: Cached/warm responses must be < 200ms.
"""

import os
import sys
import time
import math
import statistics

# Ensure project root is in sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest
from fastapi.testclient import TestClient
from server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def measure_endpoint_latency(client: TestClient, method: str, url: str, params: dict = None, iterations: int = 30):
    """
    Measures cold response time and warm/cached response distribution over N iterations.
    Returns a dict with complete latency distribution metrics (in milliseconds).
    """
    # Cold / warming request
    t0 = time.perf_counter()
    if method.upper() == "GET":
        resp0 = client.get(url, params=params)
    elif method.upper() == "POST":
        resp0 = client.post(url, params=params)
    else:
        raise ValueError(f"Unsupported method {method}")
    cold_ms = (time.perf_counter() - t0) * 1000.0
    assert resp0.status_code == 200, f"Cold request failed: {resp0.status_code} - {resp0.text}"

    # Warm / cached requests
    latencies = []
    for _ in range(iterations):
        t_start = time.perf_counter()
        if method.upper() == "GET":
            resp = client.get(url, params=params)
        elif method.upper() == "POST":
            resp = client.post(url, params=params)
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        assert resp.status_code == 200, f"Warm request failed: {resp.status_code}"
        latencies.append(t_elapsed_ms)

    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    def percentile(p):
        k = (n - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_lats[int(k)]
        d0 = sorted_lats[int(f)] * (c - k)
        d1 = sorted_lats[int(c)] * (k - f)
        return d0 + d1

    return {
        "endpoint": url,
        "method": method.upper(),
        "params": params or {},
        "cold_ms": round(cold_ms, 2),
        "iterations": iterations,
        "min_ms": round(min(sorted_lats), 2),
        "p50_ms": round(percentile(50), 2),
        "p90_ms": round(percentile(90), 2),
        "p95_ms": round(percentile(95), 2),
        "p99_ms": round(percentile(99), 2),
        "max_ms": round(max(sorted_lats), 2),
        "mean_ms": round(statistics.mean(sorted_lats), 2),
        "std_dev_ms": round(statistics.stdev(sorted_lats) if n > 1 else 0.0, 2),
        "cached_under_200ms": percentile(95) < 200.0 and statistics.mean(sorted_lats) < 200.0,
    }


class TestCachedEndpointsLatency:
    """Empirical latency test cases verifying < 200ms requirement."""

    def test_latency_valuation_comprehensive_hpg_blended(self, client):
        metrics = measure_endpoint_latency(
            client, "GET", "/api/valuation/comprehensive/HPG",
            params={"mode": "blended"}
        )
        print(f"\n[BENCHMARK] Valuation HPG Blended: mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, p50={metrics['p50_ms']}ms, cold={metrics['cold_ms']}ms")
        assert metrics["p95_ms"] < 200.0, f"p95 latency {metrics['p95_ms']}ms exceeded 200ms limit"
        assert metrics["mean_ms"] < 200.0

    def test_latency_valuation_comprehensive_hpg_omnibus(self, client):
        metrics = measure_endpoint_latency(
            client, "GET", "/api/valuation/comprehensive/HPG",
            params={"mode": "omnibus", "metric": "smape"}
        )
        print(f"\n[BENCHMARK] Valuation HPG Omnibus (SMAPE): mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, p50={metrics['p50_ms']}ms")
        assert metrics["p95_ms"] < 200.0
        assert metrics["mean_ms"] < 200.0

    def test_latency_valuation_comprehensive_multi_symbols(self, client):
        for sym in ["FPT", "VCB", "VHM", "SSI"]:
            metrics = measure_endpoint_latency(
                client, "GET", f"/api/valuation/comprehensive/{sym}",
                params={"mode": "blended"}, iterations=15
            )
            print(f"\n[BENCHMARK] Valuation {sym}: mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, min={metrics['min_ms']}ms")
            assert metrics["p95_ms"] < 200.0

    def test_latency_backtest_mode1_pure_valuation(self, client):
        metrics = measure_endpoint_latency(
            client, "POST", "/api/backtest/fair_value/run",
            params={
                "mode": "valuation_only",
                "valuation_model_id": "composite_fair_value",
                "margin_of_safety_pct": 15.0,
                "exit_premium_pct": 20.0,
                "start_year": 2023,
                "end_year": 2025,
            }
        )
        print(f"\n[BENCHMARK] Backtest Mode 1 (Valuation Only): mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, cold={metrics['cold_ms']}ms")
        assert metrics["p95_ms"] < 200.0, f"Mode 1 cached p95 {metrics['p95_ms']}ms exceeded 200ms"

    def test_latency_backtest_mode2_pure_screening(self, client):
        metrics = measure_endpoint_latency(
            client, "POST", "/api/backtest/fair_value/run",
            params={
                "mode": "screening_only",
                "screening_strategy": "peter_lynch_garp",
                "start_year": 2023,
                "end_year": 2025,
            }
        )
        print(f"\n[BENCHMARK] Backtest Mode 2 (Screening Only): mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, cold={metrics['cold_ms']}ms")
        assert metrics["p95_ms"] < 200.0, f"Mode 2 cached p95 {metrics['p95_ms']}ms exceeded 200ms"

    def test_latency_backtest_mode3_hybrid_funnel(self, client):
        metrics = measure_endpoint_latency(
            client, "POST", "/api/backtest/fair_value/run",
            params={
                "mode": "hybrid_funnel",
                "screening_strategy": "peter_lynch_garp",
                "valuation_model_id": "composite_fair_value",
                "margin_of_safety_pct": 15.0,
                "exit_premium_pct": 20.0,
                "start_year": 2023,
                "end_year": 2025,
            }
        )
        print(f"\n[BENCHMARK] Backtest Mode 3 (Hybrid Funnel): mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, cold={metrics['cold_ms']}ms")
        assert metrics["p95_ms"] < 200.0, f"Mode 3 cached p95 {metrics['p95_ms']}ms exceeded 200ms"

    def test_latency_data_lake_status(self, client):
        metrics = measure_endpoint_latency(client, "GET", "/api/data-lake-status", iterations=30)
        print(f"\n[BENCHMARK] Data Lake Status: mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, cold={metrics['cold_ms']}ms")
        assert metrics["p95_ms"] < 200.0
        assert metrics["mean_ms"] < 200.0

    def test_latency_alerts(self, client):
        metrics = measure_endpoint_latency(client, "GET", "/api/alerts", iterations=30)
        print(f"\n[BENCHMARK] Price Alerts: mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, cold={metrics['cold_ms']}ms")
        assert metrics["p95_ms"] < 200.0
        assert metrics["mean_ms"] < 200.0

    def test_latency_screener_quant_export_csv(self, client):
        metrics = measure_endpoint_latency(
            client, "GET", "/api/screener/quant/export.csv",
            params={"exchange": "ALL", "sector": "ALL"}, iterations=20
        )
        print(f"\n[BENCHMARK] Screener Quant CSV Export: mean={metrics['mean_ms']}ms, p95={metrics['p95_ms']}ms, cold={metrics['cold_ms']}ms")
        assert metrics["p95_ms"] < 200.0
        assert metrics["mean_ms"] < 200.0


if __name__ == "__main__":
    import json
    c = TestClient(app)
    endpoints_to_benchmark = [
        ("GET", "/api/valuation/comprehensive/HPG", {"mode": "blended"}),
        ("GET", "/api/valuation/comprehensive/HPG", {"mode": "omnibus", "metric": "smape"}),
        ("GET", "/api/valuation/comprehensive/FPT", {"mode": "blended"}),
        ("GET", "/api/valuation/comprehensive/VCB", {"mode": "blended"}),
        ("GET", "/api/valuation/comprehensive/VHM", {"mode": "blended"}),
        ("POST", "/api/backtest/fair_value/run", {
            "mode": "valuation_only", "valuation_model_id": "composite_fair_value",
            "margin_of_safety_pct": 15.0, "exit_premium_pct": 20.0, "start_year": 2023, "end_year": 2025
        }),
        ("POST", "/api/backtest/fair_value/run", {
            "mode": "screening_only", "screening_strategy": "peter_lynch_garp",
            "start_year": 2023, "end_year": 2025
        }),
        ("POST", "/api/backtest/fair_value/run", {
            "mode": "hybrid_funnel", "screening_strategy": "peter_lynch_garp",
            "valuation_model_id": "composite_fair_value", "margin_of_safety_pct": 15.0,
            "exit_premium_pct": 20.0, "start_year": 2023, "end_year": 2025
        }),
        ("GET", "/api/data-lake-status", None),
        ("GET", "/api/alerts", None),
        ("GET", "/api/screener/quant/export.csv", {"exchange": "ALL", "sector": "ALL"}),
    ]

    results = []
    print("=" * 90)
    print("EMPIRICAL LATENCY BENCHMARK SUITE — EXECUTING TESTS")
    print("=" * 90)
    for method, url, params in endpoints_to_benchmark:
        res = measure_endpoint_latency(c, method, url, params, iterations=35)
        results.append(res)
        param_str = f" ({params})" if params else ""
        print(f"[{method}] {url}{param_str:<40} -> Cold: {res['cold_ms']:>6.1f}ms | Mean: {res['mean_ms']:>5.2f}ms | p50: {res['p50_ms']:>5.2f}ms | p95: {res['p95_ms']:>5.2f}ms | Under 200ms: {res['cached_under_200ms']}")

    print("\n" + "=" * 90)
    print("BENCHMARK SUMMARY TABLE")
    print("=" * 90)
    print(f"{'Endpoint':<42} | {'Cold (ms)':<9} | {'Mean (ms)':<9} | {'p50 (ms)':<8} | {'p95 (ms)':<8} | {'Status (<200ms)':<15}")
    print("-" * 90)
    for r in results:
        ep_label = r['endpoint']
        if r['params']:
            if 'mode' in r['params']:
                ep_label += f" [{r['params']['mode']}]"
        print(f"{ep_label:<42} | {r['cold_ms']:>9.1f} | {r['mean_ms']:>9.2f} | {r['p50_ms']:>8.2f} | {r['p95_ms']:>8.2f} | {'PASS (OK)' if r['cached_under_200ms'] else 'FAIL (TIMEOUT)'}")
