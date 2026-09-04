## 2026-09-02T10:46:01Z

You are the Implementation Worker for Milestone 1 (M1: Dynamic 3-Way Statement Engine).

Your working directory is: c:\Users\Admin\Documents\Vibecoding vnstock\.agents\worker_m1

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\ORIGINAL_REQUEST.md
Also read `PROJECT.md` at `c:\Users\Admin\Documents\Vibecoding vnstock\PROJECT.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Ownership:
You exclusively own `services/three_statement_engine.py`.

Scope & Tasks:
1. Verify and implement/refine `services/three_statement_engine.py` to ensure:
   - Full 5-year integrated forecast for P&L, BS, and Direct Method CFS for any VN symbol.
   - Dynamic Statement Link 1: Net Profit After Tax ($NPAT \to \text{Retained Profits}$ roll-forward $\text{RE}_t = \text{RE}_{t-1} + \text{NPAT}_t - \text{Dividends}_t$).
   - Dynamic Statement Link 2: Net change in cash directly links to Balance Sheet ending cash asset line ($\text{Cash}_t = \text{Cash}_{t-1} + \Delta\text{Cash}_t$).
   - Strict Balance Sheet closure: $|\text{Total Assets}_t - (\text{Total Liabilities}_t + \text{Total Equity}_t)| < 10^{-5}$ across all 5 forecast years.
   - Direct Method Cash Flow conservation: Cash from customers, cash paid to suppliers/opex/tax/interest reconciles to Net CFO ($\text{NPAT} + \text{D\&A} - \Delta\text{NWC}$).
   - Liquidity Distress Firewall & Negative Cash Risk Alert: Detects $\text{Cash}_t < 0$, calculates shortfall ratio, equity dilution penalty (5%-25%), MoS penalty (5%-15%), and diagnostic messaging.
   - Downstream cash flow generation for valuation models: FCFF, FCFE, Buffett Owner's Earnings, and DDM streams.
2. Run tests to verify your implementation:
   `pytest -v tests/test_three_statement_engine.py`
3. Document your changes, test results, and file diffs in `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\worker_m1\handoff.md` and `progress.md`.
4. Send a message to your parent when done.
