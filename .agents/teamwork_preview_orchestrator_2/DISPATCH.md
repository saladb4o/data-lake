## 2026-08-31T14:37:06Z
Mission:
Comprehensive optimization and rigorous zero-compromise hardening of the Pure Valuation Quantitative Backtest Engine (Định Giá Nội Tại Thuần Túy) across 100% of the stock universe, ensuring all valid tickers and historical periods are processed with genuine point-in-time financial data, zero lookahead bias, no fake/random data, no synthetic shortcuts or truncation tricks, and maximum mathematical/caching performance.

Key Requirements:
R1. 100% Universe Coverage Without Truncation or Heuristic Shortcuts:
- Process all valid universe stocks across all available listing boards (HOSE, HNX, UPCOM, VN30, VN70, VN100, and full 1,600+ stock Data Lake) without arbitrary `[:200]` caps, artificial exclusions, or dummy placeholders.
- Ensure all historical quarterly timelines and rebalance cadences (quarterly, semi-annual, annual) evaluate all valid Point-in-Time fundamental and pricing records in the data lake.

R2. Strict Quantitative Integrity & Authentic Point-in-Time Valuation:
- Compute intrinsic fair values using genuine historical fundamentals (EPS, BVPS, ROE, ROIC, Net Margin, Debt, Cash, EBITDA, FCF, CAPEX) for all active valuation models (DCF 2-Stage McKinsey, Greenwald EPV, RIM/EBO, Buffett Owner's Earnings, Rhodes-Kropf P/B, Graham Growth, Blended Composite, Omnibus SMAPE/MALE/WMAPE/RMSLE/IVW).
- Zero lookahead bias, zero synthetic/random fallback data, and strict Margin of Safety (MoS) filtering with Dynamic Beta (beta-) and Toxic Firewalls (Altman Z'', Beneish M, Rhodes-Kropf Value Trap).

R3. High-Performance Execution & Algorithmic Vectorization:
- Maximize calculation throughput and eliminate CPU/memory bottlenecks through efficient in-memory pre-indexing, vectorized quarterly evaluation, fast dictionary lookups, and multi-tier LRU caching of invariant financial metrics across simulation quarters.
- Ensure the backtesting engine achieves sub-second to low-second responsiveness even when running universe-wide backtests across multi-year horizons.

R4. Automated Continuous Test Loop & Zero-Regression Verification:
- Execute and maintain 100% pass rate across the comprehensive pytest suite (`pytest tests/`).
- Verify empirical differentiation and accurate portfolio simulations across all valuation models with dedicated benchmarks.
