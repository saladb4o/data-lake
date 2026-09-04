## 2026-09-02T04:28:25Z
You are teamwork_preview_worker_m1.
Your working directory is: c:\Users\Admin\Documents\Vibecoding vnstock\.agents\worker_m1_1\
Project root is: c:\Users\Admin\Documents\Vibecoding vnstock

MANDATORY FIRST STEP: Read the original user request at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\ORIGINAL_REQUEST.md
Also read the project architecture at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\PROJECT.md
and the Milestone 1 scope at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\m1_working_capital\SCOPE.md

Also read the detailed Explorer reports for Milestone 1:
1. `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m1_1\analysis_m1_math_arch.md`
2. `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m1_2\analysis_m1_integration.md`
3. `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m1_3\analysis_m1_test_spec.md`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Exclusive Write Ownership Files:
- `services/working_capital_engine.py`
- `tests/test_working_capital_engine.py`

Your Implementation Tasks:
1. Implement `services/working_capital_engine.py` with:
   - `WorkingCapitalMetrics`, `WorkingCapitalSchedulePeriod`, `WorkingCapitalForecastResult` (Pydantic models with v1/v2 compatibility).
   - `SECTOR_WC_PRIORS` dictionary covering all VN sectors (`VNCONS`, `VNCOND`, `VNMAT`, `VNIND`, `VNIT`/`VNTECH`, `VNREAL`, `VNENE`, `VNUTI`, `VNHEAL`, `VNFIN`, `VNBNK`, `VNSEC`, `VNINS`, and numeric ICBs `3000`, `5000`, `1700`, `2700`, `9500`, `0500`, `7000`, `8600`, `4500`, `8300`, `8700`, `8500`, `DEFAULT`).
   - `safe_div(num, den, fallback=0.0)` and `clamp(val, min_val, max_val)` robust arithmetic helpers.
   - `WorkingCapitalEngine.calculate_historical_days(rev, cogs, ar, inv, ap, other_ca=0.0, other_cl=0.0, sector='DEFAULT', days_in_period=365)`.
   - `WorkingCapitalEngine.project_working_capital_schedule(base_metrics, revenue_series, cogs_series, other_ca_series=None, other_cl_series=None, sector='DEFAULT', mean_revert_speed=0.0)`.
   - `WorkingCapitalEngine.compute_direct_cash_flow_adjustments(current_period, prior_period, revenue, cogs)`.
   - Exact mathematical precision: $\Delta \text{NWC}_t \equiv \Delta \text{AR}_t + \Delta \text{Inv}_t + \Delta \text{OCA}_t - \Delta \text{AP}_t - \Delta \text{OCL}_t$.
   - Financial sector gating (banks, insurance, securities set $DIO=0$, $NWC=0$ safely).

2. Implement the comprehensive 4-Tier test suite in `tests/test_working_capital_engine.py` covering:
   - Tier 1: Standard calculations, Pydantic contracts, 5Y constant and mean-reverting schedules.
   - Tier 2: Boundary values (zero rev, zero cogs, zero everything, negative AR/AP, gross loss, days clamping, negative CCC retail, missing/dirty inputs, financial sector gating).
   - Tier 3: Accounting invariants (Delta NWC component additivity, CCC identity, Direct Method Cash Flow reconciliation, steady-state zero growth, linear scaling).
   - Tier 4: Empirical VN30 tickers (VNM, FPT, HPG, MWG, MSN, GAS, VCB/TCB/MBB banking suite, full batch pass).

3. Run the test suite:
   `pytest tests/test_working_capital_engine.py tests/test_valuation_engine.py tests/test_valuation_endpoints.py -v`
   Ensure 100% tests pass with 0 failures and 0 regressions.

4. Write your comprehensive handoff report to:
   `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\worker_m1_1\handoff.md`

5. Maintain `progress.md` with timestamp heartbeats in your working directory.
6. Send a message to orchestrator with summary and verification evidence when done.
