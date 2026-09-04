# Mathematical Specifications & Technical Design: R1 Quantitative Valuation Engine (22 Models, WACC 5-Factor VN CAPM, Multi-Algo Weighting & Scenarios)

**Author**: Explorer 2 — Valuation Models & Mathematical Specs Specialist  
**Target File**: `services/valuation_engine.py`  
**Date**: 2026-08-27  
**Status**: Comprehensive Mathematical Specification & Implementation Blueprint  

---

## 1. System Architecture & Valuation Pipeline Overview

The Quantitative Valuation Engine (`services/valuation_engine.py`) provides an institutional-grade valuation architecture ported and expanded from the quantitative framework of **Pine Script FFV Pro** and Goldman Sachs / McKinsey equity research standards, specifically calibrated for Vietnam equities (HOSE, HNX, UPCOM).

```
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │                      INPUT: FINANCIAL DATA & MARKET SNAPSHOT                      │
 │    (screener_snapshot.json, historical_prices.json, financial_statements.json)   │
 └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │                       STEP 1: CAPITAL COST & MACRO ENGINE                         │
 │  - 5-Factor Vietnam CAPM: Market, SMB, HML, Momentum, Amihud Illiquidity, RMW     │
 │  - Damodaran Synthetic Rating & Cost of Debt (Interest Coverage -> Spread)        │
 │  - WACC Calculator & Cost of Equity (Ke) with Vietnam Sovereign Risk Adjustment   │
 └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │                        STEP 2: 22 QUANTITATIVE VALUATION MODELS                   │
 │ ┌──────────────────────┐ ┌──────────────────────┐ ┌─────────────────────────────┐ │
 │ │  8 RELATIVE MODELS   │ │  7 ABSOLUTE MODELS   │ │   7 SECTOR-SPECIFIC MODELS  │ │
 │ │ - Blended P/E & CAPE │ │ - 2-Stage Driver DCF │ │ - Pharma rNPV Pipeline      │ │
 │ │ - P/S Multiplier     │ │ - Residual Income RIM│ │ - Banking Equity Cash Flow  │ │
 │ │ - P/FCF Yield        │ │ - Greenwald EPV      │ │ - REITs AFFO DCF            │ │
 │ │ - P/B (Rhodes-Kropf) │ │ - Graham Growth No.  │ │ - Telecom Unbundled SOTP/RAB│ │
 │ │ - P/TBV (Tangible)   │ │ - Rule of 40/X Model │ │ - Industrial APV            │ │
 │ │ - Blended EV/EBITDA  │ │ - Acquirer's Multiple│ │ - Consumer Staples EVA      │ │
 │ │ - P/CF Operating     │ │ - Buffett Owner Earn │ │ - Utilities 3-Stage DDM     │ │
 │ │ - P/AFFO Multiple    │ │                      │ │                             │ │
 │ └──────────────────────┘ └──────────────────────┘ └─────────────────────────────┘ │
 └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │                 STEP 3: OUTLIER FILTERING & NUMERICAL SAFEGUARDS                  │
 │  - Non-negativity constraint ($FV \ge 0$) & Boundary Capping                      │
 │  - Winsorization (5th - 95th percentile) & 1.5x IQR Outlier Rejection             │
 │  - Sector Applicability Gate (Filter irrelevant models for specialized sectors)   │
 └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │                 STEP 4: MULTI-ALGO ADAPTIVE ERROR WEIGHTING (IVW)                 │
 │  - Historical Rolling Prediction Error Tracking (SMAPE, MALE, WMAPE, RMSLE)       │
 │  - Inverse Variance Weighting (IVW): $w_i \propto 1 / \sigma_i^2$                 │
 │  - Cold-Start / Zero Track Record Sector Prior Fallback                           │
 └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │              STEP 5: STRESS-TEST SCENARIOS & 2D SENSITIVITY ENGINE                │
 │  - Bear / Base / Bull Scenarios via Driver Perturbations                          │
 │  - 5x5 Matrix: WACC ($\pm 2.0\%$) vs Terminal Growth $g$ ($\pm 1.5\%$)            │
 │  - Output: Composite Fair Value, Model Breakdown, Confidence Score, Scenarios    │
 └───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. WACC Engine & 5-Factor Vietnam CAPM Specification

### 2.1 5-Factor Vietnam CAPM for Cost of Equity ($K_e$)

The standard 1-factor CAPM understates risks in emerging frontier markets like Vietnam due to retail liquidity shocks, state ownership skew, and book-to-market anomalies. We formulate the **5-Factor Vietnam CAPM**:

$$K_e = R_f + \beta_{\text{mkt}} \cdot \text{ERP} + s \cdot \text{SMB} + h \cdot \text{HML} + m \cdot \text{UMD} + l \cdot \text{ILLIQ} + r \cdot \text{RMW}$$

#### Component Parameterization (Vietnam Market Calibrated):
1. **Risk-Free Rate ($R_f$)**:
   - Benchmark: Vietnam 10-Year Government Bond Yield (State Treasury / SBV).
   - Baseline: $R_f = 5.00\%$ ($0.050$), dynamically fetched from `services/macro_monetary_service.py` if live, fallback to $5.0\%$.
2. **Equity Risk Premium ($\text{ERP}$)**:
   - Damodaran Vietnam ERP = Mature Market ERP ($4.60\%$) + Vietnam Country Risk Premium ($\text{CRP} = 3.55\%$) $\approx 8.15\%$.
   - Range: $[7.5\%, 9.0\%]$, default $\text{ERP} = 8.15\%$.
3. **Market Beta ($\beta_{\text{mkt}}$)**:
   - 60-month / 252-day regression against VN-Index:
     $$\beta_{\text{raw}} = \frac{\text{Cov}(R_i, R_{\text{VNINDEX}})}{\text{Var}(R_{\text{VNINDEX}})}$$
   - Vasicek / Blume Adjusted Beta to prevent sampling noise:
     $$\beta_{\text{adj}} = 0.67 \cdot \beta_{\text{raw}} + 0.33 \cdot 1.0$$
4. **Size Factor ($\text{SMB}$ - Small Minus Big)**:
   - Market Cap categorization:
     - Large Cap ($> 25,000$ tỷ VND, VN30): $s = 0.0, \text{SMB} = 0.0\%$
     - Mid Cap ($5,000 - 25,000$ tỷ VND, VNMID/VN70): $s = 0.5, \text{SMB} = 1.25\%$
     - Small Cap ($1,000 - 5,000$ tỷ VND, VNSML): $s = 1.0, \text{SMB} = 2.50\%$
     - Micro Cap ($< 1,000$ tỷ VND / UPCOM): $s = 1.5, \text{SMB} = 3.75\%$
5. **Value Factor ($\text{HML}$ - High Minus Low Book-to-Market)**:
   - $h = \text{clamp}\left(\frac{P/B_{\text{sector\_median}} - P/B_i}{P/B_{\text{sector\_median}}}, -1.0, 1.0\right)$
   - $\text{HML} = 1.50\%$
6. **Momentum Factor ($\text{UMD}$ - Up Minus Down 12M-1M Momentum)**:
   - $m = -\text{clamp}\left(\frac{R_{12M} - R_{1M}}{0.30}, -1.0, 1.0\right) \times 0.5$ (Contrarian factor premium)
   - $\text{UMD} = 1.00\%$
7. **Amihud Illiquidity Factor ($\text{ILLIQ}$)**:
   - Amihud Illiquidity Measure:
     $$\text{ILLIQ}_i = \frac{1}{D} \sum_{d=1}^D \frac{|R_{i, d}|}{\text{Volume}_{i, d} \times P_{i, d}}$$
   - Premium $l \cdot \text{ILLIQ}$:
     - High liquidity (ADTV $> 50$ tỷ VND): $0.0\%$
     - Moderate liquidity (ADTV $10 - 50$ tỷ VND): $0.50\%$
     - Low liquidity (ADTV $2 - 10$ tỷ VND): $1.25\%$
     - Illiquid (ADTV $< 2$ tỷ VND): $2.50\%$
8. **Profitability Factor ($\text{RMW}$ - Robust Minus Weak Operating Profitability)**:
   - $r = \text{clamp}\left(\frac{15.0 - \text{ROE}_i}{10.0}, -1.0, 1.0\right)$
   - $\text{RMW} = 1.20\%$

**Cost of Equity Boundary Constraint**:
$$K_e = \text{clamp}(K_e, 0.085, 0.220) \quad (8.5\% \text{ to } 22.0\%)$$

---

### 2.2 Damodaran Synthetic Credit Spread & Cost of Debt ($K_d$)

For non-financial firms in Vietnam where bond ratings are rarely public, $K_d$ is derived via **Aswath Damodaran's Synthetic Credit Rating Table** based on Interest Coverage Ratio ($\text{ICR} = \frac{\text{EBIT}}{\text{Interest Expense}}$):

$$\text{ICR} = \frac{\text{Operating Profit (EBIT)}}{\max(\text{Interest Expense}, 1.0)}$$

| Interest Coverage Ratio (Large Cap $> 5,000$B VND) | ICR (Small Cap $\le 5,000$B VND) | Synthetic Rating | Credit Spread over $R_f$ |
|---|---|---|---|
| $> 8.50$ | $> 12.50$ | **AAA** | $+0.65\%$ |
| $6.50 - 8.50$ | $9.50 - 12.50$ | **AA** | $+0.90\%$ |
| $5.50 - 6.50$ | $7.50 - 9.50$ | **A+** | $+1.15\%$ |
| $4.25 - 5.50$ | $6.00 - 7.50$ | **A** | $+1.35\%$ |
| $3.00 - 4.25$ | $4.50 - 6.00$ | **A-** | $+1.60\%$ |
| $2.50 - 3.00$ | $4.00 - 4.50$ | **BBB** | $+2.10\%$ |
| $2.25 - 2.50$ | $3.50 - 4.00$ | **BB+** | $+2.85\%$ |
| $2.00 - 2.25$ | $3.00 - 3.50$ | **BB** | $+3.40\%$ |
| $1.75 - 2.00$ | $2.50 - 3.00$ | **B+** | $+4.25\%$ |
| $1.50 - 1.75$ | $2.00 - 2.50$ | **B** | $+5.25\%$ |
| $1.25 - 1.50$ | $1.50 - 2.00$ | **B-** | $+6.50\%$ |
| $0.80 - 1.25$ | $1.25 - 1.50$ | **CCC** | $+8.50\%$ |
| $0.50 - 0.80$ | $0.80 - 1.25$ | **CC** | $+10.00\%$ |
| $< 0.50$ (Distressed) | $< 0.80$ | **D** | $+12.50\%$ |

**Pre-Tax Cost of Debt**:
$$K_{d, \text{pre}} = R_f + \text{Credit Spread}$$

**After-Tax Cost of Debt**:
$$K_d = K_{d, \text{pre}} \times (1 - t_c)$$
where $t_c = 0.20$ (Vietnam standard corporate income tax rate $20\%$).

---

### 2.3 Weighted Average Cost of Capital (WACC)

$$WACC = \left(\frac{E}{V} \times K_e\right) + \left(\frac{D}{V} \times K_d\right)$$

where:
- $E = \text{Market Capitalization} = \text{Price} \times \text{Shares Outstanding}$
- $D = \text{Total Interest-Bearing Debt} = \text{Short-term Debt (Code 315)} + \text{Long-term Debt (Code 338)}$
- $V = E + D$
- Weight of Equity $w_e = \frac{E}{V}$, Weight of Debt $w_d = \frac{D}{V}$
- Constraint: $w_e \in [0.20, 1.00], w_d \in [0.00, 0.80]$

**WACC Numerical Floor / Ceiling**:
$$WACC = \text{clamp}(WACC, 0.085, 0.185) \quad (8.5\% \text{ to } 18.5\%)$$

---

## 3. The 8 Relative Valuation Models (R1.1)

All relative models compute intrinsic fair value per share in Vietnamese Dong (or thousand VND) by combining company fundamental metrics with sector-normalized and historical harmonic multiples.

### 3.1 Model 1: Blended P/E & Cyclically Adjusted CAPE Multiplier
- **Concept**: Combines trailing P/E, 3-year weighted median P/E, and Shiller's 5-Year / 10-Year Cyclically Adjusted Price-to-Earnings (CAPE) to neutralize earnings cycles in cyclical sectors (Steel, Real Estate, Securities, Chemicals).
- **Formulation**:
  $$\text{EPS}_{\text{cyclical}} = \frac{1}{\sum_{k=1}^K w_k} \sum_{k=1}^K w_k \cdot \text{EPS}_{t-k} \cdot \left(\frac{\text{CPI}_t}{\text{CPI}_{t-k}}\right)$$
  where $K = \min(N_{\text{available\_years}}, 5)$, weights $w = [0.35, 0.25, 0.20, 0.12, 0.08]$.
  $$\text{Target P/E} = 0.40 \cdot P/E_{\text{sector\_median}} + 0.35 \cdot P/E_{\text{hist\_5y\_harmonic}} + 0.25 \cdot \text{PEG\_derived\_PE}$$
  where $\text{PEG\_derived\_PE} = \text{clamp}(g_{\text{EPS}} \times 100 \times 1.0, 8.0, 22.0)$.
- **Fair Value**:
  $$FV_{\text{Blended\_PE}} = \text{Target P/E} \times \left(0.60 \cdot \text{EPS}_{\text{TTM}} + 0.40 \cdot \text{EPS}_{\text{cyclical}}\right)$$
- **Boundary & Fallback**: If $\text{EPS}_{\text{TTM}} \le 0$, return fallback from P/B-ROE regressed value.

---

### 3.2 Model 2: Price-to-Sales (P/S) Margin-Adjusted Multiplier
- **Concept**: Ken Fisher's Price-to-Sales valuation scaled by sustainable net profit margin relative to sector peers.
- **Formulation**:
  $$\text{Target P/S} = P/S_{\text{sector\_median}} \times \left(\frac{\text{Net Margin}_i}{\text{Net Margin}_{\text{sector\_median}}}\right)^{0.65}$$
  $$FV_{\text{PS}} = \text{Target P/S} \times \text{Sales Per Share (SPS)}$$
  where $\text{SPS} = \frac{\text{Revenue}_{\text{TTM}}}{\text{Shares Outstanding}}$.
- **Boundary**: Clamped Target P/S $\in [0.25 \cdot P/S_{\text{sector}}, 3.0 \cdot P/S_{\text{sector}}]$.

---

### 3.3 Model 3: Price-to-Free Cash Flow (P/FCF) Multiplier
- **Concept**: Valuing the business based on actual cash generated after all capital expenditures.
- **Formulation**:
  $$\text{FCF}_{\text{TTM}} = \text{CFO}_{\text{TTM}} - \text{CapEx}_{\text{TTM}}$$
  $$\text{Target P/FCF} = \text{median}\left(P/FCF_{\text{sector\_positive}}, P/FCF_{\text{hist\_3y}}, 15.0\right)$$
  $$FV_{\text{P/FCF}} = \text{Target P/FCF} \times \frac{\max(\text{FCF}_{\text{TTM}}, 0.05 \cdot \text{Revenue})}{\text{Shares Outstanding}}$$
- **Edge Case**: If $\text{FCF}_{\text{TTM}} \le 0$ (e.g. high CapEx growth phase), compute Normalized FCF $= \text{EBITDA} \times 0.60 - \text{Maintenance CapEx}$.

---

### 3.4 Model 4: Price-to-Book (P/B) with Rhodes-Kropf (RKV) Filter
- **Concept**: Price-to-Book valuation adjusted by ROE-justified P/B and filtered through the Rhodes-Kropf valuation decomposition to remove overvalued/undervalued accounting noise.
- **Formulation**:
  $$\text{Justified P/B} = \frac{\text{ROE} - g}{K_e - g}$$
  where $g = \text{min}(\text{ROE} \times (1 - \text{Payout Ratio}), 0.06)$.
  $$\text{Target P/B} = 0.50 \cdot \text{Justified P/B} + 0.50 \cdot P/B_{\text{sector\_median}}$$
  $$FV_{\text{PB}} = \text{Target P/B} \times \text{Book Value Per Share (BVPS)}$$
- **Rhodes-Kropf Adjustment**: If firm-specific misvaluation $M/V > 1.30$, haircut $FV_{\text{PB}}$ by $(1 - 0.15)$.

---

### 3.5 Model 5: Price-to-Tangible Book Value (P/TBV)
- **Concept**: Conservative asset valuation stripping out goodwill, brand value, and intangible assets (Crucial for M&A heavy holding companies and banks).
- **Formulation**:
  $$\text{TBV} = \text{Total Equity} - \text{Goodwill} - \text{Intangible Fixed Assets}$$
  $$\text{TBVPS} = \frac{\text{TBV}}{\text{Shares Outstanding}}$$
  $$\text{Target P/TBV} = P/TBV_{\text{sector\_median}} \times \text{clamp}\left(\frac{\text{ROIC}}{WACC}, 0.6, 1.8\right)$$
  $$FV_{\text{PTBV}} = \text{Target P/TBV} \times \text{TBVPS}$$
- **Fallback**: If $\text{TBV} \le 0$, fallback to $0.50 \times \text{BVPS}$.

---

### 3.6 Model 6: Blended EV/EBITDA Enterprise Multiple
- **Concept**: Capital-structure-neutral enterprise valuation comparing operating earnings before non-cash charges.
- **Formulation**:
  $$\text{EBITDA} = \text{Operating Profit (EBIT)} + \text{Depreciation \& Amortization (D\&A)}$$
  $$\text{Target EV/EBITDA} = 0.60 \cdot \text{EV/EBITDA}_{\text{sector\_median}} + 0.40 \cdot \text{EV/EBITDA}_{\text{hist\_5y}}$$
  $$\text{Implied Enterprise Value (EV)} = \text{Target EV/EBITDA} \times \text{EBITDA}_{\text{TTM}}$$
  $$\text{Equity Value} = \text{EV} - \text{Total Debt} + \text{Cash \& Cash Equivalents} + \text{Short-term Investments} - \text{Minority Interest}$$
  $$FV_{\text{EV/EBITDA}} = \frac{\max(\text{Equity Value}, 0.10 \cdot \text{Market Cap})}{\text{Shares Outstanding}}$$

---

### 3.7 Model 7: Price-to-Operating Cash Flow (P/CF)
- **Concept**: Cash-flow based valuation free from accrual accounting manipulation (Beneish red flags).
- **Formulation**:
  $$\text{CFO}_{\text{per\_share}} = \frac{\text{Cash Flow from Operations (Code 100)}}{\text{Shares Outstanding}}$$
  $$\text{Target P/CF} = \text{median}\left(P/CF_{\text{sector}}, 8.5\right) \times \left(1 + 0.5 \cdot \min(\text{CFO\_to\_PAT} - 1.0, 0.5)\right)$$
  $$FV_{\text{PCF}} = \text{Target P/CF} \times \max(\text{CFO}_{\text{per\_share}}, 0.03 \cdot \text{Price})$$

---

### 3.8 Model 8: Price-to-AFFO Multiple (P/AFFO)
- **Concept**: Price to Adjusted Funds From Operations, standard for Real Estate Developers and asset leasing firms.
- **Formulation**:
  $$\text{AFFO} = \text{Net Income} + \text{D\&A} - \text{Maintenance CapEx} - \text{Gains on Asset Disposal} + \text{Lease Amortization}$$
  $$\text{Target P/AFFO} = \text{median}\left(P/AFFO_{\text{peers}}, 12.0\right)$$
  $$FV_{\text{PAFFO}} = \text{Target P/AFFO} \times \frac{\max(\text{AFFO}, 0.5 \cdot \text{Net Income})}{\text{Shares Outstanding}}$$

---

## 4. The 7 Absolute Intrinsic Models (R1.2)

### 4.1 Model 9: Extended 2-Stage Value Driver DCF (McKinsey / ROIC Framework)
- **Concept**: Rather than arbitrary FCF growth projections, cash flows are driven fundamentally by **Return on Invested Capital (ROIC)** and **Reinvestment Rate ($b$)**:
  $$g = \text{ROIC} \times b \implies b = \frac{g}{\text{ROIC}}$$
  $$\text{FCFF}_t = \text{NOPAT}_t \times (1 - b_t) = \text{NOPAT}_t \times \left(1 - \frac{g_t}{\text{ROIC}_t}\right)$$
- **Mathematical Derivation**:
  1. **Stage 1 (Years 1 to 5 - Explicit Forecast)**:
     - $\text{NOPAT}_0 = \text{EBIT} \times (1 - t_c)$
     - For $t = 1 \dots 5$:
       $$\text{NOPAT}_t = \text{NOPAT}_0 \times (1 + g_{\text{stage1}})^t$$
       $$\text{FCFF}_t = \text{NOPAT}_t \times \left(1 - \frac{g_{\text{stage1}}}{\text{ROIC}_{\text{stage1}}}\right)$$
       $$\text{PV}(\text{FCFF}_t) = \frac{\text{FCFF}_t}{(1 + WACC)^t}$$
  2. **Stage 2 (Terminal Value - Key Value Driver Formula)**:
     - At terminal stage, $\text{ROIC}_{\text{terminal}}$ fades toward the cost of capital ($WACC + 2.0\%$ competitive moat spread).
     $$\text{Terminal FCFF} = \text{NOPAT}_5 \times (1 + g_n) \times \left(1 - \frac{g_n}{\text{ROIC}_{\text{terminal}}}\right)$$
     $$TV_5 = \frac{\text{Terminal FCFF}}{WACC - g_n}$$
     $$\text{PV}(TV) = \frac{TV_5}{(1 + WACC)^5}$$
  3. **Enterprise to Equity Value**:
     $$\text{Enterprise Value} = \sum_{t=1}^5 \text{PV}(\text{FCFF}_t) + \text{PV}(TV)$$
     $$\text{Equity Value} = \text{Enterprise Value} + \text{Cash} - \text{Debt} - \text{Minority Interest}$$
     $$FV_{\text{ValueDriver\_DCF}} = \frac{\text{Equity Value}}{\text{Shares Outstanding}}$$
- **Parameter Bounds**:
  - $g_{\text{stage1}} = \text{clamp}(g_{\text{hist\_3y}}, 0.05, 0.20)$
  - $g_n = \text{clamp}(\text{GDP terminal}, 0.025, 0.040)$ (Default $3.5\%$)
  - $WACC > g_n + 0.015$ (Guarantees denominator $\ge 1.5\%$).

---

### 4.2 Model 10: Residual Income Model (RIM / Edwards-Bell-Ohlson)
- **Concept**: Equity value equals current book value plus the present value of all expected future **Residual Income (Economic Profits)** generated in excess of the Cost of Equity.
- **Formulation**:
  $$\text{Residual Income}_t = \text{Net Income}_t - (K_e \times \text{Book Value}_{t-1}) = (\text{ROE}_t - K_e) \times \text{Book Value}_{t-1}$$
- **Stage 1 (Years 1 to 5)**:
  - $\text{Book Value}_0 = \text{Total Equity}$
  - For $t = 1 \dots 5$:
    - $\text{ROE}_t = \text{ROE}_{\text{base}} + (\text{ROE}_{\text{target}} - \text{ROE}_{\text{base}}) \times \frac{t}{5}$
    - $\text{RI}_t = (\text{ROE}_t - K_e) \times \text{Book Value}_{t-1}$
    - $\text{Book Value}_t = \text{Book Value}_{t-1} + \text{Net Income}_t - \text{Dividends}_t = \text{Book Value}_{t-1} \times (1 + \text{ROE}_t \times (1 - \text{payout}))$
    - $\text{PV}(\text{RI}_t) = \frac{\text{RI}_t}{(1 + K_e)^t}$
- **Stage 2 (Continuing Residual Income with Fade Factor $\omega \in [0, 1]$)**:
  $$\text{Continuing RI} = \frac{\text{RI}_5 \times (1 + g)}{(1 + K_e - \omega)}$$
  $$\text{PV}(\text{Continuing RI}) = \frac{\text{Continuing RI}}{(1 + K_e)^5}$$
- **Total Intrinsic Equity Value**:
  $$\text{Equity Value} = \text{Book Value}_0 + \sum_{t=1}^5 \text{PV}(\text{RI}_t) + \text{PV}(\text{Continuing RI})$$
  $$FV_{\text{RIM}} = \frac{\text{Equity Value}}{\text{Shares Outstanding}}$$
- **Strength**: Not reliant on dividend payout assumptions; highly stable for financial institutions and capital-heavy businesses.

---

### 4.3 Model 11: Greenwald Earnings Power Value (EPV)
- **Concept**: Bruce Greenwald (Columbia University) model isolating current earnings power without paying for speculative future growth.
- **Formulation**:
  1. **Normalized EBIT**:
     $$\text{Normalized EBIT} = \text{EBIT}_{\text{margin\_5y\_avg}} \times \text{Revenue}_{\text{TTM}}$$
  2. **Normalized NOPAT**:
     $$\text{NOPAT}_{\text{normalized}} = \text{Normalized EBIT} \times (1 - t_c) + \text{Depreciation} - \text{Maintenance CapEx}$$
     where $\text{Maintenance CapEx} = \text{Depreciation} \times \left(\frac{\text{PPE}_{\text{net}}}{\text{Revenue}} \times \text{Depr Rate}\right)$
  3. **Earnings Power Value of the Firm ($EPV_{\text{firm}}$)**:
     $$EPV_{\text{firm}} = \frac{\text{NOPAT}_{\text{normalized}}}{WACC}$$
  4. **Equity EPV**:
     $$EPV_{\text{equity}} = EPV_{\text{firm}} + \text{Cash} - \text{Total Debt}$$
     $$FV_{\text{EPV}} = \frac{\max(EPV_{\text{equity}}, 0.0)}{\text{Shares Outstanding}}$$
- **Strategic Interpretation**:
  - If Market Cap $\ll EPV_{\text{equity}}$: Deep Value / Margin of Safety.
  - If Market Cap $\gg EPV_{\text{equity}}$: Market is paying heavily for future franchise growth.

---

### 4.4 Model 12: Graham Growth Number & Revised Formula
- **Concept**: Benjamin Graham's classical intrinsic value formulas (1962 & 1974 revisions).
- **Formulas**:
  1. **Graham Classic Number**:
     $$FV_{\text{Graham\_Classic}} = \sqrt{22.5 \times \text{EPS}_{\text{TTM}} \times \text{BVPS}}$$
     *(Valid when both $\text{EPS} > 0$ and $\text{BVPS} > 0$)*
  2. **Graham Revised Growth Formula**:
     $$FV_{\text{Graham\_Growth}} = \text{EPS} \times (8.5 + 2g) \times \frac{4.4}{Y}$$
     where:
     - $8.5 = \text{P/E base for a zero-growth company}$
     - $g = \text{expected 3-5 year growth rate in } \%$ (e.g. $10\% \to g = 10$)
     - $4.4 = \text{Graham's benchmark AAA corporate bond yield in 1962}$
     - $Y = \text{Current Vietnam Corporate/Treasury Yield } \approx 5.5\%$
  3. **Blended Graham Fair Value**:
     $$FV_{\text{Graham}} = 0.50 \cdot FV_{\text{Graham\_Classic}} + 0.50 \cdot FV_{\text{Graham\_Growth}}$$

---

### 4.5 Model 13: Rule of 40 / Rule of X Growth Valuation
- **Concept**: Valuation framework for high-growth tech/platform/consumer businesses scaling revenue multiple by the "Rule of 40 / Rule of X" score.
- **Formulation**:
  $$\text{Score}_{\text{Rule40}} = \text{Revenue Growth Rate (\%)} + \text{Free Cash Flow Margin (\%)} \times \text{Multiplier}_X$$
  where $\text{Multiplier}_X = 1.25$ (Weighting cash flow efficiency higher than raw revenue growth).
  $$\text{Target P/S} = P/S_{\text{base}} \times \left(1 + \frac{\text{Score}_{\text{Rule40}} - 40\%}{50\%}\right)$$
  where $P/S_{\text{base}} = \text{median}(P/S_{\text{sector}}, 1.5)$.
  $$FV_{\text{Rule40}} = \text{Target P/S} \times \text{Sales Per Share}$$
- **Boundary**: Target P/S clamped to $[0.5 \cdot P/S_{\text{base}}, 4.0 \cdot P/S_{\text{base}}]$.

---

### 4.6 Model 14: Acquirer's Multiple (Tobias Carlisle EV/EBIT)
- **Concept**: Tobias Carlisle's deep value model focusing on operating earnings yield $\text{EBIT}/\text{EV}$ to find companies offering the highest un-leveraged yield.
- **Formulation**:
  $$\text{Acquirer's Multiple} = \frac{\text{Enterprise Value}}{\text{Operating Earnings (EBIT)}}$$
  $$\text{Target Multiple} = \text{min}\left(\text{EV/EBIT}_{\text{sector\_median}}, 10.0\right)$$
  $$\text{Implied EV} = \text{Target Multiple} \times \max(\text{EBIT}_{\text{TTM}}, 0.05 \cdot \text{Revenue})$$
  $$\text{Equity Value} = \text{Implied EV} - \text{Net Debt}$$
  $$FV_{\text{Acquirers}} = \frac{\max(\text{Equity Value}, 0.10 \cdot \text{Market Cap})}{\text{Shares Outstanding}}$$

---

### 4.7 Model 15: Warren Buffett Owner's Earnings DCF
- **Concept**: Warren Buffett's 1986 Berkshire Hathaway shareholder letter definition of true owner cash flow.
- **Formulation**:
  $$\text{Owner's Earnings} = \text{Net Income} + \text{Depreciation \& Amortization} - \text{Maintenance CapEx} - \Delta\text{Working Capital}$$
  where:
  - $\text{Maintenance CapEx} = \text{CapEx} \times \left(\frac{1}{1 + g_{\text{revenue}}}\right)$ (Separating growth CapEx from maintenance)
  - $\Delta\text{Working Capital} = (\text{AR}_t + \text{Inv}_t - \text{AP}_t) - (\text{AR}_{t-1} + \text{Inv}_{t-1} - \text{AP}_{t-1})$
- **Discounting**:
  $$\text{PV}(\text{Owner's Earnings}) = \sum_{t=1}^5 \frac{\text{Owner's Earnings}_0 \times (1 + g)^t}{(1 + K_e)^t} + \frac{\text{Owner's Earnings}_5 \times (1 + g_n)}{(K_e - g_n)(1 + K_e)^5}$$
  $$FV_{\text{Owners\_Earnings}} = \frac{\text{PV}(\text{Owner's Earnings})}{\text{Shares Outstanding}}$$

---

## 5. The 7 Sector-Specific Models (R1.3)

### 5.1 Model 16: Risk-Adjusted NPV (rNPV) — Pharma & Project Pipeline
- **Target Sectors**: ICB 4500 (Healthcare, Pharmaceuticals, Biotechnology), Project Contractors.
- **Concept**: Calculates project-by-project Net Present Value weighted by cumulative clinical/execution probability of success ($p_s$).
- **Formulation**:
  $$rNPV = \sum_{k=1}^K p_{s, k} \times \text{NPV}_k + \text{Base Business EPV}$$
  - Success Probabilities ($p_s$):
    - Commercialized Drugs / Existing Manufacturing: $p_s = 1.00$
    - Bioequivalence / Phase III Trials: $p_s = 0.70$
    - Formulation / Phase II: $p_s = 0.40$
    - R&D / Preclinical: $p_s = 0.15$
  $$FV_{\text{rNPV}} = \frac{rNPV + \text{Net Cash}}{\text{Shares Outstanding}}$$

---

### 5.2 Model 17: Equity Cash Flow & Regulatory Capital Model — Banking & Insurance
- **Target Sectors**: ICB 8300 (Banks), ICB 8500 (Insurance).
- **Concept**: Banks cannot use standard DCF (debt is raw material, not capital structure). Cash flows to equity are constrained by **State Bank of Vietnam (SBV) Circular 41/2016 (Basel II CAR $\ge 8.0\%$ or target $11.0\%$)**:
  $$\text{Required Equity}_t = \text{Risk Weighted Assets (RWA)}_t \times \text{Target CAR}$$
  $$\Delta\text{Required Capital}_t = \text{Required Equity}_t - \text{Required Equity}_{t-1}$$
  $$\text{Free Cash Flow to Equity (FCFE)}_t = \text{Net Income}_t - \Delta\text{Required Capital}_t$$
- **Formulation**:
  $$FV_{\text{Bank\_ECF}} = \sum_{t=1}^5 \frac{\text{FCFE}_t}{(1 + K_e)^t} + \frac{\text{FCFE}_5 \times (1 + g_n)}{(K_e - g_n)(1 + K_e)^5} \div \text{Shares}$$
  Combined with **P/B - ROE Matrix**:
  $$FV_{\text{Bank\_Composite}} = 0.60 \cdot FV_{\text{Bank\_ECF}} + 0.40 \cdot \left(\text{BVPS} \times \frac{\text{ROE} - g_n}{K_e - g_n}\right)$$

---

### 5.3 Model 18: AFFO DCF & Cap Rate Model — Real Estate Developers & REITs
- **Target Sectors**: ICB 8600 (Real Estate).
- **Concept**: Real estate cash generation based on Net Operating Income (NOI) capitalized at market Cap Rate, plus project landbank discounted pipeline.
- **Formulation**:
  $$\text{NOI} = \text{Rental Revenue} - \text{Property Operating Expenses}$$
  $$\text{Operating Portfolio Value} = \frac{\text{NOI}}{\text{Cap Rate}_{\text{VN}}}$$
  where $\text{Cap Rate}_{\text{VN}} = 8.50\%$.
  $$\text{Landbank Pipeline Value} = \sum_{j=1}^M \frac{\text{Projected Landbank Cash Flow}_j}{(1 + WACC)^{t_j}} \times (1 - \text{Legal Discount } 20\%)$$
  $$\text{Total RNAV} = \text{Operating Portfolio Value} + \text{Landbank Pipeline Value} + \text{Cash} - \text{Debt}$$
  $$FV_{\text{AFFO\_REIT}} = \frac{\text{Total RNAV}}{\text{Shares Outstanding}}$$

---

### 5.4 Model 19: Unbundled SOTP & Regulated Asset Base (RAB) — Telecom & Infrastructure
- **Target Sectors**: ICB 6500 (Telecommunications), ICB 7500 (Utilities / Infrastructure).
- **Concept**: Unbundles company into **NetCo (Infrastructure/Towers/Grid)** under Regulated Asset Base (RAB) and **ServeCo (Digital Services/Retail)** under EV/EBITDA multiple:
  $$\text{EV}_{\text{NetCo}} = \text{Regulated Asset Base (RAB)} \times (1 + \text{Allowed Return Spread})$$
  $$\text{EV}_{\text{ServeCo}} = \text{EBITDA}_{\text{ServeCo}} \times \text{Multiple}_{\text{Digital}}$$
  $$\text{Total EV} = \text{EV}_{\text{NetCo}} + \text{EV}_{\text{ServeCo}}$$
  $$FV_{\text{SOTP}} = \frac{\text{Total EV} - \text{Net Debt}}{\text{Shares Outstanding}}$$

---

### 5.5 Model 20: Adjusted Present Value (APV) — Industrials & High Debt
- **Target Sectors**: ICB 2700 (Industrial Goods & Services), ICB 1700 (Basic Resources / Steel).
- **Concept**: Decouples operational value from financing side effects (interest tax shields and expected financial distress costs).
- **Formulation**:
  $$APV = V_{\text{unlevered}} + PV(\text{Interest Tax Shield}) - PV(\text{Financial Distress})$$
  1. **Unlevered Firm Value ($V_{\text{unlevered}}$)**:
     $$V_{\text{unlevered}} = \sum_{t=1}^5 \frac{\text{FCFF}_t}{(1 + K_u)^t} + \frac{\text{FCFF}_5 \times (1 + g_n)}{(K_u - g_n)(1 + K_u)^5}$$
     where $K_u = R_f + \beta_{\text{unlevered}} \cdot \text{ERP}$, and $\beta_{\text{unlevered}} = \frac{\beta_{\text{levered}}}{1 + (1 - t_c) \frac{D}{E}}$.
  2. **PV of Interest Tax Shield**:
     $$PV(\text{Tax Shield}) = \sum_{t=1}^5 \frac{t_c \times K_d \times \text{Debt}_t}{(1 + K_d)^t} + \frac{t_c \times \text{Debt}_5 \times g_n}{K_d - g_n}$$
  3. **PV of Financial Distress**:
     $$PV(\text{Distress}) = \pi_{\text{default}} \times \text{Distress Cost} \times V_{\text{unlevered}}$$
     where $\pi_{\text{default}} = \frac{1}{1 + e^{Z_{\text{Altman}} - 1.8}}$ and $\text{Distress Cost} = 25\%$.
  4. **Fair Value**:
     $$FV_{\text{APV}} = \frac{APV - \text{Debt} + \text{Cash}}{\text{Shares Outstanding}}$$

---

### 5.6 Model 21: Economic Value Added (EVA & MVA) — Consumer Staples & Retail
- **Target Sectors**: ICB 3000 (Consumer Goods), ICB 5000 (Consumer Services / Retail).
- **Concept**: Stern Stewart Economic Value Added measuring true economic value created above total cost of capital.
- **Formulation**:
  $$\text{EVA}_t = \text{NOPAT}_t - (WACC \times \text{Invested Capital}_{t-1})$$
  $$\text{Market Value Added (MVA)} = \sum_{t=1}^5 \frac{\text{EVA}_t}{(1 + WACC)^t} + \frac{\text{EVA}_5 \times (1 + g_n)}{(WACC - g_n)(1 + WACC)^5}$$
  $$\text{Total Enterprise Value} = \text{Invested Capital}_0 + \text{MVA}$$
  $$FV_{\text{EVA}} = \frac{\text{Enterprise Value} - \text{Net Debt}}{\text{Shares Outstanding}}$$

---

### 5.7 Model 22: 3-Stage Dividend Discount Model (DDM / H-Model) — Utilities & Power
- **Target Sectors**: ICB 7000 (Utilities - Power, Water, Gas).
- **Concept**: Regulated utilities distribute predictable cash dividends. We apply the **Fuller-Hsia 3-Stage / H-Model**:
  - Stage 1: High dividend growth $g_a$ for $T$ years.
  - Stage 2: Linear transition from $g_a$ to long-term growth $g_n$ over $2H$ years.
  - Stage 3: Perpetual steady growth $g_n$.
- **Formulation**:
  $$FV_{\text{DDM}} = \frac{D_0 \times (1 + g_n)}{K_e - g_n} + \frac{D_0 \times H \times (g_a - g_n)}{K_e - g_n}$$
  where:
  - $D_0 = \text{Trailing Cash Dividend Per Share}$
  - $H = 2.5 \text{ years (half-life of transition)}$
  - $g_a = \text{historical 3-year dividend CAGR}$
  - $g_n = 4.0\%$

---

## 6. Stress-Test Scenarios & 2D Sensitivity Grid (R1.4)

### 6.1 Bear / Base / Bull Parameter Perturbation Matrix

| Parameter / Driver | Bear Scenario (Downside Stress) | Base Scenario (Consensus Fair) | Bull Scenario (Optimistic Expansion) |
|---|---|---|---|
| **Revenue Growth ($g$)** | $g_{\text{base}} - 2.50\%$ (Min $2.0\%$) | Historical / Consensus CAGR | $g_{\text{base}} + 2.50\%$ (Max $25.0\%$) |
| **Operating Margin (EBIT Margin)** | Base Margin $\times 0.85$ (15% compression) | Base TTM Margin | Base Margin $\times 1.10$ (10% expansion) |
| **WACC / Discount Rate** | $WACC_{\text{base}} + 1.50\%$ (+150 bps) | Baseline 5-Factor WACC | $WACC_{\text{base}} - 1.00\%$ (-100 bps) |
| **Cost of Equity ($K_e$)** | $K_{e, \text{base}} + 1.50\%$ | Baseline 5-Factor $K_e$ | $K_{e, \text{base}} - 1.00\%$ |
| **Terminal Growth Rate ($g_n$)** | $2.50\%$ | $3.50\%$ | $4.25\%$ |
| **Target Multiple (P/E, P/B, EV/EBITDA)** | 25th percentile of peers | Median of peers | 75th percentile of peers |
| **Exit Premium Target** | $+10.0\%$ | $+20.0\%$ | $+30.0\%$ |

---

### 6.2 2D Sensitivity Matrix ($5 \times 5$ Grid)
The engine generates a complete 2D matrix evaluating Intrinsic Value across 5 WACC steps ($\text{WACC} - 2.0\%, \text{WACC} - 1.0\%, \text{WACC}, \text{WACC} + 1.0\%, \text{WACC} + 2.0\%$) and 5 Terminal Growth steps ($g_n - 1.5\%, g_n - 0.75\%, g_n, g_n + 0.75\%, g_n + 1.5\%$).

```
                      TERMINAL GROWTH RATE (g_n)
         ┌──────────┬──────────┬──────────┬──────────┬──────────┐
         │ gn - 1.5%│gn - 0.75%│  gn Base │gn + 0.75%│ gn + 1.5%│
 ┌───────┼──────────┼──────────┼──────────┼──────────┼──────────┤
 │W-2.0% │  FV_1,1  │  FV_1,2  │  FV_1,3  │  FV_1,4  │  FV_1,5  │
 │W-1.0% │  FV_2,1  │  FV_2,2  │  FV_2,3  │  FV_2,4  │  FV_2,5  │
W│W Base │  FV_3,1  │  FV_3,2  │ FV_BASE  │  FV_3,4  │  FV_3,5  │
A│W+1.0% │  FV_4,1  │  FV_4,2  │  FV_4,3  │  FV_4,4  │  FV_4,5  │
C│W+2.0% │  FV_5,1  │  FV_5,2  │  FV_5,3  │  FV_5,4  │  FV_5,5  │
 └───────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

---

## 7. Adaptive Multi-Algo Weighting & Outlier Rejection

### 7.1 Historical Prediction Error Tracking
For each model $m \in [1 \dots 22]$, evaluate its quarter-by-quarter fair value prediction $FV_{m, t}$ against future realizable stock price $P_{t+k}$ ($k = 2 \text{ quarters / 6 months}$ ahead):

1. **SMAPE (Symmetric Mean Absolute Percentage Error)**:
   $$\text{SMAPE}_m = \frac{1}{T} \sum_{t=1}^T \frac{|FV_{m, t} - P_{t+k}|}{(|FV_{m, t}| + |P_{t+k}|) / 2} \times 100\%$$
2. **MALE (Mean Absolute Log Error)**:
   $$\text{MALE}_m = \frac{1}{T} \sum_{t=1}^T |\ln(FV_{m, t}) - \ln(P_{t+k})|$$
3. **WMAPE (Weighted Mean Absolute Percentage Error)**:
   $$\text{WMAPE}_m = \frac{\sum_{t=1}^T |FV_{m, t} - P_{t+k}|}{\sum_{t=1}^T P_{t+k}}$$
4. **RMSLE (Root Mean Squared Logarithmic Error)**:
   $$\text{RMSLE}_m = \sqrt{\frac{1}{T} \sum_{t=1}^T (\ln(FV_{m, t} + 1) - \ln(P_{t+k} + 1))^2}$$

---

### 7.2 Inverse Variance Weighting (IVW)
The model weights $w_m$ are assigned inversely proportional to historical variance of error $\sigma_m^2$:

$$\sigma_m^2 = \frac{1}{T} \sum_{t=1}^T \left(\frac{FV_{m, t} - P_{t+k}}{P_{t+k}}\right)^2$$
$$w_m = \frac{1 / (\sigma_m^2 + \epsilon)}{\sum_{j=1}^M 1 / (\sigma_j^2 + \epsilon)}$$
where $\epsilon = 10^{-6}$ prevents division by zero.

---

### 7.3 Outlier Filtering & Robust Aggregation
Before combining model outputs:
1. **Model Applicability Gate**:
   - Filter out models inapplicable to the company's sector (e.g. Banks skip EV/EBITDA, Value Driver DCF, AFFO; Industrials skip Banking Equity Cash Flow).
2. **IQR 1.5x Fence Rejection**:
   - Let $\mathcal{V} = \{FV_1, FV_2, \dots, FV_K\}$ be the valid model outputs.
   - Calculate $Q_1 = \text{Percentile}_{25}(\mathcal{V}), Q_3 = \text{Percentile}_{75}(\mathcal{V}), \text{IQR} = Q_3 - Q_1$.
   - Reject any model $m$ where $FV_m < Q_1 - 1.5 \cdot \text{IQR}$ or $FV_m > Q_3 + 1.5 \cdot \text{IQR}$.
3. **Composite Fair Value Calculation**:
   $$FV_{\text{Composite}} = \frac{\sum_{m \in \mathcal{V}_{\text{filtered}}} w_m \cdot FV_m}{\sum_{m \in \mathcal{V}_{\text{filtered}}} w_m}$$

---

### 7.4 Cold-Start & Zero Track Record Fallback Hierarchy
When a stock has fewer than 4 quarters of historical data:
1. **Tier 1 (Prior Sector Weights)**: Use pre-calibrated sector IVW weights based on the ICB industry group.
2. **Tier 2 (Category Equal Weights)**: Equal weight within each active model tier ($1/3$ Relative, $1/3$ Absolute, $1/3$ Sector).
3. **Tier 3 (Uniform 1/K)**: $w_m = 1/K$ for all $K$ surviving models.

---

## 8. Sector Applicability Matrix (ICB Mapping)

| ICB Sector Code | Sector Name | Primary Applicable Models | Inactive / Bypassed Models |
|---|---|---|---|
| **VNBNK (8300)** | Ngân Hàng (Banks) | Model 4 (P/B), Model 10 (RIM), Model 17 (Bank ECF/CAR), Model 1 (P/E), Model 12 (Graham) | Model 3 (P/FCF), Model 6 (EV/EBITDA), Model 9 (DCF), Model 18 (AFFO), Model 20 (APV) |
| **VNSEC (8700)** | Chứng Khoán (Securities) | Model 4 (P/B), Model 1 (P/E), Model 10 (RIM), Model 14 (Acquirer's) | Model 6 (EV/EBITDA), Model 18 (AFFO), Model 22 (DDM) |
| **VNREA (8600)** | Bất Động Sản (Real Estate) | Model 18 (AFFO REIT/RNAV), Model 4 (P/B RKV), Model 8 (P/AFFO), Model 9 (DCF), Model 10 (RIM) | Model 2 (P/S), Model 13 (Rule of 40) |
| **VNINS (8500)** | Bảo Hiểm (Insurance) | Model 17 (ECF/Embedded Value), Model 4 (P/B), Model 10 (RIM), Model 22 (DDM) | Model 6 (EV/EBITDA), Model 9 (DCF) |
| **VNENG (0500)** | Dầu Khí & Năng Lượng | Model 6 (EV/EBITDA), Model 9 (Value Driver DCF), Model 20 (APV), Model 1 (Blended P/E) | Model 13 (Rule of 40), Model 17 (Bank ECF) |
| **VNUTI (7500)** | Tiện Ích (Điện, Nước) | Model 22 (3-Stage DDM), Model 19 (Unbundled RAB), Model 6 (EV/EBITDA), Model 9 (DCF) | Model 13 (Rule of 40), Model 17 (Bank ECF) |
| **VNMAT (1700)** | Tài Nguyên & Thép | Model 20 (APV), Model 6 (EV/EBITDA), Model 1 (CAPE P/E), Model 4 (P/B), Model 9 (DCF) | Model 13 (Rule of 40), Model 17 (Bank ECF) |
| **VNFOB (3500)** | Thực Phẩm & Tiêu Dùng | Model 21 (EVA), Model 15 (Owner's Earnings), Model 1 (P/E), Model 9 (Value Driver DCF) | Model 17 (Bank ECF), Model 18 (AFFO) |
| **VNTEC (9500)** | Công Nghệ Thông Tin | Model 13 (Rule of 40/X), Model 9 (Value Driver DCF), Model 15 (Owner's Earnings), Model 1 (P/E) | Model 4 (P/B), Model 18 (AFFO), Model 22 (DDM) |
| **VNHEA (4500)** | Y Tế & Dược Phẩm | Model 16 (rNPV Pipeline), Model 9 (DCF), Model 15 (Owner's Earnings), Model 1 (P/E) | Model 18 (AFFO), Model 17 (Bank ECF) |

---

## 9. Boundary Conditions & Numerical Safeguards

1. **Non-Negativity Constraint**:
   $$FV_m \ge 0.0 \quad \forall m \in [1 \dots 22]$$
2. **Cap on Outlier Values**:
   $$FV_m \le 10.0 \times \text{Current Price}$$
3. **Discount Rate vs Terminal Growth Singularity**:
   $$\text{Denominator} = \max(WACC - g_n, 0.015)$$
4. **Negative Earnings / Cash Flows**:
   - Absolute models using cash flows switch to normalized turn-around margins or 5-year average profitability.
5. **Negative Equity / Book Value**:
   - P/B and RIM models deactivate; engine defaults to Liquidation NAV or Revenue-based multiples.

---

## 10. Summary of Key Python Interfaces for Implementation

```python
class ValuationEngine:
    """Institutional 22-Model Valuation Engine."""
    
    def __init__(self, data_lake: Optional[DiskDataLake] = None):
        self.data_lake = data_lake
        
    def calculate_wacc_5factor(self, symbol: str, stock_snap: Dict[str, Any]) -> Dict[str, float]:
        """Calculates 5-Factor VN CAPM, Damodaran Cost of Debt, and WACC."""
        ...
        
    def evaluate_all_22_models(self, symbol: str) -> Dict[str, Any]:
        """Evaluates all 8 relative, 7 absolute, and 7 sector models."""
        ...
        
    def calculate_adaptive_weights(self, symbol: str, model_outputs: Dict[str, float]) -> Dict[str, float]:
        """Calculates IVW and multi-error metric weights."""
        ...
        
    def generate_scenario_matrix(self, symbol: str, base_valuation: Dict[str, Any]) -> Dict[str, Any]:
        """Generates Bear, Base, Bull scenarios and 5x5 WACC/Growth sensitivity matrix."""
        ...
        
    def get_comprehensive_valuation(self, symbol: str) -> Dict[str, Any]:
        """End-to-end composite fair value API method."""
        ...
```

This specification provides the complete mathematical and architectural foundation required to implement `services/valuation_engine.py` cleanly, robustly, and with zero ambiguity.
