# Comprehensive 4-Tier Test Specification: Debt & Capital Schedule Engine (Milestone 2)

**Author:** teamwork_preview_explorer_m2_3  
**Target File Under Test:** `services/debt_capital_schedule_engine.py`  
**Test Suite Target:** `tests/test_debt_capital_schedule_engine.py`  
**Status:** COMPLETE DESIGN SPECIFICATION  
**Coverage Target:** $\ge 95\%$ Line Coverage with 0 Failures  

---

## 1. Executive Summary & Architectural Overview

Milestone 2 implements the **Capital Allocation & Debt Schedule Engine** (`services/debt_capital_schedule_engine.py`), fulfilling Requirement 4 (R4) of the Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem.

This module provides institutional-grade debt roll-forwards, interest expense computations based on **Aswath Damodaran's synthetic credit ratings**, solvency-guarded dividend payouts, share repurchase modeling, and structured data outputs for downstream integration into:
1. **`services/three_statement_engine.py` (M3)**: Balance Sheet short-term and long-term debt liabilities, Income Statement interest expense, Cash Flow Statement debt drawdowns, principal repayments, and cash dividends.
2. **`services/valuation_engine.py` (M4)**: 5-Factor WACC cost of debt ($K_d$), Dividend Discount Models (DDM), Free Cash Flow to Equity (FCFE) debt adjustments, and Buffett Owner's Earnings.

To guarantee zero mathematical discrepancies, numerical stability under extreme economic distress, and strict accounting balance, this document specifies a comprehensive **4-Tier Test Architecture** (expanded with Tier 5 integration contracts) comprising **43 distinct test cases**.

---

## 2. Interface Contracts & Data Structures Under Test

The test suite validates compliance against the following Pydantic models and engine interface:

```python
from typing import Dict, List, Any, Optional, Tuple, Union
from pydantic import BaseModel, Field

class DebtSchedulePeriod(BaseModel):
    """Single period in the 5-year debt roll-forward schedule."""
    year: int
    opening_debt: float
    principal_amortization: float
    new_borrowings: float
    closing_debt: float
    average_debt: float
    interest_coverage_ratio: float
    synthetic_rating: str
    credit_spread_bps: float
    cost_of_debt_pre_tax: float
    cost_of_debt_after_tax: float
    interest_expense: float
    cash_interest_paid: float
    dividends_paid: float
    share_repurchases: float
    total_capital_returned: float
    is_covenant_breached: bool = False
    covenant_notes: Optional[str] = None

class CapitalAllocationPolicy(BaseModel):
    """Policy governing dividend distribution and leverage management."""
    target_dividend_payout_ratio: float = 0.30
    min_icr_for_dividend: float = 1.20
    debt_funded_capex_ratio: float = 0.40
    annual_amortization_rate: float = 0.20
    enable_share_repurchases: bool = False
    max_share_repurchase_pct_npat: float = 0.10

class DebtCapitalScheduleResult(BaseModel):
    """Container for the complete multi-year forecast schedule."""
    symbol: str
    sector: str
    market_cap: float
    is_large_cap: bool
    policy: CapitalAllocationPolicy
    schedule: List[DebtSchedulePeriod]
    summary: Dict[str, Any]
```

### Core Engine Interface:
```python
class DebtCapitalScheduleEngine:
    @staticmethod
    def calculate_icr(ebit: float, interest_expense: float) -> float: ...

    @staticmethod
    def calculate_synthetic_rating(
        icr: float,
        is_large_cap: bool = True,
    ) -> Tuple[str, float]: ...

    @staticmethod
    def calculate_cost_of_debt(
        icr: float,
        is_large_cap: bool = True,
        rf: float = 0.0500,
        tax_rate: float = 0.20,
    ) -> Tuple[str, float, float, float]: ...

    @staticmethod
    def project_debt_and_capital_schedule(
        base_debt: float,
        ebit_series: List[float],
        npat_series: List[float],
        capex_series: List[float],
        market_cap: float = 10_000e9,
        policy: Optional[CapitalAllocationPolicy] = None,
        rf: float = 0.0500,
        tax_rate: float = 0.20,
        start_year: int = 2026,
    ) -> List[DebtSchedulePeriod]: ...

    @staticmethod
    def build_debt_schedule_forecast(
        symbol: str,
        base_data: Dict[str, Any],
        ebit_forecast: List[float],
        npat_forecast: List[float],
        capex_forecast: List[float],
        policy: Optional[CapitalAllocationPolicy] = None,
        start_year: int = 2026,
    ) -> DebtCapitalScheduleResult: ...
```

---

## 3. Mathematical Foundations & Damodaran Calibration Tables

### 3.1 Damodaran Rating & Spread Mappings
Synchronized exactly with `services/valuation_engine.py` (lines 87-119):

**Large-Cap Firms ($Market\_Cap > 5,000 \text{ Billion VND}$):**
| Minimum ICR ($\ge$) | Synthetic Rating | Spread over $R_f$ (bps) | Spread ($s$) | Pre-Tax $K_d$ ($R_f=5.0\%$) |
|---|---|---|---|---|
| $8.50$ | AAA | 65 bps | $0.0065$ | $5.65\%$ |
| $6.50$ | AA | 90 bps | $0.0090$ | $5.90\%$ |
| $5.50$ | A+ | 115 bps | $0.0115$ | $6.15\%$ |
| $4.25$ | A | 135 bps | $0.0135$ | $6.35\%$ |
| $3.00$ | A- | 160 bps | $0.0160$ | $6.60\%$ |
| $2.50$ | BBB | 210 bps | $0.0210$ | $7.10\%$ |
| $2.25$ | BB+ | 285 bps | $0.0285$ | $7.85\%$ |
| $2.00$ | BB | 340 bps | $0.0340$ | $8.40\%$ |
| $1.75$ | B+ | 425 bps | $0.0425$ | $9.25\%$ |
| $1.50$ | B | 525 bps | $0.0525$ | $10.25\%$ |
| $1.25$ | B- | 650 bps | $0.0650$ | $11.50\%$ |
| $0.80$ | CCC | 850 bps | $0.0850$ | $13.50\%$ |
| $0.50$ | CC | 1000 bps | $0.1000$ | $15.00\%$ |
| $-\infty$ | D | 1250 bps | $0.1250$ | $17.50\%$ |

**Small-Cap Firms ($Market\_Cap \le 5,000 \text{ Billion VND}$):**
| Minimum ICR ($\ge$) | Synthetic Rating | Spread over $R_f$ (bps) | Spread ($s$) | Pre-Tax $K_d$ ($R_f=5.0\%$) |
|---|---|---|---|---|
| $12.50$ | AAA | 65 bps | $0.0065$ | $5.65\%$ |
| $9.50$ | AA | 90 bps | $0.0090$ | $5.90\%$ |
| $7.50$ | A+ | 115 bps | $0.0115$ | $6.15\%$ |
| $6.00$ | A | 135 bps | $0.0135$ | $6.35\%$ |
| $4.50$ | A- | 160 bps | $0.0160$ | $6.60\%$ |
| $4.00$ | BBB | 210 bps | $0.0210$ | $7.10\%$ |
| $3.50$ | BB+ | 285 bps | $0.0285$ | $7.85\%$ |
| $3.00$ | BB | 340 bps | $0.0340$ | $8.40\%$ |
| $2.50$ | B+ | 425 bps | $0.0425$ | $9.25\%$ |
| $2.00$ | B | 525 bps | $0.0525$ | $10.25\%$ |
| $1.50$ | B- | 650 bps | $0.0650$ | $11.50\%$ |
| $1.25$ | CCC | 850 bps | $0.0850$ | $13.50\%$ |
| $0.80$ | CC | 1000 bps | $0.1000$ | $15.00\%$ |
| $-\infty$ | D | 1250 bps | $0.1250$ | $17.50\%$ |

### 3.2 Dynamic Schedule Equations
1. **Amortization & Borrowings:**
   $$Principal\_Amortization_t = \min\left(Debt\_Opening_t, Debt\_Opening_t \times \text{Amortization\_Rate}\right)$$
   $$New\_Borrowings_t = \max(0, CapEx_t \times \text{Debt\_Funded\_Ratio})$$
   $$Debt\_Closing_t = Debt\_Opening_t + New\_Borrowings_t - Principal\_Amortization_t$$
   $$Debt\_Opening_{t+1} = Debt\_Closing_t$$
2. **Average Debt & Interest Expense:**
   $$Average\_Debt_t = \frac{Debt\_Opening_t + Debt\_Closing_t}{2}$$
   $$Interest\_Expense_t = Average\_Debt_t \times K_{d, pre-tax, t}$$
   $$Cash\_Interest\_Paid_t = Interest\_Expense_t$$
3. **Solvency-Guarded Capital Allocation:**
   $$\text{If } ICR_t < 1.20 \text{ or } NPAT_t \le 0: \quad Dividends\_Paid_t = 0.0, \quad Share\_Repurchases_t = 0.0$$
   $$\text{Else}: \quad Dividends\_Paid_t = \min\left(NPAT_t, NPAT_t \times \text{Payout\_Ratio}\right)$$

---

## 4. Test Taxonomy & 4-Tier Test Architecture

```
tests/test_debt_capital_schedule_engine.py
├── TestTier1StandardCalculations           (10 Tests: Unit math, ICR, Damodaran lookup, 5Y roll-forward)
├── TestTier2BoundaryAndAdversarial         (12 Tests: Zero debt, EBIT<=0, extreme interest, covenant breach)
├── TestTier3AccountingInvariants           (10 Tests: Roll-forward identity, midpoints, monotonicity, additivity)
├── TestTier4VN30Integration                (7 Tests: HPG, VIC, MSN, VHM, GAS, VNM, Banking isolation)
└── TestTier5PydanticAndIntegrationContract (4 Tests: Schemas, serialization, M3/M4 integration contracts)
Total: 43 Exhaustive Automated Pytest Test Cases
```

---

## 5. Tier 1: Unit & Standard Calculation Specifications

### Test 1.1: `test_damodaran_synthetic_rating_lookup_large_cap`
- **Objective:** Verify that every ICR value correctly maps to the exact Damodaran rating and credit spread for large-cap firms ($> 5,000\text{B VND}$).
- **Parametrized Inputs:**
  - `(10.0, "AAA", 0.0065)`
  - `(7.50, "AA", 0.0090)`
  - `(6.00, "A+", 0.0115)`
  - `(5.00, "A", 0.0135)`
  - `(3.50, "A-", 0.0160)`
  - `(2.75, "BBB", 0.0210)`
  - `(2.35, "BB+", 0.0285)`
  - `(2.10, "BB", 0.0340)`
  - `(1.85, "B+", 0.0425)`
  - `(1.60, "B", 0.0525)`
  - `(1.35, "B-", 0.0650)`
  - `(1.00, "CCC", 0.0850)`
  - `(0.65, "CC", 0.1000)`
  - `(0.20, "D", 0.1250)`
- **Assertion:** `rating == expected_rating` and `math.isclose(spread, expected_spread, abs_tol=1e-5)`.

### Test 1.2: `test_damodaran_synthetic_rating_lookup_small_cap`
- **Objective:** Verify rating mapping under the stricter small-cap ICR schedule ($\le 5,000\text{B VND}$).
- **Parametrized Inputs:**
  - `(15.0, "AAA", 0.0065)`
  - `(10.0, "AA", 0.0090)`
  - `(8.00, "A+", 0.0115)`
  - `(6.50, "A", 0.0135)`
  - `(5.00, "A-", 0.0160)`
  - `(4.20, "BBB", 0.0210)`
  - `(3.70, "BB+", 0.0285)`
  - `(3.20, "BB", 0.0340)`
  - `(2.60, "B+", 0.0425)`
  - `(2.10, "B", 0.0525)`
  - `(1.60, "B-", 0.0650)`
  - `(1.30, "CCC", 0.0850)`
  - `(0.90, "CC", 0.1000)`
  - `(0.50, "D", 0.1250)`
- **Assertion:** `rating == expected_rating` and `math.isclose(spread, expected_spread, abs_tol=1e-5)`.

### Test 1.3: `test_pre_and_after_tax_cost_of_debt_calculation`
- **Inputs:** $ICR = 3.50$, Large-Cap ($A-$, Spread $1.60\%$), $R_f = 0.0500$, $\text{Tax Rate} = 0.20$.
- **Expected Calculations:**
  - $K_{d, pre-tax} = 0.0500 + 0.0160 = 0.0660$ ($6.60\%$)
  - $K_{d, after-tax} = 0.0660 \times (1 - 0.20) = 0.0528$ ($5.28\%$)
- **Assertion:** `math.isclose(kd_pre, 0.0660, rel_tol=1e-5)` and `math.isclose(kd_after, 0.0528, rel_tol=1e-5)`.

### Test 1.4: `test_interest_coverage_ratio_standard`
- **Inputs:** $EBIT = 15,000.0$, $Interest\_Expense = 3,000.0$.
- **Expected:** $ICR = 15000.0 / 3000.0 = 5.0$.
- **Assertion:** `math.isclose(icr, 5.0, rel_tol=1e-5)`.

### Test 1.5: `test_5year_debt_roll_forward_constant_amortization`
- **Inputs:** $Opening\_Debt_0 = 10,000.0$, $Amortization\_Rate = 0.20$, $New\_Borrowings = [0, 0, 0, 0, 0]$.
- **Expected Values:**
  - Year 1: Opening 10000, Amort 2000, Closing 8000, Average 9000
  - Year 2: Opening 8000, Amort 1600, Closing 6400, Average 7200
  - Year 3: Opening 6400, Amort 1280, Closing 5120, Average 5760
  - Year 4: Opening 5120, Amort 1024, Closing 4096, Average 4608
  - Year 5: Opening 4096, Amort 819.2, Closing 3276.8, Average 3686.4
- **Assertion:** All period values match geometric amortization schedule within $10^{-4}$ tolerance.

### Test 1.6: `test_5year_debt_roll_forward_with_capex_debt_financing`
- **Inputs:** $Opening\_Debt_0 = 5,000.0$, $Amortization\_Rate = 0.10$, $CapEx = [2000, 2500, 3000, 3500, 4000]$, $Debt\_Funded\_Ratio = 0.50$.
- **Expected Year 1:**
  - $New\_Borrowing_1 = 2000 \times 0.50 = 1000.0$
  - $Amort_1 = 5000 \times 0.10 = 500.0$
  - $Closing_1 = 5000 + 1000 - 500 = 5500.0$
  - $Average_1 = (5000 + 5500) / 2 = 5250.0$
- **Assertion:** `closing_debt == 5500.0` and `new_borrowings == 1000.0`.

### Test 1.7: `test_period_interest_expense_and_cash_paid`
- **Inputs:** $Average\_Debt = 6,000.0$, $K_{d, pre-tax} = 0.0750$.
- **Expected:** $Interest\_Expense = 6000 \times 0.0750 = 450.0$, $Cash\_Interest\_Paid = 450.0$.
- **Assertion:** `math.isclose(period.interest_expense, 450.0, rel_tol=1e-5)` and `math.isclose(period.cash_interest_paid, 450.0, rel_tol=1e-5)`.

### Test 1.8: `test_standard_dividend_payout_and_retained_earnings`
- **Inputs:** $NPAT = 4,000.0$, $Payout\_Ratio = 0.35$, $ICR = 4.50$ (Safe).
- **Expected:** $Dividends\_Paid = 4000 \times 0.35 = 1400.0$, $Retained\_Profits = 2600.0$.
- **Assertion:** `math.isclose(period.dividends_paid, 1400.0, rel_tol=1e-5)`.

### Test 1.9: `test_share_repurchase_capital_allocation`
- **Inputs:** $NPAT = 5,000.0$, $Dividend\_Payout = 0.30$, $Enable\_Repurchase = True$, $Repurchase\_Ratio = 0.10$, $ICR = 6.0$.
- **Expected:**
  - $Dividends = 1500.0$
  - $Repurchases = 500.0$
  - $Total\_Capital\_Returned = 2000.0$
- **Assertion:** `math.isclose(period.share_repurchases, 500.0, rel_tol=1e-5)` and `math.isclose(period.total_capital_returned, 2000.0, rel_tol=1e-5)`.

### Test 1.10: `test_build_debt_schedule_full_pipeline`
- **Inputs:** Full stock profile (`symbol="HPG"`, `sector="VNMAT"`, `market_cap=165_000e9`), 5-year forecasted EBIT, NPAT, and CapEx vectors.
- **Assertion:** Returns valid `DebtCapitalScheduleResult`, contains 5 periods with consecutive years (e.g. 2026-2030), summary contains `weighted_average_kd_pre_tax` and `total_dividends_5y`.

---

## 6. Tier 2: Boundary Value, Extreme Values & Adversarial Edge Cases

### Test 2.1: `test_zero_debt_pristine_balance_sheet`
- **Condition:** $Base\_Debt = 0.0$, $CapEx = [0, 0, 0, 0, 0]$, $EBIT = 5,000.0$, $Interest = 0.0$.
- **Expected Behavior:**
  - $ICR = 100.0$ (or safe upper bound).
  - Synthetic Rating: $AAA$, Spread: $0.0065$ ($0.65\%$).
  - $Interest\_Expense = 0.0$, $Cash\_Interest\_Paid = 0.0$.
  - $Closing\_Debt_t = 0.0$ for all 5 years.
  - Zero `#DIV/0`, `NaN`, or `Inf` errors.

### Test 2.2: `test_zero_ebit_operating_breakeven`
- **Condition:** $EBIT = 0.0$, $Interest\_Expense = 500.0$.
- **Expected Behavior:**
  - $ICR = 0.0$ or $-1.0$.
  - Synthetic Rating: $D$, Spread: $0.1250$ ($12.50\%$).
  - Pre-tax $K_d = 5.0\% + 12.5\% = 17.50\%$.
  - Solvency guard triggers: Dividend payout forced to $0.0$.

### Test 2.3: `test_negative_ebit_operating_loss_distress`
- **Condition:** $EBIT = -5,000.0$, $Interest\_Expense = 1,200.0$.
- **Expected Behavior:**
  - $ICR = -1.0$ (distressed floor).
  - Synthetic Rating: $D$, Spread: $0.1250$.
  - Pre-tax $K_d = 17.50\%$.
  - $is\_covenant\_breached = True$, $Dividends\_Paid = 0.0$, $Share\_Repurchases = 0.0$.

### Test 2.4: `test_covenant_breach_dividend_suspension`
- **Condition:** $NPAT = 2,000.0$ (positive net income), but $EBIT = 800.0$, $Interest = 1,000.0 \implies ICR = 0.80 < 1.20$.
- **Expected Behavior:**
  - Solvency firewall blocks dividend distribution despite positive NPAT.
  - $Dividends\_Paid = 0.0$ (instead of $2000 \times 0.30 = 600$).
  - $is\_covenant\_breached = True$, `covenant_notes` records "ICR below 1.20 threshold".

### Test 2.5: `test_negative_npat_dividend_guard`
- **Condition:** $NPAT = -1,500.0$, $Payout\_Ratio = 0.50$, $ICR = 2.50$.
- **Expected Behavior:**
  - $Dividends\_Paid = 0.0$ (never distribute negative dividends).

### Test 2.6: `test_extreme_debt_100pct_financing`
- **Condition:** $Base\_Debt = 10,000.0$, $CapEx = [50000, 60000, 70000, 80000, 90000]$, $Debt\_Funded\_Ratio = 1.00$.
- **Expected Behavior:**
  - Engine tracks debt accumulating to $> 300,000.0$ without numeric overflow.
  - $ICR$ gracefully downgrades as interest expense surges, spreading $K_d$ up to $17.50\%$.

### Test 2.7: `test_zero_payout_and_100pct_payout_extremes`
- **Condition A:** $Payout\_Ratio = 0.0 \implies Dividends = 0.0$.
- **Condition B:** $Payout\_Ratio = 1.0 \implies Dividends = NPAT$ (when $ICR \ge 1.20$).
- **Assertion:** Exact equality verified on boundary values.

### Test 2.8: `test_negative_amortization_and_negative_borrowings_clamping`
- **Adversarial Input:** User provides $Amortization\_Rate = -0.30$ or $CapEx = -5,000.0$.
- **Expected Behavior:** Clamped safely to $0.0$. No negative borrowings generated.

### Test 2.9: `test_dirty_string_and_null_imputation_handling`
- **Adversarial Input:**
  ```python
  base_data = {
      "total_debt": "15,000.0",
      "interest_expense": "--",
      "ebit": None,
      "market_cap": "nan",
  }
  ```
- **Expected Behavior:** Sanitized without unhandled `TypeError` or `ValueError`. Imputes fallback rating $D$ or sector prior.

### Test 2.10: `test_damodaran_boundary_step_functions`
- **Exact Step Transition Verification:**
  - Large Cap $ICR = 8.5000 \implies AAA$ ($0.65\%$), $ICR = 8.4999 \implies AA$ ($0.90\%$)
  - Large Cap $ICR = 6.5000 \implies AA$ ($0.90\%$), $ICR = 6.4999 \implies A+$ ($1.15\%$)
  - Large Cap $ICR = 0.8000 \implies CCC$ ($8.50\%$), $ICR = 0.7999 \implies CC$ ($10.00\%$)
  - Large Cap $ICR = 0.5000 \implies CC$ ($10.00\%$), $ICR = 0.4999 \implies D$ ($12.50\%$)
- **Assertion:** Exact step transitions match theoretical Damodaran step function without epsilon leakage.

### Test 2.11: `test_market_cap_large_small_boundary`
- **Threshold:** $5,000.0 \text{ Billion VND}$.
- **Scenario:** $ICR = 7.00$.
  - At $Market\_Cap = 5,000.01\text{B} \implies$ Large-Cap $\implies AA$ ($Spread = 0.90\%$).
  - At $Market\_Cap = 4,999.99\text{B} \implies$ Small-Cap $\implies A$ ($Spread = 1.35\%$).
- **Assertion:** Strict separation of Large vs Small cap tables at boundary.

### Test 2.12: `test_amortization_exceeding_total_debt_clamped`
- **Condition:** $Debt\_Opening = 1,000.0$, $Amortization\_Rate = 1.50$ (150%) or fixed repayment $= 2,500.0$.
- **Expected Behavior:** Principal amortization capped at available debt $1,000.0$. $Closing\_Debt = 0.0$ (never negative).

---

## 7. Tier 3: Accounting Invariants & Conservation Laws

Every test in Tier 3 enforces mathematical equality across multiple randomized and edge-case permutations.

### Test 3.1: `test_debt_balance_roll_forward_invariant`
$$\forall t \in [1, 5]: \quad \left| Debt\_Closing_t - \left(Debt\_Opening_t + New\_Borrowings_t - Principal\_Amortization_t\right) \right| < 10^{-5}$$
- **Verification:** Loop over 20 randomized param sets (varying initial debt, amortization rates, CapEx series).

### Test 3.2: `test_period_linkage_opening_equals_prior_closing_invariant`
$$\forall t \in [2, 5]: \quad Debt\_Opening_t \equiv Debt\_Closing_{t-1}$$
- **Verification:** Strict equality check across all projected horizons.

### Test 3.3: `test_average_debt_midpoint_invariant`
$$\forall t: \quad Average\_Debt_t \equiv \frac{Debt\_Opening_t + Debt\_Closing_t}{2}$$

### Test 3.4: `test_interest_expense_exact_product_invariant`
$$\forall t: \quad \left| Interest\_Expense_t - \left(Average\_Debt_t \times K_{d, pre-tax, t}\right) \right| < 10^{-5}$$

### Test 3.5: `test_after_tax_cost_of_debt_tax_shield_invariant`
$$\forall t: \quad \left| K_{d, after-tax, t} - \left(K_{d, pre-tax, t} \times (1 - \text{Tax Rate})\right) \right| < 10^{-6}$$

### Test 3.6: `test_non_negative_debt_and_payout_invariant`
$$\forall t: \quad Debt\_Closing_t \ge 0, \quad Dividends\_Paid_t \ge 0, \quad Cash\_Interest\_Paid_t \ge 0$$

### Test 3.7: `test_dividend_solvency_envelope_invariant`
$$\forall t: \quad Dividends\_Paid_t \le \max(0, NPAT_t)$$
$$\text{If } ICR_t < 1.20 \implies Dividends\_Paid_t \equiv 0.0$$

### Test 3.8: `test_damodaran_spread_monotonicity_invariant`
$$\forall ICR_a > ICR_b \implies Spread(ICR_a) \le Spread(ICR_b) \quad \text{and} \quad K_d(ICR_a) \le K_d(ICR_b)$$
- **Verification:** Monotonicity verified across continuous range $ICR \in [-2.0, 20.0]$ with step $0.1$.

### Test 3.9: `test_linear_homogeneity_scale_invariance`
- **Theorem:** If all nominal VND variables ($Debt, EBIT, NPAT, CapEx$) are scaled by scalar $k > 0$:
  - $ICR$ remains invariant: $ICR(k \cdot X) = ICR(X)$.
  - Synthetic rating & $K_d$ remain invariant.
  - All nominal schedule items ($Debt\_Closing, Interest, Dividends$) scale identically by $k$.
- **Verification:** Test with $k = 4.25$ against unscaled baseline.

### Test 3.10: `test_zero_growth_steady_state_amortization_invariance`
- **Theorem:** In the absence of new borrowings ($CapEx = 0$), $Debt_t = Debt_0 \times (1 - \delta)^t$, where $\delta$ is constant amortization rate.
- **Assertion:** $|Debt\_Closing_t - Debt_0 (1 - \delta)^t| < 10^{-4}$ for all $t=1..5$.

---

## 8. Tier 4: Real-World VN30 Tickers Integration Specifications

Real-world constituents from HOSE VN30 tested with actual balance sheet and income characteristics:

| Symbol | Company Name | Sector | Real Debt (B VND) | EBIT (B VND) | CapEx Cycle | Payout Policy | Key Risk Under Test |
|---|---|---|---|---|---|---|---|
| **HPG** | Hoa Phat Group | VNMAT | 55,000 | 20,000 | High (Dung Quat 2: 15,000B/yr) | 20% Cash | Large CapEx debt financing capacity |
| **VIC** | Vingroup | VNREAL | 160,000 | 18,000 | Intensive (EV + Real Estate) | 0% Cash | High leverage, ICR covenant monitoring |
| **MSN** | Masan Group | VNCONS | 68,000 | 6,500 | Moderate (3,000B/yr) | 10% Cash | Leverage deleveraging path |
| **VHM** | Vinhomes | VNREAL | 45,000 | 25,000 | Moderate | 25% Cash | Strong operating cash flow, moderate ICR |
| **GAS** | PV Gas | VNENE | 8,000 | 14,000 | Low | 60% Cash | Low leverage, pristine ICR > 15 ($AAA$) |
| **VNM** | Vinamilk | VNCONS | 5,000 | 11,000 | Maintenance (1,500B/yr) | 70% Cash | High dividend payout, net cash fortress |
| **VCB** | Vietcombank | VNBNK | N/A (Bank) | 45,000 | IT / Infra | 25% Cash | Financial sector safe isolation |

### Test 4.1: `test_vn30_hpg_steel_expansion_debt_cycle`
- Verifies heavy CapEx schedule ($15,000\text{B/yr}$, 50% debt-funded), Opening debt $55,000\text{B}$.
- Asserts that closing debt peaks and stabilizes, $ICR$ remains healthy in $[4.0, 6.0]$ ($A$ to $A+$ rating), and dividends are permitted.

### Test 4.2: `test_vn30_vic_vhm_real_estate_leverage_schedule`
- Tests high debt ($160,000\text{B}$), interest rate sensitivity, and bond amortization schedule.
- Validates covenant trigger: if operating income fluctuates causing $ICR < 1.20$, dividend distribution immediately locks down.

### Test 4.3: `test_vn30_msn_consumer_debt_restructuring`
- Tests 5-year deleveraging plan where debt amortization rate is set to $25\%$ and debt-funded CapEx is restricted to $20\%$.
- Asserts that total debt decreases monotonically over 5 years and synthetic rating upgrades from $BB$ to $BBB$.

### Test 4.4: `test_vn30_vnm_consumer_staples_cash_rich_high_dividend`
- Tests cash-rich balance sheet with $5,000\text{B}$ debt, $11,000\text{B}$ EBIT ($ICR > 15 \implies AAA$), and high dividend payout ($70\%$).
- Asserts full dividend delivery across all 5 years with zero covenant alerts.

### Test 4.5: `test_vn30_gas_energy_utility_pristine_coverage`
- Tests low leverage utility profile ($8,000\text{B}$ debt, $14,000\text{B}$ EBIT).
- Asserts lowest credit spread ($0.0065$) and highest safety rating throughout 5-year horizon.

### Test 4.6: `test_vn30_banking_financial_gating_isolation`
- Parametrized over `["VCB", "TCB", "MBB", "ACB", "BID", "CTG", "SSI", "BVH"]`.
- Asserts that financial sector tickers are handled safely: either flagged with `is_financial_sector = True` or debt schedule properly isolated from standard industrial manufacturing leverage formulas.

### Test 4.7: `test_full_vn30_universe_batch_execution`
- Batch execution over 30 constituents in a single automated loop.
- Asserts $100\%$ execution success rate, 0 uncaught exceptions, 0 NaNs, and $100\%$ accounting invariant pass rate.

---

## 9. Tier 5: Pydantic Contract, Helper & Downstream Integration Integrity

### Test 5.1: `test_pydantic_debt_schedule_period_schema`
- Validates Pydantic serialization via `.model_dump()` and JSON round-trip `DebtSchedulePeriod.model_validate_json(...)`.
- Confirms all 16 attributes maintain strict float/int/str typing.

### Test 5.2: `test_pydantic_debt_capital_schedule_result_schema`
- Validates container model `DebtCapitalScheduleResult`, ensuring nested `DebtSchedulePeriod` objects and summary dictionaries deserialize without data loss.

### Test 5.3: `test_downstream_three_statement_engine_integration_contract`
- Verifies that the dictionary representation emitted by `DebtCapitalScheduleEngine` contains exact keys required by `services/three_statement_engine.py` (M3):
  - Balance Sheet lines: `opening_debt`, `closing_debt`, `average_debt`
  - Income Statement lines: `interest_expense`, `cost_of_debt_pre_tax`
  - Cash Flow lines: `new_borrowings` (Cash from Financing - Debt Drawdown), `principal_amortization` (Cash from Financing - Debt Repayment), `cash_interest_paid` (Operating Cash Flow), `dividends_paid` (Cash from Financing - Dividends Paid).

### Test 5.4: `test_downstream_valuation_engine_integration_contract`
- Verifies that $K_{d, pre-tax}$ and $K_{d, after-tax}$ match the output of `WACCEngine.calculate(...)` in `services/valuation_engine.py` for identical inputs.
- Verifies that DDM models in M4 can directly consume `dividends_paid` vector and FCFE models can consume `new_borrowings - principal_amortization`.

---

## 10. Concrete Pytest Code Architecture Blueprint

The test file `tests/test_debt_capital_schedule_engine.py` will be structured as follows:

```python
"""
=============================================================================
COMPREHENSIVE 4-TIER TEST SUITE: DEBT & CAPITAL SCHEDULE ENGINE (MILESTONE 2)
=============================================================================
Tiers Covered:
- Tier 1: Unit & Standard Calculations (ICR, Damodaran ratings, 5Y roll-forward)
- Tier 2: Boundary Value, Extreme Values & Adversarial Edge Cases
- Tier 3: Cross-Consistency & Accounting Invariants
- Tier 4: Real-World VN30 Constituent Integration (HPG, VIC, MSN, VHM, GAS, VNM)
- Tier 5: Pydantic Contract & Downstream Integration Contracts
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
    DAMODARAN_SPREAD_LARGE_CAP,
    DAMODARAN_SPREAD_SMALL_CAP,
    DEFAULT_RF,
    DEFAULT_TAX_RATE,
    safe_div,
    clamp,
    sanitize_float,
)

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
    ...

# =============================================================================
# TIER 2: BOUNDARY VALUE & ADVERSARIAL EDGE CASES
# =============================================================================
class TestTier2BoundaryAndAdversarial:
    ...

# =============================================================================
# TIER 3: ACCOUNTING INVARIANTS & CONSERVATION LAWS
# =============================================================================
class TestTier3AccountingInvariants:
    ...

# =============================================================================
# TIER 4: REAL-WORLD VN30 INTEGRATION
# =============================================================================
class TestTier4VN30Integration:
    ...

# =============================================================================
# TIER 5: PYDANTIC CONTRACT & DOWNSTREAM INTEGRATION
# =============================================================================
class TestTier5PydanticAndIntegrationContract:
    ...
```

---

## 11. Verification Command & Acceptance Criteria

### Execution Command:
```bash
pytest tests/test_debt_capital_schedule_engine.py -v --cov=services/debt_capital_schedule_engine --cov-report=term-missing
```

### Acceptance Thresholds:
1. **0 Test Failures** ($43 / 43$ tests passing).
2. **$\ge 95\%$ Line Coverage** on `services/debt_capital_schedule_engine.py`.
3. **$100\%$ Invariant Preservation**: Zero floating-point drift ($|\text{Error}| < 10^{-5}$) across all 5 forecast years.
4. **$100\%$ VN30 Constituent Robustness**: Clean execution with zero `#DIV/0`, `NaN`, `Inf`, or unhandled exceptions.
