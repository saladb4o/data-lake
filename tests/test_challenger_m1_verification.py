"""
=============================================================================
CHALLENGER EMPIRICAL VERIFICATION HARNESS: MILESTONE M1
=============================================================================
Empirical validation and stress tests for:
1. Trade holding days calculation (exact date diff vs quarterly block)
2. Early Stop-Loss (SL) and Take-Profit (TP) triggers & tiebreak behavior
3. Screening mode TP decoupling vs Valuation mode TP bounds
4. Equity curve timestamps strict monotonicity and chronological ordering
5. Equity curve lifespan amortization (strict termination on early exit)
6. Metrics strict numeric sanity (CAGR, MDD, Sharpe, Sortino, Calmar, Win Rate, Profit Factor)
7. Multi-cadence timeline forward settlement without lookbehind
8. JSON serialization safety (no NaN / Inf)
"""

import math
import json
import pytest
from datetime import datetime
from typing import List, Dict, Any

from services.fair_value_backtest_service import (
    FairValueBacktestService,
    BacktestMode,
    BacktestResultPayload,
    TradeRecord,
    _build_quarterly_equity_curve,
    _compute_beta_and_alpha,
    _compute_benchmark_mdd,
    VALUATION_MODELS_CATALOG,
)
from services.backtest_service import QUARTERS_TIMELINE


@pytest.fixture(scope="module")
def engine() -> FairValueBacktestService:
    return FairValueBacktestService()


# =============================================================================
# 1. TRADE HOLDING DAYS VERIFICATION
# =============================================================================

class TestTradeHoldingDays:
    """Empirical verification of trade holding days across all exit scenarios."""

    def test_holding_days_strictly_positive_for_all_trades(self, engine):
        """Holding days must be > 0 for all generated trades across all modes."""
        for mode in [BacktestMode.VALUATION_ONLY, BacktestMode.SCREENING_ONLY, BacktestMode.HYBRID_FUNNEL]:
            res = engine.run_backtest(
                mode=mode,
                start_year=2021,
                end_year=2025,
                custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
            )
            assert res.metrics["total_trades"] >= 0
            for trade in res.trades:
                assert trade["holding_days"] > 0, f"Trade {trade['symbol']} has invalid holding_days: {trade['holding_days']}"
                assert isinstance(trade["holding_days"], int)

    def test_holding_days_date_diff_consistency(self, engine):
        """Holding days must equal calendar day difference between entry and exit (or 90d min block)."""
        res = engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG", "DGC", "SSI"],
        )
        for trade in res.trades:
            d_in = datetime.strptime(trade["entry_date"], "%Y-%m-%d")
            d_out = datetime.strptime(trade["exit_date"], "%Y-%m-%d")
            expected_diff = (d_out - d_in).days
            if expected_diff > 0:
                assert trade["holding_days"] == expected_diff
            else:
                # Same-quarter exit defaults to 90 days
                assert trade["holding_days"] >= 90

    def test_holding_days_early_tp_vs_holding_expiry(self, engine):
        """Trades with early TAKE_PROFIT must have holding_days <= nominal holding period."""
        res = engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            exit_premium_pct=5.0,  # low TP threshold encourages early TP
            holding_period_months=24,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        nominal_max_days = 24 * 30 + 60  # ~780 days
        for trade in res.trades:
            assert trade["holding_days"] <= nominal_max_days
            if trade["exit_reason"] == "TAKE_PROFIT":
                assert trade["holding_days"] > 0

    def test_holding_days_early_stop_loss(self, engine):
        """Trades stopped out early must record holding_days reflective of the trigger quarter."""
        res = engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            exit_premium_pct=200.0,  # high TP ensures exits are either SL or EXPIRY
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
        )
        sl_trades = [t for t in res.trades if t["exit_reason"] == "STOP_LOSS"]
        for trade in sl_trades:
            assert trade["holding_days"] > 0
            d_in = datetime.strptime(trade["entry_date"], "%Y-%m-%d")
            d_out = datetime.strptime(trade["exit_date"], "%Y-%m-%d")
            assert d_out >= d_in


# =============================================================================
# 2. EARLY STOP-LOSS & TAKE-PROFIT TRIGGERS
# =============================================================================

class TestStopLossTakeProfitTriggers:
    """Stress tests on SL/TP mechanics, boundary conditions, and mode decoupling."""

    def test_stop_loss_trigger_price_level(self, engine):
        """STOP_LOSS exit price must strictly equal p_in * 0.82."""
        res = engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
        )
        sl_trades = [t for t in res.trades if t["exit_reason"] == "STOP_LOSS"]
        for trade in sl_trades:
            expected_sl_price = round(trade["entry_price"] * 0.82, 2)
            assert abs(trade["exit_price"] - expected_sl_price) <= 0.05

    def test_screening_mode_tp_decoupling_from_fair_value(self, engine):
        """In SCREENING_ONLY mode, TP target price must be based on p_in * (1 + exit_premium_pct/100), not FV."""
        res = engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            exit_premium_pct=15.0,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
        )
        tp_trades = [t for t in res.trades if t["exit_reason"] == "TAKE_PROFIT"]
        for trade in tp_trades:
            expected_tp = round(trade["entry_price"] * 1.15, 2)
            assert abs(trade["exit_price"] - expected_tp) <= 0.05

    def test_valuation_mode_tp_bound_by_fair_value(self, engine):
        """In VALUATION_ONLY mode when FV > p_in, TP target price respects FV bounds."""
        res = engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            exit_premium_pct=20.0,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
        )
        tp_trades = [t for t in res.trades if t["exit_reason"] == "TAKE_PROFIT"]
        for trade in tp_trades:
            p_in = trade["entry_price"]
            fv = trade["entry_fair_value"]
            if fv > p_in:
                target_tp = min(p_in * 1.20, fv * 1.10)
                assert abs(trade["exit_price"] - target_tp) <= 0.05


# =============================================================================
# 3. EQUITY CURVE AMORTIZATION & TIMESTAMPS MONOTONICITY
# =============================================================================

class TestEquityCurveAmortizationAndTimestamps:
    """Stress tests on equity curve amortization logic, timestamp monotonicity, and quarter alignment."""

    def test_equity_curve_timestamps_strictly_monotonic(self, engine):
        """Timestamps in equity_curve must be in strict chronological order with no duplicates."""
        res = engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            start_year=2021,
            end_year=2026,
            custom_symbols=["HPG", "FPT", "VCB", "MBB", "MWG"],
        )
        eq = res.equity_curve
        assert len(eq) > 1
        dates = [datetime.strptime(pt["date"], "%Y-%m-%d") for pt in eq]
        for i in range(1, len(dates)):
            assert dates[i] > dates[i - 1], f"Timestamp monotonicity violated: {dates[i]} <= {dates[i-1]}"

    def test_equity_curve_exact_quarter_count(self, engine):
        """Equity curve points must exactly match the number of quarters in the active timeline."""
        for start_y, end_y in [(2024, 2025), (2022, 2025), (2021, 2026)]:
            expected_timeline = [q for q in QUARTERS_TIMELINE if start_y <= q["year"] <= end_y]
            res = engine.run_backtest(
                mode=BacktestMode.SCREENING_ONLY,
                start_year=start_y,
                end_year=end_y,
                custom_symbols=["HPG", "FPT"],
            )
            assert len(res.equity_curve) == len(expected_timeline)
            for i, pt in enumerate(res.equity_curve):
                assert pt["date"] == expected_timeline[i]["date"]

    def test_isolated_early_exit_amortization_termination(self):
        """Empirical direct test of _build_quarterly_equity_curve amortization termination.

        A trade entering at Q0 (2021-03-31) and exiting early at Q1 (2021-06-30)
        with +21% return must contribute ONLY to Q0 and Q1.
        Q2 and Q3 must receive ZERO contribution from this trade.
        """
        timeline = [
            {"code": "2021-Q1", "date": "2021-03-31", "year": 2021, "vni_return_pct": 0.0},
            {"code": "2021-Q2", "date": "2021-06-30", "year": 2021, "vni_return_pct": 0.0},
            {"code": "2021-Q3", "date": "2021-09-30", "year": 2021, "vni_return_pct": 0.0},
            {"code": "2021-Q4", "date": "2021-12-31", "year": 2021, "vni_return_pct": 0.0},
        ]
        # 21% net return over 2 quarters -> (1 + 0.21)^(1/2) - 1 = 10% per quarter
        trade_early_exit = TradeRecord(
            symbol="HPG",
            entry_date="2021-03-31",
            entry_price=30000.0,
            exit_date="2021-06-30",
            exit_price=36300.0,
            return_pct=21.0,
            holding_days=91,
            entry_fair_value=40000.0,
            entry_mos_pct=20.0,
            exit_reason="TAKE_PROFIT",
            model_name="test_model",
        )
        curve = _build_quarterly_equity_curve(
            timeline_quarters=timeline,
            all_closed_trades=[trade_early_exit],
            initial_capital=100_000_000.0,
            holding_period_months=12,  # nominal horizon is 4 quarters
        )
        assert len(curve) == 4

        # Q0: 100M * 1.10 = 110M
        assert abs(curve[0]["strategy_equity"] - 110_000_000.0) < 1.0
        # Q1: 110M * 1.10 = 121M
        assert abs(curve[1]["strategy_equity"] - 121_000_000.0) < 1.0
        # Q2: trade closed! 121M * 1.00 = 121M (0 return contribution)
        assert abs(curve[2]["strategy_equity"] - 121_000_000.0) < 1.0
        # Q3: trade closed! 121M * 1.00 = 121M (0 return contribution)
        assert abs(curve[3]["strategy_equity"] - 121_000_000.0) < 1.0

    def test_amortization_maximum_loss_guard(self):
        """Direct test: a -100% loss trade must not trigger math errors (e.g. 0^(1/n) or complex)."""
        timeline = [
            {"code": "2021-Q1", "date": "2021-03-31", "year": 2021, "vni_return_pct": 0.0},
            {"code": "2021-Q2", "date": "2021-06-30", "year": 2021, "vni_return_pct": 0.0},
        ]
        trade_total_loss = TradeRecord(
            symbol="XYZ",
            entry_date="2021-03-31",
            entry_price=30000.0,
            exit_date="2021-06-30",
            exit_price=0.0,
            return_pct=-100.0,
            holding_days=91,
            entry_fair_value=10000.0,
            entry_mos_pct=20.0,
            exit_reason="STOP_LOSS",
            model_name="test_model",
        )
        curve = _build_quarterly_equity_curve(
            timeline_quarters=timeline,
            all_closed_trades=[trade_total_loss],
            initial_capital=100_000_000.0,
            holding_period_months=6,
        )
        assert len(curve) == 2
        for pt in curve:
            assert math.isfinite(pt["strategy_equity"])
            assert pt["strategy_equity"] > 0.0
            assert pt["drawdown_pct"] <= 0.0


# =============================================================================
# 4. STRICT NUMERIC SANITY & EDGE CASES (NO NaN, NO Inf)
# =============================================================================

class TestNumericMetricsSanity:
    """Stress tests verifying all metrics are strictly finite and numeric under all edge cases."""

    def test_zero_trades_produces_finite_metrics(self, engine):
        """When 0 trades are generated, all metrics must be strictly finite (no NaN, no Inf)."""
        res = engine.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            margin_of_safety_pct=99.0,
            start_year=2024,
            end_year=2025,
        )
        m = res.metrics
        required_numeric_keys = [
            "total_return_pct", "cagr_pct", "benchmark_total_return_pct", "benchmark_cagr_pct",
            "excess_cagr_pct", "max_drawdown_pct", "benchmark_max_drawdown_pct", "sharpe_ratio",
            "sortino_ratio", "calmar_ratio", "win_rate_pct", "profit_factor", "total_trades",
            "winning_trades", "losing_trades", "avg_trade_return_pct", "avg_holding_days",
            "alpha_pct", "beta"
        ]
        for k in required_numeric_keys:
            assert k in m, f"Missing metric key: {k}"
            val = m[k]
            assert isinstance(val, (int, float)), f"Metric {k} is not numeric: {val} ({type(val)})"
            assert math.isfinite(val), f"Metric {k} is not finite: {val}"

    def test_single_trade_metric_sanity(self, engine):
        """A run with only 1 trade must not crash on sample variance (ddof=1) or division by zero."""
        res = engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            top_k=1,
            start_year=2025,
            end_year=2025,
            custom_symbols=["HPG"],
        )
        m = res.metrics
        assert math.isfinite(m["sharpe_ratio"])
        assert math.isfinite(m["sortino_ratio"])
        assert math.isfinite(m["calmar_ratio"])
        assert math.isfinite(m["profit_factor"])
        assert math.isfinite(m["beta"])
        assert math.isfinite(m["alpha_pct"])

    def test_json_serialization_strict_sanity(self, engine):
        """to_dict() and json.dumps() must succeed with zero NaN/Inf occurrences."""
        res = engine.run_backtest(
            mode=BacktestMode.HYBRID_FUNNEL,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB"],
        )
        d = res.to_dict()
        assert isinstance(d, dict)
        raw_json = json.dumps(d)
        assert "NaN" not in raw_json
        assert "Infinity" not in raw_json
        assert "-Infinity" not in raw_json


# =============================================================================
# 5. MULTI-CADENCE TIMELINE FORWARD SETTLEMENT
# =============================================================================

class TestCadenceForwardSettlement:
    """Stress tests on cadence stepping to verify forward settlement with zero lookbehind."""

    @pytest.mark.parametrize("cadence", ["quarterly", "semi_annual", "annual", "monthly"])
    def test_cadence_temporal_forward_direction(self, engine, cadence):
        """All trades generated under any cadence must settle forward in time."""
        res = engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence=cadence,
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT", "VCB", "MBB"],
        )
        for trade in res.trades:
            d_in = datetime.strptime(trade["entry_date"], "%Y-%m-%d")
            d_out = datetime.strptime(trade["exit_date"], "%Y-%m-%d")
            assert d_out >= d_in, f"Lookbehind detected in {cadence}: entry {d_in} > exit {d_out}"
            assert int(trade["entry_date"][:4]) >= 2021
            assert int(trade["exit_date"][:4]) >= 2021

    def test_annual_cadence_step_index_alignment(self, engine):
        """Annual cadence (step=4) over 5 years produces rebalance rounds spaced by 4 quarters."""
        res = engine.run_backtest(
            mode=BacktestMode.SCREENING_ONLY,
            rebalance_cadence="annual",
            start_year=2021,
            end_year=2025,
            custom_symbols=["HPG", "FPT"],
        )
        entry_dates = set(t["entry_date"] for t in res.trades)
        # 5-year timeline with annual cadence -> entries should only be in Q1 of each year
        for ed in entry_dates:
            assert ed.endswith("-03-31"), f"Annual entry date not aligned to Q1: {ed}"
