# Handoff Report: Milestone M1 Iteration 2 Remediations

**Agent**: `worker_m1_it2`  
**Role**: `implementer`, `qa`  
**Working Directory**: `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/worker_m1_it2/`  
**Project Root**: `c:/Users/Admin/Documents/Vibecoding vnstock`  
**Target File**: `services/fair_value_backtest_service.py`  
**Date**: 2026-08-31  

---

## 1. Observation

Direct inspection of `services/fair_value_backtest_service.py` and the Challenger 1 audit report (`.agents/challenger_m1_1/handoff.md`) revealed 5 areas requiring remediation:

1. **Cache Key Parameter Omission** (`services/fair_value_backtest_service.py:492-498`):  
   `cache_key` did not include `holding_period_months` and `initial_capital`, leading to cache cross-contamination between backtests differing only by holding horizon or capital size.
2. **Timeline Inversion & Out-of-Bounds KeyError** (`services/fair_value_backtest_service.py:540-558, 865, 896, 1007`):  
   Inverted year spans (e.g., `start_year=2026, end_year=2021`) or out-of-range timeline queries defaulted `timeline_quarters` without updating start/end bounds, causing `KeyError: 2021` on `yearly_trade_stats[curr_year].append(net_ret_pct)`.
3. **Strict Inequality in Take-Profit Boundary** (`services/fair_value_backtest_service.py:805`):  
   `hit_tp = (f_high >= tp_target_price and tp_target_price > p_in)` prevented take-profit execution when `exit_premium_pct=0.0` because `tp_target_price == p_in`.
4. **Dynamic MoS Overriding User MoS** (`services/fair_value_backtest_service.py:741`):  
   `effective_mos` was unconditionally overwritten by `val_res.risk_firewall.dynamic_margin_of_safety`, rendering user-specified `margin_of_safety_pct` inert when `use_dynamic_beta_mos=True`.
5. **Hardcoded Summary Metric `avg_holding_days`** (`services/fair_value_backtest_service.py:989`):  
   `BacktestMetrics.avg_holding_days` was set to `float(holding_period_months * 30)` rather than computing the empirical average across closed trade records.

---

## 2. Logic Chain

1. **Cache Partitioning**: Added `holding_period_months` and `initial_capital` to the formatted cache string prefix `fv_bt_v7_...`. Now, any changes to capital or investment horizon generate distinct cache entries.
2. **Timeline Boundary Hardening**:
   - Sanitized year bounds using `eff_start_year = min(start_year, end_year)` and `eff_end_year = max(start_year, end_year)`.
   - Converted `yearly_trade_stats` to `defaultdict(list)` so recording trade stats never raises `KeyError`.
   - Dynamically derived `matrix_start_year` and `matrix_end_year` from active `timeline_quarters` to ensure `yearly_matrix` and `payload.start_date`/`payload.end_date` remain fully consistent.
3. **Take-Profit Boundary Relaxing**:
   - Changed `tp_target_price > p_in` to `tp_target_price >= p_in`. When `exit_premium_pct=0.0`, `tp_target_price = p_in`, so positions can exit immediately upon price reach without being blocked.
4. **Proportional Downside-Beta MoS Scaling**:
   - Normalized `val_res.risk_firewall.dynamic_margin_of_safety` by `DEFAULT_BASE_MOS` (0.20) to extract the risk factor (`risk_factor = dyn_mos / base_scale`).
   - Scaled user `margin_of_safety_pct` proportionally: `effective_mos = max(0.0, margin_of_safety_pct * risk_factor)`. User-specified MoS is now honored while preserving dynamic downside-beta and distress adjustments.
5. **Realized Metric Computation**:
   - Updated `BacktestMetrics.avg_holding_days` to `round(float(np.mean([t.holding_days for t in sorted_trades])), 1) if sorted_trades else float(holding_period_months * 30)`.

---

## 3. Caveats

- When zero trades are generated (e.g. extreme MoS or empty universe), `avg_holding_days` gracefully falls back to nominal `float(holding_period_months * 30)`.
- No modifications were made outside `services/fair_value_backtest_service.py`, maintaining strict write boundary adherence.

---

## 4. Conclusion

All 5 defects identified in the Challenger 1 audit have been remediated in `services/fair_value_backtest_service.py`. The backtesting engine is robust against inverted timelines, extreme parameters, zero exit premiums, varying holding periods, and dynamic beta scaling.

---

## 5. Verification Method

### Test Commands Executed:

1. **Backtest-Specific Verification & Stress Suite**:
   ```powershell
   pytest tests/test_fair_value_backtest.py tests/test_e2e_fair_value_backtest.py tests/test_fair_value_backtest_stress.py tests/test_challenger_m1_verification.py -v
   ```
   *Result*: **152 passed, 0 failures** in 20.48s.

2. **Full Workspace Regression Test**:
   ```powershell
   pytest tests/ -q
   ```
   *Result*: **430 passed, 0 failures** in 83.75s.

### Invalidation Conditions:
- Any `KeyError` when running inverted year simulations (`start_year=2026, end_year=2021`).
- Cache collisions between simulations with different `holding_period_months` or `initial_capital`.
- Inability of `exit_premium_pct=0.0` to trigger take-profit.
- Invariance of simulation trade count when changing `margin_of_safety_pct` with `use_dynamic_beta_mos=True`.
- Deviation of summary `avg_holding_days` from the arithmetic mean of individual trade `holding_days`.
