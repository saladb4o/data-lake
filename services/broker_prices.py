"""Daily candles from Vietnamese brokers' own chart endpoints.

Why not vnstock
---------------
The price lake used to be fetched by a yfinance batch download with a
vnstock fallback, while the module header and the saved payload both
claimed TradingView. vnstock is rate-limited to 60 requests a minute on
the community tier and wraps these same brokers anyway, so going to them
directly removes a dependency, a rate limit and a layer of indirection at
once.

Where these URLs come from
--------------------------
Read out of https://github.com/vietfin/vietfin (Apache-2.0), which calls
them from working code with a response model attached - so the shapes
below were observed by somebody, not inferred from a specification. The
library itself is not a dependency here: it is version 0.2.0, self-
declared alpha, and its last commit is from April 2024. Two URLs and two
response shapes are what this needs; httpx, pydantic and selectolax are
not.

Order, and why
--------------
DNSE and SSI both take a from/to window and answer a decade in one
request. TCBS caps a response at 365 points - vietfin's own loop says so
- so ten years costs ten requests per symbol, fifteen thousand across the
universe, which is why it goes last and only picks up what the other two
had nothing for.

DNSE leads because its endpoint carries no authentication in vietfin's
call and its documented 90-day ceiling applies only to intraday
intervals, not to the daily bars this needs. TCBS is last also because it
is reported to have closed its unauthenticated endpoints since vietfin
was written; if that is so it will answer for nobody, the probe below
will drop it after forty symbols, and the tally will say so.

SSI's `iboard/dchart` is the public chart endpoint behind the iBoard
website, not FastConnect Data. FastConnect is SSI's supported route and
would very likely be steadier, but it requires an account and a
registered key - a decision for whoever owns the account, not something
to wire in unasked.

What has NOT been established
-----------------------------
Both hosts are refused by this container's egress proxy, so none of this
has run against the live endpoints from here. The caller counts which
source answered for each symbol and prints the tally; until a runner
prints it, these are candidate sources being measured, which is why
yfinance and vnstock stay behind them.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from services.tls_config import tls_verify

logger = logging.getLogger(__name__)

DNSE_OHLC_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
SSI_HISTORY_URL = "https://iboard.ssi.com.vn/dchart/api/history"
TCBS_BARS_URL = ("https://apipubaws.tcbs.com.vn/stock-insight/v2/stock/"
                 "bars-long-term")

#: The lake starts at 2016-Q1; ask from just before it so the first
#: quarter has candles rather than opening mid-quarter.
DEFAULT_START = "2016-01-01"

#: TCBS answers at most this many points per request. vietfin's fetch
#: loop chunks on the same number, and a larger countBack is silently
#: truncated - which would look like a symbol that stopped trading.
TCBS_MAX_POINTS = 365

_DNSE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/119.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://banggia.dnse.com.vn/",
}

_SSI_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/119.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Origin": "https://iboard.ssi.com.vn",
    "Referer": "https://iboard.ssi.com.vn/",
}

_TCBS_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/119.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Accept-language": "vi",
    "Referer": "https://tcinvest.tcbs.com.vn/",
}


def _day(stamp: Any) -> Optional[str]:
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(float(stamp)))
    except (TypeError, ValueError):
        return None


def parse_udf(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """Turns one UDF chart response into rows, or None if it carries none.

    UDF answers ``{"s": "ok", "t": [...], "o": [...], ...}``: one parallel
    array per field. Arrays of unequal length mean a truncated response,
    and zipping them would pair one day's close with another day's open -
    silently, across years. The short case is refused, not trimmed.
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("s") not in ("ok", None):
        return None
    times = payload.get("t")
    if not isinstance(times, list) or not times:
        return None
    series = {}
    for key in ("o", "h", "l", "c", "v"):
        column = payload.get(key)
        if not isinstance(column, list) or len(column) != len(times):
            return None
        series[key] = column

    rows: List[Dict[str, Any]] = []
    for index, stamp in enumerate(times):
        day = _day(stamp)
        if day is None:
            continue
        try:
            rows.append({
                "time": day,
                "open": float(series["o"][index]),
                "high": float(series["h"][index]),
                "low": float(series["l"][index]),
                "close": float(series["c"][index]),
                "volume": float(series["v"][index] or 0.0),
            })
        except (TypeError, ValueError):
            continue
    return rows or None


def parse_tcbs_bars(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """Rows out of a TCBS bars-long-term response.

    Shaped as a list of dicts under ``data``, keyed ``tradingDate`` and
    the four prices. tradingDate arrives as an ISO timestamp rather than
    a unix one, so it is cut to its date rather than converted.
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get("data")
    if not isinstance(raw, list) or not raw:
        return None
    rows: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stamp = item.get("tradingDate")
        if not isinstance(stamp, str) or len(stamp) < 10:
            continue
        try:
            rows.append({
                "time": stamp[:10],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume") or 0.0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return rows or None


def _window(start: str, end: Optional[str]) -> tuple:
    """The from/to pair both window endpoints want, as unix seconds."""
    start_ts = int(datetime.strptime(start, "%Y-%m-%d")
                   .replace(tzinfo=timezone.utc).timestamp())
    end_ts = (int(datetime.strptime(end, "%Y-%m-%d")
                  .replace(tzinfo=timezone.utc).timestamp())
              if end else int(time.time()))
    return start_ts, end_ts


def fetch_dnse(symbol: str, start: str = DEFAULT_START,
               end: Optional[str] = None, timeout: int = 20,
               session: Optional[requests.Session] = None
               ) -> Optional[List[Dict[str, Any]]]:
    """The whole daily history in one request, or None.

    ``resolution=1D`` deliberately: the 90-day ceiling vietfin warns about
    is a property of the intraday resolutions, and asking for those here
    would inherit a limit that does not apply.
    """
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return None
    start_ts, end_ts = _window(start, end)
    get = (session or requests).get
    try:
        response = get(DNSE_OHLC_URL,
                       params={"symbol": symbol, "resolution": "1D",
                               "from": start_ts, "to": end_ts},
                       headers=_DNSE_HEADERS, timeout=timeout,
                       verify=tls_verify())
        if response.status_code != 200:
            return None
        return parse_udf(response.json())
    except (requests.RequestException, ValueError):
        logger.debug("dnse ohlcs failed for %s", symbol, exc_info=True)
        return None


def fetch_ssi(symbol: str, start: str = DEFAULT_START,
              end: Optional[str] = None, timeout: int = 20,
              session: Optional[requests.Session] = None
              ) -> Optional[List[Dict[str, Any]]]:
    """The whole history in one request, or None."""
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return None
    start_ts, end_ts = _window(start, end)
    get = (session or requests).get
    try:
        response = get(SSI_HISTORY_URL,
                       params={"resolution": "1D", "symbol": symbol,
                               "from": start_ts, "to": end_ts},
                       headers=_SSI_HEADERS, timeout=timeout,
                       verify=tls_verify())
        if response.status_code != 200:
            return None
        return parse_udf(response.json())
    except (requests.RequestException, ValueError):
        logger.debug("ssi history failed for %s", symbol, exc_info=True)
        return None


def fetch_tcbs(symbol: str, start: str = DEFAULT_START,
               end: Optional[str] = None, timeout: int = 20,
               session: Optional[requests.Session] = None
               ) -> Optional[List[Dict[str, Any]]]:
    """The history in 365-point chunks, walked forward from ``start``.

    Stops at the first empty chunk. A symbol that listed late has no bars
    before its listing, so an empty first chunk is ordinary and must not
    abandon the symbol - the walk continues until a chunk that had data
    is followed by one that does not.
    """
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return None
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = (datetime.strptime(end, "%Y-%m-%d") if end
              else datetime.utcnow())
    get = (session or requests).get

    rows: List[Dict[str, Any]] = []
    seen_any = False
    while start_dt < end_dt:
        span = min((end_dt - start_dt).days, TCBS_MAX_POINTS)
        if span <= 0:
            break
        chunk_end = start_dt + timedelta(days=span)
        try:
            response = get(
                TCBS_BARS_URL,
                params={"ticker": symbol, "type": "stock", "resolution": "D",
                        "to": int(chunk_end.replace(tzinfo=timezone.utc)
                                  .timestamp()),
                        "countBack": span},
                headers=_TCBS_HEADERS, timeout=timeout, verify=tls_verify())
            chunk = (parse_tcbs_bars(response.json())
                     if response.status_code == 200 else None)
        except (requests.RequestException, ValueError):
            logger.debug("tcbs bars failed for %s", symbol, exc_info=True)
            chunk = None
        if chunk:
            seen_any = True
            rows.extend(chunk)
        elif seen_any:
            break
        start_dt = chunk_end

    if not rows:
        return None
    # Chunks overlap at their boundaries, and a duplicated trading day
    # would be counted twice by the quarteriser.
    unique = {row["time"]: row for row in rows}
    return [unique[day] for day in sorted(unique)]
