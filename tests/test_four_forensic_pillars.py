"""
Unit and Integration Tests for the 4 Institutional Forensic Pillars:
  1. CIPForensicEngine (Quỹ Đất & Dự Án CIP)
  2. SayDoManagementIntegrityEngine (Đối Soát ĐHĐCĐ & Chỉ Số Nói/Làm)
  3. PledgedCollateralEngine (Radar Cầm Cố Cổ Phiếu & Giải Chấp)
  4. DividendSustainabilityAndDilutionEngine (Sức Bền Cổ Tức & Bẫy Pha Loãng)
  5. Integration with get_company_forensic_report API Contract
"""

import pytest
from services.forensic_intelligence_engine import (
    CIPForensicEngine,
    SayDoManagementIntegrityEngine,
    PledgedCollateralEngine,
    DividendSustainabilityAndDilutionEngine,
    build_complete_forensic_suite
)
from services.stock_service import get_company_forensic_report


def test_cip_forensic_engine_cash_reality():
    """Verifies that CIPForensicEngine correctly cross-checks B01 vs B03 cash reality."""
    mock_bctc = {
        "extracted_data": {
            "balance_sheet": {
                "items": {
                    "154": {"current_val": 200_000_000_000.0},
                    "242": {"current_val": 800_000_000_000.0},
                    "132": {"current_val": 150_000_000_000.0}
                }
            },
            "cash_flow": {
                "items": {
                    "21": {"current_val": -450_000_000_000.0}  # Cash outflow 450B
                }
            },
            "capex_cip_projects": [
                {"project_name": "Nhà máy Thép Giai Đoạn 2", "carrying_value_vnd": 800_000_000_000.0, "page": 24}
            ]
        }
    }
    res = CIPForensicEngine.analyze("MOCK", bctc_record=mock_bctc)

    assert res["total_cip_vnd"] == 1_000_000_000_000.0
    assert res["capex_cash_paid_vnd"] == 450_000_000_000.0
    assert res["cash_backed_capex_pct"] > 70.0
    assert len(res["projects_breakdown"]) == 1
    assert "XUẤT SẮC" in res["cip_health_rating"] or "CHUẨN MỰC" in res["cip_health_rating"]


def test_say_do_management_integrity_scoring():
    """Verifies that SayDoManagementIntegrityEngine computes deterministic 0-100 score and detects manipulation."""
    mock_bctc = {
        "extracted_data": {
            "income_statement": {
                "items": {
                    "10": {"current_val": 12_000_000_000_000.0},  # Actual rev 12,000B
                    "60": {"current_val": 1_100_000_000_000.0},   # Actual NPAT 1,100B
                    "30": {"current_val": 1_000_000_000_000.0}    # Operating profit 1,000B
                }
            }
        }
    }
    mock_corp_lake = {
        "MOCK_AGM": {
            "symbol": "MOCK",
            "title": "MOCK: Nghị quyết ĐHĐCĐ thường niên 2024",
            "extracted_data": {
                "resolution_data": {
                    "target_revenue_vnd": 10_000_000_000_000.0,  # Target rev 10,000B
                    "target_npat_vnd": 1_000_000_000_000.0,      # Target NPAT 1,000B
                    "target_dividend_rate_pct": 20.0,
                    "dividend_payout_form": "CASH"
                }
            }
        }
    }
    res = SayDoManagementIntegrityEngine.analyze("MOCK", bctc_record=mock_bctc, corp_lake=mock_corp_lake)

    assert res["npat_delivery_pct"] == 110.0
    assert res["revenue_delivery_pct"] == 120.0
    assert res["say_do_score"] >= 85
    assert "LÃNH ĐẠO UY TÍN" in res["integrity_rating"]
    assert res["is_core_backed"] is True


def test_pledged_collateral_engine_margin_call_trigger():
    """Verifies that PledgedCollateralEngine calculates LTV trigger and liquidity absorption days."""
    mock_bctc = {
        "extracted_data": {
            "balance_sheet": {
                "items": {
                    "320": {"current_val": 2_000_000_000_000.0},
                    "338": {"current_val": 3_000_000_000_000.0}
                }
            },
            "debt_schedule_footnotes": [
                {
                    "lender": "Techcombank",
                    "amount_vnd": 1_500_000_000_000.0,
                    "collateral_type": "CỔ PHIẾU / CỔ PHẦN",
                    "is_share_pledged": True,
                    "raw_line": "Vay TCB bảo đảm bằng 50 triệu cổ phiếu của Chủ tịch HĐQT"
                }
            ]
        }
    }
    mock_quote = {
        "current_price": 20000.0,
        "avg_volume_50d": 3_000_000
    }
    res = PledgedCollateralEngine.analyze("MOCK", bctc_record=mock_bctc, market_quote=mock_quote)

    assert res["total_debt_vnd"] == 5_000_000_000_000.0
    assert res["pledged_debt_vnd"] == 1_500_000_000_000.0
    assert res["pledged_debt_ratio_pct"] == 30.0
    assert res["has_shares_pledged"] is True
    assert res["estimated_trigger_price"] == 13000.0  # -35% trigger
    assert res["days_to_liquidate"] > 0


def test_dividend_sustainability_and_dilution_speedometer():
    """Verifies that DividendSustainabilityAndDilutionEngine detects debt-funded dividend traps and dilution spread."""
    # Case 1: Healthy Cash-backed dividend
    mock_bctc_healthy = {
        "extracted_data": {
            "cash_flow": {
                "items": {
                    "20": {"current_val": 5_000_000_000_000.0},   # CFO 5,000B
                    "21": {"current_val": -2_000_000_000_000.0},  # CapEx 2,000B -> FCF = 3,000B
                    "36": {"current_val": -1_000_000_000_000.0}   # Div 1,000B
                }
            },
            "income_statement": {
                "items": {"60": {"current_val": 3_500_000_000_000.0}}
            }
        }
    }
    res_h = DividendSustainabilityAndDilutionEngine.analyze("MOCK_H", bctc_record=mock_bctc_healthy)
    assert res_h["fcf_vnd"] == 3_000_000_000_000.0
    assert res_h["fcf_coverage_ratio"] == 3.0
    assert "VỮNG CHẮC" in res_h["dividend_status"]

    # Case 2: Debt-funded dividend trap (Negative FCF)
    mock_bctc_trap = {
        "extracted_data": {
            "cash_flow": {
                "items": {
                    "20": {"current_val": -500_000_000_000.0},    # CFO -500B
                    "21": {"current_val": -1_500_000_000_000.0},  # CapEx 1,500B -> FCF = -2,000B
                    "36": {"current_val": -800_000_000_000.0}    # Div 800B
                }
            },
            "income_statement": {
                "items": {"60": {"current_val": 200_000_000_000.0}}
            }
        }
    }
    res_t = DividendSustainabilityAndDilutionEngine.analyze("MOCK_T", bctc_record=mock_bctc_trap)
    assert res_t["fcf_vnd"] == -2_000_000_000_000.0
    assert "BẪY NỢ" in res_t["dividend_status"]


def test_forensic_report_api_payload_enrichment():
    """Verifies that get_company_forensic_report payload integrates all 4 pillars seamlessly."""
    rep = get_company_forensic_report("HPG")

    assert "accounting_integrity_score" in rep
    assert "forensic_triangles" in rep
    assert "cip_forensic_tracker" in rep
    assert "say_do_management_integrity" in rep
    assert "pledged_shares_margin_risk" in rep
    assert "dividend_dilution_radar" in rep

    # Verify pillar data structure integrity
    cip = rep["cip_forensic_tracker"]
    assert "cip_health_rating" in cip
    assert "cash_backed_capex_pct" in cip

    say_do = rep["say_do_management_integrity"]
    assert "say_do_score" in say_do
    assert "integrity_rating" in say_do

    margin = rep["pledged_shares_margin_risk"]
    assert "margin_call_risk_level" in margin

    div = rep["dividend_dilution_radar"]
    assert "dividend_status" in div
    assert "fcf_coverage_ratio" in div
