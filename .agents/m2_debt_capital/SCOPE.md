# Scope: Milestone 2 — Capital Allocation & Debt Schedule Engine (R4)

## Architecture & Responsibilities
Milestone 2 implements the complete Capital Allocation & Debt Schedule Engine in `services/debt_capital_schedule_engine.py` and unit tests in `tests/test_debt_capital_schedule_engine.py`.

## Key Capabilities
1. **Interest Coverage Ratio (ICR) & Damodaran Synthetic Rating**:
   - Map ICR ($EBIT / \text{Interest Expense}$) to Damodaran synthetic credit ratings ($AAA, AA, A+, A, A-, BBB, BB+, BB, B+, B, B-, CCC, CC, C, D$) for both Large-Cap and Small-Cap firms using `DAMODARAN_SPREAD_LARGE_CAP` and `DAMODARAN_SPREAD_SMALL_CAP`.
   - Compute pre-tax cost of debt ($K_{d, \text{pre-tax}} = R_f + \text{Credit Spread}$, with $R_f = 5.0\%$) and after-tax cost of debt ($K_{d, \text{after-tax}} = K_{d, \text{pre-tax}} \times (1 - \text{Tax Rate})$).
2. **5-Year Debt Amortization & Roll-Forward Schedule**:
   - Track Opening Debt, Mandatory Principal Amortization repayments, New Debt drawdowns (linked to debt-financed CapEx or expansion), Closing Debt, and Average Debt balance.
   - Compute period interest expense ($Interest\_Expense_t = Average\_Debt_t \times K_{d, \text{pre-tax}}$) and cash interest paid.
3. **Solvency-Guarded Capital Allocation & Payout Policy**:
   - Model dividend payout policy ($\text{Dividends}_t = \max(0, \text{NPAT}_t \times \text{Payout Ratio})$) and share repurchase allocation.
   - Solvency guard: ensure dividend payouts do not exceed available cash or breach debt covenants ($ICR < 1.2$ or $Cash < 0$).
4. **Integration Linkages for Downstream Engines**:
   - Provide clean data structures feeding `services/three_statement_engine.py` (M3) and `services/valuation_engine.py` (M4: dynamic $K_d$, DDM, FCFE, Owner's Earnings).

## Code Layout
- `services/debt_capital_schedule_engine.py` (Worker write ownership)
- `tests/test_debt_capital_schedule_engine.py` (Worker / Reviewer / Challenger test verification)

## Acceptance Criteria
- 100% accurate synthetic rating and spread determination across all ICR intervals.
- Amortization roll-forwards maintain exact balance: $Closing\_Debt_t \equiv Opening\_Debt_t + New\_Borrowings_t - Principal\_Amortization_t$.
- Solvency guard prevents illegal dividends when in distressed ICR regimes.
- Automated pytest suite `tests/test_debt_capital_schedule_engine.py` passes with 0 failures and $\ge 90\%$ line coverage.
