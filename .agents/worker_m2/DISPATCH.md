## 2026-09-02T10:46:01Z

You are the Implementation Worker for Milestone 2 (M2: Working Capital Days & NWC Analyzer).

Your working directory is: c:\Users\Admin\Documents\Vibecoding vnstock\.agents\worker_m2

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\ORIGINAL_REQUEST.md
Also read `PROJECT.md` at `c:\Users\Admin\Documents\Vibecoding vnstock\PROJECT.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Ownership:
You exclusively own `services/working_capital_engine.py`.

Scope & Tasks:
1. Verify and implement/refine `services/working_capital_engine.py` to ensure:
   - Computation of historical and projected Debtor Days (DSO = (AR / Revenue) * 365), Inventory Days (DIO = (Inventory / COGS) * 365), Creditor Days (DPO = (AP / COGS) * 365), and Cash Conversion Cycle (CCC = DSO + DIO - DPO).
   - Safe division against zero/NaN on missing, zero, or negative financial data, with days clamped to $[0, 1095]$.
   - Mean-reverting working capital trajectory ($\lambda \in [0, 1]$) towards calibrated ICB sector priors.
   - Economic handling of negative CCC retail business models (e.g. MWG), preserving valid negative working capital without artificial clamping.
   - Financial sector isolation: automatically assigns $\text{DSO}=\text{DIO}=\text{DPO}=\text{NWC}=0$ for 42 banks, insurers, and brokerages.
   - Direct Method cash bridges: Cash collected from customers ($R - \Delta\text{AR}$), Cash paid to suppliers ($\text{COGS} + \Delta\text{Inv} - \Delta\text{AP}$), Cash paid for OPEX ($\text{SGA} + \Delta\text{OCA} - \Delta\text{OCL}$).
2. Run tests to verify your implementation:
   `pytest -v tests/test_working_capital_engine.py`
3. Document your changes, test results, and file diffs in `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\worker_m2\handoff.md` and `progress.md`.
4. Send a message to your parent when done.
