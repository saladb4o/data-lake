# Handoff Report — Milestone 1 Working Capital & Direct Cash Flow Integration Analysis

- **Agent**: `teamwork_preview_explorer_m1_2`
- **Role**: Explorer / Integration Architect
- **Target Deliverable**: `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m1_2\analysis_m1_integration.md`
- **Recipient**: Orchestrator / M1 Implementer
- **Timestamp**: 2026-09-02T11:28:00+07:00

---

## 1. Observation

1. **Data Lake Structure**:
   - `data/screener_snapshot.json` contains snapshot fundamental data for 1,645 stocks and 10 sector medians (`VNCOND`, `VNMAT`, `VNCONS`, `VNFIN`, `VNREAL`, `VNIT`, `VNIND`, `VNHEAL`, `VNUTI`, `VNENE`).
   - `data/financial_models.json` contains 2,500+ standard accounting line items indexed across 4 company forms (`NON_FINANCE`, `BANK`, `SECURITIES`, `INSURANCE`).
   - `services/stock_service.py` provides `resolve_data_file()`, `DiskDataLake`, and `get_company_financial_statements(symbol, statement_type, period, periods_count)`.

2. **Accounting Line Item Codes (VAS Circular 200 & `financial_models.json`)**:
   - Current Assets (`11000`): Cash (`11100`), ST Investments (`11200`), Accounts Receivable (`11300` / `11310`), Inventory (`11400` / `11410`), Other Current Assets (`11500`).
   - Current Liabilities (`13100`): Short-term Debt (`13110`), Accounts Payable (`13120`), Customer Advances (`13130`), Accrued Expenses (`13160`), Other Current Liabilities (`13190`).
   - Income Statement: Net Sales / Revenue (`21001`), Cost of Goods Sold (`22100`), Gross Profit (`23100`), SG&A (`22110` + `22200`), EBIT (`23110`), NPAT (`23003`).

3. **Empirical Verification across VN30**:
   - Executed live extraction on representative VN30 constituents (`HPG`, `VNM`, `MWG`, `FPT`, `GAS`, `GVR`, `BCM`, `BID`, `CTG`).
   - Verified for HPG (2025): Revenue = 156,116 B, COGS = 131,618 B, AR = 15,042 B ($DSO = 35.2$ d), Inv = 52,828 B ($DIO = 146.5$ d), AP = 21,183 B ($DPO = 58.7$ d), $CCC = 122.9$ d, Core NWC = 46,687 B.
   - 2024 to 2025 deltas for HPG: $\Delta AR = +7,394$ B, $\Delta Inv = +6,737$ B, $\Delta AP = +7,136$ B.
   - Direct Cash Flow Calculations: Cash Receipts = $156,116 - 7,394 = 148,722$ B; Cash Paid to Suppliers = $131,618 + 6,737 - 7,136 = 131,219$ B.

---

## 2. Logic Chain

1. **Step 1: Input Resolution**: `WorkingCapitalEngine` resolves data via `stock_service.get_company_financial_statements` or `screener_snapshot.json` with a 4-tier fallback hierarchy, guaranteeing immunity to missing files or missing fields.
2. **Step 2: Historical Days & NWC Computation**:
   - Days formulas: $DSO = \frac{AR}{Rev} \times 365$, $DIO = \frac{Inv}{COGS} \times 365$, $DPO = \frac{AP}{COGS} \times 365$, $CCC = DSO + DIO - DPO$.
   - Safety checks: When $Rev \le 0$ or $COGS \le 0$, fallback to sector priors (`SECTOR_BENCHMARKS`) and clamp bounds ($DSO \in [0, 365]$, $DIO \in [0, 730]$, $DPO \in [0, 365]$).
3. **Step 3: Forward Schedule Projection**:
   - Given projected revenue and COGS series for 5 forecast years, efficiency days are projected (either constant or mean-reverting toward sector benchmarks with speed $\lambda$).
   - Balance sheet balances are generated: $AR_t = Rev_t \times \frac{DSO_t}{365}$, $Inv_t = COGS_t \times \frac{DIO_t}{365}$, $AP_t = COGS_t \times \frac{DPO_t}{365}$.
4. **Step 4: Direct Method Cash Flow Derivation**:
   - Cash Receipts from Customers: $CF_{\text{cust}, t} = Revenue_t - \Delta AR_t$.
   - Cash Paid to Suppliers: $CF_{\text{supp}, t} = COGS_t + \Delta Inv_t - \Delta AP_t$.
   - Operating Cash Flow ($Net CFO$) derived via Direct Method is mathematically identical to Indirect Method ($NPAT + Depr - \Delta NWC$).
5. **Step 5: Statement Linkage**:
   - The projected working capital schedule feeds the Balance Sheet and Cash Flow Statement in `services/three_statement_engine.py` (M3), ensuring $|Total Assets - Total Liab \& Eq| < 10^{-5}$ and exact cash balance closure.

---

## 3. Caveats

1. **Financial Institutions & Banks**: Commercial banks (`BANK` form, ICB 8300) and insurance firms (`INSURANCE` form, ICB 8500) do not carry commercial trade inventory ($DIO \equiv 0.0$). The engine handles them safely with $DIO=0.0$ and fallback prior days, while specialized bank equity cash flows are handled in M4 (`valuation_engine.py`).
2. **Real Estate Developers**: Real estate developers (e.g., `BCM`, `VHM`, `NVL`) classify land banks and property development projects under inventory (Circular 200), resulting in high $DIO$ (> 1,000 days). Clamping $DIO$ upper bound to 730 days or allowing custom sector ceiling is provided.
3. **Indirect vs Direct CFS in Historical Reports**: Many Vietnamese corporations report statutory cash flow statements using the Indirect Method. The 3-Way Engine generates true Direct Method schedules dynamically from balance sheet deltas.

---

## 4. Conclusion

- The integration architecture and mathematical formulation for Milestone 1 are complete, validated, and fully documented in:
  `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m1_2\analysis_m1_integration.md`.
- `services/working_capital_engine.py` can be directly implemented using the provided Pydantic dataclasses, zero-division safeguards, and 5-year projection mechanics.
- The unit test suite in `tests/test_working_capital_engine.py` should test:
  1. Standard manufacturing calculation (e.g. `HPG`).
  2. FMCG / Retail negative CCC calculation (e.g. `MWG`, `MSN`).
  3. Tech / Service low inventory calculation (e.g. `FPT`).
  4. Zero/negative revenue/COGS adversarial input handling.
  5. 5-year forward schedule projection and delta verification.

---

## 5. Verification Method

To independently verify all findings and math in this report:

1. **Inspect the comprehensive analysis report**:
   `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_m1_2\analysis_m1_integration.md`
2. **Run the empirical verification test**:
   ```bash
   python .agents/teamwork_preview_explorer_m1_2/test_wc_math.py
   python .agents/teamwork_preview_explorer_m1_2/test_vn30_wc.py
   ```
3. **Execute standard test suite after implementation**:
   ```bash
   pytest tests/test_working_capital_engine.py
   ```
