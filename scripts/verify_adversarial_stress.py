"""
=============================================================================
EMPIRICAL ADVERSARIAL STRESS & INTEGRITY VERIFICATION HARNESS
=============================================================================
Executes deep stress workloads, extreme input boundaries, burst concurrency,
and data lake outage simulations against the quantitative engine.
"""

import sys
import os
import time
import math
import json
import concurrent.futures
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

# Ensure UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("Could not switch the console to UTF-8", exc_info=True)

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.valuation_engine import (
    ValuationEngine,
    WACCEngine,
    RiskFirewallEngine,
    ValuationModelsSuite,
    AdaptiveWeightingEngine,
    ScenarioEngine,
    WACCResult,
    RiskFirewallResult,
    ModelValuationOutput,
    ValuationMatrixResult,
    ScenarioResult,
    safe_div,
    clamp,
)
from services.fair_value_backtest_service import (
    fv_backtest_service,
    BacktestMode,
    BacktestResultPayload,
)
import services.stock_service as stock_service


def run_test_suite():
    print("=" * 80)
    print("STARTING EMPIRICAL ADVERSARIAL STRESS TESTING HARNESS")
    print("=" * 80)

    total_checks = 0
    passed_checks = 0
    failed_checks = []

    # -------------------------------------------------------------------------
    # SUITE 1: Extreme Valuation Inputs & Pathological Boundaries
    # -------------------------------------------------------------------------
    print("\n[SUITE 1] Testing Extreme Valuation Inputs & Pathological Boundaries...")
    wacc_engine = WACCEngine()
    models_suite = ValuationModelsSuite()
    firewall_engine = RiskFirewallEngine()
    val_engine = ValuationEngine()

    extreme_cases = [
        ("Zero Inputs", {"market_cap": 0.0, "debt": 0.0, "ebit": 0.0, "interest": 0.0, "beta": 0.0, "roe": 0.0}),
        ("Deep Insolvency", {"market_cap": -100e9, "debt": 500e9, "ebit": -80e9, "interest": 100e9, "beta": -3.0, "roe": -500.0}),
        ("Singular Inf/NaN", {"market_cap": float("nan"), "debt": float("inf"), "ebit": float("-inf"), "interest": 0.0, "beta": float("nan"), "roe": float("inf")}),
    ]

    for label, case in extreme_cases:
        total_checks += 1
        try:
            res = wacc_engine.calculate(
                market_cap=case["market_cap"],
                interest_bearing_debt=case["debt"],
                ebit=case["ebit"],
                interest_expense=case["interest"],
                beta_raw=case["beta"],
                roe=case["roe"],
                pb=1.0,
                pb_sector_median=1.5,
                adtv=1e9,
            )
            assert isinstance(res, WACCResult)
            assert not math.isnan(res.wacc) and not math.isinf(res.wacc)
            assert res.wacc > 0.0
            passed_checks += 1
            print(f"  ✓ WACC Engine handled {label:20s} -> WACC: {res.wacc*100:.2f}%, Rating: {res.synthetic_rating}")
        except Exception as e:
            failed_checks.append(f"WACC Engine failed on {label}: {e}")
            print(f"  ✗ WACC Engine failed on {label}: {e}")

    # Test all 22 models on ultra-distressed payload
    distressed_payload = {
        "symbol": "STRESS_CORP",
        "price": -5000.0,
        "shares_out": 0.0,
        "market_cap": -100e9,
        "revenue": -50e9,
        "ebit": -20e9,
        "ebitda": -15e9,
        "net_income": -30e9,
        "eps": -10000.0,
        "bvps": -5000.0,
        "tbvps": -6000.0,
        "cfo": -40e9,
        "fcf": -60e9,
        "affo": -30e9,
        "dividend_per_share": -100.0,
        "total_assets": 0.0,
        "total_liabilities": 500e9,
        "interest_bearing_debt": 400e9,
        "cash": -10e9,
        "capex": -5e9,
        "gross_ppe": 0.0,
        "working_capital": -100e9,
        "retained_earnings": -200e9,
        "roic": -80.0,
        "roe": -120.0,
        "net_margin": -150.0,
        "beta": -2.0,
        "downside_beta": -1.0,
        "rwa": 0.0,
        "nii": -20e9,
        "car_ratio": -10.0,
        "regulated_asset_base": -5e9,
        "netco_ebitda": -2e9,
        "serveco_ebitda": -3e9,
        "pipeline_success_rate": -0.5,
        "peak_sales": -50e9,
    }

    print("\n[SUITE 1.1] Testing all 22 quantitative models under distressed payloads...")
    model_outputs = val_engine.calculate_all_models(symbol="STRESS_CORP", fundamental_data=distressed_payload)
    for m in model_outputs:
        total_checks += 1
        try:
            assert isinstance(m, ModelValuationOutput)
            assert not math.isnan(m.fair_value) and not math.isinf(m.fair_value)
            assert m.fair_value >= 0.0
            passed_checks += 1
            print(f"  ✓ {m.model_id:35s} -> Fair Value: {m.fair_value:,.2f} VND (Safe non-negative)")
        except Exception as e:
            failed_checks.append(f"{m.model_id} failed under distressed payload: {e}")
            print(f"  ✗ {m.model_id} crashed: {e}")

    # -------------------------------------------------------------------------
    # SUITE 2: High Concurrency & Burst Stress Simulations
    # -------------------------------------------------------------------------
    print("\n[SUITE 2] Testing High Concurrency & Burst Execution...")
    symbols = ["HPG", "VNM", "VCB", "FPT", "MWG", "VIC", "VHM", "MSN", "TCB", "MBB"]

    def _concurrent_val(sym_idx):
        sym = symbols[sym_idx % len(symbols)]
        return val_engine.get_comprehensive_valuation(
            symbol=sym,
            fundamental_data={"symbol": sym, "price": 30000.0, "sector_code": "VNMAT"},
            composite_mode="blended" if sym_idx % 2 == 0 else "omnibus",
        )

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(_concurrent_val, i) for i in range(100)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    t1 = time.time()

    total_checks += 1
    if len(results) == 100 and all(isinstance(r, ValuationMatrixResult) for r in results):
        passed_checks += 1
        print(f"  ✓ 100 concurrent valuation evaluations passed in {t1 - t0:.2f}s ({100 / (t1 - t0):.1f} req/s)")
    else:
        failed_checks.append("Concurrent valuation evaluations returned invalid count or types")
        print("  ✗ Concurrent valuation evaluations failed")

    # Concurrent 3-Mode Backtesting
    print("\n[SUITE 2.1] Testing Concurrent 3-Mode Backtesting Pipelines...")
    bt_configs = [
        (BacktestMode.VALUATION_ONLY, "peter_lynch_garp", "blended_pe"),
        (BacktestMode.SCREENING_ONLY, "benjamin_graham_deep_value", "composite_fair_value"),
        (BacktestMode.HYBRID_FUNNEL, "buffett_quality_moat", "composite_fair_value"),
        (BacktestMode.HYBRID_FUNNEL, "magic_formula_greenblatt", "dcf_2stage_mckinsey"),
    ]

    def _concurrent_bt(cfg):
        mode, strat, val_m = cfg
        return fv_backtest_service.run_backtest(
            mode=mode,
            screening_strategy=strat,
            valuation_model_id=val_m,
            margin_of_safety_pct=15.0,
            start_year=2024,
            end_year=2025,
            top_k=5,
        )

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_concurrent_bt, cfg) for cfg in bt_configs * 2]
        bt_results = [f.result() for f in concurrent.futures.as_completed(futures)]
    t1 = time.time()

    total_checks += 1
    if len(bt_results) == 8 and all(isinstance(r, BacktestResultPayload) for r in bt_results):
        passed_checks += 1
        print(f"  ✓ 8 concurrent multi-mode backtests completed in {t1 - t0:.2f}s without race conditions")
    else:
        failed_checks.append("Concurrent backtesting failed")
        print("  ✗ Concurrent backtesting failed")

    # -------------------------------------------------------------------------
    # SUITE 3: Missing Data Lake Scenario Fallbacks
    # -------------------------------------------------------------------------
    print("\n[SUITE 3] Testing Missing Data Lake Scenario Fallbacks...")
    total_checks += 1
    try:
        # Simulate unknown symbol with no data lake footprint
        val_orphan = val_engine.get_comprehensive_valuation(
            symbol="UNKNOWN_ORPHAN_999",
            fundamental_data=None,
            composite_mode="blended",
        )
        assert isinstance(val_orphan, ValuationMatrixResult)
        assert val_orphan.composite_fair_value >= 0.0
        assert len(val_orphan.models) == 22
        passed_checks += 1
        print(f"  ✓ Non-existent symbol fallback succeeded -> Composite Fair Value: {val_orphan.composite_fair_value}")
    except Exception as e:
        failed_checks.append(f"Unknown symbol valuation failed: {e}")
        print(f"  ✗ Unknown symbol valuation failed: {e}")

    total_checks += 1
    try:
        # Test backtest on non-existent universe
        bt_empty = fv_backtest_service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            exchange="NON_EXISTENT_EXCHANGE",
            start_year=2024,
            end_year=2025,
        )
        assert isinstance(bt_empty, BacktestResultPayload)
        assert bt_empty.metrics["total_trades"] == 0
        assert bt_empty.metrics["total_return_pct"] == 0.0
        passed_checks += 1
        print("  ✓ Non-existent exchange universe backtest returned graceful 0-trade payload")
    except Exception as e:
        failed_checks.append(f"Non-existent exchange backtest failed: {e}")
        print(f"  ✗ Non-existent exchange backtest failed: {e}")

    # -------------------------------------------------------------------------
    # SUMMARY & VERDICT
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("ADVERSARIAL STRESS TEST SUMMARY")
    print("=" * 80)
    print(f"Total Checks Executed : {total_checks}")
    print(f"Passed Checks         : {passed_checks} ({passed_checks / total_checks * 100:.1f}%)")
    print(f"Failed Checks         : {len(failed_checks)}")

    if failed_checks:
        print("\nFAILURE DETAILS:")
        for f in failed_checks:
            print(f"  - {f}")
        print("\nVERDICT: REQUEST_CHANGES")
        return False
    else:
        print("\nVERDICT: ALL ADVERSARIAL STRESS TESTS PASSED CLEANLY (APPROVE)")
        return True


if __name__ == "__main__":
    success = run_test_suite()
    sys.exit(0 if success else 1)
