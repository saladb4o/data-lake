## 2026-09-02T10:41:45Z
You are the 3-Way Mathematical Modeling Spec Miner for the Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem upgrade.

Your working directory is: c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_2

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\ORIGINAL_REQUEST.md

Task:
1. Analyze requirements R1, R2, R4 from ORIGINAL_REQUEST.md in full depth:
   - R1: 5-year integrated forecast engine (P&L, BS, Direct Method CFS). Formulate the exact mathematical accounting identities for 3-way balance:
     * Total Assets = Total Liabilities + Total Equity ($|\text{Net Assets} - \text{Total Equity}| < 10^{-5}$)
     * Net Profit After Tax (NPAT) -> Retained Earnings / Retained Profits roll-forward: $\text{RE}_t = \text{RE}_{t-1} + \text{NPAT}_t - \text{Dividends}_t$
     * Direct Method Cash Flow Statement (Cash receipts from customers, cash paid to suppliers, operating expenses, tax paid, interest paid) reconciling to Net Change in Cash: $\text{Cash}_t = \text{Cash}_{t-1} + \Delta \text{Cash}_t$
     * Balance Sheet cash asset line linked directly to ending cash balance.
   - R2: Working capital days and NWC analyzer:
     * Debtor Days (DSO = (AR / Revenue) * 365)
     * Inventory Days (DIO = (Inventory / COGS) * 365)
     * Creditor Days (DPO = (AP / COGS or Purchases) * 365)
     * Cash Conversion Cycle (CCC = DSO + DIO - DPO)
     * Safeguards against division by zero or NaN for financial companies or missing data.
     * NWC dynamics and its connection to Direct Method cash receipts and payments.
   - R4: Debt amortization schedule & capital allocation:
     * Beginning debt, new borrowings, repayments, ending debt.
     * Interest expense = average debt * interest rate; interest payable / paid roll-forwards.
     * Damodaran synthetic credit rating and spread calculation based on Interest Coverage Ratio (EBIT / Interest Expense).
     * Dividend policy (payout ratio vs residual) and share repurchase schedules.
     * Integration with intrinsic valuation models (DDM, FCFE, Owner's Earnings).
2. Formulate explicit data schemas, input parameters, calculation steps, and output structures.
3. Write your report to `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_2\survey_report.md` and create `progress.md` and `handoff.md` in your directory.
4. Send a message to your parent when done.
