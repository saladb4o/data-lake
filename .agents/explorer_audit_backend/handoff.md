# Handoff Report — Backend Services & API Audit

## 1. Observation

Direct code analysis of `server.py`, `services/`, `scripts/`, and `tests/` revealed the following specific defects:

1. **`server.py:629`** — `_os.path.exists(_disk_path)`:
   - Line content: `if _os.path.exists(_disk_path):`
   - Observation: Module-level import is `import os`. Local alias `_os` was never imported in `api_sectors_rrg`.
   - Result: Silent `NameError` caught by `except Exception: _disk = {}`, permanently disabling RRG Stale-While-Revalidate disk cache loading on server startup.
2. **`services/valuation_engine.py:2122-2149`** — `dict.get("key", default)` with explicit `None` values:
   - Line content: `rwa=fundamental_data.get("rwa", mcap * 1.2)`
   - Observation: If `fundamental_data["rwa"]` is explicitly `None`, `.get("rwa", ...)` returns `None`.
   - Result: In `model_17_bank_equity_cash_flow` line 1354, `max(rwa, book_equity / target_car)` executes `max(None, float)`, triggering an unhandled `TypeError`.
3. **`server.py:160-170`** — Unsafe string-to-float conversions:
   - Line content: `float(row["match_p"])` and `float(row["match_pct"])`
   - Observation: Price feeds returning non-numeric strings (`"-"`, `"N/A"`) raise `ValueError`.
   - Result: Background task `_alerts_poll_loop` crashes on rule evaluation during market hours.
4. **`server.py:189`** — Blocking synchronous disk I/O in async task:
   - Line content: `_save_alert_rules()`
   - Observation: Atomic file writing (`json.dump` and `os.replace`) runs on the single-threaded asyncio event loop.
   - Result: Latency spikes for concurrent client connections.
5. **`server.py:635, 709`** — Deprecated `datetime.datetime.utcnow()`:
   - Observation: `_dt.utcnow().timestamp()` emits `DeprecationWarning` under Python 3.12+.
6. **`server.py:682`** — Dynamic `ThreadPoolExecutor` churn:
   - Observation: Spawns up to 11 threads per request rather than reusing the application-wide threadpool `executor`.

---

## 2. Logic Chain

1. **RRG Cache Invalidation Logic:**
   - On server start or after TTL expiration, `api_sectors_rrg()` checks `_rrg_disk_path()`.
   - Line 629 attempts `_os.path.exists(...)`.
   - Python raises `NameError: name '_os' is not defined`.
   - The outer `except Exception:` catches `NameError` and initializes `_disk = {}`.
   - Therefore, disk cache is never restored, causing unnecessary upstream recalculations.
2. **Valuation Engine Null Safety:**
   - Upstream JSON payloads from data lake crawlers (`screener_snapshot.json`) often contain `null` for uncalculated metrics (`rwa: null`, `capex: null`).
   - `dict.get("rwa", fallback)` returns `None` (not `fallback`) because the key exists with value `None`.
   - Passing `None` to `model_17_bank_equity_cash_flow` causes `max(rwa, ...)` to raise `TypeError`.
   - Therefore, defensive cleaning with `(fundamental_data.get(...) or fallback)` is required for all model parameters.
3. **Async Event Loop Health:**
   - In FastAPI, coroutines (`async def`) execute cooperatively on the main thread.
   - Calling synchronous disk I/O in `_alerts_poll_loop()` halts the event loop until the OS disk write finishes.
   - Using `asyncio.to_thread(_save_alert_rules)` offloads the write to the default threadpool, ensuring zero event loop blocking.

---

## 3. Caveats

- Live network external scraping feeds (e.g. Vietcap, TCBS, World Bank API) are subject to third-party upstream availability and IP rate limiting; mock fallbacks and local cache layers are active when offline.
- No production source code files outside `.agents/` were directly modified during this read-only exploratory audit.

---

## 4. Conclusion

The backend codebase is structurally complete with institutional quant capabilities. The 6 identified defects (`DEF-01` to `DEF-06`) can be addressed through localized code hardening in `server.py` and `services/valuation_engine.py` without breaking any existing API contracts or data lake schemas.

---

## 5. Verification Method

To independently verify the defects and validate subsequent fixes:

1. **Verify DEF-01 (RRG `_os` NameError):**
   ```python
   # Run in Python REPL:
   from server import api_sectors_rrg
   resp = api_sectors_rrg(benchmark="VNINDEX", interval="1W", tail=8, method="jdk")
   assert resp.status_code == 200
   ```
2. **Verify DEF-02 (Valuation Engine `None` Handling):**
   ```python
   # Run with explicit None fields:
   from services.valuation_engine import ValuationEngine
   engine = ValuationEngine()
   res = engine.get_comprehensive_valuation("TEST", fundamental_data={"symbol": "TEST", "rwa": None, "capex": None, "price": 25000})
   assert res.composite_fair_value > 0
   ```
3. **Execute Full Test Suite:**
   ```bash
   pytest tests/test_valuation_engine.py tests/test_fair_value_backtest.py tests/test_institutional_valuation_integration.py -v
   ```
