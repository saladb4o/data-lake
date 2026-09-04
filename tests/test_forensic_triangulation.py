"""
=============================================================================
UNIT TESTS FOR SOURCE 0 FORENSIC TRIANGLES & GROUND TRUTH ARBITRATION
=============================================================================
Verifies:
  1. Circular 200/2014/TT-BTC Income Statement (B02) & Cash Flow (B03) parser logic.
  2. The 5 Forensic Accounting Triangles (Gian Lận Kế Toán & Giám Định BCTC):
     - Triangle 1: Sloan Accrual Quality (NPAT vs CFO)
     - Triangle 2: Bank Debt Reconciliation (Footnotes vs Mã 320/338)
     - Triangle 3: Effective Borrowing & Tax Rates
     - Triangle 4: Related-Party Drain Ratio (Giao dịch sân sau)
     - Triangle 5: AGM Guidance Fulfillment Rate (Tỷ lệ đạt kế hoạch ĐHĐCĐ)
  3. Tier 0 Ground Truth Arbiter in reconstruct_financial_triangles & normalize_stock_data:
     - Discrepancy resolution with field_provenance = 4
     - Zero-missing data imputation for cash, CapEx, CFO
     - Provenance promotion to "Tier 0 (Ground Truth Audited)"
"""

import pytest
from typing import Dict, Any

from services.bctc_pdf_parser import (
    TT200_INCOME_CODES,
    TT200_CASH_FLOW_CODES,
    calculate_forensic_triangles,
    parse_vietnamese_accounting_number
)
from services.unified_data_service import (
    reconstruct_financial_triangles,
    normalize_stock_data,
    load_source0_symbol_data
)
from tests.test_normalizer import GOLDEN_KEYS


# =============================================================================
# 1. B02 & B03 ACCOUNTING DICTIONARY & NUMBER PARSING
# =============================================================================

def test_tt200_code_definitions():
    """Verifies that circular 200 codes for B02 and B03 are fully cataloged."""
    assert 10 in TT200_INCOME_CODES
    assert 11 in TT200_INCOME_CODES
    assert 20 in TT200_INCOME_CODES
    assert 50 in TT200_INCOME_CODES
    assert 60 in TT200_INCOME_CODES
    assert 70 in TT200_INCOME_CODES

    assert 20 in TT200_CASH_FLOW_CODES  # CFO
    assert 21 in TT200_CASH_FLOW_CODES  # CapEx
    assert 30 in TT200_CASH_FLOW_CODES  # CFI
    assert 40 in TT200_CASH_FLOW_CODES  # CFF
    assert 50 in TT200_CASH_FLOW_CODES  # Net Cash Flow
    assert 70 in TT200_CASH_FLOW_CODES  # Ending Cash


# =============================================================================
# 2. 5 FORENSIC ACCOUNTING TRIANGLES
# =============================================================================

def test_forensic_triangle_1_sloan_accrual_quality():
    """
    Triangle 1: Sloan Accrual Ratio = (NPAT - CFO) / Total Assets.
    High accrual (> 0.10) indicates paper profits / aggressive revenue recognition.
    Low/negative accrual (< -0.10) indicates high cash conversion / conservative accounting.
    """
    # Case A: Paper profits (NPAT 100B, CFO negative -20B, Assets 500B) -> Sloan = 120/500 = 0.24 (> 0.10)
    report_poor = {
        "balance_sheet": {"items": {270: {"current_val": 500_000_000_000.0}}},
        "income_statement": {"npat_vnd": 100_000_000_000.0},
        "cash_flow": {"cfo_vnd": -20_000_000_000.0}
    }
    f_poor = calculate_forensic_triangles(report_poor)
    t1_poor = f_poor["sloan_accrual_triangle"]
    assert t1_poor["sloan_ratio"] == 0.24
    assert "POOR" in t1_poor["earnings_quality"]
    assert t1_poor["is_cash_backed"] is False

    # Case B: Cash-rich earnings (NPAT 100B, CFO 200B, Assets 500B) -> Sloan = -100/500 = -0.20 (< -0.10)
    report_good = {
        "balance_sheet": {"items": {270: {"current_val": 500_000_000_000.0}}},
        "income_statement": {"npat_vnd": 100_000_000_000.0},
        "cash_flow": {"cfo_vnd": 200_000_000_000.0}
    }
    f_good = calculate_forensic_triangles(report_good)
    t1_good = f_good["sloan_accrual_triangle"]
    assert t1_good["sloan_ratio"] == -0.20
    assert "EXCELLENT" in t1_good["earnings_quality"]
    assert t1_good["is_cash_backed"] is True


def test_forensic_triangle_2_bank_debt_reconciliation():
    """
    Triangle 2: Footnote Bank Debt vs Balance Sheet Borrowings (Code 320 + 338).
    Tests full footnote transparency vs hidden/unreconciled debt.
    """
    # Balance sheet has 1,000B short-term + 500B long-term = 1,500B
    bctc_report = {
        "balance_sheet": {
            "items": {
                320: {"current_val": 1_000_000_000_000.0},
                338: {"current_val": 500_000_000_000.0}
            }
        },
        "debt_schedule_footnotes": [
            {"lender": "Vietcombank", "amount_vnd": 600_000_000_000.0},
            {"lender": "BIDV", "amount_vnd": 500_000_000_000.0},
            {"lender": "Trái phiếu", "amount_vnd": 380_000_000_000.0}
        ]
    }
    f = calculate_forensic_triangles(bctc_report)
    t2 = f["bank_debt_triangle"]
    assert t2["reported_borrowings_vnd"] == 1_500_000_000_000.0
    assert t2["footnote_debt_sum_vnd"] == 1_480_000_000_000.0
    assert t2["discrepancy_vnd"] == 20_000_000_000.0
    assert t2["reconciliation_pct"] == 98.67
    assert "HIGH" in t2["transparency_rating"]


def test_forensic_triangle_3_effective_rates():
    """
    Triangle 3: Effective Borrowing Cost (Interest / Borrowings) and Effective Tax Rate (Tax / PBT).
    """
    bctc_report = {
        "balance_sheet": {
            "items": {
                320: {"current_val": 1_000_000_000_000.0},
                338: {"current_val": 1_000_000_000_000.0}
            }
        },
        "income_statement": {
            "interest_expense_vnd": 160_000_000_000.0,
            "pbt_vnd": 500_000_000_000.0,
            "tax_expense_vnd": 100_000_000_000.0
        }
    }
    f = calculate_forensic_triangles(bctc_report)
    t3 = f["effective_rates_triangle"]
    assert t3["effective_borrowing_rate_pct"] == 8.0  # 160B / 2000B = 8%
    assert t3["effective_tax_rate_pct"] == 20.0       # 100B / 500B = 20%
    assert t3["tax_deviation_pct"] == 0.0             # Exactly matches 20% standard rate


def test_forensic_triangle_4_related_party_drain():
    """
    Triangle 4: Related-Party Volume / Equity.
    Flags excessive insider or sister company transactions.
    """
    bctc_report = {
        "balance_sheet": {"items": {400: {"current_val": 1_000_000_000_000.0}}}
    }
    # Case A: 350B related party transactions on 1,000B equity -> 35% (> 25% High Risk)
    disclosures_high = {
        "related_party_transactions": [
            {"entity_name": "CTCP Sân Sau A", "transaction_value_vnd": 200_000_000_000.0},
            {"entity_name": "CTCP Sân Sau B", "transaction_value_vnd": 150_000_000_000.0}
        ]
    }
    f_high = calculate_forensic_triangles(bctc_report, disclosures_high)
    t4_high = f_high["related_party_drain_triangle"]
    assert t4_high["drain_ratio"] == 0.35
    assert "HIGH" in t4_high["risk_assessment"]

    # Case B: 30B on 1,000B equity -> 3% (Low Risk)
    disclosures_low = {
        "related_party_transactions": [
            {"entity_name": "Công ty liên kết C", "transaction_value_vnd": 30_000_000_000.0}
        ]
    }
    f_low = calculate_forensic_triangles(bctc_report, disclosures_low)
    t4_low = f_low["related_party_drain_triangle"]
    assert t4_low["drain_ratio"] == 0.03
    assert "LOW" in t4_low["risk_assessment"]


def test_forensic_triangle_5_agm_guidance_fulfillment():
    """
    Triangle 5: Actual Revenue & NPAT vs AGM Resolution Targets.
    """
    bctc_report = {
        "income_statement": {
            "revenue_vnd": 10_500_000_000_000.0,
            "npat_vnd": 1_200_000_000_000.0
        }
    }
    disclosures = {
        "resolution_data": {
            "target_revenue_vnd": 10_000_000_000_000.0,
            "target_npat_vnd": 1_000_000_000_000.0
        }
    }
    f = calculate_forensic_triangles(bctc_report, disclosures)
    t5 = f["agm_fulfillment_triangle"]
    assert t5["revenue_fulfillment_pct"] == 105.0
    assert t5["npat_fulfillment_pct"] == 120.0
    assert t5["guidance_status"] == "EXCEEDED_TARGET"


# =============================================================================
# 3. TIER 0 GROUND TRUTH ARBITRATION IN UNIFIED_DATA_SERVICE
# =============================================================================

def test_source0_ground_truth_arbiter_override():
    """
    Tests that when Source 0 (Audited Filing) is supplied, it acts as Tier 0 Arbiter:
      - Overrides TradingView values with field_provenance = 4
      - Imputes missing fields (Cash, CapEx, CFO) with field_provenance = 4
      - Upgrades overall provenance_tier to 'Tier 0 (Ground Truth Audited)'
    """
    tv = {
        "close": 25000.0,
        "market_cap_basic": 25_000_000_000_000.0,
        "total_assets_fq": 50_000_000_000_000.0,
        "total_liabilities_fq": 30_000_000_000_000.0,
        "total_equity_fq": 20_000_000_000_000.0,
        # Notice: TradingView has NO cash, NO capex, NO debt
    }
    s0 = {
        "balance_sheet": {
            "items": {
                270: {"current_val": 52_000_000_000_000.0}, # Audited Total Assets
                300: {"current_val": 31_000_000_000_000.0}, # Audited Liab
                400: {"current_val": 21_000_000_000_000.0}, # Audited Equity
                110: {"current_val": 4_500_000_000_000.0},  # Audited Cash (was missing in TV)
                320: {"current_val": 8_000_000_000_000.0},  # Short-term debt
                338: {"current_val": 2_000_000_000_000.0},  # Long-term debt
            }
        },
        "income_statement": {
            "revenue_vnd": 30_000_000_000_000.0,
            "npat_vnd": 2_500_000_000_000.0
        },
        "cash_flow": {
            "cfo_vnd": 3_200_000_000_000.0,
            "capex_vnd": 1_000_000_000_000.0,
            "free_cash_flow_vnd": 2_200_000_000_000.0
        }
    }

    tri = reconstruct_financial_triangles(
        symbol="SHS",
        price=25000.0,
        raw_mcap=25_000_000_000_000.0,
        sector_code="VNFIN",
        tv_data=tv,
        vn_data={},
        yf_data={},
        source0_data=s0
    )

    fp = tri["field_provenance"]
    # Total assets, equity, debt, cash, revenue, net income must be Tier 4
    assert fp["total_assets"] == 4
    assert fp["total_equity"] == 4
    assert fp["total_debt"] == 4
    assert fp["cash"] == 4
    assert fp["revenue"] == 4
    assert fp["net_income"] == 4
    assert fp["cfo"] == 4
    assert fp["capex"] == 4
    assert fp["fcf_ttm"] == 4

    # The provenance tier must be Tier 0 (Ground Truth Audited)
    assert tri["provenance_tier"] == "Tier 0 (Ground Truth Audited)"
    assert tri["data_quality_score"] >= 65.0
    # Tier 4 fields are not imputed
    assert tri["is_imputed"]["total_assets"] is False
    assert tri["is_imputed"]["revenue"] is False


def test_normalize_stock_data_source0_integration():
    """
    Verifies that normalize_stock_data integrates Source 0 seamlessly:
      - Preserves GOLDEN_KEYS top-level contract (zero drift)
      - Enriches _metadata with forensic_triangles, auditor_summary, and footnotes
      - Registers 'source_0_lake' in sources_used
    """
    tv = {
        "close": 25000.0,
        "market_cap_basic": 25_000_000_000_000.0,
        "total_assets_fq": 50_000_000_000_000.0,
        "total_equity_fq": 20_000_000_000_000.0,
    }
    s0 = {
        "balance_sheet": {
            "items": {
                270: {"current_val": 50_000_000_000_000.0},
                400: {"current_val": 20_000_000_000_000.0},
                110: {"current_val": 5_000_000_000_000.0}
            }
        },
        "income_statement": {
            "revenue_vnd": 10_000_000_000_000.0,
            "npat_vnd": 1_000_000_000_000.0
        },
        "cash_flow": {
            "cfo_vnd": 1_200_000_000_000.0,
            "capex_vnd": 400_000_000_000.0
        },
        "auditor_summary": {
            "auditor_firm": "AASC",
            "is_big4": False,
            "opinion_type": "Chấp nhận toàn phần (Unqualified)",
            "risk_flags": []
        },
        "debt_schedule_footnotes": [
            {"lender": "Vietcombank", "amount_vnd": 2_000_000_000_000.0}
        ],
        "forensic_triangles": {
            "sloan_accrual_triangle": {"sloan_ratio": -0.004, "earnings_quality": "NORMAL"}
        }
    }

    rec = normalize_stock_data(
        symbol="SHS",
        exchange="HNX",
        name="Chứng khoán SHS",
        sector_code="VNFIN",
        sector_name="Tài Chính",
        tv_data=tv,
        source0_data=s0
    )

    # 1. Exact top-level key preservation
    assert set(rec.keys()) == GOLDEN_KEYS, (
        f"Key drift: extra={set(rec.keys()) - GOLDEN_KEYS}, missing={GOLDEN_KEYS - set(rec.keys())}"
    )

    # 2. Metadata contains Source 0 artifacts
    meta = rec["_metadata"]
    assert "source_0_lake" in meta["sources_used"]
    assert meta["has_source0_lake"] is True
    assert meta["auditor_summary"]["auditor_firm"] == "AASC"
    assert len(meta["debt_schedule_footnotes"]) == 1
    assert meta["forensic_triangles"]["sloan_accrual_triangle"]["earnings_quality"] == "NORMAL"
