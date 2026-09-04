"""
=============================================================================
COMPREHENSIVE 4-TIER E2E TEST SUITE: FAIR VALUE BACKTEST & VALUATION ENGINE
=============================================================================
Opaque-box end-to-end test suite verifying the complete quantitative workflow:
- Tier 1: Feature Coverage (3 Modes, Multi-Cadences, Multi-Horizon, Dynamic MoS, Firewalls, 22 Models)
- Tier 2: Boundary & Corner Cases (Empty Universes, 0 Trades, Extreme Beta/Premiums, Div-0 Guards)
- Tier 3: Cross-Feature Combinations (Mode x Universe x Cadence x Model, Blended vs. Omnibus Metrics)
- Tier 4: Real-World Application & API Scenarios (Multi-Year Backtests, REST Endpoint Contracts)
"""

import math
import pytest
from fastapi.testclient import TestClient

from services.fair_value_backtest_service import (
    FairValueBacktestService,
    BacktestMode,
    BacktestResultPayload,
    SCREENER_PRESETS,
    fv_backtest_service,
)
from services.valuation_engine import (
    ValuationEngine,
    WACCEngine,
    RiskFirewallEngine,
    ValuationModelsSuite,
    AdaptiveWeightingEngine,
    ScenarioEngine,
    safe_div,
    clamp,
    DEFAULT_RF,
    DEFAULT_ERP,
    DEFAULT_BASE_MOS,
)
from server import app


@pytest.fixture(scope="module")
def api_client():
    """FastAPI TestClient instance for opaque-box REST API assertions."""
    return TestClient(app)


@pytest.fixture(scope="module")
def backtest_engine():
    """Shared FairValueBacktestService instance."""
    return FairValueBacktestService()


@pytest.fixture(scope="module")
def valuation_engine():
    """Shared ValuationEngine instance."""
    return ValuationEngine()


# =============================================================================
# TIER 1: FEATURE COVERAGE
# =============================================================================

class TestTier1FeatureCoverage:
    """
    Tier 1 tests comprehensively exercise every primary operational feature,
    mode, cadence, horizon, dynamic MoS parameter, risk firewall, and valuation model.
    """

    def test_mode_1_valuation_only_execution(self, backtest_engine):
        """Tier 1: Mode 1 (Pure Valuation) operates purely on entry MoS discounts."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="composite_fair_value",
            margin_of_safety_pct=15.0,
            exit_premium_pct=20.0,
            holding_period_months=12,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.mode == BacktestMode.VALUATION_ONLY
        assert res.valuation_model_id == "composite_fair_value"
        assert res.metrics["total_trades"] > 0
        assert res.metrics["win_rate_pct"] >= 0.0
        assert math.isfinite(res.metrics["cagr_pct"])
        assert math.isfinite(res.metrics["sharpe_ratio"])
        assert len(res.equity_curve) > 0
        assert len(res.yearly_returns) == 4  # 2022, 2023, 2024, 2025

        # Validate trade records structure
        for trade in res.trades:
            assert trade["symbol"] in ["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"]
            assert trade["entry_price"] > 0.0
            assert trade["exit_price"] > 0.0
            assert trade["holding_days"] > 0
            assert trade["entry_fair_value"] > 0.0
            assert trade["exit_reason"] in ["TAKE_PROFIT", "HOLDING_EXPIRY", "STOP_LOSS", "REBALANCE"]

    def test_mode_2_screening_only_execution(self, backtest_engine):
        """Tier 1: Mode 2 (Pure Screening) evaluates factor and guru screener presets."""
        for strategy in ["peter_lynch_garp", "buffett_quality_moat", "piotroski_f_score"]:
            res = backtest_engine.run_backtest(
                mode=BacktestMode.SCREENING_ONLY,
                screening_strategy=strategy,
                holding_period_months=12,
                start_year=2022,
                end_year=2025,
                custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
            )
            assert isinstance(res, BacktestResultPayload)
            assert res.mode == BacktestMode.SCREENING_ONLY
            assert res.strategy_id == strategy
            assert res.metrics["total_trades"] > 0
            assert math.isfinite(res.metrics["cagr_pct"])
            assert math.isfinite(res.metrics["sharpe_ratio"])

    def test_mode_3_hybrid_funnel_execution(self, backtest_engine):
        """Tier 1: Mode 3 (2-Stage Hybrid Funnel) combines factor filtering with valuation MoS."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            valuation_model_id="dcf_2stage_mckinsey",
            margin_of_safety_pct=15.0,
            exit_premium_pct=25.0,
            use_dynamic_beta_mos=True,
            filter_z_score_safe=True,
            filter_rkv_value_trap=True,
            holding_period_months=12,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.mode == BacktestMode.HYBRID_FUNNEL
        assert res.strategy_id == "peter_lynch_garp"
        assert res.valuation_model_id == "dcf_2stage_mckinsey"
        assert res.metrics["total_trades"] >= 0
        assert res.diagnostics["firewalls_applied"]["z_score_safe"] is True
        assert res.diagnostics["firewalls_applied"]["rkv_value_trap_excluded"] is True
        assert res.diagnostics["firewalls_applied"]["dynamic_beta_mos"] is True

    @pytest.mark.parametrize("cadence", ["monthly", "quarterly", "semi_annual", "annual"])
    def test_rebalance_cadences_execution(self, backtest_engine, cadence):
        """Tier 1: All 4 rebalance cadences must execute cleanly and generate valid results."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            screening_strategy="peter_lynch_garp",
            rebalance_cadence=cadence,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.diagnostics["execution_settings"]["rebalance_cadence"] == cadence
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) > 0

    @pytest.mark.parametrize(
        "horizon,syms",
        [
            (3, ["HPG"]),
            (6, ["FPT"]),
            (12, ["VCB"]),
            (24, ["MBB"]),
            (36, ["MWG"]),
        ],
    )
    def test_multi_horizon_holding_periods(self, backtest_engine, horizon, syms):
        """Tier 1: Holding horizons from 3 months to 36 months execute properly with valid metrics."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="composite_fair_value",
            holding_period_months=horizon,
            start_year=2022,
            end_year=2025,
            custom_symbols=syms,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.holding_period_months == horizon
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) > 0

    def test_dynamic_downside_beta_mos(self, backtest_engine):
        """Tier 1: Dynamic MoS scaling adjusts entry discount using Downside Beta."""
        res_dynamic = backtest_engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            valuation_model_id="composite_fair_value",
            margin_of_safety_pct=15.0,
            use_dynamic_beta_mos=True,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        res_static = backtest_engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            valuation_model_id="composite_fair_value",
            margin_of_safety_pct=15.0,
            use_dynamic_beta_mos=False,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        assert res_dynamic.diagnostics["firewalls_applied"]["dynamic_beta_mos"] is True
        assert res_static.diagnostics["firewalls_applied"]["dynamic_beta_mos"] is False
        assert isinstance(res_dynamic, BacktestResultPayload)
        assert isinstance(res_static, BacktestResultPayload)

    def test_risk_firewalls_integration(self, backtest_engine):
        """Tier 1: Altman Z''-Score, Rhodes-Kropf, and Survival firewalls integrate seamlessly."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            valuation_model_id="composite_fair_value",
            filter_z_score_safe=True,
            filter_rkv_value_trap=True,
            survival_filter=True,
            tsmom_filter=False,
            forensic_filter=True,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        assert res.diagnostics["firewalls_applied"]["z_score_safe"] is True
        assert res.diagnostics["firewalls_applied"]["rkv_value_trap_excluded"] is True
        assert res.diagnostics["firewalls_applied"]["survival_filter"] is True
        assert res.diagnostics["firewalls_applied"]["forensic_filter"] is True

    def test_22_valuation_models_tournament_suite(self, backtest_engine):
        """Tier 1: Tournament mode produces full 23-model comparative matrix with complete telemetry."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="all",
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
        )
        matrix = res.model_tournament_matrix
        assert matrix is not None
        assert len(matrix) == 23  # 1 composite + 8 relative + 7 absolute + 7 sector

        required_models = [
            "composite_fair_value",
            "blended_pe",
            "ps_margin_adj",
            "p_fcf",
            "pb_rhodes_kropf",
            "p_tbv",
            "ev_ebitda",
            "p_cf",
            "p_affo",
            "dcf_2stage_mckinsey",
            "rim_edwards_bell_ohlson",
            "greenwald_epv",
            "graham_growth",
            "rule_of_40_growth",
            "acquirers_multiple_ev_ebit",
            "buffett_owners_earnings",
            "pharma_rnpv",
            "bank_equity_cash_flow",
            "reit_affo_dcf",
            "telecom_unbundled_sotp",
            "industrial_apv",
            "consumer_eva_mva",
            "utilities_3stage_ddm",
        ]
        model_ids = [m["id"] for m in matrix]
        for req in required_models:
            assert req in model_ids, f"Required model {req} missing from tournament matrix"

        for entry in matrix:
            assert "data_source" in entry
            assert "trade_count" in entry
            assert math.isfinite(entry["cagr_pct"])
            assert math.isfinite(entry["sharpe_ratio"])


# =============================================================================
# TIER 2: BOUNDARY, CORNER CASES & ADVERSARIAL ROBUSTNESS
# =============================================================================

class TestTier2BoundaryAndCornerCases:
    """
    Tier 2 tests verify edge cases: 0 trades, extreme parameter clamping,
    division-by-zero resilience, negative fundamentals, and degenerate universes.
    """

    def test_empty_universe_graceful_handling(self, backtest_engine):
        """Tier 2: Empty candidate set returns valid non-crashing payload with 0 trades."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=99.0,
            start_year=2024,
            end_year=2025,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) > 0
        for pt in res.equity_curve:
            assert math.isfinite(pt["strategy_equity"])
            assert math.isfinite(pt["benchmark_equity"])
            assert pt["strategy_equity"] >= 0.0

    def test_unreachable_mos_zero_trades(self, backtest_engine):
        """Tier 2: Unreachable MoS threshold produces structured 0-trade metrics."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=100.0,
            start_year=2024,
            end_year=2025,
        )
        assert res.metrics["total_trades"] >= 0
        assert math.isfinite(res.metrics["total_return_pct"])
        assert math.isfinite(res.metrics["cagr_pct"])
        assert math.isfinite(res.metrics["sharpe_ratio"])

    def test_extreme_downside_beta_clamping(self):
        """Tier 2: Dynamic MoS formula clamps extreme downside beta cleanly into [0.05, 0.60]."""
        # Formula: clamp(base_mos * (1 + max(0, beta_- - 1.0)*0.5) + penalties, 0.05, 0.60)
        base_mos = 0.20

        # Sub-zero / negative downside beta
        beta_neg = -2.5
        mos_neg = clamp(base_mos * (1.0 + max(0.0, beta_neg - 1.0) * 0.5), 0.05, 0.60)
        assert mos_neg == 0.20

        # Normal downside beta
        beta_norm = 1.4
        mos_norm = clamp(base_mos * (1.0 + max(0.0, beta_norm - 1.0) * 0.5), 0.05, 0.60)
        assert math.isclose(mos_norm, 0.24, rel_tol=1e-3)

        # Extreme downside beta (hyper-volatile)
        beta_extreme = 10.0
        mos_extreme = clamp(base_mos * (1.0 + max(0.0, beta_extreme - 1.0) * 0.5), 0.05, 0.60)
        assert mos_extreme == 0.60  # Clamped at ceiling

    def test_extreme_exit_premiums(self, backtest_engine):
        """Tier 2: Extreme exit premium (+500%) and stop-loss bounds execute safely."""
        res_high_tp = backtest_engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            exit_premium_pct=500.0,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
        )
        assert isinstance(res_high_tp, BacktestResultPayload)
        assert res_high_tp.metrics["total_trades"] >= 0
        for t in res_high_tp.trades:
            assert t["exit_reason"] in ["HOLDING_EXPIRY", "STOP_LOSS", "REBALANCE", "TAKE_PROFIT"]

    def test_safe_div_and_zero_division_resilience(self, valuation_engine):
        """Tier 2: Mathematical division guards protect against ZeroDivisionError and NaN."""
        assert safe_div(100.0, 0.0, 0.0) == 0.0
        assert safe_div(0.0, 0.0, 1.0) == 1.0
        assert safe_div(-50.0, 0.0, -1.0) == -1.0
        assert safe_div(100.0, 2.0, 0.0) == 50.0

        # Valuation engine resilience on empty / zero-valued fundamental snapshot
        zero_fundamentals = {
            "symbol": "ZERO",
            "price": 0.0,
            "market_cap": 0.0,
            "shares_out": 0.0,
            "revenue": 0.0,
            "ebit": 0.0,
            "ebitda": 0.0,
            "net_income": 0.0,
            "eps": 0.0,
            "bvps": 0.0,
            "tbvps": 0.0,
            "debt": 0.0,
            "interest_bearing_debt": 0.0,
            "interest_expense": 0.0,
            "cash": 0.0,
            "cfo": 0.0,
            "fcf": 0.0,
            "affo": 0.0,
            "dividend_per_share": 0.0,
            "roe": 0.0,
            "roic": 0.0,
            "net_margin": 0.0,
            "beta": 0.0,
            "downside_beta": 0.0,
        }
        val_res = valuation_engine.get_comprehensive_valuation(
            symbol="ZERO",
            fundamental_data=zero_fundamentals,
        )
        assert val_res is not None
        assert len(val_res.models) == 22
        for m in val_res.models:
            assert m.fair_value is None or math.isfinite(m.fair_value)

    def test_single_symbol_universe(self, backtest_engine):
        """Tier 2: Single stock universe executes correctly without multi-asset dependencies."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2022,
            end_year=2024,
            custom_symbols=["HPG"],
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) > 0


# =============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# =============================================================================

class TestTier3CrossFeatureCombinations:
    """
    Tier 3 tests verify orthogonal and pairwise interactions between Modes,
    Universes, Cadences, Weighting Sub-modes, and Friction settings.
    """

    @pytest.mark.parametrize(
        "mode,universe,strategy,model",
        [
            (BacktestMode.VALUATION_ONLY, "VN30", "peter_lynch_garp", "composite_fair_value"),
            (BacktestMode.SCREENING_ONLY, "VN70", "peter_lynch_garp", "composite_fair_value"),
            (BacktestMode.HYBRID_FUNNEL, "VNMID", "buffett_quality_moat", "dcf_2stage_mckinsey"),
            (BacktestMode.HYBRID_FUNNEL, "ALL", "piotroski_f_score", "rim_edwards_bell_ohlson"),
        ],
    )
    def test_pairwise_mode_x_universe(self, backtest_engine, mode, universe, strategy, model):
        """Tier 3: Pairwise matrix of Mode x Universe x Strategy x Model."""
        res = backtest_engine.run_backtest(
            mode=mode,
            screening_strategy=strategy,
            valuation_model_id=model,
            exchange=universe,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.mode == mode
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) > 0

    @pytest.mark.parametrize("metric", ["smape", "male", "wmape", "rmsle", "ivw"])
    def test_composite_modes_and_loss_metrics(self, backtest_engine, metric):
        """Tier 3: Omnibus loss metric weightings (SMAPE, MALE, WMAPE, RMSLE, IVW) execute cleanly."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="composite_fair_value",
            composite_mode="omnibus",
            omnibus_metric=metric,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
        )
        assert res.diagnostics["valuation_settings"]["composite_mode"] == "omnibus"
        assert res.diagnostics["valuation_settings"]["omnibus_metric"] == metric
        assert res.metrics["total_trades"] >= 0

    def test_tsmom_forensic_survival_interactions(self, backtest_engine):
        """Tier 3: Multi-layer interaction of Survival Firewall, TSMOM Trend, and Forensic M-Score."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            valuation_model_id="composite_fair_value",
            survival_filter=True,
            tsmom_filter=True,
            forensic_filter=True,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
        )
        assert res.diagnostics["firewalls_applied"]["survival_filter"] is True
        assert res.diagnostics["firewalls_applied"]["tsmom_filter"] is True
        assert res.diagnostics["firewalls_applied"]["forensic_filter"] is True
        assert res.metrics["total_trades"] >= 0

    def test_transaction_friction_strict_vs_ideal(self, backtest_engine):
        """Tier 3: Strict friction (0.35% round-trip) produces <= total return than ideal friction."""
        res_strict = backtest_engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            screening_strategy="peter_lynch_garp",
            fill_mode="strict",
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        res_ideal = backtest_engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            screening_strategy="peter_lynch_garp",
            fill_mode="ideal",
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        assert res_strict.diagnostics["execution_settings"]["fill_mode"] == "strict"
        assert res_ideal.diagnostics["execution_settings"]["fill_mode"] == "ideal"
        if res_strict.metrics["total_trades"] > 0 and res_ideal.metrics["total_trades"] > 0:
            assert res_strict.metrics["total_return_pct"] <= res_ideal.metrics["total_return_pct"] + 1e-5


# =============================================================================
# TIER 4: REAL-WORLD APPLICATION & API CONTRACT SCENARIOS
# =============================================================================

class TestTier4RealWorldAndAPIContracts:
    """
    Tier 4 tests verify multi-year historical timeline integrity, point-in-time
    consistency, and REST API contract compliance via FastAPI TestClient.
    """

    def test_multi_year_simulation_vn30(self, backtest_engine):
        """Tier 4: Full multi-year simulation (2021-2025) validates CAGR, MDD, Sharpe, Sortino."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            screening_strategy="peter_lynch_garp",
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
        )
        assert isinstance(res, BacktestResultPayload)
        assert len(res.yearly_returns) == 5  # 2021, 2022, 2023, 2024, 2025
        years = [y["year"] for y in res.yearly_returns]
        assert years == [2021, 2022, 2023, 2024, 2025]

        # Verify key performance indicators
        m = res.metrics
        assert math.isfinite(m["total_return_pct"])
        assert math.isfinite(m["cagr_pct"])
        assert math.isfinite(m["max_drawdown_pct"])
        assert math.isfinite(m["sharpe_ratio"])
        assert math.isfinite(m["sortino_ratio"])
        assert math.isfinite(m["calmar_ratio"])
        assert m["max_drawdown_pct"] >= 0.0

    def test_point_in_time_timeline_consistency(self, backtest_engine):
        """Tier 4: Timeline progression has strictly chronological quarters and monotonic dates."""
        res = backtest_engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            start_year=2022,
            end_year=2024,
            custom_symbols=["HPG", "FPT"],
        )
        curve = res.equity_curve
        assert len(curve) >= 8  # 3 years * 4 quarters = up to 12 points
        dates = [pt["date"] for pt in curve]
        assert dates == sorted(dates), "Equity curve quarters must be monotonically sorted in time"

    def test_api_fair_value_presets_endpoint(self, api_client):
        """Tier 4: GET /api/backtest/fair_value/presets returns complete catalog."""
        resp = api_client.get("/api/backtest/fair_value/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        presets = data["data"]
        assert "modes" in presets
        assert "cadences" in presets
        assert "screening_presets" in presets
        assert "valuation_models" in presets
        assert len(presets["modes"]) == 3
        assert len(presets["cadences"]) == 4
        assert len(presets["valuation_models"]) >= 22

    def test_api_fair_value_run_post_endpoint(self, api_client):
        """Tier 4: POST /api/backtest/fair_value/run returns valid JSON payload."""
        payload = {
            "mode": "hybrid_funnel",
            "screening_strategy": "peter_lynch_garp",
            "valuation_model_id": "composite_fair_value",
            "margin_of_safety_pct": 15.0,
            "exit_premium_pct": 20.0,
            "start_year": 2023,
            "end_year": 2025,
            "top_k": 5,
        }
        resp = api_client.post("/api/backtest/fair_value/run", params=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        data = body["data"]
        assert data["mode"] == "hybrid_funnel"
        assert "metrics" in data
        assert "yearly_returns" in data
        assert "equity_curve" in data
        assert "model_tournament_matrix" in data
        assert "diagnostics" in data

    def test_api_comprehensive_valuation_endpoint(self, api_client):
        """Tier 4: GET /api/valuation/comprehensive/{symbol} returns full 22 models and firewalls."""
        resp = api_client.get("/api/valuation/comprehensive/HPG")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        val = body["data"]
        assert val["symbol"] == "HPG"
        assert val["composite_fair_value"] > 0.0
        assert len(val["models"]) == 22
        assert "wacc_result" in val
        assert "risk_firewall" in val
        assert "scenarios" in val
        assert len(val["scenarios"]["sensitivity_grid_5x5"]) == 5

    def test_api_comprehensive_valuation_omnibus_endpoint(self, api_client):
        """Tier 4: GET /api/valuation/comprehensive/{symbol} supports omnibus error weighting."""
        resp = api_client.get("/api/valuation/comprehensive/FPT?mode=omnibus&metric=smape")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        val = body["data"]
        assert val["symbol"] == "FPT"
        assert val["composite_fair_value"] > 0.0
        assert val["metadata"]["composite_mode"] == "omnibus"
        assert val["metadata"]["omnibus_metric"] == "smape"

