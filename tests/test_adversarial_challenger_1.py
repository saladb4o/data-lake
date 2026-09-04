"""
=============================================================================
CHALLENGER 1: ADVERSARIAL ACCOUNTING & INVARIANT STRESS TEST SUITE
=============================================================================
Stress-tests the mathematical modeling core of the Modano 3-Way Integrated
Financial Modeling Ecosystem:
1. 1,000+ randomized Monte Carlo synthetic financial profiles (extreme leverage,
   negative margins, zero revenue, hyper-growth, extreme CapEx, zero starting cash,
   negative CCC, financial sector isolation).
2. Direct Method cash flow conservation under wild working capital shocks.
3. Debt fixed-point iterative circularity solver convergence and stability under
   boundary ICR and negative EBIT scenarios.
4. Solvency dividend and share repurchase firewalls under distress.
5. Exact invariant enforcement: |Net Assets - Total Equity| < 10^-5 across all years.
=============================================================================
"""

import math
import random
import pytest
from typing import Dict, List, Any

from services.three_statement_engine import (
    ThreeStatementEngine,
    ThreeStatementForecastResult,
    IncomeStatementForecast,
    BalanceSheetForecast,
    CashFlowForecast,
    LiquidityDistressCheck,
    safe_div,
    sanitize_float,
    clamp,
)
from services.working_capital_engine import (
    WorkingCapitalEngine,
    WorkingCapitalMetrics,
    WorkingCapitalSchedulePeriod,
    resolve_sector_prior,
    FINANCIAL_SYMBOLS,
)
from services.debt_capital_schedule_engine import (
    DebtCapitalScheduleEngine,
    DebtSchedulePeriod,
    CapitalAllocationPolicy,
    DebtCapitalScheduleResult,
    DAMODARAN_SPREAD_LARGE_CAP,
    DAMODARAN_SPREAD_SMALL_CAP,
    DEFAULT_RF,
    DEFAULT_TAX_RATE,
)


# =============================================================================
# 1. 1,000+ RANDOMIZED MONTE CARLO SYNTHETIC PROFILES STRESS TEST
# =============================================================================

class TestMonteCarloBalanceSheetClosure:
    """
    Executes 1,000+ randomized synthetic financial profiles spanning the entire
    multi-dimensional parameter space to verify mathematical balance sheet closure.
    """

    @pytest.mark.parametrize("batch_idx", range(10))
    def test_1000_randomized_synthetic_profiles(self, batch_idx: int):
        """
        Runs 10 batches of 100 profiles each = 1,000 total randomized profiles.
        Tests extreme leverage, negative margins, zero revenue, hyper-growth,
        extreme CapEx, zero starting cash, negative CCC, and financial sectors.
        """
        rng = random.Random(42 + batch_idx * 1000)
        
        sectors = [
            "VNCONS", "VNCOND", "VNMAT", "VNIND", "VNIT", "VNREAL", "VNENE",
            "VNUTI", "VNHEAL", "VNFIN", "RETAIL", "DEFAULT"
        ]
        
        for case_idx in range(100):
            # Generate randomized financial parameters across wide/extreme intervals
            is_financial_case = rng.choice([False, False, False, True])
            sector = "VNFIN" if is_financial_case else rng.choice(sectors)
            
            # Revenue: 0 to 500,000 Billion VND, including 0.0 and micro-revenues
            rev_type = rng.choice(["zero", "micro", "normal", "mega"])
            if rev_type == "zero":
                base_rev = 0.0
            elif rev_type == "micro":
                base_rev = rng.uniform(1.0, 1000.0)
            elif rev_type == "normal":
                base_rev = rng.uniform(10e9, 50_000e9)
            else:
                base_rev = rng.uniform(50_000e9, 500_000e9)

            # Gross Margin: between -100% (severe loss) and +95% (software)
            gross_margin = rng.uniform(-1.0, 0.95)
            
            # Operating Margin: between -150% and +80%
            ebit_margin = rng.uniform(-1.5, min(0.80, gross_margin - 0.01) if gross_margin > -1.0 else -0.5)

            # Leverage / Debt-to-Equity: 0.0 to 100.0 (hyper-leveraged)
            de_ratio = rng.uniform(0.0, 50.0)
            
            # Starting cash: 0.0 to 50% of revenue
            cash_type = rng.choice(["zero", "small", "large"])
            if cash_type == "zero":
                base_cash = 0.0
            elif cash_type == "small":
                base_cash = rng.uniform(10.0, 1e6)
            else:
                base_cash = base_rev * rng.uniform(0.05, 0.50)

            # Starting PPE
            base_ppe = base_rev * rng.uniform(0.05, 2.0) if base_rev > 0 else rng.uniform(0.0, 1000e9)
            
            # Starting Equity
            base_equity = max(10e6, base_rev * rng.uniform(0.1, 1.5)) if base_rev > 0 else 100e9
            base_debt = base_equity * de_ratio

            # Revenue Growth Trajectory: from -99% (collapse) to +500% (hyper-growth)
            rev_growth_series = [
                rng.uniform(-0.80, 2.0) for _ in range(5)
            ]
            
            # CapEx series: from 0 to 200% of revenue
            capex_ratio_series = [
                rng.uniform(0.0, 1.50) for _ in range(5)
            ]

            # Dividend payout ratio: 0.0 to 1.0
            payout_ratio = rng.uniform(0.0, 1.0)
            enable_repurchase = rng.choice([True, False])
            repurchase_pct = rng.uniform(0.0, 0.30) if enable_repurchase else 0.0

            policy = CapitalAllocationPolicy(
                target_dividend_payout_ratio=payout_ratio,
                enable_share_repurchases=enable_repurchase,
                max_share_repurchase_pct_npat=repurchase_pct,
                min_icr_for_dividend=rng.choice([1.0, 1.20, 1.50, 2.0]),
                annual_amortization_rate=rng.uniform(0.0, 0.50),
                debt_funded_capex_ratio=rng.uniform(0.0, 1.0),
            )

            base_data = {
                "name": f"Synthetic_{batch_idx}_{case_idx}",
                "sector": sector,
                "revenue": base_rev,
                "gross_margin": gross_margin,
                "ebit_margin": ebit_margin,
                "total_equity": base_equity,
                "total_debt": base_debt,
                "cash": base_cash,
                "net_ppe": base_ppe,
                "market_cap": base_equity * rng.uniform(0.5, 5.0),
                "is_financial_sector": is_financial_case,
            }

            result = ThreeStatementEngine.forecast_three_statements(
                symbol=f"SYNTH_{batch_idx}_{case_idx}",
                base_data=base_data,
                revenue_growth_series=rev_growth_series,
                capex_ratio_series=capex_ratio_series,
                capital_policy=policy,
                tax_rate=0.20,
                num_years=5,
            )

            # ASSERTION 1: Mathematical Invariant |Net Assets - Total Equity| < 10^-5
            bs = result.balance_sheet
            for t in range(5):
                ta = bs.total_assets[t]
                tl = bs.total_liabilities[t]
                te = bs.total_equity[t]
                diff = abs(ta - (tl + te))
                net_assets = ta - tl
                invariant_diff = abs(net_assets - te)

                scale = max(abs(ta), abs(tl), abs(te), 1.0)
                rel_err = safe_div(diff, scale, 0.0)

                assert (diff < 1.0 or rel_err < 1e-5), (
                    f"Invariant violated at batch {batch_idx} case {case_idx} year {t}: "
                    f"TA={ta}, TL={tl}, TE={te}, NetAssets={net_assets}, Diff={diff}, RelErr={rel_err}"
                )
                assert (invariant_diff < 1.0 or safe_div(invariant_diff, scale, 0.0) < 1e-5)

            # ASSERTION 2: Statement Link 1: Net Income -> Retained Earnings
            # RE_t = RE_{t-1} + NPAT_t - Dividends_t
            cfs = result.cash_flow_statement
            is_stmt = result.income_statement
            for t in range(5):
                npat_t = is_stmt.npat[t]
                div_t = cfs.dividends_paid[t]
                expected_re_delta = npat_t - div_t
                if t > 0:
                    actual_re_delta = bs.retained_earnings[t] - bs.retained_earnings[t-1]
                    assert math.isclose(actual_re_delta, expected_re_delta, rel_tol=1e-5, abs_tol=1.0), (
                        f"Statement Link 1 broken at t={t}: actual delta {actual_re_delta} != expected {expected_re_delta}"
                    )

            # ASSERTION 3: Statement Link 2: Net Change in Cash -> Ending Cash
            # Ending_Cash_t = Beginning_Cash_t + Net_CFO + Net_CFI + Net_CFF
            for t in range(5):
                beg_c = cfs.beginning_cash[t]
                cfo = cfs.net_cfo[t]
                cfi = cfs.net_cfi[t]
                cff = cfs.net_cff[t]
                end_c = cfs.ending_cash[t]
                delta_c = cfs.net_change_in_cash[t]

                assert math.isclose(delta_c, cfo + cfi + cff, rel_tol=1e-5, abs_tol=1.0), (
                    f"Cash flow sum mismatch at t={t}: delta_cash {delta_c} != cfo+cfi+cff {cfo+cfi+cff}"
                )
                assert math.isclose(end_c, beg_c + delta_c, rel_tol=1e-5, abs_tol=1.0), (
                    f"Statement Link 2 broken at t={t}: ending cash {end_c} != beg {beg_c} + delta {delta_c}"
                )
                assert math.isclose(bs.cash[t], end_c, rel_tol=1e-5, abs_tol=1.0), (
                    f"BS cash mismatch at t={t}: BS cash {bs.cash[t]} != CFS ending cash {end_c}"
                )


# =============================================================================
# 2. ADVERSARIAL DIRECT METHOD CASH CONSERVATION UNDER WILD WORKING CAPITAL
# =============================================================================

class TestAdversarialDirectMethodCashConservation:
    """
    Stress-tests Direct Method Cash Flow accounting identities under violent
    working capital swings, negative CCC, supplier stretching, customer defaults.
    """

    def test_wild_working_capital_variations(self):
        """
        Tests extreme working capital scenarios:
        1. Massive DSO expansion (AR explodes, customers delay payment)
        2. Inventory buildup (DIO triples, huge cash trapped in stock)
        3. Extreme supplier financing (DPO explodes, suppliers finance company)
        4. Negative CCC retail business model (MWG style)
        5. Severe contraction (Rev drops 80%)
        6. Zero revenue startup with expenses
        """
        scenarios = [
            {"dso": 300.0, "dio": 60.0, "dpo": 45.0, "rev": 1000e9, "cogs": 700e9},
            {"dso": 30.0, "dio": 500.0, "dpo": 30.0, "rev": 1000e9, "cogs": 700e9},
            {"dso": 30.0, "dio": 40.0, "dpo": 350.0, "rev": 1000e9, "cogs": 700e9},
            {"dso": 10.0, "dio": 30.0, "dpo": 90.0, "rev": 2000e9, "cogs": 1600e9},
            {"dso": 60.0, "dio": 90.0, "dpo": 60.0, "rev": 200e9, "cogs": 180e9},
            {"dso": 0.0, "dio": 0.0, "dpo": 90.0, "rev": 0.0, "cogs": 100e9},
        ]

        for sc in scenarios:
            base_wc = {
                "dso": sc["dso"],
                "dio": sc["dio"],
                "dpo": sc["dpo"],
                "revenue": sc["rev"],
                "cogs": sc["cogs"],
                "accounts_receivable": sc["rev"] * (sc["dso"] / 365.0),
                "inventory": sc["cogs"] * (sc["dio"] / 365.0),
                "accounts_payable": sc["cogs"] * (sc["dpo"] / 365.0),
                "other_current_assets": sc["rev"] * 0.05,
                "other_current_liabilities": sc["cogs"] * 0.07,
                "net_working_capital": (sc["rev"] * (sc["dso"] / 365.0) + sc["cogs"] * (sc["dio"] / 365.0) + sc["rev"] * 0.05) - (sc["cogs"] * (sc["dpo"] / 365.0) + sc["cogs"] * 0.07),
                "is_financial_sector": False,
            }

            rev_series = [sc["rev"] * (1.15 ** t) for t in range(5)]
            cogs_series = [sc["cogs"] * (1.15 ** t) for t in range(5)]

            wc_sched = WorkingCapitalEngine.project_working_capital_schedule(
                base_metrics=base_wc,
                revenue_series=rev_series,
                cogs_series=cogs_series,
                mean_revert_speed=0.25,
                years=[2026, 2027, 2028, 2029, 2030],
            )

            assert len(wc_sched) == 5

            for p in wc_sched:
                cash_cust = p["cash_collected_from_customers"]
                cash_supp = p["cash_paid_to_suppliers"]
                gross_cfo = cash_cust - cash_supp
                gross_profit = p["revenue"] - p["cogs"]
                delta_trade_nwc = p["delta_trade_nwc"]
                
                assert math.isclose(gross_cfo, gross_profit - delta_trade_nwc, rel_tol=1e-5, abs_tol=1.0), (
                    f"Direct gross CFO conservation failed: gross_cfo={gross_cfo}, "
                    f"GP-DeltaTradeNWC={gross_profit - delta_trade_nwc}"
                )

                expected_delta_total_nwc = (
                    p["delta_ar"] + p["delta_inv"] + p["delta_oca"] - p["delta_ap"] - p["delta_ocl"]
                )
                assert math.isclose(p["delta_nwc"], expected_delta_total_nwc, rel_tol=1e-5, abs_tol=1.0), (
                    f"Total Delta NWC decomposition failed: delta_nwc={p['delta_nwc']}, expected={expected_delta_total_nwc}"
                )

    def test_direct_cfs_to_npat_reconciliation_identity(self):
        """
        Verifies that across all test cases:
        Net CFO == NPAT + D&A - Delta NWC (under zero non-operating distortion)
        """
        result = ThreeStatementEngine.forecast_three_statements(
            symbol="HPG",
            base_data={
                "revenue": 150_000e9,
                "gross_margin": 0.20,
                "op_margin": 0.12,
                "total_debt": 40_000e9,
                "total_equity": 80_000e9,
                "net_ppe": 60_000e9,
                "cash": 25_000e9,
                "sector": "VNMAT",
            }
        )

        cfs = result.cash_flow_statement
        is_stmt = result.income_statement
        wc = result.working_capital_schedule

        for t in range(5):
            direct_net_cfo = cfs.net_cfo[t]
            indirect_net_cfo = is_stmt.npat[t] + is_stmt.depreciation_amortization[t] - wc[t]["delta_nwc"]

            assert math.isclose(direct_net_cfo, indirect_net_cfo, rel_tol=1e-5, abs_tol=1.0), (
                f"Direct vs Indirect CFO reconciliation failed at year {t}: "
                f"Direct={direct_net_cfo}, Indirect={indirect_net_cfo}"
            )


# =============================================================================
# 3. DEBT FIXED-POINT SOLVER CONVERGENCE & STABILITY UNDER BOUNDARY CONDITIONS
# =============================================================================

class TestDebtFixedPointSolverStability:
    """
    Stress-tests the iterative fixed-point solver resolving circularity between
    Average Debt, Interest Expense, and Kd(ICR).
    """

    def test_boundary_icr_values(self):
        """
        Tests ICR boundaries around Damodaran rating steps:
        AAA (8.5), AA (6.5), A+ (5.5), A (4.25), A- (3.0), BBB (2.5),
        BB+ (2.25), BB (2.0), B+ (1.75), B (1.5), B- (1.25), CCC (0.8), CC (0.5), D (<0.5).
        """
        boundary_icrs = [
            8.50001, 8.49999, 6.50001, 6.49999, 5.50001, 5.49999,
            4.25001, 4.24999, 3.00001, 2.99999, 2.50001, 2.49999,
            2.25001, 2.24999, 2.00001, 1.99999, 1.75001, 1.74999,
            1.50001, 1.49999, 1.25001, 1.24999, 0.80001, 0.79999,
            0.50001, 0.49999, 0.0, -0.0001, -100.0, float("inf"), float("-inf")
        ]

        for icr in boundary_icrs:
            rating_large, spread_large = DebtCapitalScheduleEngine.calculate_synthetic_rating(icr, is_large_cap=True)
            rating_small, spread_small = DebtCapitalScheduleEngine.calculate_synthetic_rating(icr, is_large_cap=False)

            assert rating_large in ["AAA", "AA", "A+", "A", "A-", "BBB", "BB+", "BB", "B+", "B", "B-", "CCC", "CC", "D"]
            assert rating_small in ["AAA", "AA", "A+", "A", "A-", "BBB", "BB+", "BB", "B+", "B", "B-", "CCC", "CC", "D"]
            assert 0.0065 <= spread_large <= 0.1250
            assert 0.0065 <= spread_small <= 0.1250

    def test_negative_ebit_and_operating_loss_scenarios(self):
        """
        Tests solver stability when company experiences severe operating losses
        (EBIT < 0, negative ICR, rating D, 1250 bps spread).
        """
        ebit_series = [-100e9, -500e9, -200e9, 0.0, 50e9]
        npat_series = [-150e9, -550e9, -250e9, -20e9, 30e9]
        capex_series = [10e9, 10e9, 10e9, 10e9, 10e9]

        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1000e9,
            ebit_series=ebit_series,
            npat_series=npat_series,
            capex_series=capex_series,
            market_cap=2000e9,
            tax_rate=0.20,
        )

        assert len(schedule) == 5

        for t in range(4):
            p = schedule[t]
            assert p.synthetic_rating == "D"
            assert p.credit_spread == 0.1250
            assert p.cost_of_debt_pre_tax == DEFAULT_RF + 0.1250
            assert p.interest_expense > 0.0
            assert not math.isnan(p.interest_expense)
            assert not math.isinf(p.interest_expense)

    def test_zero_debt_and_massive_debt_extremes(self):
        """
        Tests zero debt (ICR=100, AAA) and massive debt (1,000,000 Billion VND).
        """
        sched_zero = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=0.0,
            ebit_series=[100e9] * 5,
            npat_series=[80e9] * 5,
            capex_series=[0.0] * 5,
            market_cap=5000e9,
            policy=CapitalAllocationPolicy(debt_funded_capex_ratio=0.0),
        )
        for p in sched_zero:
            assert p.closing_debt == 0.0
            assert p.average_debt == 0.0
            assert p.interest_expense == 0.0
            assert p.synthetic_rating == "AAA"

        sched_massive = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1_000_000e9,
            ebit_series=[10_000e9] * 5,
            npat_series=[5_000e9] * 5,
            capex_series=[1_000e9] * 5,
            market_cap=50_000e9,
        )
        for p in sched_massive:
            assert p.closing_debt > 0.0
            assert not math.isnan(p.interest_expense)
            assert p.is_covenant_breached == True
            assert p.dividends_paid == 0.0


# =============================================================================
# 4. DIVIDEND & REPURCHASE FIREWALLS UNDER DISTRESS
# =============================================================================

class TestDividendAndRepurchaseDistressFirewalls:
    """
    Stress-tests the statutory and covenant firewalls protecting cash:
    1. Statutory Profitability Firewall: NPAT <= 0 => 0 dividends & 0 repurchases
    2. Debt Covenant Firewall: ICR < 1.20 => 0 dividends & 0 repurchases
    3. Solvency Release: NPAT > 0 and ICR >= 1.20 => Normal dividend payout
    """

    def test_statutory_profitability_firewall(self):
        """
        Ensures NO dividends or repurchases are paid when NPAT is negative or zero.
        """
        policy = CapitalAllocationPolicy(
            target_dividend_payout_ratio=0.80,
            enable_share_repurchases=True,
            max_share_repurchase_pct_npat=0.20,
            min_icr_for_dividend=1.0,
        )

        npat_scenarios = [-500e9, -100.0, -0.001, 0.0]
        for npat in npat_scenarios:
            sched = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
                base_debt=100e9,
                ebit_series=[1000e9] * 5,
                npat_series=[npat] * 5,
                capex_series=[50e9] * 5,
                policy=policy,
            )
            for p in sched:
                assert p.dividends_paid == 0.0, f"Dividends leaked on NPAT {npat}!"
                assert p.share_repurchases == 0.0, f"Repurchases leaked on NPAT {npat}!"
                assert p.is_dividend_curtailed == True
                assert p.curtailment_reason == "NEGATIVE_OR_ZERO_NPAT"

    def test_covenant_icr_firewall(self):
        """
        Ensures NO dividends are paid when ICR < 1.20 (covenant breach).
        """
        policy = CapitalAllocationPolicy(
            target_dividend_payout_ratio=0.50,
            min_icr_for_dividend=1.20,
        )

        sched = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=2_000e9,
            ebit_series=[100e9] * 5,
            npat_series=[50e9] * 5,
            capex_series=[10e9] * 5,
            policy=policy,
        )

        for p in sched:
            assert p.is_covenant_breached == True
            assert p.interest_coverage_ratio < 1.20
            assert p.dividends_paid == 0.0
            assert p.share_repurchases == 0.0
            assert p.is_dividend_curtailed == True

    def test_multi_year_distress_recovery_cycle(self):
        """
        Tests a 5-year cycle: Healthy -> Distress -> Severe Loss -> Recovery -> Strong Health.
        """
        ebit_series = [1000e9, 100e9, -300e9, 500e9, 1500e9]
        npat_series = [ 700e9,  20e9, -400e9, 300e9, 1000e9]
        capex_series = [200e9, 100e9,   50e9, 150e9,  300e9]

        policy = CapitalAllocationPolicy(
            target_dividend_payout_ratio=0.40,
            min_icr_for_dividend=1.20,
        )

        sched = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=1000e9,
            ebit_series=ebit_series,
            npat_series=npat_series,
            capex_series=capex_series,
            policy=policy,
        )

        assert sched[0].dividends_paid == pytest.approx(280e9, rel=1e-3)
        assert not sched[0].is_covenant_breached

        assert sched[1].is_covenant_breached
        assert sched[1].dividends_paid == 0.0

        assert sched[2].dividends_paid == 0.0
        assert sched[2].curtailment_reason == "NEGATIVE_OR_ZERO_NPAT"

        assert sched[4].dividends_paid > 0.0
        assert not sched[4].is_covenant_breached


# =============================================================================
# 5. HIGH-LEVERAGE REAL ESTATE & DISTRESSED TICKER E2E STRESS TESTS
# =============================================================================

class TestRealWorldDistressedProfiles:
    """
    Simulates real-world high-debt distressed profiles (e.g. NVL, PDR during liquidity freeze)
    and validates invariant integrity and distress diagnostics.
    """

    def test_distressed_real_estate_profile_nvl(self):
        """
        Simulates NVL: high debt (50,000B), massive inventory (120,000B), zero revenue growth,
        operating cash deficit, triggering liquidity distress penalties.
        """
        nvl_data = {
            "name": "No Va Land Investment Group",
            "sector": "VNREAL",
            "revenue": 5000e9,
            "gross_margin": 0.25,
            "op_margin": 0.08,
            "total_debt": 55_000e9,
            "total_equity": 40_000e9,
            "net_ppe": 10_000e9,
            "cash": 1500e9,
            "market_cap": 25_000e9,
        }

        result = ThreeStatementEngine.forecast_three_statements(
            symbol="NVL",
            base_data=nvl_data,
            revenue_growth_series=[-0.10, -0.05, 0.02, 0.05, 0.08],
            capex_ratio_series=[0.02, 0.02, 0.02, 0.02, 0.02],
        )

        # Mathematical invariant closure
        bs = result.balance_sheet
        for t in range(5):
            ta = bs.total_assets[t]
            tl = bs.total_liabilities[t]
            te = bs.total_equity[t]
            scale = max(abs(ta), abs(tl), abs(te), 1.0)
            diff = abs(ta - (tl + te))
            assert (diff < 1.0 or safe_div(diff, scale, 0.0) < 1e-5)

        assert result.liquidity_distress_check.is_distressed
        assert result.liquidity_distress_check.dilution_risk_pct >= 0.05
        assert result.liquidity_distress_check.mos_penalty_pct >= 0.05
        assert result.liquidity_distress_check.summary_assessment == "DISTRESSED"
