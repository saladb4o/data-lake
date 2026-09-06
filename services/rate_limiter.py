"""Process-wide token-bucket rate limiting for upstream data providers.

The platform runs eleven independent thread pools (24 + 25 + 12 + 10 + 10 + 8 +
8 + 8 + 5 + 4 + ... workers) that all reach the same handful of upstreams. The
vnstock community tier allows 60 requests/minute, so uncoordinated concurrency
does not just risk throttling - it guarantees it, and the resulting 429s look
like flaky data rather than self-inflicted load.

A bucket is shared by name across every caller in the process, so adding a new
thread pool cannot widen the real request budget.

Configuration (requests per minute, 0 disables the limit):

    VNSTOCK_RATE_LIMIT_PER_MIN   default 55   vnstock provider calls
    HTTP_RATE_LIMIT_PER_MIN      default 240  direct HTTP egress

The vnstock default sits just under the documented 60/min so the retry layer
has headroom to work with.

Usage::

    from services.rate_limiter import limit

    with limit("vnstock"):
        df = quote.history(start=..., end=...)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

logger = logging.getLogger(__name__)

DEFAULT_LIMITS_PER_MIN: Dict[str, float] = {
    "vnstock": 55.0,
    "http": 240.0,
}


def _configured_rate(name: str) -> float:
    """Requests/minute for a bucket, from the environment or the default."""
    env_var = f"{name.upper()}_RATE_LIMIT_PER_MIN"
    raw = os.environ.get(env_var, "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            logger.warning("%s=%r is not a number; using the default rate.", env_var, raw)
    return DEFAULT_LIMITS_PER_MIN.get(name, 60.0)


class TokenBucket:
    """Thread-safe token bucket.

    Tokens refill continuously at ``rate_per_minute / 60`` per second up to
    ``capacity``. ``acquire`` blocks until a token is available, which is what
    callers want here: the work still needs doing, it just has to queue.
    """

    def __init__(self, rate_per_minute: float, capacity: Optional[float] = None):
        self.rate_per_minute = float(rate_per_minute)
        self._rate_per_second = self.rate_per_minute / 60.0
        # Default burst of one second's worth (min 1) - enough to avoid
        # lock-stepping every caller, small enough not to blow the budget.
        self.capacity = float(capacity if capacity is not None else max(1.0, self._rate_per_second))
        self._tokens = self.capacity
        self._updated_at = time.monotonic()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.rate_per_minute > 0

    def _refill_locked(self, now: float) -> None:
        elapsed = now - self._updated_at
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self._rate_per_second)
            self._updated_at = now

    def acquire(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """Consume ``tokens``, waiting if needed.

        Returns True once consumed, or False if ``timeout`` elapsed first.
        A disabled bucket (rate 0) always returns True immediately.
        """
        if not self.enabled:
            return True
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self._refill_locked(now)
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                shortfall = tokens - self._tokens
                wait = shortfall / self._rate_per_second
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait = min(wait, remaining)
            # Sleep outside the lock so other callers can refill and proceed.
            time.sleep(max(wait, 0.001))


_buckets: Dict[str, TokenBucket] = {}
_registry_lock = threading.Lock()


def get_bucket(name: str) -> TokenBucket:
    """Returns the process-wide bucket for ``name``, creating it on first use."""
    bucket = _buckets.get(name)
    if bucket is not None:
        return bucket
    with _registry_lock:
        bucket = _buckets.get(name)
        if bucket is None:
            bucket = TokenBucket(_configured_rate(name))
            _buckets[name] = bucket
            if bucket.enabled:
                logger.debug("Rate limiter %r: %.0f req/min", name, bucket.rate_per_minute)
            else:
                logger.debug("Rate limiter %r disabled", name)
    return bucket


def reset_buckets() -> None:
    """Drops every bucket so the next call re-reads the environment (tests)."""
    with _registry_lock:
        _buckets.clear()


@contextmanager
def limit(name: str, tokens: float = 1.0, timeout: Optional[float] = None) -> Iterator[bool]:
    """Context manager acquiring from the named bucket before the wrapped call."""
    yield get_bucket(name).acquire(tokens=tokens, timeout=timeout)
