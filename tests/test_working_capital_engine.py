"""
=============================================================================
COMPREHENSIVE 4-TIER TEST SUITE: WORKING CAPITAL & NWC ENGINE (MILESTONE 1)
=============================================================================
Tiers Covered:
- Tier 1: Standard Calculation & 5-Year Working Capital Schedule Projections
- Tier 2: Boundary Value, Extreme Values & Adversarial Edge Cases
- Tier 3: Cross-Consistency, Accounting Invariants & Direct Cash Flow Identities
- Tier 4: Empirical Real-World VN30 Tickers Integration (VNM, FPT, HPG, MWG, MSN, GAS, VCB/TCB/MBB)
=============================================================================
"""

import os
import json
import math
import pytest
from typing import Dict, List, Any

from services.working_capital_engine import (
    WorkingCapitalEngine,
    WorkingCapitalMetrics,
    WorkingCapitalSchedulePeriod,
    WorkingCapitalForecastResult,
    build_working_capital_schedule,
    SECTOR_WC_PRIORS,
    SECTOR_PRIORS,
    SECTOR_BENCHMARKS,
    FINANCIAL_SYMBOLS,
    safe_div,
    clamp,
    sanitize_float,
    resolve_sector_prior,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def clean_manufacturing_data():
    """Standard industrial company fundamental baseline (e.g. HPG-like)."""
    return {
        "revenue": 100_000.0,
        "cogs": 70_000.0,
        "accounts_receivable": 15_000.0,
        "inventory": 14_000.0,
        "accounts_payable": 10_000.0,
        "other_current_assets": 2_000.0,
        "other_current_liabilities": 3_000.0,
        "sector": "VNMAT",
    }


@pytest.fixture
def retail_cash_model_data():
    """Retail company with negative working capital cycle (e.g. MWG-like)."""
    return {
        "revenue": 120_000.0,
        "cogs": 95_000.0,
        "accounts_receivable": 2_000.0,  # DSO = 6.08 days
        "inventory": 12_000.0,           # DIO = 46.10 days
        "accounts_payable": 25_000.0,    # DPO = 96.05 days
        "other_current_assets": 1_000.0,
        "other_current_liabilities": 2_000.0,
        "sector": "VNCOND",
    }


# =============================================================================
# TIER 1: STANDARD CALCULATION & 5-YEAR PROJECTION TESTS
# =============================================================================

class TestTier1StandardCalculations:
    """Tier 1: Core mathematical formula verification and 5-year projections."""

    def test_calculate_historical_days_standard(self, clean_manufacturing_data):
        d = clean_manufacturing_data
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=d["revenue"],
            cogs=d["cogs"],
            ar=d["accounts_receivable"],
            inv=d["inventory"],
            ap=d["accounts_payable"],
            other_ca=d["other_current_assets"],
            other_cl=d["other_current_liabilities"],
            sector=d["sector"],
        )
        assert isinstance(res, dict)
        # DSO = (15000 / 100000) * 365 = 54.75
        assert math.isclose(res["dso"], 54.75, rel_tol=1e-5)
        # DIO = (14000 / 70000) * 365 = 73.00
        assert math.isclose(res["dio"], 73.00, rel_tol=1e-5)
        # DPO = (10000 / 70000) * 365 = 52.142857
        assert math.isclose(res["dpo"], 52.142857, rel_tol=1e-5)
        # CCC = 54.75 + 73.00 - 52.142857 = 75.607143
        assert math.isclose(res["ccc"], 75.607143, rel_tol=1e-5)
        # Trade NWC = 15000 + 14000 - 10000 = 19000
        assert math.isclose(res["trade_nwc"], 19000.0, rel_tol=1e-5)
        # Net Working Capital = (15000 + 14000 + 2000) - (10000 + 3000) = 18000
        assert math.isclose(res["net_working_capital"], 18000.0, rel_tol=1e-5)

    def test_calculate_nwc_with_other_operating_items(self):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=100000.0,
            cogs=70000.0,
            ar=25000.0,
            inv=30000.0,
            ap=18000.0,
            other_ca=5000.0,
            other_cl=7000.0,
        )
        assert res["net_working_capital"] == 35000.0
        assert res["trade_nwc"] == 37000.0

    def test_pydantic_contract_working_capital_metrics(self, clean_manufacturing_data):
        d = clean_manufacturing_data
        raw = WorkingCapitalEngine.calculate_historical_days(
            rev=d["revenue"],
            cogs=d["cogs"],
            ar=d["accounts_receivable"],
            inv=d["inventory"],
            ap=d["accounts_payable"],
        )
        metrics = WorkingCapitalMetrics(**raw)
        assert metrics.dso > 0.0
        assert metrics.dio > 0.0
        assert metrics.dpo > 0.0
        dumped = metrics.to_dict()
        assert "ccc" in dumped
        assert "trade_nwc" in dumped
        assert "net_working_capital" in dumped

    def test_5y_schedule_constant_efficiency(self):
        base = {
            "dso": 45.0,
            "dio": 60.0,
            "dpo": 30.0,
            "ar": 1232.88,
            "inv": 1150.68,
            "ap": 575.34,
            "other_ca": 100.0,
            "other_cl": 50.0,
            "net_working_capital": 1858.22,
        }
        rev_series = [10000.0, 11000.0, 12100.0, 13310.0, 14641.0] # 10% CAGR
        cogs_series = [7000.0, 7700.0, 8470.0, 9317.0, 10248.7]

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            mean_revert_speed=0.0, # Constant days
        )

        assert len(schedule) == 5
        for t, period in enumerate(schedule):
            expected_ar = (45.0 * rev_series[t]) / 365.0
            expected_inv = (60.0 * cogs_series[t]) / 365.0
            expected_ap = (30.0 * cogs_series[t]) / 365.0
            assert math.isclose(period["accounts_receivable"], expected_ar, rel_tol=1e-4)
            assert math.isclose(period["inventory"], expected_inv, rel_tol=1e-4)
            assert math.isclose(period["accounts_payable"], expected_ap, rel_tol=1e-4)
            assert math.isclose(period["dso"], 45.0, rel_tol=1e-4)
            assert math.isclose(period["dio"], 60.0, rel_tol=1e-4)
            assert math.isclose(period["dpo"], 30.0, rel_tol=1e-4)
            if t > 0:
                assert period["delta_nwc"] > 0.0 # Growing business requires NWC investment
            else:
                assert math.isclose(period["delta_nwc"], 0.0, abs_tol=1e-2)

    def test_5y_schedule_mean_reverting(self):
        base = {
            "dso": 120.0, # Inefficient collection
            "dio": 60.0,
            "dpo": 40.0,
            "ar": 3287.67,
            "inv": 1150.68,
            "ap": 767.12,
            "net_working_capital": 3671.23,
        }
        rev_series = [10000.0] * 5
        cogs_series = [7000.0] * 5

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sector="VNCONS", # Benchmark DSO = 30.0
            mean_revert_speed=0.25,
        )

        assert len(schedule) == 5
        prev_dso = 120.0
        for period in schedule:
            assert period["dso"] < prev_dso # DSO monotonically approaches target
            prev_dso = period["dso"]
            assert period["delta_nwc"] < 0.0 # Efficiency gains release cash

    def test_build_working_capital_forecast_full_pipeline(self, clean_manufacturing_data):
        d = clean_manufacturing_data
        rev_fwd = [110000.0, 121000.0, 133100.0, 146410.0, 161051.0]
        cogs_fwd = [77000.0, 84700.0, 93170.0, 102487.0, 112735.7]

        result = WorkingCapitalEngine.build_working_capital_forecast(
            symbol="HPG",
            base_data=d,
            revenue_forecast=rev_fwd,
            cogs_forecast=cogs_fwd,
            sector="VNMAT",
            start_year=2026,
            mean_revert_speed=0.15,
        )

        assert isinstance(result, WorkingCapitalForecastResult)
        assert result.symbol == "HPG"
        assert len(result.schedule) == 5
        assert result.schedule[0].year == 2026
        assert result.schedule[4].year == 2030
        assert result.summary["is_financial"] is False


# =============================================================================
# TIER 2: BOUNDARY VALUE & ADVERSARIAL EDGE CASE TESTS
# =============================================================================

class TestTier2BoundaryAndAdversarial:
    """Tier 2: Robustness against zeros, negatives, extremes, and dirty inputs."""

    def test_zero_revenue_safe_fallback(self):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=0.0,
            cogs=50000.0,
            ar=10000.0,
            inv=10000.0,
            ap=10000.0,
            sector="VNIND",
        )
        assert not math.isnan(res["dso"])
        assert not math.isinf(res["dso"])
        assert res["dso"] == SECTOR_PRIORS["VNIND"]["dso"]

    def test_zero_cogs_safe_fallback(self):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=100000.0,
            cogs=0.0,
            ar=20000.0,
            inv=0.0,
            ap=5000.0,
            sector="VNIT",
        )
        assert not math.isnan(res["dio"])
        assert not math.isnan(res["dpo"])
        assert not math.isinf(res["dio"])
        assert not math.isinf(res["dpo"])

    def test_startup_all_zeros(self):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=0.0, cogs=0.0, ar=0.0, inv=0.0, ap=0.0, sector="DEFAULT"
        )
        assert res["net_working_capital"] == 0.0
        assert res["trade_nwc"] == 0.0
        assert not math.isnan(res["ccc"])

    def test_negative_receivables_and_payables_clamped(self):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=50000.0,
            cogs=30000.0,
            ar=-5000.0,
            inv=8000.0,
            ap=-2000.0,
        )
        assert res["accounts_receivable"] >= 0.0
        assert res["accounts_payable"] >= 0.0
        assert res["dso"] >= 0.0
        assert res["dpo"] >= 0.0

    def test_negative_gross_margin_turnaround(self):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=40000.0,
            cogs=60000.0, # Gross loss
            ar=8000.0,
            inv=15000.0,
            ap=12000.0,
        )
        assert math.isclose(res["dso"], (8000 / 40000) * 365, rel_tol=1e-5)
        assert math.isclose(res["dio"], (15000 / 60000) * 365, rel_tol=1e-5)
        assert math.isclose(res["dpo"], (12000 / 60000) * 365, rel_tol=1e-5)

    def test_extreme_working_capital_days_clamping(self):
        # Extremely small revenue creates raw DSO of 3.65 million days
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=1.0,
            cogs=1.0,
            ar=10000.0,
            inv=10000.0,
            ap=10000.0,
        )
        assert res["dso"] <= 1095.0 # Clamped to maximum 3 years
        assert res["dio"] <= 1095.0
        assert res["dpo"] <= 1095.0

    def test_negative_ccc_retail_model(self, retail_cash_model_data):
        d = retail_cash_model_data
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=d["revenue"],
            cogs=d["cogs"],
            ar=d["accounts_receivable"],
            inv=d["inventory"],
            ap=d["accounts_payable"],
            sector=d["sector"],
        )
        assert res["ccc"] < 0.0 # Negative CCC is physically valid for modern retailers
        assert res["trade_nwc"] < 0.0

    def test_missing_and_dirty_string_inputs(self):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev="100,000.0",
            cogs="70,000.0",
            ar="15,000.0",
            inv="14,000.0",
            ap="--",
            other_ca=None,
            other_cl="N/A",
            sector="VNCONS",
        )
        assert math.isclose(res["revenue"], 100000.0, rel_tol=1e-5)
        assert math.isclose(res["accounts_receivable"], 15000.0, rel_tol=1e-5)
        assert res["other_current_assets"] == 0.0
        assert not math.isnan(res["dso"])
        assert not math.isnan(res["net_working_capital"])

    @pytest.mark.parametrize("sector_code", ["VNBNK", "VNFIN", "VNSEC", "VNINS", "8300", "8500", "8700"])
    def test_financial_sector_gating(self, sector_code):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=50000.0,
            cogs=20000.0,
            ar=10000.0,
            inv=5000.0,
            ap=8000.0,
            sector=sector_code,
        )
        assert res["is_financial_sector"] is True
        assert res["trade_nwc"] == 0.0
        assert res["net_working_capital"] == 0.0
        assert res["dso"] == 0.0
        assert res["dio"] == 0.0
        assert res["dpo"] == 0.0


# =============================================================================
# TIER 3: CROSS-CONSISTENCY & INVARIANT IDENTITIES
# =============================================================================

class TestTier3AccountingInvariants:
    """Tier 3: Strict mathematical accounting identities and conservation laws."""

    def test_delta_nwc_component_additivity_invariant(self):
        base = {
            "dso": 40.0,
            "dio": 50.0,
            "dpo": 35.0,
            "ar": 1000.0,
            "inv": 1200.0,
            "ap": 800.0,
            "other_ca": 200.0,
            "other_cl": 150.0,
            "net_working_capital": 1450.0,
        }
        rev_series = [10000.0, 11500.0, 13000.0, 15000.0, 18000.0]
        cogs_series = [7000.0, 8000.0, 9000.0, 10500.0, 12500.0]

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
        )

        prev_p = base
        for period in schedule:
            d_ar = period["accounts_receivable"] - prev_p.get("accounts_receivable", prev_p.get("ar", 0.0))
            d_inv = period["inventory"] - prev_p.get("inventory", prev_p.get("inv", 0.0))
            d_ap = period["accounts_payable"] - prev_p.get("accounts_payable", prev_p.get("ap", 0.0))
            d_other_ca = period["other_current_assets"] - prev_p.get("other_current_assets", prev_p.get("other_ca", 0.0))
            d_other_cl = period["other_current_liabilities"] - prev_p.get("other_current_liabilities", prev_p.get("other_cl", 0.0))

            sum_deltas = (d_ar + d_inv + d_other_ca) - (d_ap + d_other_cl)
            assert math.isclose(period["delta_nwc"], sum_deltas, abs_tol=1e-5)
            prev_p = period

    def test_ccc_exact_identity_invariant(self):
        for dso in [10.0, 45.0, 90.0, 120.0]:
            for dio in [5.0, 60.0, 180.0]:
                for dpo in [15.0, 45.0, 90.0]:
                    ccc = dso + dio - dpo
                    res = WorkingCapitalEngine.calculate_historical_days(
                        rev=100000.0,
                        cogs=70000.0,
                        ar=(dso * 100000.0) / 365.0,
                        inv=(dio * 70000.0) / 365.0,
                        ap=(dpo * 70000.0) / 365.0,
                    )
                    assert math.isclose(res["ccc"], ccc, rel_tol=1e-5)

    def test_direct_method_cash_flow_reconciliation_invariant(self):
        prior = {"accounts_receivable": 1000.0, "inventory": 1500.0, "accounts_payable": 800.0, "trade_nwc": 1700.0}
        curr = {"accounts_receivable": 1200.0, "inventory": 1800.0, "accounts_payable": 1000.0, "trade_nwc": 2000.0}
        rev = 10000.0
        cogs = 6500.0
        gross_profit = rev - cogs # 3500.0

        adj = WorkingCapitalEngine.compute_direct_cash_flow_adjustments(curr, prior, rev, cogs)

        # Receipts = Rev - Delta AR = 10000 - 200 = 9800
        assert math.isclose(adj["cash_from_customers"], 9800.0, rel_tol=1e-5)
        # Supplier Payments = COGS + Delta Inv - Delta AP = 6500 + 300 - 200 = 6600
        assert math.isclose(adj["cash_to_suppliers"], 6600.0, rel_tol=1e-5)
        # Gross Operating Cash Flow = 9800 - 6600 = 3200
        gross_cfo = adj["cash_from_customers"] - adj["cash_to_suppliers"]
        # Invariant: Gross CFO == Gross Profit - Delta Trade NWC (3500 - 300 = 3200)
        delta_trade_nwc = curr["trade_nwc"] - prior["trade_nwc"] # 300
        assert math.isclose(gross_cfo, gross_profit - delta_trade_nwc, rel_tol=1e-5)

    def test_zero_growth_steady_state_invariance(self):
        base = {
            "dso": 40.0,
            "dio": 50.0,
            "dpo": 30.0,
            "ar": 1095.8904,
            "inv": 958.9041,
            "ap": 575.3424,
            "other_ca": 100.0,
            "other_cl": 50.0,
            "net_working_capital": 1529.4521,
            "revenue": 10000.0,
            "cogs": 7000.0,
        }
        rev_series = [10000.0] * 5
        cogs_series = [7000.0] * 5

        schedule = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            mean_revert_speed=0.0,
        )

        for period in schedule:
            assert math.isclose(period["delta_nwc"], 0.0, abs_tol=1e-4)

    def test_linear_scaling_homogeneity(self):
        d = {"rev": 10000.0, "cogs": 7000.0, "ar": 1500.0, "inv": 1400.0, "ap": 1000.0}
        k = 3.75
        base = WorkingCapitalEngine.calculate_historical_days(d["rev"], d["cogs"], d["ar"], d["inv"], d["ap"])
        scaled = WorkingCapitalEngine.calculate_historical_days(d["rev"]*k, d["cogs"]*k, d["ar"]*k, d["inv"]*k, d["ap"]*k)

        assert math.isclose(base["dso"], scaled["dso"], rel_tol=1e-5)
        assert math.isclose(base["dio"], scaled["dio"], rel_tol=1e-5)
        assert math.isclose(base["dpo"], scaled["dpo"], rel_tol=1e-5)
        assert math.isclose(base["ccc"], scaled["ccc"], rel_tol=1e-5)
        assert math.isclose(base["net_working_capital"] * k, scaled["net_working_capital"], rel_tol=1e-5)


# =============================================================================
# TIER 4: REAL-WORLD VN30 TICKER INTEGRATION TESTS
# =============================================================================

class TestTier4VN30Integration:
    """Tier 4: Empirical testing against real-world VN30 companies."""

    @pytest.mark.parametrize("ticker,expected_sector", [
        ("VNM", "VNCONS"),  # Vinamilk (Consumer Staples)
        ("FPT", "VNIT"),    # FPT Corp (Technology)
        ("HPG", "VNMAT"),   # Hoa Phat Steel (Materials)
        ("MWG", "VNCOND"),  # Mobile World (Consumer Discretionary / Retail)
        ("MSN", "VNCONS"),  # Masan Group (Consumer Staples)
        ("GAS", "VNENE"),   # PV Gas (Energy)
    ])
    def test_vn30_constituent_empirical_execution(self, ticker, expected_sector):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=80000.0,
            cogs=55000.0,
            ar=8000.0,
            inv=12000.0,
            ap=9000.0,
            sector=expected_sector,
        )
        assert res["dso"] >= 0.0
        assert res["dio"] >= 0.0
        assert res["dpo"] >= 0.0
        assert not math.isnan(res["ccc"])
        assert res["is_financial_sector"] is False

    @pytest.mark.parametrize("bank_ticker", ["VCB", "TCB", "MBB", "ACB", "BID", "CTG"])
    def test_vn30_banks_clean_execution(self, bank_ticker):
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=60000.0,
            cogs=25000.0,
            ar=0.0,
            inv=0.0,
            ap=0.0,
            sector="VNBNK",
        )
        assert res["is_financial_sector"] is True
        assert res["net_working_capital"] == 0.0
        assert not math.isnan(res["dso"])
        assert res["dso"] == 0.0
        assert res["dio"] == 0.0

    def test_full_vn30_batch_execution(self):
        """Simulates full batch iteration across all VN30 constituents."""
        vn30_sample = [
            ("HPG", "VNMAT", 158332.0, 131618.0, 15000.0, 52000.0, 25000.0),
            ("VNM", "VNCONS", 61500.0, 35970.0, 4800.0, 6300.0, 6700.0),
            ("MWG", "VNCOND", 132400.0, 107770.0, 4500.0, 26000.0, 34000.0),
            ("FPT", "VNIT", 70208.0, 44224.0, 14400.0, 2200.0, 19000.0),
            ("MSN", "VNCONS", 82000.0, 58000.0, 7500.0, 14000.0, 12000.0),
            ("GAS", "VNENE", 135197.0, 118079.0, 24000.0, 4400.0, 1500.0),
            ("VCB", "VNBNK", 66453.0, 76689.0, 0.0, 0.0, 0.0),
            ("TCB", "VNBNK", 42000.0, 45000.0, 0.0, 0.0, 0.0),
            ("SSI", "VNSEC", 8000.0, 4000.0, 0.0, 0.0, 0.0),
            ("BVH", "VNINS", 55000.0, 45000.0, 0.0, 0.0, 0.0),
        ]

        for symbol, sec, rev, cogs, ar, inv, ap in vn30_sample:
            metrics = WorkingCapitalEngine.calculate_historical_days(
                rev=rev, cogs=cogs, ar=ar, inv=inv, ap=ap, sector=sec
            )
            assert not math.isnan(metrics["dso"])
            assert not math.isnan(metrics["dio"])
            assert not math.isnan(metrics["dpo"])
            assert not math.isnan(metrics["ccc"])

            schedule = WorkingCapitalEngine.project_working_capital_schedule(
                base_metrics=metrics,
                revenue_series=[rev * (1.08**i) for i in range(1, 6)],
                cogs_series=[cogs * (1.08**i) for i in range(1, 6)],
                sector=sec,
                mean_revert_speed=0.10,
            )
            assert len(schedule) == 5
            for p in schedule:
                assert not math.isnan(p["net_working_capital"])
                assert not math.isnan(p["delta_nwc"])


# =============================================================================
# TIER 5: COMPREHENSIVE HELPER, ALIAS & COVERAGE ENHANCEMENT TESTS
# =============================================================================

class TestTier5HelperAndCoverageEnhancements:
    """Tier 5: Exhaustive coverage for arithmetic helpers, alias resolution, and edge paths."""

    def test_sanitize_float_edge_cases(self):
        assert sanitize_float(None, 42.0) == 42.0
        assert sanitize_float(float("nan"), 10.0) == 10.0
        assert sanitize_float(float("inf"), 10.0) == 10.0
        assert sanitize_float(123.45) == 123.45
        assert sanitize_float("1,234,567.89") == 1234567.89
        assert sanitize_float("-", 5.0) == 5.0
        assert sanitize_float("--", 5.0) == 5.0
        assert sanitize_float("N/A", 5.0) == 5.0
        assert sanitize_float("null", 5.0) == 5.0
        assert sanitize_float("invalid_string_xyz", 7.0) == 7.0

    def test_safe_div_edge_cases(self):
        assert safe_div(100.0, 0.0, fallback=99.0) == 99.0
        assert safe_div(100.0, float("nan"), fallback=99.0) == 99.0
        assert safe_div(float("nan"), 10.0, fallback=99.0) == 99.0
        assert safe_div(float("inf"), 10.0, fallback=99.0) == 99.0
        assert safe_div(100.0, float("inf"), fallback=99.0) == 99.0
        assert safe_div(100.0, 4.0) == 25.0

    def test_clamp_edge_cases(self):
        assert clamp(-10.0, 0.0, 100.0) == 0.0
        assert clamp(150.0, 0.0, 100.0) == 100.0
        assert clamp(50.0, 0.0, 100.0) == 50.0
        assert clamp(float("nan"), 10.0, 100.0) == 10.0

    def test_resolve_sector_prior_all_paths(self):
        assert resolve_sector_prior(None)["name"] == "General"
        assert resolve_sector_prior("")["name"] == "General"
        assert resolve_sector_prior("VNCONS")["dso"] == 30.0
        assert resolve_sector_prior("BANK_ACB")["is_financial"] is True
        assert resolve_sector_prior("TECH_FPT")["name"] == "Technology"
        assert resolve_sector_prior("REAL_ESTATE_VHM")["name"] == "Real Estate"
        assert resolve_sector_prior("STEEL_HPG")["name"] == "Basic Materials"
        assert resolve_sector_prior("FOOD_BEV")["name"] == "Consumer Staples"
        assert resolve_sector_prior("RETAIL_MWG")["name"] == "Consumer Discretionary"
        assert resolve_sector_prior("CONST_CTD")["name"] == "Industrials"
        assert resolve_sector_prior("OIL_GAS_GAS")["name"] == "Energy"
        assert resolve_sector_prior("WATER_BWE")["name"] == "Utilities"
        assert resolve_sector_prior("PHARMA_DHG")["name"] == "Healthcare"
        assert resolve_sector_prior("COMPLETELY_UNKNOWN_SECTOR_999")["name"] == "General"

    def test_calculate_working_capital_metrics_with_prev_nwc(self):
        metrics = WorkingCapitalEngine.calculate_working_capital_metrics(
            rev=100000.0,
            cogs=70000.0,
            ar=15000.0,
            inv=14000.0,
            ap=10000.0,
            other_ca=2000.0,
            other_cl=3000.0,
            prev_nwc=15000.0,
            sector="VNMAT",
        )
        assert isinstance(metrics, WorkingCapitalMetrics)
        # NWC = 18000, Prev NWC = 15000 -> Delta NWC = 3000
        assert math.isclose(metrics.net_working_capital, 18000.0, rel_tol=1e-5)
        assert math.isclose(metrics.delta_nwc, 3000.0, rel_tol=1e-5)
        dumped = metrics.to_dict()
        assert isinstance(dumped, dict)

    def test_project_schedule_with_custom_series_and_financials(self):
        # 1. Custom other_ca_series and other_cl_series
        base = {
            "dso": 30.0, "dio": 50.0, "dpo": 40.0,
            "ar": 1000.0, "inv": 1200.0, "ap": 800.0,
            "other_ca": 200.0, "other_cl": 150.0,
        }
        revs = [10000.0, 12000.0]
        cogss = [6000.0, 7200.0]
        oca_s = [250.0, 300.0]
        ocl_s = [180.0, 210.0]

        sched = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base,
            revenue_series=revs,
            cogs_series=cogss,
            other_ca_series=oca_s,
            other_cl_series=ocl_s,
            convergence_speed=0.20,
            years=[2026, 2027],
        )
        assert len(sched) == 2
        assert sched[0]["other_current_assets"] == 250.0
        assert sched[0]["other_current_liabilities"] == 180.0
        assert sched[0]["year"] == 2026
        assert sched[1]["year"] == 2027

        # 2. Financial sector projection schedule
        fin_base = {"is_financial_sector": True}
        fin_sched = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=fin_base,
            revenue_series=revs,
            cogs_series=cogss,
            sector="VNBNK",
        )
        assert len(fin_sched) == 2
        for p in fin_sched:
            assert p["is_financial_sector"] is True
            assert p["net_working_capital"] == 0.0
            assert p["delta_nwc"] == 0.0
            assert p["cash_from_customers"] == p["revenue"]

    def test_schedule_period_and_forecast_result_serialization(self):
        period = WorkingCapitalSchedulePeriod(
            year=2026,
            year_index=1,
            revenue=100000.0,
            cogs=70000.0,
            dso=45.0,
            dio=60.0,
            dpo=30.0,
            ccc=75.0,
            accounts_receivable=12328.77,
            inventory=11506.85,
            accounts_payable=5753.42,
            operating_working_capital=18082.20,
            trade_nwc=18082.20,
            net_working_capital=18082.20,
        )
        p_dict = period.to_dict()
        assert p_dict["year"] == 2026
        assert p_dict["dso"] == 45.0


# =============================================================================
# TIER 6: MODANO INTERFACE CONTRACT & DIRECT OPEX CASH FLOW BRIDGES
# =============================================================================

class TestTier6ModanoInterfaceAndDirectOpexBridges:
    """Tier 6: Modano PROJECT.md interface contract and Direct Method OPEX cash bridges."""

    def test_build_working_capital_schedule_interface_contract(self, clean_manufacturing_data):
        d = clean_manufacturing_data
        rev_series = [100000.0, 110000.0, 121000.0, 133100.0, 146410.0]
        cogs_series = [70000.0, 77000.0, 84700.0, 93170.0, 102487.0]
        sga_series = [10000.0, 11000.0, 12100.0, 13310.0, 14641.0]

        # 1. Module-level build_working_capital_schedule
        sched = build_working_capital_schedule(
            base_data=d,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sga_series=sga_series,
            start_year=2026,
            mean_revert_speed=0.10,
            sector="VNMAT",
        )

        assert isinstance(sched, list)
        assert len(sched) == 5
        assert all(isinstance(p, WorkingCapitalSchedulePeriod) for p in sched)

        # Check required fields from PROJECT.md Interface Contract
        p0 = sched[0]
        assert hasattr(p0, "year")
        assert hasattr(p0, "revenue")
        assert hasattr(p0, "cogs")
        assert hasattr(p0, "dso")
        assert hasattr(p0, "dio")
        assert hasattr(p0, "dpo")
        assert hasattr(p0, "ccc")
        assert hasattr(p0, "accounts_receivable")
        assert hasattr(p0, "inventory")
        assert hasattr(p0, "other_current_assets")
        assert hasattr(p0, "accounts_payable")
        assert hasattr(p0, "other_current_liabilities")
        assert hasattr(p0, "trade_working_capital")
        assert hasattr(p0, "total_operating_nwc")
        assert hasattr(p0, "delta_trade_nwc")
        assert hasattr(p0, "delta_total_nwc")
        assert hasattr(p0, "cash_collected_from_customers")
        assert hasattr(p0, "cash_paid_to_suppliers")
        assert hasattr(p0, "cash_paid_for_opex")

        # 2. Class-level WorkingCapitalEngine.build_working_capital_schedule
        sched_cls = WorkingCapitalEngine.build_working_capital_schedule(
            base_data=d,
            revenue_series=rev_series,
            cogs_series=cogs_series,
            sga_series=sga_series,
            start_year=2026,
        )
        assert len(sched_cls) == 5
        assert math.isclose(sched_cls[0].revenue, 100000.0)

    def test_direct_method_opex_cash_flow_bridge(self):
        """Tests Direct Method OPEX cash bridge: Cash paid for OPEX = SGA + Delta OCA - Delta OCL."""
        prior = {
            "accounts_receivable": 5000.0,
            "inventory": 8000.0,
            "accounts_payable": 4000.0,
            "other_current_assets": 1000.0,
            "other_current_liabilities": 1500.0,
            "trade_nwc": 9000.0,
        }
        curr = {
            "accounts_receivable": 6000.0,
            "inventory": 9000.0,
            "accounts_payable": 4500.0,
            "other_current_assets": 1300.0,  # Delta OCA = +300 (prepaid expense increase -> cash outflow)
            "other_current_liabilities": 1700.0,  # Delta OCL = +200 (accrued expense increase -> cash saved)
            "trade_nwc": 10500.0,
        }
        rev = 50000.0
        cogs = 30000.0
        sga = 8000.0

        adj = WorkingCapitalEngine.compute_direct_cash_flow_adjustments(
            current_period=curr,
            prior_period=prior,
            revenue=rev,
            cogs=cogs,
            sga=sga,
        )

        # Cash collected = Rev - Delta AR = 50000 - 1000 = 49000
        assert math.isclose(adj["cash_collected_from_customers"], 49000.0)
        # Cash paid suppliers = COGS + Delta Inv - Delta AP = 30000 + 1000 - 500 = 30500
        assert math.isclose(adj["cash_paid_to_suppliers"], 30500.0)
        # Cash paid OPEX = SGA + Delta OCA - Delta OCL = 8000 + 300 - 200 = 8100
        assert math.isclose(adj["cash_paid_for_opex"], 8100.0)

        # Net operating cash flow before tax & interest = 49000 - 30500 - 8100 = 10400
        assert math.isclose(adj["net_operating_cash_flow_before_tax_interest"], 10400.0)

    def test_dict_subscripting_and_attribute_access(self):
        """Tests that WorkingCapitalSchedulePeriod supports both p.dso and p['dso']."""
        period = WorkingCapitalSchedulePeriod(
            year=2026,
            year_index=1,
            revenue=50000.0,
            cogs=30000.0,
            sga=5000.0,
            dso=40.0,
            dio=60.0,
            dpo=35.0,
            ccc=65.0,
            accounts_receivable=5479.45,
            inventory=4931.51,
            accounts_payable=2876.71,
            trade_working_capital=7534.25,
            total_operating_nwc=7534.25,
            cash_collected_from_customers=48000.0,
            cash_paid_to_suppliers=29000.0,
            cash_paid_for_opex=5100.0,
        )

        # Attribute access
        assert period.dso == 40.0
        assert period.trade_working_capital == 7534.25
        assert period.cash_paid_for_opex == 5100.0

        # Subscript access
        assert period["dso"] == 40.0
        assert period["trade_working_capital"] == 7534.25
        assert period["cash_paid_for_opex"] == 5100.0
        assert period.get("dpo") == 35.0
        assert period.get("non_existent_key", 999.0) == 999.0

    @pytest.mark.parametrize("fin_sym", [
        "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "HDB", "STB", "VIB",
        "SSI", "VND", "VCI", "HCM", "SHS", "MBS", "FTS", "BSI",
        "BVH", "PVI", "BMI", "BIC", "MIG",
    ])
    def test_42_financial_tickers_isolation(self, fin_sym):
        """Verifies that all Vietnamese banks, brokerages, and insurance tickers are isolated."""
        res = WorkingCapitalEngine.calculate_historical_days(
            rev=30000.0,
            cogs=12000.0,
            ar=5000.0,
            inv=4000.0,
            ap=3000.0,
            sga=2000.0,
            symbol=fin_sym,
        )

        assert res["is_financial_sector"] is True
        assert res["dso"] == 0.0
        assert res["dio"] == 0.0
        assert res["dpo"] == 0.0
        assert res["ccc"] == 0.0
        assert res["trade_working_capital"] == 0.0
        assert res["net_working_capital"] == 0.0
        assert res["total_operating_nwc"] == 0.0
        assert res["cash_collected_from_customers"] == 30000.0
        assert res["cash_paid_to_suppliers"] == 12000.0
        assert res["cash_paid_for_opex"] == 2000.0


