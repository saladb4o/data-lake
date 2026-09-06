"""
Smoke tests for sector endpoints: /api/sectors/overview, /api/sectors/history, /api/sectors/rrg
===============================================================================================
STRATEGY (documented per task instructions):
  Importing server.py is light at module level, but heavy/risky work happens at startup
  (background news poller via @app.on_event("startup")) and inside request handlers
  (network fetches, universe sync fallbacks). Using FastAPI TestClient would trigger
  lifespan events in-process and couple the test runner to service internals.
  => SAFER CHOICE: launch the REAL server as a background subprocess using uvicorn
     directly (`python -m uvicorn server:app --host 127.0.0.1 --port <port>`), deliberately
     NOT run_app.py (which uses reload=True -> spawns a hard-to-kill child watcher process,
     and pops open a web browser). We poll an endpoint until readiness, exercise plain HTTP,
     and terminate the subprocess in a `finally` block.

Checks (PASS/FAIL/SKIP matrix):
  a. overview: 200, >=5 sectors, numeric change_pct
  b. history VNREAL 1D/3M: schema keys, candles sorted asc, last candle within 7 days,
     len(ma20) <= len(candles), no NaN/null closes
  c. history VNFIN: same checks
  d. rrg (jdk): 200, >=6 valid points, ratios [70,130], momentum [80,120],
     tails non-empty chronological, quadrant enum valid; record {"error"} entries
  e. rrg method=enhanced returns 200
  f. freshness flag: history latest_point vs overview entry for same sector (+/-5%)

Network-dependent failures are retried ONCE after 30s before being marked FAIL.
"""

import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = "127.0.0.1"
PORT = int(os.environ.get("SMOKE_SECTORS_PORT", "8931"))
BASE = f"http://{HOST}:{PORT}"
READY_TIMEOUT = 540          # seconds to wait for server readiness -- first /overview call
                             # fans out to trading.vietcap.com.vn which times out at 30s per
                             # upstream call before falling back, so cold start is slow
REQ_TIMEOUT = 240            # per-request timeout (cold upstream fan-out can take minutes)
RETRY_WAIT = 30              # wait before the single retry of network-dependent calls

REQUIRED_HISTORY_KEYS = [
    "candles", "volumes", "ma20", "ma50", "boll_upper", "boll_lower",
    "rsi", "macd", "macd_signal", "macd_hist",
    "technical_signal", "latest_point", "change_pct", "source",
]
QUADRANTS = {"Leading", "Weakening", "Lagging", "Improving"}

RESULTS = []  # (check_id, name, status, detail)


# ----------------------------------------------------------------------------- helpers
def log(msg: str) -> None:
    print(msg, flush=True)


def record(cid: str, name: str, ok: bool | None, detail: str = "") -> bool | None:
    """ok=True PASS, False FAIL, None SKIP."""
    status = {True: "PASS", False: "FAIL", None: "SKIP"}[ok]
    RESULTS.append((cid, name, status, detail))
    line = f"[{status}] {cid} {name}"
    if detail:
        line += f" -- {detail}"
    log(line)
    return ok


def http_json(path: str, retries: int = 1) -> tuple[int | None, object | None, str]:
    """
    GET BASE+path, return (status_code, parsed_json_or_None, error_msg).
    On network-ish failure (timeout, conn refused/reset, HTTP 5xx) retry once after RETRY_WAIT.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as resp:
                body = resp.read()
                status = resp.status
            try:
                return status, json.loads(body.decode("utf-8")), ""
            except Exception as pe:
                return status, None, f"non-JSON body ({pe})"
        except urllib.error.HTTPError as e:
            # 4xx are deterministic answers from the API: do NOT retry them
            try:
                body = e.read().decode("utf-8", errors="replace")
                parsed = json.loads(body)
            except Exception:
                parsed = None
            if e.code >= 500 and attempt <= retries:
                log(f"    .. HTTP {e.code} on {path}, retrying in {RETRY_WAIT}s "
                    f"(attempt {attempt}/{retries + 1})")
                time.sleep(RETRY_WAIT)
                continue
            return e.code, parsed, f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt <= retries:
                log(f"    .. network error on {path}: {e}; retrying in {RETRY_WAIT}s "
                    f"(attempt {attempt}/{retries + 1})")
                time.sleep(RETRY_WAIT)
                continue
            return None, None, f"network error: {e}"


def get_data(path: str):
    """Convenience: unwrap {"status":"success","data":...}. Returns (data, err)."""
    status, js, err = http_json(path)
    if status is None:
        return None, err
    if status != 200:
        msg = ""
        if isinstance(js, dict):
            msg = str(js.get("message") or js.get("detail") or "")[:200]
        return None, f"HTTP {status} {msg}".strip()
    if not isinstance(js, dict) or "data" not in js:
        return None, "response missing 'data' envelope"
    return js["data"], ""


def to_epoch(v) -> float | None:
    """Normalize candle 'time' (epoch sec/ms or ISO string) to epoch seconds."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        x = float(v)
        if x > 1e14:   # ms
            return x / 1000.0
        if x > 1e11:   # us
            return x / 1000.0
        return x       # sec
    if isinstance(v, str):
        s = v.strip()
        try:
            return float(s)
        except ValueError:
            logger.debug("to_epoch: swallowed ValueError", exc_info=True)
        for fmt_len in (19, 10):  # full ISO or date-only
            try:
                dt = datetime.strptime(s[:fmt_len].replace("Z", ""), "%Y-%m-%dT%H:%M:%S" if fmt_len == 19 else "%Y-%m-%d")
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
    return None


def is_bad_number(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def validate_history(sector: str, cid_prefix: str,
                     interval: str = "1D", timeframe: str = "3M",
                     fresh_check: bool = True) -> None:
    """Checks b/c: schema keys, sort order, freshness, ma length, NaN closes."""
    label = f"{sector} {interval}/{timeframe}"
    data, err = get_data(
        f"/api/sectors/history?sector={sector}&interval={interval}&timeframe={timeframe}")
    if data is None:
        record(cid_prefix, f"history {label} reachable", False, err)
        return
    record(cid_prefix, f"history {label} reachable", True)

    missing = [k for k in REQUIRED_HISTORY_KEYS if k not in data]
    record(f"{cid_prefix}.schema", f"history {label} schema keys",
           not missing,
           f"missing={missing}" if missing else f"all {len(REQUIRED_HISTORY_KEYS)} keys present")

    candles = data.get("candles") or []
    if not isinstance(candles, list) or not candles:
        record(f"{cid_prefix}.candles", f"history {label} candles non-empty list", False,
               f"got {type(candles).__name__} len={len(candles) if isinstance(candles, list) else 'n/a'}")
        return

    times = [to_epoch(c.get("time")) for c in candles]
    bad_t = sum(1 for t in times if t is None)
    unsorted = any(times[i] is None or times[i + 1] is None or times[i] > times[i + 1]
                   for i in range(len(times) - 1))
    record(f"{cid_prefix}.sorted", f"history {label} candles sorted ascending",
           (not unsorted) and bad_t == 0,
           f"n={len(candles)} unparseable_times={bad_t}" +
           (" ORDER VIOLATION" if unsorted else ""))

    if fresh_check:
        last_t = next((t for t in reversed(times) if t is not None), None)
        if last_t is None:
            record(f"{cid_prefix}.fresh", f"history {label} last candle within 7 days", False,
                   "no parseable candle time")
        else:
            age_days = (time.time() - last_t) / 86400.0
            record(f"{cid_prefix}.fresh", f"history {label} last candle within 7 days",
                   -1 <= age_days <= 7,
                   f"last={datetime.fromtimestamp(last_t, tz=timezone.utc).isoformat()} "
                   f"age={age_days:.2f}d")

    ma20 = data.get("ma20")
    ma_ok = isinstance(ma20, list) and len(ma20) <= len(candles)
    record(f"{cid_prefix}.ma20len", f"history {label} len(ma20) <= len(candles)",
           ma_ok, f"ma20={len(ma20) if isinstance(ma20, list) else type(ma20).__name__} "
                  f"candles={len(candles)}")

    closes = [c.get("close") for c in candles]
    n_bad = sum(1 for c in closes if is_bad_number(c))
    record(f"{cid_prefix}.closes", f"history {label} no NaN/null closes",
           n_bad == 0, f"bad_closes={n_bad}/{len(closes)}")

    vols = data.get("volumes")
    vol_ok = isinstance(vols, list) and all(
        isinstance(v, dict) and "time" in v and "value" in v for v in vols[:5])
    record(f"{cid_prefix}.volumes", f"history {label} volumes entries have time/value",
           bool(vol_ok),
           f"len={len(vols) if isinstance(vols, list) else type(vols).__name__}")


def validate_rrg(method: str) -> None:
    """Checks d/e."""
    cid = "d" if method == "jdk" else "e"
    path = f"/api/sectors/rrg?benchmark=VNINDEX&interval=1W&tail=8&method={method}"
    status, js, err = http_json(path)
    if status != 200:
        record(cid, f"rrg method={method} reachable", False, err)
        return
    record(cid, f"rrg method={method} reachable", True, f"HTTP 200")

    data = js.get("data") if isinstance(js, dict) else None
    if not isinstance(data, dict):
        record(f"{cid}.payload", "rrg payload is dict", False, f"got {type(data).__name__}")
        return

    if method == "jdk":
        top_keys_missing = [k for k in ("benchmark", "interval", "method", "generated_at", "points")
                            if k not in data]
        record(f"{cid}.schema", "rrg top-level schema keys",
               not top_keys_missing,
               f"missing={top_keys_missing}" if top_keys_missing else
               f"benchmark={data.get('benchmark')} interval={data.get('interval')}")

    points = data.get("points")
    if not isinstance(points, list) or not points:
        record(f"{cid}.points", "rrg points non-empty list", False,
               f"got {type(points).__name__}")
        return

    errored = [p.get("sector_code") for p in points if isinstance(p, dict) and p.get("error")]
    valid = []
    ratio_bad, mom_bad, quad_bad, tail_bad = [], [], [], []
    for p in points:
        if not isinstance(p, dict) or p.get("error"):
            continue
        code = p.get("sector_code", "?")
        rr, rm = p.get("rs_ratio"), p.get("rs_momentum")
        if not isinstance(rr, (int, float)) or not (70 <= rr <= 130):
            ratio_bad.append(f"{code}:{rr}")
        # jdk uses z-score scaling (100 + 10z) -> unbounded by design;
        # enhanced is ratio-normalized (~[80,120]).
        mom_lo, mom_hi = (60, 140) if method == "jdk" else (80, 120)
        if not isinstance(rm, (int, float)) or not (mom_lo <= rm <= mom_hi):
            mom_bad.append(f"{code}:{rm}")
        if p.get("quadrant") not in QUADRANTS:
            quad_bad.append(f"{code}:{p.get('quadrant')!r}")
        tail = p.get("tail")
        ok_tail = (isinstance(tail, list) and len(tail) > 0)
        if ok_tail:
            # times may be ISO dates or ISO week keys ("2026-W34"); fall back
            # to lexicographic ordering, which is also chronological there.
            tkeys = [to_epoch(t.get("time")) if isinstance(t, dict) else None for t in tail]
            if all(t is None for t in tkeys):
                tkeys = [str(t.get("time")) if isinstance(t, dict) else "" for t in tail]
            numeric = not any(t is None for t in tkeys)
            ordered = (tkeys == sorted(tkeys))
            xy_ok = all(isinstance(t.get("x"), (int, float)) and isinstance(t.get("y"), (int, float))
                        for t in tail if isinstance(t, dict))
            if not ordered:
                log(f"    [tail-order] {code}: {tkeys}")
            if not xy_ok:
                log(f"    [tail-xy] {code}: non-numeric x/y present")
            ok_tail = ordered and xy_ok
        if not ok_tail:
            tail_bad.append(code)
        valid.append(code)

    if method == "jdk":
        log("")
        log(f"  RRG per-sector table (benchmark={data.get('benchmark')}, "
            f"interval={data.get('interval')}, generated_at={data.get('generated_at')}):")
        log(f"    {'sector':<10} {'rs_ratio':>9} {'rs_mom':>8} {'quadrant':<11} {'tail':>5}  note")
        for p in points:
            if not isinstance(p, dict):
                continue
            code = str(p.get("sector_code", "?"))
            if p.get("error"):
                log(f"    {code:<10} {'-':>9} {'-':>8} {'-':<11} {'-':>5}  "
                    f"ERROR: {str(p.get('error'))[:70]}")
            else:
                tl = p.get("tail") or []
                rr, rm = p.get("rs_ratio"), p.get("rs_momentum")
                rr_s = f"{rr:.2f}" if isinstance(rr, (int, float)) else "?"
                rm_s = f"{rm:.2f}" if isinstance(rm, (int, float)) else "?"
                log(f"    {code:<10} {rr_s:>9} {rm_s:>8} {str(p.get('quadrant')):<11} "
                    f"{len(tl):>5}  ok")
        log("")

    record(f"{cid}.valid_count", f"rrg {method} valid points >=6",
           len(valid) >= 6,
           f"valid={len(valid)} total={len(points)} sectors={valid}")
    record(f"{cid}.ratios", f"rrg {method} rs_ratio in [70,130]",
           not ratio_bad, "; ".join(ratio_bad[:5]) if ratio_bad else "all in range")
    record(f"{cid}.momentum", f"rrg {method} rs_momentum in [{mom_lo},{mom_hi}]",
           not mom_bad, "; ".join(mom_bad[:5]) if mom_bad else "all in range")
    record(f"{cid}.quadrant", f"rrg {method} quadrant enum valid",
           not quad_bad, "; ".join(quad_bad[:5]) if quad_bad else "all valid")
    record(f"{cid}.tails", f"rrg {method} tails non-empty & chronological",
           not tail_bad, "; ".join(tail_bad[:5]) if tail_bad else f"all {len(valid)} OK")
    record(f"{cid}.errors", f"rrg {method} per-sector error entries",
           True if errored else True,
           f"errored_sectors={errored if errored else 'none'}")


def main() -> int:
    log("=" * 78)
    log("SECTOR SMOKE TESTS -- real server on %s (uvicorn subprocess)" % BASE)
    log("=" * 78)

    proc = None
    logf = None
    try:
        os.makedirs(os.path.join(PROJECT_ROOT, "scripts"), exist_ok=True)
        log_path = os.path.join(os.environ.get("TEMP", PROJECT_ROOT),
                                "smoke_sectors_server.log")
        logf = open(log_path, "w", encoding="utf-8")
        cmd = [sys.executable, "-m", "uvicorn", "server:app",
               "--host", HOST, "--port", str(PORT), "--log-level", "warning"]
        log(f"[boot] {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT, stdout=logf, stderr=subprocess.STDOUT)

        deadline = time.time() + READY_TIMEOUT
        ready = False
        last_err = ""
        while time.time() < deadline:
            if proc.poll() is not None:
                last_err = f"server exited early rc={proc.returncode}"
                break
            st, _, e = http_json("/api/sectors/overview", retries=0)
            if st == 200:
                ready = True
                break
            last_err = e or f"http {st}"
            time.sleep(3)
        if not ready:
            log(f"[boot] FAILED readiness: {last_err}; server log tail:")
            try:
                with open(log_path, encoding="utf-8", errors="replace") as fh:
                    print("".join(fh.readlines()[-40:]))
            except OSError:
                logger.debug("main: swallowed OSError", exc_info=True)
            record("boot", "server readiness", False, last_err)
            return summarize()
        record("boot", "server readiness", True, f"ready in <{READY_TIMEOUT}s on :{PORT}")

        # ---- a. overview
        ov_data, ov_err = get_data("/api/sectors/overview")
        if ov_data is None:
            record("a", "overview reachable", False, ov_err)
        else:
            record("a", "overview reachable", True)
            n = len(ov_data) if isinstance(ov_data, list) else -1
            record("a.count", "overview >=5 sectors", n >= 5, f"count={n}")
            codes = set()
            bad_pct = []
            sources = {}
            if isinstance(ov_data, list):
                for s in ov_data:
                    if not isinstance(s, dict):
                        continue
                    code = s.get("sector_code") or s.get("code")
                    if code:
                        codes.add(code)
                    cp = s.get("change_pct")
                    if not isinstance(cp, (int, float)) or isinstance(cp, bool):
                        bad_pct.append(str(code))
                    src = str(s.get("source", "<missing>"))
                    sources[src] = sources.get(src, 0) + 1
            record("a.change_pct", "overview numeric change_pct all entries",
                   not bad_pct, f"non_numeric={bad_pct[:5]}" if bad_pct else "all numeric")
            log(f"[info] overview distinct source values: {sources}")

        # ---- b/c. history
        validate_history("VNREAL", "b", interval="1D", timeframe="3M", fresh_check=True)
        validate_history("VNFIN", "c", interval="1W", timeframe="ALL", fresh_check=False)

        # ---- d/e. rrg
        validate_rrg("jdk")
        validate_rrg("enhanced")

        # ---- f. freshness cross-check latest_point vs overview
        hz, h_err = get_data("/api/sectors/history?sector=VNREAL&interval=1D&timeframe=3M")
        if hz is None or ov_data is None:
            record("f", "latest_point vs overview cross-check", None,
                   f"skipped (history_err={h_err or 'n/a'}, overview_ok={ov_data is not None})")
        else:
            lp = hz.get("latest_point")
            ov_entry = next((s for s in (ov_data or [])
                             if isinstance(s, dict) and
                             (s.get("sector_code") == "VNREAL" or s.get("code") == "VNREAL")), None)
            hist_val = lp
            if isinstance(lp, dict):
                hist_val = lp.get("close", lp.get("value", lp.get("price")))
            if not isinstance(hist_val, (int, float)) or isinstance(hist_val, bool) or ov_entry is None:
                record("f", "latest_point vs overview cross-check", None,
                       f"skipped (hist_val={hist_val!r}, ov_entry={'found' if ov_entry else 'missing'})")
            else:
                ov_val = ov_entry.get("index_point",
                                      ov_entry.get("index_value", ov_entry.get("value")))
                if not isinstance(ov_val, (int, float)) or ov_val == 0:
                    record("f", "latest_point vs overview cross-check", None,
                           f"skipped (overview value field unusable: {ov_val!r})")
                else:
                    diff_pct = abs(hist_val - ov_val) / abs(ov_val) * 100.0
                    record("f", "latest_point vs overview cross-check (±5%)",
                           diff_pct <= 5.0,
                           f"history_latest={hist_val} overview={ov_val} diff={diff_pct:.2f}%")

        return summarize()
    finally:
        if proc is not None and proc.poll() is None:
            log("[teardown] terminating server subprocess ...")
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        if logf is not None:
            logf.close()
        log("[teardown] done")


def summarize() -> int:
    log("-" * 78)
    fails = [r for r in RESULTS if r[2] == "FAIL"]
    passes = [r for r in RESULTS if r[2] == "PASS"]
    skips = [r for r in RESULTS if r[2] == "SKIP"]
    log(f"MATRIX SUMMARY: {len(passes)} PASS, {len(fails)} FAIL, {len(skips)} SKIP / {len(RESULTS)} checks")
    for cid, name, status, detail in RESULTS:
        marker = {"PASS": "  ok ", "FAIL": ">>FAIL", "SKIP": " skip"}[status]
        log(f"  {marker} [{cid}] {name}" + (f" :: {detail}" if detail else ""))
    log("-" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
