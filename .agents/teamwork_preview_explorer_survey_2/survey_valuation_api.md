# COMPREHENSIVE SURVEY REPORT: VALUATION ENGINES, BACKTEST FRAMEWORK & API ECOSYSTEM

**Author:** `teamwork_preview_explorer_survey_2`  
**Date:** 2026-09-02  
**Target File:** `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_survey_2\survey_valuation_api.md`  
**Scope:** Deep-dive architectural survey of `services/valuation_engine.py`, `services/fair_value_backtest_service.py`, `server.py`, related core modules, and integration blueprints for R3, R4, and R5.

---

## 1. Executive Summary

The quantitative valuation and backtesting ecosystem of `Vibecoding vnstock` is an institutional-grade platform calibrated specifically for the Vietnamese equity market (HOSE, HNX, UPCOM). 

The platform currently features:
1. **A 22-Model Valuation Suite (`services/valuation_engine.py`)** spanning 8 Relative Multiples, 7 Absolute Intrinsic Models, and 7 Sector-Specific Models, driven by a 5-Factor Vietnam CAPM, Aswath Damodaran Synthetic Credit Rating table, 4-Quadrant Altman Z'' + Beneish M-Score risk firewalls, Rhodes-Kropf (RKV) misvaluation decomposition, and multi-algo adaptive weighting (Sector Blended vs. Omnibus Loss Metrics).
2. **A 3-Mode Modular Backtest Service (`services/fair_value_backtest_service.py`)** enabling Hybrid Funnel (Screener + Valuation MoS), Pure Valuation, and Pure Screening backtests across historical quarters (2016–2026) with realistic transaction friction (fees, taxes, slippage), quarterly equity curve amortization, and a 22-model tournament matrix.
3. **A FastAPI Web Server (`server.py`)** exposing REST endpoints with asynchronous background lifespans, CORS middleware, standardized JSON response envelopes `{"status": "success", "data": ...}`, and streaming export capabilities.

This survey details the exact mathematical formulas, current code structures, data interfaces, and concrete integration blueprints for:
- **R3 (Liquidity Distress Firewall & Negative Cash Risk Alert)**
- **R4 (Capital Allocation & Debt Schedule Engine Integration)**
- **R5 (Modano 3-Way Forecasting & Excel Export REST Endpoints)**

---

## 2. Valuation Engine Architecture Deep-Dive (`services/valuation_engine.py`)

### 2.1 Macro & Capital Cost Engine (`WACCEngine`)

The cost of capital is evaluated via a customized 5-Factor Vietnam Capital Asset Pricing Model (Ke) and Damodaran Synthetic Credit Rating table (Kd).

```
                      ┌──────────────────────────────────────────────┐
                      │              5-Factor VN CAPM                │
                      │ Ke = Rf + Beta_adj*ERP + SMB + HML + UMD    │
                      │      + ILLIQ + RMW                           │
                      └──────────────────────┬───────────────────────┘
                                             │
┌─────────────────────────────┐              │              ┌─────────────────────────────┐
│  Interest Coverage Ratio    │              │              │  Capital Structure Weights  │
│  ICR = EBIT / Interest_Exp  ├──────────────┼─────────────►│  We = E / (E + D)           │
│  -> Damodaran Rating -> Kd  │              │              │  Wd = D / (E + D)           │
└─────────────────────────────┘              │              └──────────────┬──────────────┘
                                             ▼                             │
                      ┌──────────────────────────────────────────────┐     │
                      │               WACC Calculator                │◄────┘
                      │ WACC = We * Ke + Wd * Kd * (1 - Tax_Rate)    │
                      │ Clamped bounded: [8.5%, 18.5%]               │
                      └──────────────────────────────────────────────┘
```

#### Factor Breakdown:
1. **Benchmark Risk-Free Rate ($R_f$):** `DEFAULT_RF = 0.0500` (5.00% Vietnam 10-Year Government Bond benchmark).
2. **Equity Risk Premium (ERP):** `DEFAULT_ERP = 0.0815` (8.15% = Mature ERP 4.60% + Vietnam Country Risk Premium CRP 3.55%).
3. **Blume Adjusted Beta:** $\beta_{\text{adj}} = 0.67 \cdot \beta_{\text{raw}} + 0.33 \cdot 1.0$.
4. **Size Premium (SMB):**
   - Market Cap $> 25,000\text{B VND} \implies 0.00\%$
   - $5,000\text{B} - 25,000\text{B VND} \implies 1.00\%$
   - $1,000\text{B} - 5,000\text{B VND} \implies 2.00\%$
   - $< 1,000\text{B VND} \implies 3.00\%$
5. **Value Premium (HML):** High-minus-low book-to-market distress spread:
   $$h = \text{clamp}\left(\frac{PB_{\text{sector}} - PB}{PB_{\text{sector}}}, -1.0, 1.0\right), \quad \text{HML} = h \cdot 1.50\%$$
6. **Momentum (UMD):** Contrarian 12M-1M return spread factor:
   $$m = -\text{clamp}\left(\frac{R_{12\text{M}} - R_{1\text{M}}}{0.30}, -1.0, 1.0\right) \cdot 0.5, \quad \text{UMD} = m \cdot 1.00\%$$
7. **Amihud Illiquidity Premium (ILLIQ):** Scaled by Average Daily Turnover (ADTV in Billion VND):
   - $\text{ADTV} > 50\text{B} \implies 0.00\%$
   - $10\text{B} - 50\text{B} \implies 0.50\%$
   - $2\text{B} - 10\text{B} \implies 1.25\%$
   - $< 2\text{B} \implies 2.50\%$
8. **Robust Profitability Premium (RMW):** Operating profitability scale:
   $$r = \text{clamp}\left(\frac{15.0 - \text{ROE}}{10.0}, -1.0, 1.0\right), \quad \text{RMW} = r \cdot 1.20\%$$
9. **Bounded Cost of Equity ($K_e$):** $\text{clamp}(K_{e,\text{raw}}, 0.085, 0.220)$.

#### Damodaran Synthetic Cost of Debt ($K_d$):
Calculated by mapping $\text{ICR} = \frac{\text{EBIT}}{\text{Interest Expense}}$ to credit ratings and default spreads:
- Large Cap ($> 5,000\text{B VND}$):
  - $\text{ICR} \ge 8.50 \implies \text{AAA (+0.65\%)}$
  - $\text{ICR} \ge 6.50 \implies \text{AA (+0.90\%)}$
  - $\text{ICR} \ge 5.50 \implies \text{A+ (+1.15\%)}$
  - $\text{ICR} \ge 4.25 \implies \text{A (+1.35\%)}$
  - $\text{ICR} \ge 3.00 \implies \text{A- (+1.60\%)}$
  - $\text{ICR} \ge 2.50 \implies \text{BBB (+2.10\%)}$
  - $\text{ICR} \ge 2.25 \implies \text{BB+ (+2.85\%)}$
  - $\text{ICR} \ge 2.00 \implies \text{BB (+3.40\%)}$
  - $\text{ICR} \ge 1.75 \implies \text{B+ (+4.25\%)}$
  - $\text{ICR} \ge 1.50 \implies \text{B (+5.25\%)}$
  - $\text{ICR} \ge 1.25 \implies \text{B- (+6.50\%)}$
  - $\text{ICR} \ge 0.80 \implies \text{CCC (+8.50\%)}$
  - $\text{ICR} \ge 0.50 \implies \text{CC (+10.00\%)}$
  - $\text{ICR} < 0.50 \implies \text{D (+12.50\%)}$
- Small Cap ($\le 5,000\text{B VND}$): Higher ICR thresholds (e.g., AAA requires $\text{ICR} \ge 12.50$).
- After-tax Cost of Debt: $K_{d,\text{after-tax}} = (R_f + \text{Spread}) \cdot (1 - \text{Tax Rate})$.

---

### 2.2 Risk Firewalls & Anti-Trap Diagnostics (`RiskFirewallEngine`)

1. **4-Factor Emerging Market Altman $Z''$-Score:**
   $$Z'' = 6.56 \frac{\text{Working Capital}}{\text{Total Assets}} + 3.26 \frac{\text{Retained Earnings}}{\text{Total Assets}} + 6.72 \frac{\text{EBIT}}{\text{Total Assets}} + 1.05 \frac{\text{Book Equity}}{\text{Total Liabilities}}$$
   - Safe Zone: $Z'' \ge 2.60$
   - Grey Zone: $1.10 \le Z'' < 2.60$
   - Distress Zone: $Z'' < 1.10$

2. **Beneish 8-Variable M-Score:**
   $$M = -4.84 + 0.920 \cdot \text{DSRI} + 0.528 \cdot \text{GMI} + 0.404 \cdot \text{AQI} + 0.892 \cdot \text{SGI} + 0.115 \cdot \text{DEPI} - 0.172 \cdot \text{SGAI} + 4.037 \cdot \text{TATA} + 0.0327 \cdot \text{LVGI}$$
   - Manipulator: $M \ge -1.78$
   - Safe: $M < -1.78$

3. **4-Quadrant Institutional Matrix:**
   | Quadrant | $Z''$ Zone | Beneish $M$ | Institutional Action |
   |---|---|---|---|
   | **Safe Institutional (Q1)** | $\ge 1.10$ | $< -1.78$ | Approved for composite valuation |
   | **Distressed Turnaround (Q2)** | $< 1.10$ | $< -1.78$ | Flagged for deep value distress penalty |
   | **Toxic Exclusion (Q3)** | $< 1.10$ | $\ge -1.78$ | Hard disqualification (`firewall_passed = False`) |
   | **Forensic Trap (Q4)** | $\ge 1.10$ | $\ge -1.78$ | Hard disqualification (`firewall_passed = False`) |

4. **Rhodes-Kropf (RKV) Enterprise Valuation Decomposition:**
   $$\ln(M/B) = \underbrace{(m - v_i)}_{\text{Firm Misvaluation}} + \underbrace{(v_i - v_j)}_{\text{Sector Time-Series Error}} + \underbrace{(v_j - b)}_{\text{Long-Run Sector Growth}}$$
   Where $v_i = b + \ln(\text{Justified } PB)$, $v_j = b + \ln(PB_{\text{sector}})$, $\text{Justified } PB = \frac{\text{ROE} - g}{K_e - g}$.
   - Classifies: `VALUE TRAP` (if $PB < 1.5$ and $v_b < 1.0$), `TRUE DEEP VALUE` (if $PB < 1.5$ and $P/V < 0.85$), `OVERVALUED`, or `UNDERVALUED`.

5. **Dynamic Margin of Safety (MOS):**
   $$\text{MOS}_{\text{dynamic}} = \text{MOS}_{\text{base}} \cdot \text{clamp}(1.0 + 0.5 \cdot (\beta_- - 1.0), 0.70, 2.00) + \Delta_{\text{Altman}} + \Delta_{\text{Beneish}} + \Delta_{D/E}$$
   Clamped bounded within $[10.0\%, 60.0\%]$.

---

### 2.3 The 22 Quantitative Valuation Models Breakdown (`ValuationModelsSuite`)

| # | Model ID | Name | Category | Core Mathematical Formula | Key Inputs |
|---|---|---|---|---|---|
| **1** | `blended_pe` | Blended P/E with CAPE | Relative | $FV = \text{Target P/E} \cdot (0.60 \cdot \text{EPS}_{\text{TTM}} + 0.40 \cdot \text{EPS}_{\text{cyclical}})$ | $\text{EPS}_{\text{TTM}}$, hist EPS, sector P/E, EPS growth |
| **2** | `ps_margin_adj` | Margin-Adjusted P/S | Relative | $FV = \text{Sector P/S} \cdot \left(\frac{\text{Net Margin}}{\text{Sector Margin}}\right)^{0.65} \cdot \text{SPS}$ | Sales/share, Net Margin, Sector P/S |
| **3** | `p_fcf` | Price-to-FCF Yield | Relative | $FV = \text{Target P/FCF} \cdot \max(\text{FCFPS}, 0.05 \cdot \text{SPS})$ | FCF/share, SPS, Sector P/FCF |
| **4** | `pb_rhodes_kropf` | P/B with RKV Filter | Relative | $FV = (0.50 \cdot \text{Justified P/B} + 0.50 \cdot \text{Sector P/B}) \cdot \text{BVPS} \cdot \text{Haircut}_{\text{RKV}}$ | BVPS, ROE, $K_e$, Sector P/B, RKV flag |
| **5** | `p_tbv` | Price-to-Tangible Book | Relative | $FV = \text{Sector P/TBV} \cdot \text{clamp}(\text{ROIC}/\text{WACC}, 0.6, 1.8) \cdot \text{TBVPS}$ | TBVPS, BVPS, ROIC, WACC, Sector P/TBV |
| **6** | `ev_ebitda` | Blended EV/EBITDA | Relative | $EV = \text{Target EV/EBITDA} \cdot \text{EBITDA}$; $FV = (EV - \text{Debt} + \text{Cash} - \text{Minority}) / \text{Shares}$ | EBITDA, Debt, Cash, Shares, Sector EV/EBITDA |
| **7** | `p_cf` | Price-to-CFO | Relative | $FV = \text{Sector P/CF} \cdot (1 + 0.5 \cdot \text{QualityAdj}) \cdot \text{CFOPS}$ | CFO/share, PAT/share, Sector P/CF |
| **8** | `p_affo` | Price-to-AFFO Multiple | Relative | $FV = \text{Sector P/AFFO} \cdot \max(\text{AFFO}, 0.5 \cdot \text{NI}) / \text{Shares}$ | AFFO, Net Income, Shares, Sector P/AFFO |
| **9** | `dcf_2stage_mckinsey` | Extended 2-Stage McKinsey DCF | Absolute | $PV = \sum_{t=1}^5 \frac{\text{NOPAT}_t (1 - g_t/\text{ROIC}_t)}{(1+\text{WACC})^t} + \frac{TV_5}{(1+\text{WACC})^5}$; $TV_5 = \frac{\text{NOPAT}_5(1+g_n)(1 - g_n/\text{ROIC}_n)}{\text{WACC} - g_n}$ | EBIT, ROIC, WACC, Debt, Cash, Shares, $g_1$, $g_n$, Tax |
| **10** | `rim_edwards_bell_ohlson` | Residual Income Model (RIM) | Absolute | $FV = \left(BV_0 + \sum_{t=1}^5 \frac{(\text{ROE}_t - K_e) BV_{t-1}}{(1+K_e)^t} + \frac{RI_5(1+g_n)}{(1+K_e - \omega)(1+K_e)^5}\right) / \text{Shares}$ | Book Equity, ROE, $K_e$, Payout Ratio, $\omega_{\text{fade}} = 0.85$ |
| **11** | `greenwald_epv` | Greenwald Earnings Power Value | Absolute | $\text{EPV}_{\text{firm}} = \frac{\text{Normalized NOPAT}}{\text{WACC}}$; $FV = (\text{EPV}_{\text{firm}} + \text{Cash} - \text{Debt}) / \text{Shares}$ | Revenue, normalized EBIT margin, WACC, Depr, MaintCapEx |
| **12** | `graham_growth` | Graham Growth Formula | Absolute | $FV = 0.50 \sqrt{22.5 \cdot \text{EPS} \cdot \text{BVPS}} + 0.50 \left(\text{EPS}(8.5 + 1.5g)\frac{4.4}{Y}\right)$ | EPS, BVPS, Growth $g$, Bond Yield $Y$ |
| **13** | `rule_of_40_growth` | Rule of 40 / Rule of X | Absolute | $\text{Multiple} = f(\text{RevGrowth} + \text{FCFMargin}, 2\cdot\text{RevGrowth}+\text{FCFMargin})$; $FV = (\text{Multiple}\cdot\text{Rev} - \text{NetDebt}) / \text{Shares}$ | RevGrowth%, FCFMargin%, Revenue, NetDebt, Shares |
| **14** | `acquirers_multiple_ev_ebit` | Tobias Carlisle Acquirer's Multiple | Absolute | $EV = \min(\text{Sector EV/EBIT}, 10.0) \cdot \text{EBIT}$; $FV = (EV - \text{NetDebt}) / \text{Shares}$ | EBIT, Revenue, NetDebt, Shares, Sector EV/EBIT |
| **15** | `buffett_owners_earnings` | Warren Buffett Owner's Earnings DCF | Absolute | $\text{OE} = \text{OCF} - \text{MaintCapEx}$; $\text{MaintCapEx} = \text{TotalCapEx} - \Delta\text{Rev}\cdot\frac{\text{GrossPPE}}{\text{Rev}}$; $FV = \sum \frac{\text{OE}_t}{(1+K_e)^t} + \frac{TV}{(1+K_e)^5}$ | OCF, Net Income, CapEx, Rev, PrevRev, GrossPPE, $\Delta\text{WC}$, $K_e$ |
| **16** | `pharma_rnpv` | Risk-Adjusted NPV (rNPV) | Sector (Pharma) | $FV = \sum (p_{s,k} \cdot \text{NPV}_k) + \text{Base EPV} + \text{Net Cash}$ | Pipeline project NPVs, success probabilities, Base EPV |
| **17** | `bank_equity_cash_flow` | Banking Equity CF & Basel II | Sector (Banks) | $\text{ReqEquity}_t = \text{RWA}_t \cdot \text{CAR}$; $\text{FCFE}_t = \text{NI}_t - \Delta\text{ReqEquity}_t$; $FV = 0.60 \cdot \text{PV}(\text{FCFE}) + 0.40 \cdot \text{Justified P/B}$ | Net Income, RWA, Equity, ROE, $K_e$, Target CAR |
| **18** | `reit_affo_dcf` | REIT AFFO & RNAV | Sector (Real Estate) | $\text{RNAV} = \frac{\text{NOI}}{\text{CapRate}_{\text{VN}}} + \text{Landbank Pipeline} + \text{Cash} - \text{Debt}$ | NOI, Cap Rate, Landbank value, Cash, Debt, Shares |
| **19** | `telecom_unbundled_sotp` | RAB & Unbundled Infra SOTP | Sector (Telco/Infra) | $EV_{\text{RAB}} = \text{RAB} \cdot \frac{r_{\text{allowed}} - g}{\text{WACC} - g}$; $FV = (EV_{\text{RAB}} - \text{NetDebt}) / \text{Shares}$ | Regulated Asset Base, WACC, Allowed return $r$, Net Debt |
| **20** | `industrial_apv` | Adjusted Present Value (APV) | Sector (Materials) | $\text{APV} = V_{\text{unlevered}} + PV(\text{Tax Shield}) - PV(\text{Distress Cost})$ | EBIT, Debt, Cash, Unlevered Beta, $K_d$, $Z''$-score |
| **21** | `consumer_eva_mva` | Economic Value Added (EVA & MVA) | Sector (Consumer) | $\text{EVA} = \text{NOPAT} - \text{WACC} \cdot \text{IC}$; $EV = \text{IC}_0 + \frac{\text{EVA}_0 (1+g)}{\text{WACC} - g}$; $FV = (EV - \text{NetDebt})/\text{Shares}$ | EBIT, Invested Capital (IC), WACC, Net Debt, Shares |
| **22** | `utilities_3stage_ddm` | 3-Stage Fuller-Hsia H-Model DDM | Sector (Utilities) | $FV = \frac{D_0 (1 + g_n) + D_0 \cdot H \cdot (g_a - g_n)}{K_e - g_n}$ | Dividend/share $D_0$, Initial growth $g_a$, Terminal $g_n$, Half-life $H$ |

---

### 2.4 Multi-Algo Adaptive Weighting & Composite Calculation (`AdaptiveWeightingEngine`)

1. **1.5x IQR Outlier Rejection Fence:**
   Computes $Q_1, Q_3, \text{IQR} = Q_3 - Q_1$. Rejects models where $FV < Q_1 - 1.5\cdot\text{IQR}$ or $FV > Q_3 + 1.5\cdot\text{IQR}$ (status set to `OUTLIER_REJECTED`).
2. **Dual-Mode Weighting Schemes:**
   - **Mode 1: Blended Mode (`composite_mode = 'blended'` - Default):**
     Uses structural sector weight priors (`SECTOR_WEIGHT_PRIORS`) calibrated to ICB sectors.
     - *Banking (VNFIN/VNBNK):* P/B RKV (35%), Bank Equity CF (30%), RIM (20%), Blended P/E (15%).
     - *Real Estate (VNREAL):* REIT AFFO (35%), P/AFFO (25%), P/B RKV (20%), McKinsey DCF (20%).
     - *Utilities (VNUTI):* 3-Stage DDM (40%), McKinsey DCF (30%), EV/EBITDA (20%), Blended P/E (10%).
     - *Technology (VNIT):* Rule of 40 (35%), McKinsey DCF (30%), Buffett Owner's Earnings (20%), Blended P/E (15%).
     - *Materials (VNMAT):* APV (35%), EV/EBITDA (30%), Blended P/E (20%), P/B RKV (15%).
   - **Mode 2: Omnibus Master Engine (`composite_mode = 'omnibus'`):**
     Assigns dynamic weights inversely proportional to rolling prediction loss metrics:
     - `smape`: Symmetric Mean Absolute % Error ($w_i \propto 1 / \text{SMAPE}_i$).
     - `male`: Mean Absolute Log Error ($w_i \propto 1 / \text{MALE}_i$).
     - `wmape`: Weighted Mean Absolute % Error ($w_i \propto 1 / \text{WMAPE}_i$).
     - `rmsle`: Root Mean Squared Log Error ($w_i \propto 1 / \text{RMSLE}_i$).
     - `ivw`: Inverse Variance Weighting ($w_i \propto 1 / \sigma_{i}^2$).

---

### 2.5 Stress Scenarios & 2D Sensitivity Grid (`ScenarioEngine`)

- **Bear Scenario:** Growth $-1.0\%$, WACC $+1.5\%$, Operating Margin $0.85\times$.
- **Base Scenario:** Base composite fair value.
- **Bull Scenario:** Growth $+1.0\%$, WACC $-1.0\%$, Operating Margin $1.10\times$.
- **5x5 Sensitivity Grid:** WACC steps $[-2.0\%, -1.0\%, 0.0\%, +1.0\%, +2.0\%]$ vs Terminal Growth steps $[-1.5\%, -0.75\%, 0.0\%, +0.75\%, +1.5\%]$.

---

## 3. Fair Value Backtest Service Architecture (`services/fair_value_backtest_service.py`)

### 3.1 3-Mode Execution Pipeline

```
                               ┌────────────────────────────────┐
                               │   Point-in-Time Data Lake      │
                               │ historical_prices.json         │
                               │ screener_snapshot.json         │
                               │ precomputed_valuations.json    │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────────┐
                              │  Mode Selection (3 Modalities)   │
                              └────────────────┬─────────────────┘
                                               │
            ┌──────────────────────────────────┼──────────────────────────────────┐
            │                                  │                                  │
            ▼                                  ▼                                  ▼
 ┌──────────────────────┐          ┌──────────────────────┐          ┌──────────────────────┐
 │   1. HYBRID FUNNEL   │          │  2. VALUATION ONLY   │          │  3. SCREENING ONLY   │
 │ Stage 1: Screener    │          │ Stage 1: Full Market │          │ Stage 1: Screener    │
 │ (32 Factor/Guru)     │          │ (100% Coverage)      │          │ (32 Factor/Guru)     │
 │ Stage 2: Fair Value  │          │ Stage 2: Fair Value  │          │ Stage 2: Rebalance   │
 │ MoS Entry Filter     │          │ MoS Entry Filter     │          │ without MoS filter   │
 └──────────┬───────────┘          └──────────┬───────────┘          └──────────┬───────────┘
            │                                 │                                 │
            └─────────────────────────────────┼─────────────────────────────────┘
                                              │
                                              ▼
                               ┌────────────────────────────────┐
                               │  Risk Firewalls & Anti-Traps   │
                               │  - Universal Survival Firewall │
                               │  - TSMOM 12M Trend Filter      │
                               │  - Forensic M-Score            │
                               │  - Altman Z'' Toxic Exclusion  │
                               │  - Rhodes-Kropf Value Trap     │
                               └──────────────┬─────────────────┘
                                              │
                                              ▼
                               ┌────────────────────────────────┐
                               │  Real Price Bar Trade Engine   │
                               │  - Entry at Quarter Open/Close │
                               │  - Strict Friction (0.15% fee, │
                               │    0.10% tax, 0.10% slippage)  │
                               │  - Stop-Loss / Take-Profit     │
                               └──────────────┬─────────────────┘
                                              │
                                              ▼
                               ┌────────────────────────────────┐
                               │   Amortized NAV Equity Curve   │
                               │   Master Quant Metrics (CAGR,  │
                               │   Sharpe, MDD, Beta, Alpha)    │
                               │   22-Model Tournament Matrix   │
                               └────────────────────────────────┘
```

### 3.2 Key Quant Calculation Safeguards
1. **Amortized Quarterly Equity Curve:** Returns are distributed evenly across the exact quarters a trade was active ($r_q = (1 + R_{\text{total}})^{1/N} - 1$), avoiding lump-sum distortion.
2. **OLS Regression Beta & Jensen's Alpha:** Evaluated strictly against the quarterly return series of VN-Index benchmark:
   $$\beta = \frac{\text{Cov}(R_{\text{strat}}, R_{\text{bm}})}{\text{Var}(R_{\text{bm}})}, \quad \alpha = E[R_{\text{strat}}] - (R_f + \beta (E[R_{\text{bm}}] - R_f))$$
3. **Tournament Matrix:** Groups closed trade records by model name and computes empirical CAGR, Sharpe ratio, win rate %, and max drawdown per model.

---

## 4. Integration Analysis for R3: Liquidity Distress Firewall & Negative Cash Risk Alert

### 4.1 Requirement Summary
- Detect projected cash shortfalls ($\text{Cash}_t < 0$) across any period in the 5-year forecast horizon generated by the 3-Way Integrated Forecasting Engine (`services/three_statement_engine.py`).
- Integrate this diagnostic into:
  1. `services/valuation_engine.py` Risk Firewalls (with Dynamic MOS and valuation dilution penalties).
  2. `services/fair_value_backtest_service.py` screening filters (with automated exclusion and distress scoring).

### 4.2 Integration Blueprint in `services/valuation_engine.py`

#### 1. Data Contract & Detection:
The Valuation Engine receives the forecasted balance sheet and direct cash flow statements (or computes them on-the-fly via the 3-Way Engine).
Let $\text{Cash}_t$ be the projected ending cash balance for $t \in [1..5]$.

```python
@dataclass
class LiquidityDistressDiagnostic:
    has_liquidity_distress: bool
    distress_years: List[int]
    min_projected_cash: float
    max_cash_shortfall: float
    shortfall_to_revenue_pct: float
    dilution_haircut_pct: float
    mos_penalty_pct: float
    distress_verdict: str
```

#### 2. Risk Firewall Penalty Logic:
If $\min(\text{Cash}_1, \dots, \text{Cash}_5) < 0$:
- **Severity Classification:**
  - *Mild Shortfall* ($|\text{Shortfall}| \le 5\%\text{ Revenue}$): Short-term liquidity crunch $\implies \Delta\text{MOS} = +5.0\%$, Valuation Dilution Haircut $= 10.0\%$.
  - *Severe Distress* ($|\text{Shortfall}| > 5\%\text{ Revenue}$): Structural insolvency risk $\implies \Delta\text{MOS} = +15.0\%$, Valuation Dilution Haircut $= 25.0\%$.
- **Dynamic MOS Adjustment:**
  `RiskFirewallEngine.calculate_dynamic_mos` adds the liquidity distress penalty:
  $$\text{MOS}_{\text{dynamic}} \mathrel{+}= \Delta\text{MOS}_{\text{liquidity\_distress}}$$
- **Fair Value Haircut:**
  Composite Fair Value and individual intrinsic models (DCF, DDM, FCFE, Owner's Earnings) are adjusted:
  $$FV_{\text{adjusted}} = FV_{\text{raw}} \cdot (1 - \text{Dilution Haircut})$$

#### 3. Payload Schema Update (`ValuationMatrixResult`):
Add `liquidity_distress: Dict[str, Any]` into `ValuationMatrixResult` and `RiskFirewallResult.details`.

### 4.3 Integration Blueprint in `services/fair_value_backtest_service.py`

1. **New Parameter:** `filter_liquidity_distress: bool = True` in `run_backtest(...)` and presets.
2. **Execution Gate:** In Stage 2 valuation screening:
   ```python
   if filter_liquidity_distress and val_res.risk_firewall.details.get("has_liquidity_distress"):
       continue  # Exclude distressed stock from candidate basket
   ```
3. **Trade Record Annotation:** Store `liquidity_safe: bool` in `TradeRecord`.
4. **Diagnostics:** Report count and percentage of universe filtered by liquidity distress.

---

## 5. Integration Analysis for R4: Capital Allocation & Debt Schedule Engine

### 5.1 Requirement Summary
- Implement debt amortization schedules, interest payable/paid roll-forwards, and dividend payout vs. share repurchase policies in `services/debt_capital_schedule_engine.py`.
- Link dynamic debt metrics with:
  1. Damodaran synthetic credit spreads and $K_d$ in `services/valuation_engine.py`.
  2. Intrinsic valuation models (DDM, FCFE, Owner's Earnings, Extended 2-Stage McKinsey DCF).

### 5.2 Dynamic Linkage Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│             R4 Capital Allocation & Debt Schedule Engine               │
│             (services/debt_capital_schedule_engine.py)                 │
├──────────────────────────────────┬─────────────────────────────────────┤
│ Debt Schedule Roll-Forward:      │ Capital Allocation Policy:          │
│ - Opening Debt                   │ - Net Income Allocation             │
│ - Scheduled Principal Repayment  │ - Dividend Payout Ratio (%)         │
│ - New Borrowing / Refinancing    │ - Share Repurchase Budget (%)       │
│ - Ending Interest-Bearing Debt   │ - Reinvestment in Capex / Growth    │
│ - Interest Expense & Cash Paid   │ - Ending Share Count Roll-Forward   │
└────────────────┬─────────────────┴──────────────────┬──────────────────┘
                 │                                    │
                 ▼                                    ▼
┌────────────────────────────────┐   ┌───────────────────────────────────┐
│   Dynamic Damodaran Rating     │   │   Intrinsic Valuation Engines     │
│ Projected ICR_t = EBIT_t/Int_t │   │                                   │
│ Dynamic Spread -> Dynamic Kd   │   │ - DDM: Dynamic Dividends / Share  │
│ Dynamic WACC across t=1..5     │   │ - FCFE: FCFF - Int*(1-t) + NetDebt│
└────────────────────────────────┘   │ - Owner's Earnings: Real CapEx    │
                                     │ - McKinsey DCF: Dynamic Tax Shield│
                                     └───────────────────────────────────┘
```

### 5.3 Detailed Model Upgrades in `services/valuation_engine.py`

1. **Enhanced 2-Stage DCF (`dcf_2stage_mckinsey`):**
   Instead of assuming static reinvestment rates ($g / \text{ROIC}$), pull projected NOPAT, CapEx, and Working Capital changes directly from the 5-year forecasted 3-Way & Capital Schedule.
   $$FCFF_t = \text{NOPAT}_t + \text{Depr}_t - \text{CapEx}_t - \Delta\text{NWC}_t$$
2. **Enhanced Free Cash Flow to Equity (FCFE):**
   $$FCFE_t = FCFF_t - \text{Interest}_t \cdot (1 - T) - \text{Principal Repayments}_t + \text{New Debt Issued}_t$$
   Discounted at the dynamic Cost of Equity $K_e$.
3. **Enhanced 3-Stage Dividend Discount Model (DDM / H-Model):**
   Pull projected cash dividends $D_t = \text{NPAT}_t \cdot \text{Payout Ratio}_t / \text{Shares}_t$ directly from the Capital Allocation schedule.
4. **Enhanced Buffett Owner's Earnings (`buffett_owners_earnings`):**
   Directly use the decomposed Maintenance CapEx vs. Growth CapEx and $\Delta\text{WC}$ from R2 and R4.
5. **Capital Allocation Health Matrix (`capital_allocation` block):**
   Classifies capital deployment:
   - *Disciplined Compounder:* High ROIC, sustainable dividend payout ($30-50\%$), moderate reinvestment, low leverage.
   - *Empire Builder:* High CapEx / asset growth outstripping EBITDA growth, debt-fueled expansion.
   - *Cash Cow / Return of Capital:* Low CapEx, high dividend/buyback yield ($> 7\%$), steady cash flow.
   - *Distressed Deterioration:* Negative FCFE, debt refinancing stress, dividend suspension.

---

## 6. FastAPI Application & API Infrastructure Analysis (`server.py`)

### 6.1 Server Architecture & Patterns
- **Application Core:** `app = FastAPI(title="Vietnam Stock Trading Terminal Pro API", version="2.0.0", lifespan=lifespan)`
- **Lifespan Management (`lifespan`):** Modern async context manager initializing:
  - `_load_alert_rules()`
  - Background alert poller task `_alerts_poll_loop()`
  - `start_background_news_poller()`
  - Asynchronous RRG cache warmer thread `_warm_rrg_cache_async()`
- **CORS Policy:** Full open CORS (`allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`).
- **Response Format Convention:**
  - Standard JSON Envelope: `JSONResponse(content={"status": "success", "data": ...})`
  - Error Envelope: `JSONResponse(status_code=500, content={"status": "error", "message": str(e)})`
  - Streaming File Downloads: `Response(content=..., media_type=..., headers={"Content-Disposition": "attachment; filename=..."})`

### 6.2 Existing Valuation & Backtest Endpoints Catalog

| HTTP Method | Route | Handler Function | Purpose | Response Format |
|---|---|---|---|---|
| `GET` | `/api/valuation/comprehensive/{symbol}` | `api_get_comprehensive_valuation` | Full 22-model valuation, WACC, Risk Firewalls, Scenarios, 5x5 Grid | JSON (`ValuationMatrixResult`) |
| `GET` | `/api/valuation/matrix/{symbol}` | `api_get_comprehensive_valuation` | Alias for comprehensive valuation | JSON (`ValuationMatrixResult`) |
| `GET` | `/api/valuation/matrix?symbol=...` | `api_get_valuation_matrix_query` | Query param alias for comprehensive valuation | JSON (`ValuationMatrixResult`) |
| `GET` | `/api/backtest/fair_value/presets` | `api_get_fair_value_backtest_presets` | Returns catalog of modes, strategies, valuation models, universes | JSON |
| `GET/POST` | `/api/backtest/fair_value/run` | `api_run_fair_value_backtest` | Executes 3-mode institutional fair value backtest | JSON (`BacktestResultPayload`) |
| `GET` | `/api/company/financials` | `api_company_financials` | Historical financial statements & ratios | JSON (Rows & Columns) |
| `GET` | `/api/company/earnings-engine` | `api_company_earnings_engine` | 5-way growth attribution & 3-scenario earnings | JSON |
| `GET` | `/api/company/health` | `api_company_financial_health` | 4-pillar scorecard & Graham/Lynch valuations | JSON |

### 6.3 Architectural Blueprint for Required R5 Endpoints

#### Endpoint 1: `GET /api/valuation/3-way-forecast/{symbol}`
- **Purpose:** Exposes the full 5-year Modano-compliant integrated 3-Way financial model for `{symbol}`.
- **Query Parameters:**
  - `revenue_growth_override: Optional[float] = None`
  - `gross_margin_override: Optional[float] = None`
  - `tax_rate: float = 0.20`
  - `forecast_years: int = 5`
- **Response Schema (`200 OK`):**
  ```json
  {
    "status": "success",
    "data": {
      "symbol": "HPG",
      "company_name": "Tập đoàn Hòa Phát",
      "forecast_horizon_years": 5,
      "base_year": 2025,
      "forecast_years": [2026, 2027, 2028, 2029, 2030],
      "income_statement": {
        "revenue": [...],
        "cogs": [...],
        "gross_profit": [...],
        "sga": [...],
        "ebit": [...],
        "interest_expense": [...],
        "pbt": [...],
        "tax": [...],
        "npat": [...]
      },
      "balance_sheet": {
        "cash_and_equivalents": [...],
        "accounts_receivable": [...],
        "inventories": [...],
        "net_ppe": [...],
        "total_assets": [...],
        "accounts_payable": [...],
        "short_term_debt": [...],
        "long_term_debt": [...],
        "total_liabilities": [...],
        "retained_earnings": [...],
        "total_equity": [...],
        "net_assets": [...],
        "balance_check_passed": true,
        "max_balance_discrepancy": 0.0
      },
      "cash_flow_statement": {
        "cash_receipts_from_customers": [...],
        "cash_paid_to_suppliers": [...],
        "cash_paid_for_operating_expenses": [...],
        "cash_paid_for_income_tax": [...],
        "net_cfo_direct": [...],
        "capex_payments": [...],
        "net_cfi": [...],
        "net_borrowing": [...],
        "dividends_paid": [...],
        "net_cff": [...],
        "net_change_in_cash": [...],
        "closing_cash": [...]
      },
      "working_capital_schedule": {
        "dso_days": [...],
        "dio_days": [...],
        "dpo_days": [...],
        "ccc_days": [...],
        "net_working_capital": [...]
      },
      "debt_and_capital_schedule": {
        "opening_debt": [...],
        "new_borrowing": [...],
        "principal_repayment": [...],
        "closing_debt": [...],
        "interest_expense": [...],
        "interest_coverage_ratio": [...],
        "synthetic_rating": [...],
        "credit_spread": [...]
      },
      "liquidity_distress_firewall": {
        "has_liquidity_distress": false,
        "distress_years": [],
        "min_projected_cash": 25400.0,
        "dilution_haircut_pct": 0.0,
        "mos_penalty_pct": 0.0,
        "status": "SOLVENT_SAFE"
      }
    }
  }
  ```

#### Endpoint 2: `GET /api/valuation/export-excel/{symbol}`
- **Purpose:** Generates and streams a formatted Modano-compliant Excel `.xlsx` workbook using `openpyxl`.
- **Implementation Characteristics:**
  - Dynamic formulas embedded (`=SUM(...)`, `=IF(...)`, cross-sheet cell links).
  - Outlines / Collapsible Row Groupings (Level 1 summary, Level 2 detail).
  - Balance Sheet validation cell check (`=IF(ABS(TotalAssets - (TotalLiabilities + TotalEquity)) < 0.001, "BALANCED", "UNBALANCED")`).
  - Strict zero formula error guarantee (no `#REF!`, `#NAME?`, `#VALUE!`).
- **Response Headers:**
  - `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - `Content-Disposition: attachment; filename="{symbol}_3Way_Valuation_Model.xlsx"`

---

## 7. Synthesis & Recommendations for Implementation Specialists

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                          PROJECT ARCHITECTURE SUMMARY                          │
├───────────────────────┬───────────────────────────────┬────────────────────────┤
│ Specialist 1          │ Specialist 2                  │ Specialist 3           │
│ Core Modeling         │ Valuation & Backtesting       │ Excel Exporter & API   │
├───────────────────────┼───────────────────────────────┼────────────────────────┤
│ - three_statement_    │ - valuation_engine.py updates │ - financial_model_     │
│   engine.py (R1)      │   (R3 Distress & R4 Linked)   │   exporter.py (R5)     │
│ - working_capital_    │ - fair_value_backtest_service │ - server.py endpoints  │
│   engine.py (R2)      │   updates (R3 Screening Gate) │   (/3-way-forecast and │
│ - debt_capital_       │ - ValuationMatrixResult &     │    /export-excel)      │
│   schedule_engine.py  │   RiskFirewallResult schemas  │ - openpyxl streaming   │
│   (R4)                │                               │   response             │
└───────────────────────┴───────────────────────────────┴────────────────────────┘
```

### Key Recommendations:
1. **Mathematical Invariant Discipline:** Maintain $| \text{Total Assets} - (\text{Total Liabilities} + \text{Total Equity}) | < 10^{-5}$ across all forecast years for all VN30 symbols.
2. **Direct Method CFS Integrity:** Ensure Net Change in Cash from Direct Method CFS identically matches $\Delta\text{Cash}$ on the Balance Sheet.
3. **Safe Division & Robust Imputation:** Continue using `safe_div` and `clamp` to guarantee zero `#DIV/0!`, `NaN`, or `Infinity` exceptions across all financial ratios and models.
4. **Endpoint Cohesion:** Follow established `server.py` conventions (`JSONResponse`, standard status envelopes, proper error handling, query param validation).

---
*Report compiled and verified by `teamwork_preview_explorer_survey_2`.*
