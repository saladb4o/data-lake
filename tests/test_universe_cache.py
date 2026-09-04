"""
M5 universe-cache hardening tests (offline only).

Covers:
  A. compute_quant_percentile_universe no longer fabricates a synthetic
     universe on sync failure: it raises RuntimeError (chained cause) and
     leaves the cache unpopulated, UNLESS a fresh schema-valid snapshot
     exists on disk.
  B. Cache key bumped to v2; old-schema snapshots (missing per-stock
     _metadata.is_imputed) and over-age snapshots are treated as stale.
  C. TLS honesty: _request_with_retry verifies certificates by default;
     VNSTOCK_INSECURE_TLS=1 at import flips to insecure mode.
  D. Snapshot writes are atomic (.tmp + os.replace): a crash mid-dump
     cannot corrupt the published file.

No network access anywhere in this module.
"""

import json
import logging
import os
import sys
import subprocess
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from services import unified_data_service as uds
from services import stock_service as ss

CACHE_KEY = "quant_percentile_universe_v2"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_snapshot_payload(n_stocks: int = 60, with_schema: bool = True) -> dict:
    """A snapshot carrying the v2 schema markers (>50 stocks required)."""
    stocks = {}
    for i in range(n_stocks):
        s = {
            "symbol": f"TS{i:03d}",
            "pe": round(8.0 + i * 0.31, 2),
            "percentiles": {"composite": float(i % 100)},
            "matching_strategies": [],
        }
        if with_schema:
            s["_metadata"] = {"is_imputed": False, "provenance_tier": "Tier 3 (Reported)"}
        stocks[f"TS{i:03d}"] = s
    return {
        "updated_at": "test-fixture",
        "total_symbols": n_stocks,
        "sectors": {},
        "stocks": stocks,
    }


def write_json(path, payload) -> None:
    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(payload, f)


@pytest.fixture()
def quant_env(monkeypatch, tmp_path):
    """
    Isolated environment for compute_quant_percentile_universe:
    - snapshot path redirected to tmp
    - master universe pre-populated (no load_master_universe network call)
    - in-memory cache saved/restored around each test
    """
    snap_path = tmp_path / "screener_snapshot.json"
    monkeypatch.setattr(ss, "QUANT_SNAPSHOT_FILE", str(snap_path))
    monkeypatch.setattr(
        ss,
        "ALL_SYMBOLS_MAP",
        {"FPT": {"exchange": "HOSE", "type": "STOCK", "ref": 120000.0}},
    )
    yield SimpleNamespace(snap_path=snap_path)
    ss.cache._store.clear()


def failing_sync(master):
    raise ConnectionError("simulated transient outage")


def ok_sync(master):
    return {"stocks": {}, "total_symbols": 0, "sectors": {}, "source": "fake"}


# ---------------------------------------------------------------------------
# FIX A/B: failure semantics + cache invalidation
# ---------------------------------------------------------------------------

def test_sync_failure_no_snapshot_raises_and_cache_not_populated(quant_env, monkeypatch):
    assert not quant_env.snap_path.exists()
    monkeypatch.setattr(uds, "sync_unified_screener_universe", failing_sync)

    with pytest.raises(RuntimeError) as ei:
        ss.compute_quant_percentile_universe(force_recompute=True)

    # Clear chaining to the underlying outage.
    assert isinstance(ei.value.__cause__, ConnectionError)
    # No fabricated payload was persisted under the API's cache key...
    assert ss.cache.get(CACHE_KEY) is None
    # ...and nothing was written to the snapshot location either.
    assert not quant_env.snap_path.exists()


def test_sync_failure_with_fresh_valid_snapshot_serves_snapshot(quant_env, monkeypatch):
    payload = make_snapshot_payload()
    write_json(quant_env.snap_path, payload)
    monkeypatch.setattr(uds, "sync_unified_screener_universe", failing_sync)

    result = ss.compute_quant_percentile_universe(force_recompute=True)

    # Real-but-stale on-disk data is served instead of raising/fabricating.
    assert result["total_symbols"] == 60
    meta = result["stocks"]["TS000"]["_metadata"]
    assert meta["is_imputed"] is False
    # And the served snapshot is what the cache now holds.
    assert ss.cache.get(CACHE_KEY) is result


def test_fresh_snapshot_served_without_sync(quant_env, monkeypatch):
    write_json(quant_env.snap_path, make_snapshot_payload())

    def must_not_run(master):
        raise AssertionError("sync must not be called when a fresh valid snapshot exists")

    monkeypatch.setattr(uds, "sync_unified_screener_universe", must_not_run)
    result = ss.compute_quant_percentile_universe(force_recompute=False)
    assert result["stocks"]["TS059"]["_metadata"]["is_imputed"] is False


def test_schema_old_snapshot_treated_as_stale_and_raises(quant_env, monkeypatch):
    # Old payloads lack per-stock _metadata.is_imputed -> never served.
    write_json(quant_env.snap_path, make_snapshot_payload(with_schema=False))
    monkeypatch.setattr(uds, "sync_unified_screener_universe", failing_sync)

    with pytest.raises(RuntimeError):
        ss.compute_quant_percentile_universe(force_recompute=True)
    assert ss.cache.get(CACHE_KEY) is None


def test_overage_snapshot_treated_as_stale_and_raises(quant_env, monkeypatch):
    write_json(quant_env.snap_path, make_snapshot_payload())
    monkeypatch.setattr(uds, "sync_unified_screener_universe", failing_sync)

    with pytest.raises(RuntimeError):
        ss.compute_quant_percentile_universe(force_recompute=True, max_age_hours=0.0)
    assert ss.cache.get(CACHE_KEY) is None


# ---------------------------------------------------------------------------
# FIX B: cache key versioning
# ---------------------------------------------------------------------------

def test_cache_key_is_v2_and_success_populates_cache(quant_env, monkeypatch):
    monkeypatch.setattr(uds, "sync_unified_screener_universe", ok_sync)

    result = ss.compute_quant_percentile_universe(force_recompute=True)

    assert CACHE_KEY in ss.cache._store
    assert ss.cache.get(CACHE_KEY) is result

    # Second call hits the cache (same object identity), no re-sync needed.
    calls = {"n": 0}

    def counting_sync(master):
        calls["n"] += 1
        return ok_sync(master)

    monkeypatch.setattr(uds, "sync_unified_screener_universe", counting_sync)
    again = ss.compute_quant_percentile_universe(force_recompute=False)
    assert again is result
    assert calls["n"] == 0


def test_no_v1_cache_key_remains_in_source():
    import inspect
    src = inspect.getsource(ss.compute_quant_percentile_universe)
    assert "quant_percentile_universe_v1" not in src
    assert CACHE_KEY in src


# ---------------------------------------------------------------------------
# FIX 2: snapshot rejection logging + extended schema gate
# ---------------------------------------------------------------------------

def test_corrupt_snapshot_rejected_with_logged_reason(quant_env, caplog):
    quant_env.snap_path.write_text('{"stocks": {"AAA": {"pe": 10}}', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="services.stock_service"):
        assert ss._load_quant_snapshot_if_valid(max_age_hours=25.0) is None
    assert any("corrupt" in rec.message.lower() for rec in caplog.records)


def test_stale_snapshot_rejected_with_logged_reason(quant_env, caplog):
    write_json(quant_env.snap_path, make_snapshot_payload())
    with caplog.at_level(logging.WARNING, logger="services.stock_service"):
        assert ss._load_quant_snapshot_if_valid(max_age_hours=0.0) is None
    assert any("stale" in rec.message.lower() for rec in caplog.records)


def test_snapshot_missing_composite_rejected_as_old_schema(quant_env, caplog):
    payload = make_snapshot_payload(n_stocks=60)
    # Strip percentiles from exactly one stock -> whole snapshot must be refused.
    del payload["stocks"]["TS007"]["percentiles"]
    write_json(quant_env.snap_path, payload)
    with caplog.at_level(logging.WARNING, logger="services.stock_service"):
        snap = ss._load_quant_snapshot_if_valid(max_age_hours=25.0)
    assert snap is None
    assert any("percentiles.composite" in rec.message for rec in caplog.records)
    assert any("old schema" in rec.message.lower() for rec in caplog.records)


@pytest.mark.parametrize("bad_composite", [None, "73", True])
def test_snapshot_non_numeric_composite_rejected(quant_env, bad_composite):
    payload = make_snapshot_payload(n_stocks=60)
    payload["stocks"]["TS003"]["percentiles"]["composite"] = bad_composite
    write_json(quant_env.snap_path, payload)
    assert ss._load_quant_snapshot_if_valid(max_age_hours=25.0) is None


def test_snapshot_valid_schema_with_composite_served(quant_env):
    write_json(quant_env.snap_path, make_snapshot_payload())
    snap = ss._load_quant_snapshot_if_valid(max_age_hours=25.0)
    assert snap is not None
    comp = snap["stocks"]["TS000"]["percentiles"]["composite"]
    assert isinstance(comp, float)


# ---------------------------------------------------------------------------
# FIX 3: SimpleCache.invalidate (no private poking at call sites)
# ---------------------------------------------------------------------------

def test_simple_cache_invalidate_drops_entry_and_is_noop_on_missing():
    c = ss.SimpleCache()
    c.set("k", {"v": 1}, ttl_seconds=60)
    assert c.get("k") == {"v": 1}
    c.invalidate("k")
    assert c.get("k") is None
    # Invalidating an absent key must not raise.
    c.invalidate("never-existed")


def test_orchestrator_uses_invalidate_not_private_store_pop():
    import inspect
    src = inspect.getsource(ss.compute_quant_percentile_universe)
    assert "_store.pop" not in src
    assert "cache.invalidate(cache_key)" in src


# ---------------------------------------------------------------------------
# FIX 1: TLS honesty — no process-wide monkeypatching of requests.Session
# ---------------------------------------------------------------------------

def test_fresh_session_verifies_by_default_after_importing_services():
    # Subprocess probe: importing both services in a clean env (without
    # VNSTOCK_INSECURE_TLS) must NOT globally force verify=False.
    env = {k: v for k, v in os.environ.items() if k != "VNSTOCK_INSECURE_TLS"}
    env["VNSTOCK_INSECURE_TLS"] = ""
    env["PYTHONPATH"] = PROJECT_ROOT
    proc = subprocess.run(
        [sys.executable, "-c",
         "import requests\n"
         "import services.stock_service\n"
         "import services.unified_data_service\n"
         "s = requests.Session()\n"
         "print('VERIFY:', s.verify)\n"
         "print('INIT:', requests.Session.__init__.__name__)"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=PROJECT_ROOT, env=env, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    lines = {l.split(":")[0].strip(): l.split(":", 1)[1].strip()
             for l in proc.stdout.splitlines() if ":" in l}
    assert lines.get("VERIFY") == "True", (
        "A fresh requests.Session must verify certificates by default "
        "when VNSTOCK_INSECURE_TLS is not set"
    )
    assert lines.get("INIT") != "_safe_session_init"


# ---------------------------------------------------------------------------
# FIX C: TLS honesty
# ---------------------------------------------------------------------------

class _FakeResponse:
    status_code = 200


def test_tls_verify_true_by_default(monkeypatch):
    captured = {}

    def fake_request(method, url, timeout=None, **kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(uds._HTTP_SESSION, "request", fake_request)
    # Override TLS_VERIFY in the unified_data_service module scope so that
    # _request_with_retry uses verify=True regardless of the .env setting.
    monkeypatch.setattr(uds, "TLS_VERIFY", True)
    resp = uds._request_with_retry("GET", "https://example.invalid/quote")
    assert resp is not None
    assert resp.status_code == 200
    assert captured.get("verify") is True, (
        "_request_with_retry must verify TLS certificates by default"
    )


def _run_tls_probe(env_extra: dict) -> bool:
    env = {k: v for k, v in os.environ.items() if k != "VNSTOCK_INSECURE_TLS"}
    # Explicitly set to empty so load_dotenv(override=False) in tls_config.py
    # won't re-inject the .env file's VNSTOCK_INSECURE_TLS=1 value.
    env["VNSTOCK_INSECURE_TLS"] = ""
    env.update(env_extra)
    env["PYTHONPATH"] = PROJECT_ROOT
    proc = subprocess.run(
        [sys.executable, "-c",
         "import services.unified_data_service as u; print('TLSVERIFY:', u.TLS_VERIFY)"],
        capture_output=True, text=True, cwd=PROJECT_ROOT, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(l for l in proc.stdout.splitlines() if l.startswith("TLSVERIFY:"))
    return line.split(":")[1].strip() == "True"


def test_tls_default_true_and_insecure_env_flips_false():
    assert _run_tls_probe({}) is True, "TLS verification must default to ON"
    assert _run_tls_probe({"VNSTOCK_INSECURE_TLS": "1"}) is False, (
        "VNSTOCK_INSECURE_TLS=1 must opt out of certificate verification"
    )
    assert _run_tls_probe({"VNSTOCK_INSECURE_TLS": "0"}) is True, (
        "any value other than '1' keeps verification ON"
    )


def _run_session_verify_probe(env_extra: dict) -> bool:
    """Subprocess: import BOTH services, then check a FRESH requests.Session."""
    env = {k: v for k, v in os.environ.items() if k != "VNSTOCK_INSECURE_TLS"}
    # Explicitly set to empty so load_dotenv(override=False) in tls_config.py
    # won't re-inject the .env file's VNSTOCK_INSECURE_TLS=1 value.
    env["VNSTOCK_INSECURE_TLS"] = ""
    env.update(env_extra)
    env["PYTHONPATH"] = PROJECT_ROOT
    proc = subprocess.run(
        [sys.executable, "-c",
         "import requests\n"
         "import services.stock_service\n"
         "import services.unified_data_service\n"
         "print('SESSIONVERIFY:', requests.Session().verify)"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=PROJECT_ROOT, env=env, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(l for l in proc.stdout.splitlines() if l.startswith("SESSIONVERIFY:"))
    return line.split(":")[1].strip() == "True"


def test_fresh_session_verify_default_on_and_env_flips_off():
    assert _run_session_verify_probe({}) is True, (
        "a fresh requests.Session must verify certificates by default after "
        "importing both services (no process-wide monkeypatch)"
    )
    assert _run_session_verify_probe({"VNSTOCK_INSECURE_TLS": "1"}) is False, (
        "VNSTOCK_INSECURE_TLS=1 at import must flip fresh-session verify off"
    )


# ---------------------------------------------------------------------------
# FIX D: atomic snapshot write
# ---------------------------------------------------------------------------

MASTER_MINIMAL = {
    "AAA": {"exchange": "HOSE", "sector_code": "VNIND", "sector_name": "Công Nghiệp",
            "name": "Test A Corp"},
}


@pytest.fixture()
def offline_sync_env(monkeypatch):
    monkeypatch.setattr(
        uds, "fetch_tradingview_batch_by_tickers", lambda tickers, chunk_size=150: {}
    )
    monkeypatch.setattr(uds, "fetch_vnstock_financials", lambda symbol: {})
    monkeypatch.setattr(uds, "fetch_yfinance_financials", lambda symbol: {})


class _JsonShim:
    """Proxies json but makes dump explode mid-write."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def dump(self, *args, **kwargs):
        raise OSError("simulated crash mid-write")


def test_atomic_write_target_preserved_when_dump_crashes(
    monkeypatch, tmp_path, offline_sync_env
):
    target = tmp_path / "screener_snapshot.json"
    target.write_text('{"sentinel": true}', encoding="utf-8")
    monkeypatch.setattr(uds, "SCREENER_SNAPSHOT_FILE", str(target))
    monkeypatch.setattr(uds, "json", _JsonShim(json))

    with pytest.raises(OSError):
        uds.sync_unified_screener_universe(dict(MASTER_MINIMAL))

    # Original target content untouched; partial dump isolated in .tmp.
    assert target.read_text(encoding="utf-8") == '{"sentinel": true}'


def test_atomic_write_publishes_via_replace(monkeypatch, tmp_path, offline_sync_env):
    target = tmp_path / "screener_snapshot.json"
    monkeypatch.setattr(uds, "SCREENER_SNAPSHOT_FILE", str(target))

    uds.sync_unified_screener_universe(dict(MASTER_MINIMAL))

    # Successful sync publishes atomically: target exists, .tmp cleaned up.
    assert target.exists()
    assert not os.path.exists(str(target) + ".tmp")
    with open(str(target), encoding="utf-8") as f:
        snap = json.load(f)
    assert set(snap["stocks"]) == set(MASTER_MINIMAL)
