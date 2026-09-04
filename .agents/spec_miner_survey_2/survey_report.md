# MODANO 3-WAY INTEGRATED FINANCIAL MODELING & VALUATION ECOSYSTEM
## Mathematical Modeling & Specification Survey Report (Requirements R1, R2, R4)

**Working Directory:** `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_2`  
**Target File:** `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\spec_miner_survey_2\survey_report.md`  
**Date:** 2026-09-02  
**Author:** 3-Way Mathematical Modeling Specification Miner  
**System Under Analysis:** `Vibecoding vnstock` — Quantitative Valuation & 3-Way Integrated Financial Forecast System  

---

## 1. Executive Summary & Architecture Overview

The Modano 3-Way Integrated Financial Modeling ecosystem creates an institutional-grade, multi-period financial forecasting and valuation platform for the Vietnamese stock market (HOSE, HNX, UPCOM). The core architectural requirement is the strict maintenance of **double-entry accounting invariants** and **direct method cash flow conservation** across all 5 forecast years ($t \in [1, 5]$).

The modeling core consists of three interdependent mathematical engines:
1. **Dynamic 3-Way Statement Forecasting Engine (`services/three_statement_engine.py`) [R1]**: Orchestrates the 5-year integrated forecast (P&L, BS, Direct Method CFS) enforcing the fundamental identity:
   $$\text{Total Assets}_t \equiv \text{Total Liabilities}_t + \text{Total Equity}_t \quad \left( |\text{Net Assets}_t - \text{Total Equity}_t| < 10^{-5} \right)$$
2. **Working Capital Days & NWC Analyzer (`services/working_capital_engine.py`) [R2]**: Computes operating efficiency days (DSO, DIO, DPO, CCC), models mean-reverting working capital schedules, handles negative cash conversion cycles, isolates financial institutions, and derives Direct Method cash receipts and payments.
3. **Debt Schedule & Capital Allocation Engine (`services/debt_capital_schedule_engine.py`) [R4]**: Models debt amortization, solves the circular interest-debt feedback loop via fixed-point iteration, implements Damodaran synthetic credit spreads based on Interest Coverage Ratios (ICR), enforces statutory dividend and covenant firewalls, and feeds downstream valuation engines (FCFF, FCFE, DDM, Owner's Earnings).

```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                        3-Way Integrated Forecast Pipeline                   │
   └─────────────────────────────────────────────────────────────────────────────┘
                                          │
                 ┌────────────────────────┴────────────────────────┐
                 ▼                                                 ▼
   ┌───────────────────────────┐                     ┌───────────────────────────┐
   │  Working Capital Engine   │                     │  Debt & Capital Schedule  │
   │  (R2: DSO, DIO, DPO, CCC) │                     │  (R4: Amortization, Kd,   │
   │  Delta NWC & Direct Cash  │                     │   Damodaran ICR Spreads,  │
   │  Receipts / Payments      │                     │   Dividend Firewalls)     │
   └─────────────┬─────────────┘                     └─────────────┬─────────────┘
                 │                                                 │
                 └────────────────────────┬────────────────────────┘
                                          ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │             Dynamic 3-Way Forecasting Engine (R1: 5-Year 3-Way)             │
   │   - Income Statement (P&L)                                                  │
   │   - Direct Method Cash Flow Statement (CFS) -> Delta Cash                   │
   │   - Balance Sheet (BS) -> Total Assets == Total Liabilities + Equity        │
   │   - Mathematical Invariant Closure: |TA - (TL + TE)| < 10^-5                │
   └──────────────────────────────────────┬──────────────────────────────────────┘
                                          ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │               Downstream Valuation & Risk Integration (R3, R4)              │
   │   - Free Cash Flow to Firm (FCFF)       - Liquidity Distress Firewall (R3)  │
   │   - Free Cash Flow to Equity (FCFE)     - Buffett Owner's Earnings          │
   │   - Dividend Discount Model (DDM)       - 22 Quant Valuation Models         │
   └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Requirement R1: Dynamic 5-Year 3-Way Statement Forecasting Engine

### 2.1 Fundamental Accounting Identities & Mathematical Balance Proof

A standard financial model often suffers from "plugging" (forcing cash or debt to balance the balance sheet without an underlying transaction reason). In the Modano standard, the 3-way balance is **algebraically exact** by construction because every balance sheet change is the direct result of an income statement or cash flow statement transaction.

#### The Two Primary Dynamic Statement Links:
1. **Dynamic Statement Link 1 (Net Income to Equity):**
   $$\text{Retained Earnings}_t = \text{Retained Earnings}_{t-1} + \text{NPAT}_t - \text{Dividends Paid}_t$$
   $$\text{Contributed Capital}_t = \text{Contributed Capital}_{t-1} - \text{Share Repurchases}_t$$
   $$\text{Total Equity}_t = \text{Contributed Capital}_t + \text{Retained Earnings}_t$$

2. **Dynamic Statement Link 2 (Net Change in Cash to Balance Sheet Cash):**
   $$\text{Cash}_t = \text{Cash}_{t-1} + \Delta \text{Cash}_t$$
   $$\Delta \text{Cash}_t = \text{Net CFO}_t + \text{Net CFI}_t + \text{Net CFF}_t$$

#### Mathematical Proof of Balance Sheet Closure:
Let the Balance Sheet at time $t$ consist of:
- $\text{Total Assets}_t = \text{Cash}_t + \text{AR}_t + \text{Inv}_t + \text{OCA}_t + \text{Net PPE}_t + \text{ONCA}_t$
- $\text{Total Liabilities}_t = \text{AP}_t + \text{OCL}_t + \text{Total Debt}_t$
- $\text{Total Equity}_t = \text{Contributed Capital}_t + \text{Retained Earnings}_t$

The period change in Total Assets is:
$$\Delta \text{TA}_t = \Delta \text{Cash}_t + \Delta \text{AR}_t + \Delta \text{Inv}_t + \Delta \text{OCA}_t + \Delta \text{Net PPE}_t + \Delta \text{ONCA}_t$$

Given:
- $\Delta \text{Net PPE}_t = \text{CapEx}_t - \text{D\&A}_t$
- $\Delta \text{ONCA}_t = 0$ (held constant or modeled separately)
- $\Delta \text{Cash}_t = \text{Net CFO}_t + \text{Net CFI}_t + \text{Net CFF}_t$
- $\text{Net CFO}_t = \text{NPAT}_t + \text{D\&A}_t - (\Delta \text{AR}_t + \Delta \text{Inv}_t + \Delta \text{OCA}_t - \Delta \text{AP}_t - \Delta \text{OCL}_t)$
- $\text{Net CFI}_t = -\text{CapEx}_t$
- $\text{Net CFF}_t = \Delta \text{Debt}_t - \text{Dividends Paid}_t - \text{Share Repurchases}_t$

Substituting into $\Delta \text{Cash}_t$:
$$\Delta \text{Cash}_t = [\text{NPAT}_t + \text{D\&A}_t - \Delta \text{NWC}_t] - \text{CapEx}_t + [\Delta \text{Debt}_t - \text{Dividends Paid}_t - \text{Share Repurchases}_t]$$

Now substitute $\Delta \text{Cash}_t$ and $\Delta \text{Net PPE}_t$ into $\Delta \text{TA}_t$:
$$\Delta \text{TA}_t = [\text{NPAT}_t + \text{D\&A}_t - \Delta \text{NWC}_t - \text{CapEx}_t + \Delta \text{Debt}_t - \text{Dividends}_t - \text{Repurchases}_t] + \Delta \text{Operating Assets}_t + (\text{CapEx}_t - \text{D\&A}_t)$$

Since $\Delta \text{Operating Assets}_t - \Delta \text{NWC}_t = \Delta \text{Operating Liabilities}_t = \Delta \text{AP}_t + \Delta \text{OCL}_t$:
$$\Delta \text{TA}_t = \text{NPAT}_t - \text{Dividends}_t - \text{Repurchases}_t + \Delta \text{Debt}_t + \Delta \text{AP}_t + \Delta \text{OCL}_t$$

Compare this to the period change in Total Liabilities & Equity:
$$\Delta (\text{TL}_t + \text{TE}_t) = (\Delta \text{AP}_t + \Delta \text{OCL}_t + \Delta \text{Debt}_t) + (-\text{Repurchases}_t + \text{NPAT}_t - \text{Dividends}_t)$$
$$\Delta \text{TA}_t \equiv \Delta (\text{TL}_t + \text{TE}_t) \quad \forall t \in [1, 5]$$

When the base period $t=0$ is calibrated such that $\text{TA}_0 = \text{TL}_0 + \text{TE}_0$, then for all forecast periods $t \ge 1$:
$$|\text{Total Assets}_t - (\text{Total Liabilities}_t + \text{Total Equity}_t)| < 10^{-5} \quad \blacksquare$$

---

### 2.2 Income Statement (P&L) Formulation & Line-by-Line Mechanics

The 5-year forecast Income Statement is constructed recursively for each period $t$:

| Line Item | Mathematical Formula / Derivation | Description |
|---|---|---|
| **Revenue ($R_t$)** | $R_t = R_{t-1} \times (1 + g_{R,t})$ | Projected turnover using mean-reverting revenue growth trajectory. |
| **COGS ($\text{COGS}_t$)** | $\text{COGS}_t = R_t \times (1 - \text{GM}_t)$ | Cost of sales determined by gross margin forecast ($\text{GM}_t$). |
| **Gross Profit ($\text{GP}_t$)** | $\text{GP}_t = R_t - \text{COGS}_t = R_t \times \text{GM}_t$ | Gross trading profit. |
| **D&A ($\text{DA}_t$)** | $\text{DA}_t = \text{Net PPE}_{t-1} \times r_{\text{depr}}$ | Straight-line depreciation based on opening Net PPE ($r_{\text{depr}} \approx 8.0\%$). |
| **SG&A ($\text{SGA}_t$)** | $\text{SGA}_t = \max(0, \text{GP}_t - \text{DA}_t - R_t \times \text{OPM}_t)$ | Operating expenses backing into targeted operating margin ($\text{OPM}_t$). |
| **EBITDA ($\text{EBITDA}_t$)** | $\text{EBITDA}_t = \text{GP}_t - \text{SGA}_t = \text{EBIT}_t + \text{DA}_t$ | Earnings before interest, taxes, depreciation, and amortization. |
| **EBIT ($\text{EBIT}_t$)** | $\text{EBIT}_t = \text{EBITDA}_t - \text{DA}_t = R_t \times \text{OPM}_t$ | Operating profit. |
| **Interest Expense ($\text{IntExp}_t$)** | $\text{IntExp}_t = \text{Average Debt}_t \times K_{d,\text{pre},t}$ | Financing cost calculated from debt schedule sub-engine. |
| **Interest Income ($\text{IntInc}_t$)** | $\text{IntInc}_t = \max(0, \text{Cash}_{t-1} \times r_{\text{cash}})$ | Interest earned on cash balances ($r_{\text{cash}} \approx 2.0\%$). |
| **Earnings Before Tax ($\text{EBT}_t$)** | $\text{EBT}_t = \text{EBIT}_t - \text{IntExp}_t + \text{IntInc}_t$ | Pre-tax profit. |
| **Tax Expense ($\text{Tax}_t$)** | $\text{Tax}_t = \max(0, \text{EBT}_t \times T)$ | Corporate income tax ($T = 20\%$). If $\text{EBT} \le 0 \implies \text{Tax} = 0$. |
| **Net Profit After Tax ($\text{NPAT}_t$)** | $\text{NPAT}_t = \text{EBT}_t - \text{Tax}_t$ | Bottom-line earnings rolling forward into Retained Earnings. |

---

### 2.3 Direct Method Cash Flow Statement (CFS) Formulation & Conservation Invariants

The Cash Flow Statement is implemented via the **Direct Method**, which reflects actual cash inflows and outflows directly rather than only adjusting Net Income.

#### Direct Method Operating Cash Flows:
1. **Cash Receipts from Customers:**
   $$\text{Cash}_{\text{cust},t} = R_t - \Delta \text{AR}_t = R_t - (\text{AR}_t - \text{AR}_{t-1})$$
2. **Cash Paid to Suppliers:**
   $$\text{Cash}_{\text{supp},t} = \text{COGS}_t + \Delta \text{Inv}_t - \Delta \text{AP}_t = \text{COGS}_t + (\text{Inv}_t - \text{Inv}_{t-1}) - (\text{AP}_t - \text{AP}_{t-1})$$
3. **Cash Paid for Operating Expenses (SG&A):**
   $$\text{Cash}_{\text{opex},t} = \text{SGA}_t + \Delta \text{OCA}_t - \Delta \text{OCL}_t$$
4. **Cash Interest Paid & Received:**
   $$\text{Cash}_{\text{int\_paid},t} = \text{IntExp}_t$$
   $$\text{Cash}_{\text{int\_rec},t} = \text{IntInc}_t$$
5. **Cash Tax Paid:**
   $$\text{Cash}_{\text{tax\_paid},t} = \text{Tax}_t$$

#### Operating Cash Flow Invariant Identities:
- **Gross CFO Invariant:**
  $$\text{Gross CFO}_t = \text{Cash}_{\text{cust},t} - \text{Cash}_{\text{supp},t} \equiv \text{Gross Profit}_t - \Delta \text{Trade NWC}_t$$
- **Net CFO Invariant:**
  $$\text{Net CFO}_t = \text{Cash}_{\text{cust},t} - \text{Cash}_{\text{supp},t} - \text{Cash}_{\text{opex},t} - \text{Cash}_{\text{int\_paid},t} + \text{Cash}_{\text{int\_rec},t} - \text{Cash}_{\text{tax\_paid},t}$$
  $$\text{Net CFO}_t \equiv \text{NPAT}_t + \text{DA}_t - \Delta \text{NWC}_t$$

#### Investing and Financing Activities:
- **Net Cash from Investing Activities (CFI):**
  $$\text{Net CFI}_t = -\text{CapEx}_t + \text{Other CFI}_t \quad (\text{where CapEx}_t = R_t \times \text{CapEx Ratio}_t)$$
- **Net Cash from Financing Activities (CFF):**
  $$\text{Net CFF}_t = \text{New Borrowings}_t - \text{Principal Amortization}_t - \text{Dividends Paid}_t - \text{Share Repurchases}_t$$
  $$\text{Net Debt Drawdown}_t = \text{New Borrowings}_t - \text{Principal Amortization}_t$$
- **Net Change in Cash ($\Delta \text{Cash}_t$):**
  $$\Delta \text{Cash}_t = \text{Net CFO}_t + \text{Net CFI}_t + \text{Net CFF}_t$$
  $$\text{Ending Cash}_t = \text{Beginning Cash}_t + \Delta \text{Cash}_t = \text{Cash}_{t-1} + \Delta \text{Cash}_t$$

---

### 2.4 Balance Sheet (BS) Formulation & Closure Mechanics

The Balance Sheet is generated period-by-period:

#### Assets:
- **Cash & Cash Equivalents ($\text{Cash}_t$):** Taken directly from CFS ending cash ($\text{Cash}_t = \text{Ending Cash}_t$).
- **Accounts Receivable ($\text{AR}_t$):** From Working Capital Engine ($\text{AR}_t = R_t \times \frac{\text{DSO}_t}{365}$).
- **Inventory ($\text{Inv}_t$):** From Working Capital Engine ($\text{Inv}_t = \text{COGS}_t \times \frac{\text{DIO}_t}{365}$).
- **Other Current Assets ($\text{OCA}_t$):** From Working Capital Engine ($\text{OCA}_t = R_t \times \text{OCA Pct}$).
- **Total Current Assets ($\text{TCA}_t$):** $\text{TCA}_t = \text{Cash}_t + \text{AR}_t + \text{Inv}_t + \text{OCA}_t$.
- **Net PPE ($\text{PPE}_t$):** $\text{PPE}_t = \text{PPE}_{t-1} + \text{CapEx}_t - \text{DA}_t$.
- **Other Non-Current Assets ($\text{ONCA}_t$):** $\text{ONCA}_t = \text{ONCA}_{t-1}$.
- **Total Non-Current Assets ($\text{TNCA}_t$):** $\text{TNCA}_t = \text{PPE}_t + \text{ONCA}_t$.
- **Total Assets ($\text{TA}_t$):** $\text{TA}_t = \text{TCA}_t + \text{TNCA}_t$.

#### Liabilities & Shareholders' Equity:
- **Accounts Payable ($\text{AP}_t$):** From Working Capital Engine ($\text{AP}_t = \text{COGS}_t \times \frac{\text{DPO}_t}{365}$).
- **Other Current Operating Liabilities ($\text{OCL}_t$):** From Working Capital Engine ($\text{OCL}_t = \text{COGS}_t \times \text{OCL Pct}$).
- **Short-Term Debt ($\text{ST\_Debt}_t$):** $\text{ST\_Debt}_t = \min(\text{Closing Debt}_t, \text{Closing Debt}_t \times 0.35)$.
- **Total Current Liabilities ($\text{TCL}_t$):** $\text{TCL}_t = \text{AP}_t + \text{OCL}_t + \text{ST\_Debt}_t$.
- **Long-Term Debt ($\text{LT\_Debt}_t$):** $\text{LT\_Debt}_t = \text{Closing Debt}_t - \text{ST\_Debt}_t$.
- **Total Debt ($\text{Debt}_t$):** From Debt Schedule Engine ($\text{Debt}_t = \text{ST\_Debt}_t + \text{LT\_Debt}_t$).
- **Total Liabilities ($\text{TL}_t$):** $\text{TL}_t = \text{AP}_t + \text{OCL}_t + \text{Debt}_t$.
- **Contributed Capital ($\text{Cap}_t$):** $\text{Cap}_t = \text{Cap}_{t-1} - \text{Share Repurchases}_t$.
- **Retained Earnings ($\text{RE}_t$):** $\text{RE}_t = \text{RE}_{t-1} + \text{NPAT}_t - \text{Dividends Paid}_t$.
- **Total Shareholders' Equity ($\text{TE}_t$):** $\text{TE}_t = \text{Cap}_t + \text{RE}_t$.
- **Total Liabilities & Equity:** $\text{TL\&E}_t = \text{TL}_t + \text{TE}_t$.

#### Balance Invariant Check:
$$\text{Difference}_t = \text{TA}_t - \text{TL\&E}_t = (\text{TA}_t - \text{TL}_t) - \text{TE}_t = \text{Net Assets}_t - \text{Total Equity}_t$$
$$\text{is\_balanced}_t = \left( |\text{Difference}_t| < 1.0 \right) \lor \left( \frac{|\text{Difference}_t|}{\max(\text{TA}_t, 1.0)} < 10^{-5} \right)$$

---

## 3. Requirement R2: Working Capital Days & Net Working Capital (NWC) Analyzer

### 3.1 Mathematical Activity Ratios (DSO, DIO, DPO, CCC)

Working capital efficiency ratios determine how long cash is tied up in operating activities.

| Metric | Symbol | Mathematical Formula | Economic Interpretation |
|---|---|---|---|
| **Days Sales Outstanding (Debtor Days)** | $\text{DSO}$ | $\text{DSO} = \frac{\text{Accounts Receivable}}{\text{Revenue}} \times 365$ | Average number of days required to collect customer receivables. |
| **Days Inventory Outstanding (Inventory Days)** | $\text{DIO}$ | $\text{DIO} = \frac{\text{Inventory}}{\text{COGS}} \times 365$ | Average days inventory is held before being converted into sales. |
| **Days Payables Outstanding (Creditor Days)** | $\text{DPO}$ | $\text{DPO} = \frac{\text{Accounts Payable}}{\text{COGS}} \times 365$ | Average days company takes to settle trade obligations with suppliers. |
| **Cash Conversion Cycle** | $\text{CCC}$ | $\text{CCC} = \text{DSO} + \text{DIO} - \text{DPO}$ | Net duration (days) from cash outlay for raw materials to cash collection. |

---

### 3.2 NWC Aggregates & Balance Sheet Connection

1. **Trade / Operating Working Capital (OWC):**
   $$\text{OWC}_t = \text{AR}_t + \text{Inv}_t - \text{AP}_t$$
2. **Total Operating Net Working Capital (NWC):**
   $$\text{NWC}_t = (\text{AR}_t + \text{Inv}_t + \text{OCA}_t) - (\text{AP}_t + \text{OCL}_t)$$
3. **Change in Net Working Capital ($\Delta \text{NWC}_t$):**
   $$\Delta \text{NWC}_t = \text{NWC}_t - \text{NWC}_{t-1} = (\Delta \text{AR}_t + \Delta \text{Inv}_t + \Delta \text{OCA}_t) - (\Delta \text{AP}_t + \Delta \text{OCL}_t)$$

---

### 3.3 Direct Cash Flow Conversion Equations

The working capital engine provides the exact mathematical bridges between accrual accounting revenues/expenses and actual cash transactions:

$$\begin{aligned}
\text{Cash Collected from Customers}_t &= \text{Revenue}_t - \Delta \text{AR}_t \\
\text{Cash Paid to Suppliers}_t &= \text{COGS}_t + \Delta \text{Inv}_t - \Delta \text{AP}_t \\
\text{Cash Paid for OPEX}_t &= \text{SGA}_t + \Delta \text{OCA}_t - \Delta \text{OCL}_t
\end{aligned}$$

#### Algebraic Identity Verification:
$$\begin{aligned}
\text{Gross Operating Cash Flow}_t &= \text{Cash Collected}_t - \text{Cash Paid to Suppliers}_t \\
&= (\text{Revenue}_t - \Delta \text{AR}_t) - (\text{COGS}_t + \Delta \text{Inv}_t - \Delta \text{AP}_t) \\
&= (\text{Revenue}_t - \text{COGS}_t) - (\Delta \text{AR}_t + \Delta \text{Inv}_t - \Delta \text{AP}_t) \\
&= \text{Gross Profit}_t - \Delta \text{Trade NWC}_t \quad \blacksquare
\end{aligned}$$

---

### 3.4 Sector Priors, Mean Reversion Dynamics & Industry Benchmarks

When projecting working capital across 5 years, efficiency days can either stay constant or mean-revert towards industry benchmark standards:

$$\text{DSO}_t = \text{DSO}_{t-1} + \lambda \times (\text{DSO}_{\text{target}} - \text{DSO}_{t-1})$$
$$\text{DIO}_t = \text{DIO}_{t-1} + \lambda \times (\text{DIO}_{\text{target}} - \text{DIO}_{t-1})$$
$$\text{DPO}_t = \text{DPO}_{t-1} + \lambda \times (\text{DPO}_{\text{target}} - \text{DPO}_{t-1})$$
$$\text{CCC}_t = \text{DSO}_t + \text{DIO}_t - \text{DPO}_t$$
*(where $\lambda \in [0.0, 1.0]$ is the `mean_revert_speed` parameter, default $0.0$ for constant historical efficiency).*

#### Calibrated Sector Priors for the Vietnamese Market:

| ICB Sector Code | Sector Name | Target DSO | Target DIO | Target DPO | Target CCC | OCA % Rev | OCL % COGS | Is Financial |
|---|---|---|---|---|---|---|---|---|
| **VNCONS / 3000** | Consumer Staples | 30.0 | 65.0 | 45.0 | 50.0 | 5.0% | 8.0% | `False` |
| **VNCOND / 5000** | Consumer Discretionary | 20.0 | 70.0 | 55.0 | 35.0 | 4.0% | 7.0% | `False` |
| **5300 / RETAIL** | Retail Trade | 15.0 | 85.0 | 60.0 | 40.0 | 4.0% | 7.0% | `False` |
| **VNMAT / 1700** | Basic Materials & Steel | 25.0 | 95.0 | 45.0 | 75.0 | 6.0% | 6.0% | `False` |
| **VNIND / 2700** | Industrials & Construction| 65.0 | 75.0 | 50.0 | 90.0 | 8.0% | 10.0% | `False` |
| **VNIT / 9500** | Technology & Telecom | 70.0 | 15.0 | 45.0 | 40.0 | 7.0% | 9.0% | `False` |
| **VNREAL / 8600** | Real Estate Developers | 90.0 | 365.0 | 60.0 | 395.0 | 12.0% | 18.0% | `False` |
| **VNENE / 0500** | Energy & Oil/Gas | 35.0 | 30.0 | 40.0 | 25.0 | 5.0% | 6.0% | `False` |
| **VNUTI / 7500** | Utilities (Power/Water) | 45.0 | 20.0 | 40.0 | 25.0 | 4.0% | 5.0% | `False` |
| **VNHEAL / 4500** | Healthcare & Pharma | 60.0 | 90.0 | 45.0 | 105.0 | 6.0% | 6.0% | `False` |
| **VNFIN / 8300** | Financials (Banks/Sec) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0% | 0.0% | `True` |
| **DEFAULT** | General Economy Prior | 45.0 | 60.0 | 40.0 | 65.0 | 5.0% | 7.0% | `False` |

---

### 3.5 Negative CCC Handling & Zero-Division Safeguards

1. **Negative Cash Conversion Cycle (Retail Business Models):**
   - In modern retail companies (e.g. MWG, WinCommerce, Amazon-like models), customers pay immediately in cash ($\text{DSO} \approx 5 \text{ days}$), inventory turns rapidly ($\text{DIO} \approx 45 \text{ days}$), while suppliers grant extended payment terms ($\text{DPO} \approx 90 \text{ days}$).
   - This results in $\text{CCC} = 5 + 45 - 90 = -40 \text{ days}$, creating **negative working capital** ($\text{Trade NWC} < 0$).
   - **Architectural Safeguard:** The engine permits negative CCC and negative NWC as economically valid states, recognizing them as an interest-free source of operating financing rather than an error condition.
2. **Division by Zero & Micro-Revenue Guards:**
   - If $\text{Revenue} \le 0$ or $\text{COGS} \le 0$, raw days calculations $\frac{\text{AR}}{\text{Rev}} \times 365$ would produce `#DIV/0!`, `NaN`, or $+\infty$.
   - **Hierarchy of Fallbacks:**
     1. Fallback to sector prior benchmark ($\text{DSO}_{\text{sector}}$).
     2. If sector is unrecognized, fallback to `DEFAULT` benchmark (45 days).
   - **Days Clamping:** Any raw ratio output is clamped within $[0.0, 1095.0]$ days (max 3 years) to prevent distorted micro-revenues from creating astronomical working capital spikes.

---

### 3.6 Financial Sector Isolation (Banks, Insurance, Securities)

Financial institutions (e.g., VCB, TCB, MBB, SSI, BVH) operate on deposit intermediation, credit portfolios, and underwriting reserves. Traditional working capital metrics ($\text{DSO}$, $\text{DIO}$, $\text{DPO}$, $\text{CCC}$, $\text{NWC}$) are economically meaningless and methodologically invalid for banks.

**Isolation Rules:**
- Ticker check: If symbol is in the 42-ticker financial bank/brokerage set, or `is_financial_sector == True`, or ICB $\in \{8300, 8500, 8700, \text{VNFIN}, \text{VNBNK}, \text{VNSEC}, \text{VNINS}\}$.
- Automatic assignment: $\text{DSO} = 0$, $\text{DIO} = 0$, $\text{DPO} = 0$, $\text{CCC} = 0$, $\text{Inventory} = 0$, $\text{NWC} = 0$, $\Delta \text{NWC} = 0$.
- Downstream valuation safely switches to Bank Equity Cash Flow / Residual Income Model rather than traditional DCF.

---

## 4. Requirement R4: Capital Allocation & Debt Schedule Engine

### 4.1 Debt Amortization Schedule & Roll-Forward Mechanics

The debt sub-engine models multi-period debt evolution and financing flows:

```
  Debt_Opening_t ──► (-) Principal Amortization_t ──┐
                 ──► (+) New Borrowings_t          ──┴──► Debt_Closing_t ──► Average_Debt_t
```

1. **Opening Debt:**
   $$\text{Debt}_{\text{opening},t} = \begin{cases} \text{Base Debt}, & t = 1 \\ \text{Debt}_{\text{closing},t-1}, & t > 1 \end{cases}$$
2. **Principal Amortization:**
   $$\text{Principal Amortization}_t = \min\left(\text{Debt}_{\text{opening},t}, \, \text{Debt}_{\text{opening},t} \times r_{\text{amort}}\right) \quad (r_{\text{amort}} \approx 20\% \text{ default})$$
3. **New Borrowings (CapEx Debt Financing):**
   $$\text{New Borrowings}_t = \max\left(0, \, \text{CapEx}_t \times r_{\text{debt\_capex}}\right) \quad (r_{\text{debt\_capex}} \approx 40\% \text{ default})$$
4. **Closing Debt Identity:**
   $$\text{Debt}_{\text{closing},t} = \max\left(0, \, \text{Debt}_{\text{opening},t} + \text{New Borrowings}_t - \text{Principal Amortization}_t\right)$$
5. **Midpoint Average Debt Balance:**
   $$\text{Average Debt}_t = \frac{\text{Debt}_{\text{opening},t} + \text{Debt}_{\text{closing},t}}{2}$$
6. **Debt Breakdown:**
   $$\text{ST Debt}_t = \min(\text{Debt}_{\text{closing},t}, \, \text{Debt}_{\text{closing},t} \times 0.35)$$
   $$\text{LT Debt}_t = \max(0, \, \text{Debt}_{\text{closing},t} - \text{ST Debt}_t)$$
7. **Net Debt Drawdown (CFF Financing Line):**
   $$\text{Net Debt Drawdown}_t = \text{New Borrowings}_t - \text{Principal Amortization}_t$$

---

### 4.2 Aswath Damodaran Synthetic Credit Rating & Credit Spread Engine

In emerging markets like Vietnam, most non-financial firms lack international credit ratings from Moody's or S&P. Damodaran's **Synthetic Credit Rating Framework** provides an objective market standard by mapping the **Interest Coverage Ratio (ICR)** to a synthetic credit rating and credit default spread.

$$\text{ICR}_t = \frac{\text{EBIT}_t}{\max(\text{Interest Expense}_t, \, 1.0)}$$

#### Boundary Gating:
- If $\text{EBIT}_t \le 0 \implies \text{ICR} = -1.0 \implies \text{Rating} = \text{"D"}$, Spread $= 1250 \text{ bps}$.
- If $\text{Interest Expense}_t \le 0 \implies \text{ICR} = 100.0 \implies \text{Rating} = \text{"AAA"}$, Spread $= 65 \text{ bps}$.

#### Calibrated Damodaran Rating & Spread Curves:

| Rating | Minimum ICR (Large Cap > 5,000B VND) | Minimum ICR (Small/Mid Cap $\le$ 5,000B VND) | Spread over $R_f$ (bps) | Spread (Decimal) | Typical Pre-Tax $K_d$ ($R_f=5.0\%$) |
|---|---|---|---|---|---|
| **AAA** | $\ge 8.50$ | $\ge 12.50$ | 65 | 0.0065 | 5.65% |
| **AA** | $\ge 6.50$ | $\ge 9.50$ | 90 | 0.0090 | 5.90% |
| **A+** | $\ge 5.50$ | $\ge 7.50$ | 115 | 0.0115 | 6.15% |
| **A** | $\ge 4.25$ | $\ge 6.00$ | 135 | 0.0135 | 6.35% |
| **A-** | $\ge 3.00$ | $\ge 4.50$ | 160 | 0.0160 | 6.60% |
| **BBB** *(Inv. Grade)* | $\ge 2.50$ | $\ge 4.00$ | 210 | 0.0210 | 7.10% |
| **BB+** | $\ge 2.25$ | $\ge 3.50$ | 285 | 0.0285 | 7.85% |
| **BB** | $\ge 2.00$ | $\ge 3.00$ | 340 | 0.0340 | 8.40% |
| **B+** | $\ge 1.75$ | $\ge 2.50$ | 425 | 0.0425 | 9.25% |
| **B** | $\ge 1.50$ | $\ge 2.00$ | 525 | 0.0525 | 10.25% |
| **B-** *(Covenant Dist.)* | $\ge 1.25$ | $\ge 1.50$ | 650 | 0.0650 | 11.50% |
| **CCC** | $\ge 0.80$ | $\ge 1.25$ | 850 | 0.0850 | 13.50% |
| **CC** | $\ge 0.50$ | $\ge 0.80$ | 1000 | 0.1000 | 15.00% |
| **D** *(Default/Loss)* | $< 0.50$ | $< 0.80$ | 1250 | 0.1250 | 17.50% |

---

### 4.3 Pre-Tax and After-Tax Cost of Debt ($K_d$) & WACC Integration

1. **Pre-Tax Cost of Debt ($K_{d,\text{pre}}$):**
   $$K_{d,\text{pre},t} = R_f + \text{Spread}(\text{Rating}_t) \quad (R_f = 5.0\% \text{ default for Vietnam 10Y Bond})$$
2. **After-Tax Cost of Debt ($K_{d,\text{after}}$):**
   $$K_{d,\text{after},t} = K_{d,\text{pre},t} \times (1 - T) \quad (T = 20.0\% \text{ default corporate tax rate})$$
3. **Interest Expense Calculation:**
   $$\text{Interest Expense}_t = \text{Average Debt}_t \times K_{d,\text{pre},t}$$
4. **WACC Integration Linkage:**
   $$\text{WACC}_t = \left( \frac{\text{Equity}}{\text{Debt} + \text{Equity}} \times K_{e,t} \right) + \left( \frac{\text{Debt}}{\text{Debt} + \text{Equity}} \times K_{d,\text{after},t} \right)$$
   *(where $K_e$ is computed via the 5-Factor Vietnam CAPM).*

---

### 4.4 Fixed-Point Iterative Convergence Algorithm

A classic circularity exists in financial modeling:
$$\text{Average Debt} \longrightarrow \text{Interest Expense} \longrightarrow \text{EBT / EBIT} \longrightarrow \text{ICR} \longrightarrow K_d(\text{ICR}) \longrightarrow \text{Interest Expense}$$

To prevent Excel circular reference errors (`#CIRC!`) or numerical oscillation, the engine implements a **Fixed-Point Iteration Algorithm** that converges in $\le 5$ iterations:

```python
# Fixed-Point Iteration Solver
spread = 0.0210  # Initial seed: BBB rating spread (210 bps)
rating = "BBB"
for _ in range(5):
    kd_pre = rf + spread
    trial_interest = avg_debt * kd_pre
    trial_icr = ebit / max(trial_interest, 1.0)
    new_rating, new_spread = calculate_synthetic_rating(trial_icr, is_large_cap)
    if new_rating == rating and math.isclose(new_spread, spread, abs_tol=1e-5):
        break
    rating = new_rating
    spread = new_spread

kd_pre = rf + spread
kd_after = kd_pre * (1.0 - tax_rate)
interest_expense = avg_debt * kd_pre
```

---

### 4.5 Solvency-Guarded Capital Allocation & Dividend Waterfall

To reflect Vietnamese corporate law (Enterprise Law 2020) and institutional banking covenant clauses, the engine applies a **Solvency-Guarded Capital Allocation Waterfall**:

```
                         NPAT_t
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
        NPAT <= 0                   NPAT > 0
             │                           │
    [DIVIDEND FREEZE]                    ▼
     Dividends = 0.0            Debt Covenant Check
     Repurchases = 0.0                   │
                           ┌─────────────┴─────────────┐
                           ▼                           ▼
                     ICR < 1.20                   ICR >= 1.20
                           │                           │
                  [COVENANT BREACH]            [SOLVENT DISTRIBUTION]
                   Dividends = 0.0              Dividends = min(NPAT, NPAT * Payout_Ratio)
                   Repurchases = 0.0            Repurchases = NPAT * Repurchase_Ratio
```

1. **Statutory Profitability Guard:** Dividends can only be distributed from positive net profits after tax. If $\text{NPAT}_t \le 0 \implies \text{Dividends}_t = 0.0$.
2. **Debt Covenant Firewall:** If $\text{Average Debt}_t > 0$ and $\text{ICR}_t < 1.20$ (or operating loss with active debt), a debt covenant breach is triggered:
   - `is_covenant_breached = True`
   - `is_dividend_curtailed = True`
   - `curtailment_reason = "COVENANT_BREACH_ICR_BELOW_1_2"`
   - `dividends_paid = 0.0`, `share_repurchases = 0.0`
3. **Solvent Capital Distribution:**
   $$\text{Dividends Paid}_t = \min\left(\text{NPAT}_t, \, \text{NPAT}_t \times \text{Payout Ratio}\right)$$
   $$\text{Share Repurchases}_t = \begin{cases} \text{NPAT}_t \times \text{Repurchase Ratio}, & \text{if enabled and } \text{ICR}_t \ge 1.20 \\ 0.0, & \text{otherwise} \end{cases}$$
   $$\text{Total Capital Returned}_t = \text{Dividends Paid}_t + \text{Share Repurchases}_t$$

---

### 4.6 Intrinsic Valuation Integration (FCFF, FCFE, Owner's Earnings, DDM)

The 3-way engine directly produces dynamic cash flow streams used by the 22 valuation models:

#### 1. Free Cash Flow to Firm (FCFF / Unlevered Free Cash Flow):
$$\text{NOPAT}_t = \text{EBIT}_t \times (1 - T)$$
$$\text{FCFF}_t = \text{NOPAT}_t + \text{D\&A}_t - \text{CapEx}_t - \Delta \text{NWC}_t$$
- Used in McKinsey 2-Stage DCF, APV, and WACC enterprise discounting.

#### 2. Free Cash Flow to Equity (FCFE / Levered Free Cash Flow):
$$\text{FCFE}_t = \text{Net CFO}_t - \text{CapEx}_t + \text{Net Debt Drawdown}_t$$
$$\text{FCFE}_t = (\text{NPAT}_t + \text{D\&A}_t - \Delta \text{NWC}_t) - \text{CapEx}_t + (\text{New Borrowings}_t - \text{Principal Amortization}_t)$$
- Used in Equity Cash Flow models and levered DCF discounting at Cost of Equity ($K_e$).

#### 3. Warren Buffett Owner's Earnings:
$$\text{Owner's Earnings}_t = \text{NPAT}_t + \text{D\&A}_t - \text{Maintenance CapEx}_t - \Delta \text{NWC}_t \quad (\text{Maintenance CapEx} \approx 75\% \text{ of CapEx})$$
- Used in Buffett Owner's Earnings valuation model.

#### 4. Dividend Discount Model (DDM / H-Model):
$$\text{Intrinsic Equity Value} = \sum_{t=1}^{5} \frac{\text{Dividends Paid}_t}{(1 + K_e)^t} + \frac{\text{Dividends}_5 \times (1 + g_{\text{term}})}{(K_e - g_{\text{term}}) \times (1 + K_e)^5}$$
- Directly utilizes the solvency-guarded `dividends_paid` vector from the debt schedule engine.

---

## 5. Comprehensive Data Schemas & API Contracts

### 5.1 ThreeStatementForecastResult Schema

```typescript
interface ThreeStatementForecastResult {
  symbol: string;                       // e.g. "HPG"
  company_name: string;                 // e.g. "Tập đoàn Hòa Phát"
  sector: string;                       // e.g. "VNMAT"
  is_financial_sector: boolean;         // true if Bank/Insurance/Securities
  start_year: number;                   // e.g. 2026
  forecast_years: number[];             // [2026, 2027, 2028, 2029, 2030]

  income_statement: {
    years: number[];                    // [2026, 2027, 2028, 2029, 2030]
    revenue: number[];                  // [154000e9, 169400e9, ...]
    revenue_growth: number[];           // [0.10, 0.088, ...]
    cogs: number[];                     // [126280e9, 138908e9, ...]
    gross_profit: number[];             // [27720e9, 30492e9, ...]
    gross_margin: number[];             // [0.18, 0.18, ...]
    sga_expense: number[];              // [8240e9, 8760e9, ...]
    ebitda: number[];                   // [19480e9, 21732e9, ...]
    depreciation_amortization: number[];// [6800e9, 6944e9, ...]
    ebit: number[];                     // [12680e9, 14788e9, ...]
    ebit_margin: number[];              // [0.0823, 0.0873, ...]
    interest_expense: number[];         // [4320e9, 4110e9, ...]
    interest_income: number[];          // [500e9, 580e9, ...]
    ebt: number[];                      // [8860e9, 11258e9, ...]
    tax_expense: number[];              // [1772e9, 2251.6e9, ...]
    effective_tax_rate: number[];       // [0.20, 0.20, ...]
    npat: number[];                     // [7088e9, 9006.4e9, ...]
    net_margin: number[];               // [0.0460, 0.0531, ...]
  };

  balance_sheet: {
    years: number[];
    cash: number[];                     // [26400e9, 29150e9, ...]
    cash_and_equivalents: number[];     // alias
    accounts_receivable: number[];      // [10547e9, 11602e9, ...]
    inventory: number[];                // [32890e9, 36179e9, ...]
    other_current_assets: number[];     // [9240e9, 10164e9, ...]
    total_current_assets: number[];     // [79077e9, 87095e9, ...]
    net_ppe: number[];                  // [87440e9, 90696e9, ...]
    other_non_current_assets: number[]; // [15000e9, 15000e9, ...]
    total_non_current_assets: number[]; // [102440e9, 105696e9, ...]
    total_assets: number[];             // [181517e9, 192791e9, ...]
    accounts_payable: number[];         // [15560e9, 17116e9, ...]
    other_current_liabilities: number[];// [7576e9, 8334e9, ...]
    short_term_debt: number[];          // [21700e9, 20300e9, ...]
    total_current_liabilities: number[];// [44836e9, 45750e9, ...]
    long_term_debt: number[];           // [40300e9, 37700e9, ...]
    total_debt: number[];               // [62000e9, 58000e9, ...]
    total_liabilities: number[];        // [85136e9, 83450e9, ...]
    contributed_capital: number[];      // [52500e9, 52500e9, ...]
    retained_earnings: number[];        // [43881e9, 50841e9, ...]
    total_equity: number[];             // [96381e9, 103341e9, ...]
    total_liabilities_and_equity: number[]; // [181517e9, 192791e9, ...]
    balance_check_difference: number[]; // [0.0, 0.0, 0.0, 0.0, 0.0]
    net_assets_minus_equity: number[];  // alias
    is_balanced: boolean[];             // [true, true, true, true, true]
  };

  cash_flow_statement: {
    years: number[];
    cash_from_customers: number[];      // [153453e9, 168345e9, ...]
    cash_to_suppliers: number[];        // [121624e9, 133642e9, ...]
    cash_for_opex: number[];            // [7984e9, 8482e9, ...]
    cash_interest_paid: number[];       // [4320e9, 4110e9, ...]
    cash_interest_received: number[];   // [500e9, 580e9, ...]
    cash_tax_paid: number[];            // [1772e9, 2251.6e9, ...]
    gross_operating_cash_flow: number[];// [31829e9, 34703e9, ...]
    net_cfo: number[];                  // [18253e9, 20439.4e9, ...]
    operating_cash_flow: number[];      // alias
    capex: number[];                    // [9240e9, 10164e9, ...]
    other_cfi: number[];                // [0.0, 0.0, ...]
    net_cfi: number[];                  // [-9240e9, -10164e9, ...]
    investing_cash_flow: number[];      // alias
    new_debt_drawdowns: number[];       // [3696e9, 4065.6e9, ...]
    principal_debt_repayments: number[];// [13600e9, 12400e9, ...]
    net_debt_drawdown: number[];        // [-9904e9, -8334.4e9, ...]
    dividends_paid: number[];           // [2126.4e9, 2701.9e9, ...]
    share_repurchases: number[];        // [0.0, 0.0, ...]
    net_cff: number[];                  // [-12030.4e9, -11036.3e9, ...]
    financing_cash_flow: number[];      // alias
    net_change_in_cash: number[];       // [-3017.4e9, -760.9e9, ...]
    delta_cash: number[];               // alias
    beginning_cash: number[];           // [25000e9, 21982.6e9, ...]
    ending_cash: number[];              // [21982.6e9, 21221.7e9, ...]
    free_cash_flow_to_firm: number[];   // [12650e9, 14210e9, ...]
    fcff: number[];                     // alias
    free_cash_flow_to_equity: number[]; // [-891e9, 1941e9, ...]
    fcfe: number[];                     // alias
    buffett_owners_earnings: number[];  // [10340e9, 11670e9, ...]
  };

  working_capital_schedule: Array<Record<string, any>>;
  debt_schedule: Array<Record<string, any>>;

  liquidity_distress_check: {
    is_distressed: boolean;             // false
    has_negative_cash: boolean;         // false
    distressed_years: number[];         // []
    min_cash_balance: number;           // 21221.7e9
    max_cash_shortfall: number;         // 0.0
    dilution_risk_pct: number;          // 0.0
    mos_penalty_pct: number;            // 0.0
    summary_assessment: string;         // "HEALTHY"
    diagnostic_messages: string[];      // []
  };

  all_years_balanced: boolean;          // true
  max_balance_difference: number;       // 0.0
  summary_metrics: Record<string, any>;
}
```

---

## 6. Features Discovered Table

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|---|---|---|---|---|---|---|
| 1 | R1: 3-Way Engine | **5-Year Synchronized Forecast** | Generates full P&L, BS, and Direct Method CFS for $t \in [1, 5]$. | Baseline dict, revenue growth series, margin series | `ThreeStatementForecastResult` | Clamps inputs, falls back to sector defaults | Codebase / Spec Inspection |
| 2 | R1: 3-Way Engine | **Strict Balance Sheet Closure** | Enforces $|\text{TA} - (\text{TL} + \text{TE})| < 10^{-5}$ without plug lines. | P&L and CFS flows | `BalanceSheetForecast.is_balanced` | Sets `is_balanced=False` if discrepancy $\ge 1.0$ and $\ge 10^{-5}$ | Mathematical Invariant Proof |
| 3 | R1: 3-Way Engine | **Direct Method CFO Reconciliation** | Reconciles customer/supplier cash to $\text{NPAT} + \text{D\&A} - \Delta \text{NWC}$. | Revenue, COGS, SGA, $\Delta \text{AR}, \Delta \text{Inv}, \Delta \text{AP}$ | `net_cfo`, `gross_operating_cash_flow` | Invariant guaranteed by additivity proof | Codebase / `three_statement_engine.py` |
| 4 | R1: 3-Way Engine | **Statement Link 1 (NPAT $\to$ RE)** | Rolls forward Retained Earnings via $\text{RE}_t = \text{RE}_{t-1} + \text{NPAT}_t - \text{Div}_t$. | NPAT, prior RE, dividends | `retained_earnings` | If NPAT $\le 0$, dividends frozen, RE decreases | `three_statement_engine.py` |
| 5 | R1: 3-Way Engine | **Statement Link 2 ($\Delta \text{Cash} \to \text{Cash}$)** | Directly links ending CFS cash to Balance Sheet cash asset line. | Prior cash, Net CFO, CFI, CFF | `bs_cash`, `ending_cash` | Cash permitted to go negative to signal distress | `three_statement_engine.py` |
| 6 | R2: Working Capital | **Efficiency Days Analyzer** | Computes DSO, DIO, DPO, and CCC from historical statements. | Rev, COGS, AR, Inv, AP | `dso`, `dio`, `dpo`, `ccc` | Safe division against 0/NaN, clamped $[0, 1095]$ | `working_capital_engine.py` |
| 7 | R2: Working Capital | **Mean-Reverting Schedule** | Projects 5Y NWC with geometric speed $\lambda$ towards sector priors. | Base days, $\lambda \in [0, 1]$, sector | `WorkingCapitalSchedulePeriod[]` | If $\lambda=0$, maintains constant historical days | `working_capital_engine.py` |
| 8 | R2: Working Capital | **Negative CCC Acceptance** | Allows negative CCC for retailers (e.g. MWG) generating negative OWC. | Retailer financials | Negative `ccc`, negative `trade_nwc` | Preserves valid retail cash model without error | `test_working_capital_engine.py` |
| 9 | R2: Working Capital | **Financial Sector Isolation** | Zeroes out DSO/DIO/DPO/NWC for 42 banks, insurers, and brokerages. | ICB code or ticker symbol | $\text{DSO}=\text{DIO}=\text{DPO}=\text{NWC}=0$ | Gated safely, routes to Bank Equity Cash Flow | `working_capital_engine.py` |
| 10 | R2: Working Capital | **Direct Cash Adjustments** | Calculates Cash from Customers ($R - \Delta \text{AR}$) and Paid Suppliers. | Schedule periods, Rev, COGS | `cash_from_customers`, `cash_to_suppliers` | Cross-validated against Gross Profit $-\Delta \text{OWC}$ | `working_capital_engine.py` |
| 11 | R4: Debt Schedule | **Debt Amortization Schedule** | Tracks Opening Debt, Amortization, CapEx Borrowings, Closing Debt. | Base debt, CapEx, policy rates | `DebtSchedulePeriod[]` | Clamped amortization $[0, \text{Opening Debt}]$ | `debt_capital_schedule_engine.py` |
| 12 | R4: Debt Schedule | **Damodaran Synthetic Ratings** | Maps Interest Coverage Ratio (ICR) to AAA..D ratings and spreads. | $\text{ICR} = \text{EBIT} / \text{Interest Expense}$ | Synthetic rating, credit spread bps | EBIT $\le 0 \implies \text{"D"}$, Int $\le 0 \implies \text{"AAA"}$ | `debt_capital_schedule_engine.py` |
| 13 | R4: Debt Schedule | **Fixed-Point Iteration Solver** | Resolves circular feedback between Debt, Interest, and $K_d(\text{ICR})$. | Base debt, EBIT, Rf, Tax | Converged pre-tax $K_d$, Interest Expense | Converges in $\le 5$ iterations, zero circular error | `debt_capital_schedule_engine.py` |
| 14 | R4: Debt Schedule | **Solvency Dividend Firewall** | Blocks dividends and buybacks if $\text{NPAT} \le 0$ or $\text{ICR} < 1.20$. | NPAT, ICR, policy | `dividends_paid=0.0`, `is_covenant_breached` | Sets `curtailment_reason` diagnostic string | `debt_capital_schedule_engine.py` |
| 15 | R4: Debt Schedule | **Dual Rating Curves** | Applies separate ICR tables for Large-Cap (> 5,000B VND) vs Small-Cap. | Market Cap in VND | Adjusted ICR lookup thresholds | Automatically selects correct Damodaran table | `debt_capital_schedule_engine.py` |
| 16 | R4: Valuation Links | **Intrinsic Cash Flow Generators**| Outputs dynamic FCFF, FCFE, Owner's Earnings, and DDM streams. | 3-Way statement collections | `fcff`, `fcfe`, `buffett_oe`, `dividends_paid` | Feeds into 22 valuation models seamlessly | `three_statement_engine.py` |
| 17 | R3: Distress Firewall | **Liquidity Distress Diagnostic** | Detects projected cash deficits ($\text{Cash}_t < 0$) and assigns MOS penalties.| Ending cash time series | `LiquidityDistressCheck` | Flags `is_distressed=True`, adds +5%..+15% MOS | `three_statement_engine.py` |

---

## 7. Edge Cases & Adversarial Scenarios Table

| # | Feature | Input / Condition | Observed Behavior | Handling / Safeguard Mechanism |
|---|---|---|---|---|
| 1 | **Working Capital Days** | `Revenue = 0` or `COGS = 0` (Startup / Zero Activity) | Raw division would yield `ZeroDivisionError` / `NaN`. | `safe_div` catches zero denominator, returns calibrated sector prior benchmark (`SECTOR_WC_PRIORS`). |
| 2 | **Working Capital Days** | Microscopic Revenue (`Revenue = 1.0`, `AR = 10,000.0`) | Raw formula yields $\text{DSO} = 3,650,000 \text{ days}$. | Clamped within $[0.0, 1095.0]$ days (max 3 years) via `clamp()` function. |
| 3 | **Working Capital Days** | Negative Accounts Receivable or Payables (Dirty Data) | Negative asset balances distort accounting. | Sanitized to $\ge 0.0$ via `sanitize_float` and `max(0.0, val)`. |
| 4 | **Working Capital Days** | Negative Gross Margin ($\text{COGS} > \text{Revenue}$, Loss Leader) | Gross Loss condition. | Computes valid positive DSO and DIO based on respective revenue and COGS bases; $\text{CCC}$ reflects operating stretch. |
| 5 | **Working Capital Days** | Retailer with Negative CCC (e.g. MWG: $\text{DSO}=6, \text{DIO}=46, \text{DPO}=96$) | $\text{CCC} = -44 \text{ days} < 0$. | Preserved as valid negative operating working capital without artificially clamping to zero. |
| 6 | **Working Capital Days** | Financial Institution (Bank `VCB`, Brokerage `SSI`, Insurer `BVH`) | Industrial NWC metrics are inapplicable. | Financial sector detector overrides $\text{DSO}=\text{DIO}=\text{DPO}=\text{NWC}=0.0$, sets `is_financial_sector=True`. |
| 7 | **Debt & Rating Engine** | Debt-Free Firm ($\text{Total Debt} = 0$, $\text{Interest Expense} = 0$) | Raw $\text{ICR} = \text{EBIT} / 0 \implies \text{ZeroDivisionError}$. | Guarded: returns $\text{ICR} = 100.0$, maps to $\text{"AAA"}$ rating, lowest spread (65 bps), $\text{Interest Expense} = 0.0$. |
| 8 | **Debt & Rating Engine** | Operating Loss ($\text{EBIT} \le 0$) with Active Debt Burden | Negative ICR would fail lookup table. | Guarded: returns $\text{ICR} = -1.0$, maps to $\text{"D"}$ rating (Default), maximum spread (1250 bps), covenants breached. |
| 9 | **Capital Allocation** | Solvency Breach ($\text{ICR} < 1.20$, Distressed Firm) | Target dividend payout is $30\%$. | Dividend firewall freezes payouts: `dividends_paid = 0.0`, `is_covenant_breached = True`, cash retained. |
| 10 | **Capital Allocation** | Negative Net Profit ($\text{NPAT} < 0$) | Target dividend payout is $30\%$. | Enterprise Law 2020 guard triggers: `dividends_paid = 0.0`, `curtailment_reason = "NEGATIVE_OR_ZERO_NPAT"`. |
| 11 | **Debt Schedule** | Rapid Principal Repayment ($\text{Amortization Rate} > 100\%$) | Closing debt could become negative. | Principal amortization is clamped: $\text{Amort} = \min(\text{Opening Debt}, \, \text{Opening Debt} \times r_{\text{amort}})$, $\text{Debt} \ge 0$. |
| 12 | **3-Way Forecast** | Severe Operating Distress ($\text{NVL}$-like debt burn) | Projected ending cash falls below zero ($\text{Cash}_t < 0$). | Balance sheet remains strictly balanced; `LiquidityDistressCheck` triggers with $+10\%$ MOS penalty and dilution haircut. |
| 13 | **3-Way Forecast** | Dirty String Inputs (`"15,000.0"`, `"--"`, `"N/A"`, `None`, `NaN`) | Type conversion error in calculations. | `sanitize_float` strips commas, spaces, currency symbols, and maps invalid strings to safe default fallbacks. |
| 14 | **3-Way Forecast** | High CapEx Growth Firm ($\text{CapEx} = 30\% \text{ of Rev}$) | D&A roll-forward could lag PPE additions. | Net PPE rolls forward accurately ($\text{PPE}_t = \text{PPE}_{t-1} + \text{CapEx}_t - \text{DA}_t$); Balance Sheet remains 100% closed. |
| 15 | **3-Way Forecast** | Zero Growth Steady State ($\text{Growth} = 0\%$, Constant Margins) | Stationary equilibrium check. | $\Delta \text{NWC} = 0.0$, $\text{Net CFO} = \text{NPAT} + \text{D\&A}$, balance sheet balances to $0.00000$ difference. |

---

## 8. Implementation Recommendations & Verification Guidance

1. **Maintain Double-Entry Additivity:** When extending or introducing new balance sheet line items (e.g., Leases under IFRS 16 or Right-of-Use Assets), ensure corresponding cash flow lines (e.g., Lease Principal Repayment in CFF, Lease Interest in CFO) and P&L lines (Lease Depreciation) are added simultaneously to maintain the mathematical balance invariant.
2. **Preserve Pydantic Dual Contract (v1 & v2 Compatibility):** Ensure all models implement both `.to_dict()` and standard dictionary getters with fallback aliases (`cash` vs `cash_and_equivalents`, `net_cfo` vs `operating_cash_flow`).
3. **Automated Verification Command:**
   ```powershell
   pytest tests/test_three_statement_engine.py tests/test_working_capital_engine.py tests/test_debt_capital_schedule_engine.py -v
   ```
   All 39 unit, boundary, invariant, and real-world ticker integration tests must pass with 0 failures and 0 warnings.

---
*Report successfully compiled and ready for Modano Ecosystem integration.*
