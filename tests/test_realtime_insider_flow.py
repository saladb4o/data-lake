"""
Unit and Integration Tests for Real-Time Insider & Shareholder Flow Engine:
  1. Regex Extraction under Vietnam Statutory Disclosure (TT96/2020/TT-BTC)
  2. Separation of Realized Executed Flow vs Pending Registrations
  3. Forced Liquidation / Margin Call Trigger Detection
  4. Integration with get_company_leadership and get_company_ecosystem
"""

import pytest
from services.insider_flow_engine import (
    parse_insider_disclosure_title,
    compute_insider_flow_analytics
)
from services.stock_service import get_company_leadership, get_company_ecosystem


def test_parse_insider_disclosure_title_executed_sell():
    title = "HPG: Ông Nguyễn Ngọc Quang - Thành viên HĐQT đã bán 6.600.000 cp"
    parsed = parse_insider_disclosure_title(title, date_str="09/07/2026", detail_url="https://cafef.vn/test")

    assert parsed is not None
    assert parsed["action_type"] == "EXECUTED_SELL"
    assert parsed["action_label"] == "ĐÃ BÁN"
    assert parsed["shares"] == 6_600_000.0
    assert "Nguyễn Ngọc Quang" in parsed["trader_name"]
    assert "HĐQT" in parsed["relationship"]


def test_parse_insider_disclosure_title_registered_sell():
    title = "NVL: CTCP NovaGroup đăng ký bán 4.400.000 cp"
    parsed = parse_insider_disclosure_title(title, date_str="05/06/2026", detail_url="https://cafef.vn/test")

    assert parsed is not None
    assert parsed["action_type"] == "REGISTERED_SELL"
    assert parsed["action_label"] == "ĐĂNG KÝ BÁN"
    assert parsed["shares"] == 4_400_000.0
    assert "NovaGroup" in parsed["trader_name"]


def test_parse_insider_disclosure_title_forced_liquidation():
    title = "DIG: CTCK Mirae Asset bán giải chấp 1.200.000 cp của Chủ tịch HĐQT"
    parsed = parse_insider_disclosure_title(title, date_str="15/11/2025", detail_url="https://cafef.vn/test")

    assert parsed is not None
    assert parsed["action_type"] == "FORCED_SELL"
    assert parsed["action_label"] == "BÁN GIẢI CHẤP"
    assert parsed["shares"] == 1_200_000.0


def test_parse_insider_disclosure_title_executed_buy():
    title = "VHM: Vingroup đã mua 10.000.000 cp"
    parsed = parse_insider_disclosure_title(title, date_str="20/08/2026", detail_url="https://cafef.vn/test")

    assert parsed is not None
    assert parsed["action_type"] == "EXECUTED_BUY"
    assert parsed["action_label"] == "ĐÃ MUA"
    assert parsed["shares"] == 10_000_000.0


def test_compute_insider_flow_analytics_strict_separation():
    """Verifies that Realized Net Flow strictly excludes registered non-executed shares."""
    mock_deals = [
        {"action_type": "EXECUTED_BUY", "shares": 2_000_000.0},
        {"action_type": "EXECUTED_SELL", "shares": 500_000.0},
        {"action_type": "REGISTERED_SELL", "shares": 10_000_000.0},  # Huge registration must NOT distort realized flow
        {"action_type": "REGISTERED_BUY", "shares": 1_000_000.0}
    ]
    res = compute_insider_flow_analytics(mock_deals, current_price=20000.0)

    # Realized Flow must be 2M - 0.5M = +1.5M shares (+30B VND)
    assert res["realized_net_shares"] == 1_500_000.0
    assert res["realized_net_flow_vnd"] == 30_000_000_000.0
    assert "MUA RÒNG" in res["sentiment"]

    # Pending Pipeline must reflect registrations: 1M - 10M = -9M shares
    assert res["pending_net_shares"] == -9_000_000.0
    assert res["registered_sell_shares"] == 10_000_000.0


def test_forced_liquidation_margin_call_sentiment():
    mock_deals = [
        {"action_type": "FORCED_SELL", "shares": 1_500_000.0, "trader_name": "CTCK VPS"}
    ]
    res = compute_insider_flow_analytics(mock_deals, current_price=15000.0)

    assert res["has_forced_sell_alert"] is True
    assert res["forced_sell_count"] == 1
    assert "GIẢI CHẤP" in res["sentiment"]


def test_leadership_and_ecosystem_api_contract():
    lead = get_company_leadership("HPG")
    assert "realtime_insider_flow" in lead
    flow = lead["realtime_insider_flow"]
    assert "realized_net_flow_vnd" in flow
    assert "sentiment" in flow
    assert "has_forced_sell_alert" in flow

    eco = get_company_ecosystem("HPG", depth=2, min_ownership=0.0)
    assert "recent_insider_events" in eco
