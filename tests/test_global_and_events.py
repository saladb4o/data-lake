import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from services.global_market_service import get_global_commodities_overview, GLOBAL_ASSETS_MAP
from services.etf_rebalance_service import get_etf_rebalancing_overview, calculate_review_dates
from services.stock_service import get_market_wide_events_calendar, get_market_upgrade_tracker

def test_global_commodities_overview():
    res = get_global_commodities_overview()
    assert res is not None
    assert res.get("status") == "success"
    assert "items" in res
    assert len(res["items"]) >= len(GLOBAL_ASSETS_MAP)
    
    # Check that key commodities exist
    keys = [item["key"] for item in res["items"]]
    assert "BRENT_OIL" in keys
    assert "WTI_OIL" in keys
    assert "DXY" in keys
    assert "US10Y" in keys
    assert "GOLD" in keys

    # Verify price data structure
    for item in res["items"]:
        assert item["price"] > 0
        assert "direction" in item
        assert "impact_symbols" in item

def test_etf_rebalancing_overview():
    res = get_etf_rebalancing_overview()
    assert res is not None
    assert res.get("status") == "success"
    assert "next_rebalance_event" in res
    assert "schedule" in res
    assert len(res["schedule"]) == 4
    assert len(res["funds"]) >= 5

def test_market_wide_events_calendar():
    res = get_market_wide_events_calendar(limit=20, offset=0)
    assert res is not None
    assert res.get("status") == "success"
    assert "events" in res
    assert "category_counts" in res
    assert isinstance(res["events"], list)

def test_market_upgrade_tracker():
    res = get_market_upgrade_tracker()
    assert res is not None
    assert res.get("status") == "success"
    assert "ftse_criteria" in res
    assert "msci_criteria" in res
    assert "institutional_funds" in res
    assert res["overall_readiness_pct"] > 50
