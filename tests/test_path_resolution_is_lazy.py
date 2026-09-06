"""Data paths must resolve per call, not at import.

Five module constants were computed at import time, freezing before anything
could configure the environment: a Google Drive mount appearing after startup
was never seen, DATA_LOCAL_DIR could not redirect them, and one of them ran
os.makedirs as an import side effect.
"""

import importlib
import os

import pytest

import services.bctc_batch_processor as bctc
import services.stock_service as ss
import services.unified_data_service as uds


@pytest.fixture(autouse=True)
def no_drive_mount(tmp_path, monkeypatch):
    """Isolate every test in this module from a real Google Drive mount.

    resolve_data_file() falls back to a hardcoded "G:/My Drive/vnstock_data"
    when GOOGLE_DRIVE_DATA_DIR is unset, and prefers it when it exists. On a
    developer machine with the Drive actually mounted, these tests were
    asserting against the real data lake instead of tmp_path and failing for
    a reason that had nothing to do with what they test. Deleting the
    variable is not enough - it has to point somewhere that does not exist.
    """
    monkeypatch.setenv("GOOGLE_DRIVE_DATA_DIR", str(tmp_path / "no-such-drive"))


@pytest.mark.parametrize(
    "resolver",
    [
        lambda: ss.quant_snapshot_file(),
        lambda: uds.screener_snapshot_file(),
        lambda: uds.historical_prices_file(),
        lambda: uds.data_dir(),
        lambda: bctc.pdf_lake_dir(),
    ],
)
def test_resolver_follows_the_environment_after_import(resolver, tmp_path, monkeypatch):
    """Changing DATA_LOCAL_DIR after import must change where paths point."""
    first = tmp_path / "one"
    monkeypatch.setenv("DATA_LOCAL_DIR", str(first))
    assert str(first) in resolver()

    second = tmp_path / "two"
    monkeypatch.setenv("DATA_LOCAL_DIR", str(second))
    assert str(second) in resolver(), "path was frozen at import time"


def test_importing_does_not_create_directories(tmp_path, monkeypatch):
    """Importing a module must not touch the filesystem."""
    target = tmp_path / "untouched"
    monkeypatch.setenv("DATA_LOCAL_DIR", str(target))
    importlib.reload(bctc)
    assert not target.exists(), "import created directories as a side effect"


def test_old_constants_are_gone():
    """Guards against a constant creeping back in."""
    for module, name in (
        (ss, "QUANT_SNAPSHOT_FILE"),
        (uds, "SCREENER_SNAPSHOT_FILE"),
        (uds, "HISTORICAL_PRICES_FILE"),
        (uds, "DATA_DIR"),
        (bctc, "PDF_LAKE_DIR"),
    ):
        assert not isinstance(getattr(module, name, None), str), (
            f"{module.__name__}.{name} is an import-time constant again"
        )


def test_server_write_paths_follow_the_environment(tmp_path, monkeypatch):
    """server.py wrote three files at a hardcoded relative "data/...".

    That ignored DATA_LOCAL_DIR, so a test run persisted the RRG cache and
    the alert rules into the checkout instead of its isolated directory -
    which the leak guard in conftest correctly failed the run on. Same
    defect as the five lake paths above, including one that was an
    import-time constant.
    """
    import server

    first = tmp_path / "one"
    monkeypatch.setenv("DATA_LOCAL_DIR", str(first))
    assert str(first) in server._rrg_disk_path()
    assert str(first) in server.alert_rules_path()

    second = tmp_path / "two"
    monkeypatch.setenv("DATA_LOCAL_DIR", str(second))
    assert str(second) in server._rrg_disk_path(), "path was frozen"
    assert str(second) in server.alert_rules_path(), "path was frozen"


def test_server_alert_rules_path_is_not_a_constant():
    import server

    assert not isinstance(getattr(server, "ALERT_RULES_PATH", None), str), (
        "server.ALERT_RULES_PATH is an import-time constant again"
    )


def test_valuation_engine_uses_the_shared_resolver(tmp_path, monkeypatch):
    """It read data/screener_snapshot.json directly, bypassing the resolver."""
    import json

    from services.valuation_engine import ValuationEngine

    monkeypatch.setenv("DATA_LOCAL_DIR", str(tmp_path))
    monkeypatch.delenv("GOOGLE_DRIVE_DATA_DIR", raising=False)
    (tmp_path / "screener_snapshot.json").write_text(
        json.dumps({"stocks": {"XYZ": {"price": 33000, "eps": 2500, "bvps": 18000}}}),
        encoding="utf-8",
    )

    res = ValuationEngine().get_comprehensive_valuation("XYZ")
    assert res.current_price == 33000, "the engine did not read the resolved snapshot"
