"""
=============================================================================
COMPREHENSIVE TEST SUITE: THREE-STATEMENT FORECAST ENGINE (MILESTONE 3)
=============================================================================
Tiers Covered:
- Tier 1: Unit & Standard 3-Way Forecasting (P&L, BS, Direct CFS)
- Tier 2: Exact Mathematical Balance Sheet Closure (|TA - (TL + TE)| < 1e-5)
- Tier 3: Direct Method Cash Flow Conservation & Delta Cash Reconciliation
- Tier 4: Liquidity Distress Firewall, Negative Cash Detection & MOS Penalties (R3)
- Tier 5: Full VN30 Universe Integration & Sector Diversity (Manufacturing, Tech, Retail, Real Estate, Banks)
- Tier 6: Boundary Values, Extreme Distress, Zero Growth & Pydantic Contracts
=============================================================================
"""

import math
import pytest
from typing import Dict, List, Any

from services.three_statement_engine import (
    ThreeStatementEngine,
    ThreeStatementForecastResult,
    IncomeStatementForecast,
    BalanceSheetForecast,
    CashFlowForecast,
    LiquidityDistressCheck,
    forecast_3way,
    safe_div,
    clamp,
    sanitize_float,
)
from services.debt_capital_schedule_engine import CapitalAllocationPolicy
from services.stock_service import VN30_SYMBOLS


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def fpt_tech_profile():
    """FPT high-growth technology services baseline."""
    return {
        "symbol": "FPT",
        "company_name": "Công ty Cổ phần FPT",
        "sector": "VNIT",
        "market_cap": 180_000e9,
        "revenue": 52_000e9,
        "gross_margin": 0.38,
        "op_margin": 0.18,
        "net_margin": 0.15,
        "pb": 4.5,
        "de_ratio": 0.40,
        "total_equity": 40_000e9,
        "total_debt": 16_000e9,
        "cash": 8_000e9,
        "accounts_receivable": 9_500e9,
        "inventory": 2_100e9,
        "accounts_payable": 5_500e9,
        "net_ppe": 20_000e9,
    }


@pytest.fixture
def hpg_industrial_profile():
    """HPG capital-intensive steel manufacturing baseline."""
    return {
        "symbol": "HPG",
        "company_name": "Tập đoàn Hòa Phát",
        "sector": "VNMAT",
        "market_cap": 170_000e9,
        "revenue": 140_000e9,
        "gross_margin": 0.18,
        "op_margin": 0.12,
        "net_margin": 0.09,
        "pb": 1.6,
        "de_ratio": 0.65,
        "total_equity": 105_000e9,
        "total_debt": 68_000e9,
        "cash": 25_000e9,
        "accounts_receivable": 10_000e9,
        "inventory": 35_000e9,
        "accounts_payable": 18_000e9,
        "net_ppe": 85_000e9,
    }


@pytest.fixture
def mwg_retail_profile():
    """MWG retail profile with negative cash conversion cycle."""
    return {
        "symbol": "MWG",
        "company_name": "Công ty Cổ phần Đầu tư Thế Giới Di Động",
        "sector": "VNCOND",
        "market_cap": 75_000e9,
        "revenue": 120_000e9,
        "gross_margin": 0.22,
        "op_margin": 0.05,
        "net_margin": 0.035,
        "pb": 2.8,
        "de_ratio": 0.85,
        "total_equity": 26_000e9,
        "total_debt": 22_000e9,
        "cash": 12_000e9,
        "accounts_receivable": 4_000e9,
        "inventory": 25_000e9,
        "accounts_payable": 22_000e9,
        "net_ppe": 15_000e9,
    }


@pytest.fixture
def distressed_turnaround_profile():
    """Distressed corporate profile with severe cash burn."""
    return {
        "symbol": "NVL",
        "company_name": "Tập đoàn Đầu tư Địa ốc No Va",
        "sector": "VNREAL",
        "market_cap": 25_000e9,
        "revenue": 8_000e9,
        "gross_margin": 0.15,
        "op_margin": -0.05,
        "net_margin": -0.12,
        "pb": 0.7,
        "de_ratio": 2.50,
        "total_equity": 35_000e9,
        "total_debt": 87_000e9,
        "cash": 1_200e9,
        "accounts_receivable": 12_000e9,
        "inventory": 130_000e9,
        "accounts_payable": 25_000e9,
        "net_ppe": 5_000e9,
    }


# =============================================================================
# TIER 1: UNIT & STANDARD 3-WAY FORECASTING
# =============================================================================

class TestTier1StandardForecasting:
    """Tier 1: Standard 5-Year Financial Statement Forecasting."""

    def test_forecast_generates_5_full_periods(self, fpt_tech_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="FPT",
            base_data=fpt_tech_profile,
            start_year=2026,
        )
        assert len(result.forecast_years) == 5
        assert result.forecast_years == [2026, 2027, 2028, 2029, 2030]
        assert len(result.income_statement.revenue) == 5
        assert len(result.balance_sheet.total_assets) == 5
        assert len(result.cash_flow_statement.net_cfo) == 5

    def test_statement_link_npat_to_retained_earnings(self, hpg_industrial_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="HPG",
            base_data=hpg_industrial_profile,
            start_year=2026,
        )
        bs = result.balance_sheet
        is_stmt = result.income_statement
        cfs = result.cash_flow_statement
        
        for t in range(1, 5):
            expected_re = bs.retained_earnings[t-1] + is_stmt.npat[t] - cfs.dividends_paid[t]
            assert math.isclose(bs.retained_earnings[t], expected_re, rel_tol=1e-5, abs_tol=1e-3)

    def test_statement_link_delta_cash_to_balance_sheet_cash(self, mwg_retail_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="MWG",
            base_data=mwg_retail_profile,
            start_year=2026,
        )
        bs = result.balance_sheet
        cfs = result.cash_flow_statement
        
        for t in range(5):
            assert math.isclose(bs.cash[t], cfs.ending_cash[t], rel_tol=1e-5, abs_tol=1e-3)
            if t > 0:
                calc_delta = bs.cash[t] - bs.cash[t-1]
                assert math.isclose(cfs.net_change_in_cash[t], calc_delta, rel_tol=1e-5, abs_tol=1e-3)


# =============================================================================
# TIER 2: EXACT MATHEMATICAL BALANCE SHEET CLOSURE (|TA - (TL + TE)| < 1e-5)
# =============================================================================

class TestTier2BalanceSheetClosure:
    """Tier 2: Verification of Exact Balance Sheet Closure across all periods."""

    def test_fpt_exact_balance_closure(self, fpt_tech_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="FPT",
            base_data=fpt_tech_profile,
        )
        bs = result.balance_sheet
        assert result.all_years_balanced is True
        for t in range(5):
            diff = abs(bs.total_assets[t] - (bs.total_liabilities[t] + bs.total_equity[t]))
            assert bs.is_balanced[t] is True, f"Year {result.forecast_years[t]} balance discrepancy: {diff}"
            assert diff < 1.0 or (diff / max(bs.total_assets[t], 1.0)) < 1e-5

    def test_hpg_exact_balance_closure(self, hpg_industrial_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="HPG",
            base_data=hpg_industrial_profile,
        )
        bs = result.balance_sheet
        assert result.all_years_balanced is True
        for t in range(5):
            diff = abs(bs.total_assets[t] - bs.total_liabilities_and_equity[t])
            assert diff < 1.0 or (diff / max(bs.total_assets[t], 1.0)) < 1e-5
            assert bs.is_balanced[t] is True

    def test_mwg_exact_balance_closure(self, mwg_retail_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="MWG",
            base_data=mwg_retail_profile,
        )
        assert result.all_years_balanced is True
        for t in range(5):
            diff = abs(result.balance_sheet.balance_check_difference[t])
            assert diff < 1.0 or (diff / max(result.balance_sheet.total_assets[t], 1.0)) < 1e-5
            assert result.balance_sheet.is_balanced[t] is True


# =============================================================================
# TIER 3: DIRECT METHOD CASH FLOW RECONCILIATION
# =============================================================================

class TestTier3DirectCashFlowReconciliation:
    """Tier 3: Direct Method Operating Cash Flow conservation and reconciliation."""

    def test_direct_cfo_gross_identity(self, hpg_industrial_profile):
        """Gross CFO == (Cash from Customers - Cash to Suppliers) == Gross Profit - Delta Trade NWC."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="HPG",
            base_data=hpg_industrial_profile,
        )
        cfs = result.cash_flow_statement
        wc = result.working_capital_schedule
        is_stmt = result.income_statement
        
        for t in range(5):
            gross_cfo = cfs.cash_from_customers[t] - cfs.cash_to_suppliers[t]
            trade_delta = wc[t]["delta_ar"] + wc[t]["delta_inv"] - wc[t]["delta_ap"]
            expected_gross_cfo = is_stmt.gross_profit[t] - trade_delta
            assert math.isclose(gross_cfo, expected_gross_cfo, rel_tol=1e-5, abs_tol=1e-2)

    def test_net_cfo_equals_npat_plus_da_minus_delta_nwc(self, fpt_tech_profile):
        """Net CFO == NPAT + D&A - Delta NWC."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="FPT",
            base_data=fpt_tech_profile,
        )
        cfs = result.cash_flow_statement
        is_stmt = result.income_statement
        wc = result.working_capital_schedule
        
        for t in range(5):
            expected_net_cfo = is_stmt.npat[t] + is_stmt.depreciation_amortization[t] - wc[t]["delta_nwc"]
            assert math.isclose(cfs.net_cfo[t], expected_net_cfo, rel_tol=1e-4, abs_tol=1e-2)

    def test_cash_flow_total_reconciliation_to_ending_cash(self, mwg_retail_profile):
        """Ending Cash_t == Beginning Cash_t + Net CFO_t + Net CFI_t + Net CFF_t."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="MWG",
            base_data=mwg_retail_profile,
        )
        cfs = result.cash_flow_statement
        for t in range(5):
            calc_end = cfs.beginning_cash[t] + cfs.net_cfo[t] + cfs.net_cfi[t] + cfs.net_cff[t]
            assert math.isclose(cfs.ending_cash[t], calc_end, rel_tol=1e-5, abs_tol=1e-3)


# =============================================================================
# TIER 4: LIQUIDITY DISTRESS FIREWALL (REQUIREMENT R3)
# =============================================================================

class TestTier4LiquidityDistressFirewall:
    """Tier 4: Liquidity distress diagnostics and negative cash detection."""

    def test_healthy_firm_no_distress_penalties(self, fpt_tech_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="FPT",
            base_data=fpt_tech_profile,
        )
        check = result.liquidity_distress_check
        assert check.is_distressed is False
        assert check.has_negative_cash is False
        assert check.mos_penalty_pct == 0.0
        assert check.dilution_risk_pct == 0.0
        assert check.summary_assessment in ("HEALTHY", "TIGHT")

    def test_distressed_turnaround_triggers_firewall(self, distressed_turnaround_profile):
        """Severe debt service, amortization, and negative margins drive cash < 0."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="NVL",
            base_data=distressed_turnaround_profile,
            revenue_growth_series=[-0.15, -0.10, 0.0, 0.05, 0.10],
            gross_margin_series=[0.05, 0.05, 0.08, 0.10, 0.12],
            ebit_margin_series=[-0.10, -0.08, -0.02, 0.01, 0.03],
            capex_series=[15_000e9] * 5,
            capital_policy=CapitalAllocationPolicy(annual_amortization_rate=0.40, debt_funded_capex_ratio=0.0),
        )
        check = result.liquidity_distress_check
        assert check.is_distressed is True
        assert check.has_negative_cash is True
        assert len(check.distressed_years) > 0
        assert check.min_cash_balance < 0.0
        assert check.max_cash_shortfall > 0.0
        assert check.mos_penalty_pct >= 0.05
        assert check.dilution_risk_pct >= 0.05
        assert check.summary_assessment == "DISTRESSED"
        assert len(check.diagnostic_messages) > 0

    def test_solvency_guard_freezes_dividends_when_npat_negative(self, distressed_turnaround_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="NVL",
            base_data=distressed_turnaround_profile,
            revenue_growth_series=[-0.10, -0.05, 0.0, 0.05, 0.10],
            gross_margin_series=[0.05, 0.05, 0.08, 0.10, 0.12],
            ebit_margin_series=[-0.10, -0.08, -0.02, 0.01, 0.03],
        )
        cfs = result.cash_flow_statement
        is_stmt = result.income_statement
        for t in range(5):
            if is_stmt.npat[t] <= 0.0:
                assert cfs.dividends_paid[t] == 0.0


# =============================================================================
# TIER 5: FULL VN30 CONSTITUENT UNIVERSE INTEGRATION & BALANCE CLOSURE
# =============================================================================

class TestTier5VN30Constituents:
    """Tier 5: Automated validation across all 30 VN30 tickers."""

    @pytest.mark.parametrize("symbol", VN30_SYMBOLS)
    def test_vn30_all_symbols_produce_balanced_statements(self, symbol, screener_snapshot):
        """Validates that 100% of VN30 constituent symbols produce mathematically balanced statements."""
        result = ThreeStatementEngine.build_forecast_from_screener(symbol=symbol)
        assert result.symbol == symbol
        assert len(result.forecast_years) == 5
        assert result.all_years_balanced is True, f"{symbol} failed balance check: diff={result.max_balance_difference}"
        assert (result.max_balance_difference < 1.0) or (result.max_balance_difference / max(result.balance_sheet.total_assets[-1], 1.0) < 1e-5)


# =============================================================================
# TIER 6: BOUNDARY VALUES & PYDANTIC CONTRACT INTEGRITY
# =============================================================================

class TestTier6BoundaryAndSerialization:
    """Tier 6: Extreme values, zero growth, financial sector, and dictionary conversion."""

    def test_zero_revenue_firm_stability(self):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="ZERO",
            base_data={"revenue": 0.0, "market_cap": 500e9, "total_equity": 200e9, "total_debt": 0.0},
        )
        assert result.all_years_balanced is True
        assert len(result.income_statement.revenue) == 5

    def test_financial_bank_isolation(self):
        """Financial institution (VCB) gets isolated working capital (DIO=0, NWC=0) while keeping balanced BS."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="VCB",
            base_data={"sector": "VNBNK", "market_cap": 450_000e9, "revenue": 65_000e9, "total_equity": 130_000e9},
        )
        assert result.is_financial_sector is True
        assert result.all_years_balanced is True
        for p in result.working_capital_schedule:
            assert p["dio"] == 0.0
            assert p["inventory"] == 0.0

    def test_result_model_dump_and_serialization(self, fpt_tech_profile):
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="FPT",
            base_data=fpt_tech_profile,
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["symbol"] == "FPT"
        assert "income_statement" in d
        assert "balance_sheet" in d
        assert "cash_flow_statement" in d
        assert "liquidity_distress_check" in d
        assert len(d["balance_sheet"]["total_assets"]) == 5

    def test_convenience_forecast_3way_wrapper(self, fpt_tech_profile):
        res = forecast_3way("FPT", base_data=fpt_tech_profile)
        assert isinstance(res, ThreeStatementForecastResult)
        assert res.all_years_balanced is True

    def test_micro_revenue_boundary(self):
        """Micro revenue (100 VND) handles safe division, clamp, and produces balanced statements."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="MICRO",
            base_data={
                "revenue": 100.0,
                "gross_margin": 0.20,
                "op_margin": 0.05,
                "net_margin": 0.03,
                "market_cap": 1_000.0,
                "total_equity": 500.0,
                "total_debt": 100.0,
                "cash": 50.0,
            },
        )
        assert result.all_years_balanced is True
        assert result.max_balance_difference < 1.0
        for t in range(5):
            assert result.balance_sheet.is_balanced[t] is True

    def test_negative_revenue_boundary(self):
        """Negative revenue base data sanitized safely without throwing exceptions."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="NEGREV",
            base_data={
                "revenue": -50_000.0,
                "market_cap": 10_000.0,
                "total_equity": 5_000.0,
                "total_debt": 2_000.0,
            },
        )
        assert result.all_years_balanced is True
        assert len(result.income_statement.revenue) == 5

    def test_extreme_capex_boundary(self, distressed_turnaround_profile):
        """Extreme CapEx ratio and distress margin series trigger cash burn and distress firewall while maintaining balanced BS."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="NVL",
            base_data=distressed_turnaround_profile,
            revenue_growth_series=[-0.15, -0.10, -0.05, 0.0, 0.05],
            gross_margin_series=[0.05, 0.05, 0.08, 0.10, 0.12],
            ebit_margin_series=[-0.10, -0.08, -0.02, 0.01, 0.03],
            capex_ratio_series=[0.40, 0.40, 0.40, 0.40, 0.40],
        )
        assert result.all_years_balanced is True
        assert result.liquidity_distress_check.has_negative_cash is True
        assert result.liquidity_distress_check.is_distressed is True
        assert result.liquidity_distress_check.mos_penalty_pct >= 0.05

    def test_zero_starting_cash_boundary(self, fpt_tech_profile):
        """Zero starting cash base input roll-forwards cleanly with balanced BS."""
        profile = dict(fpt_tech_profile)
        profile["cash"] = 0.0
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="FPT_ZEROCASH",
            base_data=profile,
        )
        assert result.all_years_balanced is True
        assert result.cash_flow_statement.beginning_cash[0] >= 0.0
        assert math.isclose(result.balance_sheet.cash[0], result.cash_flow_statement.ending_cash[0], abs_tol=1e-3)





    def test_p_and_l_margins_and_taxes_reconciliation(self, fpt_tech_profile):
        """P&L line items strictly satisfy gross/net margin and corporate tax identities."""
        tax_rate = 0.20
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="FPT",
            base_data=fpt_tech_profile,
            tax_rate=tax_rate,
        )
        is_stmt = result.income_statement
        for t in range(5):
            rev = is_stmt.revenue[t]
            cogs = is_stmt.cogs[t]
            gp = is_stmt.gross_profit[t]
            assert math.isclose(gp, rev - cogs, rel_tol=1e-5)
            assert math.isclose(is_stmt.gross_margin[t], gp / rev, rel_tol=1e-5)

            ebit = is_stmt.ebit[t]
            int_exp = is_stmt.interest_expense[t]
            ebt = is_stmt.ebt[t]
            assert math.isclose(ebt, ebit - int_exp + is_stmt.interest_income[t], rel_tol=1e-4, abs_tol=1e-2)

            # Income tax
            tax = is_stmt.tax_expense[t]
            if ebt > 0.0:
                assert math.isclose(tax, ebt * tax_rate, rel_tol=1e-4, abs_tol=1e-2)
                assert math.isclose(is_stmt.npat[t], ebt - tax, rel_tol=1e-4, abs_tol=1e-2)
            else:
                assert tax == 0.0

            assert math.isclose(is_stmt.net_margin[t], is_stmt.npat[t] / rev, rel_tol=1e-5)

    def test_liquidity_distress_penalty_scaling(self, distressed_turnaround_profile):
        """Liquidity distress penalties scale within defined bounds (dilution 5%-25%, MoS 5%-15%)."""
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="NVL",
            base_data=distressed_turnaround_profile,
            revenue_growth_series=[-0.20, -0.15, -0.10, -0.05, 0.0],
            gross_margin_series=[0.02, 0.03, 0.04, 0.05, 0.06],
            ebit_margin_series=[-0.15, -0.12, -0.08, -0.05, -0.02],
            capex_series=[15_000e9] * 5,
            capital_policy=CapitalAllocationPolicy(annual_amortization_rate=0.40, debt_funded_capex_ratio=0.0),
        )
        check = result.liquidity_distress_check
        assert check.is_distressed is True
        assert 0.05 <= check.dilution_risk_pct <= 0.25
        assert 0.05 <= check.mos_penalty_pct <= 0.15


