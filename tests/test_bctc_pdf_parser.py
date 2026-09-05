"""
=============================================================================
TEST SUITE: BCTC DETERMINISTIC NON-LLM PDF PARSER
=============================================================================
Tests Vietnamese accounting number parsing, currency detection, TT200 code
mapping, auditor risk classification, and end-to-end synthetic PDF parsing.
"""

import os
import tempfile
import pytest
import fitz  # PyMuPDF

from services.bctc_pdf_parser import (
    parse_vietnamese_accounting_number,
    detect_currency_unit,
    BCTCPdfParser,
    TT200_BALANCE_SHEET_CODES,
    TT200_INCOME_CODES,
)
from services.bctc_batch_processor import BCTCBatchProcessor


# ---------------------------------------------------------------------------
# 1. Number Parsing Tests
# ---------------------------------------------------------------------------

def test_parse_vietnamese_accounting_number_standard_integer():
    assert parse_vietnamese_accounting_number("1.234.567.890") == 1234567890.0
    assert parse_vietnamese_accounting_number("500.000") == 500000.0
    assert parse_vietnamese_accounting_number("0") == 0.0


def test_parse_vietnamese_accounting_number_parenthesized_negative():
    assert parse_vietnamese_accounting_number("(123.456.789)") == -123456789.0
    assert parse_vietnamese_accounting_number("(50.000)") == -50000.0
    assert parse_vietnamese_accounting_number("-45.600") == -45600.0


def test_parse_vietnamese_accounting_number_dashes_and_nulls():
    assert parse_vietnamese_accounting_number("-") == 0.0
    assert parse_vietnamese_accounting_number("--") == 0.0
    assert parse_vietnamese_accounting_number("—") == 0.0
    assert parse_vietnamese_accounting_number("nil") == 0.0
    assert parse_vietnamese_accounting_number("không") == 0.0
    assert parse_vietnamese_accounting_number(None) is None


def test_parse_vietnamese_accounting_number_decimal_commas():
    assert parse_vietnamese_accounting_number("1.234,56") == 1234.56
    assert parse_vietnamese_accounting_number("(1.234,56)") == -1234.56


# ---------------------------------------------------------------------------
# 2. Currency Unit Detection Tests
# ---------------------------------------------------------------------------

def test_detect_currency_unit_varieties():
    assert detect_currency_unit("BÁO CÁO TÀI CHÍNH - Đơn vị tính: Tỷ đồng")[1] == 1_000_000_000.0
    assert detect_currency_unit("ĐVT: triệu đồng")[1] == 1_000_000.0
    assert detect_currency_unit("Đơn vị tính: Nghìn VNĐ")[1] == 1_000.0
    assert detect_currency_unit("BẢNG CÂN ĐỐI KẾ TOÁN (ĐVT: Đồng)")[1] == 1.0
    assert detect_currency_unit("Đơn vị tính: USD")[1] == 25_400.0


# ---------------------------------------------------------------------------
# 3. End-to-End Synthetic PDF Parsing Tests (with PyMuPDF)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_synthetic_bctc_pdf(tmp_path):
    """Generates a realistic native Vietnamese BCTC PDF for testing."""
    pdf_file = str(tmp_path / "sample_bctc.pdf")
    doc = fitz.open()

    # Page 1: Bao cao kiem toan doc lap (Independent Audit Report)
    page1 = doc.new_page()
    page1.insert_text((50, 50), "CONG TY TNHH ERNST & YOUNG VIET NAM", fontsize=12)
    page1.insert_text((50, 80), "BAO CAO KIEM TOAN DOC LAP", fontsize=14)
    page1.insert_text((50, 120), "Y kien cua kiem toan vien:\nTheo y kien cua chung toi, Bao cao tai chinh da phan anh trung thuc va hop ly...", fontsize=11)
    page1.insert_text((50, 180), "Van de can nhan manh:\nChung toi luu y nguoi doc ve viec cong ty dang tai cau truc no vay ngan han...", fontsize=11)

    # Page 2: Bang can doi ke toan (Balance Sheet - TT200)
    page2 = doc.new_page()
    page2.insert_text((50, 50), "BANG CAN DOI KE TOAN (MAU SO B 01 - DN)", fontsize=14)
    page2.insert_text((50, 70), "Tai ngay 31 thang 12 nam 2024 - Don vi tinh: Trieu dong", fontsize=10)

    # Draw table text
    y = 100
    rows = [
        ("TAI SAN NGAN HAN", "100", "V.01", "120.000", "100.000"),
        ("Tien va cac khoan tuong duong tien", "110", "V.02", "50.000", "40.000"),
        ("Hang ton kho", "140", "V.04", "70.000", "60.000"),
        ("TAI SAN DAI HAN", "200", "", "80.000", "70.000"),
        ("TAI SAN CO DINH", "220", "V.08", "80.000", "70.000"),
        ("TONG CONG TAI SAN", "270", "", "200.000", "170.000"),
        ("NO PHAI TRA", "300", "", "90.000", "80.000"),
        ("No ngan han", "310", "V.12", "90.000", "80.000"),
        ("VON CHU SO HUU", "400", "V.18", "110.000", "90.000"),
        ("TONG CONG NGUON VON", "440", "", "200.000", "170.000"),
    ]
    for r in rows:
        page2.insert_text((50, y), r[0], fontsize=9)
        page2.insert_text((260, y), r[1], fontsize=9)
        page2.insert_text((310, y), r[2], fontsize=9)
        page2.insert_text((370, y), r[3], fontsize=9)
        page2.insert_text((450, y), r[4], fontsize=9)
        y += 20

    # Page 3: Thuyet minh no vay & BDS do dang
    page3 = doc.new_page()
    page3.insert_text((50, 50), "BAN THUYET MINH BAO CAO TAI CHINH", fontsize=14)
    page3.insert_text((50, 80), "V.12. Vay va no thue tai chinh ngan han:", fontsize=11)
    page3.insert_text((50, 110), "Vay Ngan hang TMCP Ngoai thuong Viet Nam (Vietcombank): 45.000.000.000 dong, ky han 12 thang", fontsize=10)
    page3.insert_text((50, 130), "Vay Ngan hang TMCP Dau tu va Phat trien Viet Nam (BIDV): 25.000.000.000 dong, lai suat 7.5%/nam", fontsize=10)
    page3.insert_text((50, 170), "V.05. Chi phi san xuat, kinh doanh do dang bat dong san:", fontsize=11)
    page3.insert_text((50, 200), "Du an Khu do thi AquaCity: 15.000.000.000 dong", fontsize=10)
    page3.insert_text((50, 220), "Du an Grand Marina: 8.500.000.000 dong", fontsize=10)

    doc.save(pdf_file)
    doc.close()
    return pdf_file


def test_bctc_parser_inspection_and_routing(sample_synthetic_bctc_pdf):
    parser = BCTCPdfParser(sample_synthetic_bctc_pdf)
    assert parser.total_pages == 3
    assert parser.doc_type == "NATIVE"
    assert parser.currency_unit == "TRIỆU_VND"
    assert parser.currency_scale == 1_000_000.0

    pages = parser.locate_statement_pages()
    assert 0 in pages["auditor_report"]
    assert 1 in pages["balance_sheet"]
    assert 2 in pages["footnotes"]


def test_bctc_parser_auditor_opinion_extraction(sample_synthetic_bctc_pdf):
    parser = BCTCPdfParser(sample_synthetic_bctc_pdf)
    audit = parser.extract_auditor_opinion()

    assert audit["is_big4"] is True
    assert "Ernst & Young" in audit["auditor_firm"]
    assert "Unqualified" in audit["opinion_type"]
    assert audit["has_emphasis_of_matter"] is True


def test_bctc_parser_debt_and_landbank_footnotes(sample_synthetic_bctc_pdf):
    parser = BCTCPdfParser(sample_synthetic_bctc_pdf)
    debt = parser.extract_debt_footnotes()
    landbank = parser.extract_landbank_footnotes()

    # Verify bank facilities extracted
    lenders = [d["lender"] for d in debt]
    assert any("Vietcombank" in l or "VCB" in l for l in lenders)
    assert any("BIDV" in l for l in lenders)

    # Verify landbank projects extracted
    projects = [p["project_name"] for p in landbank]
    assert any("AquaCity" in p or "Du an" in p for p in projects)


def test_bctc_parser_full_report_orchestration(sample_synthetic_bctc_pdf):
    parser = BCTCPdfParser(sample_synthetic_bctc_pdf)
    rep = parser.extract_full_report()

    assert rep["document_type"] == "NATIVE"
    assert rep["currency_unit"] == "TRIỆU_VND"
    assert rep["auditor_summary"]["is_big4"] is True
    assert len(rep["debt_schedule_footnotes"]) >= 1
    assert len(rep["landbank_wip_footnotes"]) >= 1


def test_bctc_batch_processor_local_flow(tmp_path, sample_synthetic_bctc_pdf):
    lake_dir = str(tmp_path / "pdf_lake")
    proc = BCTCBatchProcessor(lake_dir=lake_dir)

    # Test local pdf storage
    sym_dir = os.path.join(lake_dir, "TEST")
    os.makedirs(sym_dir, exist_ok=True)
    target_pdf = os.path.join(sym_dir, "2024_Q4.pdf")
    with open(sample_synthetic_bctc_pdf, "rb") as src, open(target_pdf, "wb") as dst:
        dst.write(src.read())

    assert os.path.exists(target_pdf)
    parser = BCTCPdfParser(target_pdf)
    res = parser.extract_full_report()
    assert res["auditor_summary"]["is_big4"] is True


def test_semantic_title_matching_without_code_column(sample_synthetic_bctc_pdf):
    """Verifies that rows lacking numeric code columns are correctly resolved via semantic title matching."""
    parser = BCTCPdfParser(sample_synthetic_bctc_pdf)

    # 1. Balance Sheet: "TỔNG CỘNG TÀI SẢN" without code column
    bs_items = {}
    row_bs = ["TỔNG CỘNG TÀI SẢN", "50.000.000", "40.000.000"]
    parser._parse_balance_sheet_row(row_bs, bs_items)
    assert 270 in bs_items
    assert bs_items[270]["name"] == "TỔNG CỘNG TÀI SẢN"

    # 2. Income Statement: "Doanh thu thuần" without code column
    is_items = {}
    row_is = ["Doanh thu thuần về bán hàng và cung cấp dịch vụ", "100.000.000", "80.000.000"]
    parser._parse_income_row(row_is, is_items)
    assert 10 in is_items
    assert is_items[10]["name"] == "Doanh thu thuần về bán hàng và cung cấp dịch vụ"

    # 3. Cash Flow: "Lưu chuyển tiền thuần từ hoạt động kinh doanh" without code column
    cf_items = {}
    row_cf = ["Lưu chuyển tiền thuần từ hoạt động kinh doanh", "15.000.000", "12.000.000"]
    parser._parse_cash_flow_row(row_cf, cf_items)
    assert 20 in cf_items
    assert "kinh doanh" in cf_items[20]["name"].lower()


def test_negative_keyword_filtering_in_batch_processor():
    """Verifies that corporate explanation memos and notices are filtered out."""
    from services.bctc_batch_processor import BCTC_NEGATIVE_KEYWORDS
    bad_titles = [
        "Công văn giải trình chênh lệch LNST BCTC kiểm toán 2024",
        "Thông báo phát hành BCTC năm 2024",
        "Nghị quyết HĐQT thông qua BCTC soát xét bán niên",
        "Biên bản họp ĐHĐCĐ thường niên 2024",
        "CBTT Báo cáo tài chính quý 4/2024"
    ]
    for title in bad_titles:
        t_low = title.lower()
        assert any(kw in t_low for kw in BCTC_NEGATIVE_KEYWORDS), f"Failed to detect negative keyword in: {title}"

