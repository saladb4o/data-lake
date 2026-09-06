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
from typing import Any, Dict, List, Optional

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
        """When the filing became public: its filing_date, else quarter end + lag."""
        filed = _parse_date(record.get("filing_date"))
        if filed is not None:
            return filed
        if quarter_end is None:
            return None
        return date.fromordinal(quarter_end.toordinal() + self._lag_days)

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
