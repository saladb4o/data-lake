"""
Benchmark index history service (VNINDEX, VN30, HNXINDEX, UPCOM).
Fetches real OHLCV via vnstock Quote.history (VCI preferred, TCBS fallback),
normalizes into strict candle/volume shapes, and caches results in-process.
Graceful failure: never raises; returns empty candles + "error" field instead.
"""

import os
import sys
import time
import json
import math
import logging
import datetime
import subprocess
from typing import Dict, Any, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from services.tls_config import tls_verify, configure_urllib_warnings
    configure_urllib_warnings()
except Exception:
    pass

# Import vnstock safely
try:
    from vnstock import Quote
    from vnstock.core import setup_api_key

    # Env-only; see services/stock_service.py for the rationale.
    api_key = os.environ.get("VNSTOCK_API_KEY", "").strip()
    if api_key:
        try:
            setup_api_key(api_key)
        except Exception:
            pass
except Exception:
    Quote = None


class _SimpleCache:
    def __init__(self):
        self._store = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            data, expire_at = self._store[key]
            if time.time() < expire_at:
                return data
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 60):
        self._store[key] = (value, time.time() + ttl_seconds)


_cache = _SimpleCache()

SUPPORTED_BENCHMARKS = ["VNINDEX", "VN30", "HNXINDEX", "UPCOM"]

# Per-source ticker aliases (some feeds use different index codes)
_SOURCE_SYMBOL_MAP = {
    src: {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNXINDEX", "UPCOM": "UPCOM"}
    for src in ("VCI", "TCBS", "KBS")
}

_INTERVAL_MAP = {"1D": "1D", "1W": "1W", "1M": "1M"}

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TV_BENCH_MAP = {
    "VNINDEX": "HOSE:VNINDEX",
    "VN30": "HOSE:VN30",
    "HNXINDEX": "HNX:HNXINDEX",
    "UPCOM": "UPCOM:UPCOMINDEX",
}

_TV_NODE_SCRIPT = (
    "const m=require(require('path').resolve(process.argv[1]));"
    "m.getTradingViewCandles(process.argv[2],Number(process.argv[3])||1200)"
    ".then(c=>process.stdout.write(JSON.stringify(c)))"
    ".catch(e=>{process.stderr.write(String(e));process.exit(1)});"
)
_TV_FETCHER_PATH = os.path.join(_BASE_DIR, "scripts", "fetch_tradingview.js")
_TV_FETCH_TIMEOUT = 20.0
_TV_CACHE_TTL = 300


def _tv_fetch_candles(symbol: str, max_count: int = 1200) -> Optional[List[Dict[str, Any]]]:
    cache_key = f"tv:{symbol}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    if not os.path.exists(_TV_FETCHER_PATH):
        logger.debug("TradingView fetcher script missing: %s", _TV_FETCHER_PATH)
        return None

    cmd = ["node", "-e", _TV_NODE_SCRIPT, _TV_FETCHER_PATH, symbol, str(max_count)]
    run_kwargs = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TV_FETCH_TIMEOUT,
            **run_kwargs,
        )
    except FileNotFoundError:
        logger.info("node executable not found; TradingView fast path unavailable for %s", symbol)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("TradingView fetch timed out after %.0fs for %s", _TV_FETCH_TIMEOUT, symbol)
        return None
    except Exception as exc:
        logger.debug("TradingView fetch failed for %s: %s", symbol, exc)
        return None

    if proc.returncode != 0:
        logger.debug(
            "TradingView fetcher exit %s for %s: %s",
            proc.returncode, symbol, (proc.stderr or "")[:200],
        )
        return None

    try:
        raw = json.loads(proc.stdout)
    except ValueError:
        logger.debug("TradingView fetcher returned malformed JSON for %s", symbol)
        return None
    if not isinstance(raw, list) or len(raw) < 10:
        return None

    candles: List[Dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            return None
        t = str(row.get("time") or "")[:10]
        try:
            o = float(row.get("open"))
            h = float(row.get("high"))
            lo = float(row.get("low"))
            c = float(row.get("close"))
            v_raw = row.get("volume")
            v = 0.0 if v_raw is None else float(v_raw)
        except (TypeError, ValueError):
            return None
        vals = (o, h, lo, c, v)
        if not all(math.isfinite(x) for x in vals) or c <= 0 or min(o, h, lo) <= 0:
            return None
        candles.append({"time": t, "open": o, "high": h, "low": lo, "close": c, "volume": v})

    candles.sort(key=lambda x: x["time"])
    times = [c["time"] for c in candles]
    if len(times) < 10 or any(len(t) != 10 for t in times):
        return None
    if any(times[i] >= times[i + 1] for i in range(len(times) - 1)):
        return None

    _cache.set(cache_key, candles, ttl_seconds=_TV_CACHE_TTL)
    return candles


def list_supported_benchmarks() -> List[str]:
    return list(SUPPORTED_BENCHMARKS)


def _clean_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        if pd.isna(f):
            return None
        return f
    except Exception:
        return None


def _validate_and_shape(df: pd.DataFrame, lookback_days: int) -> Optional[Dict[str, Any]]:
    if df is None or df.empty:
        return None
    cols = {str(c).lower(): c for c in df.columns}
    required = ["time", "open", "high", "low", "close"]
    if any(r not in cols for r in required):
        return None

    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    out["time"] = pd.to_datetime(out["time"], errors="coerce")
    out = out.dropna(subset=["time"])
    for r in required[1:]:
        out[r] = pd.to_numeric(out[r], errors="coerce")

    has_volume = "volume" in out.columns
    if has_volume:
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)

    # Drop rows with NaN in OHLC
    out = out.dropna(subset=required[1:])
    if out.empty:
        return None

    out = out.sort_values("time").drop_duplicates(subset=["time"], keep="last")
    out = out.tail(lookback_days)

    candles: List[Dict[str, Any]] = []
    volumes: List[Dict[str, Any]] = []
    for _, row in out.iterrows():
        t = row["time"].strftime("%Y-%m-%d")
        o, h, l, c = (_clean_float(row[k]) for k in ("open", "high", "low", "close"))
        if None in (o, h, l, c):
            continue
        candles.append({"time": t, "open": o, "high": h, "low": l, "close": c})
        vol = int(row["volume"]) if has_volume else 0
        volumes.append({"time": t, "value": max(0, vol)})

    if not candles or not all(candles[i]["time"] < candles[i + 1]["time"] for i in range(len(candles) - 1)):
        return None
    return {"candles": candles, "volumes": volumes}


def _fetch_from_source(source: str, symbol: str, interval: str, lookback_days: int) -> Optional[pd.DataFrame]:
    feed_symbol = _SOURCE_SYMBOL_MAP.get(source, {}).get(symbol)
    if feed_symbol is None or Quote is None:
        return None
    end = datetime.date.today() + datetime.timedelta(days=1)
    start = datetime.date.today() - datetime.timedelta(days=max(lookback_days * 3, 90))
    q = Quote(symbol=feed_symbol, source=source)
    return q.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval=interval)


def get_benchmark_history(symbol: str = "VNINDEX", interval: str = "1D", lookback_days: int = 500) -> Dict[str, Any]:
    result: Dict[str, Any] = {"symbol": symbol.upper(), "candles": [], "volumes": [], "source": ""}
    sym = (symbol or "").upper().strip()
    result["symbol"] = sym
    ivl = _INTERVAL_MAP.get((interval or "").upper())
    if sym not in SUPPORTED_BENCHMARKS:
        result["error"] = f"Unsupported benchmark symbol: {symbol}. Supported: {', '.join(SUPPORTED_BENCHMARKS)}"
        return result
    if ivl is None:
        result["error"] = f"Unsupported interval: {interval}. Supported: 1D, 1W, 1M"
        return result
    try:
        lookback_days = int(lookback_days)
    except Exception:
        result["error"] = f"Invalid lookback_days: {lookback_days}"
        return result
    if lookback_days <= 0:
        result["error"] = f"Invalid lookback_days: {lookback_days}"
        return result

    ttl = 300 if ivl == "1D" else 1800
    cache_key = f"benchmark:{sym}:{ivl}:{lookback_days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    last_error = ""
    if ivl == "1D":
        tv_symbol = _TV_BENCH_MAP.get(sym)
        if tv_symbol:
            try:
                tv_candles = _tv_fetch_candles(tv_symbol)
            except Exception as exc:
                logger.warning("TradingView benchmark fetch failed (%s): %s", sym, exc)
                tv_candles = None
            if tv_candles:
                trimmed = tv_candles[-lookback_days:]
                result["candles"] = [
                    {
                        "time": c["time"],
                        "open": round(c["open"], 2),
                        "high": round(c["high"], 2),
                        "low": round(c["low"], 2),
                        "close": round(c["close"], 2),
                    }
                    for c in trimmed
                ]
                result["volumes"] = [
                    {"time": c["time"], "value": max(0, int(c["volume"]))} for c in trimmed
                ]
                result["source"] = "tradingview"
                result.pop("error", None)
                _cache.set(cache_key, result, ttl_seconds=ttl)
                return result
            last_error = "tradingview: empty or invalid history payload"

    for source in ("VCI", "TCBS", "KBS"):
        try:
            raw = _fetch_from_source(source, sym, ivl, lookback_days)
            shaped = _validate_and_shape(raw, lookback_days) if raw is not None else None
            if shaped:
                result["candles"] = shaped["candles"]
                result["volumes"] = shaped["volumes"]
                result["source"] = source
                break
            last_error = f"{source}: empty or invalid history payload"
        except Exception as e:
            logger.warning("benchmark fetch failed (%s/%s): %s", sym, source, e)
            last_error = f"{source}: {e}"

    if not result["candles"]:
        result["error"] = f"No benchmark data available for {sym} ({ivl}). Last error: {last_error}" if last_error \
            else f"No benchmark data available for {sym} ({ivl})"
        if Quote is None:
            result["error"] += " | vnstock library unavailable"
    else:
        result.pop("error", None)

    _cache.set(cache_key, result, ttl_seconds=ttl)
    return result
