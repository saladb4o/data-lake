import pytest
from services.institutional_backtest_service import (
    run_bar_by_bar_backtest,
    run_parameter_sensitivity,
    run_walk_forward_analysis,
    run_monte_carlo_stress_test,
    VALUATION_STRATEGY_CATALOG
)
from services.valuation_engine import ValuationEngine
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

def test_valuation_strategies_catalog_present():
    assert "val_composite_fair_value" in VALUATION_STRATEGY_CATALOG
    assert "val_dcf_2stage_mckinsey" in VALUATION_STRATEGY_CATALOG
    assert "hybrid_garp_composite" in VALUATION_STRATEGY_CATALOG


def test_run_institutional_mode1_pure_factor():
    res = run_bar_by_bar_backtest(
        symbol="VN30",
        strategy_type="peter_lynch_garp",
        backtest_mode="factor",
        time_horizon_years=2,
        top_k=5
    )
    assert res["status"] == "success"
    assert "metrics" in res
    assert "cagr_pct" in res["metrics"]


def test_run_institutional_mode2_pure_valuation_blended():
    res = run_bar_by_bar_backtest(
        symbol="VN30",
        backtest_mode="valuation",
        valuation_model_id="composite_fair_value",
        time_horizon_years=2,
        top_k=5,
        margin_of_safety_pct=15.0,
        composite_mode="blended"
    )
    assert res["status"] == "success"
    assert res["is_valuation_strategy"] is True
    assert "metrics" in res
    assert "cagr_pct" in res["metrics"]
    assert "fundamental_law" in res
    fl = res["fundamental_law"]
    assert "formula_display" in fl
    assert "realized_information_ratio" in fl


@pytest.mark.parametrize("metric", ["smape", "male", "wmape", "rmsle", "ivw"])
def test_run_institutional_mode2_pure_valuation_omnibus_submodes(metric):
    res = run_bar_by_bar_backtest(
        symbol="VN30",
        backtest_mode="valuation",
        valuation_model_id="composite_fair_value",
        time_horizon_years=2,
        top_k=5,
        margin_of_safety_pct=15.0,
        composite_mode="omnibus",
        omnibus_metric=metric
    )
    assert res["status"] == "success"
    assert res["is_valuation_strategy"] is True
    assert "equity_curve" in res


def test_run_institutional_mode3_arbitrary_hybrid_pairs():
    # Test pairing Magic Formula (Stage 1) with Extended McKinsey DCF (Stage 2)
    res1 = run_bar_by_bar_backtest(
        symbol="VN30",
        backtest_mode="hybrid",
        screening_strategy="guru_magic_formula_greenblatt",
        valuation_model_id="dcf_2stage_mckinsey",
        time_horizon_years=2,
        top_k=5,
        margin_of_safety_pct=15.0
    )
    assert res1["status"] == "success"
    assert res1["is_valuation_strategy"] is True
    assert "trades" in res1

    # Test pairing Seth Klarman Deep Value (Stage 1) with Owner's Earnings (Stage 2)
    res2 = run_bar_by_bar_backtest(
        symbol="VN30",
        backtest_mode="hybrid",
        screening_strategy="deep_value_klarman",
        valuation_model_id="buffett_owners_earnings",
        time_horizon_years=2,
        top_k=5,
        margin_of_safety_pct=20.0
    )
    assert res2["status"] == "success"
    assert res2["is_valuation_strategy"] is True


def test_run_valuation_parameter_sensitivity_hybrid():
    res = run_parameter_sensitivity(
        symbol="VN30",
        backtest_mode="hybrid",
        screening_strategy="peter_lynch_garp",
        valuation_model_id="composite_fair_value",
        time_horizon_years=2
    )
    assert res["status"] == "success"
    assert res["param1_name"] == "margin_of_safety_pct"
    assert res["param2_name"] == "top_k"
    assert "matrix_sharpe" in res
    assert len(res["matrix_sharpe"]) > 0


def test_run_valuation_monte_carlo():
    res = run_bar_by_bar_backtest(
        symbol="VN30",
        backtest_mode="factor",
        strategy_type="peter_lynch_garp",
        time_horizon_years=2,
        top_k=5,
    )
    trades = res.get("trades", [])
    mc = run_monte_carlo_stress_test(
        trades=trades,
        initial_capital=100000000.0,
        iterations=50
    )
    assert mc["status"] == "success"
    assert "confidence_intervals_95" in mc


def test_api_valuation_comprehensive_modes_and_metrics():
    # Test blended
    r1 = client.get("/api/valuation/comprehensive/FPT?mode=blended")
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["status"] == "success"
    assert j1["data"]["metadata"]["composite_mode"] == "blended"

    # Test omnibus with all 5 metrics
    for m in ["smape", "male", "wmape", "rmsle", "ivw"]:
        r2 = client.get(f"/api/valuation/comprehensive/FPT?mode=omnibus&metric={m}")
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["status"] == "success"
        assert j2["data"]["metadata"]["composite_mode"] == "omnibus"
        assert j2["data"]["metadata"]["omnibus_metric"] == m


def test_api_quant_institutional_run_endpoint():
    r = client.get("/api/quant/institutional/run?symbol=VN30&backtest_mode=hybrid&screening_strategy=peter_lynch_garp&valuation_model_id=composite_fair_value&time_horizon_years=2&top_k=5")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "success"
    assert "metrics" in j["data"]
