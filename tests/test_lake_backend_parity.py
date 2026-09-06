"""The JSON and SQLite backends must be interchangeable.

DATA_LAKE_BACKEND only makes sense as a flag if flipping it changes nothing an
observer can see: same reads, same JSON file on disk for merge_shards.py, the
crawler workflows and the Colab notebooks.
"""

import json

import pytest

from services.stock_service import DiskDataLake


@pytest.fixture(params=["json", "sqlite"])
def backend(request, tmp_path, monkeypatch):
    # The lake dir and the database must be separate: a DB placed inside the
    # sync directory is relocated by the guard, which would otherwise land it
    # in the repo's real data/ dir and leak state between tests.
    lake_dir = tmp_path / "gdrive"
    lake_dir.mkdir()
    monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(lake_dir))
    monkeypatch.setenv("DATA_LAKE_BACKEND", request.param)
    monkeypatch.setenv("DATA_LAKE_DB_PATH", str(tmp_path / "db" / "lake.db"))
    monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "30")
    return request.param


@pytest.fixture
def lake_dir(tmp_path):
    return tmp_path / "gdrive"


def test_write_then_read_is_identical(backend, tmp_path):
    lake = DiskDataLake()
    lake.save_symbol_record("prices.json", "VCB", {"close": 90000})
    lake.save_symbol_record("prices.json", "TCB", {"close": 24000})

    assert lake.read_json("prices.json") == {
        "VCB": {"close": 90000},
        "TCB": {"close": 24000},
    }


def test_flush_produces_the_json_file_downstream_tools_read(backend, lake_dir):
    lake = DiskDataLake()
    lake.save_symbol_record("prices.json", "VCB", {"close": 90000, "name": "Ngân hàng"})
    lake.flush()

    path = lake_dir / "prices.json"
    assert path.exists(), f"[{backend}] no JSON file was produced"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "VCB": {"close": 90000, "name": "Ngân hàng"}
    }


def test_updates_overwrite_in_both_backends(backend):
    lake = DiskDataLake()
    lake.save_symbol_record("prices.json", "VCB", {"close": 1})
    lake.save_symbol_record("prices.json", "VCB", {"close": 2})
    assert lake.read_json("prices.json") == {"VCB": {"close": 2}}


def test_unknown_backend_value_falls_back_to_json(tmp_path, monkeypatch):
    (tmp_path / "gdrive").mkdir()
    monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(tmp_path / "gdrive"))
    monkeypatch.setenv("DATA_LAKE_BACKEND", "postgres")
    monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "0")
    lake = DiskDataLake()
    lake.save_symbol_record("prices.json", "VCB", {"close": 1})
    assert json.loads((tmp_path / "gdrive" / "prices.json").read_text(encoding="utf-8"))["VCB"]["close"] == 1


def test_sqlite_failure_falls_back_to_json_rather_than_losing_the_write(tmp_path, monkeypatch):
    """A broken database must not silently drop data."""
    (tmp_path / "gdrive").mkdir()
    monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(tmp_path / "gdrive"))
    monkeypatch.setenv("DATA_LAKE_BACKEND", "sqlite")
    monkeypatch.setenv("DATA_LAKE_FLUSH_INTERVAL_SECONDS", "0")

    lake = DiskDataLake()

    class Broken:
        def put(self, *a, **k):
            raise RuntimeError("disk I/O error")

        def get_all(self, *a, **k):
            raise RuntimeError("disk I/O error")

    lake._store = Broken()
    lake.save_symbol_record("prices.json", "VCB", {"close": 90000})

    on_disk = json.loads((tmp_path / "gdrive" / "prices.json").read_text(encoding="utf-8"))
    assert on_disk == {"VCB": {"close": 90000}}, "the write was lost when SQLite failed"
