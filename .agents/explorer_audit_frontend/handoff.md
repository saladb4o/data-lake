# Handoff Report: Frontend & Static Assets UI Audit

**Agent**: Explorer (Frontend & Static Assets UI Audit)  
**Date**: 2026-08-29  
**Working Directory**: `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/explorer_audit_frontend/`  
**Handoff Type**: Hard (Task Complete)

---

## 1. Observation

Direct examination of client-side static assets (`static/index.html`, `static/js/app.js`, `static/js/chart.js`, `static/js/sector_rotation.js`, `static/js/treemap.js`, `static/css/style.css`) revealed the following concrete technical observations:

1. **Un-debounced Keypress Event Listener**:
   - In `static/js/app.js:496-498`:
     ```javascript
     boardFilterInput.addEventListener('input', (e) => {
       this.boardFilterKeyword = e.target.value.trim().toLowerCase();
       this.renderFilteredTradingBoard();
     });
     ```
   - Triggers `renderCleanTradingBoard` (lines 1500–1620) on every single keystroke. `renderCleanTradingBoard` executes full `tbody.innerHTML = ...` reconstruction over 400+ DOM rows without requestAnimationFrame or debounce buffering.
2. **Unconditional Background Polling Timers**:
   - In `static/js/app.js:106-118`:
     ```javascript
     setInterval(() => this.fetchIndicesAnalytics(), 30000);
     setInterval(() => this.fetchDataLakeStatus(), 60000);
     setInterval(() => this.fetchTradingBoard(), 20000);
     setInterval(() => this.pollFiredAlerts(), 30000);
     ```
   - Polling timers are active continuously regardless of `document.visibilityState` (browser tab background/inactive) or the active tab (e.g. user working in Backtesting or Valuation tabs).
3. **Race Conditions in Rapid Stock Selection**:
   - In `static/js/app.js:1220-1370` (`loadStockDetails`), clicking ticker items dispatches ~10 concurrent asynchronous fetch requests without an `AbortController`. Rapid sequential stock selection allows earlier slower requests to resolve after newer requests, resulting in stale UI overwrite.
4. **Silent Fetch Rejections and Missing Error States**:
   - In `static/js/app.js:1381, 1455, 2780, 5300, 6480`, fetch handlers check `if (json.status !== 'success' || !json.data) return;` without clearing loading shimmers (`⏳ Đang tính toán dữ liệu...`), leaving containers in permanent loading states if the API returns 500 or error payloads.
5. **Direct Unescaped HTML Interpolation**:
   - In `static/js/app.js:1594-1620` (`renderCleanTradingBoard`), company names (`r.name`) and symbols are directly interpolated into table row HTML without `escapeHTML(r.name)`.
6. **Chart & Canvas Lifecycle Synchronization**:
   - In `static/js/chart.js:8-69`, `sanitizeSeriesData` effectively normalizes BusinessDay and unix timestamp objects, preventing LightweightCharts scale crashes. However, chart canvas destruction during interval switches (`initCharts`) relies on innerHTML resetting without explicitly calling `chart.remove()`.

---

## 2. Logic Chain

1. **Keystroke Performance**: Because typing in the trading board filter immediately triggers a full table re-render without debouncing, the main UI thread executes layout recalculations and garbage collections on every keystroke, resulting in observable typing latency on large symbol lists.
2. **Network Saturation**: Because background interval timers run unconditionally across all tabs, backend API capacity is continuously consumed by background board updates even when the user is performing heavy client-side computations (e.g., Monte Carlo simulations).
3. **Data Integrity**: Because stock detail requests lack `AbortController` cancellation, asynchronous network latency variations can cause out-of-order state application when switching between tickers quickly.
4. **UI Resilience**: Because error branches in fetch methods return silently without updating DOM containers, users cannot distinguish between slow network requests and failed backend endpoints.
5. **Security & Layout Stability**: Because `renderCleanTradingBoard` omits string escaping on company names, unexpected characters in market feeds can disrupt DOM table formatting.

---

## 3. Caveats

- **Backend API Contract Assumptions**: The audit analyzed client-side behavior against the existing FastAPI endpoint routes (`/api/board/*`, `/api/valuation/*`, `/api/quant/*`, `/api/backtest/*`). Backend server performance under high concurrent load was not measured directly.
- **Browser Compatibility**: Audio/video elements are not used; LightweightCharts and HTML5 Canvas are supported on all modern Evergreen browsers (Chrome, Edge, Firefox, Safari).

---

## 4. Conclusion

The client application architecture is robust, highly modular, and provides comprehensive institutional analytics. However, immediate remediation is recommended for:
1. Adding a 150ms debounce to `boardFilterInput` and `quantKeyword`.
2. Adding `AbortController` request cancellation to `loadStockDetails`.
3. Adding `document.visibilityState` checks to suspend polling in hidden tabs.
4. Standardizing UI error state banners when API calls fail or return error statuses.
5. Escaping company names in `renderCleanTradingBoard`.

Detailed remediation proposals with exact before/after patterns are documented in `.agents/explorer_audit_frontend/analysis.md`.

---

## 5. Verification Method

To independently verify the observations and findings:

1. **Verify Un-debounced Keystroke Lag**:
   - Open browser developer tools → Performance tab.
   - Type rapidly into `#boardFilterInput` on the Trading Board.
   - Inspect CPU profile for repeated layout thrashing and string concatenation spikes at `app.js:496`.
2. **Verify Background Polling**:
   - Open Network tab, filter by `Fetch/XHR`.
   - Minimize browser tab or switch to another OS window for 60 seconds.
   - Observe recurring requests to `/api/board/trading-clean` and `/api/board/indices` every 20-30 seconds.
3. **Inspect File Locations**:
   - Review `static/js/app.js` lines 496–498, 106–118, 1220–1370, 1594–1620.
   - Review `static/js/chart.js` lines 8–69, 131–146.
   - Review `.agents/explorer_audit_frontend/analysis.md` for the full technical breakdown.
