"""
=============================================================================
UNIT TESTS: SBV & GSO MACROECONOMIC & MONETARY POLICY INTELLIGENCE
=============================================================================
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.macro_monetary_service import (
    get_sbv_monetary_policy_data,
    get_gso_macroeconomic_data,
    get_macro_monetary_comprehensive_overview
)
from services.global_market_service import get_global_commodities_overview
from server import app


def test_sbv_monetary_policy_data():
    data = get_sbv_monetary_policy_data()
    assert data["status"] == "success"
    assert "exchange_rates" in data
    assert data["exchange_rates"]["central_rate"] > 20000
    assert data["exchange_rates"]["band_pct"] == 5.0
    
    # OMO & Liquidity
    assert "liquidity_operations" in data
    assert "net_liquidity_position" in data["liquidity_operations"]
    assert "weekly_trend" in data["liquidity_operations"]
    
    # Interbank curve
    assert "interbank_rates" in data
    assert len(data["interbank_rates"]) >= 6
    for r in data["interbank_rates"]:
        assert "tenure" in r and "rate" in r


def test_gso_macroeconomic_data():
    data = get_gso_macroeconomic_data()
    assert data["status"] == "success"
    
    # GDP
    assert "gdp" in data
    assert data["gdp"]["latest_full_year_growth"] > 0
    assert len(data["gdp"]["quarterly_series"]) == 4
    
    # CPI
    assert "cpi" in data
    assert data["cpi"]["headline_cpi_yoy"] > 0
    assert data["cpi"]["target_ceiling"] == 4.5
    
    # IIP, FDI, Trade, PMI
    assert "iip" in data and data["iip"]["overall_iip_yoy"] > 0
    assert "fdi" in data and data["fdi"]["disbursed_capital_bil_usd"] > 0
    assert "trade" in data and data["trade"]["trade_balance_bil_usd"] > 0
    assert "pmi" in data and data["pmi"]["latest_score"] >= 50.0


def test_macro_monetary_comprehensive_overview():
    data = get_macro_monetary_comprehensive_overview()
    assert data["status"] == "success"
    assert "macro_score" in data and 0 <= data["macro_score"] <= 10
    assert "sbv" in data
    assert "gso" in data
    assert "impact_matrix" in data
    assert len(data["impact_matrix"]) >= 4


def test_macro_monetary_api_endpoint():
    client = TestClient(app)
    resp = client.get("/api/macro/monetary-policy")
    assert resp.status_code == 200
    json_data = resp.json()
    assert json_data["status"] == "success"
    payload = json_data["data"]
    assert "sbv" in payload
    assert "gso" in payload
    assert "impact_matrix" in payload


def test_global_commodities_instant_performance():
    data = get_global_commodities_overview()
    assert data["status"] == "success"
    assert len(data["items"]) == 8
    for item in data["items"]:
        assert "price" in item and item["price"] > 0
        assert "impact_symbols" in item
