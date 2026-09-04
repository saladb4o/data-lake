"""Cap-weighted composite sector indices built from real constituent data.

Data sources:
- data/historical_prices.json : quarterly OHLCV aggregates per symbol
- data/screener_snapshot.json : market cap / price / pe / pb / roe per symbol
- data/industries.json        : per-symbol ICB classification
- vnstock Quote.history       : recent daily candles for top-weight constituents
"""

import json
import logging
import math
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")

_MAX_DAILY_SYMBOLS = 4
_DAILY_BATCH_TIMEOUT = 1.0
_DAILY_CACHE_TTL = 6 * 3600

_TV_SYMBOL_MAP = {
    "VNFIN": "HOSE:VNFIN",
    "VNFINLEAD": "HOSE:VNFINLEAD",
    "VNDIAMOND": "HOSE:VNDIAMOND",
    "VNSI": "HOSE:VNSI",
    "VN100": "HOSE:VN100",
    "VNIT": "HOSE:VNIT",
    "VNREAL": "HOSE:VNREAL",
    "VNUTI": "HOSE:VNUTI",
    "VNMAT": "HOSE:VNMAT",
    "VNHEAL": "HOSE:VNHEAL",
    "VNIND": "HOSE:VNIND",
    "VNCONS": "HOSE:VNCONS",
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
    run_kwargs: Dict[str, Any] = {}
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


class SimpleCache:
    def __init__(self):
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._store:
                data, expire_at = self._store[key]
                if time.time() < expire_at:
                    return data
                del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        with self._lock:
            self._store[key] = (value, time.time() + ttl_seconds)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


_cache = SimpleCache()
_file_cache: Dict[str, Tuple[float, Any]] = {}
_file_lock = threading.Lock()

_vnstock_ok = False
try:
    from vnstock import Quote

    try:
        from vnstock.core import setup_api_key

        _api_key = os.environ.get("VNSTOCK_API_KEY")
        if _api_key:
            try:
                setup_api_key(_api_key)
            except Exception:
                pass
    except Exception:
        pass
    _vnstock_ok = True
except Exception:
    Quote = None
    _vnstock_ok = False


def _load_json(name: str) -> Optional[Any]:
    default_data_dir = os.path.join(_BASE_DIR, "data")
    if _DATA_DIR and _DATA_DIR != default_data_dir:
        path = os.path.join(_DATA_DIR, name)
    else:
        try:
            from services.stock_service import resolve_data_file
            path = resolve_data_file(name)
        except Exception:
            path = os.path.join(_DATA_DIR, name)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with _file_lock:
        hit = _file_cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    with _file_lock:
        _file_cache[path] = (mtime, data)
    return data


def _get_registry() -> Dict[str, Any]:
    reg = _cache.get("icb_registry")
    if reg is not None:
        return reg
    try:
        from services.stock_service import SECTOR_ICB_REGISTRY

        reg = dict(SECTOR_ICB_REGISTRY)
    except Exception as exc:
        logger.debug("SECTOR_ICB_REGISTRY unavailable: %s", exc)
        reg = {}
    _cache.set("icb_registry", reg, ttl_seconds=600)
    return reg


def get_sector_constituents(sector_code: str) -> List[str]:
    key = f"constituents:{sector_code}"
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)

    tickers: Set[str] = set()
    registry = _get_registry()
    entry = registry.get(sector_code) or {}
    icb_codes = {c.strip() for c in str(entry.get("icb_code") or "").split(",") if c.strip()}

    # 1. From industries.json ICB mappings
    industries = _load_json("industries.json") or []
    if icb_codes and isinstance(industries, list):
        for e in industries:
            try:
                c = str(e.get("icb_code") or "").strip()
                if (c in icb_codes or any(c.startswith(code[:2]) for code in icb_codes if len(code) >= 2)) and e.get("com_type_code") != "QU":
                    sym = str(e.get("symbol") or "").upper().strip()
                    if sym:
                        tickers.add(sym)
            except Exception:
                continue

    # 2. From industries ICB name matching (fallback)
    if not tickers and isinstance(industries, list):
        sector_name = re.sub(r"[^a-zà-ỹ0-9 ]+", " ", str(entry.get("name") or "").lower()).strip()
        if sector_name:
            by_icb_name: Dict[str, Set[str]] = {}
            for e in industries:
                try:
                    if e.get("com_type_code") != "QU":
                        n = str(e.get("icb_name") or "").strip().lower()
                        sym = str(e.get("symbol") or "").upper().strip()
                        if n and sym:
                            by_icb_name.setdefault(n, set()).add(sym)
                except Exception:
                    continue
            for icb_name, syms in by_icb_name.items():
                if sector_name in icb_name or icb_name in sector_name:
                    tickers.update(syms)

    # 3. From master categorized universe in stock_service (fallback)
    if not tickers:
        try:
            from services.stock_service import ALL_SYMBOLS_MAP, SECTOR_INVERTED_INDEX
            if sector_code in SECTOR_INVERTED_INDEX and SECTOR_INVERTED_INDEX[sector_code]:
                tickers.update(SECTOR_INVERTED_INDEX[sector_code])
            for s, inf in ALL_SYMBOLS_MAP.items():
                if (inf.get("sector_code") == sector_code or inf.get("sector") == sector_code) and inf.get("type", "STOCK") == "STOCK":
                    tickers.add(s)
        except Exception:
            pass

    # 4. From screener_snapshot.json (fallback)
    if not tickers:
        stocks = (_load_json("screener_snapshot.json") or {}).get("stocks") or {}
        for sym, info in stocks.items():
            if isinstance(info, dict) and info.get("sector_code") == sector_code:
                tickers.add(str(sym).upper())

    # 5. Fallback to representative stocks
    if not tickers:
        rep = entry.get("representative_stocks") or []
        tickers.update(str(s).upper() for s in rep)

    result = sorted(tickers)
    _cache.set(key, result, ttl_seconds=900)
    return list(result)


def _screener_stocks() -> Dict[str, Any]:
    return ((_load_json("screener_snapshot.json") or {}).get("stocks")) or {}


def _sector_weights(constituents: List[str]) -> Dict[str, float]:
    stocks = _screener_stocks()
    caps: Dict[str, float] = {}
    for s in constituents:
        info = stocks.get(s)
        if isinstance(info, dict):
            try:
                cap = float(info.get("market_cap") or 0)
            except (TypeError, ValueError):
                cap = 0.0
            if cap > 0 and math.isfinite(cap):
                caps[s] = cap
    if not caps:
        n = max(len(constituents), 1)
        return {s: 1.0 / n for s in constituents}
    vals = sorted(caps.values())
    median_cap = vals[len(vals) // 2]
    weights: Dict[str, float] = {}
    for s in constituents:
        weights[s] = caps.get(s, median_cap)
    total = sum(weights.values()) or 1.0
    return {s: w / total for s, w in weights.items()}


def _quarterly_index_series(
    constituents: List[str],
    weights: Dict[str, float],
    base_point: float,
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    hp = _load_json("historical_prices.json") or {}
    symbols_data = hp.get("symbols") or {}
    per_symbol: Dict[str, Dict[str, Dict[str, float]]] = {}

    for s in constituents:
        rec = symbols_data.get(s)
        if not isinstance(rec, dict):
            continue
        quarters = rec.get("quarters") or {}
        rows: Dict[str, Dict[str, float]] = {}
        for qkey, qd in quarters.items():
            try:
                rows[qkey] = {
                    "time": str(qd.get("end_date")),
                    "open": float(qd.get("start_price")),
                    "high": float(qd.get("high")),
                    "low": float(qd.get("low")),
                    "close": float(qd.get("close_price")),
                    "volume": float(qd.get("volume") or 0),
                }
            except (TypeError, ValueError):
                continue
        if rows:
            per_symbol[s] = rows

    if not per_symbol:
        return [], set()

    all_qkeys = sorted({q for rows in per_symbol.values() for q in rows})

    normalized: Dict[str, Dict[str, Dict[str, float]]] = {}
    for s, rows in per_symbol.items():
        first = min(rows.keys())
        base_close = rows[first]["close"]
        if not base_close or base_close <= 0:
            continue
        normalized[s] = {
            q: {f: v[f] / base_close for f in ("open", "high", "low", "close")}
            for q, v in rows.items()
        }

    covered: Set[str] = set(normalized.keys())

    def field_series(field: str) -> List[Tuple[str, float, int]]:
        out = []
        for q in all_qkeys:
            num = 0.0
            den = 0.0
            vol = 0.0
            for s, rows in normalized.items():
                v = rows.get(q)
                if v is None:
                    continue
                w = weights.get(s, 0.0)
                num += w * v[field]
                den += w
                vol += per_symbol[s][q]["volume"]
            if den > 0:
                out.append((q, num / den, vol))
        return out

    closes = field_series("close")
    opens = dict((q, v) for q, v, _ in field_series("open"))
    highs = dict((q, v) for q, v, _ in field_series("high"))
    lows = dict((q, v) for q, v, _ in field_series("low"))
    volumes = dict((q, v) for q, _, v in field_series("close"))

    if not closes:
        return [], covered

    q_times: Dict[str, str] = {}
    for s in covered:
        for q, v in per_symbol[s].items():
            t = v.get("time")
            if t and t not in ("None", ""):
                q_times.setdefault(q, t)

    scale = base_point / closes[0][1] if closes[0][1] else 1.0
    candles: List[Dict[str, Any]] = []
    prev_close = None
    for q, close_val, vol in closes:
        c = close_val * scale
        o = opens.get(q, close_val) * scale
        h = highs.get(q, close_val) * scale
        lo = lows.get(q, close_val) * scale
        h = max(h, c, o)
        lo = min(lo, c, o)
        if prev_close is not None:
            o = prev_close
            h = max(h, o)
            lo = min(lo, o)
        candles.append(
            {
                "time": q_times.get(q, q),
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(lo, 2),
                "close": round(c, 2),
                "volume": int(vol),
            }
        )
        prev_close = c
    return candles, covered


def _fetch_daily_history(symbol: str, start: str, end: str) -> Optional[List[Dict[str, Any]]]:
    cache_key = f"daily:{symbol}:{start}:{end}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    bars: Optional[List[Dict[str, Any]]] = None

    # Fast path 1: Check local L2 historical_prices.json lake
    hp = _load_json("historical_prices.json") or {}
    sym_bars = hp.get(symbol)
    if sym_bars and isinstance(sym_bars, list) and len(sym_bars) >= 5:
        filtered = [b for b in sym_bars if isinstance(b, dict) and start <= str(b.get("time", ""))[:10] <= end]
        if len(filtered) >= 5:
            _cache.set(cache_key, filtered, ttl_seconds=_DAILY_CACHE_TTL)
            return filtered

    # Fast path 2: Live quote with tight timeout (2.0s)
    try:
        def _call_quote():
            try:
                quote = Quote(symbol=symbol)
                df = quote.history(start=start, end=end, interval="1D")
                if df is not None and hasattr(df, "to_dict"):
                    records = df.to_dict(orient="records")
                    res = []
                    for r in records:
                        try:
                            t = r.get("time") or r.get("date")
                            if hasattr(t, "strftime"):
                                t = t.strftime("%Y-%m-%d")
                            res.append(
                                {
                                    "time": str(t)[:10],
                                    "open": float(r["open"]),
                                    "high": float(r["high"]),
                                    "low": float(r["low"]),
                                    "close": float(r["close"]),
                                    "volume": float(r.get("volume") or 0),
                                }
                            )
                        except (KeyError, TypeError, ValueError):
                            continue
                    return res if res else None
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_call_quote)
            bars = fut.result(timeout=2.0)
    except Exception as exc:
        logger.debug("daily history failed for %s: %s", symbol, exc)
        bars = None
    _cache.set(cache_key, bars, ttl_seconds=_DAILY_CACHE_TTL)
    return bars


def _daily_overlay(
    constituents: List[str],
    weights: Dict[str, float],
    lookback_days: int,
    quarterly_candles: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    if not _vnstock_ok or Quote is None:
        return [], set()

    ranked = sorted(constituents, key=lambda s: weights.get(s, 0.0), reverse=True)[
        :_MAX_DAILY_SYMBOLS
    ]
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=max(int(lookback_days * 1.5), 30))).strftime("%Y-%m-%d")

    results: Dict[str, List[Dict[str, Any]]] = {}
    executor = ThreadPoolExecutor(max_workers=min(4, len(ranked) or 1))
    futures = {executor.submit(_fetch_daily_history, s, start, end): s for s in ranked}
    deadline = time.time() + _DAILY_BATCH_TIMEOUT
    for fut in list(futures.keys()):
        remaining = max(deadline - time.time(), 0.5)
        try:
            res = fut.result(timeout=remaining)
        except Exception:
            res = None
        sym = futures[fut]
        if res:
            results[sym] = res
    executor.shutdown(wait=False)

    usable: Dict[str, List[Dict[str, Any]]] = {}
    ref_map: Dict[str, float] = {}
    hp = _load_json("historical_prices.json") or {}
    symbols_data = hp.get("symbols") or {}
    for s, bars in results.items():
        if len(bars) < 2:
            continue
        rec = symbols_data.get(s)
        if isinstance(rec, dict):
            quarters = rec.get("quarters") or {}
            if quarters:
                last_q = max(quarters.keys())
                try:
                    ref = float(quarters[last_q].get("close_price"))
                except (TypeError, ValueError, KeyError):
                    ref = 0.0
                if ref > 0 and math.isfinite(ref):
                    usable[s] = bars
                    ref_map[s] = ref
    if not usable:
        return [], set(results.keys())

    dates = sorted({b["time"] for bars in usable.values() for b in bars})
    by_date: Dict[str, Dict[str, Dict[str, float]]] = {}
    for s, bars in usable.items():
        ref = ref_map[s]
        for b in bars:
            if b["close"] <= 0:
                continue
            by_date.setdefault(b["time"], {})[s] = {
                "open": b["open"] / ref,
                "high": b["high"] / ref,
                "low": b["low"] / ref,
                "close": b["close"] / ref,
                "volume": b["volume"],
            }

    raw: List[Dict[str, Any]] = []
    for d in dates:
        day = by_date.get(d)
        if not day:
            continue
        num = den = vol = 0.0
        onum = oden = 0.0
        hnum = hden = 0.0
        lnum = lden = 0.0
        for s, v in day.items():
            w = weights.get(s, 0.0)
            num += w * v["close"]
            den += w
            onum += w * v["open"]
            oden += w
            hnum += w * v["high"]
            hden += w
            lnum += w * v["low"]
            lden += w
        if den <= 0:
            continue
        raw.append(
            {
                "time": d,
                "close": num / den,
                "open": onum / oden,
                "high": hnum / hden,
                "low": lnum / lden,
                "volume": vol,
            }
        )

    if not raw:
        return [], set(usable.keys())

    first_raw = raw[0]["close"]
    d0 = raw[0]["time"]
    anchor_value = None
    for qc in quarterly_candles:
        if qc["time"] < d0:
            anchor_value = qc["close"]
        else:
            break
    if anchor_value and first_raw:
        scale = anchor_value / first_raw
    else:
        scale = 1.0

    candles = []
    prev = None
    for row in raw:
        c = row["close"] * scale
        o = row["open"] * scale
        h = max(row["high"] * scale, c, o)
        lo = min(row["low"] * scale, c, o)
        if prev is not None:
            o = prev
            h = max(h, o)
            lo = min(lo, o)
        candles.append(
            {
                "time": row["time"],
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(lo, 2),
                "close": round(c, 2),
                "volume": int(row["volume"]),
            }
        )
        prev = c
    return candles, set(usable.keys())


def _resample(candles: List[Dict[str, Any]], volumes: List[Dict[str, Any]], interval: str):
    bucket_fn = None
    if interval in ("1W", "W"):
        def bucket_fn(t):
            d = datetime.strptime(str(t)[:10], "%Y-%m-%d")
            monday = d - timedelta(days=d.weekday())
            return monday.strftime("%Y-%m-%d")
    elif interval in ("1M", "M"):
        def bucket_fn(t):
            return t[:7] + "-01"
    if bucket_fn is None:
        return candles, volumes

    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for idx, c in enumerate(candles):
        b = bucket_fn(c["time"])
        if b not in merged:
            merged[b] = {
                "time": b,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": volumes[idx]["value"],
            }
            order.append(b)
        else:
            m = merged[b]
            m["high"] = max(m["high"], c["high"])
            m["low"] = min(m["low"], c["low"])
            m["close"] = c["close"]
            m["volume"] += volumes[idx]["value"]
    out_candles = [
        {"time": k, "open": merged[k]["open"], "high": merged[k]["high"], "low": merged[k]["low"], "close": merged[k]["close"]}
        for k in order
    ]
    out_volumes = [{"time": k, "value": merged[k]["volume"]} for k in order]
    return out_candles, out_volumes


def _try_tv_sector_index(
    sector_code: str,
    tv_symbol: str,
    interval_u: str,
    lookback_days: int,
    base_point: float,
) -> Optional[Dict[str, Any]]:
    try:
        candles = _tv_fetch_candles(tv_symbol)
    except Exception as exc:
        logger.warning("TradingView fast path error for %s: %s", sector_code, exc)
        return None
    if not candles:
        return None

    candles = candles[-max(int(lookback_days), 1):]
    out_candles: List[Dict[str, Any]] = []
    out_volumes: List[Dict[str, Any]] = []
    for c in candles:
        out_candles.append(
            {
                "time": c["time"],
                "open": round(c["open"], 2),
                "high": round(c["high"], 2),
                "low": round(c["low"], 2),
                "close": round(c["close"], 2),
            }
        )
        out_volumes.append({"time": c["time"], "value": int(c["volume"])})

    if interval_u not in ("1D", "D"):
        out_candles, out_volumes = _resample(out_candles, out_volumes, interval_u)

    try:
        constituents_count = len(get_sector_constituents(sector_code))
    except Exception:
        constituents_count = 0

    return {
        "sector_code": sector_code,
        "candles": out_candles,
        "volumes": out_volumes,
        "coverage": 1.0,
        "constituents_count": constituents_count,
        "base_point": base_point,
        "source": "tradingview",
    }


def build_sector_index(sector_code: str, interval: str = "1D", lookback_days: int = 500) -> Dict[str, Any]:
    cache_key = f"index:{sector_code}:{interval}:{lookback_days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    interval_u = (interval or "1D").upper()
    registry_entry_early = _get_registry().get(sector_code) or {}
    base_point_early = float(registry_entry_early.get("base_point") or 1000.0)

    tv_symbol = _TV_SYMBOL_MAP.get(str(sector_code).upper())
    if tv_symbol:
        fast = _try_tv_sector_index(sector_code, tv_symbol, interval_u, lookback_days, base_point_early)
        if fast is not None:
            _cache.set(cache_key, fast, ttl_seconds=_TV_CACHE_TTL)
            return fast

    constituents = get_sector_constituents(sector_code)
    registry_entry = _get_registry().get(sector_code) or {}
    base_point = float(registry_entry.get("base_point") or 1000.0)
    result: Dict[str, Any] = {"sector_code": sector_code, "candles": [], "volumes": []}

    if not constituents:
        result["coverage"] = 0.0
        result["constituents_count"] = 0
        logger.warning("no constituents resolved for sector %s", sector_code)
        _cache.set(cache_key, result, ttl_seconds=120)
        return result

    weights = _sector_weights(constituents)

    quarterly, q_covered = _quarterly_index_series(constituents, weights, base_point)
    coverage = len(q_covered) / len(constituents)

    daily: List[Dict[str, Any]] = []
    daily_covered: Set[str] = set()
    try:
        daily, daily_covered = _daily_overlay(constituents, weights, lookback_days, quarterly)
    except Exception as exc:
        logger.warning("daily overlay failed for %s: %s", sector_code, exc)

    if daily:
        first_daily_time = daily[0]["time"]
        kept = [c for c in quarterly if c["time"] < first_daily_time]
        candles = kept + daily
        coverage = max(coverage, (len(q_covered | daily_covered)) / len(constituents))
    else:
        candles = quarterly

    if not quarterly and candles:
        first = candles[0]["close"]
        if first:
            rebase = base_point / first
            for c in candles:
                for f in ("open", "high", "low", "close"):
                    c[f] = round(c[f] * rebase, 2)

    volumes = [{"time": c["time"], "value": int(c.pop("volume", 0))} for c in candles]

    if interval_u not in ("1D", "D"):
        candles, volumes = _resample(candles, volumes, interval_u)

    result["candles"] = candles
    result["volumes"] = volumes
    result["coverage"] = round(coverage, 3)
    result["constituents_count"] = len(constituents)
    result["base_point"] = base_point
    logger.info(
        "sector index %s: %d/%d constituents covered (%.1f%%), %d candles",
        sector_code, len(q_covered | daily_covered), len(constituents), coverage * 100, len(candles),
    )
    _cache.set(cache_key, result, ttl_seconds=300)
    return result


def get_sector_snapshot(sector_code: str) -> Dict[str, Any]:
    cache_key = f"snapshot:{sector_code}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    registry_entry = _get_registry().get(sector_code) or {}
    constituents = get_sector_constituents(sector_code)
    weights = _sector_weights(constituents)
    stocks = _screener_stocks()

    total_market_cap = 0.0
    pe_num = pb_num = roe_num = 0.0
    pe_den = pb_den = roe_den = 0.0
    advancers = decliners = unchanged = 0

    for s in constituents:
        info = stocks.get(s)
        if not isinstance(info, dict):
            continue
        w = weights.get(s, 0.0)
        try:
            cap = float(info.get("market_cap") or 0)
            if cap > 0:
                total_market_cap += cap
        except (TypeError, ValueError):
            pass
        for attr in ("pe", "pb", "roe"):
            try:
                val = float(info.get(attr) or 0)
            except (TypeError, ValueError):
                val = 0.0
            valid = 0 < val < 500 and math.isfinite(val)
            if not valid:
                continue
            if attr == "pe":
                pe_num += w * val
                pe_den += w
            elif attr == "pb":
                pb_num += w * val
                pb_den += w
            else:
                roe_num += w * val
                roe_den += w
        try:
            chg = float(info.get("change_pct") or 0)
        except (TypeError, ValueError):
            chg = 0.0
        if chg > 0:
            advancers += 1
        elif chg < 0:
            decliners += 1
        else:
            unchanged += 1

    try:
        idx = build_sector_index(sector_code, "1D", lookback_days=500)
        candles = idx.get("candles") or []
        latest = float(candles[-1]["close"]) if candles else base_or_default(registry_entry)
        if len(candles) >= 2 and candles[-2]["close"]:
            change_pct = (latest / float(candles[-2]["close"]) - 1.0) * 100.0
        else:
            change_pct = 0.0
    except Exception:
        latest = base_or_default(registry_entry)
        change_pct = 0.0

    snapshot = {
        "sector_code": sector_code,
        "latest": round(latest, 2),
        "change_pct": round(change_pct, 2),
        "total_market_cap": round(total_market_cap, 2),
        "pe": round(pe_num / pe_den if pe_den > 0 else float(registry_entry.get("pe") or 0.0), 2),
        "pb": round(pb_num / pb_den if pb_den > 0 else float(registry_entry.get("pb") or 0.0), 2),
        "roe": round(roe_num / roe_den if roe_den > 0 else float(registry_entry.get("roe") or 0.0), 2),
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
        "constituents_count": len(constituents),
    }
    _cache.set(cache_key, snapshot, ttl_seconds=180)
    return snapshot


def base_or_default(entry: Dict[str, Any]) -> float:
    try:
        return float(entry.get("base_point") or 1000.0)
    except (TypeError, ValueError):
        return 1000.0
