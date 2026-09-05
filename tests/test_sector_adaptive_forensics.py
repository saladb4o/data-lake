import unittest
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services.bctc_pdf_parser import (
    detect_accounting_regime,
    calculate_forensic_triangles,
    TT49_BANK_BALANCE_CODES,
    TT49_BANK_INCOME_CODES,
    TT334_SECURITIES_BALANCE_CODES,
    TT334_SECURITIES_INCOME_CODES,
    TT200_BALANCE_SHEET_CODES,
    TT200_INCOME_CODES
)
from services.bctc_batch_processor import get_stock_forensic_dossier
from services.stock_service import get_company_forensic_report


class TestSectorAdaptiveForensics(unittest.TestCase):
    def test_01_detect_accounting_regime_symbols(self):
        """Tests that sector regimes are accurately identified by ticker symbol."""
        # Banking
        self.assertEqual(detect_accounting_regime(symbol="VCB"), "BANK")
        self.assertEqual(detect_accounting_regime(symbol="MBB"), "BANK")
        self.assertEqual(detect_accounting_regime(symbol="TCB"), "BANK")
        self.assertEqual(detect_accounting_regime(symbol="CTG"), "BANK")

        # Securities
        self.assertEqual(detect_accounting_regime(symbol="SSI"), "SECURITIES")
        self.assertEqual(detect_accounting_regime(symbol="VND"), "SECURITIES")
        self.assertEqual(detect_accounting_regime(symbol="VCI"), "SECURITIES")
        self.assertEqual(detect_accounting_regime(symbol="HCM"), "SECURITIES")

        # Real Estate
        self.assertEqual(detect_accounting_regime(symbol="VHM"), "REAL_ESTATE")
        self.assertEqual(detect_accounting_regime(symbol="NVL"), "REAL_ESTATE")
        self.assertEqual(detect_accounting_regime(symbol="CEO"), "REAL_ESTATE")
        self.assertEqual(detect_accounting_regime(symbol="KDH"), "REAL_ESTATE")

        # Industrial / Non-Finance
        self.assertEqual(detect_accounting_regime(symbol="HPG"), "NON_FINANCE")
        self.assertEqual(detect_accounting_regime(symbol="VNM"), "NON_FINANCE")
        self.assertEqual(detect_accounting_regime(symbol="FPT"), "NON_FINANCE")

    def test_02_detect_accounting_regime_text_headers(self):
        """Tests regime detection from PDF title and text content."""
        bank_text = "NGÂN HÀNG THƯƠNG MẠI CỔ PHẦN QUÂN ĐỘI BÁO CÁO TÀI CHÍNH HỢP NHẤT Thông tư 49/2014/TT-NHNN B 01/TCTD"
        self.assertEqual(detect_accounting_regime(text_sample=bank_text), "BANK")

        sec_text = "CÔNG TY CỔ PHẦN CHỨNG KHOÁN SSI BÁO CÁO TÀI CHÍNH Thông tư 334/2016/TT-BTC B 01/CTCK FVTPL CHO VAY KÝ QUỸ"
        self.assertEqual(detect_accounting_regime(text_sample=sec_text), "SECURITIES")

        gen_text = "TẬP ĐOÀN HÒA PHÁT BÁO CÁO TÀI CHÍNH HỢP NHẤT Thông tư 200/2014/TT-BTC B 01 - DN"
        self.assertEqual(detect_accounting_regime(text_sample=gen_text), "NON_FINANCE")

    def test_03_banking_forensic_triangles(self):
        """Tests the 5 banking-specific forensic triangles under Circular 49/NHNN."""
        mock_bank_bctc = {
            "symbol": "MBB",
            "accounting_regime": "BANK",
            "balance_sheet": {
                "items": {
                    250: {"code": 250, "current_val": 850_000_000_000_000.0}, # Total Assets
                    400: {"code": 400, "current_val": 95_000_000_000_000.0},  # Equity
                    150: {"code": 150, "current_val": 600_000_000_000_000.0}, # Loans net
                    151: {"code": 151, "current_val": 612_000_000_000_000.0}, # Loans gross
                    152: {"code": 152, "current_val": -12_000_000_000_000.0}, # Loan loss reserves
                    320: {"code": 320, "current_val": 580_000_000_000_000.0}, # Customer deposits
                    200: {"code": 200, "current_val": 4_500_000_000_000.0}    # Accrued interest
                }
            },
            "income_statement": {
                "revenue_vnd": 45_000_000_000_000.0,
                "net_interest_income_vnd": 45_000_000_000_000.0,
                "ppop_vnd": 32_000_000_000_000.0,
                "provision_expense_vnd": 7_000_000_000_000.0,
                "pbt_vnd": 25_000_000_000_000.0,
                "npat_vnd": 20_000_000_000_000.0
            },
            "bank_npl_footnotes": {
                "npl_loans_vnd": 9_500_000_000_000.0,
                "npl_ratio_pct": 1.55,
                "llr_coverage_ratio_pct": 126.3
            }
        }

        triangles = calculate_forensic_triangles(mock_bank_bctc, company_form="BANK")
        self.assertEqual(triangles["regime"], "BANK")
        self.assertIn("npl_provision_triangle", triangles)
        self.assertIn("casa_cost_of_funds_triangle", triangles)
        self.assertIn("accrued_interest_fraud_triangle", triangles)
        self.assertIn("capital_adequacy_basel2_triangle", triangles)
        self.assertIn("agm_fulfillment_triangle", triangles)

        # Verify NPL and LLR
        npl_t = triangles["npl_provision_triangle"]
        self.assertLessEqual(npl_t["npl_ratio_pct"], 2.0)
        self.assertGreaterEqual(npl_t["llr_coverage_pct"], 100.0)
        self.assertTrue(npl_t["is_healthy"])

        # Verify Accrued Interest (Accrued < 15% NII -> Safe)
        acc_t = triangles["accrued_interest_fraud_triangle"]
        self.assertFalse(acc_t["is_flagged"])
        self.assertIn("SAFE", acc_t["fraud_risk_level"])

    def test_04_securities_forensic_triangles(self):
        """Tests the 5 securities-specific forensic triangles under Circular 334/BTC."""
        mock_sec_bctc = {
            "symbol": "SSI",
            "accounting_regime": "SECURITIES",
            "balance_sheet": {
                "items": {
                    270: {"code": 270, "current_val": 60_000_000_000_000.0},
                    400: {"code": 400, "current_val": 22_000_000_000_000.0},
                    110: {"code": 110, "current_val": 18_000_000_000_000.0}, # FVTPL
                    112: {"code": 112, "current_val": 25_000_000_000_000.0}, # Margin
                    312: {"code": 312, "current_val": 30_000_000_000_000.0}  # Short-term debt
                }
            },
            "income_statement": {
                "revenue_vnd": 7_500_000_000_000.0,
                "brokerage_revenue_vnd": 2_100_000_000_000.0,
                "operating_expense_vnd": 1_400_000_000_000.0,
                "financial_expense_vnd": 1_800_000_000_000.0,
                "pbt_vnd": 3_200_000_000_000.0,
                "npat_vnd": 2_600_000_000_000.0
            }
        }

        triangles = calculate_forensic_triangles(mock_sec_bctc, company_form="SECURITIES")
        self.assertEqual(triangles["regime"], "SECURITIES")
        self.assertIn("margin_leverage_triangle", triangles)
        self.assertIn("fvtpl_asset_quality_triangle", triangles)
        self.assertIn("brokerage_commission_triangle", triangles)
        self.assertIn("borrowing_cost_triangle", triangles)

        # Verify Margin Leverage (25T / 22T = 113.6% < 200% legal cap)
        m_t = triangles["margin_leverage_triangle"]
        self.assertLess(m_t["margin_to_equity_pct"], 200.0)
        self.assertIn("SAFE", m_t["leverage_status"])

    def test_05_real_estate_forensic_triangles(self):
        """Tests the 5 real estate forensic triangles (WIP Landbank & Bond Wall)."""
        mock_re_bctc = {
            "symbol": "VHM",
            "accounting_regime": "REAL_ESTATE",
            "balance_sheet": {
                "items": {
                    270: {"code": 270, "current_val": 450_000_000_000_000.0},
                    400: {"code": 400, "current_val": 180_000_000_000_000.0},
                    140: {"code": 140, "current_val": 70_000_000_000_000.0},  # Inventory WIP
                    312: {"code": 312, "current_val": 28_000_000_000_000.0},  # Customer advances
                    110: {"code": 110, "current_val": 25_000_000_000_000.0},  # Cash
                    320: {"code": 320, "current_val": 20_000_000_000_000.0},
                    338: {"code": 338, "current_val": 40_000_000_000_000.0}
                }
            },
            "debt_schedule_footnotes": [
                {"lender": "Trái phiếu VinHomes 2024", "amount_vnd": 12_000_000_000_000.0}
            ],
            "income_statement": {
                "revenue_vnd": 110_000_000_000_000.0,
                "npat_vnd": 35_000_000_000_000.0,
                "interest_expense_vnd": 3_500_000_000_000.0
            }
        }

        triangles = calculate_forensic_triangles(mock_re_bctc, company_form="REAL_ESTATE")
        self.assertEqual(triangles["regime"], "REAL_ESTATE")
        self.assertIn("landbank_wip_advances_triangle", triangles)
        self.assertIn("bond_refinancing_wall_triangle", triangles)
        self.assertIn("capitalized_interest_triangle", triangles)

        # Advances to Inventory = 28T / 70T = 40.0% (> 30% -> Excellent absorption)
        wip_t = triangles["landbank_wip_advances_triangle"]
        self.assertGreaterEqual(wip_t["advances_to_inventory_pct"], 30.0)

        # Bond coverage = 25T Cash / 12T Bond = 2.08x (> 1.2x -> Safe)
        bond_t = triangles["bond_refinancing_wall_triangle"]
        self.assertGreaterEqual(bond_t["bond_coverage_ratio"], 1.2)

    def test_06_dossier_integration_and_api(self):
        """Tests that get_stock_forensic_dossier and get_company_forensic_report return sector metadata."""
        # Bank
        bank_report = get_company_forensic_report("MBB")
        self.assertEqual(bank_report["company_form"], "BANK")
        self.assertEqual(bank_report["company_form_name"], "Ngân hàng Thương mại")
        self.assertGreaterEqual(bank_report["accounting_integrity_score"], 50)

        # Securities
        sec_report = get_company_forensic_report("SSI")
        self.assertEqual(sec_report["company_form"], "SECURITIES")
        self.assertEqual(sec_report["company_form_name"], "Công ty Chứng khoán")

        # Real Estate
        re_report = get_company_forensic_report("VHM")
        self.assertEqual(re_report["company_form"], "REAL_ESTATE")
        self.assertEqual(re_report["company_form_name"], "Bất động sản Dự án")

        # Industrial
        ind_report = get_company_forensic_report("HPG")
        self.assertEqual(ind_report["company_form"], "NON_FINANCE")


if __name__ == "__main__":
    unittest.main()
