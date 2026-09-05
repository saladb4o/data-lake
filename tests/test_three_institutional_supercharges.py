"""
Automated Integration and Unit Test Suite for The 3 Institutional Supercharges:
  1. Hướng 1: Commodity Crack Spread Engine (Peter Lynch / Howard Marks / Damodaran)
  2. Hướng 2: Smart Money Order Flow & Wyckoff Matrix (Order Flow, Prop Trading, Foreign VWAP, Room)
  3. Hướng 3: Related-Party Tunneling Radar (Prof. Andrei Shleifer T-Index, VAS 26, Subsidized Capital Arbitrage)
"""

import pytest
from services.commodity_spread_engine import (
    CommoditySpreadEngine,
    get_commodity_spread_for_symbol,
    CYCLICAL_SECTORS_REGISTRY
)
from services.smart_money_flow_engine import (
    SmartMoneyFlowEngine,
    compute_smart_money_analytics,
    compute_smart_money_order_flow
)
from services.related_party_tunneling_engine import (
    RelatedPartyTunnelingEngine,
    compute_related_party_tunneling
)
from services.stock_service import (
    get_commodity_spread_analysis,
    get_company_leadership,
    get_company_forensic_report
)


def test_commodity_spread_engine_cyclical_stocks():
    # 1. Test Steel (HPG)
    hpg_res = get_commodity_spread_for_symbol("HPG")
    assert hpg_res["is_cyclical"] is True
    assert hpg_res["sector_key"] == "STEEL"
    assert "Thép" in hpg_res["sector_name"]
    assert "usd/tấn" in hpg_res["spread_unit"].lower()
    
    analysis = hpg_res["spread_analysis"]
    assert analysis["current_spread"] > 0
    assert any(phase in analysis["cycle_phase"] for phase in ["ĐÁY", "BÙNG NỔ", "CO HẸP", "SUY THOÁI", "CÂN BẰNG"])
    assert "peter_lynch_guidance" in analysis
    assert len(analysis["peter_lynch_guidance"]) > 10
    assert "gross_margin_forecast" in analysis
    assert "direction" in analysis["gross_margin_forecast"]
    assert len(hpg_res["input_commodities"]) >= 2
    assert "HRC" in hpg_res["output_commodity"]["name"]

    # 2. Test Livestock (DBC)
    dbc_res = get_commodity_spread_for_symbol("DBC")
    assert dbc_res["is_cyclical"] is True
    assert dbc_res["sector_key"] == "LIVESTOCK"
    assert "Chăn Nuôi" in dbc_res["sector_name"]
    assert "vnd/kg" in dbc_res["spread_unit"].lower()
    assert "Heo Hơi" in dbc_res["output_commodity"]["name"]

    # 3. Test Fertilizer (DPM)
    dpm_res = get_commodity_spread_for_symbol("DPM")
    assert dpm_res["is_cyclical"] is True
    assert dpm_res["sector_key"] == "FERTILIZER"
    assert "Phân Bón" in dpm_res["sector_name"]


def test_commodity_spread_engine_non_cyclical():
    # Test FPT (Technology / Services)
    fpt_res = get_commodity_spread_for_symbol("FPT")
    assert fpt_res["is_cyclical"] is False
    assert "all_cyclical_sectors" in fpt_res
    assert len(fpt_res["all_cyclical_sectors"]) == 10
    assert "phi chu kỳ" in fpt_res["message"].lower()


def test_smart_money_flow_engine_strict_separation():
    # Evaluate Smart Money Flow on HPG
    flow = compute_smart_money_order_flow("HPG", current_price=27500.0)
    
    assert "matched_flow" in flow
    assert "put_through_flow" in flow
    assert "prop_trading" in flow
    assert "foreign_flow" in flow
    assert "foreign_vwap_analysis" in flow
    assert "foreign_room_exhaustion" in flow
    assert "wyckoff_footprint" in flow

    # Check strict separation of matched vs put-through
    matched = flow["matched_flow"]
    pt = flow["put_through_flow"]
    assert "foreign_net_matched_val" in matched
    assert "foreign_net_pt_val" in pt

    # Check prop trading sentiment
    prop = flow["prop_trading"]
    assert any(k in prop["sentiment"] for k in ["CÂN BẰNG", "GOM", "PHÂN PHỐI", "ĐỠ GIÁ"])

    # Check foreign VWAP support anchors
    vwap = flow["foreign_vwap_analysis"]
    assert vwap["cost_basis_vwap_30d"] > 0
    assert vwap["cost_basis_vwap_90d"] > 0
    assert "distance_to_30d_pct" in vwap
    assert "support_resistance_status" in vwap

    # Check Foreign room
    room = flow["foreign_room_exhaustion"]
    assert 0 <= room["foreign_owned_pct"] <= 100
    assert room["remaining_room_pct"] >= 0
    assert any(k in room["status"] for k in ["ROOM", "KỊCH", "HỞ"])

    # Check Wyckoff footprint
    wyckoff = flow["wyckoff_footprint"]
    assert wyckoff["phase"] in ["TÍCH LŨY NGẦM", "PHÂN PHỐI", "ĐẨY GIÁ", "GIỮ NHỊP"]


def test_related_party_tunneling_shleifer_index():
    engine = RelatedPartyTunnelingEngine()
    
    # 1. Test clean company (e.g. HPG)
    hpg_rp = engine.analyze("HPG")
    assert "shleifer_t_index" in hpg_rp
    t_index = hpg_rp["shleifer_t_index"]
    assert t_index["t_index_pct"] >= 0
    assert t_index["tunneling_risk_rating"] in ["AN TOÀN", "TRUNG BÌNH", "NGUY HIỂM", "BÁO ĐỘNG ĐỎ"]
    assert "subsidized_capital_arbitrage" in hpg_rp
    assert "remuneration_asymmetry" in hpg_rp
    assert isinstance(hpg_rp["transactions"], list)

    # 2. Test synthetic extreme tunneling scenario
    mock_records = [{
        "doc_id": "TEST_DOC",
        "period": "2025_Q4",
        "balance_sheet": {
            "total_assets": 100_000_000_000,   # 100 Tỷ
            "short_term_loans": 30_000_000_000, # 30 Tỷ
            "short_term_receivables": 20_000_000_000 # 20 Tỷ
        },
        "income_statement": {
            "net_profit": 2_000_000_000 # 2 Tỷ
        },
        "cash_flow": {},
        "notes": {
            "related_party_transactions": [
                {
                    "counterparty_name": "Công ty TNHH Sân Sau Chủ Tịch",
                    "relationship": "Công ty của người nhà TGĐ",
                    "nature": "Cho vay ngắn hạn lãi suất 0%",
                    "amount_vnd": 30_000_000_000,
                    "interest_rate_pct": 0.0
                },
                {
                    "counterparty_name": "CTCP Đầu tư Vệ Tinh",
                    "relationship": "Bên liên quan",
                    "nature": "Đặt cọc mua cổ phần dự án chưa hoàn tất",
                    "amount_vnd": 10_000_000_000,
                    "interest_rate_pct": 0.0
                }
            ],
            "management_remuneration": {
                "total_remuneration_vnd": 1_500_000_000 # 1.5 Tỷ (75% LNST!)
            }
        }
    }]
    
    extreme_rp = engine.analyze_from_records("TEST_TICKER", mock_records)
    ex_t = extreme_rp["shleifer_t_index"]
    # Loans (30B) + Advances (10B) = 40B on 100B assets = 40% T-Index!
    assert ex_t["t_index_pct"] >= 25.0
    assert ex_t["tunneling_risk_rating"] in ["NGUY HIỂM", "BÁO ĐỘNG ĐỎ"]
    
    # Subsidized arbitrage on 30B loan at 0% interest vs 9.5% cost of capital
    sub = extreme_rp["subsidized_capital_arbitrage"]
    assert sub["estimated_annual_leakage_vnd"] > 500_000_000
    assert sub["reported_related_interest_rate_pct"] == 0.0

    # Remuneration Asymmetry: 1.5B remuneration on 2B NPAT = 75% of NPAT!
    rem = extreme_rp["remuneration_asymmetry"]
    assert rem["remuneration_to_npat_pct"] > 50.0
    assert rem["asymmetry_flag"] is True


def test_stock_service_full_api_integration():
    # 1. Test Commodity Spread API
    spread_data = get_commodity_spread_analysis("HPG")
    assert spread_data is not None
    assert spread_data["symbol"] == "HPG"
    assert spread_data["is_cyclical"] is True

    # 2. Test Leadership API enriched with Smart Money Flow
    lead_data = get_company_leadership("HPG")
    assert "smart_money_flow" in lead_data
    sm = lead_data["smart_money_flow"]
    assert "matched_flow" in sm
    assert "prop_trading" in sm
    assert "foreign_vwap_analysis" in sm

    # 3. Test Forensic API enriched with Related-Party Tunneling
    forensic_data = get_company_forensic_report("HPG")
    assert "related_party_tunneling" in forensic_data
    rp = forensic_data["related_party_tunneling"]
    assert "shleifer_t_index" in rp
    assert "subsidized_capital_arbitrage" in rp


def test_commodity_spread_dynamic_universe_discovery():
    """Verify market-wide Dynamic Universe Discovery across all 7 cyclical sectors."""
    # 1. HPG (Steel) should contain core leaders + 40+ discovered steel stocks
    hpg_res = get_commodity_spread_for_symbol("HPG")
    assert hpg_res["is_cyclical"] is True
    assert "all_sector_symbols" in hpg_res
    assert "core_leaders" in hpg_res
    assert hpg_res["total_sector_symbols_count"] >= 40
    assert "HPG" in hpg_res["core_leaders"]
    assert "HSG" in hpg_res["core_leaders"]
    assert "NKG" in hpg_res["core_leaders"]
    assert "GDA" in hpg_res["all_sector_symbols"]
    assert "POM" in hpg_res["all_sector_symbols"]

    # 2. Test dynamically discovering a secondary stock not in original core list
    gda_res = get_commodity_spread_for_symbol("GDA")
    assert gda_res["is_cyclical"] is True
    assert gda_res["sector_key"] == "STEEL"

    las_res = get_commodity_spread_for_symbol("LAS")
    assert las_res["is_cyclical"] is True
    assert las_res["sector_key"] == "FERTILIZER"
    assert las_res["total_sector_symbols_count"] >= 30

    hag_res = get_commodity_spread_for_symbol("HAG")
    assert hag_res["is_cyclical"] is True
    assert hag_res["sector_key"] == "LIVESTOCK"

    # 3. Summary covers all 10 sectors with total counts
    summary = hpg_res.get("all_cyclical_sectors", [])
    assert len(summary) == 10
    total_market_cyclicals = sum(s.get("total_sector_symbols_count", 0) for s in summary)
    assert total_market_cyclicals >= 200


def test_ten_cyclical_sectors_and_dual_layer_spread():
    """
    Verifies:
      1. All 10 cyclical sectors are active (including Seafood, Cement, Shipping).
      2. Dynamic market-cap ranking places top capitalized leaders in core_leaders.
      3. Dual-layer data: International futures vs Vietnam domestic spot and basis spread analysis.
    """
    from services.domestic_commodity_service import DomesticCommodityService

    # Verify DomesticCommodityService has data for all 10 sectors
    assert len(DomesticCommodityService.DOMESTIC_COMMODITIES_REGISTRY) == 10

    # 1. Seafood: VHC (Vĩnh Hoàn)
    vhc_res = get_commodity_spread_for_symbol("VHC")
    assert vhc_res["is_cyclical"] is True
    assert vhc_res["sector_key"] == "SEAFOOD"
    assert "Thủy Sản" in vhc_res["sector_name"]
    assert "domestic_spot" in vhc_res
    assert vhc_res["domestic_spot"]["spot_price"] > 0
    assert "basis_analysis" in vhc_res
    assert "basis_gap_pct" in vhc_res["basis_analysis"]

    # 2. Cement: HT1 (Hà Tiên 1)
    ht1_res = get_commodity_spread_for_symbol("HT1")
    assert ht1_res["is_cyclical"] is True
    assert ht1_res["sector_key"] == "CEMENT"
    assert "Xi Măng" in ht1_res["sector_name"]
    assert ht1_res["domestic_spot"]["spot_price"] > 0

    # 3. Shipping: HAH (Hải An)
    hah_res = get_commodity_spread_for_symbol("HAH")
    assert hah_res["is_cyclical"] is True
    assert hah_res["sector_key"] == "SHIPPING"
    assert "Vận Tải Biển" in hah_res["sector_name"]
    assert hah_res["domestic_spot"]["spot_price"] > 0

    # 4. Livestock: DBC with Live VietnamBiz Crawl data
    dbc_res = get_commodity_spread_for_symbol("DBC")
    dom = dbc_res["domestic_spot"]
    assert dom["has_domestic_data"] is True
    assert "VietnamBiz" in dom["source"]
    assert 50000 <= dom["spot_price"] <= 80000
    assert "regions" in dom
    assert "Bắc" in dom["regions"]
    basis = dbc_res["basis_analysis"]
    assert basis["domestic_spot_vnd"] > 0
    assert basis["global_benchmark_vnd"] > 0

    # 5. Refinery: BSR with Petrolimex data
    bsr_res = get_commodity_spread_for_symbol("BSR")
    bsr_dom = bsr_res["domestic_spot"]
    assert "Petrolimex" in bsr_dom["source"]
    assert bsr_dom["spot_price"] > 15000
    assert "products" in bsr_dom and any("RON 95" in k or "Vùng 1" in k for k in bsr_dom["products"])

    # 6. Dynamic Market-Cap Ranking: HPG must be #1 leader in Steel
    hpg_res = get_commodity_spread_for_symbol("HPG")
    assert hpg_res["core_leaders"][0] == "HPG"

