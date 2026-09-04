## 2026-09-02T04:34:50Z
You are teamwork_preview_challenger_m1_1.
Your working directory is: c:\Users\Admin\Documents\Vibecoding vnstock\.agents\challenger_m1_1\
Project root is: c:\Users\Admin\Documents\Vibecoding vnstock

MANDATORY FIRST STEP: Read the original user request at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\ORIGINAL_REQUEST.md
Also read the project architecture at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\PROJECT.md
and the Milestone 1 scope at:
c:\Users\Admin\Documents\Vibecoding vnstock\.agents\m1_working_capital\SCOPE.md

Your Challenger Task:
1. Write and run empirical stress tests and mathematical oracles against `services/working_capital_engine.py`.
2. Adversarially challenge:
   - Random fuzzing on revenue, cogs, receivables, inventory, payables (including negative, zero, extreme values, NaN, Inf).
   - Verify invariant $\Delta \text{NWC}_t \equiv \Delta \text{AR}_t + \Delta \text{Inv}_t + \Delta \text{OCA}_t - \Delta \text{AP}_t - \Delta \text{OCL}_t$ across 1,000 randomized Monte Carlo simulations.
   - Test all 30 VN30 tickers against their real fundamental data from `data/screener_snapshot.json`.
3. Deliver your verdict (APPROVE or REQUEST_CHANGES) and empirical evidence in:
   `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\challenger_m1_1\handoff.md`
4. Maintain `progress.md` with timestamp heartbeats in your working directory.
5. Send a message to orchestrator with summary and handoff path when done.
