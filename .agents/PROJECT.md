# Project: Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem

## Architecture
The Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem adds dynamic 5-year 3-Way forecasting (P&L, Balance Sheet, Direct Method Cash Flow), working capital dynamics (DSO, DIO, DPO, CCC), debt amortizations and Damodaran synthetic credit spreads, liquidity distress firewalls, and live dynamic Excel model exports to the quantitative valuation platform.

```
                      ┌──────────────────────────────────────┐
                      │            DATA LAKE                 │
                      │  - data/screener_snapshot.json       │
                      │  - data/historical_prices.json       │
                      │  - data/financial_models.json        │
                      └──────────────────┬───────────────────┘
                                         │
                                         ▼
                      ┌──────────────────────────────────────┐
                      │      services/stock_service.py       │
                      │  - resolve_data_file() / DiskDataLake│
                      └──────────────────┬───────────────────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
                 ▼                       ▼                       ▼
   ┌───────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
   │ services/working_capital_ │ │ services/debt_capital_    │ │ services/valuation_engine │
   │ engine.py                 │ │ schedule_engine.py        │ │ - 5-Factor CAPM WACC      │
   │ - DSO, DIO, DPO, CCC      │ │ - Debt Amortization       │ │ - Damodaran Spreads       │
   │ - NWC Schedule            │ │ - ICR & Synthetic Rating  │ │ - Liquidity Firewall (R3) │
   │ - Direct Cash Flow Delta  │ │ - Dividend Capital Alloc  │ │ - Intrinsic DCF/DDM/FCFE  │
   └─────────────┬─────────────┘ └─────────────┬─────────────┘ └─────────────┬─────────────┘
                 │                             │                             │
                 └───────────────┬─────────────┴─────────────────────────────┘
                                 │
                                 ▼
                 ┌───────────────────────────────────────────┐
                 │    services/three_statement_engine.py     │
                 │  - 5-Year Integrated 3-Way Forecast Engine│
                 │  - Income Statement (P&L)                 │
                 │  - Balance Sheet (BS)                     │
                 │  - Direct Method Cash Flow (CFS)          │
                 │  - Mathematical Balance Identity:         │
                 │    |Total Assets - Total Liab & Eq| < 0   │
                 │  - Statement Links: NPAT->RE, D-Cash->Cash│
                 │  - Liquidity Distress Diagnostics         │
                 └─────────────────────┬─────────────────────┘
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 │                                           │
                 ▼                                           ▼
   ┌───────────────────────────┐               ┌───────────────────────────┐
   │ services/financial_model_ │               │      API (server.py)      │
   │ exporter.py               │               │ - /api/valuation/3-way-   │
   │ - OpenPyXL 7-Tab Workbook │               │   forecast/{symbol}       │
   │ - Dynamic Formulas (SUM)  │               │ - /api/valuation/export-  │
   │ - Outline Groups / Colors │               │   excel/{symbol}          │
   └───────────────────────────┘               └───────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Working Capital Days & NWC Analysis | Historical & projected DSO, DIO, DPO, CCC with zero-div safeguards | M1 | ORIGINAL_REQUEST §R2 |
| 2 | NWC Cash Flow Adjustments | Delta AR, Delta Inv, Delta AP driving Direct Cash Flow operating receipts/payments | M1 | ORIGINAL_REQUEST §R2 |
| 3 | Debt Amortization Schedule | Principal amortizations, new debt drawdowns, roll-forwards | M2 | ORIGINAL_REQUEST §R4 |
| 4 | Damodaran Synthetic Credit Rating | ICR-based rating lookup ($AAA$ to $D$) & pre/after-tax $K_d$ computation | M2 | ORIGINAL_REQUEST §R4 |
| 5 | Solvency-Guarded Dividend Payout | Dividend payout & share repurchase policies respecting liquidity | M2 | ORIGINAL_REQUEST §R4 |
| 6 | 5-Year Integrated 3-Way Forecasting | Dynamic 5-year integrated P&L, BS, and Direct Method CFS | M3 | ORIGINAL_REQUEST §R1 |
| 7 | Exact Balance Sheet Closure | $|Total Assets_t - (Total Liabilities_t + Total Equity_t)| < 10^{-5}$ across all years | M3 | ORIGINAL_REQUEST §R1 |
| 8 | Direct Method Cash Flow Reconciliation | CFS Delta Cash identically matches Balance Sheet cash change | M3 | ORIGINAL_REQUEST §R1 |
| 9 | Liquidity Distress Firewall | Detect $Cash_t < 0$ and emit `LiquidityDistressCheck` diagnostic | M4 | ORIGINAL_REQUEST §R3 |
| 10 | Dynamic MOS & Dilution Penalties | Apply $+5\%$ to $+15\%$ MOS risk penalty and equity dilution haircut on distress | M4 | ORIGINAL_REQUEST §R3 |
| 11 | Intrinsic Model Cash Flow Linkages | Dynamic cash flows from 3-Way Engine into DCF, DDM, FCFE, Owner's Earnings | M4 | ORIGINAL_REQUEST §R4 |
| 12 | Backtest Screening Filter for Distress | Quantitative screening filter to penalize/exclude cash-distressed tickers | M4 | ORIGINAL_REQUEST §R3 |
| 13 | Modano-Compliant OpenPyXL Exporter | 7-tab audit-ready workbook with live formulas, outlines, balance checks | M5 | ORIGINAL_REQUEST §R5 |
| 14 | FastAPI 3-Way Forecast Route | `/api/valuation/3-way-forecast/{symbol}` returning full 5-year statement JSON | M5 | ORIGINAL_REQUEST §R5 |
| 15 | FastAPI Excel Download Route | `/api/valuation/export-excel/{symbol}` streaming `.xlsx` binary | M5 | ORIGINAL_REQUEST §R5 |
| 16 | Comprehensive E2E Verification | Automated Pytest suite across 100% VN30 symbols with 0 failures | M6 | ORIGINAL_REQUEST §Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Working Capital & NWC Engine | `services/working_capital_engine.py`, `tests/test_working_capital_engine.py` | none | DONE |
| 2 | M2: Capital Allocation & Debt Schedule Engine | `services/debt_capital_schedule_engine.py` | none | PLANNED |
| 3 | M3: Dynamic 3-Way Statement Forecasting Engine | `services/three_statement_engine.py`, `tests/test_three_statement_engine.py` | M1, M2 | PLANNED |
| 4 | M4: Liquidity Distress Firewall & Valuation Integration | `services/valuation_engine.py`, `services/fair_value_backtest_service.py` | M3 | PLANNED |
| 5 | M5: Modano Excel Exporter & FastAPI Endpoints | `services/financial_model_exporter.py`, `server.py`, `tests/test_financial_model_exporter.py` | M3 | PLANNED |
| 6 | M6: Final Verification & Tier 1-5 E2E Suite Pass | Full Pytest suite execution, 100% VN30 balance validation, adversarial coverage | M1, M2, M3, M4, M5 | PLANNED |

## Interface Contracts

### `services/working_capital_engine.py`
```python
class WorkingCapitalMetrics(BaseModel):
    dso: float
    dio: float
    dpo: float
    ccc: float
    accounts_receivable: float
    inventory: float
    accounts_payable: float
    net_working_capital: float
    delta_nwc: float

class WorkingCapitalEngine:
    @staticmethod
    def calculate_historical_days(rev: float, cogs: float, ar: float, inv: float, ap: float, sector: str = "DEFAULT") -> Dict[str, float]: ...
    
    @staticmethod
    def project_working_capital_schedule(base_metrics: Dict[str, float], revenue_series: List[float], cogs_series: List[float], sector: str = "DEFAULT") -> List[Dict[str, float]]: ...
```

### `services/debt_capital_schedule_engine.py`
```python
class DebtSchedulePeriod(BaseModel):
    year: int
    opening_debt: float
    principal_amortization: float
    new_borrowings: float
    closing_debt: float
    average_debt: float
    interest_coverage_ratio: float
    synthetic_rating: str
    credit_spread_bps: float
    cost_of_debt_pre_tax: float
    cost_of_debt_after_tax: float
    interest_expense: float
    cash_interest_paid: float
    dividends_paid: float
    share_repurchases: float

class DebtCapitalScheduleEngine:
    @staticmethod
    def calculate_synthetic_rating(icr: float, is_large_cap: bool = True) -> Tuple[str, float]: ...
    
    @staticmethod
    def project_debt_and_capital_schedule(base_debt: float, ebit_series: List[float], npat_series: List[float], capex_series: List[float], dividend_payout_ratio: float = 0.30, tax_rate: float = 0.20) -> List[DebtSchedulePeriod]: ...
```

### `services/three_statement_engine.py`
```python
class IncomeStatementForecast(BaseModel):
    years: List[int]
    revenue: List[float]
    cogs: List[float]
    gross_profit: List[float]
    sga_expense: List[float]
    ebit: List[float]
    interest_expense: List[float]
    ebt: List[float]
    tax_expense: List[float]
    npat: List[float]

class BalanceSheetForecast(BaseModel):
    years: List[int]
    cash: List[float]
    accounts_receivable: List[float]
    inventory: List[float]
    other_current_assets: List[float]
    total_current_assets: List[float]
    net_ppe: List[float]
    other_non_current_assets: List[float]
    total_non_current_assets: List[float]
    total_assets: List[float]
    accounts_payable: List[float]
    other_current_liabilities: List[float]
    short_term_debt: List[float]
    total_current_liabilities: List[float]
    long_term_debt: List[float]
    total_liabilities: List[float]
    contributed_capital: List[float]
    retained_earnings: List[float]
    total_equity: List[float]
    total_liabilities_and_equity: List[float]
    balance_check_difference: List[float]
    is_balanced: List[bool]

class CashFlowForecast(BaseModel):
    years: List[int]
    cash_from_customers: List[float]
    cash_to_suppliers: List[float]
    cash_for_opex: List[float]
    cash_interest_paid: List[float]
    cash_tax_paid: List[float]
    net_cfo: List[float]
    capex: List[float]
    net_cfi: List[float]
    net_debt_drawdown: List[float]
    dividends_paid: List[float]
    net_cff: List[float]
    net_change_in_cash: List[float]
    beginning_cash: List[float]
    ending_cash: List[float]

class ThreeStatementForecastResult(BaseModel):
    symbol: str
    company_name: str
    sector: str
    income_statement: IncomeStatementForecast
    balance_sheet: BalanceSheetForecast
    cash_flow_statement: CashFlowForecast
    working_capital_schedule: List[Dict[str, float]]
    debt_schedule: List[Dict[str, float]]
    liquidity_distress_check: Dict[str, Any]
```

### `services/financial_model_exporter.py`
```python
class FinancialModelExporter:
    @staticmethod
    def generate_excel_workbook(forecast_result: ThreeStatementForecastResult) -> openpyxl.Workbook: ...
    
    @staticmethod
    def export_excel_bytes(forecast_result: ThreeStatementForecastResult) -> io.BytesIO: ...
```

## Code Layout
- `services/working_capital_engine.py` (Exclusive to M1 Worker)
- `services/debt_capital_schedule_engine.py` (Exclusive to M2 Worker)
- `services/three_statement_engine.py` (Exclusive to M3 Worker)
- `services/valuation_engine.py` (Exclusive to M4 Worker)
- `services/fair_value_backtest_service.py` (Exclusive to M4 Worker)
- `services/financial_model_exporter.py` (Exclusive to M5 Worker)
- `server.py` (Exclusive to M5 Worker)
- `tests/test_working_capital_engine.py` (Exclusive to M1 / Test Writers)
- `tests/test_three_statement_engine.py` (Exclusive to M3 / Test Writers)
- `tests/test_financial_model_exporter.py` (Exclusive to M5 / Test Writers)
