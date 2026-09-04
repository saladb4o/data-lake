# Scope: Milestone 1 — Working Capital Days & NWC Analyzer (R2)

## Architecture & Responsibilities
Milestone 1 implements the complete Working Capital Days & Net Working Capital (NWC) analyzer engine in `services/working_capital_engine.py` and unit tests in `tests/test_working_capital_engine.py`.

## Key Capabilities
1. Compute historical Debtor Days (DSO), Inventory Days (DIO), Creditor Days (DPO), and Cash Conversion Cycle (CCC).
2. Compute historical Net Working Capital (NWC = AR + Inv + Other CA - AP - Other CL).
3. 5-Year Working Capital Schedule projection based on projected revenue and COGS, maintaining efficiency day targets or mean-reverting towards sector benchmarks.
4. NWC Delta computation ($\Delta NWC_t = NWC_t - NWC_{t-1}$) and Direct Method cash adjustments ($\Delta AR_t, \Delta Inv_t, \Delta AP_t$).
5. Strict zero-division and missing data protocol (`safe_div`, `clamp`, sector prior fallbacks) avoiding any `#DIV/0!`, `NaN`, or `None` errors.

## Code Layout
- `services/working_capital_engine.py` (Worker write ownership)
- `tests/test_working_capital_engine.py` (Worker / Reviewer / Challenger test verification)

## Acceptance Criteria
- 100% of VN30 constituents compute DSO, DIO, DPO, CCC accurately without exceptions.
- Missing or zero revenue/cogs gracefully falls back to sector priors without crashing.
- Working capital projections match direct method operating cash adjustments.
- Pytest suite `tests/test_working_capital_engine.py` passes with 0 failures.
