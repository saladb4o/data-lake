# Original User Request

## Initial Request — 2026-09-02T10:40:13Z

Implement the complete 5-phase Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem upgrade into the Vietnam quantitative valuation and backtesting platform (`Vibecoding vnstock`).

Working directory: c:\Users\Admin\Documents\Vibecoding vnstock
Integrity mode: development

## Requirements

### R1. Dynamic 3-Way Statement Forecasting Engine (`services/three_statement_engine.py`)
Build a 5-year integrated forecast engine generating complete, mathematically balanced Income Statement (P&L), Balance Sheet (BS), and Cash Flow Statement (Direct Method CFS) for any stock symbol. Enforce the two primary statement links ($NPAT \to \text{Retained Profits}$, $\Delta \text{Cash} \to \text{Cash}$) such that Total Assets equals Total Liabilities + Total Equity across all forecast periods ($|\text{Net Assets} - \text{Total Equity}| < 10^{-5}$).

### R2. Working Capital Days & NWC Analyzer (`services/working_capital_engine.py`)
Compute historical and projected Debtor Days (DSO), Inventory Days (DIO), Creditor Days (DPO), and Cash Conversion Cycle (CCC) from the local Data Lake (`data/financial_models.json`). Integrate dynamic working capital adjustments into operating cash receipts and payments.

### R3. Liquidity Distress Firewall & Negative Cash Risk Alert
Detect projected cash shortfalls ($\text{Cash}_t < 0$) across forecast horizons. Integrate this diagnostic into the Valuation Engine (`services/valuation_engine.py`) risk firewalls and the quantitative backtesting screening filters (`services/fair_value_backtest_service.py`) with dilution/distress scoring penalties.

### R4. Capital Allocation & Debt Schedule Engine (`services/debt_capital_schedule_engine.py`)
Implement debt amortization schedules, interest payable/paid roll-forwards, and dividend payout vs. share repurchase policies linked with Damodaran synthetic credit spreads and intrinsic models (DDM, FCFE, Owner's Earnings).

### R5. Modano-Compliant Interactive Excel Model Exporter (`services/financial_model_exporter.py` & API)
Provide an automated Excel exporter (`openpyxl`) that builds formatted 3-Way model workbooks containing live dynamic Excel formulas (`SUM`, `IF`, cross-sheet cell links, row grouping/outlines, balance checks) and expose FastAPI endpoints in `server.py` (`/api/valuation/3-way-forecast/{symbol}` and `/api/valuation/export-excel/{symbol}`).

## Acceptance Criteria

### Mathematical & Structural Integrity
- [ ] 100% of tested symbols in VN30 produce balanced balance sheets across all 5 forecast years ($|\text{Net Assets} - \text{Total Equity}| < 10^{-5}$).
- [ ] Direct method cash flow reconciliation matches net change in cash held on the balance sheet.
- [ ] Working capital DSO, DIO, DPO, and CCC compute accurately without `#DIV/0` or `NaN` errors on missing financial data.

### Risk & Valuation Integration
- [ ] `LiquidityDistressCheck` flags negative cash forecast periods and applies appropriate margin of safety / dilution penalties.
- [ ] Enhanced DCF, DDM, and FCFE models pull dynamic cash flows from the 3-Way engine.

### Exporter & Endpoints
- [ ] Generated `.xlsx` files open with valid dynamic formulas and zero formula errors (`#REF!`, `#NAME?`, `#VALUE!`).
- [ ] REST API endpoints in `server.py` return 200 OK with valid schema and streaming file downloads.
- [ ] Full automated pytest test suite (`tests/test_three_statement_engine.py`, `tests/test_working_capital_engine.py`, `tests/test_financial_model_exporter.py`) passes with 0 failures.
