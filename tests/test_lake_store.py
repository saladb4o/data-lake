"""Tests for the SQLite working store and its JSON interchange."""

import json
import os
import threading

import pytest

from services.lake_store import SQLiteLakeStore, _resolve_db_path


@pytest.fixture
def store(tmp_path):
    s = SQLiteLakeStore(db_path=str(tmp_path / "lake.db"))
    yield s
    s.close()


class TestRoundTrip:
    def test_put_and_get_one_symbol(self, store):
        store.put("prices", "vcb", {"close": 90000})
        assert store.get("prices", "VCB") == {"close": 90000}
        assert store.get("prices", "vcb") == {"close": 90000}, "symbols are normalised"

    def test_get_missing_symbol_returns_none(self, store):
        assert store.get("prices", "NOPE") is None

    def test_put_overwrites(self, store):
        store.put("prices", "VCB", {"close": 1})
        store.put("prices", "VCB", {"close": 2})
        assert store.get("prices", "VCB") == {"close": 2}
        assert store.count("prices") == 1

    def test_lakes_are_isolated(self, store):
        store.put("prices", "VCB", {"a": 1})
        store.put("statements", "VCB", {"b": 2})
        assert store.get("prices", "VCB") == {"a": 1}
        assert store.get("statements", "VCB") == {"b": 2}
        assert sorted(store.lakes()) == ["prices", "statements"]

    def test_get_all_matches_the_json_shape(self, store):
        store.put_many("prices", {"VCB": {"a": 1}, "TCB": {"a": 2}})
        assert store.get_all("prices") == {"VCB": {"a": 1}, "TCB": {"a": 2}}

    def test_delete(self, store):
        store.put("prices", "VCB", {"a": 1})
        store.delete("prices", "VCB")
        assert store.get("prices", "VCB") is None

    def test_unicode_survives(self, store):
        store.put("news", "VCB", {"title": "Vietcombank báo lãi quý 3 tăng trưởng"})
        assert "tăng trưởng" in store.get("news", "VCB")["title"]


class TestJsonInterchange:
    """JSON stays the format that leaves the machine."""

    def test_import_then_export_is_lossless(self, store, tmp_path):
        original = {
            "VCB": {"close": 90000, "name": "Ngân hàng Ngoại thương"},
            "TCB": {"close": 24000, "bars": [{"t": 1, "c": 2.5}]},
        }
        src = tmp_path / "prices.json"
        src.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

        assert store.import_json("prices", str(src)) == 2

        out = tmp_path / "out.json"
        assert store.export_json("prices", str(out)) == 2
        assert json.loads(out.read_text(encoding="utf-8")) == original

    def test_export_is_atomic(self, store, tmp_path):
        store.put("prices", "VCB", {"a": 1})
        out = tmp_path / "prices.json"
        store.export_json("prices", str(out))
        leftovers = [p for p in os.listdir(tmp_path) if ".tmp_" in p]
        assert leftovers == [], f"temp files left behind: {leftovers}"

    def test_import_rejects_a_non_object_document(self, store, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError, match="symbol-keyed"):
            store.import_json("prices", str(bad))


class TestDrivePlacementGuard:
    """SQLite must never live on the cloud-sync folder."""

    def test_db_is_relocated_out_of_the_drive_directory(self, tmp_path, monkeypatch):
        gdrive = tmp_path / "gdrive"
        gdrive.mkdir()
        monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(gdrive))

        resolved = _resolve_db_path(str(gdrive / "lake.db"))
        assert not resolved.startswith(str(gdrive)), (
            "database was placed inside the sync directory"
        )
        assert resolved.endswith("lake.db")

    def test_a_local_path_is_left_alone(self, tmp_path, monkeypatch):
        gdrive = tmp_path / "gdrive"
        gdrive.mkdir()
        monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(gdrive))
        local = tmp_path / "local" / "lake.db"
        assert _resolve_db_path(str(local)) == str(local)


class TestConcurrency:
    def test_parallel_writers_lose_nothing(self, store):
        def worker(start):
            for i in range(start, start + 25):
                store.put("prices", f"S{i:04d}", {"i": i})

        threads = [threading.Thread(target=worker, args=(n * 25,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
            assert not t.is_alive()
        assert store.count("prices") == 200

    def test_a_reader_works_while_writers_run(self, store):
        store.put("prices", "VCB", {"a": 1})
        stop = threading.Event()
        errors = []

        def writer():
            i = 0
            while not stop.is_set():
                store.put("prices", f"W{i:04d}", {"i": i})
                i += 1

        def reader():
            try:
                for _ in range(50):
                    assert store.get("prices", "VCB") == {"a": 1}
            except Exception as exc:
                errors.append(exc)

        w = threading.Thread(target=writer, daemon=True)
        w.start()
        r = threading.Thread(target=reader)
        r.start()
        r.join(timeout=60)
        stop.set()
        w.join(timeout=10)
        assert not errors, f"reads failed during writes: {errors[0]!r}"


class TestWrappedLakeShapes:
    """Some lakes wrap their symbols in a container key.

    historical_prices.json is read both ways in stock_service
    (`lake.get(symbol) or lake.get("symbols", {}).get(symbol)`), and
    screener_snapshot.json nests under "stocks". Treating the wrapper as a
    symbol produced rows named SYMBOLS and UPDATED_AT.
    """

    @pytest.mark.parametrize("container", ["symbols", "stocks", "records", "data"])
    def test_wrapped_document_round_trips_unchanged(self, store, tmp_path, container):
        original = {
            container: {"VCB": {"c": 1}, "TCB": {"c": 2}},
            "updated_at": "2026-01-01",
            "total_symbols": 2,
        }
        src = tmp_path / f"{container}.json"
        src.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

        assert store.import_json(container, str(src)) == 2, "should import 2 symbols, not the wrapper"
        assert store.count(container) == 2
        assert store.get(container, "VCB") == {"c": 1}

        out = tmp_path / "out.json"
        store.export_json(container, str(out))
        assert json.loads(out.read_text(encoding="utf-8")) == original, (
            "export must restore the original document shape, sidecar keys included"
        )

    def test_flat_document_is_untouched(self, store, tmp_path):
        original = {"VCB": {"c": 1}, "TCB": {"c": 2}}
        src = tmp_path / "flat.json"
        src.write_text(json.dumps(original), encoding="utf-8")
        store.import_json("flat", str(src))

        out = tmp_path / "out.json"
        store.export_json("flat", str(out))
        assert json.loads(out.read_text(encoding="utf-8")) == original

    def test_wrapper_is_not_mistaken_for_a_symbol(self, store, tmp_path):
        src = tmp_path / "hp.json"
        src.write_text(json.dumps({"symbols": {f"S{i:03d}": {"c": i} for i in range(50)},
                                   "updated_at": "x"}), encoding="utf-8")
        store.import_json("hp", str(src))
        assert "SYMBOLS" not in set(store.symbols("hp"))
        assert "UPDATED_AT" not in set(store.symbols("hp"))
        assert store.count("hp") == 50
