# E2E Test Infra: Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem

## Test Philosophy
- Opaque-box, requirement-driven testing. Validates exact mathematical invariants, financial statement conservation, formula syntax correctness in generated Excel workbooks, and REST API contract compliance.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing (all 30 VN30 blue chips + retail + distressed + financial sector tickers).

## Feature Inventory & Test Mapping
| # | Feature | Source (Requirement) | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---|---|:---:|:---:|:---:|:---:|
| 1 | 5Y 3-Way Synchronized Forecasting | docs/ORIGINAL_REQUEST.md §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Strict Balance Sheet Closure ($|\text{TA} - (\text{TL}+\text{TE})| < 10^{-5}$) | docs/ORIGINAL_REQUEST.md §R1 | 5 | 5 | ✓ | ✓ (100% VN30) |
| 3 | Statement Link 1 ($NPAT \to \text{Retained Profits}$) | docs/ORIGINAL_REQUEST.md §R1 | 5 | 5 | ✓ | ✓ |
| 4 | Statement Link 2 ($\Delta \text{Cash} \to \text{Cash}$) | docs/ORIGINAL_REQUEST.md §R1 | 5 | 5 | ✓ | ✓ |
| 5 | Direct Method CFS Reconciliation | docs/ORIGINAL_REQUEST.md §R1 | 5 | 5 | ✓ | ✓ |
| 6 | Working Capital Efficiency Ratios (DSO, DIO, DPO, CCC) | docs/ORIGINAL_REQUEST.md §R2 | 5 | 5 | ✓ | ✓ |
| 7 | Mean-Reverting NWC Schedule | docs/ORIGINAL_REQUEST.md §R2 | 5 | 5 | ✓ | ✓ |
| 8 | Negative CCC Retail Handling | docs/ORIGINAL_REQUEST.md §R2 | 5 | 5 | ✓ | ✓ (MWG) |
| 9 | Financial Sector Isolation (Banks/Brokers/Insurers) | docs/ORIGINAL_REQUEST.md §R2 | 5 | 5 | ✓ | ✓ (VCB, SSI) |
| 10 | Debt Amortization & Roll-Forward | docs/ORIGINAL_REQUEST.md §R4 | 5 | 5 | ✓ | ✓ |
| 11 | Damodaran Synthetic Ratings & Spreads | docs/ORIGINAL_REQUEST.md §R4 | 5 | 5 | ✓ | ✓ |
| 12 | Fixed-Point Circularity Solver | docs/ORIGINAL_REQUEST.md §R4 | 5 | 5 | ✓ | ✓ |
| 13 | Solvency Dividend & Covenant Firewall | docs/ORIGINAL_REQUEST.md §R4 | 5 | 5 | ✓ | ✓ |
| 14 | Liquidity Distress Firewall & Risk Penalties | docs/ORIGINAL_REQUEST.md §R3 | 5 | 5 | ✓ | ✓ |
| 15 | Dynamic Margin of Safety Integration | docs/ORIGINAL_REQUEST.md §R3 | 5 | 5 | ✓ | ✓ |
| 16 | 7-Tab Modano Excel Workbook Generator | docs/ORIGINAL_REQUEST.md §R5 | 5 | 5 | ✓ | ✓ |
| 17 | Live Dynamic Excel Formulas (`SUM`, `IF`, cell links) | docs/ORIGINAL_REQUEST.md §R5 | 5 | 5 | ✓ | ✓ |
| 18 | 2D Valuation Sensitivity Matrix (5x5 WACC vs g) | docs/ORIGINAL_REQUEST.md §R5 | 5 | 5 | ✓ | ✓ |
| 19 | Balance Check Audit Badge & Formatting | docs/ORIGINAL_REQUEST.md §R5 | 5 | 5 | ✓ | ✓ |
| 20 | FastAPI REST Endpoints (`/3-way-forecast`, `/export-excel`) | docs/ORIGINAL_REQUEST.md §R5 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Test Runner**: `pytest -v tests/`
- **Pass / Fail Semantics**: 100% of tests must pass with 0 failures and 0 errors (`exit_code == 0`).
- **Directory Layout**:
  - `tests/test_three_statement_engine.py`: Tiers 1-5 for 3-way balance, statement links, direct CFS, distress check, and VN30 constituent sweep.
  - `tests/test_working_capital_engine.py`: Tiers 1-4 for DSO/DIO/DPO/CCC, zero-division, negative CCC, and financial sector handling.
  - `tests/test_debt_capital_schedule_engine.py`: Tiers 1-4 for debt roll-forward, Damodaran ratings, fixed point solver, and dividend firewalls.
  - `tests/test_financial_model_exporter.py`: Tiers 1-5 for openpyxl workbook structure, dynamic formulas, sensitivity matrix, and cell references.
  - `tests/test_valuation_endpoints.py`: Tiers 1-4 for FastAPI REST endpoints and binary streaming file downloads.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|---|---|---|
| 1 | Standard Manufacturing / Blue-chip (`HPG`, `VNM`) | 3-Way 5Y Forecast, Working Capital, Debt Amortization, Excel Export | High |
| 2 | High-Growth Tech (`FPT`) | Revenue trajectory, NWC expansion, Intrinsic Valuation links | High |
| 3 | Retail with Negative CCC (`MWG`) | Negative CCC, Supplier Financing, Zero-Division guards | High |
| 4 | Commercial Bank / Financial Institution (`VCB`, `TCB`) | Financial sector isolation ($\text{NWC}=0$), Bank Equity Cash Flow | High |
| 5 | Distressed / High-Debt Real Estate (`NVL`) | Solvency firewall, Dividend Freeze, Liquidity Distress Penalty, MoS scaling | High |
| 6 | 30/30 Constituent Sweep (`VN30`) | Full VN30 constituent sweep validating $|\text{Net Assets} - \text{Total Equity}| < 10^{-5}$ across all 5 years | Critical |

## Coverage Thresholds
- Tier 1: $\ge 5$ test cases per feature (Happy-path isolation)
- Tier 2: $\ge 5$ boundary & corner test cases per feature (Micro-revenues, zero interest, negative margins, missing data)
- Tier 3: Pairwise cross-feature interaction testing
- Tier 4: $\ge 5$ real-world end-to-end workload scenarios (including all 30 VN30 tickers)
- Tier 5: Adversarial coverage hardening with stress generators

---

## Running the Suite

Install runtime + dev dependencies, then run pytest:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                      # everything (needs live network access)
pytest -m "not network"     # deterministic tier only - this is what CI gates on
pytest -m network           # live-upstream integration tier only
```

### Two tiers

The suite is split by whether a test reaches a live upstream:

| Tier | Selector | Count | Notes |
|---|---|---:|---|
| Deterministic | `-m "not network"` | 535 | Pure logic over fixtures/synthetic inputs. Offline, reproducible, gated in CI (`.github/workflows/ci.yml`). |
| Network | `-m network` | 322 | Hits vnstock, VNDirect, TradingView and RSS feeds. Expect failures offline, and rate-limit failures on the community vnstock tier (60 requests/minute). |

Network tests are marked centrally by module in `tests/conftest.py` (`NETWORK_TEST_MODULES`)
rather than with per-test decorators. When adding a test module that reaches a live
API, add it to that set so it does not destabilise CI.
