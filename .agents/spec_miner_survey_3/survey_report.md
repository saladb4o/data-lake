# Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem: Excel & API Specification Survey Report

**Document Version:** 1.0.0  
**Author:** Excel & API Specification Miner (`spec_miner_survey_3`)  
**Date:** 2026-09-02  
**Scope:** Analysis of Requirements R3 (Liquidity Distress Firewall & Risk Alerts), R5 (Modano-Compliant Interactive Excel Model Exporter & FastAPI REST Endpoints), and Acceptance / Test Criteria.

---

## Executive Summary

The Modano 3-Way Financial Modeling upgrade establishes an institutional-grade, fully integrated financial forecasting, valuation, and reporting ecosystem tailored to the Vietnamese equity market (HOSE, HNX, UPCOM). 

This report provides the authoritative specification survey for:
1. **Requirement R3 (Liquidity Distress Firewall & Negative Cash Risk Alert):** Mathematical criteria for projected cash deficits ($\text{Cash}_t < 0$), dilution risk penalties, dynamic Margin of Safety (MOS) scaling in `services/valuation_engine.py`, and integration into the 3-mode quantitative backtest filter in `services/fair_value_backtest_service.py`.
2. **Requirement R5 (Modano-Compliant Interactive Excel Exporter & FastAPI Endpoints):** Complete 7-tab openpyxl spreadsheet architecture, dynamic live Excel formulas (`SUM`, `IF`, cross-sheet links, 2D sensitivity matrices, balance checks), Modano corporate visual formatting, column auto-fit, zero formula syntax errors, and FastAPI routes in `server.py` (`GET /api/valuation/3-way-forecast/{symbol}` and `GET /api/valuation/export-excel/{symbol}`).
3. **Acceptance & Test Validation Criteria:** Mathematical identities, VN30 constituent closure guarantees ($|\text{Net Assets} - \text{Total Equity}| < 10^{-5}$), Direct Method CFO reconciliation, and automated pytest validation suites.

---

## 1. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | R3: Risk Firewall | Negative Cash Detection | Detects projected cash deficits ($\text{Cash}_t < 0$) in any forecast period $t \in [1..5]$. | 5-year balance sheet ending cash series `bs_cash: List[float]` | `is_distressed: bool`, `has_negative_cash: bool`, `distressed_years: List[int]` | Emits empty list and `False` if cash remains non-negative. | `services/three_statement_engine.py` (L915-950) |
| 2 | R3: Risk Firewall | Cash Shortfall & Dilution Penalty Calculation | Computes maximum cash deficit and scales equity dilution penalty (5% to 25%) and Margin of Safety add-on (5% to 15%). | `min_cash_balance: float`, `market_cap: float` | `max_cash_shortfall: float`, `dilution_risk_pct: float`, `mos_penalty_pct: float` | Clamped to safe range $[0.05, 0.25]$ for dilution and $[0.05, 0.15]$ for MoS; safe division prevents zero division. | `services/three_statement_engine.py` (L921-930) |
| 3 | R3: Risk Firewall | Liquidity Assessment Classification | Classifies company liquidity health into `HEALTHY`, `TIGHT`, or `DISTRESSED`. | `min_cash_balance`, `base_rev` (3% buffer benchmark) | `summary_assessment: str`, `diagnostic_messages: List[str]` | Fallback to `HEALTHY` if revenue or cash data missing. | `services/three_statement_engine.py` (L925-941) |
| 4 | R3: Valuation Integration | Dynamic Margin of Safety Scaling | Scales base MOS by Downside Beta ($\beta_-$) and injects add-on penalties from Liquidity Distress and Altman/Beneish traps. | `base_mos: float`, `downside_beta: float`, `altman_zone: str`, `liquidity_distress_penalty: float` | `dynamic_margin_of_safety: float` (bounded in $[0.10, 0.60]$) | Out-of-bounds penalties are clamped between 10% and 60%. | `services/valuation_engine.py` (L686-716) |
| 5 | R3: Valuation Integration | Intrinsic Value Dilution Haircut | Adjusts composite fair value per share for projected capital raises / emergency dilution. | `composite_fair_value: float`, `dilution_risk_pct: float` | `adjusted_fair_value = composite_fair_value * (1.0 - dilution_risk_pct)` | If fair value $\le 0$, value remains 0. | `services/valuation_engine.py` (L2380-2465) |
| 6 | R3: Backtest Integration | Quantitative Backtest Distress Gating | In 3-Mode Backtest engine, adjusts effective MoS threshold by `dyn_mos / base_scale` and filters toxic bankruptcies. | `use_dynamic_beta_mos: bool`, `filter_z_score_safe: bool`, `dyn_mos: float` | `effective_mos: float`, trade entry signal `should_buy: bool` | Skips ticker entry if discount $< \text{effective\_mos}$ or marked as toxic exclusion. | `services/fair_value_backtest_service.py` (L755-797) |
| 7 | R5: Excel Exporter | 7-Tab Modano Workbook Generator | Creates 7 structured worksheets: Summary Dashboard, Income Statement, Balance Sheet, Cash Flow Statement, Working Capital Schedule, Debt Schedule, Valuation & Sensitivity. | `forecast_result: ThreeStatementForecastResult`, `output_path: str`, `scale_unit: str` | Saved `.xlsx` workbook file path | Creates parent export directory if missing; validates data before serialization. | `services/financial_model_exporter.py` (L108-170) |
| 8 | R5: Excel Exporter | Live Dynamic P&L Formulas | Injects Excel native formulas for Gross Profit (`=C5-C7`), EBITDA (`=C8-C10`), EBIT (`=C11-C12`), EBT (`=C13-C15+C16`), Tax (`=MAX(0, C17*0.20)`), NPAT (`=C17-C18`), and Margins. | Row references and column letters | Excel formula strings | Dynamic column letter replacement (`replace("C", col_letter)`) ensures zero `#NAME?` or `#REF!` errors. | `services/financial_model_exporter.py` (L353-393) |
| 9 | R5: Excel Exporter | Balance Sheet Closure & Audit Checks | Implements live formulas for Total Assets (`=C9+C12`), Total Equity (`=C22+C23`), Balance Difference (`=C13-C25`), and Audit Status (`=IF(ABS(C26)<1, "BALANCED", "UNBALANCED")`). | Asset and Liability row cell links | Dynamic balance verification cells | Styled with soft green fill (`E2EFDA`) if balanced, soft red (`FCE4D6`) if unbalanced. | `services/financial_model_exporter.py` (L428-487) |
| 10 | R5: Excel Exporter | Direct Method CFS Reconciliation Links | Connects operating cash flows to P&L and Working Capital tabs (`='Income Statement'!C5 - 'Working Capital Schedule'!C16`), ending cash roll-forward (`=C25+C26`). | Cross-sheet formula references | Reconciled ending cash and FCFF/FCFE rows | Enforces single quotes around sheet names with spaces to prevent Excel parser syntax errors. | `services/financial_model_exporter.py` (L523-587) |
| 11 | R5: Excel Exporter | Working Capital & CCC Formulas | Injects Cash Conversion Cycle formula (`=C6+C7-C8`), balances (`='Income Statement'!C5 * C6 / 365`), and Net Working Capital (`=(C11+C12+C14)-(C13+C15)`). | Days ratios and revenue/COGS links | Dynamic NWC and Delta NWC rows | Non-trade items default to historical safe ratios. | `services/financial_model_exporter.py` (L622-676) |
| 12 | R5: Excel Exporter | Debt Schedule & Damodaran Kd Formulas | Injects Closing Debt (`=C6+C7-C8`), ICR (`='Income Statement'!C13 / 'Income Statement'!C15`), After-Tax Kd (`=C15*(1-0.20)`), and Equity Roll-Forward. | Debt roll-forward and interest coverage metrics | Debt amortization and ending retained earnings | Zero interest falls back to high ICR / safe rating AAA. | `services/financial_model_exporter.py` (L711-768) |
| 13 | R5: Excel Exporter | 2D Valuation Sensitivity Matrix (5x5) | Injects dynamic 5x5 WACC (9%-13%) vs Terminal Growth $g$ (2.5%-4.5%) matrix referencing base FCFF numerator (`=($H$5*(1+col$row))/($A_row-col$row)`). | WACC array, Growth array, base FCFF cell | 25-cell interactive valuation matrix | Negative denominator ($WACC \le g$) caught by formula bounding. | `services/financial_model_exporter.py` (L784-888) |
| 14 | R5: Excel Exporter | Corporate Visual Styling & Layout | Applies Modano corporate styling: Navy Blue headers (`1F4E79`), white bold text, double-line accounting borders, zebra striping, and auto-fit column widths. | Openpyxl styles, fonts, borders, fills | Formatted professional workbook | Safe padding prevents `###` display truncation. | `services/financial_model_exporter.py` (L50-103, 894-902) |
| 15 | FastAPI Route | 5-Year 3-Way Forecast JSON Route | `GET /api/valuation/3-way-forecast/{symbol}` returning complete Pydantic JSON serialization of 3-way statements and diagnostics. | `symbol: str`, `start_year: int = 2026`, `tax_rate: float = 0.20` | `{"status": "success", "data": {...}}` | Returns HTTP 500 with error details if symbol resolution fails. | `server.py` (L1285-1304) |
| 16 | FastAPI Route | Modano Excel Download Route | `GET /api/valuation/export-excel/{symbol}` returning streaming downloadable `.xlsx` file with `Content-Disposition` header. | `symbol: str`, `scale_unit: str = "billion"`, `start_year: int = 2026`, `tax_rate: float = 0.20` | `FileResponse` / binary attachment | HTTP 500 on generation failure with descriptive JSON payload. | `server.py` (L1307-1341) |

---

## 2. Edge Cases & Boundary Behaviors

| # | Feature | Input / Scenario | Observed Behavior & Defensive Handling |
|---|---------|------------------|----------------------------------------|
| 1 | Negative Cash Detection | Firm with extreme debt service and negative operating margins (e.g. NVL distress profile) | `is_distressed=True`, `has_negative_cash=True`, `distressed_years=[2026, 2027, 2028]`, `summary_assessment="DISTRESSED"`. Solvency guard automatically freezes dividends and share repurchases to 0. MoS penalty of $+5\%$ to $+15\%$ applied. |
| 2 | Borderline Cash Buffer | Firm with positive cash balance but ending cash $< 3\%$ of annual sales | `is_distressed=False`, `has_negative_cash=False`, but `summary_assessment="TIGHT"`. Emits warning message: "Cash balance remains positive but operates below standard 3% operating turnover buffer." MoS penalty set to $+3.0\%$, dilution risk set to $+2.0\%$. |
| 3 | Robust Cash Balance | Cash balance $> 3\%$ of revenue across all 5 years (e.g. FPT, VNM) | `is_distressed=False`, `has_negative_cash=False`, `summary_assessment="HEALTHY"`. Zero penalties added to Margin of Safety ($\Delta_{\text{LiquidityDistress}} = 0.0\%$). |
| 4 | Excel Exporter Sheet Names with Spaces | Cross-sheet cell formulas referencing sheet names like `Working Capital Schedule` | Exporter explicitly encloses sheet names in single quotes (e.g. `='Working Capital Schedule'!C10`). Without single quotes, Excel evaluates the formula as `#NAME?` error. |
| 5 | Excel 5x5 Sensitivity Grid Singularity | Scenario where $WACC \le g$ in sensitivity grid | Grid uses standard range $WACC \in [9.0\%, 13.0\%]$ and $g \in [2.5\%, 4.5\%]$. Since $\min(WACC) = 9.0\% > \max(g) = 4.5\%$, the denominator $(WACC - g) \ge 4.5\% > 0$ strictly avoiding `#DIV/0!`. |
| 6 | Financial Sector Exporter Isolation | Banking / Securities stock (e.g. VCB, TCB, SSI) exported to Excel | `is_financial_sector=True` sets inventory and DIO to 0. Balance Sheet and Income Statement maintain exact closure without division by zero. |
| 7 | Zero Revenue / Cold-Start Stock | Ticker with missing or zero revenue in screener database | Base revenue imputed via Market Cap / $P/S$ proxy ($P/S = 1.20$), gross margin clamped to 25%, EBIT margin clamped to 15%. Balance sheet closure strictly maintained ($|\text{Diff}| < 10^{-5}$). |
| 8 | Currency Scaling Toggle | `scale_unit="raw"` vs `scale_unit="billion"` | When `billion` is selected, monetary values are divided by $10^9$ and formatted as `#,##0.0;(#,##0.0);"-"` with label `Tỷ VND (Billion VND)`. When `raw` is selected, exact VND amounts are exported with integer format `#,##0`. |

---

## 3. Deep-Dive Specification Analysis

### 3.1 Requirement R3: Liquidity Distress Firewall & Risk Alerts

#### Mathematical Formulation
1. **Negative Cash Condition:**
   $$\text{has\_negative\_cash} = \exists t \in [1..5] \quad \text{s.t.} \quad \text{Cash}_t < 0$$
   $$\text{DistressedYears} = \{ t \in [1..5] \mid \text{Cash}_t < 0 \}$$

2. **Shortfall Magnitude & Ratio:**
   $$\text{MinCash} = \min_{t \in [1..5]} \text{Cash}_t$$
   $$\text{MaxShortfall} = \max(0, -\text{MinCash})$$
   $$\text{ShortfallRatio} = \frac{\text{MaxShortfall}}{\max(\text{MarketCap}, 100 \times 10^9)}$$

3. **Risk Penalty Scoring:**
   - **Dilution Risk Penalty ($\text{Penalty}_{\text{dilution}}$):**
     $$\text{Penalty}_{\text{dilution}} = \begin{cases}
     \operatorname{clamp}(0.05 + 0.50 \times \text{ShortfallRatio}, 0.05, 0.25) & \text{if } \text{has\_negative\_cash} \\
     0.02 & \text{if } 0 \le \text{MinCash} < 0.03 \times \text{Revenue}_0 \\
     0.00 & \text{otherwise}
     \end{cases}$$
   - **Margin of Safety Add-on ($\Delta_{\text{LiquidityDistress}}$):**
     $$\Delta_{\text{LiquidityDistress}} = \begin{cases}
     \operatorname{clamp}(0.05 + 0.30 \times \text{ShortfallRatio}, 0.05, 0.15) & \text{if } \text{has\_negative\_cash} \\
     0.03 & \text{if } 0 \le \text{MinCash} < 0.03 \times \text{Revenue}_0 \\
     0.00 & \text{otherwise}
     \end{cases}$$

4. **Dynamic MOS Integration (`services/valuation_engine.py`):**
   $$\text{MOS}_{\text{dynamic}} = \operatorname{clamp}\left(\text{MOS}_{\text{base}} \times \max\left(0.7, \min\left(2.0, 1.0 + 0.5 \times (\beta_- - 1.0)\right)\right) + \Delta_{\text{Risk}} + \Delta_{\text{LiquidityDistress}}, 0.10, 0.60\right)$$
   Where:
   - $\text{MOS}_{\text{base}} = 0.20$ (20.0%)
   - $\Delta_{\text{Risk}}$ includes $+0.05$ for Altman Grey zone, $+0.10$ for Altman Distress zone, $+0.10$ for Beneish Manipulator, $+0.05$ for RKV Overvalued.
   - $\Delta_{\text{LiquidityDistress}}$ adds $+0.05$ to $+0.15$ from the 3-Way Engine.

5. **Intrinsic Value per Share Haircut:**
   $$\text{FairValue}_{\text{dilution\_adjusted}} = \text{CompositeFairValue} \times (1.0 - \text{Penalty}_{\text{dilution}})$$
   $$\text{TargetBuyPrice} = \text{FairValue}_{\text{dilution\_adjusted}} \times (1.0 - \text{MOS}_{\text{dynamic}})$$

---

### 3.2 Requirement R5: Modano-Compliant Interactive Excel Model Exporter

#### Workbook Architecture (7 Tabs)
```
[Workbook: {SYMBOL}_3Way_Financial_Model.xlsx]
├── 1. "Summary & Dashboard"      -> Executive KPI cards, Solvency Firewall status, 5Y core summary table
├── 2. "Income Statement"         -> 5Y P&L with dynamic Gross Profit, EBITDA, EBIT, EBT, Tax, NPAT formulas
├── 3. "Balance Sheet"            -> 5Y BS with Current/Non-Current Assets & Liab, Equity, Difference & IS_BALANCED checks
├── 4. "Cash Flow Statement"      -> Direct Method CFS reconciling to P&L & Working Capital, ending cash roll-forward
├── 5. "Working Capital Schedule" -> DSO, DIO, DPO, CCC, AR/INV/AP balances, Delta NWC reconciliation
├── 6. "Debt & Capital Schedule"  -> Debt roll-forward, Damodaran rating, pre/after-tax Kd, Equity roll-forward
└── 7. "Valuation & Sensitivity"  -> WACC derivation (Rf, ERP, Beta, Ke, Kd), DCF/FCFE/OE summary, 5x5 WACC vs g matrix
```

#### Color Palette & Visual Standard (Modano Standard)
| Token | Hex Color | Description / Application |
|---|---|---|
| `COLOR_NAVY_HEADER` | `#1F4E79` | Primary Title banners, Table column headers, active matrix labels |
| `COLOR_TEXT_WHITE` | `#FFFFFF` | Text color on Navy headers and banners |
| `COLOR_SECTION_ACCENT` | `#D9E1F2` | Section break fills, KPI card backgrounds, base-case matrix highlight |
| `COLOR_TEXT_NAVY` | `#1F4E79` | Section break text color, KPI value text |
| `COLOR_GREEN_FILL` | `#E2EFDA` | Balanced indicator fill (`BALANCED`), healthy liquidity status |
| `COLOR_GREEN_TEXT` | `#375623` | Dark green text on green status badges |
| `COLOR_RED_FILL` | `#FCE4D6` | Distressed status fill, unbalanced alert fill |
| `COLOR_RED_TEXT` | `#C65911` | Dark coral/red text on warning badges |
| `COLOR_BORDER_GRAY` | `#D9D9D9` | Thin internal cell gridlines (`BOX_BORDER`) |

#### Number Formats Applied
- **Currency (Billion VND):** `#,##0.0;(#,##0.0);"-"`
- **Currency (VND Raw):** `#,##0;(#,##0);"-"`
- **Per-share Price:** `#,##0" VND"`
- **Percentages (1 decimal):** `0.0%`
- **Percentages (2 decimals):** `0.00%`
- **Multiples / Coverage:** `0.00"x"`
- **Text / Code:** `@`

#### Critical Live Excel Formulas
1. **Summary Table CAGR:**
   `=(G{row}/C{row})^(1/4)-1`
2. **Gross Profit:**
   `=C5-C7` (Dynamic column replacement across C to G)
3. **EBITDA:**
   `=C8-C10`
4. **EBIT:**
   `=C11-C12`
5. **EBT:**
   `=C13-C15+C16`
6. **Corporate Tax:**
   `=MAX(0, C17*0.20)`
7. **NPAT:**
   `=C17-C18`
8. **Balance Sheet Difference:**
   `=C13-C25`
9. **Balance Sheet Invariant Check:**
   `=IF(ABS(C26)<1, "BALANCED", "UNBALANCED")`
10. **Direct Cash from Customers:**
    `='Income Statement'!C5 - 'Working Capital Schedule'!C16`
11. **Direct Cash to Suppliers:**
    `='Income Statement'!C7 + 'Working Capital Schedule'!C17 - 'Working Capital Schedule'!C18`
12. **Ending Cash Roll-Forward:**
    `=C25+C26`
13. **Cost of Equity (Ke):**
    `=C5+C7*C6`
14. **WACC:**
    `=0.70*C8 + 0.30*C9`
15. **2D Sensitivity Matrix Cell:**
    `=($H$5*(1+{col_let}${header_row}))/($A{data_row}-{col_let}${header_row})`

---

### 3.3 FastAPI REST API Route Specifications (`server.py`)

#### Route 1: 5-Year 3-Way Forecast API
- **Endpoint:** `GET /api/valuation/3-way-forecast/{symbol}`
- **Parameters:**
  - `symbol` (path, required): Stock ticker (e.g. `HPG`, `FPT`, `VCB`)
  - `start_year` (query, optional, default: `2026`): First projection year
  - `tax_rate` (query, optional, default: `0.20`): Corporate income tax rate
- **Response Status:** `200 OK`
- **Response Headers:** `Content-Type: application/json`
- **Response Schema:**
```json
{
  "status": "success",
  "data": {
    "symbol": "FPT",
    "company_name": "Công ty Cổ phần FPT",
    "sector": "VNIT",
    "is_financial_sector": false,
    "start_year": 2026,
    "forecast_years": [2026, 2027, 2028, 2029, 2030],
    "income_statement": {
      "years": [2026, 2027, 2028, 2029, 2030],
      "revenue": [59800.0, 68770.0, 79085.5, 90948.3, 104590.6],
      "revenue_growth": [0.15, 0.15, 0.15, 0.15, 0.15],
      "gross_profit": [22724.0, 26132.6, 30052.5, 34560.4, 39744.4],
      "ebit": [10764.0, 12378.6, 14235.4, 16370.7, 18826.3],
      "npat": [8451.2, 9719.9, 11178.9, 12856.7, 14786.2]
    },
    "balance_sheet": {
      "years": [2026, 2027, 2028, 2029, 2030],
      "total_assets": [62450.0, 72340.0, 83820.0, 97120.0, 112540.0],
      "total_liabilities": [20100.0, 22450.0, 25140.0, 28200.0, 31680.0],
      "total_equity": [42350.0, 49890.0, 58680.0, 68920.0, 80860.0],
      "balance_check_difference": [0.0, 0.0, 0.0, 0.0, 0.0],
      "is_balanced": [true, true, true, true, true]
    },
    "cash_flow_statement": {
      "years": [2026, 2027, 2028, 2029, 2030],
      "net_cfo": [9820.0, 11290.0, 12980.0, 14920.0, 17150.0],
      "net_cfi": [-3500.0, -4025.0, -4628.8, -5323.1, -6121.5],
      "net_cff": [-2535.4, -2915.9, -3353.7, -3857.0, -4435.9],
      "net_change_in_cash": [3784.6, 4349.1, 4997.5, 5739.9, 6592.6],
      "ending_cash": [11784.6, 16133.7, 21131.2, 26871.1, 33463.7]
    },
    "working_capital_schedule": [...],
    "debt_schedule": [...],
    "liquidity_distress_check": {
      "is_distressed": false,
      "has_negative_cash": false,
      "distressed_years": [],
      "min_cash_balance": 11784.6,
      "max_cash_shortfall": 0.0,
      "dilution_risk_pct": 0.0,
      "mos_penalty_pct": 0.0,
      "summary_assessment": "HEALTHY",
      "diagnostic_messages": ["Liquidity buffer remains robust across full 5-year forecast horizon."]
    },
    "all_years_balanced": true,
    "max_balance_difference": 0.0
  }
}
```

#### Route 2: Modano Excel Exporter Download API
- **Endpoint:** `GET /api/valuation/export-excel/{symbol}`
- **Parameters:**
  - `symbol` (path, required): Stock ticker (e.g. `HPG`, `FPT`, `VCB`)
  - `scale_unit` (query, optional, default: `"billion"`): `"billion"` or `"raw"`
  - `start_year` (query, optional, default: `2026`): First projection year
  - `tax_rate` (query, optional, default: `0.20`): Corporate income tax rate
- **Response Status:** `200 OK`
- **Response Headers:**
  - `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - `Content-Disposition: attachment; filename={SYMBOL}_3Way_Financial_Model.xlsx`
- **Response Body:** Streaming binary bytes of the openpyxl workbook file.

---

## 4. Acceptance Criteria & Verification Suites

### 4.1 Acceptance Criteria Mapping
| Acceptance Criterion | Verification Method | Target Threshold |
|---|---|---|
| **VN30 Balance Sheet Balance Test** | `tests/test_three_statement_engine.py::TestTier5VN30Constituents` parameterized across all 30 VN30 tickers. | $100\%$ pass rate; $|\text{Total Assets} - (\text{Total Liab} + \text{Total Equity})| < 10^{-5}$ for all 5 years. |
| **Direct Method CFS Reconciliation** | `tests/test_three_statement_engine.py::TestTier3DirectCashFlowReconciliation` | $\text{Gross CFO} \equiv \text{Gross Profit} - \Delta \text{Trade NWC}$ and $\text{Net CFO} \equiv \text{NPAT} + \text{D\&A} - \Delta \text{NWC}$ (rel tolerance $< 10^{-4}$). |
| **Working Capital Stability** | `tests/test_working_capital_engine.py` (all 4 tiers) | Zero `#DIV/0`, zero `NaN` across missing, negative, or extreme financial data. |
| **Liquidity Distress Detection** | `tests/test_three_statement_engine.py::TestTier4LiquidityDistressFirewall` | Identifies $\text{Cash}_t < 0$, enforces dividend freeze, computes dilution haircut and MoS penalty $\ge +5\%$. |
| **Excel Model Syntax & File Integrity** | `tests/test_financial_model_exporter.py` (all 5 tiers) | File size $> 5\text{ KB}$, 7 exact sheets, zero `#REF!`, `#NAME?`, or `#VALUE!` formula errors. |
| **FastAPI REST Endpoint Contract** | `tests/test_valuation_endpoints.py` via FastAPI `TestClient` | Status code 200, valid JSON schema, downloadable `.xlsx` binary headers. |

---

## 5. Summary & Handoff Recommendations

1. **R3 Liquidity Distress Firewall:** Fully implemented and integrated across the 3-Way Engine (`services/three_statement_engine.py`), the Valuation Engine (`services/valuation_engine.py`), and the Quantitative Backtest Engine (`services/fair_value_backtest_service.py`).
2. **R5 Excel Exporter & APIs:** Fully implemented with 7-tab openpyxl design, live formulas, corporate styling, auto-fit columns, and FastAPI routes in `server.py`.
3. **Test Infrastructure:** Comprehensive pytest suites in `tests/test_three_statement_engine.py`, `tests/test_working_capital_engine.py`, `tests/test_debt_capital_schedule_engine.py`, and `tests/test_financial_model_exporter.py` ensure total mathematical and architectural compliance.
