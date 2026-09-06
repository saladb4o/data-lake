"""Regression tests for services.stock_service.DiskDataLake.

Motivating defect: save_symbol_record() acquired self._lock and then called
read_json(), which acquires the same lock. threading.Lock is not reentrant, so
the writer self-deadlocked and - because it died holding the lock - every
subsequent read and write of the data lake blocked behind it too.
"""

import json
import os
import threading
import time

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
    lake.flush()  # writes are coalesced; force them out to inspect the file

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
    lake.flush()

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
        lake.flush()

        with open(local_path, encoding="utf-8") as fh:
            updated = json.load(fh)
        assert updated.get("VCB") == {"v": 1}, "existing lake was not updated"
        assert updated.get("OLD") == {"v": 0}, "existing records were dropped"
        assert not (gdrive / fn).exists(), "write forked a second copy onto Google Drive"


class TestWriteCoalescing:
    """The lake is one JSON document, so saving one symbol rewrites all of it.

    Per-symbol writes made a crawl O(n^2): at 1600 symbols the file is ~155 MB,
    each rewrite ~3.3s, one pass ~89 minutes of pure serialisation - all inside
    the lake lock, serialising the 24-worker executor. Writes are now coalesced
    behind a debounce.
    """

    def test_a_burst_of_writes_costs_one_rewrite(self, lake_dir, monkeypatch):
        import services.stock_service as ss
        monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "30")  # no timer during the test

        writes = []
        real = DiskDataLake._write_file

        def counting(self, filename, lake):
            writes.append(filename)
            return real(self, filename, lake)

        monkeypatch.setattr(DiskDataLake, "_write_file", counting)

        lake = DiskDataLake()
        for i in range(200):
            lake.save_symbol_record("burst.json", f"S{i:03d}", {"i": i})
        assert writes == [], "writes should be deferred, not written per symbol"

        lake.flush()
        assert len(writes) == 1, f"a 200-symbol burst caused {len(writes)} rewrites"

        persisted = json.loads((lake_dir / "burst.json").read_text(encoding="utf-8"))
        assert len(persisted) == 200, "coalescing must not lose records"

    def test_pending_writes_are_visible_to_readers_before_flush(self, lake_dir, monkeypatch):
        """Reading must not serve the stale disk copy over unflushed changes."""
        monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "30")
        fn = "pending.json"
        (lake_dir / fn).write_text(json.dumps({"OLD": {"v": 0}}), encoding="utf-8")

        lake = DiskDataLake()
        lake.save_symbol_record(fn, "NEW", {"v": 1})
        assert lake.read_json(fn).get("NEW") == {"v": 1}, "pending write was not visible"
        assert lake.read_json(fn).get("OLD") == {"v": 0}

        lake.flush()
        on_disk = json.loads((lake_dir / fn).read_text(encoding="utf-8"))
        assert set(on_disk) == {"OLD", "NEW"}

    def test_zero_interval_is_write_through(self, lake_dir, monkeypatch):
        monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "0")
        lake = DiskDataLake()
        lake.save_symbol_record("sync.json", "VCB", {"v": 1})
        on_disk = json.loads((lake_dir / "sync.json").read_text(encoding="utf-8"))
        assert on_disk["VCB"] == {"v": 1}, "interval 0 should persist immediately"

    def test_debounce_timer_persists_without_an_explicit_flush(self, lake_dir, monkeypatch):
        monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "0.2")
        lake = DiskDataLake()
        lake.save_symbol_record("timed.json", "VCB", {"v": 1})

        path = lake_dir / "timed.json"
        for _ in range(50):
            if path.exists():
                break
            time.sleep(0.1)
        assert path.exists(), "the debounce timer never fired"
        assert json.loads(path.read_text(encoding="utf-8"))["VCB"] == {"v": 1}

    def test_concurrent_writers_under_coalescing_lose_nothing(self, lake_dir, monkeypatch):
        monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "30")
        lake = DiskDataLake()
        threads = [
            threading.Thread(target=lake.save_symbol_record, args=("conc.json", f"S{i:03d}", {"i": i}))
            for i in range(60)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()
        lake.flush()
        assert len(json.loads((lake_dir / "conc.json").read_text(encoding="utf-8"))) == 60
