# Integration and Data Flow Architecture Report: Milestone 2 Debt & Capital Schedule Engine

**Author**: `teamwork_preview_explorer_m2_2`  
**Date**: 2026-09-02  
**Target Path**: `services/debt_capital_schedule_engine.py`  
**Cross-Service Dependencies**: `services/valuation_engine.py` (M4), `services/three_statement_engine.py` (M3), `services/working_capital_engine.py` (M1)

---

## 1. Executive Summary & Problem Scope

In the Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem (`Vibecoding vnstock`), Milestone 2 introduces the **Capital Allocation & Debt Schedule Engine** (`services/debt_capital_schedule_engine.py`, Requirement R4). 

The primary objectives of this module are:
1. **Dynamic Cost of Debt ($K_d$) Determination**: Compute synthetic credit ratings ($AAA$ through $D$) and pre/after-tax cost of debt using Aswath Damodaran's Interest Coverage Ratio (ICR) tables for both Large-Cap and Small-Cap Vietnamese firms.
2. **5-Year Debt Amortization Roll-Forward**: Maintain consistent balance sheet debt trajectories (Opening Debt, Scheduled Principal Amortizations, Growth/Refinancing Borrowings, Closing Debt, and Average Debt).
3. **Solvency-Guarded Capital Allocation**: Model dividend payouts ($\text{NPAT} \times \text{Payout Ratio}$) and share repurchases subject to strict solvency and covenant constraints ($ICR \ge 1.25$, $Cash > 0$).
4. **Bilateral Integration**:
   - **Downstream to 3-Way Engine (`services/three_statement_engine.py`)**: Direct feeds for Balance Sheet debt balances, Income Statement interest expenses, and Cash Flow Statement (Direct Method) financing cash flows ($Net\_Borrowings$, $Dividends\_Paid$, $Interest\_Paid$).
   - **Upstream/Synchronized with Valuation Engine (`services/valuation_engine.py`)**: Dynamic feeding of $K_d$, capital structure weights ($W_d, W_e$), projected dividends ($D_1 \dots D_5$) into DDM (Model 22), FCFE / Equity Cash Flow (Model 17), Buffett Owner's Earnings (Model 15), and Adjusted Present Value (Model 20).

---

## 2. Investigation of `services/valuation_engine.py`

### 2.1 Damodaran Synthetic Credit Spread Tables (Lines 87-119)
`services/valuation_engine.py` defines two calibrated tables mapping Interest Coverage Ratio ($ICR = \frac{EBIT}{\text{Interest Expense}}$) to synthetic credit ratings and basis point credit spreads over the 10-year risk-free rate ($R_f = 5.0\%$):

```python
# Format: (min_icr: float, rating: str, spread_over_rf: float)
DAMODARAN_SPREAD_LARGE_CAP = [
    (8.50, "AAA", 0.0065), # 65 bps
    (6.50, "AA",  0.0090), # 90 bps
    (5.50, "A+",  0.0115), # 115 bps
    (4.25, "A",   0.0135), # 135 bps
    (3.00, "A-",  0.0160), # 160 bps
    (2.50, "BBB", 0.0210), # 210 bps (Investment Grade boundary)
    (2.25, "BB+", 0.0285), # 285 bps
    (2.00, "BB",  0.0340), # 340 bps
    (1.75, "B+",  0.0425), # 425 bps
    (1.50, "B",   0.0525), # 525 bps
    (1.25, "B-",  0.0650), # 650 bps (Distress Gating Threshold)
    (0.80, "CCC", 0.0850), # 850 bps
    (0.50, "CC",  0.1000), # 1000 bps
    (-float("inf"), "D", 0.1250), # 1250 bps (Default/Distressed Loss)
]

DAMODARAN_SPREAD_SMALL_CAP = [
    (12.50, "AAA", 0.0065),
    (9.50,  "AA",  0.0090),
    (7.50,  "A+",  0.0115),
    (6.00,  "A",   0.0135),
    (4.50,  "A-",  0.0160),
    (4.00,  "BBB", 0.0210),
    (3.50,  "BB+", 0.0285),
    (3.00,  "BB",  0.0340),
    (2.50,  "B+",  0.0425),
    (2.00,  "B",   0.0525),
    (1.50,  "B-",  0.0650),
    (1.25,  "CCC", 0.0850),
    (0.80,  "CC",  0.1000),
    (-float("inf"), "D", 0.1250),
]
```

### 2.2 WACC & Cost of Capital Engine (`WACCEngine.calculate`, Lines 384-528)
Key mechanics implemented in `WACCEngine`:
1. **Market Cap Classification**:
   - `mcap_b = market_cap / 1e9`
   - If `mcap_b > 5000.0` (Market Cap > 5,000 Billion VND ~ 5 Trillion VND), firm is evaluated against `DAMODARAN_SPREAD_LARGE_CAP`; otherwise `DAMODARAN_SPREAD_SMALL_CAP`.
2. **ICR Edge Cases**:
   - Operating Loss ($EBIT \le 0$): Sets $ICR = -1.0 \implies$ Rating `'D'` and Spread `12.50%` (1250 bps).
   - Zero Interest Expense ($Interest \le 0$): Sets $ICR = 100.0 \implies$ Rating `'AAA'` and Spread `0.65%` (65 bps).
   - Standard: $ICR = \frac{EBIT}{\max(Interest, 1.0)}$.
3. **Cost of Debt Formulations**:
   - $K_{d, \text{pre-tax}} = R_f + \text{Spread}$
   - $K_{d, \text{after-tax}} = K_{d, \text{pre-tax}} \times (1 - \text{Tax Rate})$ (with standard $\text{Tax Rate} = 20.0\%$).
4. **WACC Capital Weighting & Bounds**:
   - $W_e = \text{clamp}(\frac{E}{E + D}, 0.20, 1.00)$, $W_d = 1.0 - W_e$.
   - $WACC = \text{clamp}(W_e \times K_e + W_d \times K_{d, \text{after-tax}}, 0.085, 0.185)$.

### 2.3 Intrinsic Valuation Models in `services/valuation_engine.py` Dependent on Debt & Capital Allocation
1. **Model 9: Extended 2-Stage McKinsey DCF (`model_9_dcf_2stage_mckinsey`, Line 1053)**:
   - Enterprise Value is discounted at $WACC$; Equity Value is derived by subtracting $Total\_Debt$ and adding $Cash$.
   - High-fidelity forecast debt balances and interest expenses directly sharpen the net debt bridge.
2. **Model 10: Edwards-Bell-Ohlson Residual Income (`model_10_rim_edwards_bell_ohlson`, Line 1102)**:
   - Book equity roll-forward: $BV_t = BV_{t-1} \times (1 + ROE_t \times (1 - \text{Payout Ratio}))$.
   - Explicitly driven by the Capital Allocation dividend payout retention policy!
3. **Model 15: Warren Buffett Owner's Earnings DCF (`model_15_buffett_owners_earnings`, Line 1281)**:
   - $Owner\_Earnings_t = CFO_t - Maintenance\_CapEx_t$.
   - $CFO_t$ depends on interest paid and operating working capital deltas; CapEx decomposition is linked with the debt schedule.
4. **Model 17: Banking / Equity Cash Flow & FCFE (`model_17_bank_equity_cash_flow`, Line 1366)**:
   - Free Cash Flow to Equity: $FCFE_t = NPAT_t - \Delta Required\_Equity_t$.
   - Corporate FCFE generalization: $FCFE_t = CFO_t - CapEx_t + \Delta Debt_t$.
5. **Model 20: Industrial Adjusted Present Value (`model_20_industrial_apv`, Line 1477)**:
   - $APV = V_{unlevered} + PV(\text{Interest Tax Shield}) - PV(\text{Financial Distress})$.
   - $PV(\text{Interest Tax Shield}) = \sum_{t=1}^5 \frac{t_c \times K_{d,t} \times Debt_t}{(1 + K_{d,t})^t}$.
6. **Model 22: Utilities 3-Stage DDM / H-Model (`model_22_utilities_3stage_ddm`, Line 1549)**:
   - $FV = \frac{D_0 \times (1 + g_n) + D_0 \times H \times (g_a - g_n)}{K_e - g_n}$.
   - Driven by $D_0$ and dividend growth $g_a$, which are generated by the Debt & Capital Schedule Engine!

---

## 3. Architecture of `services/debt_capital_schedule_engine.py`

### 3.1 Single Source of Truth & Clean Import Strategy
To guarantee zero code duplication and perfect cross-engine consistency, `services/debt_capital_schedule_engine.py` must import the macro constants and Damodaran tables directly from `services.valuation_engine`:

```python
from services.valuation_engine import (
    DAMODARAN_SPREAD_LARGE_CAP,
    DAMODARAN_SPREAD_SMALL_CAP,
    DEFAULT_RF,
    DEFAULT_TAX_RATE,
    safe_div,
    clamp,
)
```

In addition, `services/debt_capital_schedule_engine.py` should define standalone fallback constants internally in case of testing or isolated imports, ensuring resilience.

### 3.2 Data Models & Interface Contracts
The interface contract defined in `PROJECT.md` is:

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Tuple, Optional, Any

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

class DebtCapitalForecastResult(BaseModel):
    symbol: str
    base_debt: float
    periods: List[DebtSchedulePeriod]
    summary_metrics: Dict[str, Any]
```

### 3.3 Dynamic 5-Year Debt Amortization Mechanics

For each forecast period $t \in \{1, 2, 3, 4, 5\}$:

$$\begin{aligned}
Opening\_Debt_t &= \begin{cases} Base\_Debt, & t = 1 \\ Closing\_Debt_{t-1}, & t > 1 \end{cases} \\
Principal\_Amortization_t &= Opening\_Debt_t \times \text{Amortization\_Rate} \quad (\text{default } 15\% \text{ to } 20\%) \\
New\_Borrowings_t &= CapEx_t \times \text{Debt\_Financing\_Ratio} \quad (\text{default } 30\% \text{ to } 50\%) \\
Closing\_Debt_t &= \max(0.0, Opening\_Debt_t - Principal\_Amortization_t + New\_Borrowings_t) \\
Average\_Debt_t &= \frac{Opening\_Debt_t + Closing\_Debt_t}{2.0}
\end{aligned}$$

### 3.4 Numerical Resolution of ICR and Period Interest Expense
Because Interest Expense depends on $K_d$, and $K_d$ depends on $ICR = \frac{EBIT}{Interest\_Expense}$, an instantaneous circularity exists within the single period.

**Resolution Algorithm (Monotonic Contraction Mapping)**:
1. **Initial Estimate**:
   $$Interest^{(0)}_t = Average\_Debt_t \times (R_f + \text{Base Spread})$$
2. **Compute ICR**:
   $$ICR^{(0)}_t = \begin{cases} -1.0, & EBIT_t \le 0 \\ 100.0, & Interest^{(0)}_t \le 0 \\ \frac{EBIT_t}{\max(Interest^{(0)}_t, 1.0)}, & \text{otherwise} \end{cases}$$
3. **Lookup Damodaran Spread**:
   $$(Rating_t, Spread_t) = \text{lookup\_damodaran}(ICR^{(0)}_t, \text{is\_large\_cap})$$
4. **Compute Refined $K_d$ and Final Interest Expense**:
   $$\begin{aligned}
   K_{d, \text{pre-tax}, t} &= R_f + Spread_t \\
   K_{d, \text{after-tax}, t} &= K_{d, \text{pre-tax}, t} \times (1 - \text{Tax Rate}) \\
   Interest\_Expense_t &= Average\_Debt_t \times K_{d, \text{pre-tax}, t} \\
   Cash\_Interest\_Paid_t &= Interest\_Expense_t
   \end{aligned}$$

Because the Damodaran spread table is a piecewise-constant monotonic step function, this 2-step evaluation converges immediately and deterministically without infinite loops.

### 3.5 Solvency-Guarded Capital Allocation & Dividend Policy

$$\begin{aligned}
Target\_Dividends_t &= \max(0.0, NPAT_t \times \text{Payout\_Ratio}) \\
\text{Solvency Guard 1 (NPAT Deficit)} &: \text{If } NPAT_t \le 0 \implies Dividends_t = 0.0 \\
\text{Solvency Guard 2 (ICR Distress)} &: \text{If } ICR_t < 1.25 \text{ (Rating } \le B^-) \implies Dividends_t = 0.0 \\
\text{Solvency Guard 3 (Cash/Coverage)} &: \text{If } 1.25 \le ICR_t < 2.00 \implies Dividends_t = 0.50 \times Target\_Dividends_t \\
\text{Share Repurchases}_t &: \begin{cases} \min(Excess\_Cash_t \times 0.20, NPAT_t \times 0.10), & \text{if } ICR_t \ge 3.0 \text{ and } NPAT_t > 0 \\ 0.0, & \text{otherwise} \end{cases}
\end{aligned}$$

---

## 4. Integration Touchpoints with `services/three_statement_engine.py` (M3)

The Modano 3-Way Statement Engine (`services/three_statement_engine.py`) builds the complete 5-year integrated financial model. Here is the exact mapping of inputs and outputs:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│             services/debt_capital_schedule_engine.py (M2)                    │
│                                                                              │
│  - Closing_Debt_t (Short-term & Long-term split)                             │
│  - Interest_Expense_t & Cash_Interest_Paid_t                                 │
│  - Principal_Amortization_t & New_Borrowings_t (Net Debt Drawdown)           │
│  - Dividends_Paid_t & Share_Repurchases_t                                    │
└──────┬───────────────────────────────┬───────────────────────────────┬───────┘
       │                               │                               │
       ▼                               ▼                               ▼
┌──────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────┐
│   INCOME STATEMENT   │ │     BALANCE SHEET         │ │  CASH FLOW STATEMENT  │
│        (P&L)         │ │         (BS)              │ │    (DIRECT METHOD)    │
├──────────────────────┤ ├───────────────────────────┤ ├───────────────────────┤
│ Interest Expense:    │ │ Current Liabilities:      │ │ Operating Cash Flow:  │
│ = Interest_Expense_t │ │ - Short-Term Debt_t       │ │ - Cash Interest Paid  │
│                      │ │ Non-Current Liabilities:  │ │   = -Cash_Int_Paid_t  │
│ EBT = EBIT - Int     │ │ - Long-Term Debt_t        │ │ - Cash Tax Paid       │
│                      │ │   (Total = Closing_Debt_t)│ │                       │
│ Tax = max(0, EBT*tc) │ │                           │ │ Financing Cash Flow:  │
│                      │ │ Equity:                   │ │ - Net Debt Drawdown   │
│ NPAT = EBT - Tax     │ │ - Retained Earnings:      │ │   = New_Debt - Amort  │
│                      │ │   RE_t = RE_{t-1} + NPAT  │ │ - Dividends Paid      │
│                      │ │          - Dividends_t    │ │   = -Dividends_Paid_t │
│                      │ │ - Contributed Capital:    │ │ - Share Repurchases   │
│                      │ │   CC_t = CC_{t-1} - Rep   │ │   = -Repurchases_t    │
└──────────────────────┘ └─────────────┬─────────────┘ └───────────┬───────────┘
                                       │                           │
                                       ▼                           ▼
                         ┌───────────────────────────────────────────────┐
                         │      EXACT BALANCE SHEET CLOSURE IDENTITY     │
                         │                                               │
                         │ Ending_Cash_t = Beg_Cash_t + Delta_Cash_t     │
                         │ BS Cash_t === Ending_Cash_t                   │
                         │                                               │
                         │ |Total Assets_t - (Total Liab_t + Equity_t)|  │
                         │                   < 10^-5                     │
                         └───────────────────────────────────────────────┘
```

### 4.1 Income Statement Linkage Table
| Line Item | Source / Formula | Explanation |
|---|---|---|
| `ebit` | $Revenue_t - COGS_t - SGA_t$ | Operating earnings from operations |
| `interest_expense` | $DebtSchedulePeriod.interest\_expense_t$ | $Average\_Debt_t \times K_{d, \text{pre-tax}, t}$ |
| `ebt` | $EBIT_t - Interest\_Expense_t$ | Earnings Before Taxes |
| `tax_expense` | $\max(0.0, EBT_t \times \text{Tax Rate})$ | Corporate income tax (20%) |
| `npat` | $EBT_t - Tax\_Expense_t$ | Net Profit After Tax |

### 4.2 Balance Sheet Linkage Table
| Balance Sheet Item | Mapping from Debt & Capital Schedule | Balance Sheet Invariant Impact |
|---|---|---|
| `short_term_debt` | $\min(Closing\_Debt_t, Principal\_Amortization_{t+1} \text{ or } 0.35 \times Closing\_Debt_t)$ | Current portion of debt obligations |
| `long_term_debt` | $Closing\_Debt_t - Short\_Term\_Debt_t$ | Non-current interest-bearing debt |
| **Total Debt** | $Short\_Term\_Debt_t + Long\_Term\_Debt_t \equiv Closing\_Debt_t$ | Matches debt schedule exactly |
| `retained_earnings` | $Retained\_Earnings_{t-1} + NPAT_t - Dividends\_Paid_t$ | Primary link between P&L, Capital Allocation, and BS |
| `contributed_capital` | $Contributed\_Capital_{t-1} - Share\_Repurchases_t$ | Equity reduction from share buybacks |
| `cash` | $Ending\_Cash_t$ from Cash Flow Statement | Dynamic cash reconciliation asset |

### 4.3 Cash Flow Statement (Direct Method) Linkage Table
| Cash Flow Item | Section | Direct Formula |
|---|---|---|
| `cash_interest_paid` | Direct Operating CFO | $-DebtSchedulePeriod.cash\_interest\_paid_t$ |
| `cash_tax_paid` | Direct Operating CFO | $-Tax\_Expense_t$ |
| `net_cfo` | Direct Operating CFO | $Receipts - Suppliers - Opex - Interest - Tax$ |
| `net_debt_drawdown` | Financing CFF | $New\_Borrowings_t - Principal\_Amortization_t = \Delta Closing\_Debt_t$ |
| `dividends_paid` | Financing CFF | $-DebtSchedulePeriod.dividends\_paid_t$ |
| `share_repurchases` | Financing CFF | $-DebtSchedulePeriod.share\_repurchases_t$ |
| `net_cff` | Financing CFF | $Net\_Debt\_Drawdown_t - Dividends\_Paid_t - Share\_Repurchases_t$ |
| `net_change_in_cash` | CFS Summary | $Net\_CFO_t + Net\_CFI_t + Net\_CFF_t$ |
| `ending_cash` | CFS Summary | $Beginning\_Cash_t + Net\_Change\_In\_Cash_t$ |

---

## 5. Directed Acyclic Graph (DAG) Execution Flow & Circular Dependency Resolution

### 5.1 Why the Traditional Circularity Occurs
In naive financial models:
$$\text{Debt} \implies \text{Interest} \implies \text{Net Income} \implies \text{Ending Cash} \implies \text{Deficit Borrowing (Plug)} \implies \text{Debt}$$

If debt is used as a dynamic plug to balance cash, a simultaneous system of equations or iterative solver is required, which frequently oscillates or fails on distressed balance sheets.

### 5.2 Modano Standard Solution: Schedule-Driven Debt with Cash Buffer Closure
In the institutional Modano standard:
1. Debt follows an **autonomous operating schedule** ($Amortization_t + Planned\_CapEx\_Borrowing_t$).
2. Cash acts as the **exact balance sheet closure plug** ($Cash_t \equiv Ending\_Cash_t$).
3. If $Cash_t < 0$, the balance sheet **still mathematically balances**, but triggers the **Liquidity Distress Firewall** (Requirement R3 / Milestone 4).

### 5.3 7-Step Pure DAG Execution Sequence

```
[Step 1: Working Capital Engine (M1)]
   Input: Historical AR, Inv, AP, Sector Priors, Projected Revenue & COGS
   Output: DSO, DIO, DPO, CCC, Schedule of AR_t, Inv_t, AP_t, Delta NWC_t
       │
       ▼
[Step 2: Fixed Assets & CapEx Schedule]
   Input: Gross PPE, Historical Depreciation Rate, Growth CapEx Rate
   Output: Net PPE_t, Depreciation_t, CapEx_t
       │
       ▼
[Step 3: Debt & Capital Allocation Schedule Engine (M2)]
   Input: Base Debt, Projected EBIT_t, CapEx_t, Target Payout Ratio, Rf, Tax Rate
   Output: Opening_Debt_t, Amortization_t, New_Borrowings_t, Closing_Debt_t,
           Avg_Debt_t, ICR_t, Kd_t, Interest_Expense_t, Dividends_t, Repurchases_t
       │
       ▼
[Step 4: Income Statement Engine (P&L)]
   Input: Revenue_t, COGS_t, SGA_t, Depreciation_t, Interest_Expense_t
   Output: Gross Profit_t, EBIT_t, EBT_t, Tax_t, NPAT_t
       │
       ▼
[Step 5: Direct Method Cash Flow Engine (CFS)]
   Input: Revenue, COGS, SGA, Delta NWC, CapEx, Interest_Paid, Tax_Paid,
          Net_Borrowings, Dividends_Paid, Share_Repurchases, Beg_Cash
   Output: Net CFO_t, Net CFI_t, Net CFF_t, Delta Cash_t, Ending_Cash_t
       │
       ▼
[Step 6: Balance Sheet Roll-Forward & Closure Check (M3)]
   Input: Cash_t (= Ending_Cash_t), AR_t, Inv_t, Net PPE_t, AP_t,
          Short_Term_Debt_t, Long_Term_Debt_t, Retained_Earnings_t, Contributed_Capital_t
   Output: Total Assets_t, Total Liabilities & Equity_t,
           Balance Check: |Total Assets - Total Liab & Eq| < 10^-5 (TRUE)
       │
       ▼
[Step 7: Liquidity Distress Firewall & Valuation Enrichment (M4)]
   Input: Ending_Cash_t, ICR_t, Projected Dividends_t, Projected Kd_t
   Output: LiquidityDistressCheck (Flag if Cash < 0 or ICR < 1.25),
           MOS Risk Penalty (+5% to +15%), Intrinsic DDM/FCFE/APV Models
```

---

## 6. Unit Testing & Verification Strategy (`tests/test_debt_capital_schedule_engine.py`)

To achieve $\ge 90\%$ line coverage and rigorous verification across all financial regimes, the test suite must implement four distinct tiers:

### Tier 1: Standard Damodaran Lookup & Amortization Calculations
- Test ICR lookup against all 14 rating brackets for Large-Cap ($AAA$ to $D$).
- Test ICR lookup against all 14 rating brackets for Small-Cap ($AAA$ to $D$).
- Verify pre-tax and after-tax cost of debt with varying $R_f$ and tax rates.
- Verify exact 5-year debt roll-forward balance identity:
  $$Closing\_Debt_t \equiv Opening\_Debt_t + New\_Borrowings_t - Principal\_Amortization_t$$

### Tier 2: Boundary Values, Extreme Regimes & Adversarial Cases
- **Zero Debt Company** (e.g., net cash rich like VNM / FPT):
  $Base\_Debt = 0 \implies Interest\_Expense = 0, ICR = 100.0, Rating = AAA, Kd = Rf + 65 \text{ bps}$.
- **Distressed Operating Loss Company** ($EBIT < 0$):
  $EBIT = -500B \implies ICR = -1.0, Rating = D, Kd = Rf + 1250 \text{ bps}$, Dividends = 0.
- **Extreme High Leverage / Negative Equity**:
  Verify zero division protection on $EBIT / Interest$ and graceful bounding.

### Tier 3: Solvency Guard & Capital Allocation Verification
- Verify that when $NPAT < 0$, $Dividends \equiv 0$.
- Verify that when $ICR < 1.25$, $Dividends \equiv 0$ regardless of positive NPAT.
- Verify that when $1.25 \le ICR < 2.00$, dividends are capped at $50\%$ of target.
- Verify that share repurchases are strictly suppressed when $ICR < 3.00$.

### Tier 4: Real-World VN30 Tickers Integration
- **VNM (Vinamilk)**: Low debt, high dividend payout (~70%), strong ICR > 15x.
- **HPG (Hoa Phat)**: Heavy CapEx industrial, substantial debt financing, cyclical EBIT.
- **MWG (Mobile World)**: Negative CCC retail model, moderate short-term debt.
- **VIC / NVL (Real Estate Developers)**: High leverage, complex debt amortizations, test distress boundary gating.

---

## 7. Recommendations for Milestone 2 & Milestone 3 Implementers

1. **Keep `services/valuation_engine.py` as Single Source of Truth**:
   Import `DAMODARAN_SPREAD_LARGE_CAP`, `DAMODARAN_SPREAD_SMALL_CAP`, `DEFAULT_RF`, and `DEFAULT_TAX_RATE`.
2. **Standardize Credit Spread Units**:
   Store `credit_spread_bps` as basis points ($Spread \times 10,000$, e.g., $135.0$) and `credit_spread` as decimal ($0.0135$) for seamless compatibility with both human reporting and financial formulas.
3. **Strict Type Annotations with Pydantic**:
   Ensure `DebtSchedulePeriod` and `DebtCapitalScheduleEngine` use strict Pydantic `BaseModel` for effortless FastAPI serialization and JSON export.
4. **Preserve Linear DAG Architecture**:
   Never make Debt a dynamic balance sheet plug in `services/three_statement_engine.py`; always keep Cash as the final balancing line item, and let negative cash trigger the Liquidity Distress Firewall (R3).

---
*End of Report `analysis_m2_integration.md`.*
