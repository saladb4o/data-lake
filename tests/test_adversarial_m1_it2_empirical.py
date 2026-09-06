"""
=============================================================================
EMPIRICAL CHALLENGER VERIFICATION HARNESS: MILESTONE M1 ITERATION 2
=============================================================================
Adversarial validation targeting the 5 specific remediations reported by Challenger 1:
1. Inverted and out-of-range timeline years (no KeyError: 2021, valid timeline derivation)
2. Cache key partitioning by holding_period_months and initial_capital (zero cross-contamination)
3. Zero exit premium (exit_premium_pct=0.0) take-profit triggering
4. Proportional dynamic beta Margin of Safety scaling with user margin_of_safety_pct
5. Metric avg_holding_days strict equivalence with empirical trade holding_days mean
"""

import math
import json
import pytest
import numpy as np
from datetime import datetime
from typing import List, Dict, Any

from services.fair_value_backtest_service import (
    FairValueBacktestService,
    BacktestMode,
    BacktestResultPayload,
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
def clean_cache():
    """Ensure cache is reset between test cases."""
    with _fv_backtest_cache._lock:
        _fv_backtest_cache._store.clear()


@pytest.fixture(scope="module")
def service() -> FairValueBacktestService:
    return FairValueBacktestService()


# =============================================================================
# DEFECT 1: INVERTED & OUT-OF-RANGE TIMELINE YEARS
# =============================================================================

class TestInvertedYearsAndBounds:
    """Validate that inverted, swapped, and out-of-range year bounds execute with zero KeyError."""

    @pytest.mark.parametrize("start_y,end_y", [
        (2026, 2021),
        (2025, 2022),
        (2024, 2021),
        (2023, 2021),
        (2026, 2024),
        (2030, 2020),
        (1995, 2000),
        (2050, 2040),
    ])
    @pytest.mark.parametrize("mode", [
        BacktestMode.VALUATION_ONLY,
        BacktestMode.SCREENING_ONLY,
        BacktestMode.HYBRID_FUNNEL,
    ])
    def test_inverted_years_no_keyerror(self, service, start_y, end_y, mode):
        """Inverted start_year > end_year must execute cleanly without KeyError."""
        res = service.run_backtest(
            mode=mode,
            start_year=start_y,
            end_year=end_y,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert isinstance(res, BacktestResultPayload)
        assert res.metrics["total_trades"] >= 0
        assert math.isfinite(res.metrics["cagr_pct"])
        assert math.isfinite(res.metrics["total_return_pct"])
        assert len(res.equity_curve) > 0
        assert len(res.yearly_returns) > 0

        # Verify yearly_returns years are monotonically increasing
        years = [yr["year"] for yr in res.yearly_returns]
        assert years == sorted(years)
        for yr in res.yearly_returns:
            assert math.isfinite(yr["strategy_return_pct"])
            assert math.isfinite(yr["benchmark_return_pct"])
            assert math.isfinite(yr["excess_return_pct"])

    def test_inverted_years_produces_identical_result_to_normalized_range(self, service):
        """start_year=2026, end_year=2021 should produce identical payload to start_year=2021, end_year=2026."""
        res_inverted = service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2026,
            end_year=2021,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        # Clear cache to ensure independent computation
        with _fv_backtest_cache._lock:
            _fv_backtest_cache._store.clear()

        res_normal = service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2021,
            end_year=2026,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res_inverted.metrics["total_trades"] == res_normal.metrics["total_trades"]
        assert res_inverted.metrics["total_return_pct"] == res_normal.metrics["total_return_pct"]
        assert res_inverted.metrics["cagr_pct"] == res_normal.metrics["cagr_pct"]
        assert len(res_inverted.trades) == len(res_normal.trades)
        assert len(res_inverted.equity_curve) == len(res_normal.equity_curve)


# =============================================================================
# DEFECT 2: CACHE KEY PARTITIONING BY HOLDING_PERIOD & INITIAL_CAPITAL
# =============================================================================

class TestCacheKeyPartitioning:
    """Validate that differing holding_period_months and initial_capital generate separate cache entries."""

    def test_holding_period_cache_isolation(self, service):
        """Holding period 12 vs 120 must yield different cache slots and accurate payload attributes."""
        res_12 = service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            holding_period_months=12,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        res_120 = service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            holding_period_months=120,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        # Verify payloads reflect their respective requested parameters
        assert res_12.holding_period_months == 12
        assert res_120.holding_period_months == 120

        # Verify holding_period_months is preserved when fetching from cache
        res_12_cached = service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            holding_period_months=12,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res_12_cached.holding_period_months == 12

    def test_initial_capital_cache_isolation(self, service):
        """Initial capital 100M vs 500M must yield separate cache slots and scaled equity curves."""
        res_100m = service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            initial_capital=100_000_000.0,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        res_500m = service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            initial_capital=500_000_000.0,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res_500m.equity_curve[0]["strategy_equity"] != res_100m.equity_curve[0]["strategy_equity"]
        assert abs(res_500m.equity_curve[0]["strategy_equity"] / res_100m.equity_curve[0]["strategy_equity"] - 5.0) < 0.01

        # Re-fetching 100M from cache returns the 100M-based curve, not contaminated by 500M
        res_100m_cached = service.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            initial_capital=100_000_000.0,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert abs(res_100m_cached.equity_curve[0]["strategy_equity"] - res_100m.equity_curve[0]["strategy_equity"]) < 1.0


# =============================================================================
# DEFECT 3: ZERO EXIT PREMIUM (0.0%) TAKE-PROFIT TRIGGERING
# =============================================================================

class TestZeroExitPremiumTakeProfit:
    """Validate that exit_premium_pct=0.0 triggers TAKE_PROFIT when price >= p_in."""

    def test_zero_exit_premium_triggers_tp_in_screening_mode(self, service):
        """In SCREENING_ONLY with exit_premium_pct=0.0, any bar with high >= p_in triggers TAKE_PROFIT."""
        res = service.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            exit_premium_pct=0.0,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res.exit_premium_pct == 0.0
        assert res.metrics["total_trades"] > 0
        tp_trades = [t for t in res.trades if t["exit_reason"] == "TAKE_PROFIT"]
        assert len(tp_trades) > 0, "No TAKE_PROFIT trades triggered when exit_premium_pct=0.0"

        for trade in tp_trades:
            # TP target price is p_in * (1 + 0/100) = p_in
            assert abs(trade["exit_price"] - trade["entry_price"]) <= 0.05
            assert trade["holding_days"] > 0

    def test_zero_exit_premium_triggers_tp_in_valuation_mode(self, service):
        """In VALUATION_ONLY with exit_premium_pct=0.0, TAKE_PROFIT triggers properly."""
        res = service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            exit_premium_pct=0.0,
            margin_of_safety_pct=10.0,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res.exit_premium_pct == 0.0
        tp_trades = [t for t in res.trades if t["exit_reason"] == "TAKE_PROFIT"]
        assert len(tp_trades) > 0, "No TAKE_PROFIT trades triggered in VALUATION_ONLY with exit_premium_pct=0.0"


# =============================================================================
# DEFECT 4: DYNAMIC BETA MARGIN OF SAFETY PROPORTIONAL SCALING
# =============================================================================

class TestDynamicBetaMoSScaling:
    """Validate that use_dynamic_beta_mos=True scales proportionally with user margin_of_safety_pct."""

    def test_extreme_mos_with_dynamic_beta_restricts_trades(self, service):
        """Setting margin_of_safety_pct=500.0 with use_dynamic_beta_mos=True must produce 0 or near-0 trades."""
        res_normal = service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=10.0,
            use_dynamic_beta_mos=True,
            start_year=2021,
            end_year=2025,
            fundamentals_mode=_SNAPSHOT,
        )
        res_extreme = service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=500.0,
            use_dynamic_beta_mos=True,
            start_year=2021,
            end_year=2025,
            fundamentals_mode=_SNAPSHOT,
        )
        assert res_normal.metrics["total_trades"] > 0
        assert res_extreme.metrics["total_trades"] == 0, (
            f"Expected 0 trades with 500% dynamic MoS, got {res_extreme.metrics['total_trades']}"
        )

    def test_monotonic_trade_count_with_increasing_mos(self, service):
        """As margin_of_safety_pct increases from 5% to 50% with dynamic beta, trade count should decrease or stay equal."""
        trade_counts = []
        for mos in [5.0, 15.0, 25.0, 40.0, 60.0]:
            res = service.run_backtest(
                mode=BacktestMode.VALUATION_ONLY,
                margin_of_safety_pct=mos,
                use_dynamic_beta_mos=True,
                start_year=2021,
                end_year=2025,
                fundamentals_mode=_SNAPSHOT,
            )
            trade_counts.append(res.metrics["total_trades"])

        # Trade counts must be monotonically non-increasing
        for i in range(1, len(trade_counts)):
            assert trade_counts[i] <= trade_counts[i - 1], (
                f"Trade count increased from {trade_counts[i-1]} to {trade_counts[i]} with higher MoS"
            )


# =============================================================================
# DEFECT 5: AVG_HOLDING_DAYS EMPIRICAL MEAN EQUIVALENCE
# =============================================================================

class TestAvgHoldingDaysCalculation:
    """Validate that BacktestMetrics.avg_holding_days strictly equals empirical mean of trade holding_days."""

    @pytest.mark.parametrize("mode", [
        BacktestMode.VALUATION_ONLY,
        BacktestMode.SCREENING_ONLY,
        BacktestMode.HYBRID_FUNNEL,
    ])
    def test_avg_holding_days_matches_trade_mean(self, service, mode):
        """BacktestMetrics.avg_holding_days must equal mean([t.holding_days for t in trades])."""
        res = service.run_backtest(
            mode=mode,
            holding_period_months=24,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC"],
            fundamentals_mode=_SNAPSHOT,
        )
        assert res.metrics["total_trades"] >= 0
        if res.trades:
            trade_days = [t["holding_days"] for t in res.trades]
            empirical_mean = round(float(np.mean(trade_days)), 1)
            reported_mean = res.metrics["avg_holding_days"]

            assert abs(reported_mean - empirical_mean) <= 0.1, (
                f"avg_holding_days discrepancy: reported {reported_mean} vs empirical {empirical_mean}"
            )

    def test_avg_holding_days_zero_trades_fallback(self, service):
        """When 0 trades exist, avg_holding_days falls back to nominal holding_period_months * 30."""
        res = service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=999.0,
            holding_period_months=18,
            use_dynamic_beta_mos=False,
            start_year=2024,
            end_year=2025,
            fundamentals_mode=_SNAPSHOT,
        )
        assert res.metrics["total_trades"] == 0
        expected_fallback = float(18 * 30)
        assert res.metrics["avg_holding_days"] == expected_fallback
