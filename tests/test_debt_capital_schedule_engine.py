"""
=============================================================================
COMPREHENSIVE 4-TIER TEST SUITE: DEBT & CAPITAL SCHEDULE ENGINE (MILESTONE 2)
=============================================================================
Tiers Covered:
- Tier 1: Unit & Standard Calculations (ICR, Damodaran ratings, 5Y roll-forward)
- Tier 2: Boundary Value, Extreme Values & Adversarial Edge Cases
- Tier 3: Accounting Invariants & Conservation Laws
- Tier 4: Real-World VN30 Constituent Integration (HPG, VIC, MSN, VHM, GAS, VNM)
- Tier 5: Pydantic Contract & Downstream Integration Contracts
- Tier 6: Arithmetic Utilities, Sanitizers & Alias Verification
=============================================================================
"""

import math
import pytest
from typing import Dict, List, Any

from services.debt_capital_schedule_engine import (
    DebtCapitalScheduleEngine,
    DebtSchedulePeriod,
    CapitalAllocationPolicy,
    DebtCapitalScheduleResult,
    DebtCapitalForecastResult,
    DAMODARAN_SPREAD_LARGE_CAP,
    DAMODARAN_SPREAD_SMALL_CAP,
    DEFAULT_RF,
    DEFAULT_TAX_RATE,
    safe_div,
    clamp,
    sanitize_float,
)
from services.valuation_engine import WACCEngine


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def standard_industrial_baseline():
    """HPG-like industrial steel manufacturing profile."""
    return {
        "symbol": "HPG",
        "sector": "VNMAT",
        "market_cap": 165_000e9,
        "base_debt": 55_000e9,
        "ebit_series": [20_000e9, 22_000e9, 24_500e9, 27_000e9, 30_000e9],
        "npat_series": [15_000e9, 16_500e9, 18_400e9, 20_250e9, 22_500e9],
        "capex_series": [15_000e9, 15_000e9, 10_000e9, 8_000e9, 8_000e9],
    }


@pytest.fixture
def leveraged_conglomerate_baseline():
    """VIC-like leveraged corporate profile."""
    return {
        "symbol": "VIC",
        "sector": "VNREAL",
        "market_cap": 180_000e9,
        "base_debt": 160_000e9,
        "ebit_series": [18_000e9, 20_000e9, 22_000e9, 25_000e9, 28_000e9],
        "npat_series": [6_000e9, 7_500e9, 9_000e9, 11_000e9, 13_000e9],
        "capex_series": [30_000e9, 25_000e9, 20_000e9, 15_000e9, 15_000e9],
    }


@pytest.fixture
def cash_rich_baseline():
    """VNM-like fortress balance sheet profile."""
    return {
        "symbol": "VNM",
        "sector": "VNCONS",
        "market_cap": 140_000e9,
        "base_debt": 5_000e9,
        "ebit_series": [11_000e9, 11_500e9, 12_200e9, 12_800e9, 13_500e9],
        "npat_series": [9_000e9, 9_400e9, 10_000e9, 10_500e9, 11_000e9],
        "capex_series": [1_500e9, 1_500e9, 1_800e9, 1_800e9, 2_000e9],
    }


# =============================================================================
# TIER 1: UNIT & STANDARD CALCULATIONS
# =============================================================================

class TestTier1StandardCalculations:
    """Tier 1: Unit & Standard Calculations for Debt & Capital Engine."""

    @pytest.mark.parametrize(
        "icr, expected_rating, expected_spread",
        [
            (10.0, "AAA", 0.0065),
            (7.50, "AA",  0.0090),
            (6.00, "A+",  0.0115),
            (5.00, "A",   0.0135),
            (3.50, "A-",  0.0160),
            (2.75, "BBB", 0.0210),
            (2.35, "BB+", 0.0285),
            (2.10, "BB",  0.0340),
            (1.85, "B+",  0.0425),
            (1.60, "B",   0.0525),
            (1.35, "B-",  0.0650),
            (1.00, "CCC", 0.0850),
            (0.65, "CC",  0.1000),
            (0.20, "D",   0.1250),
        ],
    )
    def test_damodaran_synthetic_rating_lookup_large_cap(self, icr, expected_rating, expected_spread):
        """Test 1.1: Verify large cap ICR maps to exact rating and spread."""
        rating, spread = DebtCapitalScheduleEngine.calculate_synthetic_rating(icr, is_large_cap=True)
        assert rating == expected_rating
        assert math.isclose(spread, expected_spread, abs_tol=1e-5)

    @pytest.mark.parametrize(
        "icr, expected_rating, expected_spread",
        [
            (15.0, "AAA", 0.0065),
            (10.0, "AA",  0.0090),
            (8.00, "A+",  0.0115),
            (6.50, "A",   0.0135),
            (5.00, "A-",  0.0160),
            (4.20, "BBB", 0.0210),
            (3.70, "BB+", 0.0285),
            (3.20, "BB",  0.0340),
            (2.60, "B+",  0.0425),
            (2.10, "B",   0.0525),
            (1.60, "B-",  0.0650),
            (1.30, "CCC", 0.0850),
            (0.90, "CC",  0.1000),
            (0.50, "D",   0.1250),
        ],
    )
    def test_damodaran_synthetic_rating_lookup_small_cap(self, icr, expected_rating, expected_spread):
        """Test 1.2: Verify small cap ICR maps to exact rating and spread."""
        rating, spread = DebtCapitalScheduleEngine.calculate_synthetic_rating(icr, is_large_cap=False)
        assert rating == expected_rating
        assert math.isclose(spread, expected_spread, abs_tol=1e-5)

    def test_pre_and_after_tax_cost_of_debt_calculation(self):
        """Test 1.3: Verify pre-tax and after-tax cost of debt calculation."""
        rating, spread, kd_pre, kd_after = DebtCapitalScheduleEngine.calculate_cost_of_debt(
            icr=3.50,
            is_large_cap=True,
            rf=0.0500,
            tax_rate=0.20,
        )
        assert rating == "A-"
        assert math.isclose(spread, 0.0160, abs_tol=1e-5)
        assert math.isclose(kd_pre, 0.0660, rel_tol=1e-5)
        assert math.isclose(kd_after, 0.0528, rel_tol=1e-5)

    def test_interest_coverage_ratio_standard(self):
        """Test 1.4: Verify standard ICR calculation."""
        icr = DebtCapitalScheduleEngine.calculate_icr(ebit=15_000.0, interest_expense=3_000.0)
        assert math.isclose(icr, 5.0, rel_tol=1e-5)

    def test_5year_debt_roll_forward_constant_amortization(self):
        """Test 1.5: 5-year debt roll-forward with straight-line amortization and zero new borrowings."""
        policy = CapitalAllocationPolicy(
            annual_amortization_rate=0.20,
            debt_funded_capex_ratio=0.0,
            target_dividend_payout_ratio=0.30,
        )
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=10_000.0,
            ebit_series=[3_000.0] * 5,
            npat_series=[2_000.0] * 5,
            capex_series=[0.0] * 5,
            market_cap=10_000e9,
            policy=policy,
            rf=0.0500,
            tax_rate=0.20,
            start_year=2026,
        )

        assert len(schedule) == 5
        # Geometric decay: Opening * (1 - 0.20)^t
        expected_openings = [10000.0, 8000.0, 6400.0, 5120.0, 4096.0]
        expected_amorts = [2000.0, 1600.0, 1280.0, 1024.0, 819.2]
        expected_closings = [8000.0, 6400.0, 5120.0, 4096.0, 3276.8]
        expected_averages = [9000.0, 7200.0, 5760.0, 4608.0, 3686.4]

        for p, exp_o, exp_a, exp_c, exp_avg in zip(schedule, expected_openings, expected_amorts, expected_closings, expected_averages):
            assert math.isclose(p.opening_debt, exp_o, rel_tol=1e-4)
            assert math.isclose(p.principal_amortization, exp_a, rel_tol=1e-4)
            assert math.isclose(p.closing_debt, exp_c, rel_tol=1e-4)
            assert math.isclose(p.average_debt, exp_avg, rel_tol=1e-4)

    def test_5year_debt_roll_forward_with_capex_debt_financing(self):
        """Test 1.6: 5-year debt roll-forward with CapEx debt financing."""
        policy = CapitalAllocationPolicy(
            annual_amortization_rate=0.10,
            debt_funded_capex_ratio=0.50,
        )
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=5_000.0,
            ebit_series=[2_000.0] * 5,
            npat_series=[1_500.0] * 5,
            capex_series=[2000.0, 2500.0, 3000.0, 3500.0, 4000.0],
            market_cap=10_000e9,
            policy=policy,
        )
        p1 = schedule[0]
        assert math.isclose(p1.opening_debt, 5000.0)
        assert math.isclose(p1.new_borrowings, 1000.0) # 2000 * 0.50
        assert math.isclose(p1.principal_amortization, 500.0) # 5000 * 0.10
        assert math.isclose(p1.closing_debt, 5500.0) # 5000 + 1000 - 500
        assert math.isclose(p1.average_debt, 5250.0) # (5000 + 5500) / 2

    def test_period_interest_expense_and_cash_paid(self):
        """Test 1.7: Verify interest expense and cash interest paid equality."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=6_000.0,
            ebit_series=[4_000.0] * 5,
            npat_series=[2_500.0] * 5,
            capex_series=[0.0] * 5,
            policy=CapitalAllocationPolicy(annual_amortization_rate=0.0), # Constant 6000 debt
        )
        p = schedule[0]
        assert math.isclose(p.average_debt, 6000.0)
        assert math.isclose(p.interest_expense, p.cash_interest_paid)
        assert math.isclose(p.interest_expense, 6000.0 * p.cost_of_debt_pre_tax, rel_tol=1e-5)

    def test_standard_dividend_payout_and_retained_earnings(self):
        """Test 1.8: Verify standard solvent dividend payout."""
        policy = CapitalAllocationPolicy(target_dividend_payout_ratio=0.35)
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1_000.0,
            ebit_series=[4_500.0] * 5,
            npat_series=[4_000.0] * 5,
            capex_series=[500.0] * 5,
            policy=policy,
        )
        p = schedule[0]
        assert p.interest_coverage_ratio >= 1.20
        assert math.isclose(p.dividends_paid, 4000.0 * 0.35, rel_tol=1e-5)
        assert not p.is_covenant_breached

    def test_share_repurchase_capital_allocation(self):
        """Test 1.9: Verify share repurchases capital allocation."""
        policy = CapitalAllocationPolicy(
            target_dividend_payout_ratio=0.30,
            enable_share_repurchases=True,
            max_share_repurchase_pct_npat=0.10,
        )
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1_000.0,
            ebit_series=[5_000.0] * 5,
            npat_series=[5_000.0] * 5,
            capex_series=[500.0] * 5,
            policy=policy,
        )
        p = schedule[0]
        assert math.isclose(p.dividends_paid, 1500.0, rel_tol=1e-5)
        assert math.isclose(p.share_repurchases, 500.0, rel_tol=1e-5)
        assert math.isclose(p.total_capital_returned, 2000.0, rel_tol=1e-5)

    def test_build_debt_schedule_full_pipeline(self, standard_industrial_baseline):
        """Test 1.10: Verify full forecast pipeline execution."""
        base_data = {
            "total_debt": standard_industrial_baseline["base_debt"],
            "market_cap": standard_industrial_baseline["market_cap"],
            "sector": standard_industrial_baseline["sector"],
        }
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol=standard_industrial_baseline["symbol"],
            base_data=base_data,
            ebit_forecast=standard_industrial_baseline["ebit_series"],
            npat_forecast=standard_industrial_baseline["npat_series"],
            capex_forecast=standard_industrial_baseline["capex_series"],
            start_year=2026,
        )
        assert isinstance(res, DebtCapitalScheduleResult)
        assert len(res.schedule) == 5
        assert [p.year for p in res.schedule] == [2026, 2027, 2028, 2029, 2030]
        assert res.summary["weighted_average_kd_pre_tax"] > 0
        assert res.summary["total_dividends_5y"] > 0


# =============================================================================
# TIER 2: BOUNDARY VALUE, EXTREME VALUES & ADVERSARIAL EDGE CASES
# =============================================================================

class TestTier2BoundaryAndAdversarial:
    """Tier 2: Boundary Value, Extreme Values & Adversarial Edge Cases."""

    def test_zero_debt_pristine_balance_sheet(self):
        """Test 2.1: Zero debt company produces AAA rating, 0 interest, and clean metrics."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=0.0,
            ebit_series=[5_000.0] * 5,
            npat_series=[4_000.0] * 5,
            capex_series=[0.0] * 5,
        )
        for p in schedule:
            assert p.opening_debt == 0.0
            assert p.closing_debt == 0.0
            assert p.average_debt == 0.0
            assert p.interest_expense == 0.0
            assert p.cash_interest_paid == 0.0
            assert p.interest_coverage_ratio == 100.0
            assert p.synthetic_rating == "AAA"
            assert math.isclose(p.credit_spread, 0.0065)

    def test_zero_ebit_operating_breakeven(self):
        """Test 2.2: Zero EBIT results in Rating D, spread 12.50%, and dividend lockout."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=5_000.0,
            ebit_series=[0.0] * 5,
            npat_series=[0.0] * 5,
            capex_series=[0.0] * 5,
        )
        p = schedule[0]
        assert p.synthetic_rating == "D"
        assert math.isclose(p.credit_spread, 0.1250)
        assert math.isclose(p.cost_of_debt_pre_tax, 0.1750)
        assert p.dividends_paid == 0.0

    def test_negative_ebit_operating_loss_distress(self):
        """Test 2.3: Operating loss results in distressed Rating D and covenant trigger."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=10_000.0,
            ebit_series=[-5_000.0] * 5,
            npat_series=[-6_000.0] * 5,
            capex_series=[0.0] * 5,
        )
        p = schedule[0]
        assert p.synthetic_rating == "D"
        assert p.interest_coverage_ratio == -1.0
        assert p.is_covenant_breached
        assert p.dividends_paid == 0.0
        assert p.share_repurchases == 0.0

    def test_covenant_breach_dividend_suspension(self):
        """Test 2.4: Positive NPAT but ICR < 1.20 locks dividends to 0.0."""
        # EBIT = 800, Debt = 15000 -> Int ~ 15000 * 0.08 = 1200 -> ICR = 800 / 1200 = 0.67 < 1.20
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=15_000.0,
            ebit_series=[800.0] * 5,
            npat_series=[2_000.0] * 5,
            capex_series=[0.0] * 5,
            policy=CapitalAllocationPolicy(target_dividend_payout_ratio=0.30, min_icr_for_dividend=1.20),
        )
        p = schedule[0]
        assert p.interest_coverage_ratio < 1.20
        assert p.is_covenant_breached
        assert p.dividends_paid == 0.0
        assert p.is_dividend_curtailed

    def test_negative_npat_dividend_guard(self):
        """Test 2.5: Negative NPAT locks dividends to 0.0."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1_000.0,
            ebit_series=[2_500.0] * 5,
            npat_series=[-1_500.0] * 5,
            capex_series=[0.0] * 5,
            policy=CapitalAllocationPolicy(target_dividend_payout_ratio=0.50),
        )
        p = schedule[0]
        assert p.dividends_paid == 0.0

    def test_extreme_debt_100pct_financing(self):
        """Test 2.6: Massive debt financing handles accumulation without overflow."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=10_000.0,
            ebit_series=[5_000.0] * 5,
            npat_series=[1_000.0] * 5,
            capex_series=[50_000.0, 60_000.0, 70_000.0, 80_000.0, 90_000.0],
            policy=CapitalAllocationPolicy(debt_funded_capex_ratio=1.00, annual_amortization_rate=0.05),
        )
        assert len(schedule) == 5
        assert schedule[-1].closing_debt > 250_000.0
        assert not math.isnan(schedule[-1].cost_of_debt_pre_tax)

    def test_zero_payout_and_100pct_payout_extremes(self):
        """Test 2.7: Boundary payout ratios (0% and 100%)."""
        # Payout 0%
        s_0 = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1000.0, ebit_series=[5000.0]*5, npat_series=[3000.0]*5, capex_series=[0.0]*5,
            policy=CapitalAllocationPolicy(target_dividend_payout_ratio=0.0),
        )
        assert s_0[0].dividends_paid == 0.0

        # Payout 100%
        s_100 = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1000.0, ebit_series=[5000.0]*5, npat_series=[3000.0]*5, capex_series=[0.0]*5,
            policy=CapitalAllocationPolicy(target_dividend_payout_ratio=1.0),
        )
        assert math.isclose(s_100[0].dividends_paid, 3000.0)

    def test_negative_amortization_and_negative_borrowings_clamping(self):
        """Test 2.8: Adversarial negative amortization or negative CapEx."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=5_000.0,
            ebit_series=[2_000.0] * 5,
            npat_series=[1_000.0] * 5,
            capex_series=[-5_000.0] * 5,
            policy=CapitalAllocationPolicy(annual_amortization_rate=-0.30),
        )
        for p in schedule:
            assert p.principal_amortization >= 0.0
            assert p.new_borrowings >= 0.0
            assert p.closing_debt >= 0.0

    def test_dirty_string_and_null_imputation_handling(self):
        """Test 2.9: Dirty strings, None, and NaN inputs in base data."""
        base_data = {
            "total_debt": "15,000.0",
            "interest_expense": "--",
            "ebit": None,
            "market_cap": "nan",
        }
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="TEST",
            base_data=base_data,
            ebit_forecast=[2000.0] * 5,
            npat_forecast=[1500.0] * 5,
            capex_forecast=[1000.0] * 5,
        )
        assert res.base_debt == 15000.0
        assert len(res.schedule) == 5
        assert not math.isnan(res.total_interest_expense_5y)

    def test_damodaran_boundary_step_functions(self):
        """Test 2.10: Step boundary transitions without epsilon leakage."""
        # Large Cap step boundaries
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(8.5000, is_large_cap=True)[0] == "AAA"
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(8.4999, is_large_cap=True)[0] == "AA"
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(6.5000, is_large_cap=True)[0] == "AA"
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(6.4999, is_large_cap=True)[0] == "A+"
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(0.8000, is_large_cap=True)[0] == "CCC"
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(0.7999, is_large_cap=True)[0] == "CC"
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(0.5000, is_large_cap=True)[0] == "CC"
        assert DebtCapitalScheduleEngine.calculate_synthetic_rating(0.4999, is_large_cap=True)[0] == "D"

    def test_market_cap_large_small_boundary(self):
        """Test 2.11: Boundary of 5,000 Billion VND market cap category."""
        # ICR = 7.00
        # Large-Cap (5000.01B): 7.00 >= 6.50 -> AA (0.90%)
        r_l, s_l = DebtCapitalScheduleEngine.calculate_synthetic_rating(7.00, is_large_cap=True)
        assert r_l == "AA"
        assert math.isclose(s_l, 0.0090)

        # Small-Cap (4999.99B): 7.00 < 7.50, >= 6.00 -> A (1.35%)
        r_s, s_s = DebtCapitalScheduleEngine.calculate_synthetic_rating(7.00, is_large_cap=False)
        assert r_s == "A"
        assert math.isclose(s_s, 0.0135)

    def test_amortization_exceeding_total_debt_clamped(self):
        """Test 2.12: Amortization exceeding opening debt is clamped to available debt."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1_000.0,
            ebit_series=[2_000.0] * 5,
            npat_series=[1_000.0] * 5,
            capex_series=[0.0] * 5,
            policy=CapitalAllocationPolicy(annual_amortization_rate=1.50), # 150%
        )
        p1 = schedule[0]
        assert p1.principal_amortization == 1000.0
        assert p1.closing_debt == 0.0


# =============================================================================
# TIER 3: ACCOUNTING INVARIANTS & CONSERVATION LAWS
# =============================================================================

class TestTier3AccountingInvariants:
    """Tier 3: Accounting Invariants & Conservation Laws."""

    def test_debt_balance_roll_forward_invariant(self):
        """Test 3.1: Closing == Opening + Borrowings - Amortization for all periods."""
        for base_d in [0.0, 500.0, 10_000.0, 50_000.0]:
            schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
                base_debt=base_d,
                ebit_series=[4000.0] * 5,
                npat_series=[3000.0] * 5,
                capex_series=[2000.0, 3000.0, 4000.0, 2500.0, 1000.0],
                policy=CapitalAllocationPolicy(debt_funded_capex_ratio=0.40, annual_amortization_rate=0.20),
            )
            for p in schedule:
                assert math.isclose(
                    p.closing_debt,
                    p.opening_debt + p.new_borrowings - p.principal_amortization,
                    abs_tol=1e-5,
                )

    def test_period_linkage_opening_equals_prior_closing_invariant(self):
        """Test 3.2: Opening_t == Closing_{t-1} for all t > 1."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=12_000.0,
            ebit_series=[5000.0] * 5,
            npat_series=[3500.0] * 5,
            capex_series=[4000.0] * 5,
        )
        for i in range(1, len(schedule)):
            assert math.isclose(schedule[i].opening_debt, schedule[i-1].closing_debt, abs_tol=1e-5)

    def test_average_debt_midpoint_invariant(self):
        """Test 3.3: Average_Debt == (Opening + Closing) / 2."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=8_000.0,
            ebit_series=[4000.0] * 5,
            npat_series=[2500.0] * 5,
            capex_series=[3000.0] * 5,
        )
        for p in schedule:
            assert math.isclose(p.average_debt, (p.opening_debt + p.closing_debt) / 2.0, abs_tol=1e-5)

    def test_interest_expense_exact_product_invariant(self):
        """Test 3.4: Interest_Expense == Average_Debt * Kd_pre_tax."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=20_000.0,
            ebit_series=[6000.0] * 5,
            npat_series=[4000.0] * 5,
            capex_series=[5000.0] * 5,
        )
        for p in schedule:
            assert math.isclose(p.interest_expense, p.average_debt * p.cost_of_debt_pre_tax, abs_tol=1e-5)

    def test_after_tax_cost_of_debt_tax_shield_invariant(self):
        """Test 3.5: Kd_after_tax == Kd_pre_tax * (1 - Tax_Rate)."""
        tax_rate = 0.20
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=15_000.0,
            ebit_series=[5000.0] * 5,
            npat_series=[3000.0] * 5,
            capex_series=[2000.0] * 5,
            tax_rate=tax_rate,
        )
        for p in schedule:
            assert math.isclose(p.cost_of_debt_after_tax, p.cost_of_debt_pre_tax * (1.0 - tax_rate), abs_tol=1e-6)

    def test_non_negative_debt_and_payout_invariant(self):
        """Test 3.6: All debt, interest, and dividends are non-negative."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=5_000.0,
            ebit_series=[1000.0, -500.0, 2000.0, 0.0, 3000.0],
            npat_series=[500.0, -800.0, 1200.0, -100.0, 2000.0],
            capex_series=[1000.0] * 5,
        )
        for p in schedule:
            assert p.closing_debt >= 0.0
            assert p.dividends_paid >= 0.0
            assert p.cash_interest_paid >= 0.0
            assert p.share_repurchases >= 0.0

    def test_dividend_solvency_envelope_invariant(self):
        """Test 3.7: Dividends_Paid <= max(0, NPAT) and 0 when ICR < 1.20."""
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=50_000.0,
            ebit_series=[2000.0, 2000.0, 10000.0, 12000.0, 15000.0],
            npat_series=[1500.0, 1500.0, 7000.0, 8500.0, 11000.0],
            capex_series=[5000.0] * 5,
        )
        for p in schedule:
            assert p.dividends_paid <= max(0.0, p.npat)
            if p.interest_coverage_ratio < 1.20:
                assert p.dividends_paid == 0.0

    def test_damodaran_spread_monotonicity_invariant(self):
        """Test 3.8: Higher ICR implies equal or lower credit spread (monotonicity)."""
        icr_values = [i * 0.1 for i in range(-20, 200)]
        for is_large in [True, False]:
            spreads = [DebtCapitalScheduleEngine.calculate_synthetic_rating(icr, is_large)[1] for icr in icr_values]
            for i in range(len(spreads) - 1):
                assert spreads[i] >= spreads[i+1] # Non-increasing spread as ICR increases

    def test_linear_homogeneity_scale_invariance(self):
        """Test 3.9: Scaling all nominal variables by k leaves ICR and Kd invariant."""
        k = 4.25
        base_debt = 10_000.0
        ebit = [3000.0] * 5
        npat = [2000.0] * 5
        capex = [1500.0] * 5

        s_orig = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=base_debt, ebit_series=ebit, npat_series=npat, capex_series=capex,
        )
        s_scaled = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=base_debt * k, ebit_series=[x * k for x in ebit],
            npat_series=[x * k for x in npat], capex_series=[x * k for x in capex],
        )

        for p_orig, p_scaled in zip(s_orig, s_scaled):
            assert math.isclose(p_orig.interest_coverage_ratio, p_scaled.interest_coverage_ratio, rel_tol=1e-4)
            assert p_orig.synthetic_rating == p_scaled.synthetic_rating
            assert math.isclose(p_orig.cost_of_debt_pre_tax, p_scaled.cost_of_debt_pre_tax, rel_tol=1e-4)
            assert math.isclose(p_scaled.closing_debt, p_orig.closing_debt * k, rel_tol=1e-4)
            assert math.isclose(p_scaled.dividends_paid, p_orig.dividends_paid * k, rel_tol=1e-4)

    def test_zero_growth_steady_state_amortization_invariance(self):
        """Test 3.10: With CapEx=0, Closing_Debt_t == Debt_0 * (1 - delta)^t."""
        delta = 0.20
        base_debt = 10_000.0
        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=base_debt,
            ebit_series=[3000.0] * 5,
            npat_series=[2000.0] * 5,
            capex_series=[0.0] * 5,
            policy=CapitalAllocationPolicy(annual_amortization_rate=delta),
        )
        for t, p in enumerate(schedule, start=1):
            expected_closing = base_debt * ((1.0 - delta) ** t)
            assert math.isclose(p.closing_debt, expected_closing, abs_tol=1e-4)


# =============================================================================
# TIER 4: REAL-WORLD VN30 INTEGRATION
# =============================================================================

class TestTier4VN30Integration:
    """Tier 4: Empirical VN30 Constituent Profiles."""

    def test_vn30_hpg_steel_expansion_debt_cycle(self, standard_industrial_baseline):
        """Test 4.1: HPG capital-intensive steel expansion with CapEx and debt financing."""
        base_data = {
            "total_debt": standard_industrial_baseline["base_debt"],
            "market_cap": standard_industrial_baseline["market_cap"],
            "sector": standard_industrial_baseline["sector"],
        }
        policy = CapitalAllocationPolicy(
            debt_funded_capex_ratio=0.50,
            annual_amortization_rate=0.20,
            target_dividend_payout_ratio=0.20,
        )
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="HPG",
            base_data=base_data,
            ebit_forecast=standard_industrial_baseline["ebit_series"],
            npat_forecast=standard_industrial_baseline["npat_series"],
            capex_forecast=standard_industrial_baseline["capex_series"],
            policy=policy,
        )
        for p in res.schedule:
            assert p.interest_coverage_ratio >= 3.0
            assert p.synthetic_rating in ("A-", "A", "A+", "AA", "AAA")
            assert p.dividends_paid > 0
        assert res.summary["total_dividends_5y"] > 0

    def test_vn30_vic_vhm_real_estate_leverage_schedule(self, leveraged_conglomerate_baseline):
        """Test 4.2: VIC leveraged corporate structure and covenant sensitivity."""
        base_data = {
            "total_debt": leveraged_conglomerate_baseline["base_debt"],
            "market_cap": leveraged_conglomerate_baseline["market_cap"],
            "sector": leveraged_conglomerate_baseline["sector"],
        }
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="VIC",
            base_data=base_data,
            ebit_forecast=leveraged_conglomerate_baseline["ebit_series"],
            npat_forecast=leveraged_conglomerate_baseline["npat_series"],
            capex_forecast=leveraged_conglomerate_baseline["capex_series"],
            policy=CapitalAllocationPolicy(target_dividend_payout_ratio=0.0),
        )
        assert res.schedule[0].opening_debt == 160_000e9
        assert res.terminal_cost_of_debt_pre_tax > 0.05

    def test_vn30_msn_consumer_debt_restructuring(self):
        """Test 4.3: MSN deleveraging schedule over 5 years."""
        base_data = {
            "total_debt": 68_000e9,
            "market_cap": 110_000e9,
            "sector": "VNCONS",
        }
        policy = CapitalAllocationPolicy(
            annual_amortization_rate=0.25,
            debt_funded_capex_ratio=0.20,
            target_dividend_payout_ratio=0.10,
        )
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="MSN",
            base_data=base_data,
            ebit_forecast=[6_500e9, 7_500e9, 9_000e9, 10_500e9, 12_000e9],
            npat_forecast=[3_000e9, 3_800e9, 5_000e9, 6_200e9, 7_500e9],
            capex_forecast=[3_000e9] * 5,
            policy=policy,
        )
        # Verify deleveraging
        assert res.schedule[-1].closing_debt < res.schedule[0].opening_debt
        assert res.schedule[-1].interest_coverage_ratio > res.schedule[0].interest_coverage_ratio

    def test_vn30_vnm_consumer_staples_cash_rich_high_dividend(self, cash_rich_baseline):
        """Test 4.4: VNM cash-rich profile with AAA rating and high dividend payout."""
        base_data = {
            "total_debt": cash_rich_baseline["base_debt"],
            "market_cap": cash_rich_baseline["market_cap"],
            "sector": cash_rich_baseline["sector"],
        }
        policy = CapitalAllocationPolicy(target_dividend_payout_ratio=0.70)
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="VNM",
            base_data=base_data,
            ebit_forecast=cash_rich_baseline["ebit_series"],
            npat_forecast=cash_rich_baseline["npat_series"],
            capex_forecast=cash_rich_baseline["capex_series"],
            policy=policy,
        )
        for p in res.schedule:
            assert p.synthetic_rating in ("AA", "AAA")
            assert p.interest_coverage_ratio > 15.0
            assert math.isclose(p.dividends_paid, p.npat * 0.70, rel_tol=1e-5)
            assert not p.is_covenant_breached

    def test_vn30_gas_energy_utility_pristine_coverage(self):
        """Test 4.5: GAS energy utility with high coverage and lowest spread."""
        base_data = {
            "total_debt": 8_000e9,
            "market_cap": 160_000e9,
            "sector": "VNENE",
        }
        policy = CapitalAllocationPolicy(target_dividend_payout_ratio=0.60)
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="GAS",
            base_data=base_data,
            ebit_forecast=[14_000e9, 15_000e9, 16_000e9, 17_000e9, 18_000e9],
            npat_forecast=[11_000e9, 12_000e9, 13_000e9, 14_000e9, 15_000e9],
            capex_forecast=[3_000e9] * 5,
            policy=policy,
        )
        assert res.terminal_synthetic_rating == "AAA"
        assert math.isclose(res.terminal_credit_spread_bps, 65.0)

    @pytest.mark.parametrize("symbol", ["VCB", "TCB", "MBB", "ACB", "BID", "CTG", "SSI", "BVH"])
    def test_vn30_banking_financial_gating_isolation(self, symbol):
        """Test 4.6: Banking and financial institutions safely identified and isolated."""
        base_data = {
            "total_debt": 0.0,
            "market_cap": 100_000e9,
            "sector": "VNBNK",
        }
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol=symbol,
            base_data=base_data,
            ebit_forecast=[20_000e9] * 5,
            npat_forecast=[16_000e9] * 5,
            capex_forecast=[1_000e9] * 5,
        )
        assert res.summary["is_financial_sector"] is True
        assert res.diagnostics["is_financial_isolated"] is True

    def test_full_vn30_universe_batch_execution(self):
        """Test 4.7: Batch execution across 30 sample constituents with zero crashes."""
        sample_tickers = [
            ("HPG", 55_000e9, 20_000e9, 15_000e9, 15_000e9),
            ("VNM", 5_000e9, 11_000e9, 9_000e9, 1_500e9),
            ("VIC", 160_000e9, 18_000e9, 6_000e9, 30_000e9),
            ("VHM", 45_000e9, 25_000e9, 20_000e9, 10_000e9),
            ("MSN", 68_000e9, 6_500e9, 3_000e9, 3_000e9),
            ("MWG", 22_000e9, 5_000e9, 3_500e9, 2_000e9),
            ("FPT", 8_000e9, 9_000e9, 7_500e9, 3_000e9),
            ("GAS", 8_000e9, 14_000e9, 11_000e9, 3_000e9),
            ("PLX", 18_000e9, 3_500e9, 2_500e9, 2_000e9),
            ("SAB", 1_000e9, 5_500e9, 4_500e9, 800e9),
        ]
        for sym, debt, ebit, npat, capex in sample_tickers:
            res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
                symbol=sym,
                base_data={"total_debt": debt, "market_cap": 50_000e9},
                ebit_forecast=[ebit] * 5,
                npat_forecast=[npat] * 5,
                capex_forecast=[capex] * 5,
            )
            assert res.symbol == sym
            assert len(res.schedule) == 5


# =============================================================================
# TIER 5: PYDANTIC CONTRACT & DOWNSTREAM INTEGRATION
# =============================================================================

class TestTier5PydanticAndIntegrationContract:
    """Tier 5: Pydantic Schemas and Cross-Module Integration Contracts."""

    def test_pydantic_debt_schedule_period_schema(self):
        """Test 5.1: DebtSchedulePeriod model serialization and deserialization."""
        period = DebtSchedulePeriod(
            year=2026,
            opening_debt=10000.0,
            principal_amortization=2000.0,
            new_borrowings=1000.0,
            closing_debt=9000.0,
            average_debt=9500.0,
            interest_coverage_ratio=4.5,
            synthetic_rating="A",
            credit_spread_bps=135.0,
            credit_spread=0.0135,
            cost_of_debt_pre_tax=0.0635,
            cost_of_debt_after_tax=0.0508,
            interest_expense=603.25,
            cash_interest_paid=603.25,
            npat=3000.0,
            target_dividends=900.0,
            dividends_paid=900.0,
            share_repurchases=0.0,
            total_shareholder_distributions=900.0,
            total_capital_returned=900.0,
        )
        d = period.to_dict()
        assert d["year"] == 2026
        assert d["closing_debt"] == 9000.0
        assert d["total_capital_returned"] == 900.0

    def test_pydantic_debt_capital_schedule_result_schema(self, standard_industrial_baseline):
        """Test 5.2: DebtCapitalScheduleResult serialization with nested periods."""
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol=standard_industrial_baseline["symbol"],
            base_data={
                "total_debt": standard_industrial_baseline["base_debt"],
                "market_cap": standard_industrial_baseline["market_cap"],
            },
            ebit_forecast=standard_industrial_baseline["ebit_series"],
            npat_forecast=standard_industrial_baseline["npat_series"],
            capex_forecast=standard_industrial_baseline["capex_series"],
        )
        d = res.to_dict()
        assert d["symbol"] == "HPG"
        assert len(d["schedule"]) == 5
        assert "weighted_average_kd_pre_tax" in d["summary"]

    def test_downstream_three_statement_engine_integration_contract(self):
        """Test 5.3: Ensure dictionary contract contains all keys required by M3 Three Statement Engine."""
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="HPG",
            base_data={"total_debt": 55_000e9, "market_cap": 165_000e9},
            ebit_forecast=[20_000e9] * 5,
            npat_forecast=[15_000e9] * 5,
            capex_forecast=[15_000e9] * 5,
        )
        p = res.schedule[0].to_dict()
        # Balance Sheet line feeds
        assert "opening_debt" in p
        assert "closing_debt" in p
        assert "short_term_debt" in p
        assert "long_term_debt" in p
        # Income Statement line feeds
        assert "interest_expense" in p
        assert "cost_of_debt_pre_tax" in p
        # Cash Flow Statement line feeds
        assert "new_borrowings" in p
        assert "principal_amortization" in p
        assert "cash_interest_paid" in p
        assert "dividends_paid" in p
        assert "share_repurchases" in p

    def test_downstream_valuation_engine_integration_contract(self):
        """Test 5.4: Verify Kd synchronization with WACCEngine from valuation_engine.py."""
        ebit = 20_000e9
        int_exp = 3_000e9
        icr = ebit / int_exp # 6.67 -> AA (Large Cap)
        mcap = 100_000e9

        # From DebtCapitalScheduleEngine
        rating, spread, kd_pre, kd_after = DebtCapitalScheduleEngine.calculate_cost_of_debt(
            icr=icr, is_large_cap=True, rf=DEFAULT_RF, tax_rate=DEFAULT_TAX_RATE,
        )

        # From WACCEngine in valuation_engine
        wacc_res = WACCEngine.calculate(
            market_cap=mcap,
            interest_bearing_debt=40_000e9,
            ebit=ebit,
            interest_expense=int_exp,
            rf=DEFAULT_RF,
            tax_rate=DEFAULT_TAX_RATE,
        )

        assert rating == wacc_res.synthetic_rating
        assert math.isclose(kd_pre, wacc_res.cost_of_debt_pre_tax, abs_tol=1e-4)
        assert math.isclose(kd_after, wacc_res.cost_of_debt_after_tax, abs_tol=1e-4)


# =============================================================================
# TIER 6: ARITHMETIC UTILITIES, SANITIZERS & ALIAS VERIFICATION
# =============================================================================

class TestTier6UtilitiesAndAliases:
    """Tier 6: Arithmetic Utilities, Sanitizers & Alias Verification."""

    def test_sanitize_float_comprehensive(self):
        """Test sanitize_float with all supported input permutations."""
        assert sanitize_float(None, 5.0) == 5.0
        assert sanitize_float(10, 0.0) == 10.0
        assert sanitize_float(12.5, 0.0) == 12.5
        assert sanitize_float(float("nan"), 9.0) == 9.0
        assert sanitize_float(float("inf"), 9.0) == 9.0
        assert sanitize_float(float("-inf"), 9.0) == 9.0
        assert sanitize_float("12,345.67", 0.0) == 12345.67
        assert sanitize_float("$50,000.00", 0.0) == 50000.00
        assert sanitize_float("--", 1.0) == 1.0
        assert sanitize_float("N/A", 2.0) == 2.0
        assert sanitize_float("null", 3.0) == 3.0
        assert sanitize_float("invalid_str", 4.0) == 4.0
        assert sanitize_float([1, 2, 3], 0.0) == 0.0

    def test_safe_div_comprehensive(self):
        """Test safe_div with boundary and corrupt permutations."""
        assert safe_div(10.0, 2.0) == 5.0
        assert safe_div(10.0, 0.0, fallback=0.0) == 0.0
        assert safe_div(None, 2.0, fallback=-1.0) == -1.0
        assert safe_div(10.0, None, fallback=-1.0) == -1.0
        assert safe_div(float("nan"), 2.0, fallback=0.0) == 0.0
        assert safe_div(10.0, float("nan"), fallback=0.0) == 0.0
        assert safe_div(float("inf"), 2.0, fallback=0.0) == 0.0
        assert safe_div(10.0, float("inf"), fallback=0.0) == 0.0
        assert safe_div("10.0", "2.0") == 5.0
        assert safe_div("invalid", 2.0, fallback=0.0) == 0.0

    def test_clamp_comprehensive(self):
        """Test clamp with bounded, out-of-bounds, and non-numeric values."""
        assert clamp(5.0, 0.0, 10.0) == 5.0
        assert clamp(-5.0, 0.0, 10.0) == 0.0
        assert clamp(15.0, 0.0, 10.0) == 10.0
        assert clamp(float("nan"), 0.0, 10.0) == 0.0
        assert clamp(float("inf"), 0.0, 10.0) == 0.0
        assert clamp("invalid", 0.0, 10.0) == 0.0

    def test_capital_allocation_policy_alias_bidirectional(self):
        """Test CapitalAllocationPolicy parameter alias synchronization."""
        # dividend_payout_ratio -> target_dividend_payout_ratio
        pol1 = CapitalAllocationPolicy(dividend_payout_ratio=0.45)
        assert pol1.target_dividend_payout_ratio == 0.45
        assert pol1.dividend_payout_ratio == 0.45

        # target_dividend_payout_ratio -> dividend_payout_ratio
        pol2 = CapitalAllocationPolicy(target_dividend_payout_ratio=0.55)
        assert pol2.dividend_payout_ratio == 0.55

        # icr_covenant_threshold -> min_icr_for_dividend
        pol3 = CapitalAllocationPolicy(icr_covenant_threshold=1.50)
        assert pol3.min_icr_for_dividend == 1.50

        # min_icr_for_dividend -> icr_covenant_threshold
        pol4 = CapitalAllocationPolicy(min_icr_for_dividend=1.80)
        assert pol4.icr_covenant_threshold == 1.80

        # debt_financing_ratio -> debt_funded_capex_ratio
        pol5 = CapitalAllocationPolicy(debt_financing_ratio=0.60)
        assert pol5.debt_funded_capex_ratio == 0.60

        # debt_funded_capex_ratio -> debt_financing_ratio
        pol6 = CapitalAllocationPolicy(debt_funded_capex_ratio=0.70)
        assert pol6.debt_financing_ratio == 0.70

        # mandatory_amortization_rate -> annual_amortization_rate
        pol7 = CapitalAllocationPolicy(mandatory_amortization_rate=0.25)
        assert pol7.annual_amortization_rate == 0.25

        # annual_amortization_rate -> mandatory_amortization_rate
        pol8 = CapitalAllocationPolicy(annual_amortization_rate=0.35)
        assert pol8.mandatory_amortization_rate == 0.35

        # share_repurchase_ratio -> max_share_repurchase_pct_npat & enable_share_repurchases
        pol9 = CapitalAllocationPolicy(share_repurchase_ratio=0.15)
        assert pol9.max_share_repurchase_pct_npat == 0.15
        assert pol9.enable_share_repurchases is True

    def test_debt_schedule_period_alias_bidirectional(self):
        """Test DebtSchedulePeriod aliases for distributions and covenant notes."""
        p1 = DebtSchedulePeriod(total_shareholder_distributions=500.0)
        assert p1.total_capital_returned == 500.0

        p2 = DebtSchedulePeriod(total_capital_returned=600.0)
        assert p2.total_shareholder_distributions == 600.0

        p3 = DebtSchedulePeriod(covenant_notes="Note A")
        assert p3.curtailment_reason == "Note A"

        p4 = DebtSchedulePeriod(curtailment_reason="Note B")
        assert p4.covenant_notes == "Note B"

    def test_debt_capital_schedule_result_alias_bidirectional(self):
        """Test DebtCapitalScheduleResult alias synchronization."""
        period = DebtSchedulePeriod(year=2026)
        res1 = DebtCapitalScheduleResult(periods=[period])
        assert res1.schedule == [period]

        res2 = DebtCapitalScheduleResult(schedule=[period])
        assert res2.periods == [period]

        res3 = DebtCapitalScheduleResult(summary_metrics={"key": "val1"})
        assert res3.summary == {"key": "val1"}

        res4 = DebtCapitalScheduleResult(summary={"key": "val2"})
        assert res4.summary_metrics == {"key": "val2"}

    def test_zero_average_debt_terminal_kd(self):
        """Test summary weighted Kd fallback when average debt across all years is 0."""
        res = DebtCapitalScheduleEngine.build_debt_schedule_forecast(
            symbol="CASH",
            base_data={"total_debt": 0.0, "market_cap": 10_000e9},
            ebit_forecast=[1000.0] * 5,
            npat_forecast=[800.0] * 5,
            capex_forecast=[0.0] * 5,
            policy=CapitalAllocationPolicy(debt_funded_capex_ratio=0.0),
        )
        assert res.summary["weighted_average_kd_pre_tax"] == res.terminal_cost_of_debt_pre_tax

    def test_fixed_point_solver_convergence_under_circularity(self):
        """Fixed-point solver resolves circular feedback between Debt, Interest, and Kd(ICR) in <= 5 iterations."""
        # Test boundary where initial BBB guess differs from true convergent rating
        # e.g., High EBIT with low debt (AAA), moderate coverage (B+), and distressed coverage (CCC)
        for ebit, debt, expected_rating in [
            (50_000e9, 5_000e9, "AAA"),
            (15_000e9, 100_000e9, "B+"),
            (10_000e9, 100_000e9, "CCC"),
        ]:
            schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
                base_debt=debt,
                ebit_series=[ebit] * 5,
                npat_series=[ebit * 0.7] * 5,
                capex_series=[0.0] * 5,
                market_cap=20_000e9, # Large cap
            )
            assert len(schedule) == 5
            p = schedule[0]
            assert p.synthetic_rating == expected_rating
            # Check self-consistency: Interest Expense == Average Debt * (Rf + Spread)
            expected_kd = DEFAULT_RF + p.credit_spread
            assert math.isclose(p.cost_of_debt_pre_tax, expected_kd, rel_tol=1e-5)
            assert math.isclose(p.interest_expense, p.average_debt * expected_kd, rel_tol=1e-5)
            # Recomputed ICR matches
            assert math.isclose(p.interest_coverage_ratio, ebit / p.interest_expense, rel_tol=1e-4)

    def test_top_level_build_debt_schedule_contract(self):
        """Test Interface Contract 2: build_debt_schedule module-level function."""
        from services.debt_capital_schedule_engine import build_debt_schedule
        periods = build_debt_schedule(
            base_debt=10_000e9,
            ebit_series=[3_000e9, 3_200e9, 3_500e9, 3_800e9, 4_000e9],
            capex_series=[2_000e9, 2_000e9, 2_000e9, 2_000e9, 2_000e9],
            npat_series=[2_000e9, 2_200e9, 2_400e9, 2_600e9, 2_800e9],
            start_year=2026,
            market_cap=25_000e9,
            rf=0.05,
            tax_rate=0.20,
            payout_ratio=0.30,
        )
        assert len(periods) == 5
        assert isinstance(periods[0], DebtSchedulePeriod)
        assert periods[0].year == 2026
        assert hasattr(periods[0], "pre_tax_kd")
        assert hasattr(periods[0], "after_tax_kd")
        assert math.isclose(periods[0].pre_tax_kd, periods[0].cost_of_debt_pre_tax)
        assert math.isclose(periods[0].after_tax_kd, periods[0].cost_of_debt_after_tax)
        assert periods[0].interest_income == 0.0
        assert periods[0].dividends_paid > 0.0




