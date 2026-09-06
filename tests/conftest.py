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

# Network tiering.
#
# This used to be a list of whole MODULES, which was far too coarse: 283 of the
# 317 tests it excluded run perfectly well offline, so they never ran in CI at
# all. That hid real regressions - test_orchestrator_scoring (whose own
# docstring says "No network access anywhere in this module") had been broken
# by a refactor for weeks, and five tests in test_adversarial_stress were
# failing on an unrelated contract change.
#
# Tiering is now per test. A test belongs here only if it was observed to need
# a live upstream; everything else runs in CI.
NETWORK_TEST_MODULES = {
    # Every test in these modules hits a live feed.
    "test_bctc_10y_annual_crawler",
    "test_fetchers",
    "test_vndirect_40_quarters",
}

#: Individual tests that need a live upstream, as "module::TestClass::test_name"
#: or "module::test_name". Grouped by what they reach for.
NETWORK_TESTS = {
    # Need a populated screener universe (TradingView scanner / TCBS) before
    # the backtest can generate any trades.
    "test_adversarial_m1_it2_empirical::TestDynamicBetaMoSScaling::test_extreme_mos_with_dynamic_beta_restricts_trades",
    "test_adversarial_m1_it2_empirical::TestZeroExitPremiumTakeProfit::test_zero_exit_premium_triggers_tp_in_screening_mode",
    "test_adversarial_m1_it2_empirical::TestZeroExitPremiumTakeProfit::test_zero_exit_premium_triggers_tp_in_valuation_mode",
    "test_e2e_fair_value_backtest::TestTier1FeatureCoverage::test_mode_1_valuation_only_execution",
    "test_e2e_fair_value_backtest::TestTier1FeatureCoverage::test_mode_2_screening_only_execution",
    "test_e2e_fair_value_backtest::TestTier2BoundaryAndCornerCases::test_safe_div_and_zero_division_resilience",
    "test_e2e_fair_value_backtest::TestTier2BoundaryAndCornerCases::test_unreachable_mos_zero_trades",
    "test_e2e_fair_value_backtest::TestTier4RealWorldAndAPIContracts::test_multi_year_simulation_vn30",
    "test_fair_value_backtest::TestFairValueBacktestModes::test_mode_2_pure_screening",
    "test_fair_value_backtest_stress::TestSingleStockUniverseStress::test_multiple_unknown_stocks",
    "test_fair_value_backtest_stress::TestSingleStockUniverseStress::test_single_stock_known",
    "test_fair_value_backtest_stress::TestSingleStockUniverseStress::test_single_stock_unknown_synthetic",
    "test_fair_value_backtest_stress::TestZeroTradeScenarioStress::test_impossible_mos_produces_zero_trades_gracefully",
    "test_institutional_valuation_integration::test_api_quant_institutional_run_endpoint",
    "test_institutional_valuation_integration::test_run_valuation_monte_carlo",
    "test_institutional_valuation_integration::test_run_valuation_parameter_sensitivity_hybrid",
    "test_m2_core_engine_api_hardening::TestUniverseIndexResolution::test_quant_screener_vn70_universe",
    "test_m2_core_engine_api_hardening::TestUniverseIndexResolution::test_quant_screener_vnmid_universe",
    "test_m2_core_engine_api_hardening::TestUniverseIndexResolution::test_trading_board_index_groups",
    # Call vnstock directly. These do not fail on a connection error - vnai's
    # own guardian raises RateLimitExceeded once the community tier's 60
    # requests/minute is spent - so in a full-suite run they fail depending on
    # how much quota earlier tests consumed, which is what made them look
    # order-dependent rather than network-dependent.
    "test_supercharged_ecosystem::test_family_and_ubo_power_clustering",
    "test_three_institutional_supercharges::test_stock_service_full_api_integration",
    # Reach company / market feeds directly.
    "test_global_and_events::test_market_wide_events_calendar",
    "test_supercharged_ecosystem::test_ecosystem_independent_stock_fallback",
    "test_supercharged_ecosystem::test_get_company_ecosystem_supercharged_payload",
    "test_three_institutional_supercharges::test_commodity_spread_dynamic_universe_discovery",
    "test_three_institutional_supercharges::test_commodity_spread_engine_cyclical_stocks",
    "test_three_institutional_supercharges::test_smart_money_flow_engine_strict_separation",
}


def _test_id(item) -> str:
    """"module::Class::test" for a method, "module::test" for a function."""
    module = item.module.__name__.rpartition(".")[2]
    parts = item.nodeid.split("::")[1:]
    return "::".join([module] + parts)


def pytest_collection_modifyitems(config, items):
    marker = pytest.mark.network
    for item in items:
        module = item.module.__name__.rpartition(".")[2]
        if module in NETWORK_TEST_MODULES or _test_id(item) in NETWORK_TESTS:
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


# ---------------------------------------------------------------------------
# Screener snapshot for forecast and export tests
# ---------------------------------------------------------------------------
# ThreeStatementEngine.build_forecast_from_screener reads
# data/screener_snapshot.json. Under the data-dir isolation above that file is
# absent, and the engine used to paper over it: a missing market cap defaulted
# to 10,000 (floored at 100bn) and revenue was backed out of it, so the export
# and forecast suites were exercising invented companies while appearing to
# test HPG, FPT and VCB. With that fabrication removed the engine refuses, so
# the tests need real-shaped inputs - which is what they should always have
# had, since none of them is testing where the numbers come from.
#
# Figures are plausible orders of magnitude in VND for each ticker; the point
# is that the forecast is driven by stated inputs rather than by the engine's
# imagination.
_SNAPSHOT_FIXTURES = {
    "HPG":  dict(revenue=1.40e14, market_cap=1.70e14, ps=1.21, gross_margin=13.0,
                 op_margin=9.0, net_margin=8.5, roe=12.0, de_ratio=0.65),
    "FPT":  dict(revenue=6.20e13, market_cap=1.90e14, ps=3.06, gross_margin=38.0,
                 op_margin=19.0, net_margin=15.0, roe=28.0, de_ratio=0.55),
    "VCB":  dict(revenue=6.80e13, market_cap=5.20e14, ps=7.65, gross_margin=55.0,
                 op_margin=48.0, net_margin=38.0, roe=21.0, de_ratio=0.90,
                 is_financial_sector=True),
    "MWG":  dict(revenue=1.35e14, market_cap=8.60e13, ps=0.64, gross_margin=19.0,
                 op_margin=3.0, net_margin=2.0, roe=9.0, de_ratio=1.10),
    "NVL":  dict(revenue=1.10e13, market_cap=2.30e13, ps=2.09, gross_margin=28.0,
                 op_margin=12.0, net_margin=5.0, roe=3.0, de_ratio=2.10),
    "VIC":  dict(revenue=1.60e14, market_cap=1.60e14, ps=1.00, gross_margin=22.0,
                 op_margin=8.0, net_margin=2.5, roe=4.0, de_ratio=1.80),
    "VNM":  dict(revenue=6.10e13, market_cap=1.40e14, ps=2.30, gross_margin=41.0,
                 op_margin=19.0, net_margin=16.0, roe=25.0, de_ratio=0.35),
}

#: Anything else in VN30 gets a neutral mid-cap profile, so the "all 30
#: constituents balance" checks still exercise 30 distinct forecasts.
_SNAPSHOT_DEFAULT = dict(revenue=3.00e13, market_cap=6.00e13, ps=2.00,
                         gross_margin=25.0, op_margin=12.0, net_margin=9.0,
                         roe=15.0, de_ratio=0.80)


#: Filler tickers. get_quant_screener() rejects a snapshot with 50 or fewer
#: stocks and falls back to a live sync, so the API tests that read through it
#: were never exercising this fixture at all - they were asserting against
#: whatever a network call happened to return, and against nothing when the
#: network was unavailable. Padding past the gate makes them hermetic.
_SNAPSHOT_PADDING = [
    "AAA", "ACL", "ANV", "ASM", "BCG", "BMP", "BWE", "CII", "CMG", "CTD",
    "DBC", "DCM", "DGC", "DGW", "DHC", "DPM", "DXG", "FRT", "GEX", "HAH",
    "HCM", "HDG", "HSG", "IDC", "IJC", "KBC", "KDH", "NKG", "NLG", "PAN",
    "PC1", "PET", "PNJ", "PVD", "PVT", "REE", "SCS", "SZC", "TCH", "VCI",
]


def _snapshot_record(symbol: str) -> dict:
    """One screener record shaped the way the real sync writes them.

    The engine refuses to value a record whose drivers are flagged as
    reconstructed from market cap, so a fixture that carries only ratios
    produces nothing and the test measures the refusal rather than the code
    under test. These records therefore carry the absolute statement lines and
    a tier for each, exactly as normalize_stock_data() publishes them.
    """
    payload = dict(_SNAPSHOT_FIXTURES.get(symbol, _SNAPSHOT_DEFAULT))
    payload["symbol"] = symbol
    payload.setdefault("name", f"CTCP {symbol}")

    market_cap = float(payload["market_cap"])
    revenue = float(payload["revenue"])
    price = 25_000.0
    shares_out = market_cap / price
    equity = market_cap / 1.6
    net_income = revenue * (float(payload["net_margin"]) / 100.0)
    ebit = revenue * (float(payload["op_margin"]) / 100.0)

    payload.update(
        price=price,
        shares_out=shares_out,
        market_cap_vnd=market_cap,
        eps=net_income / shares_out,
        total_assets=equity * 1.9,
        total_liabilities=equity * 0.9,
        equity=equity,
        debt=equity * float(payload["de_ratio"]),
        cash=equity * 0.12,
        net_income=net_income,
        ebit=ebit,
        ebitda=ebit * 1.25,
        cfo=net_income * 1.1,
        capex=revenue * 0.05,
    )

    # Tier 3 = vendor reported. These are stated inputs, not reconstructions
    # from the price being judged, so the gate should let them through.
    provenance = {key: 3 for key in payload if key not in ("symbol", "name")}
    payload["field_provenance"] = provenance
    payload["is_imputed"] = {key: False for key in provenance}
    payload["percentiles"] = {"composite": 50.0}
    payload["_metadata"] = {
        "is_imputed": payload["is_imputed"],
        "field_provenance": provenance,
        "provenance_tier": "Tier 3 (Reported / Audited)",
        "is_valid_fundamental": True,
        "is_real_data": True,
        "data_quality_score": 90.0,
        "sources_used": ["fixture"],
    }
    return payload


@pytest.fixture
def screener_snapshot(tmp_path, monkeypatch):
    """Writes a screener snapshot into the isolated data dir and returns it."""
    import json
    import os

    from services.stock_service import VN30_SYMBOLS

    stocks = {}
    for symbol in set(list(_SNAPSHOT_FIXTURES) + list(VN30_SYMBOLS) + _SNAPSHOT_PADDING):
        stocks[symbol] = _snapshot_record(symbol)

    data_dir = os.environ.get("DATA_LOCAL_DIR") or str(tmp_path)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "screener_snapshot.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"stocks": stocks}, handle)

    # compute_quant_percentile_universe() memoises the derived universe for an
    # hour in a process-wide cache. Without this, the first test in a session
    # to reach that code path decides what every later test sees: one that ran
    # before any snapshot existed poisons the cache with the result of a failed
    # live sync, and tests that pass alone fail in a full run. Writing a new
    # snapshot has to invalidate what was derived from the old one.
    from services.stock_service import cache
    cache.invalidate("quant_percentile_universe_v2")

    return path
