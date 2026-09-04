# Milestone 2 Handoff Report: Debt & Capital Schedule Engine Test Specifications

**Agent:** `teamwork_preview_explorer_m2_3`  
**Working Directory:** `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m2_3\`  
**Target Test File:** `tests/test_debt_capital_schedule_engine.py`  
**Analysis Report:** `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m2_3\analysis_m2_test_spec.md`  
**Handoff Type:** Hard (Complete Test Specification Designed)  

---

## 1. Observation

Direct observations from codebase inspection:
1. **Damodaran Synthetic Rating Tables & Parameters**:
   - `services/valuation_engine.py` (lines 79-119) specifies:
     - $R_f = 0.0500$ (5.00%), $\text{Tax Rate} = 0.20$ (20.0%).
     - `DAMODARAN_SPREAD_LARGE_CAP` defines 14 rating tiers from $AAA$ (ICR $\ge 8.50$, spread $0.0065$) down to $D$ (ICR $< 0.50$, spread $0.1250$).
     - `DAMODARAN_SPREAD_SMALL_CAP` defines 14 rating tiers from $AAA$ (ICR $\ge 12.50$, spread $0.0065$) down to $D$ (ICR $< 0.80$, spread $0.1250$).
     - Table threshold is $5,000 \text{ Billion VND}$ market cap.
2. **Core Debt Amortization Dynamics**:
   - Amortization roll-forward identity:
     $$Debt\_Closing_t \equiv Debt\_Opening_t + New\_Borrowings_t - Principal\_Amortization_t$$
   - Period-to-period continuity:
     $$Debt\_Opening_{t+1} \equiv Debt\_Closing_t$$
   - Average debt midpoint:
     $$Average\_Debt_t \equiv \frac{Debt\_Opening_t + Debt\_Closing_t}{2}$$
   - Interest expense:
     $$Interest\_Expense_t \equiv Average\_Debt_t \times K_{d, pre-tax, t}$$
3. **Solvency Guards & Capital Allocation**:
   - If $ICR_t < 1.20$ or $NPAT_t \le 0$, dividend distribution is strictly locked to $0.0$ to protect balance sheet liquidity.
   - Standard payout: $Dividends\_Paid_t = \min\left(NPAT_t, NPAT_t \times \text{Payout\_Ratio}\right)$.
4. **Existing Test Architecture & Fixtures**:
   - `tests/test_working_capital_engine.py` and `tests/test_valuation_engine.py` establish a clean 4-tier / 5-tier Pytest structure with fixtures, parametrized test cases, and invariant assertions.

---

## 2. Logic Chain

1. **Step 1 (Interface Synchronization):** The test specifications must validate both standalone mathematical functions (`calculate_icr`, `calculate_synthetic_rating`, `calculate_cost_of_debt`) and the multi-year orchestrator (`project_debt_and_capital_schedule`, `build_debt_schedule_forecast`), returning typed Pydantic models `DebtSchedulePeriod` and `DebtCapitalScheduleResult`.
2. **Step 2 (Risk Hardening & Adversarial Robustness):** Companies in Vietnam face varying leverage conditions (e.g. HPG CapEx cycles, VIC high leverage, VNM net cash, distressed SMEs with operating losses). Tier 2 test cases systematically test zero debt, negative EBIT, covenant breaches ($ICR < 1.2$), extreme debt financing, and unparseable/null inputs.
3. **Step 3 (Mathematical Conservation Laws):** Balance sheets in 3-way models only close if debt schedules obey exact conservation laws. Tier 3 enforces 10 mathematical invariants including roll-forward closure ($< 10^{-5}$), non-negativity ($Debt \ge 0$, $Div \ge 0$), tax-shield consistency ($K_{d, after-tax} \equiv K_{d, pre-tax} \times (1 - t)$), and scale invariance.
4. **Step 4 (Empirical Calibration on VN30):** Real corporate tickers (HPG, VIC, MSN, VHM, GAS, VNM) and banking isolation (VCB, TCB) are codified into Tier 4 integration tests with realistic capital expenditure profiles and dividend expectations.
5. **Step 5 (Downstream Compatibility):** Tier 5 validates that all emitted fields match the exact requirements of `services/three_statement_engine.py` (M3) and `services/valuation_engine.py` (M4).

---

## 3. Caveats

1. **Scope Boundary:** This agent designed the complete test specification report. Actual implementation of `tests/test_debt_capital_schedule_engine.py` and `services/debt_capital_schedule_engine.py` is reserved for the Milestone 2 worker and test writer.
2. **Financial Institution Gating:** Banks (VCB, TCB, MBB) and Securities brokers (SSI) do not have standard industrial manufacturing debt amortizations (debt is their operating inventory / deposit liabilities). Tier 4 specifies safe isolation/gating for financial sectors.

---

## 4. Conclusion

A comprehensive, institutional-grade 4-Tier test specification containing **43 distinct automated test cases** across 5 test classes has been designed and published in:
`c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m2_3\analysis_m2_test_spec.md`

### Test Suite Structure:
- **Tier 1 (10 Tests):** Unit & Standard Calculations (Damodaran rating lookup, spreads, pre/after-tax $K_d$, 5Y debt roll-forward, dividend payout, share repurchases).
- **Tier 2 (12 Tests):** Boundary Value & Adversarial Edge Cases (Zero debt, zero EBIT, negative EBIT distress, covenant breaches, dirty inputs, exact Damodaran threshold step functions).
- **Tier 3 (10 Tests):** Accounting Invariants & Conservation Laws (Roll-forward identity, opening=prior closing, average debt midpoint, non-negativity, monotonicity, linear homogeneity).
- **Tier 4 (7 Tests):** Real-World VN30 Tickers (HPG, VIC, MSN, VHM, GAS, VNM, and Banking gating).
- **Tier 5 (4 Tests):** Pydantic Serialization & Downstream Integration Contracts for M3/M4.

---

## 5. Verification Method

To independently verify the test suite once implemented:

```bash
# 1. Run the full Debt & Capital Schedule Engine test suite
pytest tests/test_debt_capital_schedule_engine.py -v

# 2. Check line coverage target (>= 95%)
pytest tests/test_debt_capital_schedule_engine.py --cov=services/debt_capital_schedule_engine --cov-report=term-missing

# 3. Verify that entire test suite passes with 0 regressions across existing tests
pytest tests/
```

### Invalidation Conditions:
- Any test failure in `tests/test_debt_capital_schedule_engine.py`.
- Line coverage below $90\%$.
- Any deviation in Damodaran rating/spread determination from `services/valuation_engine.py`.
- Any non-zero drift ($> 10^{-5}$) in closing debt vs $(Opening + New - Amortization)$.
