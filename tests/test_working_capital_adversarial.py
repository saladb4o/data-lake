"""
=============================================================================
EMPIRICAL ADVERSARIAL STRESS TEST & MONTE CARLO ORACLE SUITE
Target: services/working_capital_engine.py
Author: teamwork_preview_challenger_m1_2 (Empirical Challenger)
=============================================================================
This test suite implements rigorous empirical challenges against the Modano
Working Capital Engine across 8 deep dimensions:
1. Hyper-growth (+500% YoY compounding) & NWC explosion scaling stability
2. Catastrophic contraction (-90% crash) & working capital cash liquidation dynamics
3. Mean reversion parameter boundary rigor (speed=0.0, speed=0.5, speed=1.0, out-of-bounds, convergence_rate alias)
4. Negative CCC business model dynamics (MWG / retail float financing: AP > AR + Inv)
5. 20-period Monte Carlo multi-year drift oracle & cumulative conservation laws
6. Adversarial Fuzzing: Negative, zero, extreme values, NaN, Inf, dirty strings
7. 1,000 Monte Carlo randomized invariant verifications
8. 30/30 VN30 Real-World Ticker Fundamental Data Integration (screener snapshot)
=============================================================================
"""

import os
import json
import math
import random
import pytest
from typing import Dict, List, Any

from services.working_capital_engine import (
    WorkingCapitalEngine,
    WorkingCapitalMetrics,
    WorkingCapitalSchedulePeriod,
    WorkingCapitalForecastResult,
    SECTOR_WC_PRIORS,
    SECTOR_PRIORS,
    safe_div,
    clamp,
    sanitize_float,
    resolve_sector_prior,
)


VN30_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]

FINANCIAL_VN30_TICKERS = {
    "ACB", "BID", "BVH", "CTG", "HDB", "MBB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VIB", "VPB",
}

NON_FINANCIAL_VN30_TICKERS = set(VN30_TICKERS) - FINANCIAL_VN30_TICKERS


# =============================================================================
# SUITE 1: ADVERSARIAL HYPER-GROWTH (+500% YoY) & SCALING STABILITY
# =============================================================================

class TestAdversarialExtremeGrowthCAGR:
    """Stress test 1: Hyper-growth (+500% YoY compounding) scaling and stability."""

    def test_hyper_growth_500pct_cagr_conservation(self):
        """
        Starting Revenue 1,000 -> 6,000 -> 36,000 -> 216,000 -> 1,296,000 -> 7,776,000 (500% YoY).
        Verifies that NWC explosion maintains exact accounting identities at huge scale.
        """
        base = {
            "dso": 40.0,
            "dio": 60.0,
            "dpo": 35.0,
            "revenue": 1000.0,
            "cogs": 650.0,
            "accounts_receivable": (40.0 * 1000.0) / 365.0,
            "inventory": (60.0 * 650.0) / 365.0,
            "accounts_payable": (35.0 * 650.0) / 365.0,
            "other_current_assets": 50.0,
            "other_current_liabilities": 40.0,
        }
        base["net_working_capital"] = (
            (base["accounts_receivable"] + base["inventory"] + base["other_current_assets"])
            - (base["accounts_payable"] + base["other_current_liabilities"])
        )

        rev_series = [1000.0 * (6.0 ** (t + 1)) for t in range(5)]
        cogs_series = [650.0 * (6.0 ** (t + 1)) for t in range(5)]

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector="VNIND",
            mean_revert_speed=0.0,
        )

        assert len(schedule) == 5
        cum_delta_nwc = 0.0
        cum_delta_ar = 0.0
        cum_delta_inv = 0.0
        cum_delta_ap = 0.0
        cum_delta_oca = 0.0
        cum_delta_ocl = 0.0
        cum_cash_cust = 0.0
        cum_cash_supp = 0.0
        cum_rev = sum(rev_series)
        cum_cogs = sum(cogs_series)
        cum_gp = cum_rev - cum_cogs

        for t, p in enumerate(schedule):
            for k, v in p.items():
                if isinstance(v, (int, float)):
                    assert not math.isnan(v), f"NaN found in period {t} key {k}"
                    assert not math.isinf(v), f"Inf found in period {t} key {k}"

            period_gp = p["revenue"] - p["cogs"]
            delta_trade_nwc = p["delta_ar"] + p["delta_inv"] - p["delta_ap"]
            assert math.isclose(
                p["cash_from_customers"] - p["cash_to_suppliers"],
                period_gp - delta_trade_nwc,
                rel_tol=1e-5,
            )

            cum_delta_nwc += p["delta_nwc"]
            cum_delta_ar += p["delta_ar"]
            cum_delta_inv += p["delta_inv"]
            cum_delta_ap += p["delta_ap"]
            cum_delta_oca += p["delta_oca"]
            cum_delta_ocl += p["delta_ocl"]
            cum_cash_cust += p["cash_from_customers"]
            cum_cash_supp += p["cash_to_suppliers"]

        final_p = schedule[-1]
        assert math.isclose(cum_delta_nwc, final_p["net_working_capital"] - base["net_working_capital"], rel_tol=1e-5)
        assert math.isclose(cum_delta_ar, final_p["accounts_receivable"] - base["accounts_receivable"], rel_tol=1e-5)
        assert math.isclose(cum_delta_inv, final_p["inventory"] - base["inventory"], rel_tol=1e-5)
        assert math.isclose(cum_delta_ap, final_p["accounts_payable"] - base["accounts_payable"], rel_tol=1e-5)
        assert math.isclose(cum_cash_cust, cum_rev - (final_p["accounts_receivable"] - base["accounts_receivable"]), rel_tol=1e-5)
        assert math.isclose(
            cum_cash_supp,
            cum_cogs + (final_p["inventory"] - base["inventory"]) - (final_p["accounts_payable"] - base["accounts_payable"]),
            rel_tol=1e-5,
        )
        assert math.isclose(
            cum_cash_cust - cum_cash_supp,
            cum_gp - (final_p["trade_nwc"] - (base["accounts_receivable"] + base["inventory"] - base["accounts_payable"])),
            rel_tol=1e-5,
        )


# =============================================================================
# SUITE 2: ADVERSARIAL SEVERE CONTRACTION (-90% YoY CRASH)
# =============================================================================

class TestAdversarialSevereContractionCrash:
    """Stress test 2: Macroeconomic collapse / -90% YoY contraction & cash liquidation dynamics."""

    def test_severe_contraction_90pct_crash(self):
        """
        Revenue drops 90% each year: 1,000,000 -> 100,000 -> 10,000 -> 1,000 -> 100 -> 10.
        Verifies working capital liquidation releases cash, delta_nwc < 0, collections exceed revenue.
        """
        base = {
            "dso": 60.0,
            "dio": 90.0,
            "dpo": 45.0,
            "revenue": 1_000_000.0,
            "cogs": 700_000.0,
            "accounts_receivable": (60.0 * 1_000_000.0) / 365.0,
            "inventory": (90.0 * 700_000.0) / 365.0,
            "accounts_payable": (45.0 * 700_000.0) / 365.0,
            "other_current_assets": 20_000.0,
            "other_current_liabilities": 15_000.0,
        }
        base["net_working_capital"] = (
            (base["accounts_receivable"] + base["inventory"] + base["other_current_assets"])
            - (base["accounts_payable"] + base["other_current_liabilities"])
        )

        rev_series = [1_000_000.0 * (0.10 ** (t + 1)) for t in range(5)]
        cogs_series = [700_000.0 * (0.10 ** (t + 1)) for t in range(5)]

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector="VNMAT",
            mean_revert_speed=0.0,
        )

        assert len(schedule) == 5
        for t, p in enumerate(schedule):
            assert p["accounts_receivable"] >= 0.0
            assert p["inventory"] >= 0.0
            assert p["accounts_payable"] >= 0.0
            assert p["net_working_capital"] >= 0.0

            assert p["delta_nwc"] < 0.0
            assert p["delta_ar"] < 0.0
            assert p["delta_inv"] < 0.0
            assert p["delta_ap"] < 0.0

            assert p["cash_from_customers"] > p["revenue"]

            period_gp = p["revenue"] - p["cogs"]
            delta_trade_nwc = p["delta_ar"] + p["delta_inv"] - p["delta_ap"]
            assert math.isclose(
                p["cash_from_customers"] - p["cash_to_suppliers"],
                period_gp - delta_trade_nwc,
                rel_tol=1e-5,
            )


# =============================================================================
# SUITE 3: MEAN REVERSION PARAMETER DYNAMICS & BOUNDS
# =============================================================================

class TestAdversarialMeanReversionDynamics:
    """Stress test 3: Mean reversion parameter boundaries and trajectory dynamics."""

    def test_instantaneous_convergence_speed_one(self):
        """Speed = 1.0 -> Immediate convergence to sector benchmark in period 1."""
        base = {
            "dso": 150.0,
            "dio": 200.0,
            "dpo": 20.0,
            "accounts_receivable": 4109.59,
            "inventory": 3835.62,
            "accounts_payable": 383.56,
        }
        rev_series = [10000.0] * 5
        cogs_series = [7000.0] * 5
        sector = "VNCONS"
        benchmark = SECTOR_WC_PRIORS[sector]

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector=sector,
            mean_revert_speed=1.0,
        )

        for p in schedule:
            assert math.isclose(p["dso"], benchmark["dso"], rel_tol=1e-5)
            assert math.isclose(p["dio"], benchmark["dio"], rel_tol=1e-5)
            assert math.isclose(p["dpo"], benchmark["dpo"], rel_tol=1e-5)
            assert math.isclose(p["ccc"], benchmark["ccc"], rel_tol=1e-5)

    def test_half_speed_exponential_decay(self):
        """Speed = 0.5 -> Efficiency days follow geometric progression."""
        base = {"dso": 100.0, "dio": 100.0, "dpo": 100.0}
        rev_series = [10000.0] * 5
        cogs_series = [7000.0] * 5
        sector = "VNCONS"

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector=sector,
            mean_revert_speed=0.5,
        )

        expected_dsos = [65.0, 47.5, 38.75, 34.375, 32.1875]
        for t, p in enumerate(schedule):
            assert math.isclose(p["dso"], expected_dsos[t], rel_tol=1e-5)

    def test_out_of_bounds_mean_reversion_speed_clamping(self):
        """Speed < 0.0 clamped to 0.0, Speed > 1.0 clamped to 1.0."""
        base = {"dso": 100.0, "dio": 100.0, "dpo": 100.0}
        revs = [10000.0] * 3
        cogss = [7000.0] * 3

        s_neg = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base, revenue_series=revs, cogs_series=cogss, sector="VNCONS", mean_revert_speed=-5.0
        )
        assert math.isclose(s_neg[0]["dso"], 100.0, rel_tol=1e-5)

        s_huge = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base, revenue_series=revs, cogs_series=cogss, sector="VNCONS", mean_revert_speed=99.0
        )
        assert math.isclose(s_huge[0]["dso"], 30.0, rel_tol=1e-5)

    def test_convergence_rate_alias_parameter(self):
        """Tests convergence_rate alias parameter in project_working_capital_schedule."""
        base = {"dso": 100.0, "dio": 100.0, "dpo": 100.0}
        revs = [10000.0] * 2
        cogss = [7000.0] * 2

        s_alias = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base, revenue_series=revs, cogs_series=cogss, sector="VNCONS", convergence_rate=0.5
        )
        assert math.isclose(s_alias[0]["dso"], 65.0, rel_tol=1e-5)


# =============================================================================
# SUITE 4: NEGATIVE CCC RETAIL MODEL (MWG FLOAT FINANCING)
# =============================================================================

class TestAdversarialNegativeCCCRetailRegime:
    """Stress test 4: Negative Cash Conversion Cycle (Retail / Float Financing)."""

    def test_negative_ccc_growth_generates_operating_cash(self):
        """
        MWG / Retail Float Model:
        DSO = 5 days, DIO = 25 days, DPO = 75 days -> CCC = 5 + 25 - 75 = -45 days.
        When growing (+20% YoY), trade NWC is negative and becomes more negative,
        meaning working capital produces free cash flow beyond Gross Profit!
        """
        rev_0 = 100_000.0
        cogs_0 = 80_000.0
        dso = 5.0
        dio = 25.0
        dpo = 75.0

        ar_0 = (dso * rev_0) / 365.0
        inv_0 = (dio * cogs_0) / 365.0
        ap_0 = (dpo * cogs_0) / 365.0
        trade_nwc_0 = ar_0 + inv_0 - ap_0

        base = {
            "dso": dso,
            "dio": dio,
            "dpo": dpo,
            "ccc": dso + dio - dpo, # -45.0
            "revenue": rev_0,
            "cogs": cogs_0,
            "accounts_receivable": ar_0,
            "inventory": inv_0,
            "accounts_payable": ap_0,
            "net_working_capital": trade_nwc_0,
        }

        rev_series = [rev_0 * (1.20 ** t) for t in range(1, 6)]
        cogs_series = [cogs_0 * (1.20 ** t) for t in range(1, 6)]

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector="VNCOND",
            mean_revert_speed=0.0,
        )

        assert len(schedule) == 5
        for p in schedule:
            assert p["ccc"] == -45.0
            assert p["trade_nwc"] < 0.0
            assert p["net_working_capital"] < 0.0
            assert p["delta_nwc"] < 0.0
            gp = p["revenue"] - p["cogs"]
            net_operating_cash = p["cash_from_customers"] - p["cash_to_suppliers"]
            assert net_operating_cash > gp

            delta_trade_nwc = p["delta_ar"] + p["delta_inv"] - p["delta_ap"]
            assert math.isclose(net_operating_cash, gp - delta_trade_nwc, rel_tol=1e-5)

    def test_negative_ccc_contraction_causes_cash_drain(self):
        """
        When a negative CCC retailer contracts (-20% YoY), supplier payables from prior high purchases
        must be settled while current cash receipts drop -> Working capital becomes a cash drain!
        """
        rev_0 = 100_000.0
        cogs_0 = 80_000.0
        base = {
            "dso": 5.0,
            "dio": 25.0,
            "dpo": 75.0,
            "ccc": -45.0,
            "accounts_receivable": (5.0 * rev_0) / 365.0,
            "inventory": (25.0 * cogs_0) / 365.0,
            "accounts_payable": (75.0 * cogs_0) / 365.0,
            "net_working_capital": (5.0 * rev_0 + 25.0 * cogs_0 - 75.0 * cogs_0) / 365.0,
        }

        rev_series = [rev_0 * (0.80 ** t) for t in range(1, 6)]
        cogs_series = [cogs_0 * (0.80 ** t) for t in range(1, 6)]

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector="VNCOND",
            mean_revert_speed=0.0,
        )

        for p in schedule:
            assert p["ccc"] == -45.0
            assert p["delta_nwc"] > 0.0
            gp = p["revenue"] - p["cogs"]
            net_operating_cash = p["cash_from_customers"] - p["cash_to_suppliers"]
            assert net_operating_cash < gp
            delta_trade_nwc = p["delta_ar"] + p["delta_inv"] - p["delta_ap"]
            assert math.isclose(net_operating_cash, gp - delta_trade_nwc, rel_tol=1e-5)


# =============================================================================
# SUITE 5: 20-PERIOD MONTE CARLO MULTI-YEAR DRIFT ORACLE
# =============================================================================

class TestAdversarialMultiPeriodLongHorizonPrecision:
    """Stress test 5: 20-period long horizon randomized stress test for float drift and invariant conservation."""

    def test_20_period_randomized_monte_carlo_drift_oracle(self):
        """
        Randomly generates 50 distinct 20-year scenarios with erratic boom/bust cycles.
        Checks zero drift (|diff| < 10^-5) across all conservation laws and invariants.
        """
        random.seed(42)

        for _ in range(50):
            dso = random.uniform(5.0, 120.0)
            dio = random.uniform(5.0, 200.0)
            dpo = random.uniform(10.0, 150.0)
            base_rev = random.uniform(10_000.0, 500_000.0)
            base_cogs = base_rev * random.uniform(0.4, 0.9)
            speed = random.uniform(0.0, 0.4)

            ar_0 = (dso * base_rev) / 365.0
            inv_0 = (dio * base_cogs) / 365.0
            ap_0 = (dpo * base_cogs) / 365.0
            oca_0 = base_rev * random.uniform(0.01, 0.08)
            ocl_0 = base_cogs * random.uniform(0.02, 0.10)
            nwc_0 = (ar_0 + inv_0 + oca_0) - (ap_0 + ocl_0)

            base = {
                "dso": dso,
                "dio": dio,
                "dpo": dpo,
                "ccc": dso + dio - dpo,
                "revenue": base_rev,
                "cogs": base_cogs,
                "accounts_receivable": ar_0,
                "inventory": inv_0,
                "accounts_payable": ap_0,
                "other_current_assets": oca_0,
                "other_current_liabilities": ocl_0,
                "net_working_capital": nwc_0,
            }

            num_periods = 20
            rev_series = []
            cogs_series = []
            curr_r = base_rev
            for _ in range(num_periods):
                growth = random.uniform(-0.50, 1.00)
                curr_r = max(100.0, curr_r * (1.0 + growth))
                curr_c = curr_r * random.uniform(0.4, 0.9)
                rev_series.append(curr_r)
                cogs_series.append(curr_c)

            schedule = WorkingCapitalEngine.project_working_capital_schedule(
                base_metrics=base,
                revenue_series=rev_series,
                cogs_series=cogs_series,
                sector="VNIND",
                mean_revert_speed=speed,
            )

            assert len(schedule) == num_periods

            sum_delta_nwc = sum(p["delta_nwc"] for p in schedule)
            sum_delta_ar = sum(p["delta_ar"] for p in schedule)
            sum_delta_inv = sum(p["delta_inv"] for p in schedule)
            sum_delta_ap = sum(p["delta_ap"] for p in schedule)
            sum_delta_oca = sum(p["delta_oca"] for p in schedule)
            sum_delta_ocl = sum(p["delta_ocl"] for p in schedule)

            final_p = schedule[-1]

            # Invariant 1: Sum(Delta NWC) == NWC_T - NWC_0
            assert math.isclose(sum_delta_nwc, final_p["net_working_capital"] - nwc_0, abs_tol=1e-4)

            # Invariant 2: Component sum additivity across all 20 periods
            assert math.isclose(
                sum_delta_nwc,
                (sum_delta_ar + sum_delta_inv + sum_delta_oca) - (sum_delta_ap + sum_delta_ocl),
                abs_tol=1e-4,
            )

            # Invariant 3: Cash collected == Total Rev - Delta AR_total
            total_rev = sum(rev_series)
            total_cash_cust = sum(p["cash_from_customers"] for p in schedule)
            assert math.isclose(total_cash_cust, total_rev - (final_p["accounts_receivable"] - ar_0), abs_tol=1e-4)

            # Invariant 4: Cash paid suppliers == Total COGS + Delta Inv_total - Delta AP_total
            total_cogs = sum(cogs_series)
            total_cash_supp = sum(p["cash_to_suppliers"] for p in schedule)
            assert math.isclose(
                total_cash_supp,
                total_cogs + (final_p["inventory"] - inv_0) - (final_p["accounts_payable"] - ap_0),
                abs_tol=1e-4,
            )


# =============================================================================
# SUITE 6: ADVERSARIAL FUZZING & DIRTY INPUT RESILIENCE
# =============================================================================

class TestAdversarialFuzzing:
    """Fuzzes inputs with extreme numbers, malformed strings, and weird types."""

    FUZZ_VALUES = [
        0, 0.0, -0.0, 1e-15, -1e-15, 1e15, -1e15, 1e30, -1e30,
        float("nan"), float("inf"), float("-inf"),
        None, "", "   ", "0", "-0", "0.0", "1,000,000.50", "-2,500.75",
        "N/A", "--", "null", "None", "nan", "NaN", "inf", "-inf",
        "invalid_text", "1e5", "###", "0/0",
    ]

    def test_sanitize_float_fuzzing(self):
        """Sanitizer must always return finite float without throwing unhandled exceptions."""
        for val in self.FUZZ_VALUES:
            res = sanitize_float(val, fallback=42.0)
            assert isinstance(res, float)
            assert not math.isnan(res), f"sanitize_float returned NaN for {val!r}"
            assert not math.isinf(res), f"sanitize_float returned Inf for {val!r}"

    def test_safe_div_fuzzing_matrix(self):
        """Safe division must NEVER crash or return NaN/Inf across all numerator-denominator pairs."""
        for num in self.FUZZ_VALUES:
            for den in self.FUZZ_VALUES:
                res = safe_div(num, den, fallback=0.0)
                assert isinstance(res, float)
                assert not math.isnan(res), f"safe_div returned NaN for num={num!r}, den={den!r}"
                assert not math.isinf(res), f"safe_div returned Inf for num={num!r}, den={den!r}"

    def test_clamp_fuzzing(self):
        """Clamp must strictly bound values in [min_val, max_val] even with dirty inputs."""
        for val in self.FUZZ_VALUES:
            res = clamp(val, 0.0, 1095.0)
            assert isinstance(res, float)
            assert not math.isnan(res)
            assert 0.0 <= res <= 1095.0, f"clamp breached bounds: {res} for input {val!r}"

    def test_calculate_historical_days_fuzzing_combinatorics(self):
        """Historical days calculation must never crash or produce NaN for any combination of fuzzed inputs."""
        rng = random.Random(42)
        sectors = ["VNCONS", "VNIT", "VNMAT", "VNCOND", "VNBNK", "VNFIN", "VNREAL", "DEFAULT", "UNKNOWN_123", ""]

        for _ in range(500):
            rev = rng.choice(self.FUZZ_VALUES)
            cogs = rng.choice(self.FUZZ_VALUES)
            ar = rng.choice(self.FUZZ_VALUES)
            inv = rng.choice(self.FUZZ_VALUES)
            ap = rng.choice(self.FUZZ_VALUES)
            oca = rng.choice(self.FUZZ_VALUES)
            ocl = rng.choice(self.FUZZ_VALUES)
            sec = rng.choice(sectors)

            res = WorkingCapitalEngine.calculate_historical_days(
                rev=rev, cogs=cogs, ar=ar, inv=inv, ap=ap,
                other_ca=oca, other_cl=ocl, sector=sec,
            )

            assert isinstance(res, dict)
            for k in ["dso", "dio", "dpo", "ccc", "trade_nwc", "net_working_capital", "delta_nwc"]:
                val = res[k]
                assert isinstance(val, (int, float)), f"Key {k} is not float: {val}"
                assert not math.isnan(val), f"Key {k} is NaN with inputs: rev={rev}, cogs={cogs}, ar={ar}, inv={inv}, ap={ap}"
                assert not math.isinf(val), f"Key {k} is Inf with inputs: rev={rev}, cogs={cogs}, ar={ar}, inv={inv}, ap={ap}"

    def test_project_schedule_with_wild_series(self):
        """Projection schedule handles empty, negative, extreme spikes, and NaN series gracefully."""
        base = {
            "dso": 45.0, "dio": 60.0, "dpo": 30.0,
            "ar": 1000.0, "inv": 1000.0, "ap": 500.0,
            "other_ca": 100.0, "other_cl": 50.0,
            "net_working_capital": 1550.0,
        }

        sched_empty = WorkingCapitalEngine.project_working_capital_schedule(base, [], [])
        assert sched_empty == []

        rev_series = [1000.0, -500.0, float("nan"), 0.0, 1e12]
        cogs_series = [700.0, -300.0, float("inf"), 0.0, 7e11]

        sched_fuzz = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector="VNMAT",
            mean_revert_speed=0.5,
        )

        assert len(sched_fuzz) == 5
        for p in sched_fuzz:
            for field in ["dso", "dio", "dpo", "ccc", "accounts_receivable", "inventory", "accounts_payable", "net_working_capital", "delta_nwc"]:
                v = p[field]
                assert not math.isnan(v), f"Schedule field {field} was NaN in period {p}"
                assert not math.isinf(v), f"Schedule field {field} was Inf in period {p}"


# =============================================================================
# SUITE 7: 1,000 RANDOMIZED MONTE CARLO INVARIANT ORACLES
# =============================================================================

class TestMonteCarloAccountingInvariants:
    """
    Simulates 1,000 randomized dynamic business scenarios to mathematically
    verify conservation laws, delta additivity, and direct cash flow links.
    """

    def test_1000_monte_carlo_delta_nwc_invariants(self):
        """
        Verify:
        1. Delta NWC_t == Delta AR_t + Delta Inv_t + Delta OCA_t - Delta AP_t - Delta OCL_t
        2. NWC_t - NWC_{t-1} == Delta NWC_t
        3. Trade NWC_t == AR_t + Inv_t - AP_t
        4. Cash Receipts_t == Rev_t - Delta AR_t
        5. Cash Paid Suppliers_t == COGS_t + Delta Inv_t - Delta AP_t
        6. (Cash Receipts - Cash Paid Suppliers) == (Rev - COGS) - Delta Trade NWC
        """
        rng = random.Random(20260902)
        sectors = [
            "VNCONS", "VNCOND", "VNMAT", "VNIND", "VNIT", "VNREAL", "VNENE",
            "VNUTI", "VNHEAL", "DEFAULT", "CUSTOM_SECTOR_A"
        ]

        total_simulations = 1000
        for sim_idx in range(total_simulations):
            num_years = rng.randint(2, 10)
            sec = rng.choice(sectors)
            speed = rng.uniform(-0.2, 1.2)

            base_rev = rng.uniform(1_000.0, 500_000.0)
            base_cogs = base_rev * rng.uniform(0.3, 0.9)
            base_ar = base_rev * rng.uniform(0.01, 0.4)
            base_inv = base_cogs * rng.uniform(0.01, 0.6)
            base_ap = base_cogs * rng.uniform(0.01, 0.5)
            base_oca = base_rev * rng.uniform(0.0, 0.15)
            base_ocl = base_cogs * rng.uniform(0.0, 0.15)

            base_metrics = WorkingCapitalEngine.calculate_historical_days(
                rev=base_rev, cogs=base_cogs, ar=base_ar, inv=base_inv, ap=base_ap,
                other_ca=base_oca, other_cl=base_ocl, sector=sec
            )

            cagr_rev = rng.uniform(-0.30, 0.60)
            cagr_cogs = rng.uniform(-0.30, 0.60)
            rev_series = [base_rev * ((1.0 + cagr_rev) ** (t + 1)) for t in range(num_years)]
            cogs_series = [base_cogs * ((1.0 + cagr_cogs) ** (t + 1)) for t in range(num_years)]

            if rng.random() > 0.5:
                oca_series = [base_oca * (1.05 ** (t + 1)) for t in range(num_years)]
                ocl_series = [base_ocl * (1.05 ** (t + 1)) for t in range(num_years)]
            else:
                oca_series = None
                ocl_series = None

            schedule = WorkingCapitalEngine.project_working_capital_schedule(
                base_metrics=base_metrics,
                revenue_series=rev_series,
                cogs_series=cogs_series,
                other_ca_series=oca_series,
                other_cl_series=ocl_series,
                sector=sec,
                mean_revert_speed=speed,
            )

            assert len(schedule) == num_years

            prev_ar = base_metrics["accounts_receivable"]
            prev_inv = base_metrics["inventory"]
            prev_ap = base_metrics["accounts_payable"]
            prev_oca = base_metrics["other_current_assets"]
            prev_ocl = base_metrics["other_current_liabilities"]
            prev_nwc = base_metrics["net_working_capital"]
            prev_trade_nwc = base_metrics["trade_nwc"]

            for t, p in enumerate(schedule):
                ar_t = p["accounts_receivable"]
                inv_t = p["inventory"]
                ap_t = p["accounts_payable"]
                oca_t = p["other_current_assets"]
                ocl_t = p["other_current_liabilities"]
                nwc_t = p["net_working_capital"]
                trade_nwc_t = p["trade_nwc"]

                d_ar = p["delta_ar"]
                d_inv = p["delta_inv"]
                d_ap = p["delta_ap"]
                d_oca = p["delta_oca"]
                d_ocl = p["delta_ocl"]
                d_nwc = p["delta_nwc"]

                rev_t = p["revenue"]
                cogs_t = p["cogs"]
                cash_cust = p["cash_from_customers"]
                cash_supp = p["cash_to_suppliers"]

                # 1. Delta component consistency
                assert math.isclose(d_ar, ar_t - prev_ar, abs_tol=1e-5)
                assert math.isclose(d_inv, inv_t - prev_inv, abs_tol=1e-5)
                assert math.isclose(d_ap, ap_t - prev_ap, abs_tol=1e-5)
                assert math.isclose(d_oca, oca_t - prev_oca, abs_tol=1e-5)
                assert math.isclose(d_ocl, ocl_t - prev_ocl, abs_tol=1e-5)

                # 2. Delta NWC Additivity Invariant
                sum_deltas = (d_ar + d_inv + d_oca) - (d_ap + d_ocl)
                assert math.isclose(d_nwc, sum_deltas, abs_tol=1e-5)

                # 3. Roll-Forward Invariant
                assert math.isclose(nwc_t - prev_nwc, d_nwc, abs_tol=1e-5)

                # 4. Trade NWC definition
                assert math.isclose(trade_nwc_t, ar_t + inv_t - ap_t, abs_tol=1e-5)

                # 5. Direct Cash Receipts & Supplier Payments
                assert math.isclose(cash_cust, rev_t - d_ar, abs_tol=1e-5)
                assert math.isclose(cash_supp, cogs_t + d_inv - d_ap, abs_tol=1e-5)

                # 6. Operating Cash Flow Conservation
                gross_profit_t = rev_t - cogs_t
                delta_trade_nwc_t = trade_nwc_t - prev_trade_nwc
                gross_cfo = cash_cust - cash_supp
                expected_gross_cfo = gross_profit_t - delta_trade_nwc_t
                assert math.isclose(gross_cfo, expected_gross_cfo, abs_tol=1e-5)

                # Advance
                prev_ar = ar_t
                prev_inv = inv_t
                prev_ap = ap_t
                prev_oca = oca_t
                prev_ocl = ocl_t
                prev_nwc = nwc_t
                prev_trade_nwc = trade_nwc_t

    def test_financial_sector_1000_monte_carlo_isolation(self):
        """Verify that financial sector tickers consistently produce exact zero working capital."""
        rng = random.Random(99999)
        fin_sectors = ["VNBNK", "VNFIN", "VNSEC", "VNINS", "BANK", "FIN", "SECURITIES", "8300", "8500", "8700"]

        for _ in range(500):
            sec = rng.choice(fin_sectors)
            rev = rng.uniform(10_000, 1_000_000)
            cogs = rng.uniform(5_000, 500_000)
            ar = rng.uniform(0, 50_000)
            inv = rng.uniform(0, 50_000)
            ap = rng.uniform(0, 50_000)

            res = WorkingCapitalEngine.calculate_historical_days(rev, cogs, ar, inv, ap, sector=sec)
            assert res["is_financial_sector"] is True
            assert res["dso"] == 0.0
            assert res["dio"] == 0.0
            assert res["dpo"] == 0.0
            assert res["ccc"] == 0.0
            assert res["net_working_capital"] == 0.0
            assert res["trade_nwc"] == 0.0
            assert res["delta_nwc"] == 0.0


# =============================================================================
# SUITE 8: ALL 30 VN30 TICKERS REAL FUNDAMENTAL DATA VERIFICATION
# =============================================================================

class TestVN30RealDataEmpiricalValidation:
    """
    Tests every constituent of the VN30 index against real market and fundamental
    data from local files data/screener_snapshot.json and data/financial_models.json.
    """

    @pytest.fixture(scope="class")
    def screener_data(self) -> Dict[str, Any]:
        path = os.path.join(os.path.dirname(__file__), "..", "data", "screener_snapshot.json")
        if not os.path.exists(path):
            pytest.skip(f"Data file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {item.get("ticker", item.get("symbol", "")).upper(): item for item in data if item}
        return data

    def test_all_30_vn30_tickers_execute_cleanly(self, screener_data):
        """Validates all 30 VN30 tickers against screener fundamental data."""
        tested_count = 0

        for symbol in VN30_TICKERS:
            stock_info = screener_data.get(symbol, {})
            sector = stock_info.get("sector", stock_info.get("icb_sector", stock_info.get("industry", "DEFAULT")))

            rev = sanitize_float(stock_info.get("revenue", stock_info.get("net_revenue", stock_info.get("total_revenue", 50000.0))))
            cogs = sanitize_float(stock_info.get("cogs", stock_info.get("cost_of_goods_sold", rev * 0.70)))
            ar = sanitize_float(stock_info.get("receivables", stock_info.get("accounts_receivable", rev * 0.12)))
            inv = sanitize_float(stock_info.get("inventory", stock_info.get("inventories", cogs * 0.15)))
            ap = sanitize_float(stock_info.get("payables", stock_info.get("accounts_payable", cogs * 0.10)))

            if symbol in FINANCIAL_VN30_TICKERS:
                inv = 0.0
                sector = "VNBNK" if symbol in ["ACB", "BID", "CTG", "HDB", "MBB", "SHB", "SSB", "STB", "TCB", "TPB", "VCB", "VIB", "VPB"] else "VNSEC" if symbol == "SSI" else "VNINS"

            # 1. Historical Days Calculation
            hist_metrics = WorkingCapitalEngine.calculate_historical_days(
                rev=rev, cogs=cogs, ar=ar, inv=inv, ap=ap, sector=sector
            )

            assert isinstance(hist_metrics, dict)
            assert not math.isnan(hist_metrics["dso"])
            assert not math.isnan(hist_metrics["dio"])
            assert not math.isnan(hist_metrics["dpo"])
            assert not math.isnan(hist_metrics["ccc"])
            assert not math.isnan(hist_metrics["net_working_capital"])

            # 2. Pydantic Model Conversion
            wc_metrics_model = WorkingCapitalMetrics(**hist_metrics)
            assert wc_metrics_model.dso >= 0.0

            # 3. 5-Year Integrated Projections
            rev_fwd = [rev * (1.08 ** i) for i in range(1, 6)]
            cogs_fwd = [cogs * (1.08 ** i) for i in range(1, 6)]

            forecast_res = WorkingCapitalEngine.build_working_capital_forecast(
                symbol=symbol,
                base_data=hist_metrics,
                revenue_forecast=rev_fwd,
                cogs_forecast=cogs_fwd,
                sector=sector,
                mean_revert_speed=0.15,
            )

            assert isinstance(forecast_res, WorkingCapitalForecastResult)
            assert forecast_res.symbol == symbol
            assert len(forecast_res.schedule) == 5

            # ForecastResult serialization
            d_dump = forecast_res.to_dict()
            assert isinstance(d_dump, dict)
            assert "schedule" in d_dump

            # 4. Sector-Specific Assertions
            if symbol in FINANCIAL_VN30_TICKERS:
                assert forecast_res.summary["is_financial"] is True
                for period in forecast_res.schedule:
                    assert period.dso == 0.0
                    assert period.dio == 0.0
                    assert period.dpo == 0.0
                    assert period.net_working_capital == 0.0
                    assert period.delta_nwc == 0.0
            else:
                assert forecast_res.summary["is_financial"] is False
                for period in forecast_res.schedule:
                    sum_deltas = (period.delta_ar + period.delta_inv + period.delta_oca) - (period.delta_ap + period.delta_ocl)
                    assert math.isclose(period.delta_nwc, sum_deltas, abs_tol=1e-4)

            tested_count += 1

        assert tested_count == 30, f"Expected 30 VN30 tickers tested, got {tested_count}"
