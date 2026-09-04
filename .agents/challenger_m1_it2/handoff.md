# Milestone M1 Iteration 2 Adversarial Challenge Report: Empirical Validation & Verdict

**Agent**: `challenger_m1_it2`  
**Role**: `critic`, `specialist` (EMPIRICAL CHALLENGER)  
**Working Directory**: `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/challenger_m1_it2/`  
**Project Root**: `c:/Users/Admin/Documents/Vibecoding vnstock`  
**Target File Under Audit**: `services/fair_value_backtest_service.py`  
**Verdict**: **`APPROVE`**  
**Date**: 2026-08-31  

---

## 1. Observation

Direct empirical stress testing was conducted using a 35-test dedicated adversarial harness (`tests/test_adversarial_m1_it2_empirical.py`), the 79-test stress suite (`tests/test_fair_value_backtest_stress.py`), and the full workspace test suite (465 tests).

All 5 defects previously reported in Milestone M1 Iteration 1 (`.agents/challenger_m1_1/handoff.md`) were independently tested and verified:

### Defect 1: Inverted & Out-of-Range Timeline Years (`start_year > end_year`)
- **Direct Code Inspection**: `services/fair_value_backtest_service.py:540-550, 565, 1006-1010`
  ```python
  eff_start_year = min(start_year, end_year)
  eff_end_year = max(start_year, end_year)
  timeline_quarters = [q for q in QUARTERS_TIMELINE if eff_start_year <= q["year"] <= eff_end_year]
  yearly_trade_stats: Dict[int, List[float]] = defaultdict(list)
  ```
- **Empirical Observation**: Tested 8 inverted and out-of-range configurations (`(2026, 2021)`, `(2025, 2022)`, `(2024, 2021)`, `(2023, 2021)`, `(2026, 2024)`, `(2030, 2020)`, `(1995, 2000)`, `(2050, 2040)`) across all 3 modes (`VALUATION_ONLY`, `SCREENING_ONLY`, `HYBRID_FUNNEL`).
- **Result**: Zero `KeyError: 2021`. All 24 mode-span combinations executed cleanly and returned sorted, contiguous `yearly_returns`. `(2026, 2021)` produced outputs identical to `(2021, 2026)`.

### Defect 2: Cache Key Partitioning by `holding_period_months` and `initial_capital`
- **Direct Code Inspection**: `services/fair_value_backtest_service.py:492-498`
  ```python
  cache_key = (
      f"fv_bt_v7_{mode}_{screening_strategy}_{valuation_model_id}_"
      f"{margin_of_safety_pct}_{exit_premium_pct}_{use_dynamic_beta_mos}_"
      f"{filter_z_score_safe}_{filter_rkv_value_trap}_{exchange}_{top_k}_{rebalance_cadence}_"
      f"{fill_mode}_{survival_filter}_{tsmom_filter}_{forensic_filter}_{holding_period_months}_{initial_capital}_{start_year}_{end_year}_"
      f"{composite_mode}_{omnibus_metric}_{str(custom_symbols)}"
  )
  ```
- **Empirical Observation**: Consecutive backtest runs with `holding_period_months=12` vs `120` returned payloads with `res_12.holding_period_months == 12` and `res_120.holding_period_months == 120`. Similarly, `initial_capital=100M` vs `500M` produced strictly isolated, 5x-scaled initial equity curves without cache pollution.
- **Result**: PASSED with complete cache slot separation and zero stale cross-contamination.

### Defect 3: Take-Profit Triggering with Zero Exit Premium (`exit_premium_pct=0.0`)
- **Direct Code Inspection**: `services/fair_value_backtest_service.py:812`
  ```python
  hit_tp = (f_high >= tp_target_price and tp_target_price >= p_in)
  ```
- **Empirical Observation**: In both `SCREENING_ONLY` and `VALUATION_ONLY` modes with `exit_premium_pct=0.0`, positions where `f_high >= p_in` successfully exited with `exit_reason == "TAKE_PROFIT"`, recording `exit_price == entry_price` and positive holding days.
- **Result**: PASSED. Take-profit triggers reliably at the boundary `0.0%`.

### Defect 4: Dynamic Beta Margin of Safety Scaling with User Baseline
- **Direct Code Inspection**: `services/fair_value_backtest_service.py:741-746`
  ```python
  if use_dynamic_beta_mos:
      dyn_mos = val_res.risk_firewall.dynamic_margin_of_safety
      base_scale = DEFAULT_BASE_MOS if DEFAULT_BASE_MOS <= 1.0 else (DEFAULT_BASE_MOS / 100.0)
      risk_factor = (dyn_mos / base_scale) if dyn_mos <= 1.0 else (dyn_mos / (base_scale * 100.0))
      effective_mos = max(0.0, margin_of_safety_pct * risk_factor)
  else:
      effective_mos = margin_of_safety_pct
  ```
- **Empirical Observation**: When `margin_of_safety_pct=500.0` with `use_dynamic_beta_mos=True`, exactly 0 trades were executed (`res.metrics["total_trades"] == 0`). Progressing `margin_of_safety_pct` across `[5.0, 15.0, 25.0, 40.0, 60.0]` yielded monotonically non-increasing trade counts (`[80, 78, 62, 34, 12]`).
- **Result**: PASSED. User MoS is strictly respected and proportionally modulated by downside beta and distress risk factors.

### Defect 5: Summary Metric `avg_holding_days` Empirical Mean Calculation
- **Direct Code Inspection**: `services/fair_value_backtest_service.py:989`
  ```python
  avg_holding_days=round(float(np.mean([t.holding_days for t in sorted_trades])), 1) if sorted_trades else float(holding_period_months * 30),
  ```
- **Empirical Observation**: Tested across all 3 modes. For runs with closed trades, `res.metrics["avg_holding_days"]` matched `round(np.mean([t.holding_days for t in trades]), 1)` with `abs(reported - empirical) <= 0.1`. When 0 trades occurred (e.g. `margin_of_safety_pct=999.0`), it gracefully fell back to `holding_period_months * 30`.
- **Result**: PASSED.

---

## 2. Logic Chain

1. **Robustness to Inverted Inputs**: By calculating `min(start_year, end_year)` and `max(start_year, end_year)`, the simulation timeline is guaranteed to be chronologically valid. Replacing fixed-key dictionaries with `defaultdict(list)` guarantees that any timeline mismatch cannot crash the service with a `KeyError`.
2. **Deterministic Caching**: All simulation parameters influencing the calculation (`holding_period_months`, `initial_capital`, filters, models, horizons) are now fully represented in `cache_key`.
3. **Boundary Condition Rigor**: Changing the strict inequality `tp_target_price > p_in` to `>= p_in` preserves the mathematical definition of a zero-premium take-profit limit order.
4. **Proportional Risk Modulation**: Normalizing `dynamic_margin_of_safety` by `DEFAULT_BASE_MOS` yields a scale-free `risk_factor`, enabling user baseline MoS to be accurately modulated by market risk rather than being unconditionally overwritten.
5. **Realized Metric Fidelity**: Computing `avg_holding_days` from the empirical trade records reflects true early-exit durations while preserving the nominal fallback when no trades are executed.

---

## 3. Caveats

- In cases where a single trade has identical entry and exit quarter (e.g. intraday or same-quarter rebalance fallback), holding days are defaulted to 90 days if date difference is 0.
- All tests passed cleanly without any modifications required outside `services/fair_value_backtest_service.py`.

---

## 4. Conclusion

**Verdict**: **`APPROVE`**

Milestone M1 Iteration 2 remediations have been empirically verified. All 5 defects are completely resolved. The backtesting engine demonstrates full mathematical soundness, robust caching, clean boundary behavior, and 100% test pass rate across all 465 test cases.

---

## 5. Verification Method

To independently reproduce the empirical validation:

```powershell
# 1. Run Milestone M1 dedicated verification & adversarial suites (187 tests)
pytest tests/test_fair_value_backtest.py tests/test_e2e_fair_value_backtest.py tests/test_fair_value_backtest_stress.py tests/test_challenger_m1_verification.py tests/test_adversarial_m1_it2_empirical.py -v

# 2. Run full workspace regression suite (465 tests)
pytest tests/ -q
```

### Verified Results:
- `tests/test_adversarial_m1_it2_empirical.py`: **35 passed, 0 failures** (19.91s)
- `tests/test_fair_value_backtest_stress.py`: **79 passed, 0 failures** (27.31s)
- Combined M1 test suites (5 test files): **187 passed, 0 failures** (48.06s)
- Entire workspace test suite (26 test files): **465 passed, 0 failures** (106.97s)
