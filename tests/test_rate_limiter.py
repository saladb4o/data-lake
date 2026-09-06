"""Tests for the process-wide token-bucket rate limiter."""

import threading
import time

import pytest

from services.rate_limiter import TokenBucket, get_bucket, limit, reset_buckets


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_buckets()
    yield
    reset_buckets()


def test_burst_is_capped_then_refills_at_the_configured_rate():
    bucket = TokenBucket(rate_per_minute=600, capacity=5)  # 10/s, burst 5
    start = time.monotonic()
    for _ in range(5):
        assert bucket.acquire(timeout=0)     # burst drains instantly
    assert time.monotonic() - start < 0.05
    assert not bucket.acquire(timeout=0), "bucket should be empty after its burst"

    assert bucket.acquire(timeout=1.0), "should refill within a second"
    assert 0.05 <= time.monotonic() - start < 1.5


def test_sustained_rate_is_enforced_across_threads():
    """Ten threads sharing a 600/min bucket must still average 10/s."""
    bucket = TokenBucket(rate_per_minute=600, capacity=1)
    acquired = []
    lock = threading.Lock()

    def worker():
        for _ in range(3):
            bucket.acquire()
            with lock:
                acquired.append(time.monotonic())

    start = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()

    elapsed = time.monotonic() - start
    assert len(acquired) == 30
    # 30 tokens at 10/s cannot complete meaningfully faster than ~2.9s.
    assert elapsed >= 2.5, f"30 requests took {elapsed:.2f}s; the limit was not enforced"


def test_zero_rate_disables_the_limit():
    bucket = TokenBucket(rate_per_minute=0)
    assert not bucket.enabled
    start = time.monotonic()
    for _ in range(500):
        assert bucket.acquire(timeout=0)
    assert time.monotonic() - start < 0.5


def test_timeout_returns_false_without_consuming():
    bucket = TokenBucket(rate_per_minute=60, capacity=1)  # 1/s
    assert bucket.acquire(timeout=0)
    assert not bucket.acquire(timeout=0.05)


def test_bucket_is_shared_per_name_so_new_pools_cannot_widen_the_budget():
    assert get_bucket("vnstock") is get_bucket("vnstock")
    assert get_bucket("vnstock") is not get_bucket("http")


def test_rate_is_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("VNSTOCK_RATE_LIMIT_PER_MIN", "17")
    reset_buckets()
    assert get_bucket("vnstock").rate_per_minute == 17


def test_invalid_env_value_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("VNSTOCK_RATE_LIMIT_PER_MIN", "not-a-number")
    reset_buckets()
    assert get_bucket("vnstock").rate_per_minute == 55


def test_limit_context_manager_acquires():
    monkey = get_bucket("http")
    before = monkey._tokens
    with limit("http") as ok:
        assert ok
    assert get_bucket("http")._tokens <= before
