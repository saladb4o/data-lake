"""
=============================================================================
ADVERSARIAL STRESS TEST SUITE: QUANTITATIVE VALUATION & BACKTEST ENGINES
=============================================================================
Stress-tests the system under extreme valuation inputs, high-concurrency bursts,
corrupted data payloads, and missing data lake fallback scenarios.
"""

import os
import math
import json
import pytest
import concurrent.futures
from unittest.mock import patch
from fastapi.testclient import TestClient

from server import app
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
    DEFAULT_RF,
    DEFAULT_ERP,
)
from services.fair_value_backtest_service import (
    fv_backtest_service,
    BacktestMode,
    BacktestResultPayload,
)
import services.stock_service as stock_service


client = TestClient(app)


# =============================================================================
# 1. EXTREME VALUATION INPUTS & MATHEMATICAL BOUNDARY TESTS
# =============================================================================

class TestExtremeValuationInputs:
    """Stress tests on mathematical boundaries and pathological inputs."""

    def test_wacc_zero_and_negative_inputs(self):
        engine = WACCEngine()

        # Zero market cap, zero debt, zero EBIT, zero interest
        res1 = engine.calculate(
            market_cap=0.0,
            interest_bearing_debt=0.0,
            ebit=0.0,
            interest_expense=0.0,
            beta_raw=0.0,
            roe=0.0,
            pb=0.0,
            pb_sector_median=0.0,
            adtv=0.0,
        )
        assert isinstance(res1, WACCResult)
        assert not math.isnan(res1.wacc)
        assert not math.isinf(res1.wacc)
        assert 0.05 <= res1.wacc <= 0.30

        # Highly negative inputs (distressed insolvency)
        res2 = engine.calculate(
            market_cap=-500e9,
            interest_bearing_debt=-100e9,
            ebit=-50e9,
            interest_expense=-10e9,
            beta_raw=-2.5,
            roe=-500.0,
            pb=-10.0,
            pb_sector_median=1.5,
            adtv=-1e9,
        )
        assert isinstance(res2, WACCResult)
        assert not math.isnan(res2.wacc)
        assert not math.isinf(res2.wacc)
        assert res2.wacc > 0.0

        # NaN and Inf inputs
        res3 = engine.calculate(
            market_cap=float("nan"),
            interest_bearing_debt=float("inf"),
            ebit=float("-inf"),
            interest_expense=float("nan"),
            beta_raw=float("nan"),
            roe=float("inf"),
            pb=float("nan"),
            pb_sector_median=float("nan"),
            adtv=float("nan"),
        )
        assert isinstance(res3, WACCResult)
        assert not math.isnan(res3.wacc)
        assert not math.isinf(res3.wacc)
        assert 0.05 <= res3.wacc <= 0.30

    def test_risk_firewall_zero_division_and_negative_equity(self):
        engine = RiskFirewallEngine()
        wacc_res = WACCEngine().calculate(100e9, 500e9, -50e9, 10e9, 1.0, -20.0, 1.0, 1.5, 1e9)

        # Negative equity and zero total assets
        res1 = engine.evaluate(
            fundamental_data={
                "total_assets": 0.0,
                "working_capital": -100e9,
                "retained_earnings": -200e9,
                "ebit": -50e9,
                "market_cap": 100e9,
                "total_liabilities": 500e9,
                "revenue": 0.0,
                "book_equity": -400e9,
                "price": 10000.0,
                "bvps": -5000.0,
                "downside_beta": 0.0,
            },
            wacc_res=wacc_res,
        )
        assert isinstance(res1, RiskFirewallResult)
        assert not math.isnan(res1.altman_z_score)
        assert not math.isnan(res1.beneish_m_score)
        assert not math.isnan(res1.dynamic_margin_of_safety)
        assert res1.dynamic_margin_of_safety >= 0.10
        assert res1.four_quadrant_category in ["toxic_exclusion", "distressed_turnaround", "forensic_trap", "safe_institutional"]

        # Extreme downside beta
        res2 = engine.evaluate(
            fundamental_data={
                "total_assets": 1000e9,
                "working_capital": 200e9,
                "retained_earnings": 300e9,
                "ebit": 100e9,
                "market_cap": 500e9,
                "total_liabilities": 200e9,
                "revenue": 800e9,
                "book_equity": 800e9,
                "price": 25000.0,
                "bvps": 20000.0,
                "downside_beta": 15.0, # Extreme downside volatility
            },
            wacc_res=wacc_res,
        )
        assert res2.dynamic_margin_of_safety <= 0.60 # Bounded maximum MoS

    def test_all_22_models_with_adversarial_data(self):
        engine = ValuationEngine()

        # Extremely distressed / negative / zero data payload
        distressed_data = {
            "symbol": "DISTRESSED",
            "price": -1000.0, # Negative price
            "shares_out": 0.0, # Zero shares
            "market_cap": -50e9,
            "revenue": -10e9,
            "ebit": -20e9,
            "ebitda": -15e9,
            "net_income": -30e9,
            "eps": -5000.0,
            "bvps": -2000.0,
            "tbvps": -3000.0,
            "cfo": -25e9,
            "fcf": -35e9,
            "affo": -20e9,
            "dividend_per_share": -500.0,
            "total_assets": -100e9,
            "total_liabilities": 500e9,
            "interest_bearing_debt": 400e9,
            "cash": -50e9,
            "capex": -10e9,
            "gross_ppe": 0.0,
            "working_capital": -100e9,
            "retained_earnings": -200e9,
            "roic": -50.0,
            "roe": -80.0,
            "net_margin": -100.0,
            "beta": -1.5,
            "downside_beta": 0.0,
            "rwa": 0.0,
            "nii": -50e9,
            "car_ratio": -5.0,
            "regulated_asset_base": -10e9,
            "netco_ebitda": -5e9,
            "serveco_ebitda": -5e9,
            "pipeline_success_rate": -0.5,
            "peak_sales": -100e9,
        }

        # Run all 22 models via engine.calculate_all_models
        model_outputs = engine.calculate_all_models(symbol="DISTRESSED", fundamental_data=distressed_data)
        assert len(model_outputs) == 22
        for m in model_outputs:
            assert isinstance(m, ModelValuationOutput)
            assert not math.isnan(m.fair_value)
            assert not math.isinf(m.fair_value)
            assert m.fair_value >= 0.0, f"Model {m.model_id} produced negative fair value: {m.fair_value}"

    def test_dcf_super_growth_and_terminal_growth_exceeds_wacc(self):
        """DCF growth rate higher than WACC (g >= WACC) must be bounded and not blow up to infinity/negatives."""
        models = ValuationModelsSuite()

        # Terminal growth (g=15%) > WACC (10%)
        fv = models.model_9_dcf_2stage_mckinsey(
            ebit=2000e9,
            roic=0.25,
            wacc=0.10,
            shares_out=100_000_000,
            cash_and_equiv=1500e9,
            total_debt=1000e9,
            g_stage1=0.25,
            g_terminal=0.15, # Adversarial terminal growth > WACC
            tax_rate=0.20,
            current_price=50000.0,
        )
        assert fv > 0.0
        assert not math.isinf(fv)
        assert not math.isnan(fv)

    def test_sensitivity_grid_with_singular_coordinates(self):
        """5x5 Sensitivity Grid where WACC <= terminal growth across cells."""
        scenario_engine = ScenarioEngine()
        models = ValuationModelsSuite()
        base_models = [
            ModelValuationOutput(
                model_id="dcf_2stage_mckinsey",
                model_name="DCF",
                category="intrinsic",
                fair_value=30000.0,
                upside_pct=20.0,
                weight=1.0,
                active=True,
                status="ACTIVE",
            )
        ]

        res = scenario_engine.generate(
            base_composite_fv=30000.0,
            wacc_base=0.04, # Very low WACC
            terminal_g_base=0.05, # g > WACC
            current_price=25000.0,
            base_models=base_models,
        )
        assert isinstance(res, ScenarioResult)
        assert len(res.sensitivity_grid_5x5) == 5
        for row in res.sensitivity_grid_5x5:
            assert len(row) == 5
            for cell_val in row:
                assert isinstance(cell_val, (int, float))
                assert not math.isnan(cell_val)
                assert not math.isinf(cell_val)
                assert cell_val >= 0.0

    def test_adaptive_weighting_with_zero_and_infinite_errors(self):
        weighting = AdaptiveWeightingEngine()
        models = ["blended_pe", "dcf_2stage_mckinsey", "rim_edwards_bell_ohlson"]
        values = [25000.0, 28000.0, 27000.0]

        # Weights with empty historical errors (instantaneous error)
        w_inst, rej = weighting.calculate_weights(
            active_models=models,
            active_values=values,
            composite_mode="omnibus",
            omnibus_metric="smape",
        )
        assert len(w_inst) > 0
        assert math.isclose(sum(w_inst.values()), 1.0, rel_tol=1e-3)

        # Historical errors with zero variance / infinite errors
        pathological_errors = {
            "blended_pe": {"smape": 0.0, "male": 0.0, "wmape": 0.0, "rmsle": 0.0, "variance": 0.0, "valid_count": 12},
            "dcf_2stage_mckinsey": {"smape": float("inf"), "male": float("inf"), "wmape": float("inf"), "rmsle": float("inf"), "variance": float("inf"), "valid_count": 12},
            "rim_edwards_bell_ohlson": {"smape": float("nan"), "male": float("nan"), "wmape": float("nan"), "rmsle": float("nan"), "variance": float("nan"), "valid_count": 12},
        }
        w_path, _ = weighting.calculate_weights(
            active_models=models,
            active_values=values,
            historical_errors=pathological_errors,
            composite_mode="omnibus",
            omnibus_metric="smape",
        )
        assert len(w_path) > 0
        assert math.isclose(sum(w_path.values()), 1.0, rel_tol=1e-3)


# =============================================================================
# 2. MALFORMED & CORRUPTED PAYLOAD IMMUNITY (DEF-02 EXTENDED)
# =============================================================================

class TestCorruptedPayloadImmunity:
    """Ensures ValuationEngine is completely crash-proof against null/string/corrupt data dicts."""

    def test_completely_empty_and_null_dict(self):
        engine = ValuationEngine()

        # Completely empty dict
        res_empty = engine.get_comprehensive_valuation(symbol="EMPTY_SYM", fundamental_data={})
        assert isinstance(res_empty, ValuationMatrixResult)
        assert res_empty.composite_fair_value >= 0.0

        # Dict with explicit None values for every expected key
        all_none = {
            "symbol": "NONE_SYM",
            "price": None,
            "market_cap": None,
            "shares_out": None,
            "revenue": None,
            "ebit": None,
            "ebitda": None,
            "net_income": None,
            "eps": None,
            "bvps": None,
            "tbvps": None,
            "debt": None,
            "interest_bearing_debt": None,
            "interest_expense": None,
            "cash": None,
            "cfo": None,
            "fcf": None,
            "affo": None,
            "dividend_per_share": None,
            "roe": None,
            "roic": None,
            "net_margin": None,
            "beta": None,
            "sector_code": None,
            "working_capital": None,
            "retained_earnings": None,
            "total_assets": None,
            "total_liabilities": None,
            "book_equity": None,
            "downside_beta": None,
            "rwa": None,
            "capex": None,
            "gross_ppe": None,
            "nii": None,
            "car_ratio": None,
            "regulated_asset_base": None,
            "netco_ebitda": None,
            "serveco_ebitda": None,
        }
        res_none = engine.get_comprehensive_valuation(symbol="NONE_SYM", fundamental_data=all_none)
        assert isinstance(res_none, ValuationMatrixResult)
        assert res_none.composite_fair_value >= 0.0
        assert len(res_none.models) == 22

    def test_corrupted_types_and_strings(self):
        engine = ValuationEngine()
        corrupted = {
            "symbol": "CORRUPTED",
            "price": "N/A",
            "market_cap": "None",
            "shares_out": "-",
            "revenue": "Unknown",
            "ebit": 100e9,
            "ebitda": 150e9,
            "net_income": "0.0",
            "eps": None,
            "bvps": "invalid",
            "total_assets": 1000e9,
            "total_liabilities": 500e9,
        }
        res = engine.get_comprehensive_valuation(symbol="CORRUPTED", fundamental_data=corrupted)
        assert isinstance(res, ValuationMatrixResult)
        assert res.composite_fair_value >= 0.0


# =============================================================================
# 3. HIGH CONCURRENCY & BURST SIMULATION TESTS
# =============================================================================

class TestConcurrencyAndBurstSimulations:
    """Stress tests high concurrency and rapid multithreaded requests."""

    def test_concurrent_valuation_evaluations(self):
        engine = ValuationEngine()
        symbols = ["HPG", "VNM", "FPT", "VIC", "VHM", "MSN", "MBB", "TCB", "VCB", "MWG"]

        def _eval_symbol(sym):
            return engine.get_comprehensive_valuation(symbol=sym, fundamental_data={"symbol": sym, "price": 25000.0})

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(_eval_symbol, sym) for sym in symbols * 5] # 50 concurrent calls
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 50
        for r in results:
            assert isinstance(r, ValuationMatrixResult)
            assert r.composite_fair_value >= 0.0

    def test_concurrent_fair_value_backtests(self):
        """Simulate concurrent backtests across all 3 modes simultaneously."""
        modes = [
            (BacktestMode.VALUATION_ONLY, "peter_lynch_garp", "blended_pe"),
            (BacktestMode.SCREENING_ONLY, "benjamin_graham_deep_value", "composite_fair_value"),
            (BacktestMode.HYBRID_FUNNEL, "buffett_quality_moat", "composite_fair_value"),
        ]

        def _run_bt(mode_tuple):
            m, strat, val_m = mode_tuple
            return fv_backtest_service.run_backtest(
                mode=m,
                screening_strategy=strat,
                valuation_model_id=val_m,
                margin_of_safety_pct=15.0,
                start_year=2024,
                end_year=2025,
                top_k=5,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_run_bt, m) for m in modes * 2]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 6
        for r in results:
            assert isinstance(r, BacktestResultPayload)
            assert r.metrics is not None
            assert "cagr_pct" in r.metrics

    def test_fastapi_burst_requests(self):
        """TestClient concurrent burst against valuation and backtest endpoints."""
        def _get_val(sym):
            return client.get(f"/api/valuation/comprehensive/{sym}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_get_val, sym) for sym in ["HPG", "VNM", "NONEXISTENT1", "NONEXISTENT2"] * 5]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(responses) == 20
        for res in responses:
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert "composite_fair_value" in data["data"]


# =============================================================================
# 4. MISSING DATA LAKE SCENARIO FALLBACK TESTS
# =============================================================================

class TestMissingDataLakeFallbacks:
    """Stress tests system behavior when data lake files or directories are missing/empty."""

    def test_valuation_engine_missing_historical_and_model_lake(self):
        """When disk lake fails to find historical models, engine must fallback to sector priors."""
        engine = ValuationEngine()

        val_res = engine.get_comprehensive_valuation(
            symbol="FALLBACK_ORPHAN_SYM",
            fundamental_data={"symbol": "FALLBACK_ORPHAN_SYM", "sector_code": "VNMAT"},
        )
        assert isinstance(val_res, ValuationMatrixResult)
        assert val_res.composite_fair_value >= 0.0
        assert val_res.models is not None
        assert len(val_res.models) > 0

    def test_fair_value_backtest_non_existent_universe(self):
        """When backtesting an empty universe / exchange, returns safe 0-trade metrics."""
        res = fv_backtest_service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            exchange="NON_EXISTENT_EXCHANGE",
            start_year=2024,
            end_year=2025,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] == 0
        assert res.metrics["total_return_pct"] == 0.0
        assert len(res.trades) == 0

    def test_corrupted_screener_snapshot_fallback(self):
        """When screener_snapshot is corrupted JSON, stock_service degrades gracefully."""
        with patch("builtins.open", side_effect=json.JSONDecodeError("Corrupted file", "", 0)):
            res = stock_service.get_quant_screener(limit=10)
            assert isinstance(res, dict)
            assert "results" in res
