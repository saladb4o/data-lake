# Technical Specification & Architectural Design: Backtesting, Risk Firewalls, API & Test Architecture (R2, R3, R4, R5)

**Author**: Explorer 3 — Backtesting, Risk Firewalls, API & Test Architecture Specialist  
**Date**: 2026-08-27  
**Status**: Comprehensive Analysis & Design  
**Target Modules**:
- `services/fair_value_backtest_service.py` (New / Extended 3-Mode Backtesting Engine)
- `services/risk_firewall_service.py` (New / Unified Risk Firewalls & Anti-Trap Diagnostics)
- `server.py` (New FastAPI Endpoints & Fast Caching Layers)
- `tests/` (Comprehensive 5-Tier PyTest Test Suites)

---

## 1. Executive Summary & System Decomposition

The objective is to deliver an institutional-grade Quantitative System encompassing:
1. **Three-Mode Modular Backtesting Engine (R2)**:
   - **Mode 1 (Pure Valuation)**: Simulates entries when $P < \text{Fair Value} \times (1 - \text{MOS})$ and exits when $P > \text{Fair Value} \times (1 + \text{Exit Premium})$.
   - **Mode 2 (Pure Screening)**: Factor-based periodic rebalancing across 32 factor/guru strategies.
   - **Mode 3 (2-Stage Hybrid Funnel)**: Stage 1 filters universe for fundamental quality & safety (Quality Moat / Survival Firewall / F-Score / M-Score), and Stage 2 executes valuation-timed entries based on Margin of Safety.
   - **Quant Metrics**: CAGR, Total Return, Max Drawdown, Sharpe, Sortino, Calmar, Win Rate, Profit Factor, Alpha, Beta, Information Ratio, Equity Curves, and Trade Logs.
   - **Lookahead Bias Prevention**: Point-in-time financial statement timeline with filing lag simulation (Q1 $\to$ May 1, Q2 $\to$ Aug 15, Q3 $\to$ Nov 15, Q4/Annual $\to$ Apr 1).
2. **Institutional Risk Firewalls & Anti-Trap Diagnostics (R3)**:
   - **4-Quadrant Altman Z-Score + Beneish M-Score Risk Matrix**: Categorizes companies into 4 distinct quadrants (Institutional Safe, Distressed Turnaround, Forensic Trap, Toxic Exclusion).
   - **Rhodes-Kropf (RKV) Enterprise Valuation Decomposition**: Decomposes Market-to-Book ($M/B$) into firm-specific error, sector time-series error, and long-run growth to eliminate value traps.
   - **Dynamic Margin of Safety (MOS) Scaled by Downside Beta ($\beta_-$)**: Dynamically scales required discount based on downside covariance with VN-Index.
3. **End-to-End API & Data Lake Integration (R4)**:
   - Exposes clean FastAPI routes with sub-200ms latency on cached data.
   - Seamlessly binds to local `data/` and Google Drive synced Data Lake files (`screener_snapshot.json`, `historical_prices.json`, `financial_models.json`, `financial_statements.json`, `all_symbols.json`).
4. **Comprehensive Multi-Tier PyTest Architecture (R5)**:
   - 5 testing tiers (Feature Unit Tests, Boundary & Edge Cases, Pairwise Combinations, Workload & Performance, Adversarial & Integrity).

```
                      ┌────────────────────────────────────────────────────────┐
                      │              UNIFIED DATA LAKE & CACHES                │
                      │ (historical_prices.json, screener_snapshot.json, etc.) │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                                                  ▼
                      ┌────────────────────────────────────────────────────────┐
                      │            R3. RISK FIREWALLS & DIAGNOSTICS            │
                      │  - 4-Quadrant Altman Z / Z'' + Beneish M-Score Matrix  │
                      │  - Rhodes-Kropf (RKV) V/B Decomposition                │
                      │  - Downside Beta Dynamic Margin of Safety ($\beta_-$)  │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                                                  ▼
                      ┌────────────────────────────────────────────────────────┐
                      │         R2. 3-MODE MODULAR BACKTESTING ENGINE          │
                      │  Mode 1: Pure Valuation (MOS Entry / Exit Premium)     │
                      │  Mode 2: Pure Screening (Factor Rebalance)             │
                      │  Mode 3: 2-Stage Hybrid Funnel (Quality + Valuation)   │
                      │  Engine: Point-in-Time, Friction, Quant Metrics Engine │
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                                                  ▼
                      ┌────────────────────────────────────────────────────────┐
                      │           R4. FASTAPI ENDPOINTS & CACHING              │
                      │  /api/valuation/matrix  |  /api/valuation/comprehensive│
                      │  /api/backtest/fair-value | /api/backtest/compare-modes│
                      └───────────────────────────┬────────────────────────────┘
                                                  │
                                                  ▼
                      ┌────────────────────────────────────────────────────────┐
                      │        R5. 5-TIER VERIFICATION TEST SUITE              │
                      │  Tier 1: Feature  | Tier 2: Boundary | Tier 3: Pairwise│
                      │  Tier 4: Workload | Tier 5: Adversarial Integrity      │
                      └────────────────────────────────────────────────────────┘
```

---

## 2. R2: Three-Mode Modular Backtesting System

### 2.1 Backtesting Mode Architecture

The backtest engine will be structured as `services/fair_value_backtest_service.py`, exposing a unified interface `run_fair_value_backtest(...)` supporting three orthogonal execution modes:

#### Mode 1: Pure Valuation Backtesting
- **Concept**: Classical Graham-Dodd-Klarman value investing simulation. Trades are triggered strictly by pricing discrepancies against intrinsic/relative Fair Value ($FV_t$).
- **Entry Condition**:
  $$\text{Price}_t < FV_t \times (1 - \text{MOS})$$
  where $\text{MOS}$ is either a static user-configured margin of safety (e.g., $0.20$) or the dynamic downside-beta adjusted margin of safety $\text{MOS}_{dynamic}$.
- **Exit Condition**:
  $$\text{Price}_t > FV_t \times (1 + \text{Exit Premium})$$
  or a hard stop-loss threshold (e.g., Trailing ATR Stop / Maximum Holding Period / Downside Breakdown).
- **Portfolio Sizing**: Capital equally distributed or volatility-weighted across qualifying underpriced stocks up to $\text{Top } K$ holdings. Unallocated capital earns the risk-free rate ($R_f \approx 5.0\%$).

#### Mode 2: Pure Screening Backtesting
- **Concept**: Quantitative factor-based periodic rebalancing strategy without explicit continuous valuation timing.
- **Rules**:
  - Rebalance dates $T_1, T_2, \dots, T_N$ based on selected cadence (Quarterly, Semi-Annual, Annual).
  - Universe filtered and ranked by selected Strategy Preset (e.g., `quant_q1`, `deep_value_klarman`, `value_buffett`, `peter_lynch_garp`, `buffetts_alpha`, `novy_marx_quality_value`, `gray_quantitative_value_qval`, etc.).
  - Rebalance execution: Entire basket liquidated and rotated into the new Top $K$ passing names, incorporating portfolio turnover friction (0.15% commission + 0.10% tax + 0.10% slippage).

#### Mode 3: Two-Stage Hybrid Funnel Backtesting
- **Concept**: Institutional dual-stage investment pipeline combining quantitative fundamental screening with rigorous valuation timing.
- **Stage 1 (Quality & Safety Screening Funnel)**:
  - At each rebalance boundary $T_k$, universe is filtered through fundamental quality, profitability, and risk firewalls:
    1. Universal Survival Firewall (ROA $\ge 9.5\%$, Current Ratio $\ge 1.45$, ICR $\ge 2.4$, Operating Margin $> 0$).
    2. Forensic Accounting Firewall (Piotroski F-Score $\ge 7$, Beneish M-Score $< -1.78$).
    3. Solvency Firewall (Altman Z-Score in Safe/Grey zone $Z > 1.81$ or $Z'' > 1.1$).
    4. Quality Moat Filter (Top ROE/ROIC, positive FCF).
  - Yields a screened **High-Quality Candidate Pool** $\mathcal{S}_k$.
- **Stage 2 (Valuation-Timed Execution)**:
  - Within candidate pool $\mathcal{S}_k$, evaluate Fair Value $FV_{i, t}$ for each asset $i \in \mathcal{S}_k$.
  - Only execute Buy orders for assets meeting the Margin of Safety hurdle:
    $$\text{Price}_{i, t} < FV_{i, t} \times (1 - \text{MOS}_i)$$
  - Assets in $\mathcal{S}_k$ that are fairly priced or expensive remain on the **Watchlist** until a price correction triggers entry.
  - Existing positions are held until they reach Fair Value target $P_{i, t} \ge FV_{i, t} \times (1 + \text{Exit Premium})$ or fail the Stage 1 Quality Firewall on subsequent quarters.
- **Hypothesis**: Hybrid Mode achieves significantly superior Risk-Adjusted Returns (higher Sharpe, higher Sortino, lower Max Drawdown) compared to naive Mode 2 screening, avoiding the "buying at peak valuation" trap.

---

### 2.2 Point-in-Time Timeline & Lookahead Bias Elimination

To guarantee institutional integrity and prevent lookahead bias:
1. **Filing Lag Rules (Vietnam Market Realism)**:
   - **Q1 Financials** (ended March 31): Official disclosures released throughout April; available for backtest trading on **May 1**.
   - **Q2 Financials / Semi-Annual Audited** (ended June 30): Available on **August 15**.
   - **Q3 Financials** (ended September 30): Available on **November 15**.
   - **Q4 / Full-Year Audited Financials** (ended December 31): Available on **April 1** of year $t+1$.
2. **Strict Time-Sequencing**:
   - On simulation date $t$, the valuation engine and screening filters only ingest financial statement parameters reported **strictly prior** to date $t$.
   - Prices used for trade execution are the real historical Daily Close prices from `data/historical_prices.json` corresponding to date $t$.

---

### 2.3 Comprehensive Quant Performance Metrics Engine

The backtest results dictionary must compute and return the following institutional metrics:

| Metric | Mathematical Formula | Description |
|---|---|---|
| **CAGR** | $\left(\frac{\text{Ending NAV}}{\text{Initial NAV}}\right)^{\frac{1}{\text{Years}}} - 1$ | Compound Annual Growth Rate |
| **Total Return** | $\frac{\text{Ending NAV} - \text{Initial NAV}}{\text{Initial NAV}} \times 100\%$ | Cumulative strategy gain |
| **Max Drawdown (MDD)** | $\max_{t} \left(\frac{\text{Peak}_t - \text{NAV}_t}{\text{Peak}_t}\right)$ | Maximum peak-to-trough decline |
| **Sharpe Ratio** | $\frac{R_p - R_f}{\sigma_p \times \sqrt{252}}$ (or $\sqrt{4}$ for quarterly) | Excess return per unit of total risk ($R_f = 5.0\%$) |
| **Sortino Ratio** | $\frac{R_p - R_f}{\sigma_{\text{downside}} \times \sqrt{252}}$ | Excess return per unit of downside risk ($\sigma_{d} = \sqrt{\frac{1}{N}\sum \min(0, r_t - r_f)^2}$) |
| **Calmar Ratio** | $\frac{\text{CAGR}}{\text{Max Drawdown}}$ | Ratio of annualized return to maximum drawdown |
| **Win Rate** | $\frac{N_{\text{profitable trades}}}{N_{\text{total trades}}} \times 100\%$ | Percentage of completed round-trip trades with positive net return |
| **Profit Factor** | $\frac{\sum \text{Gross Profits}}{\sum \text{Gross Losses}}$ | Ratio of gross profits to gross losses |
| **Alpha ($\alpha$) & Beta ($\beta$)** | CAPM regression $R_{p, t} - R_f = \alpha + \beta (R_{m, t} - R_f) + \epsilon_t$ | Jensen's Alpha and Market Sensitivity vs VN-Index |
| **Information Ratio (IR)** | $\frac{R_p - R_m}{\text{Tracking Error}}$ | Active return per unit of active risk vs VN-Index |
| **Turnover Rate** | $\frac{\sum |\text{Buys}| + |\text{Sells}|}{2 \times \text{Avg Portfolio Value}}$ | Portfolio rebalancing churn per year |

---

## 3. R3: Risk Firewalls & Anti-Trap Diagnostics

### 3.1 4-Quadrant Altman Z-Score + Beneish M-Score Risk Matrix

#### 1. Altman Z-Score Formulation
For Vietnam listed non-financial equities, we implement both the **Standard Altman Z-Score (Manufacturing)** and the **Emerging Market Altman Z''-Score (Non-Manufacturing / Emerging Markets)**:

**Emerging Market 4-Factor Altman Z''-Score**:
$$Z'' = 6.56 X_1 + 3.26 X_2 + 6.72 X_3 + 1.05 X_4$$
where:
- $X_1 = \frac{\text{Working Capital}}{\text{Total Assets}} = \frac{\text{Short-Term Assets} - \text{Short-Term Liabilities}}{\text{Total Assets}}$
- $X_2 = \frac{\text{Retained Earnings}}{\text{Total Assets}} = \frac{\text{Undistributed PAT}}{\text{Total Assets}}$
- $X_3 = \frac{\text{EBIT}}{\text{Total Assets}} = \frac{\text{Operating Profit}}{\text{Total Assets}}$
- $X_4 = \frac{\text{Book Value of Equity}}{\text{Total Liabilities}}$

**Classification Bands**:
- **Safe Zone**: $Z'' \ge 2.60$ (Negligible default probability $\implies$ Strong Solvency)
- **Grey Zone**: $1.10 \le Z'' < 2.60$ (Moderate financial distress risk $\implies$ Caution)
- **Distress Zone**: $Z'' < 1.10$ (High bankruptcy/distress probability $\implies$ Danger)

#### 2. Beneish M-Score 8-Variable Formulation
$$M = -4.84 + 0.920 \cdot \text{DSRI} + 0.528 \cdot \text{GMI} + 0.404 \cdot \text{AQI} + 0.892 \cdot \text{SGI} + 0.115 \cdot \text{DEPI} - 0.172 \cdot \text{SGAI} + 4.037 \cdot \text{TATA} + 0.0327 \cdot \text{LVGI}$$
- **Threshold**: $M < -1.78 \implies$ Safe / Non-manipulator; $M \ge -1.78 \implies$ High risk of earnings manipulation.

#### 3. Four-Quadrant Forensic Diagnostic Matrix

```
       Beneish M-Score
             ▲
   Manipulator│
    (M >= -1.78)│   QUADRANT 4: FORENSIC TRAP        QUADRANT 3: TOXIC EXCLUSION
             │   (Good Solvency, Bad Accounting)  (High Distress & High Manipulation)
             │   - Earnings inflated / aggressive - Imminent bankruptcy / fraud risk
             │   - High audit risk                - HARD FILTER: Immediate Disqualification
─────────────┼──────────────────────────────────────────────────────────────────────────►
 Non-Manipulator│   QUADRANT 1: INSTITUTIONAL BUY    QUADRANT 2: DISTRESSED TURNAROUND
    (M < -1.78)│   (Prime Quality & Clean Books)    (High Distress, Honest Accounting)
             │   - Strong balance sheet           - Real cash crunch, clean books
             │   - Verified high earnings quality - Deep value turnaround candidates
             │
             └────────────────────────────────────┬────────────────────────────────────►
                  Safe Zone (Z'' >= 2.60)              Distress Zone (Z'' < 1.10)
                                      Altman Z''-Score
```

**Automated Action Rules**:
- **Quadrant 1 (Institutional Safe)**: Passed for all Backtest Modes and Investment Portfolios.
- **Quadrant 2 (Distressed Turnaround)**: Allowed ONLY in Deep Value / Klarman strategies with elevated MOS hurdle ($+15\%$).
- **Quadrant 3 (Toxic Exclusion)**: Hard Disqualification across ALL models and backtests.
- **Quadrant 4 (Forensic Trap)**: Hard Disqualification unless explicitly overridden by user.

---

### 3.2 Rhodes-Kropf (RKV) Enterprise Valuation Decomposition

To eliminate "Value Traps" (stocks that appear cheap on raw $P/B$ or $P/E$ multiples because their industry is entering structural decline or experiencing temporary cyclical exuberance), we implement the **Rhodes-Kropf, Robinson, and Viswanathan (2005)** decomposition:

$$\ln\left(\frac{M}{B}\right) = \underbrace{\left(m - v(\theta_i; \alpha_{it})\right)}_{\text{Firm-Specific Misvaluation}} + \underbrace{\left(v(\theta_i; \alpha_{it}) - v(\theta_j; \alpha_{jt})\right)}_{\text{Time-Series Sector Error}} + \underbrace{\left(v(\theta_j; \alpha_{jt}) - b\right)}_{\text{Long-Run Sector Growth}}$$
where:
- $m = \ln(\text{Market Cap})$, $b = \ln(\text{Book Equity})$.
- $v(\theta_i; \alpha_{it})$ is the fundamental value predicted by firm accounting metrics (Book value, Net income, Leverage) under current sector pricing.
- $v(\theta_j; \alpha_{jt})$ is the long-run sector benchmark value.

**Application in Valuation & Screening**:
1. **True Firm Alpha**: A low $M/B$ is ONLY attractive if the firm-specific error $m - v(\theta_i) < 0$ (firm is undervalued relative to industry peers).
2. **Value Trap Flag**: If firm $M/B$ is low because the entire sector is suffering negative industry drift $v(\theta_j) - b < 0$, the stock is flagged as a **Structural Sector Trap** and penalized in the composite ranking.

---

### 3.3 Dynamic Margin of Safety Scaled by Downside Beta ($\beta_-$)

Classical value investing assumes a rigid Margin of Safety (e.g., 20%). However, assets exhibiting severe asymmetric downside risk require a wider safety buffer.

#### 1. Downside Beta Formulation
$$\beta_- = \frac{\text{Cov}(R_i, R_m \mid R_m < R_f)}{\text{Var}(R_m \mid R_m < R_f)}$$
where $R_i$ is daily stock return, $R_m$ is daily VN-Index return, and conditioning is on down-market days ($R_m < R_f / 252$).

#### 2. Dynamic MOS Equation
$$\text{MOS}_{dynamic} = \text{MOS}_{base} \times \left[1 + \max(0, \beta_- - 1.0) \times \gamma\right] + \Delta_{\text{Risk}}$$
where:
- $\text{MOS}_{base} = 0.20$ (20% standard baseline).
- $\gamma = 0.50$ (downside beta sensitivity factor).
- $\Delta_{\text{Risk}}$ is additive risk penalty from forensic firewalls:
  - $+0.05$ if Altman Z in Grey Zone ($1.10 \le Z'' < 2.60$).
  - $+0.10$ if Beneish M borderline ($-2.20 \le M < -1.78$).
  - $+0.05$ if Net D/E $> 1.5$.

**Example Dynamics**:
- Stable Bluechip Utility (REE: $\beta_- = 0.65$, Safe Z'', Clean M): $\text{MOS}_{dynamic} = 20\% \times [1 + 0] = \mathbf{20.0\%}$.
- High-Beta Volatile Cyclical (HPG: $\beta_- = 1.60$, Grey Z''): $\text{MOS}_{dynamic} = 20\% \times [1 + (1.60 - 1.0) \times 0.5] + 5\% = 20\% \times 1.30 + 5\% = \mathbf{31.0\%}$.

---

## 4. R4: End-to-End API & Data Lake Integration

### 4.1 FastAPI Endpoint Specifications for `server.py`

#### 1. `GET /api/valuation/matrix`
- **Purpose**: Returns 22-model valuation breakdown (Bear, Base, Bull), model confidence weights, and Composite Fair Value.
- **Parameters**:
  - `symbol: str` (e.g., `"HPG"`)
  - `scenario: Optional[str]` (`"base"`, `"bear"`, `"bull"`, `"all"`)
- **Response Shape**:
```json
{
  "status": "success",
  "data": {
    "symbol": "HPG",
    "company_name": "CTCP Tập đoàn Hòa Phát",
    "exchange": "HOSE",
    "current_price": 28500,
    "composite_fair_value": 34200,
    "composite_upside_pct": 20.0,
    "valuation_status": "UNDERVALUED",
    "margin_of_safety_pct": 25.0,
    "models": [
      {
        "id": "blended_pe",
        "category": "relative",
        "name": "Blended P/E with CAPE",
        "bear_val": 26000,
        "base_val": 32000,
        "bull_val": 38000,
        "weight": 0.085,
        "status": "ACTIVE"
      }
    ],
    "scenario_drivers": {
      "wacc": {"bear": 0.135, "base": 0.115, "bull": 0.100},
      "terminal_growth": {"bear": 0.025, "base": 0.035, "bull": 0.045}
    }
  }
}
```

#### 2. `GET /api/valuation/comprehensive`
- **Purpose**: Full diagnostic report including 22 valuation models, WACC 5-Factor CAPM breakdown, 4-Quadrant Z/M Matrix, Rhodes-Kropf V/B decomposition, and Downside Beta Dynamic MOS.
- **Parameters**: `symbol: str`

#### 3. `POST /api/backtest/fair-value`
- **Purpose**: Executes on-demand backtesting across Mode 1, Mode 2, or Mode 3 with custom parameterization.
- **Request Body / Query Params**:
  - `mode: str` (`"mode1_pure_valuation"`, `"mode2_pure_screening"`, `"mode3_hybrid_funnel"`)
  - `strategy_id: Optional[str]` (e.g., `"quant_q1"`, `"value_buffett"`, `"custom"`)
  - `valuation_model_id: Optional[str]` (e.g., `"composite"`, `"dcf_2stage"`, `"graham_growth"`)
  - `margin_of_safety_pct: float` (e.g., `20.0`)
  - `exit_premium_pct: float` (e.g., `10.0`)
  - `dynamic_mos: bool` (e.g., `True`)
  - `time_horizon_years: int` (e.g., `5`)
  - `rebalance_cadence: str` (`"quarterly"`, `"semi_annual"`, `"annual"`)
  - `top_k: int` (e.g., `10`)
  - `initial_capital: float` (e.g., `100000000.0`)
  - `survival_filter: bool` (`True`/`False`)
  - `forensic_filter: bool` (`True`/`False`)
- **Response Shape**:
```json
{
  "status": "success",
  "data": {
    "mode": "mode3_hybrid_funnel",
    "parameters": { ... },
    "metrics": {
      "cagr": 24.8,
      "total_return": 202.5,
      "max_drawdown": -16.4,
      "sharpe_ratio": 1.48,
      "sortino_ratio": 2.15,
      "calmar_ratio": 1.51,
      "win_rate": 68.5,
      "profit_factor": 2.35,
      "alpha": 12.2,
      "beta": 0.78,
      "turnover_annual_pct": 45.0
    },
    "equity_curve": [
      {"date": "2021-05-01", "nav": 100000000, "benchmark_nav": 100000000, "drawdown": 0.0},
      {"date": "2021-08-15", "nav": 108500000, "benchmark_nav": 104200000, "drawdown": 0.0}
    ],
    "trades": [ ... ],
    "rebalance_timeline": [ ... ]
  }
}
```

#### 4. `POST /api/backtest/compare-modes`
- **Purpose**: Runs Mode 1, Mode 2, and Mode 3 side-by-side on identical universe and time horizon to quantify hybrid funnel alpha and drawdown reduction.

---

### 4.2 High-Performance Caching Strategy (< 200ms Latency)

1. **Dual-Tier Cache Hierarchy**:
   - **L1 In-Memory Cache (`SimpleCache`)**: Fast RAM cache with thread-safe lock and Stale-While-Revalidate (SWR) semantics. TTL: 3600s for static valuation matrices, 600s for backtest comparisons.
   - **L2 Fast JSON Memory-Mapped Store**: Data Lake files (`screener_snapshot.json`, `historical_prices.json`) are parsed once at startup and kept resident in memory as pre-indexed Python hash maps.
2. **Vectorized Computation**:
   - Metric computations, returns arrays, and drawdowns implemented with vectorized `numpy` and `pandas` operations.
   - Cross-sectional scoring and basket selection evaluated in $< 50\text{ms}$.

---

## 5. R5: Multi-Tier PyTest Test Architecture

We define a 5-tier test strategy to be implemented across modular test suites in `tests/`:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      5-TIER PYTEST TEST HIERARCHY                      │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Feature & Mathematical Unit Tests                              │
│   - test_valuation_models_22.py: 22 model formula proofs               │
│   - test_wacc_capm_engine.py: 5-factor CAPM & Damodaran spreads        │
│   - test_ivw_adaptive_weighting.py: Prediction error & IVW math        │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Boundary & Edge Cases                                          │
│   - test_valuation_boundaries.py: Negative EPS/FCF, zero debt/equity   │
│   - test_backtest_boundaries.py: Empty candidate pools, zero trades    │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Pairwise & Combinatorial Tests                                 │
│   - test_backtest_combinations.py: 3 modes x 3 cadences x 4 firewalls  │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 4: Workload & Performance Benchmarks                              │
│   - test_performance_latency.py: API latency < 200ms, backtest < 2.0s │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 5: Adversarial & System Integrity Tests                           │
│   - test_lookahead_bias_guard.py: Filing date integrity verification   │
│   - test_fair_value_non_negative.py: Invariant non-negativity check    │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Test Suites Specification

#### Suite 1: `tests/test_valuation_models_22.py`
- **Objective**: Verify exact mathematical correctness for all 22 valuation models.
- **Test Cases**:
  - `test_relative_multiples_8()`: Validates P/E, CAPE P/E, P/S, P/FCF, P/B, P/TBV, EV/EBITDA, P/CF, P/AFFO against synthetic balance sheets with known hand-calculated outputs.
  - `test_absolute_intrinsic_models_7()`: Validates 2-Stage McKinsey DCF, RIM Edwards-Bell-Ohlson, Greenwald EPV, Graham Growth, Rule of 40 / Rule of X, Acquirer's Multiple (EV/EBIT), Owner's Earnings.
  - `test_sector_specific_models_7()`: Validates rNPV (Pharma), Equity Cash Flow (Banks), AFFO DCF (REITs), SOTP RAB (Telecom), APV (Industrials), EVA (Consumer Staples), DDM (Utilities).
  - `test_scenario_generation()`: Verifies Bear/Base/Bull spreads match driver shifts (+/-15% growth, +/-150bps discount rate).

#### Suite 2: `tests/test_risk_firewalls.py`
- **Objective**: Verify Altman Z/Z'', Beneish M-Score, 4-Quadrant Matrix, Rhodes-Kropf, and Downside Beta MOS.
- **Test Cases**:
  - `test_altman_z_double_prime_calculation()`: Tests emerging market formula against known financials.
  - `test_beneish_m_score_8_variables()`: Tests all 8 sub-indices (DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA) and manipulation threshold ($-1.78$).
  - `test_four_quadrant_matrix_classification()`: Verifies proper routing into Quadrants 1 to 4 and hard firewall actions.
  - `test_rhodes_kropf_decomposition()`: Verifies decomposition math $m - b = (m - v_i) + (v_i - v_j) + (v_j - b)$.
  - `test_downside_beta_dynamic_mos()`: Verifies $\beta_-$ calculation and scaling of MOS from 20% to 35%+.

#### Suite 3: `tests/test_fair_value_backtest.py`
- **Objective**: Verify 3-mode backtest execution, timeline sequencing, and quant metrics.
- **Test Cases**:
  - `test_mode1_pure_valuation_execution()`: Verifies entry when $P < FV \times (1 - MOS)$ and exit when $P > FV \times (1 + EP)$.
  - `test_mode2_pure_screening_rebalance()`: Verifies rotation at quarterly/annual boundaries and turnover accounting.
  - `test_mode3_hybrid_funnel_superiority()`: Proves Mode 3 achieves higher Sharpe or lower MaxDD than Mode 2 on volatile test datasets.
  - `test_quant_metrics_accuracy()`: Verifies CAGR, Sharpe, Sortino, Calmar, MaxDD against standard reference calculations.

#### Suite 4: `tests/test_valuation_api.py`
- **Objective**: Verify FastAPI route contracts, JSON serialization, and sub-200ms caching.
- **Test Cases**:
  - `test_api_valuation_matrix_contract()`: Validates schema of `/api/valuation/matrix`.
  - `test_api_valuation_comprehensive_contract()`: Validates schema of `/api/valuation/comprehensive`.
  - `test_api_backtest_fair_value_execution()`: Validates `/api/backtest/fair-value` for Mode 1, Mode 2, Mode 3.
  - `test_api_cached_latency_under_200ms()`: Times repeated calls to ensure cache hits return in $< 200\text{ms}$.

#### Suite 5: `tests/test_adversarial_integrity.py`
- **Objective**: Stress-test edge cases, lookahead bias prevention, and system invariants.
- **Test Cases**:
  - `test_lookahead_bias_filing_dates()`: Injects future financial data and asserts backtester does NOT access Q2 data before August 15.
  - `test_non_negative_fair_value_invariant()`: Passes extreme negative earnings, huge debt, negative cash flows $\implies$ asserts Fair Value is strictly non-negative and does not throw unhandled exceptions.
  - `test_zero_track_record_ivw_fallback()`: Passes newly listed stock with 0 historical quarters $\implies$ verifies IVW gracefully falls back to equal weighting.

---

## 6. Implementation Blueprint & File Touch Matrix

| Component | Target File | Action | Description |
|---|---|---|---|
| **Backtesting Engine** | `services/fair_value_backtest_service.py` | Create | Implements 3-Mode Backtesting System (Mode 1, Mode 2, Mode 3), Point-in-Time timeline, Friction model, Quant Metrics engine. |
| **Risk Firewalls** | `services/risk_firewall_service.py` | Create | Implements Altman Z/Z'', Beneish M-Score, 4-Quadrant Matrix, Rhodes-Kropf Decomposition, Downside Beta MOS. |
| **API Endpoints** | `server.py` | Modify | Exposes `/api/valuation/matrix`, `/api/valuation/comprehensive`, `/api/backtest/fair-value`, `/api/backtest/compare-modes` with caching. |
| **Test Suite: Models** | `tests/test_valuation_models_22.py` | Create | PyTest suite for 22 valuation formulas, WACC, and scenario generation. |
| **Test Suite: Risk** | `tests/test_risk_firewalls.py` | Create | PyTest suite for Altman Z, Beneish M, Rhodes-Kropf, and Downside Beta. |
| **Test Suite: Backtest** | `tests/test_fair_value_backtest.py` | Create | PyTest suite for 3 Backtest modes, Quant metrics, and Hybrid funnel. |
| **Test Suite: API** | `tests/test_valuation_api.py` | Create | PyTest suite for FastAPI endpoints and < 200ms latency. |
| **Test Suite: Integrity** | `tests/test_adversarial_integrity.py` | Create | PyTest suite for lookahead bias prevention and invariants. |

---
*End of Analysis & Design Document for Explorer 3.*
