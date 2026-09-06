"""
=============================================================================
MILESTONE M2 VERIFICATION SUITE: CORE ENGINE, UNIVERSE RESOLUTION & API HARDENING
=============================================================================
Tests for:
1. Universe Index Filtering (VN30, VN70, VNMID, VN100) in stock_service & fair_value_backtest_service.
2. Route Aliases (/api/backtest/fair-value/run, /api/backtest/fair-value/presets,
   /api/valuation/matrix/{symbol}, /api/valuation/matrix?symbol=...) in server.py.
3. FastAPI Lifespan Modernization (clean context manager startup/shutdown, no deprecation warnings).
"""

import pytest
from fastapi.testclient import TestClient

from server import app
from services.stock_service import (
    get_quant_screener,
    get_trading_board,
    VN30_SYMBOLS,
    VN70_SYMBOLS,
    VNMID_SYMBOLS,
    VN100_SYMBOLS,
    INDEX_UNIVERSE_MAP,
)
from services.fair_value_backtest_service import (
    fv_backtest_service,
    BacktestMode,
)

# These tests exercise the mechanics of the backtest - trade generation,
# metrics, edge cases - not where its fundamentals come from. The default is
# now fundamentals_mode="point_in_time", which values only symbol-quarters
# with a published filing and so produces no trades until
# data/historical_fundamentals.json is populated. Each run_backtest call below
# pins "snapshot_projected" so these keep testing what they were written to
# test; the point-in-time path is covered by
# tests/test_point_in_time_fundamentals.py.
from services.fair_value_backtest_service import FundamentalsMode as _FundamentalsMode

_SNAPSHOT = _FundamentalsMode.SNAPSHOT_PROJECTED



@pytest.fixture(scope="module")
def api_client():
    """TestClient instance for FastAPI route testing."""
    with TestClient(app) as client:
        yield client


# =============================================================================
# 1. UNIVERSE INDEX RESOLUTION TESTS
# =============================================================================

class TestUniverseIndexResolution:
    """Verifies constituent resolution for VN30, VN70, VNMID, and VN100."""

    def test_universe_symbol_lists_integrity(self):
        """Checks size and overlap of defined universe constituents."""
        assert len(VN30_SYMBOLS) == 30
        assert len(VN70_SYMBOLS) == 70
        assert len(VNMID_SYMBOLS) == 70
        assert len(VN100_SYMBOLS) == 100

        # VNMID is identical to VN70
        assert set(VNMID_SYMBOLS) == set(VN70_SYMBOLS)

        # VN30 and VN70 constituents are disjoint HOSE subsets
        assert len(set(VN30_SYMBOLS).intersection(set(VN70_SYMBOLS))) == 0

        # VN100 is exact union of VN30 and VN70
        assert set(VN100_SYMBOLS) == set(VN30_SYMBOLS).union(set(VN70_SYMBOLS))

        # Index universe map contains all 4 keys
        assert "VN30" in INDEX_UNIVERSE_MAP
        assert "VN70" in INDEX_UNIVERSE_MAP
        assert "VNMID" in INDEX_UNIVERSE_MAP
        assert "VN100" in INDEX_UNIVERSE_MAP

    def test_quant_screener_vn30_universe(self):
        """Verifies get_quant_screener filters to VN30 constituents only."""
        res = get_quant_screener(exchange="VN30", limit=500)
        assert res["total"] > 0
        stocks = res["results"]
        assert len(stocks) > 0
        vn30_set = set(VN30_SYMBOLS)

        for s in stocks:
            sym = s.get("symbol")
            assert sym in vn30_set, f"Stock {sym} returned in VN30 screener but not in VN30_SYMBOLS"
            # Exchange should remain HOSE
            assert s.get("exchange") == "HOSE"

    def test_quant_screener_vn70_universe(self):
        """Verifies get_quant_screener filters to VN70 constituents only."""
        res = get_quant_screener(exchange="VN70", limit=500)
        assert res["total"] > 0
        stocks = res["results"]
        assert len(stocks) > 0
        vn70_set = set(VN70_SYMBOLS)
        vn30_set = set(VN30_SYMBOLS)

        for s in stocks:
            sym = s.get("symbol")
            assert sym in vn70_set, f"Stock {sym} returned in VN70 screener but not in VN70_SYMBOLS"
            assert sym not in vn30_set, f"VN30 stock {sym} should not appear in VN70 universe"

    def test_quant_screener_vnmid_universe(self):
        """Verifies get_quant_screener filters to VNMID constituents only."""
        res = get_quant_screener(exchange="VNMID", limit=500)
        assert res["total"] > 0
        stocks = res["results"]
        assert len(stocks) > 0
        vnmid_set = set(VNMID_SYMBOLS)

        for s in stocks:
            sym = s.get("symbol")
            assert sym in vnmid_set, f"Stock {sym} returned in VNMID screener but not in VNMID_SYMBOLS"

    def test_quant_screener_vn100_universe(self):
        """Verifies get_quant_screener filters to VN100 constituents only."""
        res = get_quant_screener(exchange="VN100", limit=500)
        assert res["total"] > 0
        stocks = res["results"]
        assert len(stocks) > 0
        vn100_set = set(VN100_SYMBOLS)

        for s in stocks:
            sym = s.get("symbol")
            assert sym in vn100_set, f"Stock {sym} returned in VN100 screener but not in VN100_SYMBOLS"

    def test_quant_screener_case_insensitivity_and_combinations(self):
        """Verifies case insensitivity (vn30, vnmid) and comma-separated tokens."""
        res_lower = get_quant_screener(exchange="vn30", limit=500)
        res_upper = get_quant_screener(exchange="VN30", limit=500)
        assert res_lower["total"] == res_upper["total"]

        # Combined index and exchange: VN30 + HNX
        res_comb = get_quant_screener(exchange="VN30,HNX", limit=500)
        assert res_comb["total"] >= res_upper["total"]
        for s in res_comb["results"]:
            sym = s.get("symbol")
            ex = s.get("exchange")
            assert (sym in set(VN30_SYMBOLS)) or (ex == "HNX")

    def test_trading_board_index_groups(self):
        """Verifies get_trading_board resolves VN30, VN70, VNMID, VN100 groups."""
        board_vn30 = get_trading_board(group="VN30")
        assert len(board_vn30) <= 30

        board_vn70 = get_trading_board(group="VN70")
        assert len(board_vn70) <= 70

        board_vnmid = get_trading_board(group="VNMID")
        assert len(board_vnmid) <= 70

        board_vn100 = get_trading_board(group="VN100")
        assert len(board_vn100) <= 100


# =============================================================================
# 2. FAIR VALUE BACKTEST ENGINE UNIVERSE INTEGRATION
# =============================================================================

class TestFairValueBacktestUniverseIntegration:
    """Verifies universe resolution inside fair_value_backtest_service."""

    def test_presets_catalog_includes_all_universes(self):
        """Presets catalog includes VN30, VN70, VNMID, VN100, HOSE, HNX, UPCOM, ALL."""
        presets = fv_backtest_service.get_presets()
        universes = presets.get("universes", [])
        assert "VN30" in universes
        assert "VN70" in universes
        assert "VNMID" in universes
        assert "VN100" in universes
        assert "ALL" in universes

    @pytest.mark.parametrize("universe", ["VN30", "VN70", "VNMID", "VN100"])
    def test_run_backtest_across_all_index_universes(self, universe):
        """Executes full backtest simulation cleanly across each index universe."""
        res = fv_backtest_service.run_backtest(
            mode=BacktestMode.VALUATION_ONLY,
            valuation_model_id="composite_fair_value",
            exchange=universe,
            start_year=2024,
            end_year=2025,
            top_k=5,
            fundamentals_mode=_SNAPSHOT,
        )
        assert res is not None
        assert res.mode == BacktestMode.VALUATION_ONLY
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) > 0


# =============================================================================
# 3. API ROUTE ALIASES & CONTRACT HARDENING
# =============================================================================

class TestAPIRouteAliases:
    """Verifies hyphenated and matrix route aliases in server.py."""

    def test_backtest_presets_aliases(self, api_client):
        """Both /api/backtest/fair_value/presets and /api/backtest/fair-value/presets work identically."""
        r1 = api_client.get("/api/backtest/fair_value/presets")
        r2 = api_client.get("/api/backtest/fair-value/presets")

        assert r1.status_code == 200
        assert r2.status_code == 200

        data1 = r1.json()["data"]
        data2 = r2.json()["data"]
        assert data1["universes"] == data2["universes"]
        assert "VN100" in data2["universes"]

    def test_backtest_run_aliases_get_and_post(self, api_client):
        """Hyphenated /api/backtest/fair-value/run works for GET and POST."""
        # GET request
        r_get = api_client.get(
            "/api/backtest/fair-value/run",
            params={
                "mode": "valuation_only",
                "exchange": "VN30",
                "start_year": 2024,
                "end_year": 2025,
                "top_k": 3,
            }
        )
        assert r_get.status_code == 200
        data_get = r_get.json()
        assert data_get["status"] == "success"
        assert "metrics" in data_get["data"]

        # POST request
        r_post = api_client.post(
            "/api/backtest/fair-value/run",
            params={
                "mode": "valuation_only",
                "exchange": "VN30",
                "start_year": 2024,
                "end_year": 2025,
                "top_k": 3,
            }
        )
        assert r_post.status_code == 200
        data_post = r_post.json()
        assert data_post["status"] == "success"
        assert "metrics" in data_post["data"]

    def test_valuation_matrix_path_parameter_alias(self, api_client):
        """/api/valuation/matrix/{symbol} returns comprehensive valuation data."""
        r_comp = api_client.get("/api/valuation/comprehensive/HPG")
        r_mat = api_client.get("/api/valuation/matrix/HPG")

        assert r_comp.status_code == 200
        assert r_mat.status_code == 200

        data_comp = r_comp.json()["data"]
        data_mat = r_mat.json()["data"]

        assert data_mat["symbol"] == "HPG"
        assert data_mat["composite_fair_value"] == data_comp["composite_fair_value"]
        assert len(data_mat["models"]) == len(data_comp["models"])

    def test_valuation_matrix_query_parameter_alias(self, api_client):
        """/api/valuation/matrix?symbol=HPG returns comprehensive valuation data."""
        r_query = api_client.get("/api/valuation/matrix", params={"symbol": "HPG"})
        assert r_query.status_code == 200
        data_query = r_query.json()["data"]
        assert data_query["symbol"] == "HPG"
        assert "composite_fair_value" in data_query

        # Test missing symbol returns 400
        r_missing = api_client.get("/api/valuation/matrix")
        assert r_missing.status_code == 400
        assert r_missing.json()["status"] == "error"
