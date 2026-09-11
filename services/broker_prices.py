"""Daily candles from DNSE's chart endpoint.

Where the URL came from
-----------------------
Read out of vietfin (Apache-2.0), which calls it from working code with a
response model attached, so the shape was observed by somebody rather
than inferred from a spec. The library itself is not a dependency here:
it is 0.2.0, self-declared alpha, last committed April 2024, and this
needs one URL and one response shape, not httpx and pydantic.

Why DNSE and nothing else
-------------------------
Three endpoints were tried on run 34570149277 against the same universe
on the same pass. DNSE answered. SSI's `iboard/dchart` and TCBS's
`bars-long-term` answered for zero symbols out of their first forty and
were removed - TCBS is reported to have closed its unauthenticated
endpoints since vietfin was written, and SSI's supported route is
FastConnect Data, which needs a registered key.

`resolution=1D` is deliberate. The 90-day ceiling vietfin documents
belongs to the intraday resolutions; the daily bars are not subject to it,
so one request covers a decade.

TLS verification is left on, through the project's single policy. The
Node fetcher this replaces opens with NODE_TLS_REJECT_UNAUTHORIZED = '0',
which is the reason it was not reused.
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

#: The lake starts at 2016-Q1; ask from just before it so the first
#: quarter has candles rather than opening mid-quarter.
DEFAULT_START = "2016-01-01"


_DNSE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/119.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://banggia.dnse.com.vn/",
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
