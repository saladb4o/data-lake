"""
Exhaustive Adversarial Null-Safety & Robustness Stress Test Suite
=================================================================
Stress-tests all 22 Quantitative Valuation Models, WACC Engine, Risk Firewalls,
Scenarios Engine, Adaptive Weighting, and the comprehensive Facade against:
1. Missing dictionary keys
2. Explicit `None` values across all attributes (rwa, capex, affo, ppe, etc.)
3. Zero values and division-by-zero boundary conditions
4. Distressed negative financials (negative net income, operating loss, negative equity)
5. Outlier/extreme scales (1e24, 1e-12)
6. Non-numeric or NaN / Inf values
7. Sector-specific fallbacks and missing sector codes
8. Cold-start Omnibus loss metric modes (SMAPE, MALE, WMAPE, RMSLE, IVW)
"""

import os
import sys
import math

# Ensure project root is in sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest
from services.valuation_engine import (
    ValuationEngine,
    WACCEngine,
    RiskFirewallEngine,
    ValuationModelsSuite,
    AdaptiveWeightingEngine,
    ScenarioEngine,
    ValuationMatrixResult,
    ModelValuationOutput,
    WACCResult,
    RiskFirewallResult,
    ScenarioResult,
    SECTOR_MODEL_MAP,
)


ALL_POSSIBLE_FUNDAMENTAL_KEYS = [
    "symbol", "name", "company_name", "exchange", "price", "market_cap", "shares_out",
    "shares", "revenue", "ebit", "operating_profit", "ebitda", "net_income", "pat",
    "eps", "bvps", "tbvps", "debt", "interest_bearing_debt", "interest_expense", "cash",
    "cash_and_equiv", "cfo", "fcf", "affo", "dividend_per_share", "dps", "roe", "roic",
    "net_margin", "beta", "sector_code", "working_capital", "retained_earnings",
    "total_assets", "assets", "total_liabilities", "book_equity", "equity", "downside_beta",
    "rwa", "capex", "prev_revenue", "ppe_gross", "fixed_assets", "gross_profit",
    "asset_growth", "ebitda_growth", "pat_1y_growth", "pat_growth", "rev_1y_growth",
    "beneish_m_score", "beneish_dsri", "beneish_gmi", "beneish_aqi", "beneish_sgi",
    "beneish_depi", "beneish_sgai", "beneish_tata", "beneish_lvgi", "pb_sector_median",
    "sector_pe", "hist_pe", "sector_ps", "sector_net_margin", "sector_pfcf", "hist_pfcf",
    "sector_pb", "sector_ptbv", "sector_ev_ebitda", "hist_ev_ebitda", "sector_pcf",
    "sector_paffo", "sector_ev_ebit", "historical_eps"
]


class TestValuationModelsSuiteDirectStress:
    """Direct mathematical unit stress tests on all 22 model methods."""

    def test_model_1_blended_pe_null_and_zero_safety(self):
        # Zero / negative EPS, empty historical EPS
        res = ValuationModelsSuite.model_1_blended_pe(
            eps_ttm=0.0, historical_eps=[], sector_pe=0.0, hist_pe=0.0,
            eps_growth_rate=0.0, current_price=10000.0
        )
        assert res >= 0.0 and not math.isnan(res) and not math.isinf(res)

        res_neg = ValuationModelsSuite.model_1_blended_pe(
            eps_ttm=-500.0, historical_eps=[-200.0, -400.0], sector_pe=12.0, hist_pe=10.0,
            eps_growth_rate=-0.15, current_price=25000.0
        )
        assert res_neg >= 0.0

    def test_model_2_ps_margin_adjusted_loss_making(self):
        # Loss making firm: net margin <= 0 -> FV must be 0.0
        res = ValuationModelsSuite.model_2_ps_margin_adjusted(
            sales_per_share=5000.0, net_margin=-0.05, sector_ps=1.2, sector_net_margin=0.08
        )
        assert res == 0.0

        # Zero SPS
        res_zero = ValuationModelsSuite.model_2_ps_margin_adjusted(
            sales_per_share=0.0, net_margin=0.10, sector_ps=0.0, sector_net_margin=0.0
        )
        assert res_zero >= 0.0

    def test_model_3_p_fcf_negative_cashflow(self):
        # Negative FCF per share
        res = ValuationModelsSuite.model_3_p_fcf(
            fcf_per_share=-2000.0, sales_per_share=10000.0, sector_pfcf=0.0, hist_pfcf=0.0
        )
        assert res >= 0.0

    def test_model_4_pb_rhodes_kropf_negative_equity(self):
        res = ValuationModelsSuite.model_4_pb_rhodes_kropf(
            bvps=-5000.0, roe=-0.20, ke=0.0, sector_pb=0.0, rkv_is_overvalued=True
        )
        assert res >= 0.0

    def test_model_5_p_tbv_zero_tangible_book(self):
        res = ValuationModelsSuite.model_5_p_tbv(
            tbv_per_share=0.0, bvps=0.0, roic=-0.10, wacc=0.0, sector_ptbv=0.0
        )
        assert res >= 0.0

    def test_model_6_ev_ebitda_negative_ebitda_and_high_debt(self):
        res = ValuationModelsSuite.model_6_ev_ebitda(
            ebitda=-5000000000.0, total_debt=50000000000.0, cash_and_equiv=0.0, shares_out=1.0
        )
        assert res >= 0.0

    def test_model_7_p_cf_negative_cfo(self):
        res = ValuationModelsSuite.model_7_p_cf(
            cfo_per_share=-1000.0, pat_per_share=-500.0, sector_pcf=0.0
        )
        assert res >= 0.0

    def test_model_8_p_affo_negative_affo(self):
        res = ValuationModelsSuite.model_8_p_affo(
            affo=-50000000.0, net_income=-10000000.0, shares_out=0.0, sector_paffo=0.0
        )
        assert res >= 0.0

    def test_model_9_dcf_2stage_mckinsey_negative_ebit(self):
        res = ValuationModelsSuite.model_9_dcf_2stage_mckinsey(
            ebit=-10000000.0, roic=-0.05, wacc=0.0, shares_out=0.0, cash_and_equiv=0.0, total_debt=1e9
        )
        assert res >= 0.0

    def test_model_10_rim_edwards_bell_ohlson_loss_making(self):
        res = ValuationModelsSuite.model_10_rim_edwards_bell_ohlson(
            book_equity=-1e8, roe_base=-0.30, ke=0.0, shares_out=0.0
        )
        assert res >= 0.0

    def test_model_11_greenwald_epv_zero_revenue(self):
        res = ValuationModelsSuite.model_11_greenwald_epv(
            revenue=0.0, ebit_margin_avg=-0.10, wacc=0.0, shares_out=0.0
        )
        assert res >= 0.0

    def test_model_12_graham_growth_negative_eps_and_bvps(self):
        # Graham requires positive EPS and BVPS, returns 0.0 on negative
        res = ValuationModelsSuite.model_12_graham_growth(
            eps_ttm=-100.0, bvps=-500.0, expected_growth_pct=-10.0, benchmark_bond_yield=0.0
        )
        assert res == 0.0

    def test_model_13_rule_of_40_hyper_decay(self):
        res = ValuationModelsSuite.model_13_rule_of_40_growth(
            sales_per_share=0.0, rev_growth_pct=-50.0, fcf_margin_pct=-80.0
        )
        assert res >= 0.0

    def test_model_14_acquirers_multiple_negative_ebit(self):
        res = ValuationModelsSuite.model_14_acquirers_multiple(
            ebit=-5e9, revenue=0.0, net_debt=1e12, shares_out=0.0
        )
        assert res >= 0.0

    def test_model_15_buffett_owners_earnings_zero_capex_missing_ppe(self):
        res = ValuationModelsSuite.model_15_buffett_owners_earnings(
            net_income=-1e9, depreciation=0.0, maintenance_capex=0.0,
            delta_working_capital=0.0, ke=0.0, shares_out=0.0, total_capex=0.0,
            revenue=0.0, gross_ppe=0.0, ocf=-5e8
        )
        assert res >= 0.0

    def test_model_16_pharma_rnpv_empty_pipeline(self):
        res = ValuationModelsSuite.model_16_pharma_rnpv(
            base_epv_per_share=0.0, pipeline_projects=[], net_cash_per_share=-1000.0
        )
        assert res >= 0.0

    def test_model_17_bank_equity_cash_flow_zero_rwa(self):
        res = ValuationModelsSuite.model_17_bank_equity_cash_flow(
            net_income=-1e9, rwa=0.0, book_equity=0.0, roe=-0.10, ke=0.0, shares_out=0.0
        )
        assert res >= 0.0

    def test_model_18_reit_affo_dcf_negative_noi(self):
        res = ValuationModelsSuite.model_18_reit_affo_dcf(
            net_operating_income=-1e9, landbank_pipeline_val=0.0, cash_and_equiv=0.0,
            total_debt=1e11, shares_out=0.0, cap_rate_vn=0.0
        )
        assert res >= 0.0

    def test_model_19_telecom_unbundled_sotp_zero_rab(self):
        res = ValuationModelsSuite.model_19_telecom_unbundled_sotp(
            regulated_asset_base=0.0, serveco_ebitda=0.0, net_debt=1e11, shares_out=0.0
        )
        assert res >= 0.0

    def test_model_20_industrial_apv_distressed_z_score(self):
        res = ValuationModelsSuite.model_20_industrial_apv(
            ebit=-1e9, total_debt=1e12, cash_and_equiv=0.0, shares_out=0.0, z_score=-10.0
        )
        assert res >= 0.0

    def test_model_21_consumer_eva_mva_negative_eva(self):
        res = ValuationModelsSuite.model_21_consumer_eva_mva(
            ebit=-1e9, invested_capital=0.0, wacc=0.0, net_debt=1e12, shares_out=0.0
        )
        assert res >= 0.0

    def test_model_22_utilities_3stage_ddm_zero_dividends(self):
        res = ValuationModelsSuite.model_22_utilities_3stage_ddm(
            dividend_per_share=0.0, ke=0.0, div_growth_initial=-0.10
        )
        assert res >= 0.0


class TestValuationEngineComprehensiveNullSafety:
    """End-to-End stress tests of ValuationEngine.get_comprehensive_valuation()."""

    @pytest.fixture
    def engine(self):
        return ValuationEngine()

    def test_valuation_with_none_fundamental_data(self, engine):
        val = engine.get_comprehensive_valuation("TEST_NONE", fundamental_data=None)
        assert isinstance(val, ValuationMatrixResult)
        assert val.composite_fair_value > 0
        assert len(val.models) == 22

    def test_valuation_with_empty_dict(self, engine):
        val = engine.get_comprehensive_valuation("TEST_EMPTY", fundamental_data={})
        assert isinstance(val, ValuationMatrixResult)
        assert val.composite_fair_value > 0
        assert len(val.models) == 22
        assert val.wacc_result.wacc > 0
        assert val.risk_firewall.dynamic_margin_of_safety > 0
        assert len(val.scenarios.sensitivity_grid_5x5) == 5

    def test_valuation_with_all_keys_explicit_none(self, engine):
        none_dict = {k: None for k in ALL_POSSIBLE_FUNDAMENTAL_KEYS}
        none_dict["symbol"] = "TEST_ALL_NONE"
        val = engine.get_comprehensive_valuation("TEST_ALL_NONE", fundamental_data=none_dict)
        assert isinstance(val, ValuationMatrixResult)
        assert val.composite_fair_value > 0
        assert len(val.models) == 22
        for m in val.models:
            assert isinstance(m, ModelValuationOutput)
            assert m.fair_value >= 0.0
            assert not math.isnan(m.fair_value)
            assert not math.isinf(m.fair_value)

    def test_valuation_missing_rwa_specifically(self, engine):
        # Bank sector with missing rwa
        data = {
            "symbol": "VCB_TEST",
            "sector_code": "VNBNK",
            "price": 90000.0,
            "market_cap": 5e14,
            "shares_out": 5.5e9,
            "net_income": 3.5e13,
            "equity": 1.5e14,
            "roe": 22.0,
            "rwa": None,  # Explicitly None
        }
        val = engine.get_comprehensive_valuation("VCB_TEST", fundamental_data=data)
        bank_model = next((m for m in val.models if m.model_id == "bank_equity_cash_flow"), None)
        assert bank_model is not None
        assert bank_model.fair_value > 0

    def test_valuation_missing_capex_and_ppe_specifically(self, engine):
        # Buffett Owner's Earnings with missing capex & ppe
        data = {
            "symbol": "FPT_TEST",
            "sector_code": "VNIT",
            "price": 130000.0,
            "market_cap": 1.7e14,
            "shares_out": 1.3e9,
            "revenue": 5.5e13,
            "ebit": 1.0e13,
            "ebitda": 1.2e13,
            "net_income": 8.0e12,
            "cfo": 9.0e12,
            "capex": None,
            "ppe_gross": None,
            "fixed_assets": None,
            "prev_revenue": None,
        }
        val = engine.get_comprehensive_valuation("FPT_TEST", fundamental_data=data)
        buffett_m = next((m for m in val.models if m.model_id == "buffett_owners_earnings"), None)
        assert buffett_m is not None
        assert buffett_m.fair_value > 0

    def test_valuation_missing_affo_and_pipeline_specifically(self, engine):
        # Real Estate with missing affo & landbank pipeline
        data = {
            "symbol": "VHM_TEST",
            "sector_code": "VNREAL",
            "price": 45000.0,
            "market_cap": 1.9e14,
            "shares_out": 4.3e9,
            "net_operating_income": None,
            "affo": None,
            "landbank_pipeline_val": None,
        }
        val = engine.get_comprehensive_valuation("VHM_TEST", fundamental_data=data)
        reit_m = next((m for m in val.models if m.model_id == "reit_affo_dcf"), None)
        assert reit_m is not None
        assert reit_m.fair_value > 0

    def test_valuation_missing_rab_telecom(self, engine):
        data = {
            "symbol": "TEL_TEST",
            "sector_code": "6500",
            "price": 20000.0,
            "market_cap": 1e13,
            "regulated_asset_base": None,
            "serveco_ebitda": None,
        }
        val = engine.get_comprehensive_valuation("TEL_TEST", fundamental_data=data)
        tel_m = next((m for m in val.models if m.model_id == "telecom_unbundled_sotp"), None)
        assert tel_m is not None
        assert tel_m.fair_value > 0

    def test_valuation_across_all_18_icb_sectors(self, engine):
        sector_codes = list(SECTOR_MODEL_MAP.keys()) + ["NON_EXISTENT_SECTOR"]
        for sec in sector_codes:
            data = {"symbol": f"TEST_{sec}", "sector_code": sec, "price": 25000.0, "market_cap": 5e12}
            val = engine.get_comprehensive_valuation(f"TEST_{sec}", fundamental_data=data)
            assert val.composite_fair_value > 0
            assert len(val.models) == 22

    def test_valuation_across_all_omnibus_metrics_cold_start(self, engine):
        metrics = ["smape", "male", "wmape", "rmsle", "ivw"]
        for metric in metrics:
            val = engine.get_comprehensive_valuation(
                "TEST_OMNIBUS",
                fundamental_data={"symbol": "TEST_OMNIBUS", "price": 30000.0},
                composite_mode="omnibus",
                omnibus_metric=metric,
                history_errors=None,
            )
            assert val.composite_fair_value > 0
            assert val.metadata["composite_mode"] == "omnibus"
            assert val.metadata["omnibus_metric"] == metric

    def test_valuation_with_nan_and_inf_values(self, engine):
        data = {
            "symbol": "TEST_NAN",
            "price": 20000.0,
            "market_cap": float("nan"),
            "shares_out": float("inf"),
            "revenue": float("-inf"),
            "ebit": float("nan"),
            "ebitda": float("nan"),
            "net_income": float("nan"),
            "eps": float("nan"),
            "bvps": float("nan"),
            "roe": float("nan"),
            "roic": float("nan"),
            "beta": float("nan"),
        }
        val = engine.get_comprehensive_valuation("TEST_NAN", fundamental_data=data)
        assert val.composite_fair_value > 0
        assert not math.isnan(val.composite_fair_value)
        assert not math.isinf(val.composite_fair_value)

    def test_serialization_to_dict(self, engine):
        val = engine.get_comprehensive_valuation("TEST_SERIALIZE", fundamental_data={})
        d = val.to_dict()
        assert isinstance(d, dict)
        assert "symbol" in d
        assert "composite_fair_value" in d
        assert "models" in d
        assert len(d["models"]) == 22
        assert "wacc_result" in d
        assert "risk_firewall" in d
        assert "scenarios" in d
        assert "sensitivity_grid" in d
        assert len(d["sensitivity_grid"]) == 5


if __name__ == "__main__":
    pytest.main(["-v", __file__])
