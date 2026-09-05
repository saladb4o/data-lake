import os
import sys
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.bctc_batch_processor import BCTCBatchProcessor


class TestBCTC10YAnnualCrawler(unittest.TestCase):
    def setUp(self):
        self.processor = BCTCBatchProcessor()

    @patch("services.bctc_batch_processor._fetch_cafef_single_page_raw")
    @patch("services.bctc_batch_processor.fetch_single_detail_pdf")
    def test_01_discover_10y_annual_reports_prioritization_and_filtering(self, mock_fetch_pdf, mock_fetch_pages):
        """Tests that discover_10y_annual_reports selects 1 authoritative audited annual filing per year, preferring consolidated over separate."""
        mock_fetch_pdf.side_effect = lambda url: f"https://example.com/download/{abs(hash(url))}.pdf"

        mock_raw_items = [
            # 2024 filings
            {"title": "HPG: Báo cáo tài chính quý 1/2024", "date": "15/04/2024", "detail_url": "url_q1_24", "audit_badge": None},
            {"title": "HPG: Báo cáo tài chính Công ty mẹ năm 2024 kiểm toán", "date": "20/03/2025", "detail_url": "url_me_24", "audit_badge": "Kiểm toán"},
            {"title": "HPG: Báo cáo tài chính Hợp nhất năm 2024 đã được kiểm toán", "date": "25/03/2025", "detail_url": "url_hn_24", "audit_badge": "Big 4 Audit"},
            {"title": "HPG: Giải trình chênh lệch lợi nhuận năm 2024", "date": "26/03/2025", "detail_url": "url_gt_24", "audit_badge": None},

            # 2023 filings
            {"title": "HPG: BCTC soát xét 6 tháng năm 2023", "date": "15/08/2023", "detail_url": "url_6m_23", "audit_badge": None},
            {"title": "HPG: Báo cáo tài chính Hợp nhất kiểm toán năm 2023", "date": "28/03/2024", "detail_url": "url_hn_23", "audit_badge": "Kiểm toán"},

            # 2022 filings
            {"title": "HPG: Báo cáo tài chính năm 2022 kiểm toán", "date": "29/03/2023", "detail_url": "url_hn_22", "audit_badge": "Kiểm toán"},

            # 2021 filings
            {"title": "HPG: BCTC kiểm toán năm 2021", "date": "30/03/2022", "detail_url": "url_hn_21", "audit_badge": "Kiểm toán"},

            # Irrelevant news
            {"title": "HPG: Khởi công nhà máy gang thép Dung Quất 2", "date": "10/05/2022", "detail_url": "url_news", "audit_badge": None},
        ]

        def mock_page_response(sym, p):
            if p == 1:
                return mock_raw_items[:5]
            elif p == 2:
                return mock_raw_items[5:]
            return []

        mock_fetch_pages.side_effect = mock_page_response

        discovered = self.processor.discover_10y_annual_reports(symbol="HPG", max_pages=2, target_years=5)

        self.assertTrue(len(discovered) >= 4)
        fiscal_years = [d["fiscal_year"] for d in discovered]
        self.assertIn("2024", fiscal_years)
        self.assertIn("2023", fiscal_years)
        self.assertIn("2022", fiscal_years)
        self.assertIn("2021", fiscal_years)

        # Ensure for 2024, Consolidated (Hợp nhất) was chosen over Separate (Công ty mẹ)
        rep_2024 = next(d for d in discovered if d["fiscal_year"] == "2024")
        self.assertEqual(rep_2024["detail_url"], "url_hn_24")
        self.assertTrue("hợp nhất" in rep_2024["title"].lower())
        self.assertTrue(rep_2024["has_pdf"])
        self.assertTrue(rep_2024["pdf_url"].endswith(".pdf"))

    @patch("services.bctc_batch_processor.BCTCBatchProcessor.discover_10y_annual_reports")
    @patch("services.bctc_batch_processor.get_company_reports")
    @patch("services.bctc_batch_processor.BCTCBatchProcessor.download_report_pdf")
    @patch("services.bctc_batch_processor.BCTCPdfParser")
    def test_02_process_single_company_10y_annual_flow(self, mock_parser_cls, mock_download, mock_get_reports, mock_discover):
        """Tests that process_single_company integrates 10y annual reports and recent quarters cleanly."""
        mock_discover.return_value = [
            {"title": "BCTC Hợp nhất kiểm toán năm 2023", "fiscal_year": "2023", "pdf_url": "http://example.com/2023.pdf", "date": "2024-03-25", "audit_badge": "Kiểm toán"},
            {"title": "BCTC Hợp nhất kiểm toán năm 2022", "fiscal_year": "2022", "pdf_url": "http://example.com/2022.pdf", "date": "2023-03-25", "audit_badge": "Kiểm toán"}
        ]
        mock_get_reports.return_value = {
            "reports": [
                {"title": "BCTC Q2/2024", "year": "2024", "pdf_url": "http://example.com/q2_2024.pdf", "date": "2024-07-20", "audit_badge": None}
            ]
        }
        mock_download.return_value = "C:/tmp/mock.pdf"
        
        mock_parser_instance = MagicMock()
        mock_parser_instance.extract_full_report.return_value = {
            "period_info": {"year": "2023", "quarter": None, "period_type": "FY", "is_audited": True},
            "balance_sheet": {"rows": [{"item_code": "100", "current_val": 1000.0, "previous_val": 800.0}]},
            "income_statement": {"rows": [{"item_code": "01", "current_val": 5000.0, "previous_val": 4200.0}]}
        }
        mock_parser_cls.return_value = mock_parser_instance

        with patch("services.bctc_batch_processor._get_lake_data", return_value={}), \
             patch("services.bctc_batch_processor._save_lake_data"):
            res = self.processor.process_single_company(symbol="HPG", max_reports=2, fetch_10y_annual=True)

            self.assertEqual(res["symbol"], "HPG")
            self.assertTrue(res["reports_processed"] >= 2)
            mock_discover.assert_called_once_with(symbol="HPG", max_pages=70, target_years=10)

    def test_03_crawler_script_argument_parsing(self):
        """Tests that scripts/bctc_worker_crawler.py supports --crawl-10y-annual flag."""
        import subprocess
        cmd = [sys.executable, "scripts/bctc_worker_crawler.py", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--crawl-10y-annual", result.stdout)


if __name__ == "__main__":
    unittest.main()
