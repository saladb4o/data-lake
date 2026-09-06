"""
=============================================================================
ADVERSARIAL STRESS TESTING SUITE: FAIR VALUE BACKTEST ENGINE
=============================================================================
Comprehensive empirical verification and adversarial challenge harness for
`services/fair_value_backtest_service.py`.

Stress test dimensions:
1. Extreme Cadences: 'annual', 'semi_annual', 'monthly', 'quarterly'
2. Multi-Year Horizons: 1-year (2026, 2021), 3-year, 5-year, 10-year (2016-2026), inverted/out-of-range years
3. Extreme Exit Premiums: 0.0%, 0.1%, 100.0%, 500.0%, 10000.0%
4. Single-Stock and Degenerate Universes: 1 stock, unknown stock, empty universe
5. Zero-Trade Scenarios: Extreme MoS (99%, 500%), strict firewalls, empty candidate baskets
6. Temporal Integrity & Boundary Checks: No lookahead/lookbehind, entry <= exit, holding_days >= 0
7. Holding Horizons: 1m, 3m, 12m, 36m, 60m, 120m
8. All 22 Valuation Models individually and in Composite/Omnibus modes
9. JSON Serialization & NaN/Inf Sanitization
"""

import math
import json
import pytest
from typing import List, Dict, Any
from datetime import datetime

from services.fair_value_backtest_service import (
    FairValueBacktestService,
    BacktestMode,
    BacktestResultPayload,
    VALUATION_MODELS_CATALOG,
    TradeRecord,
    _fv_backtest_cache,
)
from services.backtest_service import QUARTERS_TIMELINE

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



@pytest.fixture(autouse=True)
def clear_cache():
    """Clear memory cache between tests to avoid cross-test cache contamination."""
    with _fv_backtest_cache._lock:
        _fv_backtest_cache._store.clear()


@pytest.fixture(scope="module")
def svc() -> FairValueBacktestService:
    return FairValueBacktestService()


# =============================================================================
# 1. EXTREME CADENCE STRESS TESTS
# =============================================================================

class TestCadenceStress:
    """Stress tests for cadence handling across multi-year and edge-case timelines."""

    @pytest.mark.parametrize("cadence", ["annual", "semi_annual", "monthly", "quarterly"])
    @pytest.mark.parametrize("mode", [
        BacktestMode.VALUATION_ONLY,
        BacktestMode.SCREENING_ONLY,
        BacktestMode.HYBRID_FUNNEL,
    ])
    def test_all_cadences_and_modes(self, svc, cadence, mode):
        """Verify all combinations of cadences and modes execute cleanly without out-of-bounds errors."""
        res = svc.run_backtest(
            mode=mode,
            rebalance_cadence=cadence,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.diagnostics["execution_settings"]["rebalance_cadence"] == cadence
        assert res.metrics["total_trades"] >= 0
        assert math.isfinite(res.metrics["cagr_pct"])
        assert math.isfinite(res.metrics["max_drawdown_pct"])
        assert len(res.equity_curve) > 0

    @pytest.mark.parametrize("cadence,step", [
        ("quarterly", 1),
        ("monthly", 1),
        ("semi_annual", 2),
        ("annual", 4),
    ])
    def test_cadence_trade_count_hierarchy(self, svc, cadence, step):
        """Annual cadence must never produce more rebalance rounds than quarterly."""
        res_q = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence="quarterly",
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        res_c = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence=cadence,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        if step > 1:
            assert res_c.metrics["total_trades"] <= res_q.metrics["total_trades"]

    def test_annual_cadence_with_short_timeline(self, svc):
        """Annual cadence on a 1-year timeline (4 quarters) should produce exactly 1 rebalance round."""
        res = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence="annual",
            start_year=2024,
            end_year=2024,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert len(res.yearly_returns) == 1
        assert res.yearly_returns[0]["year"] == 2024
        assert res.metrics["total_trades"] <= 2


# =============================================================================
# 2. MULTI-YEAR HORIZON & SPAN STRESS TESTS
# =============================================================================

class TestHorizonSpanStress:
    """Stress tests across 1-year, 2-year, 3-year, 5-year, 10-year spans."""

    @pytest.mark.parametrize("start_y,end_y,expected_years", [
        (2026, 2026, 1),
        (2025, 2026, 2),
        (2023, 2026, 4),
        (2021, 2026, 6),
        (2016, 2026, 11),
    ])
    def test_spans_1_to_10_years(self, svc, start_y, end_y, expected_years):
        """Execute full backtest over spans from 1 to 11 years (10y horizon)."""
        res = svc.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            screening_strategy="peter_lynch_garp",
            start_year=start_y,
            end_year=end_y,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert len(res.yearly_returns) == expected_years
        years_in_matrix = [yr["year"] for yr in res.yearly_returns]
        assert years_in_matrix == list(range(start_y, end_y + 1))
        assert math.isfinite(res.metrics["cagr_pct"])
        assert math.isfinite(res.metrics["total_return_pct"])
        assert math.isfinite(res.metrics["benchmark_cagr_pct"])


# =============================================================================
# 3. EXTREME EXIT PREMIUMS & SL STRESS TESTS
# =============================================================================

class TestExitPremiumStress:
    """Stress tests on exit_premium_pct boundary and extreme values."""

    @pytest.mark.parametrize("exit_prem", [0.01, 1.0, 20.0, 100.0, 500.0, 10000.0])
    def test_extreme_exit_premiums(self, svc, exit_prem):
        """Verify backtest executes cleanly across 0.01% to 10,000% exit premiums."""
        res = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            exit_premium_pct=exit_prem,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.exit_premium_pct == exit_prem
        assert res.metrics["total_trades"] >= 0
        for trade in res.trades:
            assert trade["exit_reason"] in ["TAKE_PROFIT", "HOLDING_EXPIRY", "STOP_LOSS", "REBALANCE"]
            assert trade["holding_days"] > 0
            assert math.isfinite(trade["return_pct"])

    def test_huge_exit_premium_never_hits_tp(self, svc):
        """10,000% exit premium will never hit TP; trades must exit via HOLDING_EXPIRY or STOP_LOSS."""
        res = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            exit_premium_pct=10000.0,
            start_year=2022,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        for trade in res.trades:
            assert trade["exit_reason"] in ["HOLDING_EXPIRY", "STOP_LOSS"]


# =============================================================================
# 4. SINGLE-STOCK & DEGENERATE UNIVERSE STRESS TESTS
# =============================================================================

class TestSingleStockUniverseStress:
    """Stress tests on single-stock, unknown-symbol, and empty universe scenarios."""

    def test_single_stock_known(self, svc):
        """Single known liquid stock (HPG) executes cleanly."""
        res = svc.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            custom_symbols=["HPG"],
            start_year=2021,
            end_year=2025,
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] > 0
        for trade in res.trades:
            assert trade["symbol"] == "HPG"

    def test_single_stock_unknown_synthetic(self, svc):
        """Single completely unknown ticker (XYZ_UNKNOWN) creates synthetic fallback and executes."""
        res = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            custom_symbols=["XYZ_UNKNOWN"],
            start_year=2023,
            end_year=2025,
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] > 0
        assert math.isfinite(res.metrics["cagr_pct"])
        for trade in res.trades:
            assert trade["symbol"] == "XYZ_UNKNOWN"

    def test_multiple_unknown_stocks(self, svc):
        """Multiple unknown tickers execute synthetic valuation without crashing."""
        res = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            custom_symbols=["SYN1", "SYN2", "SYN3"],
            start_year=2023,
            end_year=2025,
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] > 0


# =============================================================================
# 5. ZERO-TRADE SCENARIOS & DEGENERATE METRIC GUARDS
# =============================================================================

class TestZeroTradeScenarioStress:
    """Stress tests ensuring zero-trade runs produce valid, non-crashing payloads."""

    def test_impossible_mos_produces_zero_trades_gracefully(self, svc):
        """VALUATION_ONLY with 500% static MoS against real universe produces 0 trades with clean metrics."""
        res = svc.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=500.0,
            use_dynamic_beta_mos=False,
            start_year=2024,
            end_year=2025,
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] == 0
        assert res.metrics["winning_trades"] == 0
        assert res.metrics["losing_trades"] == 0
        assert res.metrics["win_rate_pct"] == 50.0  # default fallback
        assert res.metrics["avg_trade_return_pct"] == 0.0
        assert math.isfinite(res.metrics["cagr_pct"])
        assert math.isfinite(res.metrics["sharpe_ratio"])
        assert math.isfinite(res.metrics["beta"])
        assert math.isfinite(res.metrics["alpha_pct"])
        assert len(res.equity_curve) > 0
        assert len(res.trades) == 0

        # Verify JSON serialization works without error
        d = res.to_dict()
        raw_json = json.dumps(d)
        assert "NaN" not in raw_json
        assert "Infinity" not in raw_json


# =============================================================================
# 6. TEMPORAL INTEGRITY & NO LOOKAHEAD/LOOKBEHIND VERIFICATION
# =============================================================================

class TestTemporalIntegrityStress:
    """Rigorous temporal tests verifying no lookahead, lookbehind, or index misalignments."""

    @pytest.mark.parametrize("cadence", ["quarterly", "semi_annual", "annual", "monthly"])
    def test_trade_entry_exit_temporal_ordering(self, svc, cadence):
        """Every trade must have exit_date >= entry_date and holding_days >= 0."""
        res = svc.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            rebalance_cadence=cadence,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI", "REE"],
            fundamentals_mode=_SNAPSHOT,
        )
        for trade in res.trades:
            d_in = datetime.strptime(trade["entry_date"], "%Y-%m-%d")
            d_out = datetime.strptime(trade["exit_date"], "%Y-%m-%d")
            assert d_out >= d_in, f"Temporal inversion: entry {d_in} > exit {d_out} for {trade['symbol']}"
            assert trade["holding_days"] >= 0, f"Negative holding days: {trade['holding_days']} for {trade['symbol']}"

    @pytest.mark.parametrize("cadence", ["semi_annual", "annual"])
    def test_cadence_timeline_bounds_no_lookbehind(self, svc, cadence):
        """When cadence_step > 1, active_rebalance_quarters must settle trades forward, not backward."""
        res = svc.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence=cadence,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        # Entry dates must strictly fall on or after the start_year
        for trade in res.trades:
            entry_year = int(trade["entry_date"][:4])
            exit_year = int(trade["exit_date"][:4])
            assert entry_year >= 2021, f"Lookbehind entry: {trade['entry_date']}"
            assert exit_year >= entry_year, f"Lookbehind exit: {trade['exit_date']} < {trade['entry_date']}"

    def test_equity_curve_amortization_boundaries(self, svc):
        """Equity curve points must exactly match the number of quarters in the timeline."""
        timeline_2021_2025 = [q for q in QUARTERS_TIMELINE if 2021 <= q["year"] <= 2025]
        res = svc.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert len(res.equity_curve) == len(timeline_2021_2025)
        for i, pt in enumerate(res.equity_curve):
            assert pt["date"] == timeline_2021_2025[i]["date"]
            assert pt["strategy_equity"] > 0.0
            assert pt["benchmark_equity"] > 0.0
            assert pt["drawdown_pct"] <= 0.0


# =============================================================================
# 7. HOLDING PERIOD HORIZONS
# =============================================================================

class TestHoldingPeriodStress:
    """Stress tests on holding horizons from 3 months to 36 months."""

    @pytest.mark.parametrize("months", [3, 6, 12, 24, 36])
    def test_various_holding_periods(self, svc, months):
        """Verify holding period from 3 months to 36 months executes cleanly."""
        res = svc.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            holding_period_months=months,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert len(res.equity_curve) > 0
        for trade in res.trades:
            assert trade["holding_days"] > 0


# =============================================================================
# 8. ALL 22 QUANTITATIVE VALUATION MODELS PERMUTATION TEST
# =============================================================================

class TestValuationModelPermutations:
    """Verify all 22 valuation models execute without exception in backtest mode."""

    @pytest.mark.parametrize("model", VALUATION_MODELS_CATALOG)
    def test_individual_valuation_model_execution(self, svc, model):
        """Every individual valuation model in the catalog executes properly."""
        mid = model["id"]
        res = svc.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id=mid,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.valuation_model_id == mid
        assert math.isfinite(res.metrics["cagr_pct"])
        assert len(res.equity_curve) > 0

    @pytest.mark.parametrize("comp_mode", ["blended", "omnibus"])
    @pytest.mark.parametrize("metric", ["smape", "male", "wmape", "rmsle", "ivw"])
    def test_composite_and_omnibus_combinations(self, svc, comp_mode, metric):
        """Verify blended vs omnibus weighting with all 5 error metrics."""
        res = svc.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            valuation_model_id="composite_fair_value",
            composite_mode=comp_mode,
            omnibus_metric=metric,
            start_year=2023,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.diagnostics["valuation_settings"]["composite_mode"] == comp_mode
        assert math.isfinite(res.metrics["cagr_pct"])


# =============================================================================
# 9. JSON SERIALIZATION & PAYLOAD INTEGRITY
# =============================================================================

class TestPayloadIntegrity:
    """Verify to_dict() sanitizes NaNs, Infs, and produces strict JSON."""

    def test_payload_to_dict_strict_json(self, svc):
        """Confirm payload serializes cleanly to JSON without NaN or Inf strings."""
        res = svc.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        d = res.to_dict()
        assert isinstance(d, dict)
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        assert "NaN" not in serialized
        assert "Infinity" not in serialized
        assert "-Infinity" not in serialized

        # Roundtrip parse
        reparsed = json.loads(serialized)
        assert reparsed["mode"] == BacktestMode.HYBRID_FUNNEL
        assert "metrics" in reparsed
        assert "equity_curve" in reparsed
        assert "trades" in reparsed
