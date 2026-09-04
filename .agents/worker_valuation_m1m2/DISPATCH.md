# Dispatch for Worker (Milestone 1 & 2: Valuation Engine & Risk Firewalls)

You are Worker: Quantitative Valuation Engine Specialist.
Your working directory is: c:/Users/Admin/Documents/Vibecoding vnstock/.agents/worker_valuation_m1m2
Original request file: c:/Users/Admin/Documents/Vibecoding vnstock/.agents/ORIGINAL_REQUEST.md
Scope document: c:/Users/Admin/Documents/Vibecoding vnstock/PROJECT.md
Detailed specification files:
- `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/explorer_survey_2/analysis.md` (complete mathematical formulas and architecture)
- `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/explorer_survey_3/analysis.md` (risk firewalls and metrics)

## Write Ownership
You EXCLUSIVELY own: `services/valuation_engine.py`.
Do NOT modify other files without coordination.

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Assignment
Implement `services/valuation_engine.py` with full production-grade rigor:
1. **WACC Engine & 5-Factor VN CAPM**:
   - Risk-free rate (5.0%), Market Risk Premium (8.5%).
   - 5 Factors: Market Beta ($\beta_i$), Size ($\text{SMB}$), Value ($\text{HML}$), Momentum ($\text{UMD}$), Amihud Illiquidity ($\text{ILLIQ}$), Profitability ($\text{RMW}$).
   - Synthetic Credit Spread table based on Interest Coverage Ratio ($\text{ICR}$) to calculate Cost of Debt $K_d$.
   - WACC $= (E/V) \times K_e + (D/V) \times K_d \times (1 - t_c)$, with $t_c = 0.20$ default, bounded in $[8.5\%, 18.5\%]$.
2. **Risk Firewalls & Anti-Trap Diagnostics**:
   - 4-Quadrant Altman Z'' + Beneish M-Score risk matrix (`safe_institutional`, `distressed_turnaround`, `forensic_trap`, `toxic_exclusion`).
   - Rhodes-Kropf (RKV) $V/B$ enterprise decomposition (firm misvaluation, industry bubble, long-run growth).
   - Dynamic Margin of Safety scaled by Downside Beta: $\text{MOS}_{\text{dynamic}} = \text{MOS}_{\text{base}} \times \max(0.7, \min(2.0, 1.0 + 0.5 \times (\beta_- - 1.0)))$.
3. **8 Relative Multiples**:
   - Blended P/E (with optional CAPE 3Y/5Y), P/S, P/FCF, P/B (with Rhodes-Kropf filter), P/TBV, Blended EV/EBITDA, P/CF, P/AFFO.
4. **7 Absolute Intrinsic Models**:
   - Extended 2-Stage Value Driver DCF (McKinsey / ROIC), Residual Income Model (RIM / Edwards-Bell-Ohlson), EPV (Greenwald Earnings Power Value), Graham Growth Number ($V = \sqrt{22.5 \times \text{EPS} \times \text{BVPS}}$ or Graham Formula), Rule of 40 / Rule of X, Acquirer's Multiple (EV/EBIT), Owner's Earnings (Buffett).
5. **7 Sector-Specific Models**:
   - rNPV (Pharma/Biotech pipeline), Equity Cash Flow (Banks/Insurance with Basel II CAR constraint), AFFO DCF (REITs), Unbundled SOTP (Telecom NetCo/ServeCo with RAB model), APV (Adjusted Present Value for Industrials), EVA (Economic Value Added for Consumer Staples), DDM (Dividend Discount Model for Utilities).
6. **Stress-Test Scenarios & 2D Sensitivity Grid**:
   - Bear / Base / Bull scenario shifts (growth rate $\pm 3\%$, WACC $\pm 1.5\%$, margin shifts).
   - 5x5 WACC vs Terminal Growth sensitivity matrix.
7. **Adaptive Multi-Algo Weighting Engine**:
   - Inverse Variance Weighting (IVW), SMAPE, MALE, WMAPE, RMSLE rolling prediction error weighting with 1.5x IQR outlier rejection and sector applicability gating.
   - Graceful fallback for new listings (< 4 quarters history).
8. Run pytest tests on your module:
   ```powershell
   pytest tests/ -k valuation
   ```
9. Write `handoff.md` with: Observation, Logic Chain, Caveats, Conclusion, Verification Method.
10. Send completion message to orchestrator.
