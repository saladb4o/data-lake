## 2026-08-28T19:03:58Z
You are Worker (Frontend Responsiveness & Static Asset Hardening - Milestone 2).
Your working directory is: c:/Users/Admin/Documents/Vibecoding vnstock/.agents/worker_frontend_m2/
Project root: c:/Users/Admin/Documents/Vibecoding vnstock

MANDATORY FIRST STEP: Read the Authoritative User Request at:
c:/Users/Admin/Documents/Vibecoding vnstock/.agents/ORIGINAL_REQUEST.md
Also read:
- `c:/Users/Admin/Documents/Vibecoding vnstock/PROJECT.md`
- `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/explorer_audit_frontend/analysis.md`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

EXCLUSIVE FILE WRITE OWNERSHIP:
You exclusively own and may edit ONLY these files:
- `static/js/app.js`
- `static/js/chart.js`
- `static/css/style.css`
- `static/index.html`
- Your working directory metadata files under `.agents/worker_frontend_m2/`

DO NOT edit any python backend files (owned by Backend Worker).

Tasks to implement:
1. UI-01: Debounce input listeners: In `static/js/app.js`, add a 150ms debounce utility function (e.g. `debounce(fn, delay)`) and apply it to `#boardFilterInput` input listener (`renderFilteredTradingBoard`) and `#quantKeyword` input listener.
2. UI-02: AbortController on rapid ticker switching: In `static/js/app.js:loadStockDetails()`, abort any in-flight stock detail requests before initiating a new stock request to avoid out-of-order race condition overwrites.
3. UI-03: Visibility-aware polling: In `static/js/app.js`, modify background interval polling (`fetchTradingBoard`, `fetchIndicesAnalytics`, `pollFiredAlerts`, `fetchDataLakeStatus`) so they pause when `document.hidden` is true (via `document.addEventListener('visibilitychange')`).
4. UI-04: Robust UI error state handlers: In `static/js/app.js`, ensure fetch rejection and error branches clear loading shimmers/spinners and render informative error alerts in UI containers.
5. UI-05: HTML escaping in tables: In `static/js/app.js:renderCleanTradingBoard()`, sanitize/escape company names (`r.name`) to prevent HTML formatting disruption.
6. UI-06: Chart lifecycle cleanup: In `static/js/chart.js`, explicitly call `chart.remove()` prior to re-initializing chart containers on interval/theme switches to prevent memory leaks and orphaned event listeners.

Verification:
- Inspect modified files for syntax errors and correct DOM event wiring.
- Deliver your handoff report to `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/worker_frontend_m2/handoff.md` and send a completion message to the caller.
