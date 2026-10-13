"""Point-in-time fundamentals for backtesting.

The fair-value backtest had no historical financial statements to work with, so
it reconstructed them from the historical price and today's valuation
multiples::

    eps  = historical_price / current_pe
    bvps = historical_price / current_pb
    net_income = eps * shares          # and revenue, ebit, cfo, fcf from there

Every input was therefore linear in price, so every model returned a fixed
multiple of the entry price and the backtest could not detect mispricing at
all - the same company valued at 10k and at 80k produced an identical
fair-value-to-price ratio. It also read today's screener for every historical
quarter, which is both lookahead (today's ROE deciding a 2021 purchase) and
survivorship bias (delisted companies are simply absent).

This module supplies the alternative: real quarterly fundamentals, keyed by
symbol and quarter, that were *publicly known* at the rebalance date. When a
symbol has no filing for a quarter, the correct answer is to skip it, not to
invent one.

Lake format (``historical_fundamentals.json``), matching the shape already used
by ``historical_prices.json``::

    {"symbols": {"HPG": {"quarters": {"2021-Q1": {
        "filing_date": "2021-04-28",
        "eps": 1234.0, "bvps": 15000.0, "revenue": 3.1e13, ...
    }}}}}

``filing_date`` is what makes it point-in-time. A Q1 report published on 28
April is not usable by a simulation rebalancing on 31 March, and treating it as
if it were is the most common way a backtest fabricates skill it does not have.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FUNDAMENTALS_LAKE_FILE = "historical_fundamentals.json"

# A filing is assumed public this many days after quarter end when the record
# carries no filing_date. Vietnamese listed companies must file quarterly
# reports within 20 days (30 for consolidated) and audited annual reports
# within 90; 45 days is the conservative middle used when the lake is silent.
DEFAULT_PUBLICATION_LAG_DAYS = 45

# Fields a valuation needs from a filing. A record must carry at least
# MIN_REQUIRED_FIELDS of these to count as usable; below that the payload
# would be padded with structural defaults, which is what this module exists
# to avoid.
STATEMENT_FIELDS = (
    "eps", "bvps", "revenue", "net_income", "ebit", "ebitda",
    "equity", "total_assets", "total_liabilities", "debt", "cash",
    "cfo", "fcf", "shares_out", "dividend_per_share",
)
MIN_REQUIRED_FIELDS = 4


def _parse_date(raw: Any) -> Optional[date]:
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None



def _quarter_order(quarter_code: str) -> Optional[Tuple[int, int]]:
    """Sortable (year, quarter); None when the code is not one."""
    try:
        year_text, quarter_text = str(quarter_code).split("-Q")
        return int(year_text), int(quarter_text)
    except (ValueError, AttributeError):
        return None


def _quarter_end_from_code(quarter_code: str) -> Optional[date]:
    """The last day of the quarter a code names."""
    order = _quarter_order(quarter_code)
    if order is None:
        return None
    year, quarter = order
    if not 1 <= quarter <= 4:
        return None
    month = quarter * 3
    return date(year, month, {3: 31, 6: 30, 9: 30, 12: 31}[month])


def _usable_field_count(record: Dict[str, Any]) -> int:
    count = 0
    for key in STATEMENT_FIELDS:
        value = record.get(key)
        if value is None or value == "":
            continue
        try:
            float(value)
        except (TypeError, ValueError):
            continue
        count += 1
    return count


class PointInTimeFundamentals:
    """Reads quarterly filings and answers "what was knowable on this date".

    Missing data is reported as missing. There is deliberately no code path
    that returns a partially invented record.
    """

    def __init__(self, lake: Optional[Dict[str, Any]] = None,
                 publication_lag_days: int = DEFAULT_PUBLICATION_LAG_DAYS):
        self._lock = threading.RLock()
        self._symbols: Dict[str, Dict[str, Any]] = {}
        self._lag_days = publication_lag_days
        self.load_errors: List[str] = []
        if lake is not None:
            self._symbols = self._normalise(lake)

    # -- loading ---------------------------------------------------------
    @classmethod
    def from_lake(cls, publication_lag_days: int = DEFAULT_PUBLICATION_LAG_DAYS
                  ) -> "PointInTimeFundamentals":
        """Loads the fundamentals lake, or an empty one if it is not present."""
        instance = cls(publication_lag_days=publication_lag_days)
        try:
            from services.stock_service import resolve_data_file
            path = resolve_data_file(FUNDAMENTALS_LAKE_FILE)
        except Exception:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, "data", FUNDAMENTALS_LAKE_FILE)

        if not path or not os.path.exists(path):
            instance.load_errors.append(
                f"{FUNDAMENTALS_LAKE_FILE} not found; point-in-time "
                "fundamentals are unavailable."
            )
            return instance
        try:
            with open(path, "r", encoding="utf-8") as handle:
                instance._symbols = instance._normalise(json.load(handle))
        except (OSError, ValueError) as exc:
            instance.load_errors.append(f"could not read {path}: {exc}")
            logger.warning("point-in-time fundamentals unreadable at %s: %s", path, exc)
        return instance

    @staticmethod
    def _normalise(raw: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(raw, dict):
            return {}
        symbols = raw.get("symbols", raw)
        if not isinstance(symbols, dict):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for symbol, payload in symbols.items():
            if isinstance(payload, dict) and isinstance(payload.get("quarters"), dict):
                out[str(symbol).upper()] = payload
        return out

    # -- queries ---------------------------------------------------------
    @property
    def is_empty(self) -> bool:
        return not self._symbols

    @property
    def symbol_count(self) -> int:
        return len(self._symbols)

    def coverage(self, quarter_code: str) -> int:
        """How many symbols have a usable filing for this quarter."""
        with self._lock:
            return sum(
                1 for payload in self._symbols.values()
                if _usable_field_count(payload["quarters"].get(quarter_code) or {})
                >= MIN_REQUIRED_FIELDS
            )

    def publication_date(self, record: Dict[str, Any], quarter_end: Optional[date]) -> Optional[date]:
        """When the filing became public: its filing_date, else quarter end + lag.

        ``quarter_end`` is the caller's, but its absence must not silently
        disable the gate. Returning None here means "publication date
        unknown", and get() reads an unknown date as no restriction - so a
        caller who simply forgot the argument would get every filing at
        every simulated date, which is lookahead that looks like skill.
        The record knows its own fiscal date, so fall back to that before
        giving up.
        """
        filed = _parse_date(record.get("filing_date"))
        if filed is not None:
            return filed
        if quarter_end is None:
            quarter_end = _parse_date(record.get("fiscal_date"))
        if quarter_end is None:
            return None
        return date.fromordinal(quarter_end.toordinal() + self._lag_days)

    def quarters_for(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """Every quarter the lake holds for ``symbol``, newest last.

        Deliberately free of any as-of restriction: the backtest needs
        point-in-time and uses ``latest_as_of`` for it, but a live quote
        is being asked about today and wants whatever was filed most
        recently. A caller that wanted point-in-time and reached for
        this would be asking the wrong question, so the name says which
        one it answers.
        """
        payload = self._symbols.get(str(symbol).upper())
        if not isinstance(payload, dict):
            return {}
        quarters = payload.get("quarters")
        return dict(quarters) if isinstance(quarters, dict) else {}

    def latest_as_of(
        self,
        symbol: str,
        as_of: date,
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """The newest filing this symbol had published by ``as_of``.

        Standing at 31 March 2021, the market has last year's Q4 report;
        it does not have Q1, which ends that same day. Asking for the
        quarter that is ending is asking for a filing that cannot exist
        yet, and the honest answer is always None - at every lag, which
        is what makes the mistake hard to see: the result looks like a
        gate working rather than a question that can never be answered.

        Returns (quarter_code, record), or None when nothing this symbol
        filed was public by that date.
        """
        with self._lock:
            payload = self._symbols.get(str(symbol).upper())
        if not payload:
            return None

        best: Optional[Tuple[Tuple[int, int], str, Dict[str, Any]]] = None
        for quarter_code, record in (payload.get("quarters") or {}).items():
            if not isinstance(record, dict):
                continue
            if _usable_field_count(record) < MIN_REQUIRED_FIELDS:
                continue
            published = self.publication_date(
                record, _quarter_end_from_code(quarter_code))
            if published is None or published > as_of:
                continue
            order = _quarter_order(quarter_code)
            if order is None:
                continue
            if best is None or order > best[0]:
                best = (order, quarter_code, dict(record))
        if best is None:
            return None
        return best[1], best[2]

    def get(
        self,
        symbol: str,
        quarter_code: str,
        as_of: Optional[date] = None,
        quarter_end: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        """Returns the filing for this quarter if it was public by ``as_of``.

        Returns None - never a padded record - when the symbol is unknown, the
        quarter is absent, the filing is too thin to value on, or the report
        had not been published yet at the simulated date.
        """
        with self._lock:
            payload = self._symbols.get(str(symbol).upper())
        if not payload:
            return None
        record = payload["quarters"].get(quarter_code)
        if not isinstance(record, dict):
            return None
        if _usable_field_count(record) < MIN_REQUIRED_FIELDS:
            return None
        if as_of is not None:
            published = self.publication_date(record, quarter_end)
            if published is not None and published > as_of:
                # Known to us now, not known to the market then.
                return None
        return dict(record)
