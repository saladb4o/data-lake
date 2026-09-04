# Implementation Plan: Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem

## Objective
Implement and verify the complete 5-phase Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem upgrade into the Vietnam quantitative valuation and backtesting platform (`Vibecoding vnstock`), strictly satisfying requirements R1 through R5 and all acceptance criteria.

## Phase 0: Survey & Architecture Discovery
1. Spawn 3 Explorers / Spec Miners in parallel:
   - Explorer 1: Inspect existing services (`services/valuation_engine.py`, `services/fair_value_backtest_service.py`, `server.py`, `data/financial_models.json`, etc.) to map existing data structures, financial modeling patterns, and API routes.
   - Explorer 2: Analyze requirements R1, R2, R4 (3-way balance sheet math, retained profits, direct method cash flow, debt/capital schedules, NWC/working capital days) and formulate exact mathematical linkages and schemas.
   - Explorer 3: Analyze requirements R3, R5 and testing criteria (liquidity distress firewall, openpyxl Excel exporter with live formulas, FastAPI routes, and pytest suite requirements).
2. Synthesize findings into `PROJECT.md` at project root with full Feature Inventory, Module Boundaries, Milestones, and Interface Contracts.

## Phase 1: Dual-Track Execution
- **Track A: E2E Testing Track**
  - E2E Test Suite orchestrator/writer: Build comprehensive tests for 3-way balance sheet balance across VN30 symbols, direct method cash flow reconciliation, working capital metrics (DSO, DIO, DPO, CCC), distress firewall, debt schedules, and Excel exporter formulas.
  - Publish `TEST_READY.md`.
- **Track B: Implementation Track**
  - Milestone 1: Dynamic 3-Way Statement Engine (`services/three_statement_engine.py`) (R1)
  - Milestone 2: Working Capital Days & NWC Analyzer (`services/working_capital_engine.py`) (R2)
  - Milestone 3: Capital Allocation, Debt Schedules, Liquidity Distress Firewall & Valuation Integration (`services/debt_capital_schedule_engine.py`, `services/valuation_engine.py`, `services/fair_value_backtest_service.py`) (R3, R4)
  - Milestone 4: Excel Model Exporter & FastAPI API Endpoints (`services/financial_model_exporter.py`, `server.py`) (R5)

## Phase 2: Final Verification & Adversarial Hardening
1. Run full E2E test suite (Tiers 1-4) across all modules and VN30 symbols.
2. Tier 5: Adversarial Coverage Hardening with Challengers.
3. Forensic Auditor Integrity Verification (`teamwork_preview_auditor`).
4. Reviewer Gate Sign-off.
5. Report completion to caller.
