# Handoff Report - Explorer 2 (Valuation Matrix & Data Lake Explorer)

## 1. Observation
- **Valuation Engine Core (`services/valuation_engine.py`)**:
  - Contains 22 quantitative valuation models (Lines 836–1564): 8 relative multiples (`blended_pe`, `ps_margin_adj`, `p_fcf`, `pb_rhodes_kropf`, `p_tbv`, `ev_ebitda`, `p_cf`, `p_affo`), 7 absolute intrinsic models (`dcf_2stage_mckinsey`, `rim_edwards_bell_ohlson`, `greenwald_epv`, `graham_growth`, `rule_of_40_growth`, `acquirers_multiple_ev_ebit`, `buffett_owners_earnings`), and 7 sector-specific models (`pharma_rnpv`, `bank_equity_cash_flow`, `reit_affo_dcf`, `telecom_unbundled_sotp`, `industrial_apv`, `consumer_eva_mva`, `utilities_3stage_ddm`).
  - `WACCEngine.calculate` (Lines 384–528) calculates 5-Factor Vietnam CAPM $K_e$ (Market Beta, Size SMB, Value HML, Momentum UMD, Amihud ILLIQ, Profitability RMW) and Damodaran Synthetic Credit Rating table $K_d$ based on Interest Coverage Ratio ($ICR$).
  - `RiskFirewallEngine` (Lines 534–833) calculates 4-variable Emerging Market Altman $Z''$-Score ($6.56X_1 + 3.26X_2 + 6.72X_3 + 1.05X_4$), 8-variable Beneish $M$-Score (threshold $-1.78$), 4-Quadrant classification (`safe_institutional`, `distressed_turnaround`, `toxic_exclusion`, `forensic_trap`), Rhodes-Kropf $\ln(M/B)$ decomposition with Value Trap ($P/B < 1.5$ and justified $V/B < 1.0$) vs True Deep Value detection, and Dynamic Margin of Safety ($MoS$) scaled by Downside Beta ($\beta^-$) with additive risk penalties.
  - `AdaptiveWeightingEngine` (Lines 1569–1766) supports dual composite modes: `mode="blended"` (using sector structural priors `SECTOR_WEIGHT_PRIORS`) and `mode="omnibus"` (evaluating error metrics: SMAPE, MALE, WMAPE, RMSLE, IVW with evidence ramp and 1.5x IQR outlier rejection).
  - `ScenarioEngine` (Lines 1772–1870) computes Bear/Base/Bull scenario fair values and a 5x5 WACC vs Terminal Growth sensitivity matrix.
- **Data Lake Files (`data/`)**:
  - `data/all_symbols.json`: 64,060 lines, 1.66MB, 4,000+ instruments across HOSE, HNX, UPCOM, ETF, CW, and Bond types.
  - `data/screener_snapshot.json`: 265,166 lines, 7.64MB, 1,645 tickers with verified 4-pillar financial metrics (EPS, BVPS, ROE, ROIC, Net Margin, Debt, Cash, EBITDA, FCF, CAPEX, D/E, Current Ratio, Quick Ratio, ICR, Rule of 40).
  - `data/historical_prices.json`: 472,937 lines, 13.35MB, 1,306 symbols with quarterly OHLCV bars spanning 2021-Q1 through 2026-Q1.
  - `data/industries.json`: 1.75MB, complete ICB classification mapping (Levels 1 to 4).
- **Universe & Index Support (`services/stock_service.py` & `services/fair_value_backtest_service.py`)**:
  - `VN30_SYMBOLS` (30 tickers), `VN70_SYMBOLS` (70 tickers), `VNMID_SYMBOLS` (70 tickers), and `VN100_SYMBOLS` (100 tickers) defined in `services/stock_service.py` (Lines 215–240).
  - `get_quant_screener(exchange=...)` (Lines 7810–7984) filters by `INDEX_UNIVERSE_MAP` and exchange names without altering true listing board (`HOSE`).
  - In `services/fair_value_backtest_service.py` Lines 593–599, under `VALUATION_ONLY` mode, candidates are capped at `[:200]`:
    ```python
    if not custom_symbols and len(candidates) > 200:
        candidates = sorted(candidates, key=lambda s: float(s.get("market_cap") or s.get("price", 0) * 1e7), reverse=True)[:200]
    ```
- **API Endpoints (`server.py`)**:
  - Comprehensive valuation routes: `GET /api/valuation/comprehensive/{symbol}`, `GET /api/valuation/matrix/{symbol}`, and `GET /api/valuation/matrix?symbol=...` (Lines 1237–1280).
  - Backtesting routes: `GET/POST /api/backtest/fair_value/run` and `GET/POST /api/backtest/fair-value/run` (Lines 1295–1350).
  - Presets route: `GET /api/backtest/fair_value/presets` and `GET /api/backtest/fair-value/presets` (Lines 1283–1292).

## 2. Logic Chain
1. The 22 valuation models in `services/valuation_engine.py` derive intrinsic fair values from fundamental financial statement metrics (EPS, BVPS, ROE, ROIC, Net Margin, Debt, Cash, EBITDA, FCF, CAPEX) with closed-form mathematical equations and defensive boundary caps (`clamp`, `safe_div`, non-negativity constraints).
2. The risk firewall integrates Altman $Z''$, Beneish $M$-Score, Rhodes-Kropf Value Trap detection, and Downside Beta scaling into a deterministic pipeline. Disqualification correctly flags Quadrant 3 (Toxic Exclusion: $Z'' < 1.10$ and $M \ge -1.78$) and Quadrant 4 (Forensic Trap: $M \ge -1.78$).
3. The data lake files provide verified fundamental metrics for 1,645 stocks (`screener_snapshot.json`) and quarterly price history for 1,306 stocks (`historical_prices.json`). Point-in-time constraints are preserved by taking entry prices from the start of the quarter and exit prices from future quarter OHLCV extremes.
4. Universe constituent filtering for VN30, VN70, VNMID, and VN100 is fully supported in `stock_service.py` and `fair_value_backtest_service.py`.
5. The `[:200]` candidate cap in `fair_value_backtest_service.py` (Line 599) restricts full-universe processing under `VALUATION_ONLY` mode and should be removed in Milestone M4.

## 3. Caveats
- While `historical_prices.json` covers 1,306 symbols with complete quarterly OHLCV series, some low-liquidity UPCOM tickers lack trading volume across all quarters and fall back gracefully to snapshot prices.
- Live external network calls to KBSEC/TradingView depend on network connectivity; when offline, the engine seamlessly uses the local JSON data lake.

## 4. Conclusion
The Valuation Matrix Engine and Data Lake infrastructure are mathematically sound, robustly structured, and meet institutional quant standards. All models compute authentic valuations without synthetic random shortcuts. Universe index resolution (VN30, VN70, VNMID, VN100) and API route aliases are verified and passing integration tests. The only minor optimization is lifting the `[:200]` cap in `fair_value_backtest_service.py` during Milestone M4.

## 5. Verification Method
1. Run pytest suite for valuation engine and API endpoints:
   - `pytest tests/test_valuation_engine.py`
   - `pytest tests/test_valuation_endpoints.py`
   - `pytest tests/test_m2_core_engine_api_hardening.py`
2. Inspect `survey_report.md` at `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/explorer_survey_2/survey_report.md`.
3. Invalidation condition: Any valuation model returning negative fair values, unhandled zero divisions, or failing to reject manipulated accounting records ($M \ge -1.78$).
