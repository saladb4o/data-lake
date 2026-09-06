"""Shared pytest configuration.

Splits the suite into two tiers:

* **Deterministic tests** - pure logic over fixtures/synthetic inputs. These run
  offline, are safe to gate CI on, and are the default in `ci.yml`.
* **Network tests** - integration suites that hit live upstreams (vnstock,
  VNDirect, TradingView, RSS feeds). They fail on a sandboxed runner and are
  rate-limited to 60 requests/minute on the community vnstock tier, so they are
  marked `network` and deselected in CI with `-m "not network"`.

Run everything locally with `pytest`; run only the CI gate with
`pytest -m "not network"`; run only the integration tier with `pytest -m network`.
"""

import pytest

# Modules whose tests reach live upstreams. Listed centrally so the individual
# test files stay untouched. Keep sorted.
NETWORK_TEST_MODULES = {
    "test_adversarial_m1_it2_empirical",
    "test_adversarial_stress",
    "test_bctc_10y_annual_crawler",
    "test_benchmark_service",
    "test_e2e_fair_value_backtest",
    "test_fair_value_backtest",
    "test_fair_value_backtest_stress",
    "test_fetchers",
    "test_global_and_events",
    "test_institutional_valuation_integration",
    "test_m2_core_engine_api_hardening",
    "test_normalizer",
    "test_orchestrator_scoring",
    "test_sector_index_service",
    "test_supercharged_ecosystem",
    "test_three_institutional_supercharges",
    "test_universe_cache",
    "test_vndirect_40_quarters",
}


def pytest_collection_modifyitems(config, items):
    marker = pytest.mark.network
    for item in items:
        if item.module.__name__.rpartition(".")[2] in NETWORK_TEST_MODULES:
            item.add_marker(marker)


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path_factory, monkeypatch, request):
    """Keeps tests out of the repository's real data/ directory.

    resolve_data_file() falls back to the checkout's data/ dir, so a test that
    wrote a lake left a file there - which later runs then resolved to,
    making the suite order-dependent and overwriting real data on a
    developer's machine.
    """
    if "no_data_isolation" in request.keywords:
        yield
        return
    isolated = tmp_path_factory.mktemp("data_local")
    monkeypatch.setenv("DATA_LOCAL_DIR", str(isolated))
    yield


@pytest.fixture(scope="session", autouse=True)
def _fail_on_repo_data_leak():
    """Fails the run if tests wrote lake files into the checkout."""
    import pathlib
    data_dir = pathlib.Path(__file__).resolve().parent.parent / "data"
    before = {p.name for p in data_dir.glob("*.json")} if data_dir.is_dir() else set()
    yield
    after = {p.name for p in data_dir.glob("*.json")} if data_dir.is_dir() else set()
    leaked = sorted(after - before)
    assert not leaked, f"tests leaked lake files into the repo's data/: {leaked}"
