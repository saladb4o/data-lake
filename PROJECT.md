# Project: Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem

## Architecture
The Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem upgrades the quantitative valuation and backtesting platform (`Vibecoding vnstock`) into an institutional-grade, multi-period financial forecasting, valuation, and reporting suite for the Vietnamese stock market (HOSE, HNX, UPCOM).

### Component Flow & Data Boundaries
```
                  ┌────────────────────────────────────────────────────────┐
                  │          Local Data Lake & Ingestion Layer             │
                  │   data/financial_models.json, data/all_symbols.json    │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                    ┌─────────────────────────┴────────────────────────┐
                    ▼                                                  ▼
      ┌─────────────────────────────┐                    ┌─────────────────────────────┐
      │   Working Capital Engine    │                    │ Debt & Capital Schedule     │
      │  (services/working_capital_ │                    │ (services/debt_capital_     │
      │           engine.py)        │                    │      schedule_engine.py)    │
      │ - DSO, DIO, DPO, CCC days   │                    │ - Debt Amortization 5Y      │
      │ - Mean-reversion trajectory │                    │ - Damodaran Synthetic Kd    │
      │ - Negative CCC (Retail)     │                    │ - 5-Iter Fixed Point Solver │
      │ - Financial sector isolation│                    │ - Solvency Dividend Firewall│
      └─────────────┬───────────────┘                    └─────────────┬───────────────┘
                    │                                                  │
                    └─────────────────────────┬────────────────────────┘
                                              ▼
                    ┌──────────────────────────────────────────────────┐
                    │      Dynamic 3-Way Statement Engine (R1, R3)     │
                    │        (services/three_statement_engine.py)      │
                    │ - 5Y Integrated Income Statement (P&L)           │
                    │ - 5Y Direct Method Cash Flow Statement (CFS)     │
                    │ - 5Y Balance Sheet (BS): Net Assets == Equity    │
                    │ - Statement Link 1: NPAT -> Retained Earnings    │
                    │ - Statement Link 2: Delta Cash -> BS Cash Asset  │
                    │ - Liquidity Distress Firewall & Risk Penalties   │
                    └─────────────────────────┬────────────────────────┘
                                              │
                    ┌─────────────────────────┴────────────────────────┐
                    ▼                                                  ▼
      ┌─────────────────────────────┐                    ┌─────────────────────────────┐
      │   Valuation & Backtesting   │                    │ Modano Excel Model Exporter │
      │          Integration        │                    │ (services/financial_model_  │
      │ (services/valuation_engine. │                    │          exporter.py)       │
      │  services/fair_value_...)   │                    │ - 7-Tab Styled Workbook     │
      │ - FCFF / FCFE / OE / DDM    │                    │ - Live Dynamic Excel Formula│
      │ - Dynamic Beta MoS scaling  │                    │ - 5x5 WACC vs g Sensitivity │
      │ - Liquidity distress haircut│                    │ - Balance Checks & Audit Row│
      └─────────────────────────────┘                    └─────────────┬───────────────┘
                                                                       │
                                                                       ▼
                                                         ┌─────────────────────────────┐
                                                         │     FastAPI REST Service    │
                                                         │         (server.py)         │
                                                         │ - GET /3-way-forecast/{sym} │
                                                         │ - GET /export-excel/{sym}   │
                                                         └─────────────────────────────┘
```

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| 1 | 5-Year Integrated 3-Way Forecast | Generates 5Y synchronized P&L, BS, and Direct Method CFS for any VN ticker. | M1 | R1 Spec |
| 2 | Strict Balance Sheet Closure | Enforces $|\text{Net Assets}_t - \text{Total Equity}_t| < 10^{-5}$ across all forecast years. | M1 | R1 Spec |
| 3 | Dynamic Statement Link 1 | Net Income to Equity roll-forward ($\text{RE}_t = \text{RE}_{t-1} + \text{NPAT}_t - \text{Div}_t$). | M1 | R1 Spec |
| 4 | Dynamic Statement Link 2 | Net change in cash directly links to Balance Sheet ending cash asset line. | M1 | R1 Spec |
| 5 | Direct Method CFS Conservation | Direct cash receipts and disbursements match Net CFO ($\text{NPAT} + \text{D\&A} - \Delta\text{NWC}$). | M1 | R1 Spec |
| 6 | Working Capital Efficiency Ratios | Computes DSO, DIO, DPO, and CCC with zero-division protection and $[0, 1095]$ clamping. | M2 | R2 Spec |
| 7 | Mean-Reverting NWC Trajectory | Projects 5Y NWC with geometric mean reversion $\lambda$ towards calibrated sector priors. | M2 | R2 Spec |
| 8 | Negative CCC Retail Handling | Preserves negative CCC and negative operating working capital for modern retailers (e.g. MWG). | M2 | R2 Spec |
| 9 | Financial Sector Isolation | Safely zeroes working capital for 42 banks, insurers, and securities brokers. | M2 | R2 Spec |
| 10 | Direct Cash Working Capital Bridges | Converts accrual revenue/COGS to cash collections ($R - \Delta\text{AR}$) and payments. | M2 | R2 Spec |
| 11 | Multi-Period Debt Amortization | Models opening debt, amortization, CapEx financing drawdowns, and closing debt. | M3 | R4 Spec |
| 12 | Aswath Damodaran Synthetic Ratings | Maps Interest Coverage Ratio (ICR) to AAA..D ratings and credit spreads for large/small cap. | M3 | R4 Spec |
| 13 | Fixed-Point Iterative Circularity Solver | Resolves circular feedback between Debt, Interest, and $K_d(\text{ICR})$ in $\le 5$ iterations. | M3 | R4 Spec |
| 14 | Solvency Dividend & Covenant Firewall | Blocks dividends and buybacks if $\text{NPAT} \le 0$ or $\text{ICR} < 1.20$. | M3 | R4 Spec |
| 15 | Intrinsic Valuation Cash Flow Linkages | Direct feeds for FCFF, FCFE, Warren Buffett Owner's Earnings, and DDM streams. | M3 | R4 Spec |
| 16 | Liquidity Distress Firewall & Risk Alerts | Detects $\text{Cash}_t < 0$, computes dilution haircut (5%-25%) and MoS penalty (5%-15%). | M3 | R3 Spec |
| 17 | Dynamic Margin of Safety Integration | Combines Downside Beta, Altman/Beneish traps, and Liquidity Distress penalties into dynamic MoS. | M3 | R3 Spec |
| 18 | 7-Tab Modano-Compliant Excel Workbook | Builds formatted workbook: Summary, P&L, BS, CFS, Working Capital, Debt, Valuation. | M4 | R5 Spec |
| 19 | Live Dynamic Excel Native Formulas | Injects Excel native formulas (`SUM`, `IF`, cell links) across all sheets with zero formula errors. | M4 | R5 Spec |
| 20 | 2D Valuation Sensitivity Matrix (5x5) | Injects dynamic 5x5 WACC vs terminal growth $g$ matrix referencing live FCFF. | M4 | R5 Spec |
| 21 | Balance Sheet Audit Row & Styling | Soft green/red audit badge (`=IF(ABS(Diff)<1, "BALANCED", "UNBALANCED")`) with corporate navy styling. | M4 | R5 Spec |
| 22 | FastAPI 3-Way Forecast REST Route | `GET /api/valuation/3-way-forecast/{symbol}` returning 5-year JSON payload. | M4 | R5 Spec |
| 23 | FastAPI Excel Download Streaming Route | `GET /api/valuation/export-excel/{symbol}` returning streaming `.xlsx` attachment. | M4 | R5 Spec |
| 24 | E2E Testing Suite (Tiers 1-4) | Comprehensive test matrix for VN30 balance, direct CFS, working capital, exporter, and endpoints. | Test Track | Acceptance Criteria |
| 25 | Tier 5 Adversarial Coverage Hardening | White-box adversarial testing, stress cases, edge-case probing, and coverage hardening. | Final Milestone | Acceptance Criteria |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| **Test Track** | E2E Testing Infrastructure & Test Cases | Build comprehensive opaque-box test suite across Tiers 1-4 and publish `TEST_READY.md`. | none | IN_PROGRESS |
| **M1** | Dynamic 3-Way Statement Engine | `services/three_statement_engine.py` (R1: 5Y P&L, BS, Direct CFS, invariant closure). | none | IN_PROGRESS |
| **M2** | Working Capital Days & NWC Analyzer | `services/working_capital_engine.py` (R2: DSO, DIO, DPO, CCC, mean-reversion, retail, financials). | none | IN_PROGRESS |
| **M3** | Debt Schedules, Capital Allocation & Distress Firewall | `services/debt_capital_schedule_engine.py`, `services/valuation_engine.py` (R3, R4: Damodaran $K_d$, dividend firewall, distress MoS). | M1, M2 | PLANNED |
| **M4** | Excel Model Exporter & FastAPI REST Endpoints | `services/financial_model_exporter.py`, `server.py` (R5: 7-tab openpyxl exporter, live formulas, REST routes). | M1, M2, M3 | PLANNED |
| **Final** | 100% E2E Test Pass & Adversarial Hardening | Verify all E2E tests pass, execute Tier 5 adversarial hardening, and pass Forensic Audit. | Test Track, M1, M2, M3, M4 | PLANNED |

---

## Interface Contracts

### 1. Working Capital Engine $\leftrightarrow$ Three-Statement Engine
```python
class WorkingCapitalSchedulePeriod(BaseModel):
    year: int
    revenue: float
    cogs: float
    dso: float
    dio: float
    dpo: float
    ccc: float
    accounts_receivable: float
    inventory: float
    other_current_assets: float
    accounts_payable: float
    other_current_liabilities: float
    trade_working_capital: float
    total_operating_nwc: float
    delta_trade_nwc: float
    delta_total_nwc: float
    cash_collected_from_customers: float
    cash_paid_to_suppliers: float
    cash_paid_for_opex: float

def build_working_capital_schedule(
    base_data: Dict[str, Any],
    revenue_series: List[float],
    cogs_series: List[float],
    sga_series: List[float],
    start_year: int = 2026,
    mean_revert_speed: float = 0.0,
    sector: Optional[str] = None
) -> List[WorkingCapitalSchedulePeriod]: ...
```

### 2. Debt Schedule Engine $\leftrightarrow$ Three-Statement Engine
```python
class DebtSchedulePeriod(BaseModel):
    year: int
    opening_debt: float
    new_borrowings: float
    principal_amortization: float
    closing_debt: float
    average_debt: float
    short_term_debt: float
    long_term_debt: float
    net_debt_drawdown: float
    ebit: float
    interest_coverage_ratio: float
    synthetic_rating: str
    credit_spread_bps: int
    pre_tax_kd: float
    after_tax_kd: float
    interest_expense: float
    interest_income: float
    npat: float
    dividends_paid: float
    share_repurchases: float
    total_capital_returned: float
    is_covenant_breached: bool
    is_dividend_curtailed: bool
    curtailment_reason: str

def build_debt_schedule(
    base_debt: float,
    ebit_series: List[float],
    capex_series: List[float],
    npat_series: List[float],
    start_year: int = 2026,
    market_cap: float = 10000e9,
    rf: float = 0.05,
    tax_rate: float = 0.20,
    payout_ratio: float = 0.30
) -> List[DebtSchedulePeriod]: ...
```

### 3. Three-Statement Engine $\leftrightarrow$ Excel Exporter & FastAPI API
```python
class ThreeStatementForecastResult(BaseModel):
    symbol: str
    company_name: str
    sector: str
    is_financial_sector: boolean
    start_year: int
    forecast_years: List[int]
    income_statement: IncomeStatementForecast
    balance_sheet: BalanceSheetForecast
    cash_flow_statement: CashFlowForecast
    working_capital_schedule: List[WorkingCapitalSchedulePeriod]
    debt_schedule: List[DebtSchedulePeriod]
    liquidity_distress_check: LiquidityDistressCheck
    all_years_balanced: bool
    max_balance_difference: float

def run_three_statement_forecast(
    symbol: str,
    start_year: int = 2026,
    tax_rate: float = 0.20,
    revenue_growth_override: Optional[List[float]] = None
) -> ThreeStatementForecastResult: ...
```

---

## Code Layout & File Ownership
| File Path | Owning Module / Milestone | Description |
|---|---|---|
| `services/three_statement_engine.py` | Milestone 1 (M1) | 5-Year 3-Way statement forecast engine & distress diagnostic |
| `services/working_capital_engine.py` | Milestone 2 (M2) | Working capital days (DSO, DIO, DPO, CCC) & NWC schedule |
| `services/debt_capital_schedule_engine.py` | Milestone 3 (M3) | Debt amortization, Damodaran ratings, solvency waterfall |
| `services/valuation_engine.py` | Milestone 3 (M3) | Downside Beta MoS, Liquidity Distress integration, intrinsic valuation |
| `services/fair_value_backtest_service.py` | Milestone 3 (M3) | Backtest screening distress filter & dynamic MoS gating |
| `services/financial_model_exporter.py` | Milestone 4 (M4) | Modano 7-tab openpyxl Excel exporter with dynamic formulas |
| `server.py` | Milestone 4 (M4) | FastAPI REST API endpoints (`/3-way-forecast`, `/export-excel`) |
| `tests/test_three_statement_engine.py` | E2E Testing Track | Unit, integration, VN30 balance, and direct CFS test suite |
| `tests/test_working_capital_engine.py` | E2E Testing Track | Unit & edge-case test suite for working capital engine |
| `tests/test_debt_capital_schedule_engine.py`| E2E Testing Track | Unit & edge-case test suite for debt schedule engine |
| `tests/test_financial_model_exporter.py` | E2E Testing Track | Test suite for openpyxl Excel generator & formula validation |
| `tests/test_valuation_endpoints.py` | E2E Testing Track | Test suite for FastAPI REST API endpoints |
