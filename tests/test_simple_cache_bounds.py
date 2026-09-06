"""SimpleCache must stay bounded.

Entries were only dropped when a caller read one past its stale window, so a
key never read again was never freed. Across ~1600 symbols and long TTLs
holding whole statement payloads, that is an unbounded leak.
"""

import time

from services.stock_service import SimpleCache


def test_cache_never_exceeds_its_limit():
    c = SimpleCache(max_entries=100)
    for i in range(1000):
        c.set(f"k{i}", {"v": i}, ttl_seconds=3600)
    assert len(c) <= 100


def test_stale_entries_are_evicted_before_live_ones():
    c = SimpleCache(max_entries=10)
    for i in range(8):
        c.set(f"stale{i}", i, ttl_seconds=1, stale_multiplier=1)  # dead in 1s
    time.sleep(1.1)
    for i in range(8):
        c.set(f"live{i}", i, ttl_seconds=3600)

    assert len(c) <= 10
    survivors = sum(1 for i in range(8) if c.get(f"live{i}") is not None)
    assert survivors == 8, "live entries were evicted while stale ones remained"


def test_values_still_round_trip_and_expire():
    c = SimpleCache(max_entries=10)
    c.set("a", 123, ttl_seconds=3600)
    assert c.get("a") == 123
    c.invalidate("a")
    assert c.get("a") is None


def test_limit_is_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("CACHE_MAX_ENTRIES", "42")
    assert SimpleCache().max_entries == 42
    monkeypatch.setenv("CACHE_MAX_ENTRIES", "rubbish")
    assert SimpleCache().max_entries == SimpleCache.DEFAULT_MAX_ENTRIES
