"""
Unit and Integration Tests for Valuation Engine & Risk Firewalls.
Covers WACC 5-Factor VN CAPM, Damodaran synthetic ratings, 22 Models,
Scenarios, 2D Grid, IVW Adaptive Weighting, and Edge Cases.
"""

import pytest
import math
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
    DEFAULT_RF,
    DEFAULT_ERP,
)


@pytest.fixture
def sample_fundamental_data():
    return {
        "symbol": "HPG",
        "name": "Hoa Phat Group",
        "exchange": "HOSE",
        "price": 28500.0,
        "market_cap": 165000000000000.0, # 165,000B VND
        "shares_out": 5800000000.0,
        "revenue": 140000000000000.0,
        "ebit": 20000000000000.0,
        "ebitda": 26000000000000.0,
        "net_income": 15000000000000.0,
        "eps": 2586.0,
        "bvps": 19500.0,
        "tbvps": 18500.0,
        "debt": 55000000000000.0,
        "interest_bearing_debt": 50000000000000.0,
        "interest_expense": 3500000000000.0,
        "cash": 30000000000000.0,
        "cfo": 18000000000000.0,
        "fcf": 12000000000000.0,
        "affo": 14000000000000.0,
        "dividend_per_share": 800.0,
        "roe": 14.5,
        "roic": 13.5,
        "net_margin": 10.7,
        "beta": 1.15,
        "sector_code": "VNMAT",
        "working_capital": 35000000000000.0,
        "retained_earnings": 40000000000000.0,
        "total_assets": 190000000000000.0,
        "total_liabilities": 75000000000000.0,
        "book_equity": 115000000000000.0,
        "downside_beta": 1.25,
    }


class TestWACCEngine:
    def test_wacc_calculation_large_cap(self, sample_fundamental_data):
        engine = WACCEngine()
        res = engine.calculate(
            market_cap=sample_fundamental_data["market_cap"],
            interest_bearing_debt=sample_fundamental_data["interest_bearing_debt"],
            ebit=sample_fundamental_data["ebit"],
            interest_expense=sample_fundamental_data["interest_expense"],
            beta_raw=sample_fundamental_data["beta"],
            roe=sample_fundamental_data["roe"],
            pb=1.46,
            pb_sector_median=1.50,
            adtv=50e9,
        )
        assert isinstance(res, WACCResult)
        assert 0.085 <= res.wacc <= 0.185
        assert 0.085 <= res.cost_of_equity <= 0.220
        assert res.cost_of_debt_after_tax < res.cost_of_debt_pre_tax
        assert res.synthetic_rating in ["AAA", "AA", "A+", "A", "A-", "BBB", "BB+", "BB", "B+", "B", "B-", "CCC", "CC", "D"]
        assert math.isclose(res.equity_weight + res.debt_weight, 1.0, rel_tol=1e-3)

    def test_wacc_small_cap_high_distress(self):
        engine = WACCEngine()
        res = engine.calculate(
            market_cap=500e9, # 500B VND (Small/Micro Cap)
            interest_bearing_debt=1000e9,
            ebit=10e9,
            interest_expense=100e9, # ICR = 0.1 (Distressed)
            beta_raw=1.8,
            roe=-5.0,
            pb=0.5,
            pb_sector_median=1.5,
            adtv=1e9,
        )
        assert res.synthetic_rating == "D"
        assert res.credit_spread == 0.1250 # 12.5% distress spread
        assert res.wacc >= 0.085


class TestRiskFirewallEngine:
    def test_altman_z_double_prime_safe(self, sample_fundamental_data):
        z, zone = RiskFirewallEngine.calculate_altman_z_double_prime(
            working_capital=sample_fundamental_data["working_capital"],
            retained_earnings=sample_fundamental_data["retained_earnings"],
            ebit=sample_fundamental_data["ebit"],
            book_equity=sample_fundamental_data["book_equity"],
            total_assets=sample_fundamental_data["total_assets"],
            total_liabilities=sample_fundamental_data["total_liabilities"],
        )
        assert z > 0
        assert zone in ["safe", "grey", "distress"]

    def test_beneish_m_score_detection(self):
        # Normal safe non-manipulator
        m_safe, status_safe = RiskFirewallEngine.calculate_beneish_m_score(
            dsri=1.0, gmi=1.0, aqi=1.0, sgi=1.0, depi=1.0, sgai=1.0, tata=-0.02, lvgi=1.0
        )
        assert m_safe < -1.78
        assert status_safe == "safe"

        # Inflated earnings manipulator
        m_bad, status_bad = RiskFirewallEngine.calculate_beneish_m_score(
            dsri=2.5, gmi=1.8, aqi=2.0, sgi=2.2, depi=1.5, sgai=1.5, tata=0.25, lvgi=2.0
        )
        assert m_bad >= -1.78
        assert status_bad == "manipulator"

    def test_four_quadrant_matrix(self):
        assert RiskFirewallEngine.evaluate_four_quadrants(3.5, -2.5) == "safe_institutional"
        assert RiskFirewallEngine.evaluate_four_quadrants(0.8, -2.5) == "distressed_turnaround"
        assert RiskFirewallEngine.evaluate_four_quadrants(0.5, -1.2) == "toxic_exclusion"
        assert RiskFirewallEngine.evaluate_four_quadrants(3.0, -1.2) == "forensic_trap"

    def test_rhodes_kropf_decomposition(self):
        rkv = RiskFirewallEngine.calculate_rhodes_kropf(
            market_cap=150e12,
            book_equity=100e12,
            roe=0.15,
            ke=0.12,
            sector_pb=1.4,
        )
        assert "ln_mb" in rkv
        assert "firm_misvaluation" in rkv
        assert "sector_time_series_error" in rkv
        assert "long_run_sector_growth" in rkv
        # Sum of decomposition equals ln(M/B)
        decomp_sum = rkv["firm_misvaluation"] + rkv["sector_time_series_error"] + rkv["long_run_sector_growth"]
        assert math.isclose(decomp_sum, rkv["ln_mb"], abs_tol=1e-4)

    def test_dynamic_margin_of_safety(self):
        mos_low_beta = RiskFirewallEngine.calculate_dynamic_mos(downside_beta=0.7, altman_zone="safe", beneish_status="safe")
        mos_high_beta = RiskFirewallEngine.calculate_dynamic_mos(downside_beta=1.8, altman_zone="grey", beneish_status="manipulator")
        assert mos_high_beta > mos_low_beta
        assert 0.10 <= mos_low_beta <= 0.60
        assert 0.10 <= mos_high_beta <= 0.60


class TestValuationEngineSuite:
    def test_all_22_models_calculated(self, sample_fundamental_data):
        engine = ValuationEngine()
        models = engine.calculate_all_models("HPG", sample_fundamental_data)
        assert len(models) == 22
        for m in models:
            assert isinstance(m, ModelValuationOutput)
            assert m.fair_value >= 0.0
            assert m.fair_value <= sample_fundamental_data["price"] * 10.0
            assert m.status in [
                "ACTIVE", "INACTIVE", "BYPASSED", "OUTLIER_REJECTED",
                "INSUFFICIENT_DATA",   # a driver was imputed, not observed
                "NOT_APPLICABLE",      # the model declined (no earnings, no book equity...)
            ]

    def test_comprehensive_valuation_flow(self, sample_fundamental_data):
        engine = ValuationEngine()
        result = engine.get_comprehensive_valuation("HPG", sample_fundamental_data)
        assert result.symbol == "HPG"
        assert result.composite_fair_value > 0.0
        assert result.valuation_status in ["UNDERVALUED", "FAIRLY_VALUED", "OVERVALUED"]
        assert len(result.models) == 22
        assert len(result.scenarios.sensitivity_grid_5x5) == 5
        assert len(result.scenarios.sensitivity_grid_5x5[0]) == 5
        assert result.scenarios.bear_fair_value <= result.scenarios.base_fair_value <= result.scenarios.bull_fair_value

    def test_edge_case_negative_earnings_and_fcf(self, sample_fundamental_data):
        bad_data = sample_fundamental_data.copy()
        bad_data["ebit"] = -5000000000000.0
        bad_data["net_income"] = -8000000000000.0
        bad_data["eps"] = -1379.0
        bad_data["fcf"] = -10000000000000.0
        bad_data["cfo"] = -2000000000000.0

        engine = ValuationEngine()
        result = engine.get_comprehensive_valuation("HPG_DISTRESSED", bad_data)
        assert result.composite_fair_value >= 0.0
        for m in result.models:
            assert m.fair_value >= 0.0, f"Model {m.model_id} produced negative FV: {m.fair_value}"

    def test_wacc_negative_ebit_damodaran_rating(self):
        engine = WACCEngine()
        res = engine.calculate(
            market_cap=10000e9,
            interest_bearing_debt=2000e9,
            ebit=-500e9, # Negative operating income
            interest_expense=0.0, # Zero interest
            beta_raw=1.2,
        )
        assert res.synthetic_rating == "D"
        assert res.credit_spread == 0.1250

    def test_modern_graham_negative_eps_zero(self):
        fv_neg = ValuationModelsSuite.model_12_graham_growth(
            eps_ttm=-500.0,
            bvps=15000.0,
            expected_growth_pct=10.0,
            benchmark_bond_yield=5.0,
            current_price=25000.0,
        )
        assert fv_neg == 0.0

    def test_modern_graham_revised_growth(self):
        fv = ValuationModelsSuite.model_12_graham_growth(
            eps_ttm=2000.0,
            bvps=20000.0,
            expected_growth_pct=10.0,
            benchmark_bond_yield=5.0,
            current_price=25000.0,
        )
        # Classic = sqrt(22.5 * 2000 * 20000) = 30000
        # Growth = 2000 * (8.5 + 1.5*10) * (4.4 / 5.0) = 2000 * 23.5 * 0.88 = 41360
        # Blended = (30000 + 41360) / 2 = 35680
        assert 35000 <= fv <= 36000


class TestAdaptiveWeighting:
    def test_iqr_outlier_rejection(self):
        values = [25000.0, 26000.0, 27000.0, 28000.0, 26500.0, 150000.0] # 150,000 is an extreme outlier
        kept_vals, kept_idx = AdaptiveWeightingEngine.filter_outliers_iqr(values)
        assert 150000.0 not in kept_vals
        assert len(kept_vals) == 5

    def test_error_metrics_calculation(self):
        preds = [30000.0, 32000.0, 31000.0, 33000.0]
        actuals = [29000.0, 31500.0, 31200.0, 32500.0]
        metrics = AdaptiveWeightingEngine.compute_error_metrics(preds, actuals)
        assert "smape" in metrics
        assert "male" in metrics
        assert "wmape" in metrics
        assert "rmsle" in metrics
        assert "variance" in metrics
        assert metrics["smape"] > 0.0
        assert metrics["variance"] > 0.0

    def test_scale_free_ivw_evidence_ramp(self):
        active_models = ["model_a", "model_b"]
        active_vals = [30000.0, 32000.0]
        # model_a has only 3 quarters (below hard gate ramp threshold)
        # model_b has 12 quarters (full evidence)
        history = {
            "model_a": {"variance": 0.01, "n_obs": 3, "r2": 0.9},
            "model_b": {"variance": 0.01, "n_obs": 12, "r2": 0.9},
        }
        weights, rejected = AdaptiveWeightingEngine.calculate_weights(
            active_models=active_models,
            active_values=active_vals,
            historical_errors=history,
            composite_mode="omnibus",
            omnibus_metric="ivw",
        )
        assert weights["model_b"] > weights["model_a"]
        assert sum(weights.values()) == 1.0

    def test_rule_of_65_super_stock(self):
        # 30% rev growth + 15% FCF margin -> Rule X Score = 2*30 + 15 = 75% (Super-Stock >= 65%)
        fv_super = ValuationModelsSuite.model_13_rule_of_40_growth(
            sales_per_share=20000.0,
            rev_growth_pct=30.0,
            fcf_margin_pct=15.0,
            total_revenue=10000e9,
            net_debt=500e9,
            shares_out=1e8,
            current_price=80000.0,
        )
        # Target multiple = 12.0 + (75 - 65)*0.3 = 15.0x
        # EV = 15.0 * 10000e9 = 150000e9 -> Equity = 149500e9 / 1e8 = 1,495,000 clamped to 800,000
        assert fv_super > 500000.0

    def test_rhodes_kropf_vb_value_trap_detection(self):
        rkv_trap = RiskFirewallEngine.calculate_rhodes_kropf(
            market_cap=1000e9,
            book_equity=1200e9, # P/B = 0.83 < 1.5
            roe=0.03,          # Very low ROE -> Justified PB < 1.0 (V/B < 1.0)
            ke=0.12,
            sector_pb=1.2,
        )
        assert rkv_trap["is_value_trap"] is True
        assert rkv_trap["rkv_verdict"] == "VALUE TRAP (Deserved Discount)"

    def test_buffett_owners_earnings_capex_decomposition(self):
        fv = ValuationModelsSuite.model_15_buffett_owners_earnings(
            net_income=1000e9,
            depreciation=300e9,
            maintenance_capex=200e9,
            delta_working_capital=50e9,
            ke=0.12,
            shares_out=1e8,
            total_capex=400e9,
            revenue=5000e9,
            prev_revenue=4000e9, # Rev Growth 1000e9
            gross_ppe=2000e9,    # PPE ratio = 0.40 -> Growth CapEx = 400e9, Maint CapEx = 0
            ocf=1200e9,
            rf=0.03,
            current_price=50000.0,
        )
        assert fv > 0.0

        # Also test end-to-end extraction in engine
        engine = ValuationEngine()
        res = engine.get_comprehensive_valuation("TEST_BUFFETT", {
            "price": 50000.0,
            "shares_out": 1e8,
            "revenue": 5000e9,
            "net_income": 1000e9,
            "cfo": 1200e9,
            "capex": 400e9,
            "ppe_gross": 2000e9,
            "ebit": 1100e9,
            "ebitda": 1400e9,
            "sector_code": "VNCONS",
        })
        assert "coupon_status" in res.buffett_coupon_spread
        assert "coupon_spread_pct" in res.buffett_coupon_spread
        assert "gpa_pass" in res.quant_quality_filters
        assert "status" in res.capital_allocation
        assert res.valuation_width_pct > 0.0

    def test_blended_mode_vs_omnibus_mode(self):
        engine = ValuationEngine()
        data = {
            "price": 30000.0,
            "shares_out": 1e8,
            "revenue": 5000e9,
            "net_income": 800e9,
            "sector_code": "VNFIN",
        }
        # 1. Blended Mode (Default)
        res_blended = engine.get_comprehensive_valuation("TCB", data, composite_mode="blended")
        assert res_blended.metadata["composite_mode"] == "blended"
        assert res_blended.composite_fair_value > 0.0

        # 2. Omnibus Mode (SMAPE)
        res_omnibus = engine.get_comprehensive_valuation("TCB", data, composite_mode="omnibus", omnibus_metric="smape")
        assert res_omnibus.metadata["composite_mode"] == "omnibus"
        assert res_omnibus.metadata["omnibus_metric"] == "smape"
        assert res_omnibus.composite_fair_value > 0.0

    def test_omnibus_metrics_all_supported(self):
        active_models = ["model_a", "model_b"]
        active_vals = [30000.0, 32000.0]
        history = {
            "model_a": {"smape": 5.0, "male": 0.05, "wmape": 4.0, "rmsle": 0.04, "variance": 0.005, "n_obs": 12, "r2": 0.9},
            "model_b": {"smape": 20.0, "male": 0.20, "wmape": 18.0, "rmsle": 0.18, "variance": 0.040, "n_obs": 12, "r2": 0.9},
        }
        for metric in ["smape", "male", "wmape", "rmsle", "ivw"]:
            w, rej = AdaptiveWeightingEngine.calculate_weights(
                active_models=active_models,
                active_values=active_vals,
                historical_errors=history,
                composite_mode="omnibus",
                omnibus_metric=metric,
            )
            # Model A has lower error across all metrics -> should have higher weight
            assert w["model_a"] > w["model_b"], f"Metric {metric} failed: {w}"
            assert round(sum(w.values()), 2) == 1.0
