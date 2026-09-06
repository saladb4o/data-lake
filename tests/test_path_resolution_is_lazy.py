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
