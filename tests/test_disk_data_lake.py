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



@pytest.fixture
def local_data_file():
    """Yields a factory for throwaway files in the repo's real data/ dir.

    resolve_data_file() derives the local candidate from the module's own
    location, so exercising the real path beats monkeypatching os.path.
    """
    import services.stock_service as ss
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ss.__file__))), "data")
    os.makedirs(base, exist_ok=True)
    created = []

    def make(name, content, mtime):
        path = os.path.join(base, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.utime(path, (mtime, mtime))
        created.append(path)
        return path

    yield make
    for path in created:
        try:
            os.remove(path)
        except OSError:
            pass


class TestDataFileResolution:
    """resolve_data_file() picks which copy of a data file wins.

    It used to sort by (size, mtime) descending, so a large stale file beat a
    smaller fresh one - wrong for financial data, where "bigger" and "more
    correct" are unrelated. Freshness now decides, with size only as tiebreak.
    """

    def test_fresher_file_wins_over_larger_stale_one(self, tmp_path, monkeypatch, local_data_file):
        import services.stock_service as ss

        gdrive = tmp_path / "gdrive"
        gdrive.mkdir()
        monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(gdrive))

        fn = "pytest_freshness_probe.json"
        stale_big = gdrive / fn
        stale_big.write_text(json.dumps({"pad": "x" * 5000}), encoding="utf-8")
        os.utime(stale_big, (1_000_000, 1_000_000))

        fresh_small = local_data_file(fn, json.dumps({"a": 1}), 2_000_000)

        assert ss.resolve_data_file(fn) == fresh_small, (
            "resolver preferred the larger stale file over the fresher one"
        )

    def test_size_still_breaks_ties_at_equal_mtime(self, tmp_path, monkeypatch, local_data_file):
        import services.stock_service as ss

        gdrive = tmp_path / "gdrive"
        gdrive.mkdir()
        monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(gdrive))

        fn = "pytest_tiebreak_probe.json"
        big = gdrive / fn
        big.write_text(json.dumps({"pad": "x" * 5000}), encoding="utf-8")
        os.utime(big, (3_000_000, 3_000_000))
        local_data_file(fn, json.dumps({"a": 1}), 3_000_000)

        assert ss.resolve_data_file(fn) == str(big), "equal mtime should prefer the richer file"

    def test_writes_update_the_existing_copy_instead_of_forking_one(self, tmp_path, monkeypatch, local_data_file):
        """Writes went to get_data_dir() regardless of where the lake already lived.

        With a lake in data/ and GOOGLE_DRIVE_DATA_DIR set, a write created a
        second, partial copy on Drive instead of updating the real one, leaving
        two diverging lakes.
        """
        import services.stock_service as ss

        gdrive = tmp_path / "gdrive"
        gdrive.mkdir()
        monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(gdrive))

        fn = "pytest_fork_probe.json"
        local_path = local_data_file(fn, json.dumps({"OLD": {"v": 0}}), 9_000_000)

        lake = DiskDataLake()
        lake.save_symbol_record(fn, "VCB", {"v": 1})

        with open(local_path, encoding="utf-8") as fh:
            updated = json.load(fh)
        assert updated.get("VCB") == {"v": 1}, "existing lake was not updated"
        assert updated.get("OLD") == {"v": 0}, "existing records were dropped"
        assert not (gdrive / fn).exists(), "write forked a second copy onto Google Drive"
