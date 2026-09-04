# Milestone 2 Handoff Report: Working Capital Days & NWC Analyzer

## 1. Observation
- **File Ownership**: `services/working_capital_engine.py` (exclusive) and `tests/test_working_capital_engine.py`.
- **Target Specifications**:
  - `PROJECT.md` Section 1: Working Capital Engine $\leftrightarrow$ Three-Statement Engine interface contract:
    - Model: `WorkingCapitalSchedulePeriod` with fields `year`, `revenue`, `cogs`, `dso`, `dio`, `dpo`, `ccc`, `accounts_receivable`, `inventory`, `other_current_assets`, `accounts_payable`, `other_current_liabilities`, `trade_working_capital`, `total_operating_nwc`, `delta_trade_nwc`, `delta_total_nwc`, `cash_collected_from_customers`, `cash_paid_to_suppliers`, `cash_paid_for_opex`.
    - Function: `build_working_capital_schedule(base_data, revenue_series, cogs_series, sga_series, start_year=2026, mean_revert_speed=0.0, sector=None) -> List[WorkingCapitalSchedulePeriod]`.
- **Observed Behavior & Test Run**:
  - Executed `pytest -v tests/test_working_capital_engine.py` via PowerShell.
  - Result: `72 passed in 0.29s` with 0 failures across Tiers 1–6.
  - Verbatim test output snippet:
    ```
    tests/test_working_capital_engine.py::TestTier1StandardCalculations::test_calculate_historical_days_standard PASSED
    tests/test_working_capital_engine.py::TestTier2BoundaryAndAdversarial::test_extreme_working_capital_days_clamping PASSED
    tests/test_working_capital_engine.py::TestTier3AccountingInvariants::test_delta_nwc_component_additivity_invariant PASSED
    tests/test_working_capital_engine.py::TestTier4VN30Integration::test_full_vn30_batch_execution PASSED
    tests/test_working_capital_engine.py::TestTier6ModanoInterfaceAndDirectOpexBridges::test_build_working_capital_schedule_interface_contract PASSED
    tests/test_working_capital_engine.py::TestTier6ModanoInterfaceAndDirectOpexBridges::test_direct_method_opex_cash_flow_bridge PASSED
    ============================= 72 passed in 0.29s ==============================
    ```

## 2. Logic Chain
1. **Mathematical Accuracy & Clamping**:
   - DSO is computed as $\text{DSO} = (\text{AR} / \text{Revenue}) \times 365$.
   - DIO is computed as $\text{DIO} = (\text{Inventory} / \text{COGS}) \times 365$.
   - DPO is computed as $\text{DPO} = (\text{AP} / \text{COGS}) \times 365$.
   - Activity days are safely guarded against zero/NaN/negative revenues and costs using calibrated sector fallback priors, clamped to $[0, 1095]$ days.
   - CCC is computed as $\text{CCC} = \text{DSO} + \text{DIO} - \text{DPO}$, unclamped to preserve economically valid negative working capital cycles for retailers (e.g. MWG).
2. **Mean-Reverting Multi-Period Projections**:
   - For each forecast period $t \in [1, 5]$, efficiency days revert geometrically: $\text{Day}_t = \text{Day}_{t-1}(1 - \lambda) + \text{Prior} \cdot \lambda$ where $\lambda \in [0, 1]$.
   - Balance sheet assets and liabilities are derived from projected efficiency days: $\text{AR}_t = (\text{DSO}_t \cdot R_t)/365$, $\text{Inv}_t = (\text{DIO}_t \cdot \text{COGS}_t)/365$, $\text{AP}_t = (\text{DPO}_t \cdot \text{COGS}_t)/365$.
   - Component additivity invariant holds exactly:
     $\Delta\text{NWC}_t = \Delta\text{AR}_t + \Delta\text{Inv}_t + \Delta\text{OCA}_t - \Delta\text{AP}_t - \Delta\text{OCL}_t$.
3. **Financial Sector Isolation**:
   - `FINANCIAL_SYMBOLS` identifies 42+ Vietnamese commercial banks (e.g. VCB, TCB, MBB, ACB, BID, CTG), securities brokerages (e.g. SSI, VND, VCI, HCM, SHS), and insurance companies (e.g. BVH, PVI, BMI, BIC).
   - For all financial institutions, $\text{DSO} = \text{DIO} = \text{DPO} = \text{CCC} = 0$, $\text{Trade NWC} = \text{Operating NWC} = 0$, and cash flows equal accrual revenue/COGS/SGA without working capital distortions.
4. **Direct Method Operating Cash Flow Bridges**:
   - Customer Cash Receipts: $\text{Cash}_{\text{cust}, t} = R_t - \Delta\text{AR}_t$.
   - Supplier Cash Payments: $\text{Cash}_{\text{supp}, t} = \text{COGS}_t + \Delta\text{Inv}_t - \Delta\text{AP}_t$.
   - OPEX Cash Payments: $\text{Cash}_{\text{opex}, t} = \text{SGA}_t + \Delta\text{OCA}_t - \Delta\text{OCL}_t$.
   - Gross CFO Invariant: $\text{Cash}_{\text{cust}, t} - \text{Cash}_{\text{supp}, t} = \text{Gross Profit}_t - \Delta\text{Trade NWC}_t$.
5. **Contract & Subscripting Compatibility**:
   - `WorkingCapitalSchedulePeriod` and `WorkingCapitalMetrics` support both object attributes (e.g. `p.trade_working_capital`, `p.cash_paid_for_opex`) and dictionary subscription (e.g. `p["dso"]`, `p["trade_working_capital"]`, `p.get("dpo")`), enabling seamless inter-module integration with Excel exporters and Three-Statement Engines.

## 3. Caveats
- No caveats. All 6 requirement pillars of Milestone 2 (DSO/DIO/DPO/CCC, zero-division safety, mean reversion, negative CCC preservation, financial sector isolation, and Direct Method cash bridges) are fully implemented, verified, and passing 100% of tests.

## 4. Conclusion
- Milestone 2 (`services/working_capital_engine.py`) is complete, robust, and verified against institutional financial modeling standards and all VN30 constituents.
- The module-level function `build_working_capital_schedule` and class methods conform to the `PROJECT.md` contract.

## 5. Verification Method
- Run the full test suite via terminal:
  ```powershell
  pytest -v tests/test_working_capital_engine.py
  ```
- Expected Result: 72 tests passed, 0 failures in $< 0.5\text{s}$.
- Invalidation Condition: Any failure in `tests/test_working_capital_engine.py` or regression in working capital metrics calculation.
