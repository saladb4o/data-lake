## 2026-08-28T19:04:00Z
You are Worker (Backend Hardening & Test Suite Fixes - Milestone 1).
Your working directory is: c:/Users/Admin/Documents/Vibecoding vnstock/.agents/worker_backend_m1/
Project root: c:/Users/Admin/Documents/Vibecoding vnstock

MANDATORY FIRST STEP: Read the Authoritative User Request at:
c:/Users/Admin/Documents/Vibecoding vnstock/.agents/ORIGINAL_REQUEST.md
Also read:
- `c:/Users/Admin/Documents/Vibecoding vnstock/PROJECT.md`
- `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/explorer_audit_backend/analysis.md`
- `c:/Users/Admin/Documents/Vibecoding vnstock/.agents/explorer_audit_perf/analysis.md`

Tasks:
1. DEF-01: Fix undefined `_os` in `server.py:629` (use `os.path.exists(_disk_path)`).
2. DEF-02: Add null safety in `services/valuation_engine.py` using `(fundamental_data.get(...) or fallback)` for parameters like `rwa`, `capex`, etc., ensuring explicit `None` values don't cause TypeError in `max()` or math operations.
3. DEF-03: Safe float casting in `server.py:160-170` within `_evaluate_rule` with try-except for non-numeric market feed strings.
4. DEF-04: Offload synchronous `_save_alert_rules()` in `_alerts_poll_loop` using `await asyncio.to_thread(_save_alert_rules)`.
5. DEF-05: Replace deprecated `utcnow()` with `datetime.datetime.now(datetime.timezone.utc)` in `server.py`.
6. DEF-06: Reuse application-wide executor instead of per-request `ThreadPoolExecutor` churn in `server.py:682`.
7. PERF-01: Create `pytest.ini` with:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
```
8. PERF-02: Export `QUANT_SNAPSHOT_FILE = resolve_data_file("screener_snapshot.json")` in `services/stock_service.py` and ensure `_load_quant_snapshot_if_valid` uses it.
9. PERF-03: In `services/sector_index_service.py:_load_json()`, check if `_DATA_DIR` is set to a custom directory and load from it before falling back to `resolve_data_file()`.
10. PERF-04: In `tests/test_tls_ssl_context.py`, ensure test cases isolate or override `_INSECURE_TLS` so that unit tests verifying default strict TLS verification pass reliably.
11. PERF-05: In `server.py`, add in-memory TTL caching (e.g. 300s cache) for `/api/data-lake-status` to eliminate repeated multi-MB disk reads.
