# COMPREHENSIVE FRONTEND & STATIC ASSETS UI AUDIT REPORT

**Audit Date**: 2026-08-29  
**Auditor**: Explorer (Frontend & Static Assets UI Specialist)  
**Target Scope**: `static/index.html`, `static/js/app.js`, `static/js/chart.js`, `static/js/sector_rotation.js`, `static/js/treemap.js`, `static/js/treemap/*.js`, `static/css/style.css`, `static/css/treemap.css`

---

## Executive Summary

A comprehensive architectural and performance audit was conducted across all client-side assets in the Vnstock Terminal PRO application. The frontend is structured as a high-performance Vanilla JavaScript Single Page Application (SPA) driven by `VnstockApp` in `static/js/app.js` (8,614 lines), TradingView LightweightCharts (`static/js/chart.js`), SVG Relative Rotation Graphs (`static/js/sector_rotation.js`), and squarified hierarchical Treemaps (`static/js/treemap.js`).

While the application provides an institutional-grade feature suite (22-model FFV Pro valuation, 3-mode backtesting, quantile screener, ecosystem graphs, macroeconomic trackers, real-time depth ladders), several critical performance bottlenecks, un-debounced DOM thrashing events, uncoordinated polling timers, race conditions on rapid stock switching, and unhandled promise/error states were discovered that degrade responsiveness and user stability.

---

## Audit Dimension 1: Performance Bottlenecks, DOM Manipulation & Main-Thread Blocking

### 1.1 Un-Debounced Trading Board Real-Time Filter
- **File & Line**: `static/js/app.js:496-498`
- **Observation**:
  ```javascript
  boardFilterInput.addEventListener('input', (e) => {
    this.boardFilterKeyword = e.target.value.trim().toLowerCase();
    this.renderFilteredTradingBoard();
  });
  ```
- **Impact**: On every keystroke, `renderFilteredTradingBoard()` executes immediately without debouncing. It iterates across hundreds of symbols, performs regex/substring matching, and re-invokes `renderCleanTradingBoard()`.
- **Root Cause**: `renderCleanTradingBoard` (lines 1500–1620) rebuilds the entire table body via string concatenation and destroys/recreates the DOM (`tbody.innerHTML = ...`).
- **Consequence**: Severe typing lag, input frame drops, garbage collection spikes, and loss of table scroll/focus position during fast typing on large universes (e.g. HOSE 400+ symbols).
- **Remediation**:
  Wrap the input handler with a 150ms debounce utility:
  ```javascript
  boardFilterInput.addEventListener('input', this.debounce((e) => {
    this.boardFilterKeyword = e.target.value.trim().toLowerCase();
    this.renderFilteredTradingBoard();
  }, 150));
  ```

### 1.2 Full-Table DOM Destruction on Polling Ticks
- **File & Line**: `static/js/app.js:1500-1620` (`renderCleanTradingBoard`)
- **Observation**: When trading board data refreshes every 20 seconds via `fetchTradingBoard()`, the entire `tbody.innerHTML` of up to 400+ table rows is wiped and replaced.
- **Impact**:
  - Re-evaluates CSS layout and recalculates layout trees for 400+ `<tr>` and 4,000+ `<td>` elements.
  - Active hover states, row selections, and tooltip anchors get detached.
  - Causes visible layout micro-stutter (layout thrashing) on low-power devices and laptops on battery.
- **Remediation**:
  Implement key-based DOM row patching or targeted cell updates (`data-symbol` keyed rows) that only update mutated columns (price, change_pct, volume, foreign buy/sell) and apply `.tick-flash-up`/`.tick-flash-down` animations selectively to changed values rather than rebuilding all rows.

### 1.3 Un-Throttled Window Resize Listeners on Canvas & SVG Charts
- **File & Line**: `static/js/chart.js:547-550`, `static/js/app.js:7181-7185`
- **Observation**:
  ```javascript
  window.addEventListener('resize', () => {
    this.resize();
  });
  ```
  `setupBacktestCanvasHover()` and `setupResizeObserver()` bind raw resize listeners that immediately trigger multi-canvas context clearing and high-DPI scaling on every pixel delta during browser window resizing.
- **Remediation**:
  Throttle resize events using `requestAnimationFrame` or a 100ms debounce timer to prevent canvas redraw thrashing.

---

## Audit Dimension 2: Network Lifecycle, Redundant Polling & Request Cascades

### 2.1 Uncoordinated, Non-Tab-Aware Background Polling
- **File & Line**: `static/js/app.js:106-118` (`init()`)
- **Observation**:
  ```javascript
  // Polling timers initiated unconditionally
  setInterval(() => this.fetchIndicesAnalytics(), 30000);
  setInterval(() => this.fetchDataLakeStatus(), 60000);
  setInterval(() => this.fetchTradingBoard(), 20000);
  setInterval(() => this.pollFiredAlerts(), 30000);
  ```
- **Impact**:
  - All 4 polling intervals fire continuously even when the user has minimized the browser tab, switched to another OS application, or navigated to `tab_backtest` or `tab_quant`.
  - Trading board polling (`/api/board/indices` and `/api/board/trading-clean`) consumes backend worker threads and CPU while the user is analyzing a 10-year Monte Carlo backtest.
- **Remediation**:
  1. Integrate `document.visibilityState`: Pause all interval timers when `document.hidden === true` and trigger an immediate refresh upon tab focus.
  2. Implement Tab-Scoping: Only poll trading board data when `this.currentTab === 'board'`, poll foreign data when `this.currentTab === 'foreign'`, and pause board polling when inside backtest/quant tabs.

### 2.2 Race Conditions in Rapid Stock Selection (`inspectStock` / `loadStockDetails`)
- **File & Line**: `static/js/app.js:1220-1370` (`loadStockDetails`, `loadAllStockSubtabs`)
- **Observation**: When a user clicks a stock (e.g. `VCB`), `loadStockDetails` fires ~10 parallel asynchronous fetch requests (history, profile, technical, financials, valuation, peer group, news, leadership, events, reports). If the user quickly clicks another stock (e.g. `FPT`), another 10 requests fire.
- **Risk**:
  - Responses can resolve out of order. A slower VCB request completing after an FPT request will overwrite FPT's UI with VCB data.
  - Network saturation with 20+ concurrent HTTP/1.1 connections.
- **Remediation**:
  Use `AbortController` attached to the active stock inspection session:
  ```javascript
  if (this.currentStockAbortController) {
    this.currentStockAbortController.abort();
  }
  this.currentStockAbortController = new AbortController();
  const signal = this.currentStockAbortController.signal;
  // pass { signal } to all fetch calls
  ```

---

## Audit Dimension 3: Exception Handling, Promise Rejections & Broken UI States

### 3.1 Silent Fetch Abort / Missing Error Notifications
- **File & Line**: `static/js/app.js:1381, 1455, 2780, 5300, 6480`
- **Observation**:
  ```javascript
  const res = await fetch(url);
  const json = await res.json();
  if (json.status !== 'success' || !json.data) return;
  ```
- **Impact**:
  - If the backend returns `status: "error"` or `500 Internal Server Error`, the function simply returns without clearing loading placeholders or skeleton shimmers (e.g. `⏳ Đang tính toán dữ liệu...`).
  - The UI remains permanently in a stuck loading state with no user feedback.
- **Remediation**:
  Standardize response checking:
  ```javascript
  if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
  const json = await res.json();
  if (json.status !== 'success' || !json.data) {
    this.renderErrorState(containerId, json.message || 'Không thể tải dữ liệu');
    return;
  }
  ```

### 3.2 HTML Injection Risk via Unescaped Trading Board Fields
- **File & Line**: `static/js/app.js:1594-1620` (`renderCleanTradingBoard`)
- **Observation**: In `renderCleanTradingBoard`, stock names (`r.name`) and symbols are interpolated directly into template strings without `escapeHTML(r.name)`:
  ```javascript
  <td class="col-name" style="text-align:left;" title="${r.name}">${r.name}</td>
  ```
  In contrast, `renderMacroTradingBoard` correctly uses `escapeHTML(r.name)`.
- **Impact**: Potential XSS vulnerability or malformed DOM if upstream data contains unescaped quotes or HTML entities.
- **Remediation**: Consistently wrap all string interpolations with `escapeHTML()`.

---

## Audit Dimension 4: Chart Rendering, Data Sanitization & Visual Alignment

### 4.1 LightweightCharts Series Synchronization & Memory Safety
- **File & Line**: `static/js/chart.js:8-69` (`sanitizeSeriesData`), `static/js/chart.js:131-362` (`initCharts`)
- **Strengths**:
  - `sanitizeSeriesData()` rigorously cleans duplicate timestamps, NaN values, and normalizes BusinessDay objects to ISO strings, preventing LightweightCharts invariant violations.
  - Multi-pane crosshair synchronization (`mainChart`, `rsiChart`, `macdChart`) prevents infinite event loops via `isSyncingRange` and `isSyncingCrosshair` guards.
- **Finding**:
  - When switching between intraday intervals (timestamp numbers) and daily intervals (date strings), `initCharts` completely recreates chart DOM nodes. While necessary for LightweightCharts scale mode transitions, chart instances should be explicitly destroyed via `chart.remove()` prior to resetting `container.innerHTML = ''` to prevent canvas memory leaks.

### 4.2 SVG Relative Rotation Graph (RRG) DOM Cleanup
- **File & Line**: `static/js/sector_rotation.js:207-211` (`draw`)
- **Observation**:
  ```javascript
  var oldSvg = container.querySelector('svg.rrg-svg');
  if (oldSvg && oldSvg.parentNode) oldSvg.parentNode.removeChild(oldSvg);
  ```
- **Assessment**: Properly tears down previous SVG root before re-rendering. Scales and bounding boxes dynamically accommodate tails and outlier points with boundary padding.

---

## Audit Dimension 5: Responsive Layout, Theme Tokens & Mobile Usability

### 5.1 Mobile Horizontal Overflow on Data-Dense Tables
- **File & Line**: `static/index.html:150-320`, `static/css/style.css:1200-1450`
- **Observation**: Tables such as the 17-column Quant Screener, 22-Model FFV Pro valuation matrix, and Institutional Backtest trades log require minimum widths of 1,100px–1,400px.
- **Assessment**: All large tables are wrapped inside `.table-responsive` / `.table-scroll-wrap` with `overflow-x: auto; -webkit-overflow-scrolling: touch;`. Sticky columns for `#` and `Mã CK` ensure ticker visibility during horizontal panning.

### 5.2 Theme Consistency & Design System Tokens
- **File & Line**: `static/css/style.css:7-41`
- **Assessment**: Strict adherence to Vietnamese market color conventions:
  - Ceiling: `--color-ceil: #c084fc` (Purple)
  - Floor: `--color-floor: #22d3ee` (Cyan)
  - Gain: `--color-up: #10b981` (Emerald Green)
  - Loss: `--color-down: #ef4444` (Ruby Red)
  - Reference: `--color-ref: #f59e0b` (Amber/Yellow)
  - Brand Cyan: `--color-blue: #38bdf8`
  - Deep dark background palette: `--bg-main: #06090e`, `--bg-surface: #0f172a`.

---

## Prioritized Remediation Roadmap

| Priority | Issue | Affected Files | Expected Impact |
|---|---|---|---|
| **P0 (Critical)** | Add debounce to `boardFilterInput` & `quantKeyword` search | `static/js/app.js:496` | Eliminates UI freeze on typing; smooth 60fps filtering |
| **P0 (Critical)** | Add `AbortController` to stock inspection dispatches | `static/js/app.js:1220` | Eliminates race conditions & out-of-order data corruption |
| **P1 (High)** | Tab-aware & visibility-aware background polling | `static/js/app.js:106` | Reduces background CPU/network load by >70% |
| **P1 (High)** | Replace silent fetch aborts with explicit error UI states | `static/js/app.js:1381, 5300` | Prevents permanent stuck loading skeleton states |
| **P2 (Medium)** | Escape HTML strings in `renderCleanTradingBoard` | `static/js/app.js:1594` | Hardens against XSS and broken HTML layout |
| **P2 (Medium)** | Throttle window resize listeners with RAF | `static/js/chart.js:547` | Prevents canvas rendering stutter on window resize |
| **P3 (Low)** | Explicit `chart.remove()` disposal before re-init | `static/js/chart.js:144` | Prevents canvas context memory leaks on interval switches |

---
