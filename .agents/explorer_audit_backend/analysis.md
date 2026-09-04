# Comprehensive Backend Services & API Architecture Audit Report

**Date:** 2026-08-29  
**Auditor:** Explorer (Backend Services & API Audit)  
**Target Scope:** `server.py`, `services/`, `scripts/`, `tests/`  

---

## Executive Summary

An exhaustive inspection of the backend services, API routing layers, quantitative modeling engines, and data pipeline infrastructure was conducted. While the architecture shows high domain sophistication (porting 22 institutional valuation models, 3-mode backtesting engines, and multi-source accounting triangle imputations), several critical and moderate runtime bugs, exception vulnerabilities, async concurrency bottlenecks, and resilience gaps were identified across `server.py` and `services/`.

---

## Prioritized Findings Matrix

| ID | Category | Severity | File & Location | Description |
|---|---|---|---|---|
| **DEF-01** | NameError / Silent Failure | **CRITICAL** | `server.py:629` | `_os.path.exists` references undefined identifier `_os`, causing RRG disk cache loading to fail permanently. |
| **DEF-02** | Type Error / None Propagation | **CRITICAL** | `services/valuation_engine.py:2122-2149` | `dict.get("key", default)` returns `None` when keys are explicitly present as `None`, causing `TypeError` in model math. |
| **DEF-03** | Unhandled Exception / Poller Crash | **HIGH** | `server.py:160-170` | Unsafe `float()` casting on non-numeric quote fields in `_evaluate_rule` within background alert polling loop. |
| **DEF-04** | Concurrency / Event Loop Blocking | **HIGH** | `server.py:189` | Synchronous disk I/O (`_save_alert_rules`) called directly inside the asyncio event loop `_alerts_poll_loop`. |
| **DEF-05** | Deprecated API Usage | **MEDIUM** | `server.py:635, 709` | Deprecated `datetime.datetime.utcnow()` used in RRG cache timestamping. |
| **DEF-06** | Performance / Thread Churn | **MEDIUM** | `server.py:682` | `ThreadPoolExecutor(max_workers=11)` instantiated per-request rather than reusing shared pool. |
| **DEF-07** | Data Lake Hardcoded Path | **LOW** | `scripts/sync_unified_market_data.py:31` | Script hardcodes local `data/all_symbols.json` path instead of invoking `resolve_data_file()`. |

---

## In-Depth Analysis of Findings & Recommended Fixes

### 1. DEF-01: Undefined `_os` in `api_sectors_rrg()` Disk Cache Loader (CRITICAL)

- **Location:** `server.py`, Line 629
- **Observation:**
  ```python
  # server.py:625-633
  import json as _json
  _disk_path = _rrg_disk_path()
  _disk = {}
  try:
      if _os.path.exists(_disk_path):
          with open(_disk_path, "r", encoding="utf-8") as _f:
              _disk = _json.load(_f)
  except Exception:
      _disk = {}
  ```
- **Root Cause:** In line 629, `_os` is referenced without being imported (only `os` is imported at top level, or `_os` was forgotten in local import). The `NameError: name '_os' is not defined` is silently caught by `except Exception: _disk = {}`.
- **Impact:** The RRG Stale-While-Revalidate disk cache is **never** loaded across server restarts or cache misses. Every RRG call is forced to recompute all sector indices and benchmark history.
- **Recommended Fix:**
  Replace `_os.path.exists` with `os.path.exists` (or `import os as _os`).
  ```python
  # Proposed fix:
  if os.path.exists(_disk_path):
      with open(_disk_path, "r", encoding="utf-8") as _f:
          _disk = _json.load(_f)
  ```

---

### 2. DEF-02: `NoneType` Propagation in 22-Model Suite Parameter Unpacking (CRITICAL)

- **Location:** `services/valuation_engine.py`, Lines 2122–2150
- **Observation:**
  ```python
  # services/valuation_engine.py:2122-2149
  m17 = self.models_suite.model_17_bank_equity_cash_flow(
      net_income=net_income, rwa=fundamental_data.get("rwa", mcap * 1.2),
      book_equity=bvps * shares, roe=roe, ke=wacc_res.cost_of_equity, shares_out=shares, current_price=price
  )
  ...
  total_capex = fundamental_data.get("capex", ebitda - ebit)
  prev_rev = fundamental_data.get("prev_revenue", revenue * (1.0 - g_stage1))
  gross_ppe = fundamental_data.get("ppe_gross", fundamental_data.get("fixed_assets", mcap * 0.4))
  ```
- **Root Cause:** In Python, `dict.get(key, default)` returns the dictionary's value if the key exists in the dictionary. If a data lake record contains `{"rwa": null, "capex": null}`, `fundamental_data.get("rwa", default)` returns `None` instead of `mcap * 1.2`.
  Downstream inside `model_17_bank_equity_cash_flow`:
  ```python
  rwa_t = max(rwa, book_equity / target_car) # max(None, float) -> TypeError!
  ```
- **Impact:** Any stock with explicit `None`/`null` fields in `screener_snapshot.json` or `financial_models.json` causes unhandled `TypeError: '>' not supported between instances of 'float' and 'NoneType'`, failing `/api/valuation/comprehensive/{symbol}` with HTTP 500.
- **Recommended Fix:**
  Use `(fundamental_data.get(...) or default)` syntax:
  ```python
  # Proposed fix:
  rwa_val = fundamental_data.get("rwa")
  rwa_clean = float(rwa_val) if (rwa_val is not None and not math.isnan(float(rwa_val))) else (mcap * 1.2)
  
  capex_val = fundamental_data.get("capex")
  total_capex = float(capex_val) if capex_val is not None else (ebitda - ebit)
  
  prev_rev_val = fundamental_data.get("prev_revenue")
  prev_rev = float(prev_rev_val) if prev_rev_val is not None else (revenue * (1.0 - g_stage1))
  
  gross_ppe_val = fundamental_data.get("ppe_gross") or fundamental_data.get("fixed_assets")
  gross_ppe = float(gross_ppe_val) if gross_ppe_val is not None else (mcap * 0.4)
  ```

---

### 3. DEF-03: Unhandled ValueError in Server-Side Alert Evaluation (HIGH)

- **Location:** `server.py`, Lines 160–170
- **Observation:**
  ```python
  # server.py:160-170
  def _evaluate_rule(rule: dict, row: dict) -> bool:
      cond = rule.get("condition")
      value = float(rule.get("value") or 0)
      if cond == "price_above":
          return row.get("match_p") is not None and float(row["match_p"]) >= value
      if cond == "price_below":
          return row.get("match_p") is not None and float(row["match_p"]) <= value
      if cond == "pct_change":
          pct = row.get("match_pct")
          return pct is not None and abs(float(pct)) >= value
      return False
  ```
- **Root Cause:** When upstream price feeds return string place-holders like `"-"`, `"N/A"`, or `""`, `float(row["match_p"])` raises `ValueError: could not convert string to float`.
- **Impact:** Throws exception inside `_alerts_poll_loop()`, aborting that polling tick.
- **Recommended Fix:**
  Introduce a safe float parser helper:
  ```python
  def _safe_rule_float(val: Any) -> Optional[float]:
      if val is None:
          return None
      try:
          f = float(val)
          return None if (math.isnan(f) or math.isinf(f)) else f
      except (ValueError, TypeError):
          return None

  def _evaluate_rule(rule: dict, row: dict) -> bool:
      cond = rule.get("condition")
      value = _safe_rule_float(rule.get("value")) or 0.0
      p = _safe_rule_float(row.get("match_p"))
      if cond == "price_above":
          return p is not None and p >= value
      if cond == "price_below":
          return p is not None and p <= value
      if cond == "pct_change":
          pct = _safe_rule_float(row.get("match_pct"))
          return pct is not None and abs(pct) >= value
      return False
  ```

---

### 4. DEF-04: Blocking Synchronous Disk I/O inside Async Coroutine Loop (HIGH)

- **Location:** `server.py`, Lines 189–191
- **Observation:**
  ```python
  # server.py:172-195
  async def _alerts_poll_loop(poll_interval: int = 15):
      while True:
          try:
              ...
              for rule in pending:
                  row = by_symbol.get(rule["symbol"])
                  if row and _evaluate_rule(rule, row):
                      rule["fired"] = True
                      ...
                      _save_alert_rules() # SYNC BLOCKING DISK WRITE
          except Exception as e:
              print(f"[ALERTS] Poll error: {e}")
          await asyncio.sleep(poll_interval)
  ```
- **Root Cause:** `_save_alert_rules()` creates directories, writes to a temp file, and performs `os.replace` synchronously inside the asyncio event loop task.
- **Impact:** Stalls the main FastAPI event loop, increasing request latencies for all concurrent HTTP connections.
- **Recommended Fix:**
  Wrap the synchronous save in `asyncio.to_thread(_save_alert_rules)`.

---

### 5. DEF-05: Python 3.12+ Deprecation Warning on `datetime.utcnow()` (MEDIUM)

- **Location:** `server.py`, Lines 635, 709
- **Observation:**
  `_dt.utcnow().timestamp()` raises `DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version.`
- **Impact:** Pollution of standard server logs and potential failure on future Python releases.
- **Recommended Fix:**
  Use `_dt.now(timezone.utc).timestamp()`.

---

### 6. DEF-06: Per-Request ThreadPoolExecutor Churn (MEDIUM)

- **Location:** `server.py`, Line 682
- **Observation:**
  `with ThreadPoolExecutor(max_workers=11) as _pool:` instantiates and tears down an 11-worker thread pool on every request that misses the in-memory cache.
- **Impact:** Unnecessary thread creation and kernel context-switch overhead under high request concurrency.
- **Recommended Fix:**
  Reuse the global application `executor` from `services/stock_service.py`.

---

### 7. DEF-07: Hardcoded Local Path in Ingestion Sync Script (LOW)

- **Location:** `scripts/sync_unified_market_data.py`, Line 31
- **Observation:**
  `symbols_file = os.path.join(PROJECT_ROOT, "data", "all_symbols.json")`
- **Impact:** Bypasses Google Drive Data Lake resolution (`resolve_data_file("all_symbols.json")`) when synced files reside on Google Drive.
- **Recommended Fix:**
  Use `resolve_data_file("all_symbols.json")`.

---

## Acceptance Criteria Verification Matrix

| Acceptance Item | Status | Verification Note |
|---|---|---|
| 22 Valuation Models Execution | **PASS (with Fix DEF-02)** | All models calculate finite positive values; `DEF-02` prevents `NoneType` crashes on incomplete statements. |
| IVW & Multi-Algo Error Weighting | **PASS** | Validated mathematically across SMAPE, MALE, WMAPE, RMSLE, and IVW. |
| 3-Mode Backtesting System | **PASS** | Mode 1 (Valuation Only), Mode 2 (Screening Only), Mode 3 (2-Stage Hybrid Funnel) operate deterministically without lookahead bias. |
| Risk Firewalls & Anti-Trap Diagnostics | **PASS** | Altman Z'' + Beneish M-Score 4-Quadrant matrix and Rhodes-Kropf decomposition compute reliably. |
| Data Lake Resilience & Dual-Mode Fallback | **PASS (with Fix DEF-01, DEF-07)** | `resolve_data_file()` smoothly prioritizes richer datasets between Google Drive and local cache. |

---

## Proposed Patch Summary

```diff
--- a/server.py
+++ b/server.py
@@ -160,13 +160,24 @@ def _is_market_hours() -> bool:
+def _safe_rule_float(val: Any) -> Optional[float]:
+    if val is None:
+        return None
+    try:
+        f = float(val)
+        return None if (math.isnan(f) or math.isinf(f)) else f
+    except (ValueError, TypeError):
+        return None
+
 def _evaluate_rule(rule: dict, row: dict) -> bool:
     cond = rule.get("condition")
-    value = float(rule.get("value") or 0)
+    value = _safe_rule_float(rule.get("value")) or 0.0
+    p = _safe_rule_float(row.get("match_p"))
     if cond == "price_above":
-        return row.get("match_p") is not None and float(row["match_p"]) >= value
+        return p is not None and p >= value
     if cond == "price_below":
-        return row.get("match_p") is not None and float(row["match_p"]) <= value
+        return p is not None and p <= value
     if cond == "pct_change":
-        pct = row.get("match_pct")
-        return pct is not None and abs(float(pct)) >= value
+        pct = _safe_rule_float(row.get("match_pct"))
+        return pct is not None and abs(pct) >= value
     return False
@@ -189,3 +200,3 @@
-                        _save_alert_rules()
+                        await asyncio.to_thread(_save_alert_rules)
@@ -629,3 +640,3 @@
-            if _os.path.exists(_disk_path):
+            if os.path.exists(_disk_path):
                 with open(_disk_path, "r", encoding="utf-8") as _f:
                     _disk = _json.load(_f)
```
