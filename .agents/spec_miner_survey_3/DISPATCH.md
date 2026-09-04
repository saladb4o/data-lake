## 2026-09-02T10:41:45Z
You are the Excel & API Spec Miner for the Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem upgrade.

Your working directory is: c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_3

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\ORIGINAL_REQUEST.md

Task:
1. Analyze requirements R3, R5 and acceptance criteria from ORIGINAL_REQUEST.md:
   - R3: Liquidity Distress Firewall & Negative Cash Risk Alert:
     * Definition of negative cash detection ($\text{Cash}_t < 0$ in any forecast period $t \in [1..5]$).
     * Margin of safety / distress dilution penalty scoring and penalty mechanisms in `services/valuation_engine.py` and backtest screening in `services/fair_value_backtest_service.py`.
   - R5: Modano-Compliant Interactive Excel Model Exporter (`services/financial_model_exporter.py` & API):
     * openpyxl workbook design: Cover/Summary sheet, Income Statement, Balance Sheet, Cash Flow Statement, Debt & Working Capital Schedules.
     * Dynamic Excel live formulas: dynamic cell references, `SUM(...)`, `IF(...)`, cross-sheet links, dynamic totals, balance checks ($= \text{Assets} - (\text{Liabilities} + \text{Equity})$ with alert styling).
     * Row grouping / outline levels for collapsible detail sections.
     * Number formatting (currency, percentages, decimals), column width auto-fit, header styling.
     * Zero formula errors (`#REF!`, `#NAME?`, `#VALUE!`).
   - FastAPI REST API routes in `server.py`:
     * `GET /api/valuation/3-way-forecast/{symbol}` returning JSON payload of 5-year integrated model.
     * `GET /api/valuation/export-excel/{symbol}` returning streaming/downloadable `.xlsx` file (`StreamingResponse` or `FileResponse` with proper headers `Content-Disposition: attachment; filename=...`).
   - Acceptance Criteria & Test Requirements:
     * VN30 balance sheet balance test across 5 years.
     * Direct method cash flow reconciliation test.
     * Pytest test suites: `tests/test_three_statement_engine.py`, `tests/test_working_capital_engine.py`, `tests/test_financial_model_exporter.py`.
2. Write your specification report to `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_3\survey_report.md` and create `progress.md` and `handoff.md` in your directory.
3. Send a message to your parent when done.
