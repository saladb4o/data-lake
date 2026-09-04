# System & Data Architecture Analysis: Fundamental Valuation & 3-Mode Backtesting Engine

**Author**: Explorer 1 (System & Data Architecture Specialist)  
**Date**: 2026-08-27  
**Workspace**: `c:/Users/Admin/Documents/Vibecoding vnstock`

---

## 1. Executive Summary & Scope

The objective is to architect and integrate an institutional-grade **22-Model Fundamental Valuation Engine** (ported and adapted from Pine Script FFV Pro concepts into pure high-performance Python), a **3-Mode Modular Backtesting Engine** (Pure Valuation, Pure Screening, and 2-Stage Hybrid Funnel), along with **Risk Firewalls & Anti-Trap Diagnostics** into the existing Vietnam Stock Monitor FastAPI backend and Data Lake.

### Core Architectural Goals:
1. **Zero-Latency In-Memory / L2 Cached Computation**: Fast retrieval (< 200ms) over 1,600+ Vietnamese tickers using cached point-in-time snapshots and quarterly price/statement histories.
2. **Robust Fallbacks & Economic Validity**: Graceful mathematical handling of negative earnings, missing cash flows, financial vs non-financial company structures (Banking, Insurance, Securities, Non-Finance).
3. **Multi-Horizon Scenarios & Quant Weighting**: Bear / Base / Bull driver shifts, 5-Factor Vietnam CAPM + Damodaran synthetic credit spread for WACC, and Adaptive Multi-Algo Weighting (IVW, SMAPE, MALE, WMAPE, RMSLE).
4. **Seamless Integration with Existing Data Lake**: Clean interop with `screener_snapshot.json`, `historical_prices.json`, `financial_models.json`, `all_symbols.json`, and `financial_statements.json` across local `data/` and Google Drive `G:/My Drive/vnstock_data/`.

---

## 2. Codebase Topography & Dependency Landscape

### 2.1 File & Directory Inventory
| Path | Size / Lines | Key Responsibilities |
|---|---|---|
| `server.py` | 62.2 KB / 1,310 lines | FastAPI app instance (v2.0.0), lifespan alerts background poller, CORS, static mounting, ~45 REST endpoints. |
| `run_app.py` | 2.2 KB / 77 lines | Application launcher, finds available port (8000-8888), auto-opens browser, loads `.env`, configures UTF-8. |
| `services/stock_service.py` | 438 KB / 8,915 lines | Core market domain service, universe management (`ALL_SYMBOLS_MAP`), `SimpleCache` (SWR), `DiskDataLake`, `get_company_financial_statements`, `get_company_financial_health`, `get_symbol_global_valuation`. |
| `services/unified_data_service.py` | 53.5 KB / 1,182 lines | 3-Tier market ingestion (TradingView scanner, vnstock/TCBS, Yahoo Finance), 4-tier data provenance, Accounting Triangles imputation. |
| `services/backtest_service.py` | 118 KB / 2,577 lines | Multi-factor quant screener backtester, 32+ strategy definitions, quarterly rebalancing (2021-2026), point-in-time friction/metrics. |
| `services/institutional_backtest_service.py` | 63.8 KB / 1,436 lines | Bar-by-bar execution, 2D parameter sensitivity, Walk-Forward Analysis (WFA), Monte Carlo simulation, Grinold & Kahn Active Management Law. |
| `services/quant_scoring.py` | 38.4 KB / 780 lines | Percentile-quintile scoring, anti-tie mid-rank tie-breakers, dispersion floors. |
| `services/tls_config.py` | 2.9 KB | Single source of truth for TLS verification and warning suppression (`VNSTOCK_INSECURE_TLS`). |
| `data/` | ~30 MB | Persistent JSON datasets (`historical_prices.json`, `screener_snapshot.json`, `financial_models.json`, `all_symbols.json`, `industries.json`). |
| `tests/` | 22 test files | Pytest suite for scoring, fetchers, imputation, normalization, macro, sectors. |

### 2.2 Python Environment & Package Dependencies
- **Core Framework**: Python 3.13.2, FastAPI 0.115+, Starlette 0.37.2, Uvicorn 0.46.0, Pydantic 2.13.4.
- **Scientific & Data**: Pandas 2.2+, NumPy 2.x, SciPy 1.17.1, Scikit-Learn 1.8.0, TA-Lib 0.6.8.
- **Market Data Feeds**: `vnstock` (v3.5.1), `vnstock3` (v3.2.1), `yfinance` (v1.1.0), `requests` (v2.33.1).
- **Testing**: `pytest` (v9.0.3), `pytest-asyncio` (v1.3.0), `pytest-cov` (v7.1.0).

---

## 3. Data Lake Architecture & Schema Analysis

### 3.1 Dual-Tier Resolution Mechanism (`resolve_data_file`)
Located in `services/stock_service.py:101-128`:
- Checks Google Drive path (`GOOGLE_DRIVE_DATA_DIR`, default `G:/My Drive/vnstock_data`) and local `data/` directory.
- Priority: Sorts candidates by **file size descending** (preferring richer data), then by **modification time (`mtime`) descending**.
- Thread-safe L2 disk cache managed by `DiskDataLake` (`services/stock_service.py:129-170`) with in-memory memoization.

### 3.2 Key Data Lake Files & Detailed Schemas

#### A. `data/historical_prices.json` (12.73 MB, 1,306 Symbols)
- **Top-Level Schema**:
  ```json
  {
    "version": "2.0",
    "last_updated": "2026-03-31T00:00:00",
    "total_symbols": 1306,
    "source": "TradingView + vnstock Unified Feed",
    "symbols": {
      "FPT": {
        "symbol": "FPT",
        "exchange": "HOSE",
        "total_quarters": 41,
        "earliest_quarter": "2016-Q1",
        "latest_quarter": "2026-Q1",
        "quarters": {
          "2026-Q1": {
            "quarter": "2026-Q1",
            "start_date": "2026-01-05",
            "end_date": "2026-03-31",
            "start_price": 95800,
            "close_price": 74700,
            "high": 108700,
            "low": 71600,
            "volume": 798012654,
            "return_pct": -22.03
          }
        }
      }
    }
  }
  ```
- **Timeline Coverage**: 41 continuous quarters (2016-Q1 to 2026-Q1).
- **Use Case**: Quarter-by-quarter lookahead-free backtesting, IVW historical error weighting, Downside Beta calculation.

#### B. `data/screener_snapshot.json` (7.29 MB, 1,647 Symbols)
- **Top-Level Schema**:
  ```json
  {
    "updated_at": "2026-08-26T...",
    "total_symbols": 1647,
    "source": "TradingView Scanner + TCBS + Imputation Engine",
    "provenance_summary": { "tier_3_reported": 12500, "tier_2_triangulated": 4200, "tier_1_sector_median": 1800 },
    "sectors": { ... },
    "stocks": {
      "FPT": {
        "symbol": "FPT", "name": "Công ty CP FPT", "exchange": "HOSE",
        "price": 135.2, "change_pct": 1.2, "market_cap": 198500,
        "sector_code": "VNIT", "sector_name": "Công nghệ Thông tin", "industry": "Dịch vụ CNTT",
        "pe": 24.5, "pb": 5.8, "ps": 3.4, "peg": 1.15, "peg_sales": 1.35, "eps": 5520, "dividend_yield": 1.85,
        "roe": 26.5, "roa": 14.2, "gross_margin": 38.5, "op_margin": 19.8, "net_margin": 16.2, "core_pat_ratio": 94.5,
        "rev_1y_growth": 19.5, "rev_3y_cagr": 21.2, "rev_5y_growth": 115.0,
        "pat_1y_growth": 21.0, "pat_3y_cagr": 22.5, "pat_5y_growth": 128.0,
        "de_ratio": 0.42, "net_de_ratio": 0.08, "current_ratio": 1.85, "quick_ratio": 1.62,
        "interest_coverage": 18.5, "cash_to_assets": 22.4, "rule_of_40": 40.7, "roic": 22.8,
        "fcf_ttm": 7850.0, "cfo_to_pat": 1.12, "share_dilution_3y": 2.1,
        "ebit_expansion": 1.4, "operating_leverage": 1.15, "dilution_spread": 20.4,
        "is_cyclical": false, "size_category": "Large Cap",
        "_metadata": { "data_quality_score": 96.0 },
        "percentiles": { "roe": 92.5, "pe": 78.0, "composite": 88.5 }
      }
    }
  }
  ```

#### C. `data/financial_models.json` (6.22 MB, 2,500 Items)
- Model taxonomy mapping line item codes across 4 company forms (`SECURITIES`, `BANK`, `ENTERPRISE`, `INSURANCE`) for Balance Sheet, Income Statement, Cashflow, and Ratios.

#### D. `data/financial_statements.json` (Managed by `DiskDataLake`)
- Cached responses from VNDIRECT Finfo API (`https://api-finfo.vndirect.com.vn/v4/financial_statements`).
- Structured by key: `{SYMBOL}_{STATEMENT_TYPE}_{PERIOD}_{PERIODS_COUNT}` (e.g. `FPT_income_quarter_8`).
- Contains raw line item breakdowns (`rows`), fiscal dates (`distinct_dates`), and unit normalizations.

---

## 4. Valuation Engine Architecture (R1 & R3 Mapping)

The Valuation Engine will be built as a modular service at `services/valuation_engine.py`.

```
services/valuation_engine.py
├── ValuationEngine (Main Coordinator)
│   ├── Relative Multiples Suite (8 Models)
│   ├── Absolute Intrinsic Suite (7 Models)
│   ├── Sector-Specific Suite (7 Models)
│   ├── Stress-Test & Scenario Generator (Bear / Base / Bull)
│   ├── 5-Factor Vietnam CAPM & WACC Engine
│   └── Adaptive Weighting Engine (IVW, SMAPE, MALE, WMAPE, RMSLE)
└── RiskFirewalls & Anti-Trap Diagnostics
    ├── 4-Quadrant Altman Z-Score & Beneish M-Score
    ├── Rhodes-Kropf (RKV) M/B Decomposition
    └── Downside Beta Dynamic Margin of Safety
```

### 4.1 Detailed Catalog of All 22 Valuation Models

```
+----------------------------------------------------------------------------------------------------+
| 8 RELATIVE MULTIPLES                                                                               |
+----------------------------------------------------------------------------------------------------+
| 1. Blended P/E (with optional CAPE):                                                               |
|    FV = EPS_norm * (w_sector * PE_sector_median + w_hist * PE_5y_hist_median)                      |
| 2. P/S (Price to Sales):                                                                           |
|    FV = Sales_per_share * PS_sector_median * (NetMargin_firm / NetMargin_sector)                   |
| 3. P/FCF (Price to Free Cash Flow):                                                                |
|    FV = FCF_per_share * PFCF_sector_median (with 3Y average FCF smoothing)                         |
| 4. P/B (with Rhodes-Kropf filter):                                                                |
|    FV = BVPS * PB_sector_median * (ROE_firm / ROE_sector)                                          |
| 5. P/TBV (Price to Tangible Book Value):                                                           |
|    FV = Tangible_BVPS * PTBV_sector_median                                                         |
| 6. Blended EV/EBITDA:                                                                              |
|    FV = (EBITDA * EV_EBITDA_peer - Total_Debt + Cash) / Shares_Outstanding                         |
| 7. P/CF (Price to Operating Cash Flow):                                                            |
|    FV = CFO_per_share * PCF_sector_median                                                          |
| 8. P/AFFO (Price to Adjusted FFO):                                                                 |
|    FV = AFFO_per_share * PAFFO_benchmark_multiple                                                  |
+----------------------------------------------------------------------------------------------------+
| 7 ABSOLUTE INTRINSIC MODELS                                                                        |
+----------------------------------------------------------------------------------------------------+
| 9. Extended 2-Stage Value Driver DCF (McKinsey/ROIC):                                              |
|    NOPAT_t = EBIT_t * (1 - t); Reinvestment = g / ROIC; FCF = NOPAT * (1 - Reinvestment)           |
|    TV = (NOPAT_{T+1} * (1 - g_L / ROIC_L)) / (WACC - g_L)                                          |
| 10. Residual Income Model (RIM / Edwards-Bell-Ohlson):                                             |
|    FV = BVPS_0 + Sum_{t=1}^T (ROE_t - r_e) * BVPS_{t-1} / (1 + r_e)^t + Continuing Residual Income |
| 11. EPV (Greenwald Earnings Power Value):                                                          |
|    Normalized_EBIT = EBIT_adj * (1 - t); EPV = (Adjusted_Earnings / Cost_of_Capital) + Excess_Cash  |
| 12. Graham Growth Number:                                                                          |
|    V = EPS * (8.5 + 2g) * (4.4 / Y) or sqrt(22.5 * EPS * BVPS)                                    |
| 13. Rule of 40 / Rule of X Valuation:                                                              |
|    Score = RevGrowth% + FCFMargin%; Multiplier = Base_Multiple * (Score / 40)^alpha                |
| 14. Acquirer's Multiple (EV/EBIT):                                                                 |
|    Target_EV = EBIT * Acquirers_Target_Multiple; FV = (Target_EV - Net_Debt) / Shares              |
| 15. Owner's Earnings (Warren Buffett):                                                             |
|    Owner_Earnings = NetIncome + D&A - Maintenance_CapEx +/- Delta_WorkingCapital                   |
|    FV = Owner_Earnings / (r_e - g_perp)                                                            |
+----------------------------------------------------------------------------------------------------+
| 7 SECTOR-SPECIFIC MODELS                                                                           |
+----------------------------------------------------------------------------------------------------+
| 16. rNPV (Risk-adjusted NPV - Pharma / Healthcare):                                                |
|     FV = Sum [ Probability_Phase_i * CF_Phase_i / (1 + r)^t ]                                      |
| 17. Equity Cash Flow (Banks / Financial Institutions):                                             |
|     ECF = NetIncome - Delta_Regulatory_Capital; FV = Sum [ ECF_t / (1 + r_e)^t ] + Terminal_Value  |
| 18. AFFO DCF (REITs / Real Estate Operations):                                                     |
|     AFFO = FFO - Maintenance_CapEx - Straight_Line_Rent; Discounted via REIT Cost of Equity        |
| 19. Unbundled SOTP (Telecom NetCo/ServeCo + RAB Model):                                            |
|     FV = (NetCo_RAB * RAB_Multiple + ServeCo_EBITDA * EV_Multiple - Debt) / Shares                |
| 20. APV (Adjusted Present Value - Industrials):                                                    |
|     APV = Unlevered_DCF + PV(Interest_Tax_Shield) - PV(Financial_Distress)                         |
| 21. EVA (Economic Value Added - Consumer Staples):                                                 |
|     EVA_t = NOPAT_t - (WACC * Invested_Capital_{t-1}); FV = Capital_0 + MVA                        |
| 22. DDM (Dividend Discount Model - Utilities / Stable Yields):                                     |
|     Multi-stage H-Model: V_0 = (D_0 * (1 + g_L) + D_0 * H * (g_S - g_L)) / (r_e - g_L)             |
+----------------------------------------------------------------------------------------------------+
```

### 4.2 WACC & 5-Factor Vietnam CAPM Engine
1. **Cost of Equity ($r_e$) via 5-Factor VN Model**:
   $$r_e = R_f + \beta_{\text{mkt}} \cdot \text{ERP} + \beta_{\text{SMB}} \cdot \text{SMB} + \beta_{\text{HML}} \cdot \text{HML} + \beta_{\text{Mom}} \cdot \text{MOM} + \beta_{\text{Liq}} \cdot \text{Amihud\_Illiquidity}$$
   - Baseline $R_f = 5.0\%$ (1Y/5Y Vietnam Government Bond yield).
   - Equity Risk Premium ($\text{ERP}$) $= 7.5\%$ for Vietnam frontier/emerging market.
2. **Cost of Debt ($r_d$) via Damodaran Synthetic Credit Spread**:
   - Computes Interest Coverage Ratio ($\text{ICR} = \frac{\text{EBIT}}{\text{Interest Expense}}$).
   - Maps ICR to Synthetic Rating (`AAA`, `AA`, `A`, `BBB`, `BB`, `B`, `CCC/D`) and adds credit spread (1.0% to 8.5%) to $R_f$.
   - Effective after-tax $K_d = r_d \times (1 - T_c)$, where $T_c = 20\%$ Vietnam CIT.
3. **Weight of Equity & Debt**: $W_e = \frac{E}{E+D}$, $W_d = \frac{D}{E+D}$.
   $$\text{WACC} = W_e \cdot r_e + W_d \cdot K_d$$

### 4.3 Adaptive Multi-Algo Weighting (IVW & Error Metrics)
- For tickers with historical quarterly track record, computes prediction error of each model against subsequent quarterly realized prices:
  $$\sigma_m^2 = \frac{1}{K} \sum_{k=1}^K (\hat{P}_{m,k} - P_{real,k})^2$$
- **Inverse Variance Weighting (IVW)**:
  $$w_m = \frac{\frac{1}{\sigma_m^2}}{\sum_{j=1}^M \frac{1}{\sigma_j^2}}$$
- Zero-track-record fallback: Sector-calibrated Bayesian prior weights.
- Metrics supported: SMAPE (Symmetric Mean Absolute Percentage Error), MALE, WMAPE, RMSLE.

### 4.4 Risk Firewalls & Anti-Trap Diagnostics
1. **Altman Z-Score (EM Version for Emerging Markets)**:
   $$Z'' = 6.56 X_1 + 3.26 X_2 + 6.72 X_3 + 1.05 X_4$$
   - $Z'' > 2.6$: Safe, $1.1 \le Z'' \le 2.6$: Grey, $Z'' < 1.1$: Distress.
2. **Beneish M-Score (8-Variable Manipulation Index)**:
   - DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA.
   - $M > -1.78$: High probability of earnings manipulation.
3. **Rhodes-Kropf (RKV) M/B Decomposition**:
   $$\ln(M/B) = \underbrace{(\ln(M) - \ln(V(\theta)))}_{\text{Firm-specific misvaluation}} + \underbrace{(\ln(V(\theta)) - \ln(V(\alpha_j)))}_{\text{Sector misvaluation}} + \underbrace{(\ln(V(\alpha_j)) - \ln(B))}_{\text{Long-run Value-to-Book}}$$
   - Filters out value traps where low P/B is due to structural sector decline or accounting impairment rather than temporary mispricing.
4. **Dynamic Margin of Safety (MoS)**:
   $$\text{MoS}_{\text{adjusted}} = \text{MoS}_{\text{base}} \times \left(1 + \max(0, \beta_{\text{downside}} - 1.0) \times 0.5\right)$$

---

## 5. Three-Mode Backtesting System Architecture (R2 Mapping)

Will be implemented in `services/fair_value_backtest_service.py` to complement existing `backtest_service.py` and `institutional_backtest_service.py`.

```
+------------------------------------------------------------------------------------+
| FAIR VALUE BACKTESTING SYSTEM (3 ORTHOGONAL MODES)                                |
+------------------------------------------------------------------------------------+
| MODE 1: PURE VALUATION                                                             |
| - Entry: Market Price < Fair Value * (1 - Margin of Safety)                        |
| - Exit: Market Price > Fair Value * (1 + Exit Premium) or Model Downgrade          |
| - Signal Source: Individual model or Composite Multi-Algo                          |
+------------------------------------------------------------------------------------+
| MODE 2: PURE SCREENING                                                             |
| - Strategy Basket Rebalancing: GARP, Deep Value, Quality Moat, Quant Q1            |
| - Rebalancing Cadence: Quarterly, Semi-Annual, Annual                              |
| - Weighting: Equal Weight, Market Cap Weight, Volatility Parity                    |
+------------------------------------------------------------------------------------+
| MODE 3: 2-STAGE HYBRID FUNNEL                                                      |
| - Stage 1 (Quality Gate): Altman Z Safe + Beneish Clean + RKV Trap Free + Liquidity|
| - Stage 2 (Timing Gate): Execute only when MoS discount trigger fires              |
| - Measurable Edge: Significant Max Drawdown reduction & higher Sharpe vs Mode 2    |
+------------------------------------------------------------------------------------+
```

### Backtest Engine Components & Data Flow
1. **Point-in-Time Price Feeds**: Reads from `historical_prices.json` across 2016-2026.
2. **Execution Realism**:
   - Friction: 0.15% Brokerage Commission + 0.10% Tax on Sell = 0.25% round-trip.
   - Slippage: 0.10% market impact buffer.
   - Price limit clamps: HOSE $\pm 7\%$, HNX $\pm 10\%$, UPCOM $\pm 15\%$.
3. **Quant Metrics Engine**:
   - Total Return, CAGR ($\%$)
   - Max Drawdown (MDD $\%$), Max Drawdown Duration (Quarters)
   - Annualized Volatility ($\%$)
   - Sharpe Ratio ($R_f = 5.0\%$)
   - Sortino Ratio (Downside deviation only)
   - Win Rate ($\%$), Profit Factor
   - Alpha, Beta against VN-Index Benchmark
   - Year-by-Year returns breakdown matrix (2021, 2022, 2023, 2024, 2025, 2026 YTD).

---

## 6. End-to-End API Architecture (R4 Mapping)

The following endpoints will be integrated into `server.py`:

| Endpoint | Method | Params / Payload | Description |
|---|---|---|---|
| `/api/valuation/matrix` | GET / POST | `symbol: str`, `scenario: str = "base"` | Returns full 22 models valuation table, Bear/Base/Bull spreads, Upside %, and Model Weights. |
| `/api/valuation/composite` | GET | `symbol: str` | Returns composite Fair Value, IVW breakdown, Altman Z, Beneish M, and RKV trap score. |
| `/api/valuation/wacc` | GET | `symbol: str` | Returns 5-Factor CAPM parameters, synthetic debt rating, and calculated WACC. |
| `/api/valuation/backtest/run` | POST | `{ mode: "mode1"\|"mode2"\|"mode3", strategy_id, mos, exit_premium, start_quarter, end_quarter }` | Executes deterministic 3-mode backtest run and returns equity curve, metrics, and trade logs. |
| `/api/valuation/backtest/compare` | POST | `{ modes: ["mode1", "mode2", "mode3"], ... }` | Runs side-by-side comparison proving Hybrid Funnel drawdown reduction. |

---

## 7. Verification & Testing Strategy (R5 Mapping)

1. **Automated Unit Tests in `tests/test_valuation_engine.py`**:
   - Mathematical formula correctness for all 22 valuation models.
   - Boundary tests for negative EPS, zero BVPS, negative FCF, extreme multiples.
   - IVW weight calculation and zero-track-record fallbacks.
   - WACC calculations with Damodaran synthetic credit spread mapping.
2. **Backtest Suite in `tests/test_fair_value_backtest.py`**:
   - Mode 1, Mode 2, Mode 3 execution tests.
   - Zero lookahead bias verification.
   - Verification of Sharpe, Sortino, Drawdown mathematical formulas.
3. **API Contract Tests in `tests/test_valuation_api.py`**:
   - Response serialization, JSON schema validation, < 200ms latency verification.

---
