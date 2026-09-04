# E2E Test Infra: Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + BVA + Pairwise Combinatorial + Workload Testing.
- 100% automated pytest suite with zero mocks of business logic, validating against both mathematical axioms and local data lake datasets.

## Feature Inventory & Test Mapping
| # | Feature | Source (Requirement) | Tier 1 (Feature) | Tier 2 (BVA/Corner) | Tier 3 (Pairwise) | Tier 4 (Real-World Workload) |
|---|---------|---------------------|:----------------:|:-------------------:|:-----------------:|:----------------------------:|
| 1 | Working Capital Days & NWC | ORIGINAL_REQUEST §R2 | 5 tests | 5 tests | ✓ | ✓ |
| 2 | Debt & Capital Schedule Engine | ORIGINAL_REQUEST §R4 | 5 tests | 5 tests | ✓ | ✓ |
| 3 | Dynamic 3-Way Statement Engine | ORIGINAL_REQUEST §R1 | 5 tests | 5 tests | ✓ | ✓ |
| 4 | Exact Balance Sheet Closure | ORIGINAL_REQUEST §R1 | 5 tests | 5 tests | ✓ | ✓ |
| 5 | Direct Method Cash Reconciliation | ORIGINAL_REQUEST §R1 | 5 tests | 5 tests | ✓ | ✓ |
| 6 | Liquidity Distress Firewall & Valuation | ORIGINAL_REQUEST §R3 | 5 tests | 5 tests | ✓ | ✓ |
| 7 | Modano Dynamic Excel Exporter | ORIGINAL_REQUEST §R5 | 5 tests | 5 tests | ✓ | ✓ |
| 8 | FastAPI Endpoints & Downloads | ORIGINAL_REQUEST §R5 | 5 tests | 5 tests | ✓ | ✓ |

## Test Architecture
- Test runner: `pytest`
- Target test files:
  - `tests/test_working_capital_engine.py`
  - `tests/test_three_statement_engine.py`
  - `tests/test_financial_model_exporter.py`
  - `tests/test_valuation_engine.py`
  - `tests/test_valuation_endpoints.py`
- Execution command: `pytest tests/ -v`
- Pass/fail semantics: Exit code 0, 100% tests passed.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | VN30 Full-Universe 5-Year Balance Check | F1, F2, F3, F4, F5, F6, F7, F8 across all 30 VN30 tickers | High |
| 2 | Distressed Industrial Turnaround Case | F1, F2, F3, F6 (Negative cash, debt roll-forward, MOS risk penalties) | High |
| 3 | High-Growth Tech Capex & Working Capital Expansion | F1, F3, F4, F5 (FPT profile: expanding receivables, capex, positive CFO) | High |
| 4 | Capital-Intensive Steel/Manufacturing Cyclical | F1, F2, F3, F4, F5 (HPG profile: heavy inventory, debt service, capex) | High |
| 5 | Interactive Excel Export & Live Formula Integrity Check | F7, F8 (Multi-sheet cell links, SUM, IF balance checks in openpyxl) | High |

## Coverage Thresholds
- Tier 1: ≥5 per feature (Total ≥ 40 tests)
- Tier 2: ≥5 per feature (Total ≥ 40 tests)
- Tier 3: pairwise coverage of major feature interactions
- Tier 4: ≥5 realistic application scenarios (including full VN30 suite)
- Target: 100% pass rate with zero formula errors and zero regressions.
