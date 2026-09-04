# Codebase & Data Infrastructure Survey Report
**Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem**
**Platform:** `Vibecoding vnstock` (Vietnam Quantitative Valuation & Backtesting Platform)
**Date:** 2026-09-02
**Author:** Codebase & Data Infrastructure Explorer (`explorer_survey_1`)

---

## 1. Executive Summary & Codebase Architecture

The `Vibecoding vnstock` platform is an institutional-grade quantitative valuation, financial modeling, and algorithmic backtesting engine tailored for the Vietnamese equity markets (HOSE, HNX, UPCOM). 

The platform integrates:
- **Comprehensive Local Data Lake:** Point-in-time fundamentals, 10-year quarterly OHLCV price histories, 1,600+ screener stocks, and TCBS/VNDIRECT financial model catalogs.
- **22-Model Quantitative Valuation Matrix (`services/valuation_engine.py`):** 8 Relative Multiples, 7 Absolute Intrinsic Models, 7 Sector-Specific Models, 5-Factor Vietnam CAPM WACC, Damodaran Synthetic Credit Rating tables, and 4-Quadrant Altman Z'' / Beneish M-Score risk firewalls.
- **3-Mode Backtesting Suite (`services/fair_value_backtest_service.py`):** `VALUATION_ONLY`, `SCREENING_ONLY`, and `HYBRID_FUNNEL` modes across multi-cadence rebalancing intervals (quarterly, semi-annual, annual, monthly) and multi-horizon periods (3M to 36M).
- **Modano 3-Way Integrated Financial Modeling Ecosystem:**
  - `services/three_statement_engine.py` (Requirement R1 & R3)
  - `services/working_capital_engine.py` (Requirement R2)
  - `services/debt_capital_schedule_engine.py` (Requirement R4)
  - `services/financial_model_exporter.py` (Requirement R5)
- **FastAPI REST API (`server.py`):** Full API routes for interactive valuation queries, 5-year 3-way forecast payloads, and streaming `.xlsx` financial model downloads.

---

## 2. Data Lake Infrastructure & Schemas

The platform relies on a hybrid local/Google Drive Data Lake (`data/` directory and `GOOGLE_DRIVE_DATA_DIR`) with atomic JSON writes, checksum caching, and Stale-While-Revalidate (SWR) in-memory tiers.

```
data/
├── all_symbols.json             # 5,041 total symbols (1,751 stocks, 1,458 corporate bonds, 1,535 warrants, 20 ETFs, etc.)
├── financial_models.json        # 2,500 accounting line-item codes & definitions across 4 company forms
├── historical_prices.json       # 1,306 symbols, 41 quarters (2016-Q1 to 2026) quarterly OHLCV & return data
├── screener_snapshot.json       # 1,645 symbols, 51 high-resolution fundamental metrics per stock
├── precomputed_valuations.json  # 41,872 valuation records across historical quarters
├── industries.json              # 8,186 company-to-ICB industry sector classifications
└── exports/                     # Generated Modano 3-Way Excel models (*.xlsx)
```

### 2.1 `data/financial_models.json`
- **Total Records:** 2,500 entries.
- **Catalog Structure:** Maps standard Vietnamese accounting codes (VAS / Circular 200 / Circular 334) to financial statement line items.
- **Company Forms (`companyForm`):**
  - `NON_FINANCE` (335 items): Commercial & industrial enterprises.
  - `BANK` (579 items): Commercial banks (Circular 49/2014/TT-NHNN).
  - `SECURITIES` (905 items): Securities brokerages (Circular 334/2016/TT-BTC).
  - `INSURANCE` (650 items): Life & general insurance companies.
  - `ALL_FORMS` (31 items): Universal items (e.g. Dividend Payout, Free Float).
- **Statement Types (`modelTypeName`):**
  - `INCOME` (198 items): P&L line items (Revenue code 21001, COGS code 22100, Pre-tax profit code 23800, etc.).
  - `BALANCESHEET` (581 items): Balance sheet items (Cash code 11100, AR code 11300, Inventory code 11400, Net PPE code 12200, Liabilities code 13000, Equity code 14000).
  - `CASHFLOW` (342 items): Direct/Indirect CFS items (CFO, CFI, CFF line items).
  - `GROWTH` (11 items), `PROFITABILITY` (10 items), `FINHEALTH` (9 items), `FUNDAMENTAL` (91 items), `GOVERNANCE` (3 items), `POSITIONING` (10 items), `EXPLAINATION` (1,167 items).

### 2.2 `data/screener_snapshot.json`
- **Total Symbols:** 1,645 active market tickers.
- **51 Fundamental Fields:**
  - Identifiers: `symbol`, `name`, `exchange`, `sector_code`, `sector_name`, `industry`.
  - Market Data: `price`, `change_pct`, `market_cap`, `size_category`.
  - Multiples: `pe`, `pb`, `ps`, `peg`, `peg_sales`, `dividend_yield`.
  - Earnings & Profitability: `eps`, `eps_3y_cagr`, `roe`, `roa`, `roic`, `gross_margin`, `op_margin`, `net_margin`, `core_pat_ratio`.
  - Growth Trajectory: `rev_1y_growth`, `rev_3y_cagr`, `rev_5y_growth`, `pat_1y_growth`, `pat_3y_cagr`, `pat_5y_growth`, `ebit_expansion`, `rule_of_40`.
  - Solvency & Liquidity: `de_ratio`, `net_de_ratio`, `current_ratio`, `quick_ratio`, `interest_coverage`, `cash_to_assets`, `cfo_to_pat`, `fcf_ttm`.
  - Forensic & Quality: `dilution_spread`, `share_dilution_3y`, `operating_leverage`, `is_cyclical`, `sector_percentile`, `sector_rank`, `sector_total`.

### 2.3 `data/historical_prices.json`
- **Total Symbols:** 1,306 tickers.
- **Historical Horizon:** 41 quarters spanning 2016-Q1 through 2026.
- **Quarterly Bar Schema:** `quarter`, `start_date`, `end_date`, `start_price`, `close_price`, `high`, `low`, `volume`, `return_pct`.

---

## 3. Quantitative Valuation Engine (`services/valuation_engine.py`)

The Valuation Engine implements 22 valuation models tailored for Vietnam equities:

### 3.1 22 Quantitative Valuation Models
| Category | Model Name | Description / Formula |
|---|---|---|
| **Relative (8)** | `blended_pe` | Blended P/E with Shiller Cyclically Adjusted CAPE (3Y/5Y) |
| | `ps_margin_adj` | Margin-Adjusted Price-to-Sales: $P/S_{fair} = Peer\_PS \times \left(\frac{NetMargin_{firm}}{NetMargin_{sector}}\right)$ |
| | `p_fcf` | Price-to-Free-Cash-Flow multiple benchmarked to ICB sector |
| | `pb_rhodes_kropf` | Price-to-Book decomposed via Rhodes-Kropf anti-mispricing filter |
| | `p_tbv` | Price-to-Tangible Book Value (stripping goodwill/intangibles) |
| | `ev_ebitda` | Enterprise Value to EBITDA adjusted for capital structure |
| | `p_cf` | Price-to-Operating Cash Flow |
| | `p_affo` | Price-to-Adjusted Funds from Operations (Real Estate / REITs) |
| **Intrinsic (7)** | `dcf_2stage_mckinsey` | 2-Stage McKinsey Value Driver DCF: $V_0 = \frac{NOPAT \times (1 - g/ROIC)}{WACC - g}$ |
| | `rim_edwards_bell_ohlson`| Residual Income Model (RIM): $BV_0 + \sum_{t=1}^T \frac{RI_t}{(1+K_e)^t} + \text{Terminal RI}$ |
| | `greenwald_epv` | Greenwald Earnings Power Value: $\frac{EBIT \times (1-t) + Depr - CapEx_{maint}}{WACC}$ |
| | `graham_growth` | Benjamin Graham Growth Number & Revised Formula: $\frac{EPS \times (8.5 + 2g) \times 4.4}{Y}$ |
| | `rule_of_40` | Rule of 40 / Rule of X SaaS & Tech Growth Multiplier |
| | `acquirers_multiple_ev_ebit` | Tobias Carlisle Deep Value Acquirer's Multiple: $EV/EBIT$ |
| | `buffett_owners_earnings` | Warren Buffett Owner's Earnings DCF: $NPAT + D\&A - CapEx_{maint} - \Delta NWC$ |
| **Sector-Specific (7)**| `rNPV_pharma` | Risk-Adjusted NPV for Pharmaceutical Pipeline (ICB 4500) |
| | `bank_equity_cash_flow` | Equity Cash Flow & Basel II Capital Adequacy Model (ICB 8300/8500) |
| | `reit_affo_dcf` | Real Estate Developer AFFO DCF & Cap Rate (ICB 8600) |
| | `telecom_unbundled_sotp` | SOTP & Regulated Asset Base (RAB) for Telecom & Infra (ICB 6500/7500) |
| | `industrial_apv` | Adjusted Present Value (APV) with Unlevered Cost of Equity + Tax Shield |
| | `consumer_eva_mva` | Economic Value Added ($EVA = NOPAT - WACC \times Capital$) |
| | `utilities_3stage_ddm` | 3-Stage Dividend Discount Model (H-Model) for Regulated Utilities |

### 3.2 Macro & Capital Cost Engine
- **5-Factor Vietnam CAPM:**
  $$K_e = R_f + \beta_{adj} \times ERP + SMB + HML + UMD + ILLIQ + RMW$$
  - Vietnam 10Y Benchmark Bond Yield $R_f = 5.0\%$.
  - Damodaran Vietnam Equity Risk Premium $ERP = 8.15\%$ (Mature ERP 4.60% + Vietnam CRP 3.55%).
  - Corporate Tax Rate $t = 20.0\%$.
- **Damodaran Synthetic Credit Rating Table:**
  - Converts Interest Coverage Ratio ($ICR = EBIT / \text{Interest}$) into Credit Rating (`AAA` to `D`) and Credit Spread (65 bps to 1,250 bps) for both Large-Cap (> 5,000B VND) and Small-Cap ($\le$ 5,000B VND).
  - Pre-Tax Cost of Debt $K_{d,pre} = R_f + \text{Spread}$; After-Tax $K_{d,post} = K_{d,pre} \times (1 - t)$.
  - Bounded WACC: $\text{clamp}(w_e K_e + w_d K_d (1 - t), 8.5\%, 18.5\%)$.

### 3.3 Risk Firewalls & Adaptive Error Weighting
- **Emerging Market 4-Factor Altman Z''-Score:**
  $$Z'' = 6.56 X_1 + 3.26 X_2 + 6.72 X_3 + 1.05 X_4$$
  ($Z'' \ge 2.60$: Safe, $1.10 \le Z'' < 2.60$: Grey, $Z'' < 1.10$: Distress/Exclusion).
- **Beneish 8-Variable M-Score:** Threshold $M < -1.78$ Safe, $M \ge -1.78$ Earnings Manipulation Flag.
- **Rhodes-Kropf (RKV) Decomposition:** Decomposes valuation into Firm Misvaluation ($V/B$), Sector Misvaluation ($B/M$), and Long-Run Growth to filter value traps.
- **Adaptive Error Weighting:** Inverse Variance Weighting (IVW), SMAPE, MALE, WMAPE, RMSLE with 1.5x IQR outlier rejection.

---

## 4. Backtesting Engine (`services/fair_value_backtest_service.py`)

The backtesting service executes point-in-time quantitative backtests without lookahead bias:
- **Operational Modes:**
  1. `VALUATION_ONLY`: Long positions taken when $P_t \le FV_t \times (1 - MoS_t)$.
  2. `SCREENING_ONLY`: Long positions taken based on 32 Factor & Guru screener presets (e.g. Peter Lynch GARP, Buffett Moat, Piotroski F-Score).
  3. `HYBRID_FUNNEL`: 2-Stage selection (Stage 1 Factor Screener $\to$ Stage 2 Dynamic MoS Valuation Gating).
- **Rebalancing Cadences:** Quarterly (1Q), Semi-Annual (2Q), Annual (4Q), and Monthly.
- **Institutional Friction:** 0.35% round-trip friction (0.15% Commission + 0.10% Tax + 0.10% Slippage) deducted from all realized trade returns.
- **Performance Analytics:** CAGR, Sharpe Ratio, Sortino Ratio, Calmar Ratio, Max Drawdown, Jensen's Alpha, Beta against VN-Index, Win Rate, and Tournament Matrix ranking 23 valuation models.

---

## 5. Modano 3-Way Integrated Financial Modeling Ecosystem

The Modano upgrade is implemented across four core service modules:

```
                                  +---------------------------------------+
                                  |     screener_snapshot.json / Lake     |
                                  +---------------------------------------+
                                                      |
                                                      v
+-------------------------------+         +---------------------------------------+
|  working_capital_engine.py    | ------> |      three_statement_engine.py        | <-------+
|  (DSO, DIO, DPO, CCC, NWC)    |         | (5Y Forecast, Direct CFS, BS Closure) |         |
+-------------------------------+         +---------------------------------------+         |
                                                      |                                     |
                                                      v                                     |
+-------------------------------+         +---------------------------------------+         |
| debt_capital_schedule_engine  | ------> |       financial_model_exporter        |         |
| (Damodaran Kd, Amort, Div)    |         |   (7-Tab Dynamic openpyxl Workbooks)  |         |
+-------------------------------+         +---------------------------------------+         |
                                                      |                                     |
                                                      v                                     |
                                          +---------------------------------------+         |
                                          |        server.py REST Endpoints       | --------+
                                          | (/3-way-forecast, /export-excel)      |
                                          +---------------------------------------+
```

### 5.1 Dynamic 3-Way Statement Forecasting Engine (`services/three_statement_engine.py`)
- **5-Year Forecasting Horizon:** Projects Income Statement, Balance Sheet, and Direct Method Cash Flow Statement for $t \in [1, 5]$.
- **Primary Statement Link 1 ($NPAT \to \text{Retained Earnings}$):**
  $$\text{Retained Earnings}_t = \text{Retained Earnings}_{t-1} + NPAT_t - \text{Dividends Paid}_t$$
- **Primary Statement Link 2 ($\Delta \text{Cash} \to \text{Ending Cash}$):**
  $$\text{Ending Cash}_t = \text{Beginning Cash}_t + Net\_CFO_t + Net\_CFI_t + Net\_CFF_t$$
- **Direct Method Cash Flow Invariant:**
  $$\text{Gross CFO}_t = \text{Revenue}_t - \Delta AR_t - (\text{COGS}_t + \Delta Inv_t - \Delta AP_t) = \text{Gross Profit}_t - \Delta \text{Trade NWC}_t$$
  $$Net\_CFO_t = \text{Gross CFO}_t - \text{SGA}_t - \text{Interest Paid}_t + \text{Interest Received}_t - \text{Tax Paid}_t$$
- **Strict Mathematical Balance Sheet Closure Identity:**
  $$|\text{Total Assets}_t - (\text{Total Liabilities}_t + \text{Total Equity}_t)| < 10^{-5} \quad \forall t \in [1, 5]$$
  Achieved by exact integration where $\Delta \text{Assets} \equiv \Delta (\text{Liabilities} + \text{Equity})$ through the cash conservation link.

### 5.2 Working Capital Days & NWC Analyzer (`services/working_capital_engine.py`)
- **Activity Ratios:**
  - Days Sales Outstanding: $DSO = \frac{AR}{\text{Revenue}} \times 365$
  - Days Inventory Outstanding: $DIO = \frac{\text{Inventory}}{COGS} \times 365$
  - Days Payables Outstanding: $DPO = \frac{AP}{COGS} \times 365$
  - Cash Conversion Cycle: $CCC = DSO + DIO - DPO$
- **Balance Sheet NWC Aggregates:**
  - Operating Working Capital $OWC = AR + \text{Inventory} - AP$
  - Net Working Capital $NWC = (AR + \text{Inventory} + OCA) - (AP + OCL)$
  - $\Delta NWC$ Invariant: $\Delta NWC_t = \Delta AR_t + \Delta Inv_t + \Delta OCA_t - \Delta AP_t - \Delta OCL_t$
- **Sector Prior Fallbacks & Gating:**
  - Negative CCC retail models (e.g. MWG) fully supported.
  - Safe financial sector isolation for Banking (ICB 8300), Securities (ICB 8700), Insurance (ICB 8500) where $DIO=0$ and $NWC=0$.
  - Clamping guards: Days bounded in $[0, 1095]$ to prevent micro-revenue distortion.

### 5.3 Liquidity Distress Firewall & Negative Cash Risk Alert (Requirement R3)
- **Detection:** Evaluates $\text{Ending Cash}_t < 0$ across all 5 forecast years.
- **Diagnostics:**
  - Emits `LiquidityDistressCheck` with `is_distressed = True`, `distress_years`, `min_projected_cash`, `cumulative_cash_shortfall`, and `required_liquidity_injection`.
- **Risk Adjustments:**
  - Computes `mos_risk_penalty` (+5% to +15% addition to Margin of Safety).
  - Computes `dilution_haircut` (equity value reduction proportional to shortfall vs market cap).

### 5.4 Capital Allocation & Debt Schedule Engine (`services/debt_capital_schedule_engine.py`)
- **Debt Amortization Roll-Forward:**
  - Opening Debt: $\text{Debt}_{open, 1} = \text{Base Debt}$, $\text{Debt}_{open, t} = \text{Debt}_{close, t-1}$.
  - Principal Amortization: $\text{Principal Amort}_t = \min(\text{Debt}_{open, t}, \text{Debt}_{open, t} \times r_{amort})$.
  - New Borrowings: $\text{New Borrowings}_t = \max(0, CapEx_t \times \delta_{debt})$.
  - Closing Debt: $\text{Debt}_{close, t} = \text{Debt}_{open, t} + \text{New Borrowings}_t - \text{Principal Amort}_t$.
  - Midpoint Average Debt: $\text{Debt}_{avg, t} = (\text{Debt}_{open, t} + \text{Debt}_{close, t}) / 2$.
- **Fixed-Point Convergence Algorithm:**
  - Resolves circularity between Interest Expense, Average Debt, and Damodaran ICR rating table in $\le 5$ iterations with $|Kd_{new} - Kd_{old}| < 10^{-5}$.
- **Solvency-Guarded Dividend Waterfall:**
  - If $NPAT_t \le 0 \implies \text{Dividends}_t = 0.0$.
  - Debt Covenant Firewall: If $ICR_t < 1.20 \implies$ 100% Dividend Freeze (`is_covenant_breached = True`).
  - Solvent Regime: $\text{Dividends Paid}_t = \min(NPAT_t, NPAT_t \times \text{Payout Ratio})$.

### 5.5 Modano-Compliant Interactive Excel Model Exporter (`services/financial_model_exporter.py`)
- **Automated Openpyxl Engine:** Generates complete 7-Tab Microsoft Excel workbooks (`.xlsx`) with live formulas and zero syntax errors:
  - **Tab 1: Cover & Dashboard:** Executive valuation summary, solvency KPIs, Altman Z'', Beneish M-Score, and dynamic Balance Sheet Health indicator.
  - **Tab 2: Income Statement:** 5-Year P&L with dynamic formulas (`SUM`, differences, margin ratios).
  - **Tab 3: Balance Sheet:** 5-Year Balance Sheet with live dynamic `=SUM(...)` formulas, Net Assets calculation, and `=IF(ABS(Net_Assets - Equity) < 0.01, "BALANCED", "UNBALANCED")` integrity checks.
  - **Tab 4: Cash Flow Statement:** Direct Method CFS linked dynamically to P&L, Working Capital, and Debt schedules, reconciling ending cash to Balance Sheet Cash.
  - **Tab 5: Working Capital Schedule:** Live DSO, DIO, DPO, CCC formulas and $\Delta NWC$ roll-forward.
  - **Tab 6: Debt & Capital Schedule:** Amortization roll-forward formulas, Damodaran rating lookups, Interest Expense, and Dividend payout waterfall.
  - **Tab 7: Valuation & Sensitivity:** 2-Stage DCF, DDM, FCFE models and live 5x5 WACC vs $g$ 2D sensitivity matrix.
- **Corporate Styling Standards:**
  - Header Fill: Navy Blue (`#1F4E79`), Header Text: White Bold (`#FFFFFF`).
  - Section Accent: Ice Lavender (`#D9E1F2`), Text: Navy (`#1F4E79`).
  - Balanced Indicator Fill: Soft Green (`#E2EFDA`), Text: Green (`#375623`).
  - Standard Number Formats: Billion VND `#,##0.0;(#,##0.0);"-"`, Percent `0.0%`, Multiples `0.00"x"`.
  - Freeze panes applied to preserve row headers and period columns.

---

## 6. Backend Integration & REST API Routes (`server.py`)

The FastAPI application in `server.py` exposes endpoints connecting the valuation models, backtesting engine, 3-way forecasting, and Excel exports:

| Endpoint | Method | Description | Key Parameters |
|---|---|---|---|
| `/api/valuation/comprehensive/{symbol}` | `GET` | 22-model valuation matrix, WACC, risk firewalls, sensitivity | `symbol`, `mode` (blended/omnibus), `metric` (smape/ivw) |
| `/api/valuation/matrix/{symbol}` | `GET` | Alias for comprehensive valuation | `symbol`, `mode`, `metric` |
| `/api/valuation/matrix` | `GET` | Query-param endpoint for valuation matrix | `symbol`, `mode`, `metric` |
| `/api/valuation/3-way-forecast/{symbol}` | `GET` | 5-Year Dynamic 3-Way Financial Statement Forecast JSON | `symbol`, `start_year` (default 2026), `tax_rate` (default 0.20) |
| `/api/valuation/export-excel/{symbol}` | `GET` | Generates & streams 7-Tab `.xlsx` Modano financial model | `symbol`, `scale_unit` (billion/raw), `start_year`, `tax_rate` |
| `/api/backtest/fair_value/presets` | `GET` | Available presets, modes, and strategies catalog | None |
| `/api/backtest/fair_value/run` | `POST` | Executes point-in-time quantitative backtest simulation | `mode`, `strategy_id`, `valuation_model_id`, `exchange`, etc. |

---

## 7. Test Framework & Verification Results

The test infrastructure under `tests/` covers unit, invariant, boundary, adversarial, combinatorial, and E2E API scenarios.

### 7.1 Test Suites Overview
- `tests/test_three_statement_engine.py` (392 lines): 6-tier test suite verifying 5-year forecast generation, exact balance sheet closure across all 30 VN30 tickers, direct method CFS conservation, liquidity distress firewall, and Pydantic data schemas.
- `tests/test_working_capital_engine.py` (680 lines): Working capital activity ratios (DSO, DIO, DPO, CCC), $\Delta NWC$ roll-forward, sector prior resolution, negative CCC retail models, and banking/securities isolation.
- `tests/test_working_capital_adversarial.py` (773 lines): Stress tests with hyper-growth (500% CAGR), contraction crashes (-90%), Monte Carlo 1,000-run invariant sweeps, and string fuzzing.
- `tests/test_debt_capital_schedule_engine.py` (794 lines): Debt amortization roll-forwards, Damodaran credit spread tables, circularity solver, and dividend waterfall covenant firewalls.
- `tests/test_financial_model_exporter.py` (272 lines): Openpyxl workbook generation, 7-tab architecture verification, live formula syntax validation, and VN30 export sweeps.
- `tests/test_valuation_engine.py` (420 lines): 22-model mathematical integrity, WACC calculation, Damodaran ratings, Altman Z'', Beneish M-Score, and adaptive weighting.
- `tests/test_fair_value_backtest.py` (480 lines): 3-mode backtester, multi-cadence rebalancing, friction deduction, tournament matrix leaderboard, and lookahead bias prevention.
- `tests/test_valuation_endpoints.py` (65 lines): REST API contract validation for `/api/valuation/comprehensive/{symbol}`, `/api/backtest/fair_value/presets`, and `/api/backtest/fair_value/run`.

### 7.2 Verification Execution Summary
All primary test suites execute cleanly with **0 failures**:

1. **3-Way Modeling & Valuation Suite:**
   - Command: `pytest tests/test_three_statement_engine.py tests/test_working_capital_engine.py tests/test_debt_capital_schedule_engine.py tests/test_financial_model_exporter.py -v`
   - **Result:** **190 PASSED, 0 FAILED** (12.88s).
   - 100% of VN30 constituents produced balanced balance sheets ($|\text{Total Assets} - (\text{Total Liabilities} + \text{Total Equity})| < 10^{-5}$).

2. **Valuation Matrix, Risk Firewalls, Backtest & Endpoints Suite:**
   - Command: `pytest tests/test_working_capital_adversarial.py tests/test_valuation_engine.py tests/test_valuation_endpoints.py tests/test_fair_value_backtest.py -v`
   - **Result:** **57 PASSED, 0 FAILED** (33.32s).

---

## 8. Integration Points & Implementation Blueprint

For any further extension or downstream agent workflows, the following integration contracts are established:

1. **3-Way Forecasting to Valuation Models:**
   - `services/three_statement_engine.py` provides `ThreeStatementForecastResult` containing `cash_flow.fcf` (Free Cash Flow to Firm), `cash_flow.fcfe` (Free Cash Flow to Equity), and `income_statement.npat` for dynamic intrinsic valuation models (DCF, DDM, Buffett Owner's Earnings).
2. **Liquidity Distress to Risk Firewalls:**
   - `ThreeStatementForecastResult.liquidity_check` directly feeds `mos_risk_penalty` into `ValuationEngine` and `fair_value_backtest_service.py` to penalize companies forecasting negative cash balances.
3. **Working Capital to Operating Cash Receipts/Payments:**
   - `services/working_capital_engine.py` provides schedule projections that feed directly into `ThreeStatementEngine._build_cash_flow_forecast`.
4. **Debt Amortization to P&L Interest & Balance Sheet Debt:**
   - `services/debt_capital_schedule_engine.py` supplies projected interest expense to the P&L and closing debt balances to the Balance Sheet.
5. **Excel Exporter to FastAPI Server:**
   - `services/financial_model_exporter.py` outputs binary workbooks formatted for streaming via FastAPI's `FileResponse` at `/api/valuation/export-excel/{symbol}`.
