"""Regression tests for services.stock_service.DiskDataLake.

Motivating defect: save_symbol_record() acquired self._lock and then called
read_json(), which acquires the same lock. threading.Lock is not reentrant, so
the writer self-deadlocked and - because it died holding the lock - every
subsequent read and write of the data lake blocked behind it too.
"""

import json
import os
import threading

import pytest

from services.stock_service import DiskDataLake


@pytest.fixture
def lake_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(tmp_path))
    return tmp_path


def _save_with_timeout(lake, *args, timeout=10):
    """Run save_symbol_record on a worker; return True if it completed."""
    done = threading.Event()
    err = []

    def run():
        try:
            lake.save_symbol_record(*args)
        except Exception as exc:  # pragma: no cover - surfaced via err
            err.append(exc)
        finally:
            done.set()

    threading.Thread(target=run, daemon=True).start()
    finished = done.wait(timeout=timeout)
    assert not err, f"save raised: {err[0]!r}"
    return finished


def test_save_into_existing_lake_does_not_deadlock(lake_dir):
    """The file exists on disk but was never read into memory (post-restart)."""
    fn = "probe_lake.json"
    (lake_dir / fn).write_text(json.dumps({"VCB": {"x": 1}}), encoding="utf-8")

    lake = DiskDataLake()
    assert _save_with_timeout(lake, fn, "TCB", {"x": 2}), "save_symbol_record deadlocked"

    written = json.loads((lake_dir / fn).read_text(encoding="utf-8"))
    assert written["TCB"] == {"x": 2}
    assert written["VCB"] == {"x": 1}, "pre-existing records must be preserved"


def test_lock_is_not_poisoned_for_subsequent_readers(lake_dir):
    """A deadlocked writer used to block every later reader as well."""
    fn = "probe_lake2.json"
    (lake_dir / fn).write_text(json.dumps({"VCB": {"x": 1}}), encoding="utf-8")

    lake = DiskDataLake()
    assert _save_with_timeout(lake, fn, "TCB", {"x": 2})

    result = {}
    done = threading.Event()

    def reader():
        result["data"] = lake.read_json(fn)
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    assert done.wait(timeout=10), "read_json blocked behind a poisoned lock"
    assert set(result["data"]) == {"VCB", "TCB"}


def test_concurrent_writers_do_not_lose_records(lake_dir):
    """Writes from the 24-thread executor must not clobber each other."""
    fn = "probe_lake3.json"
    lake = DiskDataLake()

    threads = [
        threading.Thread(target=lake.save_symbol_record, args=(fn, f"S{i:03d}", {"i": i}))
        for i in range(40)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "a concurrent writer hung"

    written = json.loads((lake_dir / fn).read_text(encoding="utf-8"))
    assert len(written) == 40, f"lost records: only {len(written)}/40 persisted"
