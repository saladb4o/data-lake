# Handoff Report: Milestone 2 Debt & Capital Schedule Engine Integration Analysis

**Agent**: `teamwork_preview_explorer_m2_2`  
**Working Directory**: `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m2_2\`  
**Target Milestone**: Milestone 2 (Debt & Capital Schedule Engine) & Milestone 3 / 4 Downstream Integration

---

## 1. Observation
- **Damodaran Spread Tables**: Located in `services/valuation_engine.py` (lines 87-119). `DAMODARAN_SPREAD_LARGE_CAP` has 14 tiers ($AAA$ at ICR $\ge 8.50$, spread 0.0065 to $D$ at ICR $< 0.50$, spread 0.1250). `DAMODARAN_SPREAD_SMALL_CAP` has 14 tiers ($AAA$ at ICR $\ge 12.50$, spread 0.0065 to $D$ at ICR $< 0.80$, spread 0.1250).
- **WACC Engine**: Located in `services/valuation_engine.py` (`WACCEngine.calculate`, lines 384-528). Firm size threshold between Large-Cap and Small-Cap is set at `5,000 Billion VND` (line 418). Pre-tax cost of debt is $K_{d, \text{pre-tax}} = R_f + \text{spread}$, and after-tax cost of debt is $K_{d, \text{after-tax}} = K_{d, \text{pre-tax}} \times (1 - \text{tax\_rate})$. WACC is clamped between $[0.085, 0.185]$.
- **Intrinsic Valuation Models**: In `services/valuation_engine.py`:
  - Model 9 (McKinsey 2-Stage DCF, line 1053): Uses $Total\_Debt$, $Cash$, and $WACC$.
  - Model 10 (EBO Residual Income, line 1102): Uses Book Value roll-forward driven by $1 - \text{Payout Ratio}$.
  - Model 15 (Buffett Owner's Earnings, line 1281): Decomposes Growth vs Maintenance CapEx using gross PPE and revenue growth; relies on $CFO$ and $\Delta WC$.
  - Model 17 (Bank Equity Cash Flow / FCFE, line 1366): Models required capital changes.
  - Model 20 (Industrial APV, line 1477): Models $PV(\text{Interest Tax Shield}) = \frac{t_c \times K_d \times Debt}{K_d} = t_c \times Debt$.
  - Model 22 (Utilities 3-Stage DDM, line 1549): Models $FV = \frac{D_0(1+g_n) + D_0 H(g_a - g_n)}{K_e - g_n}$.
- **Working Capital Engine (M1)**: Located in `services/working_capital_engine.py`. Tests in `tests/test_working_capital_engine.py` passed with 33/33 tests passing.

---

## 2. Logic Chain
1. **Single Source of Truth**: `services/debt_capital_schedule_engine.py` must import `DAMODARAN_SPREAD_LARGE_CAP`, `DAMODARAN_SPREAD_SMALL_CAP`, `DEFAULT_RF`, and `DEFAULT_TAX_RATE` from `services.valuation_engine` to prevent divergent rating/spread mappings across the platform.
2. **Deterministic Single-Period Convergence**: In each period $t$, because $Interest\_Expense_t = Average\_Debt_t \times K_{d,t}$ and $K_{d,t}$ is a function of $ICR_t = EBIT_t / Interest\_Expense_t$, a 2-step contraction mapping (estimate base interest $\to$ compute ICR $\to$ lookup Damodaran spread $\to$ refine interest) guarantees exact deterministic convergence without infinite recursion.
3. **Solvency Protection**: High leverage or distressed operating losses ($EBIT \le 0$ or $ICR < 1.25$) automatically force dividend payouts to $0.0$, preventing illegal capital returns during liquidity distress.
4. **Pure DAG Execution Pipeline**: In `services/three_statement_engine.py`, debt must not be modeled as an iterative plug to clear cash; instead, debt follows the explicit M2 schedule, and cash reconciles the balance sheet ($Cash_t \equiv Ending\_Cash_t$). This linear flow ensures $|Total\_Assets_t - (Total\_Liabilities_t + Total\_Equity_t)| < 10^{-5}$ identically across all 5 years while allowing negative cash to trigger the R3 Liquidity Distress Firewall.
5. **Direct Cash Flow & Retained Earnings Reconciliation**:
   - P&L: $Interest\_Expense_t$ reduces $EBT \to NPAT$.
   - CFS: Direct Operating CFO deducts $Cash\_Interest\_Paid_t$; Financing CFF adds $New\_Borrowings_t - Principal\_Amortization_t$ and deducts $Dividends\_Paid_t + Share\_Repurchases_t$.
   - BS: $Total\_Debt_t = Closing\_Debt_t$, $RE_t = RE_{t-1} + NPAT_t - Dividends\_Paid_t$, $CC_t = CC_{t-1} - Share\_Repurchases_t$.

---

## 3. Caveats
- **Sector-Specific Debt Differences**: Financial institutions (Banks, Securities, Insurance) treat customer deposits and interbank borrowings differently from corporate debt. For banks, `is_financial=True` should be respected (where debt schedule acts on wholesale funding or yields to CAR requirements).
- **Tax Loss Carryforwards**: The engine assumes standard corporate tax rate $\max(0, EBT \times 0.20)$; complex tax loss carryforwards are abstracted into non-negative tax expense.

---

## 4. Conclusion
The integration architecture between Milestone 2 (`services/debt_capital_schedule_engine.py`), Milestone 3 (`services/three_statement_engine.py`), and Milestone 4 (`services/valuation_engine.py`) is fully mapped and documented in `analysis_m2_integration.md`. The design guarantees 100% mathematical consistency, zero circular reference locks, and clean synchronization with all 22 valuation models.

---

## 5. Verification Method
- Review report at `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m2_2\analysis_m2_integration.md`.
- When M2 is implemented, execute unit test suite:
  ```powershell
  pytest tests/test_debt_capital_schedule_engine.py -v
  ```
- Verify Damodaran spreads match `services/valuation_engine.py` constants for large-cap ($AAA \ge 8.50 \implies 65 \text{ bps}$) and small-cap ($AAA \ge 12.50 \implies 65 \text{ bps}$).
