"""
=============================================================================
UNIT TESTS: CORPORATE DISCLOSURES PARSER (NON-BCTC ENGINE)
=============================================================================
Verifies deterministic extraction of:
  - AGM & Board Resolutions (Doanh thu kế hoạch, LNST kế hoạch, Cổ tức mục tiêu, Góp vốn cty con).
  - Corporate Governance Reports (Thông tư 96/2020: Giao dịch các bên liên quan, Danh sách HĐQT).
  - Dividend Announcements (Ngày GDKHQ, tỷ lệ chi trả tiền mặt / cổ phiếu).
"""

import os
import tempfile
import pytest
import fitz

from services.corporate_disclosures_parser import CorporateDisclosuresParser
from services.bctc_batch_processor import BCTCBatchProcessor


@pytest.fixture
def synthetic_agm_pdf():
    """Generates a synthetic AGM resolution PDF."""
    doc = fitz.open()
    page = doc.new_page()
    text = """
CONG HOA XA HOI CHU NGHIA VIET NAM
Doc lap - Tu do - Hanh phuc
---
NGHI QUYET DAI HOI DONG CO DONG THUONG NIEN NAM 2026

Ngay 25 thang 04 nam 2026, Dai hoi dong co dong thong qua cac noi dung:

Dieu 1: Thong qua ke hoach san xuat kinh doanh nam 2026:
- Tong doanh thu ke hoach: 25.000 ty dong.
- Loi nhuan sau thue hop nhat ke hoach: 3.200 ty dong.

Dieu 2: Thong qua phuong an phan phoi loi nhuan va chi tra co tuc:
- Chi tra co tuc bang tien ty le: 15% (tuong duong 1.500 dong/co phieu).

Dieu 3: Thong qua phuong an gop von thanh lap cong ty con:
- Ten cong ty: CTCP Cong Nghe Cao An Binh
- So tien gop von: 500 ty dong, ty le so huu: 80%.

Dieu 4: Thong qua phuong an phat hanh trai phieu rieng le han muc: 1.000 ty dong.
    """
    page.insert_text((50, 50), text, fontsize=10)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    doc.save(tmp_path)
    doc.close()
    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


@pytest.fixture
def synthetic_governance_pdf():
    """Generates a synthetic Corporate Governance Report PDF adhering to Circular 96."""
    doc = fitz.open()
    page = doc.new_page()
    text = """
BAO CAO TINH HINH QUAN TRI CONG TY 6 THANG DAU NAM 2026
(Ban hanh kem theo Thong tu so 96/2020/TT-BTC)

I. Hoat dong cua Hoi dong quan tri:
1. Chu tich HDQT - Ong Nguyen Van A
2. Thanh vien doc lap HDQT - Ba Tran Thi B

VIII. Giao dich giua cong ty voi nguoi co lien quan:
1. CTCP Bat Dong San Sen Vang (Cong ty co cung thanh vien HDQT):
   Hop dong thi cong xay lap so 12/2026, gia tri: 120.000.000.000 VND.
2. Cong ty TNHH Dau tu Thuong mai Hai Phat:
   Giao dich mua ban vat tu, gia tri: 45.000.000.000 VND.
    """
    page.insert_text((50, 50), text, fontsize=10)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    doc.save(tmp_path)
    doc.close()
    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


@pytest.fixture
def synthetic_dividend_pdf():
    """Generates a synthetic Ex-Dividend notice PDF."""
    doc = fitz.open()
    page = doc.new_page()
    text = """
THONG BAO NGAY DANG KY CUOI CUNG THUC HIEN QUYEN TRA CO TUC

1. Ten to chuc phat hanh: TAP DOAN CONG NGHE A CHAU
2. Ma chung khoan: AAA
3. Ngay giao dich khong huong quyen: 15/09/2026
4. Ngay dang ky cuoi cung: 16/09/2026
5. Ly do va muc dich: Chi tra co tuc nam 2025 bang tien mat
6. Ty le thuc hien: 12% (01 co phieu duoc nhan 1.200 dong/co phieu)
7. Ngay thanh toan: 10/10/2026
    """
    page.insert_text((50, 50), text, fontsize=10)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    doc.save(tmp_path)
    doc.close()
    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


def test_agm_resolution_extraction(synthetic_agm_pdf):
    parser = CorporateDisclosuresParser(synthetic_agm_pdf)
    res = parser.extract_agm_resolution()

    assert res["target_revenue_vnd"] == 25_000_000_000_000.0  # 25,000 tỷ
    assert res["target_npat_vnd"] == 3_200_000_000_000.0       # 3,200 tỷ
    assert res["target_dividend_rate_pct"] == 15.0
    assert res["dividend_payout_form"] == "CASH"
    assert res["resolution_date"] == "25/04/2026"

    # Subsidiary investment
    assert len(res["subsidiary_investments"]) >= 1
    sub = res["subsidiary_investments"][0]
    assert sub["capital_contribution_vnd"] == 500_000_000_000.0  # 500 tỷ
    assert sub["target_ownership_pct"] == 80.0

    # Bond credit limit
    assert len(res["bond_and_credit_limits"]) >= 1
    assert res["bond_and_credit_limits"][0]["limit_vnd"] == 1_000_000_000_000.0  # 1,000 tỷ


def test_governance_report_extraction(synthetic_governance_pdf):
    parser = CorporateDisclosuresParser(synthetic_governance_pdf)
    gov = parser.extract_governance_report()

    assert gov["period"] == "Bán niên"
    assert len(gov["board_members"]) >= 2
    assert any("Nguyễn Văn A" in m["name"] or "Chu tich" in m["title"] for m in gov["board_members"])

    # Related party transactions
    assert len(gov["related_party_transactions"]) >= 2
    rpt1 = gov["related_party_transactions"][0]
    assert "Sen Vàng" in rpt1["entity_name"] or "Sen Vang" in rpt1["entity_name"]
    assert rpt1["transaction_value_vnd"] == 120_000_000_000.0


def test_dividend_announcement_extraction(synthetic_dividend_pdf):
    parser = CorporateDisclosuresParser(synthetic_dividend_pdf)
    div = parser.extract_dividend_announcement()

    assert div["payout_form"] == "CASH"
    assert div["ex_dividend_date"] == "15/09/2026"
    assert div["record_date"] == "16/09/2026"
    assert div["payment_date"] == "10/10/2026"
    assert div["dividend_rate_pct"] == 12.0
    assert div["cash_value_per_share_vnd"] == 1200.0


def test_full_report_dispatcher(synthetic_agm_pdf, synthetic_dividend_pdf):
    p1 = CorporateDisclosuresParser(synthetic_agm_pdf)
    rep1 = p1.extract_full_report()
    assert rep1["detected_category"] == "RESOLUTION"
    assert "resolution_data" in rep1

    p2 = CorporateDisclosuresParser(synthetic_dividend_pdf)
    rep2 = p2.extract_full_report()
    assert rep2["detected_category"] == "DIVIDEND"
    assert "dividend_data" in rep2
