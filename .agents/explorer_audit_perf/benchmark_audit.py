"""
Performance, Caching, and Latency Benchmark Script
Audits Data Lake loading, Valuation Engine, Backtest Engine, and API Response Times.
"""

import os
import sys
import time
import json
import statistics
from fastapi.testclient import TestClient

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server import app
from services.valuation_engine import ValuationEngine
from services.fair_value_backtest_service import fv_backtest_service, BacktestMode
from services.institutional_backtest_service import (
    run_bar_by_bar_backtest,
    run_parameter_sensitivity,
    run_monte_carlo_stress_test,
)
from services.stock_service import resolve_data_file, disk_lake

client = TestClient(app)

def benchmark_data_lake():
    print("=" * 70)
    print("1. DATA LAKE CACHING & I/O PROFILE")
    print("=" * 70)
    files = [
        "all_symbols.json",
        "industries.json",
        "historical_prices.json",
        "screener_snapshot.json",
        "financial_models.json",
    ]
    for fname in files:
        resolved = resolve_data_file(fname)
        exists = os.path.exists(resolved)
        size_kb = os.path.getsize(resolved) / 1024.0 if exists else 0.0
        
        # Cold read from disk
        t0 = time.perf_counter()
        if exists:
            with open(resolved, "r", encoding="utf-8") as f:
                d = json.load(f)
            t1 = time.perf_counter()
            items_count = len(d) if isinstance(d, (dict, list)) else 0
            read_ms = (t1 - t0) * 1000.0
        else:
            read_ms = 0.0
            items_count = 0

        # In-memory lake read (L2 cache)
        t2 = time.perf_counter()
        cached_d = disk_lake.read_json(fname)
        t3 = time.perf_counter()
        cached_ms = (t3 - t2) * 1000.0

        print(f"File: {fname:<25} | Size: {size_kb:8.1f} KB | Items: {items_count:5} | Cold Disk: {read_ms:6.2f} ms | L2 Cache: {cached_ms:5.3f} ms | Path: {resolved}")


def benchmark_valuation_engine():
    print("\n" + "=" * 70)
    print("2. COMPUTATIONAL HOTSPOTS: VALUATION ENGINE (22 MODELS)")
    print("=" * 70)
    engine = ValuationEngine()
    symbols = ["FPT", "HPG", "VCB", "VHM", "GAS"]
    
    for sym in symbols:
        timings = []
        for _ in range(5):
            t0 = time.perf_counter()
            res = engine.get_comprehensive_valuation(sym, composite_mode="blended")
            t1 = time.perf_counter()
            timings.append((t1 - t0) * 1000.0)
        
        mean_ms = statistics.mean(timings)
        min_ms = min(timings)
        max_ms = max(timings)
        models_count = len(res.models)
        valid_models = sum(1 for m in res.models if m.fair_value > 0)
        active_models = sum(1 for m in res.models if m.active)
        print(f"Symbol: {sym:<5} | 22-Model Blend Avg: {mean_ms:6.2f} ms (min: {min_ms:6.2f}, max: {max_ms:6.2f}) | Models: {valid_models}/{models_count} positive ({active_models} weighted) | Base FV: {res.composite_fair_value:10,.0f} VND | Status: {res.valuation_status}")

    print("\n-- Omnibus Metric Variations for FPT --")
    for metric in ["smape", "male", "wmape", "rmsle", "ivw"]:
        t0 = time.perf_counter()
        res = engine.get_comprehensive_valuation("FPT", composite_mode="omnibus", omnibus_metric=metric)
        t1 = time.perf_counter()
        ms = (t1 - t0) * 1000.0
        print(f"Metric: {metric:<6} | Execution: {ms:6.2f} ms | Composite FV: {res.composite_fair_value:10,.0f} VND | Status: {res.valuation_status}")


def benchmark_backtest_engine():
    print("\n" + "=" * 70)
    print("3. COMPUTATIONAL HOTSPOTS: BACKTESTING & SIMULATION ENGINE")
    print("=" * 70)
    
    # Mode 1: Pure Valuation
    t0 = time.perf_counter()
    res1 = fv_backtest_service.run_backtest(
        mode=BacktestMode.VALUATION_ONLY,
        valuation_model_id="composite_fair_value",
        margin_of_safety_pct=15.0,
        exchange="VN30",
        top_k=5
    )
    t1 = time.perf_counter()
    m1_ms = (t1 - t0) * 1000.0
    print(f"Mode 1 (Pure Valuation):     {m1_ms:7.2f} ms | Trades: {len(res1.trades):3} | CAGR: {res1.metrics.get('cagr_pct', 0.0):+.2f}% | Sharpe: {res1.metrics.get('sharpe_ratio', 0.0):.2f}")

    # Mode 2: Pure Screening
    t0 = time.perf_counter()
    res2 = fv_backtest_service.run_backtest(
        mode=BacktestMode.SCREENING_ONLY,
        screening_strategy="peter_lynch_garp",
        exchange="VN30",
        top_k=5
    )
    t1 = time.perf_counter()
    m2_ms = (t1 - t0) * 1000.0
    print(f"Mode 2 (Pure Screening):     {m2_ms:7.2f} ms | Trades: {len(res2.trades):3} | CAGR: {res2.metrics.get('cagr_pct', 0.0):+.2f}% | Sharpe: {res2.metrics.get('sharpe_ratio', 0.0):.2f}")

    # Mode 3: 2-Stage Hybrid Funnel
    t0 = time.perf_counter()
    res3 = fv_backtest_service.run_backtest(
        mode=BacktestMode.HYBRID_FUNNEL,
        screening_strategy="peter_lynch_garp",
        valuation_model_id="composite_fair_value",
        margin_of_safety_pct=15.0,
        exchange="VN30",
        top_k=5
    )
    t1 = time.perf_counter()
    m3_ms = (t1 - t0) * 1000.0
    print(f"Mode 3 (2-Stage Hybrid):     {m3_ms:7.2f} ms | Trades: {len(res3.trades):3} | CAGR: {res3.metrics.get('cagr_pct', 0.0):+.2f}% | Sharpe: {res3.metrics.get('sharpe_ratio', 0.0):.2f}")

    # Monte Carlo Stress Test
    t0 = time.perf_counter()
    mc = run_monte_carlo_stress_test(trades=res3.trades, initial_capital=100000000.0, iterations=500)
    t1 = time.perf_counter()
    mc_ms = (t1 - t0) * 1000.0
    print(f"Monte Carlo (500 iterations):{mc_ms:7.2f} ms | Status: {mc.get('status')} | Mean Final Equity: {mc.get('mean_final_equity', 0):,.0f} VND")

    # 2D Parameter Sensitivity
    t0 = time.perf_counter()
    sens = run_parameter_sensitivity(
        symbol="VN30",
        backtest_mode="hybrid",
        screening_strategy="peter_lynch_garp",
        valuation_model_id="composite_fair_value",
        time_horizon_years=2
    )
    t1 = time.perf_counter()
    sens_ms = (t1 - t0) * 1000.0
    grid_size = len(sens.get("matrix_cagr", []))
    print(f"2D Sensitivity Grid Scan:   {sens_ms:7.2f} ms | Grid: {grid_size}x{len(sens.get('matrix_cagr', [[]])[0]) if grid_size else 0} points")


def benchmark_api_endpoints():
    print("\n" + "=" * 70)
    print("4. API ENDPOINT LATENCY PROFILE & < 200ms TARGET COMPLIANCE")
    print("=" * 70)
    
    endpoints = [
        ("Valuation Comprehensive (FPT)", "/api/valuation/comprehensive/FPT?mode=blended"),
        ("Valuation Comprehensive (HPG)", "/api/valuation/comprehensive/HPG?mode=blended"),
        ("Valuation Comprehensive (VCB)", "/api/valuation/comprehensive/VCB?mode=blended"),
        ("Valuation Omnibus SMAPE", "/api/valuation/comprehensive/FPT?mode=omnibus&metric=smape"),
        ("Valuation Omnibus IVW", "/api/valuation/comprehensive/FPT?mode=omnibus&metric=ivw"),
        ("Backtest Presets", "/api/backtest/fair_value/presets"),
        ("Backtest Run Mode 1 (Valuation)", "/api/backtest/fair_value/run?mode=valuation_only&exchange=VN30&top_k=5"),
        ("Backtest Run Mode 2 (Screening)", "/api/backtest/fair_value/run?mode=screening_only&exchange=VN30&top_k=5"),
        ("Backtest Run Mode 3 (Hybrid)", "/api/backtest/fair_value/run?mode=hybrid_funnel&exchange=VN30&top_k=5"),
        ("Data Lake Status", "/api/data-lake-status"),
        ("Quant Screener Export CSV", "/api/screener/quant/export.csv"),
        ("Price Alerts List", "/api/alerts"),
        ("Institutional Sensitivity", "/api/quant/institutional/sensitivity?symbol=VN30&strategy_type=peter_lynch_garp&time_horizon_years=2"),
    ]

    for label, url in endpoints:
        # Cold Request
        t0 = time.perf_counter()
        r_cold = client.get(url)
        t1 = time.perf_counter()
        cold_ms = (t1 - t0) * 1000.0
        
        # Warm Request 1
        t2 = time.perf_counter()
        r_warm1 = client.get(url)
        t3 = time.perf_counter()
        warm1_ms = (t3 - t2) * 1000.0

        # Warm Request 2
        t4 = time.perf_counter()
        r_warm2 = client.get(url)
        t5 = time.perf_counter()
        warm2_ms = (t5 - t4) * 1000.0

        avg_warm = (warm1_ms + warm2_ms) / 2.0
        meets_target = "PASS (<200ms) [OK]" if avg_warm < 200.0 else "FAIL (>200ms) [WARN]"
        status_code = r_cold.status_code
        payload_bytes = len(r_cold.content)

        print(f"{label:<32} | Code: {status_code} | Cold: {cold_ms:7.1f} ms | Warm Avg: {avg_warm:6.2f} ms | Size: {payload_bytes/1024.0:6.1f} KB | {meets_target}")


if __name__ == "__main__":
    benchmark_data_lake()
    benchmark_valuation_engine()
    benchmark_backtest_engine()
    benchmark_api_endpoints()
