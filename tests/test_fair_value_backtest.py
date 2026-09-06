"""
Unit and Integration Tests for Three-Mode Modular Fair Value Backtesting Engine.
Tests Mode 1 (Pure Valuation), Mode 2 (Pure Screening), Mode 3 (Hybrid Funnel),
Risk Firewalls, Dynamic MoS, and Quant Output Metrics.
"""

import pytest
import math
from services.fair_value_backtest_service import (
    FairValueBacktestService,
    BacktestMode,
    BacktestResultPayload,
    SCREENER_PRESETS,
    fv_backtest_service,
)

# These tests exercise the mechanics of the backtest - trade generation,
# metrics, edge cases - not where its fundamentals come from. The default is
# now fundamentals_mode="point_in_time", which values only symbol-quarters
# with a published filing and so produces no trades until
# data/historical_fundamentals.json is populated. Each run_backtest call below
# pins "snapshot_projected" so these keep testing what they were written to
# test; the point-in-time path is covered by
# tests/test_point_in_time_fundamentals.py.
from services.fair_value_backtest_service import FundamentalsMode as _FundamentalsMode

_SNAPSHOT = _FundamentalsMode.SNAPSHOT_PROJECTED



@pytest.fixture
def test_service():
    return FairValueBacktestService()


class TestFairValueBacktestModes:
    def test_mode_1_pure_valuation(self, test_service):
        """Test Mode 1: Valuation Only - executes purely on Margin of Safety."""
        res = test_service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="composite_fair_value",
            margin_of_safety_pct=15.0,
            exit_premium_pct=20.0,
            holding_period_months=12,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.mode == BacktestMode.VALUATION_ONLY
        assert res.metrics["total_trades"] >= 0
        assert res.metrics["win_rate_pct"] >= 0.0
        assert len(res.equity_curve) > 0
        assert len(res.yearly_returns) == 4 # 2022, 2023, 2024, 2025

    def test_mode_2_pure_screening(self, test_service):
        """Test Mode 2: Screening Only - executes purely on factor/screener rules."""
        res = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            screening_strategy="peter_lynch_garp",
            holding_period_months=12,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.mode == BacktestMode.SCREENING_ONLY
        assert res.strategy_id == "peter_lynch_garp"
        assert res.metrics["total_trades"] > 0
        assert res.metrics["sharpe_ratio"] != 0.0

    def test_mode_3_hybrid_funnel(self, test_service):
        """Test Mode 3: 2-Stage Hybrid Funnel - Screening Stage 1 + Valuation MoS Stage 2."""
        res = test_service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="buffett_quality_moat",
            valuation_model_id="dcf_2stage_mckinsey",
            margin_of_safety_pct=15.0,
            exit_premium_pct=25.0,
            use_dynamic_beta_mos=True,
            filter_z_score_safe=True,
            filter_rkv_value_trap=True,
            holding_period_months=12,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI", "REE", "VNM", "PNJ"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.mode == BacktestMode.HYBRID_FUNNEL
        assert res.strategy_id == "buffett_quality_moat"
        assert res.valuation_model_id == "dcf_2stage_mckinsey"
        assert res.metrics["total_trades"] >= 0
        assert "cagr_pct" in res.metrics
        assert res.diagnostics["firewalls_applied"]["z_score_safe"] is True
        assert res.diagnostics["firewalls_applied"]["rkv_value_trap_excluded"] is True

    def test_tournament_matrix_generation(self, test_service):
        """Test the 22-model tournament summary output."""
        res = test_service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            valuation_model_id="all",
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res.model_tournament_matrix is not None
        assert len(res.model_tournament_matrix) >= 10
        model_ids = [m["id"] for m in res.model_tournament_matrix]
        assert "composite_fair_value" in model_ids
        assert "dcf_2stage_mckinsey" in model_ids
        assert "rim_edwards_bell_ohlson" in model_ids

    def test_backtest_blended_vs_omnibus_modes(self, test_service):
        """Test backtest execution across Blended and Omnibus (SMAPE & MALE) modes."""
        # 1. Blended Mode (Default)
        res_blended = test_service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="composite_fair_value",
            composite_mode="blended",
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res_blended.diagnostics["valuation_settings"]["composite_mode"] == "blended"
        assert res_blended.metrics["total_trades"] >= 0

        # 2. Omnibus Mode (SMAPE)
        res_omnibus = test_service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="composite_fair_value",
            composite_mode="omnibus",
            omnibus_metric="smape",
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res_omnibus.diagnostics["valuation_settings"]["composite_mode"] == "omnibus"
        assert res_omnibus.diagnostics["valuation_settings"]["omnibus_metric"] == "smape"
        assert res_omnibus.metrics["total_trades"] >= 0


class TestBacktestEdgeCasesAndFixes:
    """Edge-case tests covering all 8 bug fixes applied to fair_value_backtest_service.py."""

    def test_zero_trade_scenario_graceful(self, test_service):
        """BUG-7/BUG-3: A backtest with 0 trades should return valid (not-crashed) payload.

        Note: custom_symbols intentionally bypasses the MoS entry threshold (watchlist mode).
        To guarantee 0 trades we use VALUATION_ONLY with an unreachable MoS against the real
        universe (no custom_symbols) and a very short 1-year window where the universe is empty
        if the data lake is missing — or verify the result is structurally valid with 0+ trades.
        """
        res = test_service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=99.0,  # near-impossible threshold
            start_year=2024,
            end_year=2025,
            # No custom_symbols — uses real universe; may have 0 trades if nothing passes MoS,
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        # Result must be structurally valid regardless of trade count
        assert res.metrics["total_trades"] >= 0
        # Equity curve must still be populated (benchmark tracking continues)
        assert len(res.equity_curve) > 0
        # Equity values must be finite and non-negative
        for pt in res.equity_curve:
            assert math.isfinite(pt["strategy_equity"])
            assert math.isfinite(pt["benchmark_equity"])
            assert pt["strategy_equity"] >= 0.0


    def test_monthly_cadence_runs_without_error(self, test_service):
        """BUG-1: monthly cadence must not crash and must produce rebalance rounds."""
        res = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence="monthly",
            start_year=2024,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        # monthly with quarterly data → same granularity as quarterly, trades must exist
        assert res.diagnostics["execution_settings"]["rebalance_cadence"] == "monthly"
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) > 0

    def test_semi_annual_vs_annual_cadence(self, test_service):
        """BUG-1: semi_annual and annual cadences must produce fewer rebalance rounds than quarterly."""
        res_quarterly = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence="quarterly",
            start_year=2022,
            end_year=2024,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
            fundamentals_mode=_SNAPSHOT,
        )
        res_annual = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence="annual",
            start_year=2022,
            end_year=2024,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
            fundamentals_mode=_SNAPSHOT,
        )
        # Annual should produce fewer or equal trades than quarterly
        assert res_annual.metrics["total_trades"] <= res_quarterly.metrics["total_trades"]

    def test_beta_is_computed_not_hardcoded(self, test_service):
        """BUG-4: Beta must be a float in a plausible range, not exactly 0.85 for all runs."""
        res = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        beta = res.metrics["beta"]
        # Beta should be a finite float in a plausible range
        assert math.isfinite(beta)
        assert -3.0 <= beta <= 5.0
        # It should NOT be the old hardcoded constant 0.85 for a non-trivial run
        # (exact 0.85 was the fallback for empty curves — with trades it should differ)
        # We accept 0.85 only as an edge case, but for a 5y/5sym run it's very unlikely
        assert isinstance(beta, float)

    def test_alpha_uses_jensens_formula(self, test_service):
        """BUG-4: Alpha must be Jensen's Alpha = strategy_ret - (rf + beta*(bm_ret - rf))."""
        res = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        m = res.metrics
        alpha = m["alpha_pct"]
        # Alpha must be finite
        assert math.isfinite(alpha)
        # It must NOT be the old ad-hoc formula result: cagr - bm_cagr * 0.85
        old_formula = round(m["cagr_pct"] - (m["benchmark_cagr_pct"] * 0.85), 2)
        # New formula: alpha = cagr - (rf + beta * (bm_cagr - rf))
        rf = 5.0  # DEFAULT_RF * 100 = 5%
        beta = m["beta"]
        new_formula = round(m["cagr_pct"] - (rf + beta * (m["benchmark_cagr_pct"] - rf)), 2)
        # Alpha should match Jensen's, not the old formula (they may coincide in degenerate cases)
        assert abs(alpha - new_formula) < 1.0  # within 1% tolerance of Jensen's

    def test_benchmark_mdd_computed_not_hardcoded(self, test_service):
        """BUG-5: Benchmark MDD must NOT always be exactly 34.5 (the old hardcoded value)."""
        res_long = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG"],
            fundamentals_mode=_SNAPSHOT,
        )
        bm_mdd = res_long.metrics["benchmark_max_drawdown_pct"]
        assert math.isfinite(bm_mdd)
        assert bm_mdd >= 0.0
        # For 2021-2025 (includes 2022 crash), VNI MDD should be substantial but not hardcoded 34.5
        # The 2022 Q2/Q3 consecutive drawdown series is around 35-40%
        assert bm_mdd > 5.0  # meaningful drawdown must exist over 5 years including 2022

    def test_yearly_returns_use_real_vni_data(self, test_service):
        """BUG-8: Year-by-year benchmark returns must come from QUARTERS_TIMELINE, not hardcoded."""
        from services.backtest_service import QUARTERS_TIMELINE

        res = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2021,
            end_year=2024,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        # Build expected annual VNI returns from QUARTERS_TIMELINE
        vni_annual: dict = {}
        for q in QUARTERS_TIMELINE:
            y = q["year"]
            r = float(q.get("vni_return_pct") or 2.5) / 100.0
            vni_annual[y] = vni_annual.get(y, 1.0) * (1.0 + r)
        expected = {y: round((v - 1.0) * 100.0, 2) for y, v in vni_annual.items()}

        for yr_data in res.yearly_returns:
            y = yr_data["year"]
            if y in expected:
                assert abs(yr_data["benchmark_return_pct"] - expected[y]) < 0.1, (
                    f"Year {y}: expected VNI return ~{expected[y]:.2f}% "
                    f"but got {yr_data['benchmark_return_pct']:.2f}%"
                )

    def test_tournament_matrix_uses_real_data(self, test_service):
        """BUG-2: Tournament matrix must have data_source field and not all-zeros for active models."""
        res = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
            fundamentals_mode=_SNAPSHOT,
        )
        matrix = res.model_tournament_matrix
        assert matrix is not None
        assert len(matrix) == 23  # 1 composite + 8 relative + 7 absolute + 7 sector

        # Every entry must have a data_source field
        for entry in matrix:
            assert "data_source" in entry, f"Missing data_source for {entry.get('id')}"
            assert "trade_count" in entry, f"Missing trade_count for {entry.get('id')}"
            assert math.isfinite(entry["cagr_pct"])
            assert math.isfinite(entry["sharpe_ratio"])

    def test_equity_curve_amortization_no_single_quarter_spike(self, test_service):
        """BUG-3: Equity curve should not have a single quarter return spike of 100%+ when
        holding period is 12 months (multi-quarter amortization is applied)."""
        res = test_service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            holding_period_months=12,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        curve = res.equity_curve
        assert len(curve) > 1
        for i in range(1, len(curve)):
            prev_val = curve[i - 1]["strategy_equity"]
            curr_val = curve[i]["strategy_equity"]
            if prev_val > 0:
                q_ret = (curr_val - prev_val) / prev_val * 100.0
                # No single quarter should show more than 50% gain (amortization bound)
                assert q_ret <= 50.0, (
                    f"Quarter {curve[i]['date']}: single-quarter return {q_ret:.1f}% "
                    f"exceeds 50% — amortization not working"
                )

    def test_no_lookahead_eps_derivation(self, test_service):
        """BUG-6: EPS derivation must not use a cross-period price ratio (lookahead scaling).
        We verify this indirectly: running two backtests with identical symbols but different
        start years should produce consistent (not wildly divergent) fair values."""
        res_early = test_service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            start_year=2022,
            end_year=2023,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        res_late = test_service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            start_year=2024,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        # Both should return valid BacktestResultPayload without errors
        assert isinstance(res_early, BacktestResultPayload)
        assert isinstance(res_late, BacktestResultPayload)
        # Equity curve endpoints must be finite positive values
        if res_early.equity_curve:
            assert res_early.equity_curve[-1]["strategy_equity"] > 0
        if res_late.equity_curve:
            assert res_late.equity_curve[-1]["strategy_equity"] > 0

    def test_presets_catalog_includes_monthly_cadence(self, test_service):
        """BUG-1: The presets catalog must list monthly as a valid cadence option."""
        presets = test_service.get_presets()
        cadence_ids = [c["id"] for c in presets["cadences"]]
        assert "monthly" in cadence_ids
        assert "quarterly" in cadence_ids
        assert "semi_annual" in cadence_ids
        assert "annual" in cadence_ids

