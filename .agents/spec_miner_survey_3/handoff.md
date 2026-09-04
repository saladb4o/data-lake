# 5-Component Handoff Report — Excel & API Specification Survey

**Agent:** `spec_miner_survey_3`  
**Task:** Specification Mining for Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem (Requirements R3, R5, and Acceptance Criteria)  
**Date:** 2026-09-02  
**Handoff Type:** Hard (Task Complete)

---

## 1. Observation

1. **`ORIGINAL_REQUEST.md` (Lines 18-26, 30-41):**
   - R3 requires detection of projected cash deficits ($\text{Cash}_t < 0$), integration into `services/valuation_engine.py` risk firewalls, and backtesting screening filters in `services/fair_value_backtest_service.py` with dilution/distress scoring penalties.
   - R5 requires an automated openpyxl Excel exporter (`services/financial_model_exporter.py`) with dynamic live formulas (`SUM`, `IF`, cross-sheet links, outlines, balance checks) and FastAPI REST endpoints in `server.py` (`/api/valuation/3-way-forecast/{symbol}` and `/api/valuation/export-excel/{symbol}`).
   - Acceptance criteria require 100% VN30 balance sheet closure ($|\text{Net Assets} - \text{Total Equity}| < 10^{-5}$), Direct Method CFS reconciliation, and passing pytest test suites (`tests/test_three_statement_engine.py`, `tests/test_working_capital_engine.py`, `tests/test_financial_model_exporter.py`).

2. **`services/three_statement_engine.py` (Lines 282-308, 915-950):**
   - `LiquidityDistressCheck` Pydantic model contains: `is_distressed: bool`, `has_negative_cash: bool`, `distressed_years: List[int]`, `min_cash_balance: float`, `max_cash_shortfall: float`, `dilution_risk_pct: float`, `mos_penalty_pct: float`, `summary_assessment: str` (`"HEALTHY"`, `"TIGHT"`, or `"DISTRESSED"`), `diagnostic_messages: List[str]`.
   - Penalty calculation in lines 921-930:
     - When `has_neg_cash` is True: `shortfall_ratio = safe_div(max_shortfall, market_cap, 0.10)`, `dilution_penalty = clamp(0.05 + shortfall_ratio * 0.50, 0.05, 0.25)`, `mos_penalty = clamp(0.05 + shortfall_ratio * 0.30, 0.05, 0.15)`.
     - When $0 \le \min(\text{Cash}) < 0.03 \times \text{base\_rev}$: `assessment = "TIGHT"`, `dilution_penalty = 0.02`, `mos_penalty = 0.03`.
     - Healthy: `dilution_penalty = 0.0`, `mos_penalty = 0.0`.

3. **`services/valuation_engine.py` (Lines 686-716, 802-846, 2380-2465):**
   - `calculate_dynamic_mos(...)` adds `liquidity_distress_penalty` to base MOS:
     `dynamic_mos = clamp(base_mos * beta_scale + risk_penalties + liquidity_distress_penalty, 0.10, 0.60)`.
   - Fundamental data with `"liquidity_distress"` extracts `mos_penalty_pct` and adjusts required upside hurdle.

4. **`services/financial_model_exporter.py` (Lines 108-170, 175-902):**
   - Generates a 7-tab openpyxl workbook: `Summary & Dashboard`, `Income Statement`, `Balance Sheet`, `Cash Flow Statement`, `Working Capital Schedule`, `Debt & Capital Schedule`, `Valuation & Sensitivity`.
   - Injects live dynamic formulas with column substitution: `=C5-C7`, `=SUM(C5:C8)`, `='Cash Flow Statement'!C26`, `='Income Statement'!C5 - 'Working Capital Schedule'!C16`, `=IF(ABS(C26)<1, "BALANCED", "UNBALANCED")`, and 5x5 sensitivity matrix formulas `=($H$5*(1+{col_let}${row}))/($A{cur_r}-{col_let}${row})`.
   - Enforces Modano corporate styling (`COLOR_NAVY_HEADER = "1F4E79"`, `BOX_BORDER`, `TOTAL_BORDER`, number format `#,##0.0;(#,##0.0);"-"`, column auto-fit padding).

5. **`server.py` (Lines 1285-1341):**
   - `GET /api/valuation/3-way-forecast/{symbol}` returns JSON representation of 5-year integrated statements and diagnostics.
   - `GET /api/valuation/export-excel/{symbol}` creates/serves the `.xlsx` workbook via `FileResponse` with `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and `filename={sym}_3Way_Financial_Model.xlsx`.

6. **`tests/test_financial_model_exporter.py` & `tests/test_three_statement_engine.py`:**
   - Test suites validate 5 tiers for Excel export and 6 tiers for 3-statement forecasting including 100% VN30 balance closure, Direct Method CFO identities, and Liquidity Distress triggers.

---

## 2. Logic Chain

1. Starting from `ORIGINAL_REQUEST.md` R3 and R5, we identified the core modeling components required for liquidity risk firewalling and interactive spreadsheet generation.
2. We inspected `services/three_statement_engine.py` and traced how projected ending cash values across $t \in [1..5]$ are evaluated. If $\text{Cash}_t < 0$, `LiquidityDistressCheck` computes the maximum cash shortfall and calculates a proportional dilution penalty (5%–25%) and Margin of Safety penalty (5%–15%).
3. We traced the downstream consumption of `LiquidityDistressCheck` into `services/valuation_engine.py`. The valuation engine incorporates `liquidity_distress_penalty` into `calculate_dynamic_mos(...)`, increasing the required discount rate before issuing buy recommendations, and scales the composite fair value for equity dilution.
4. We evaluated `services/fair_value_backtest_service.py` to verify how `use_dynamic_beta_mos` scales the effective MOS hurdle during quantitative backtesting simulations, ensuring distressed tickers must trade at a much deeper discount to trigger an entry signal.
5. We verified `services/financial_model_exporter.py` and confirmed that all 7 tabs are constructed using openpyxl with native Excel formulas and cross-sheet references wrapped in single quotes, preventing formula parsing errors (`#NAME?`, `#REF!`, `#VALUE!`).
6. We confirmed that `server.py` exposes both JSON forecast endpoints and streaming `.xlsx` download endpoints adhering to standard HTTP and MIME conventions.
7. We verified the complete testing strategy in `tests/test_financial_model_exporter.py` and `tests/test_three_statement_engine.py`, which validates mathematical invariants, VN30 constituent closure, and formula integrity.

---

## 3. Caveats

- **No caveats.** The entire specification for Requirements R3, R5, REST APIs, and Acceptance Criteria is completely analyzed and documented in `survey_report.md`.

---

## 4. Conclusion

The specification survey for Requirements R3, R5, and the associated acceptance criteria is complete and verified. All mathematical relationships, Pydantic contracts, openpyxl styling/formula definitions, FastAPI routing contracts, and automated pytest suites have been thoroughly mined and documented in `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_3\survey_report.md`.

---

## 5. Verification Method

To independently verify the findings:
1. Inspect the survey report at `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_3\survey_report.md`.
2. Inspect `services/three_statement_engine.py` (L282-308, L915-950) for `LiquidityDistressCheck` and penalty calculations.
3. Inspect `services/valuation_engine.py` (L686-716, L802-846) for `calculate_dynamic_mos` and risk firewall integration.
4. Inspect `services/financial_model_exporter.py` (L108-902) for the 7-tab openpyxl workbook generator, formulas, and formatting.
5. Inspect `server.py` (L1285-1341) for `/api/valuation/3-way-forecast/{symbol}` and `/api/valuation/export-excel/{symbol}`.
6. Run the pytest test suites:
   ```powershell
   pytest tests/test_three_statement_engine.py tests/test_financial_model_exporter.py tests/test_working_capital_engine.py -v
   ```
