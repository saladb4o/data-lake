"""The universe sync must refuse rather than publish an empty snapshot.

sync_unified_screener_universe() writes screener_snapshot.json
unconditionally. When the master list fails to load, the script used to
print "Loaded 0 valid equity symbols" and carry on, replacing a good
1,500-symbol snapshot with an empty one - which nearly destroyed a real
lake once, and did fail a CI run with "refusing to publish a 0-symbol
snapshot" only because a separate guard caught it downstream.

The refusal belongs in the script, before anything is written.
"""

import pytest

import scripts.sync_unified_market_data as sync_script


@pytest.fixture(autouse=True)
def never_touch_the_network(monkeypatch):
    """No test here may reach a vendor or write a snapshot."""
    def _explode(*args, **kwargs):
        raise AssertionError("the sync ran despite an unusable master list")

    monkeypatch.setattr(sync_script, "sync_unified_screener_universe", _explode)


def _no_symbols(monkeypatch, count: int = 0):
    master = {
        f"S{i:04d}": {"exchange": "HOSE", "sector_code": "VNIND",
                      "sector_name": "Cong Nghiep", "name": f"S{i:04d}"}
        for i in range(count)
    }
    monkeypatch.setattr(sync_script, "load_local_symbols", lambda: master)


def test_an_empty_master_list_refuses(monkeypatch, capsys):
    _no_symbols(monkeypatch)
    monkeypatch.setattr(
        sync_script, "load_local_symbols", lambda: {}
    )
    # The listing rebuild is attempted; make it a no-op failure.
    import services.stock_service as ss
    monkeypatch.setattr(
        ss, "sync_universe_from_vnstock",
        lambda force=False: (_ for _ in ()).throw(RuntimeError("no network")),
    )

    assert sync_script.main() == 1
    assert "refusing to sync" in capsys.readouterr().out


def test_a_thin_master_list_refuses(monkeypatch):
    """One symbol short of plausible is still a broken load, not a universe."""
    import services.stock_service as ss
    monkeypatch.setattr(ss, "sync_universe_from_vnstock", lambda force=False: {})

    calls = {"n": 0}

    def _load():
        calls["n"] += 1
        return {
            f"S{i:04d}": {"exchange": "HOSE"}
            for i in range(sync_script.MIN_PLAUSIBLE_UNIVERSE - 1)
        }

    monkeypatch.setattr(sync_script, "load_local_symbols", _load)
    assert sync_script.main() == 1
    assert calls["n"] == 2, "the script must retry after rebuilding the listing"


def test_a_plausible_universe_proceeds(monkeypatch):
    """The guard must not stand in the way of a real run."""
    master = {
        f"S{i:04d}": {"exchange": "HOSE", "sector_code": "VNIND",
                      "sector_name": "Cong Nghiep", "name": f"S{i:04d}"}
        for i in range(sync_script.MIN_PLAUSIBLE_UNIVERSE)
    }
    monkeypatch.setattr(sync_script, "load_local_symbols", lambda: master)
    monkeypatch.setattr(
        sync_script, "sync_unified_screener_universe",
        lambda symbols_map: {"stocks": {}},
    )
    assert sync_script.main() == 0


def test_the_master_list_goes_through_the_resolver(tmp_path, monkeypatch):
    """A hardcoded PROJECT_ROOT/data/... could not see a redirected lake."""
    import json

    monkeypatch.setenv("DATA_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(tmp_path / "no-such-drive"))
    (tmp_path / "all_symbols.json").write_text(
        json.dumps([
            {"symbol": "HPG", "type": "STOCK", "exchange": "HOSE",
             "organ_name": "Hoa Phat", "industry": "Vat lieu"},
        ]),
        encoding="utf-8",
    )

    master = sync_script.load_local_symbols()
    assert "HPG" in master, "the resolver-provided master list was not read"
