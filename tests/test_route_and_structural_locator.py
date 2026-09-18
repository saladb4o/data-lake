"""Two failures run 35301809165 separated, and neither was the locator's keywords.

The run printed the native text layer page by page for the documents that
returned nothing, and the two symbols failing turned out to be failing in
opposite directions.

PVS: every page from 2 to 13 of both filings held exactly 82 characters,
the same e-office stamp each time. The statements are images under it. The
covering letter on pages 0 and 1 carries real text, which was enough for
the density test to call a 110-page scan NATIVE - and once it is NATIVE
the OCR pass never runs, because that pass is gated on the document being
classified scanned.

BSR: the figures are all present in the text layer - "100 /
70.173.060.674.346" on page 3 - and the heading is not. The embedded font
drops accented characters, so "Mau so B 01a-DN/HN" arrives as "-DN/HN" and
"BANG CAN DOI KE TOAN" is not there in any spelling. The one page the
locator did return was a notes page keeping a fragment.
"""

import os
import tempfile

import pytest

from services.bctc_pdf_parser import (
    BCTCPdfParser,
    NATIVE_MIN_OWN_CHARS,
    looks_like_a_statement_table,
    page_own_text,
    repeated_overlay_lines,
    statement_from_its_rows,
)

fitz = pytest.importorskip("fitz")

# The exact stamp, from the run's log.
STAMP = ("Văn bản được tải lên hệ thống eoffice.ptsc.com.vn. "
         "Với số định danh: 35/CV-TK/2026")


class TestAnOverlayIsNotThePagesOwnText:
    def test_a_line_on_most_pages_is_found_to_be_an_overlay(self):
        pages = [f"{STAMP}\nreal content {i}" for i in range(10)]
        assert STAMP in repeated_overlay_lines(pages)

    def test_a_line_on_one_page_is_not(self):
        pages = [STAMP] + [f"page {i} of the report" for i in range(9)]
        assert STAMP not in repeated_overlay_lines(pages)

    def test_a_page_number_repeating_is_not_treated_as_an_overlay(self):
        # Short lines are excluded by length, or every document would
        # lose its code column.
        pages = [f"100\n{STAMP}" for _ in range(8)]
        assert "100" not in repeated_overlay_lines(pages)

    def test_a_document_too_short_to_tell_keeps_everything(self):
        pages = [STAMP, STAMP]
        assert repeated_overlay_lines(pages) == set()

    def test_subtracting_the_overlay_empties_a_stamp_only_page(self):
        own = page_own_text(STAMP, {STAMP})
        assert own.strip() == ""

    def test_the_stamp_alone_would_otherwise_pass_the_threshold(self):
        # 82 characters against a floor of 40: the reason the density test
        # was fooled rather than merely borderline.
        assert len(STAMP) > NATIVE_MIN_OWN_CHARS


class TestAStampedScanIsNotClassifiedNative:
    @staticmethod
    def _build(tmpdir, stamped_pages=12):
        path = os.path.join(tmpdir, "stamped.pdf")
        doc = fitz.open()
        for n in range(2):
            page = doc.new_page()
            page.insert_text((40, 80), "CONG TY CO PHAN DICH VU KY THUAT", fontsize=11)
            page.insert_text((40, 100), "Cong van so 35/CV-TK ve viec cong bo", fontsize=11)
            page.insert_text((40, 120), "thong tin bao cao tai chinh nam 2025", fontsize=11)
            page.insert_text((40, 140), "kinh gui Uy ban Chung khoan Nha nuoc", fontsize=11)
            page.insert_text((40, 160), STAMP, fontsize=8)
        for _ in range(stamped_pages):
            doc.new_page().insert_text((40, 80), STAMP, fontsize=8)
        doc.save(path)
        doc.close()
        return path

    def test_the_document_is_classified_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            parser = BCTCPdfParser(self._build(tmp), symbol="PVS")
        assert parser.doc_type in ("SCANNED_IMAGE", "SCANNED")

    def test_the_stamp_is_identified_as_the_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            parser = BCTCPdfParser(self._build(tmp), symbol="PVS")
        assert any("eoffice" in line for line in parser.overlay_lines)

    def test_a_genuinely_native_document_is_still_native(self):
        # The guard against fixing PVS by breaking REE.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "native.pdf")
            doc = fitz.open()
            for n in range(12):
                page = doc.new_page()
                for row in range(14):
                    page.insert_text((40, 60 + row * 14),
                                     f"Khoan muc thu {row} cua trang {n} "
                                     f"{row}0 1.234.567.890.123", fontsize=9)
                page.insert_text((40, 300), STAMP, fontsize=8)
            doc.save(path)
            doc.close()
            parser = BCTCPdfParser(path, symbol="REE")
        assert parser.doc_type == "NATIVE"


class TestATableIsRecognisedByItsShape:
    BSR_PAGE = """CONG TY
-DN/HN
(100=110+120+130+140+150) 100 70.173.060.674.346
110 5.123.456.789.012
120 1.234.567.890.123
130 2.345.678.901.234
140 3.456.789.012.345
150 4.567.890.123.456
TONG CONG TAI SAN 270 70.173.060.674.346
NO PHAI TRA 300 24.583.223.364.493
VON CHU SO HUU 400 45.589.837.309.853
TONG CONG NGUON VON 440 70.173.060.674.346"""

    def test_bsrs_balance_sheet_page_is_recognised(self):
        assert looks_like_a_statement_table(self.BSR_PAGE)
        assert statement_from_its_rows(self.BSR_PAGE) == "balance_sheet"

    def test_its_heading_really_is_absent(self):
        # The premise: there is nothing here for a heading match to find.
        from services.bctc_pdf_parser import squash
        assert squash("BANG CAN DOI KE TOAN") not in squash(self.BSR_PAGE)
        assert squash("MAU SO B 01") not in squash(self.BSR_PAGE)

    def test_an_income_page_is_told_from_a_balance_sheet(self):
        page = """1. Doanh thu ban hang va cung cap dich vu 01 37.621.442.333.111
2. Cac khoan giam tru doanh thu 02 1.442.333.111.222
Gia von hang ban 11 30.621.442.333.111
Loi nhuan gop 20 7.000.000.000.111
Doanh thu hoat dong tai chinh 21 1.621.442.333.111
Chi phi ban hang 25 2.621.442.333.111
Chi phi quan ly doanh nghiep 26 3.621.442.333.111"""
        assert statement_from_its_rows(page) == "income_statement"

    def test_a_cash_flow_page_is_told_from_an_income_statement(self):
        page = """Loi nhuan truoc thue 01 5.947.023.409.069
Khau hao tai san co dinh 02 2.201.442.333.111
Tien chi de mua sam xay dung tai san co dinh 21 1.201.442.333.111
Tien thu tu di vay 33 127.884.103.960.387
Tien chi tra no goc vay 34 133.236.468.791.732
Luu chuyen tien thuan trong ky 50 3.236.468.791.732
Tien va tuong duong tien cuoi ky 70 4.236.468.791.732"""
        assert statement_from_its_rows(page) == "cash_flow"

    def test_prose_with_a_few_numbers_is_not_a_table(self):
        page = ("Trong nam Cong ty da dau tu 1.234.567.890.123 dong vao "
                "nha may loc dau, tang 12 phan tram so voi nam truoc.")
        assert not looks_like_a_statement_table(page)

    def test_a_table_that_says_nothing_about_itself_is_left_alone(self):
        # Income statement and cash flow both number their lines 1 to 70.
        # Guessing binds rows into the wrong statement, which is worse
        # than leaving the page to nobody.
        page = "\n".join(f"{c} 1.234.567.890.123" for c in
                         (1, 2, 10, 11, 20, 21, 30, 40, 50))
        assert looks_like_a_statement_table(page)
        assert statement_from_its_rows(page) is None

    def test_a_note_reference_beside_a_year_is_not_a_row(self):
        page = "\n".join(f"Thuyet minh {n} nam 2025 tang 5 phan tram"
                         for n in range(1, 12))
        assert not looks_like_a_statement_table(page)


class TestTheStructuralPassNeverOverrulesAHeading:
    @staticmethod
    def _build(tmpdir, with_heading):
        path = os.path.join(tmpdir, "bsr.pdf")
        doc = fitz.open()
        doc.new_page().insert_text((40, 80), "CONG TY CO PHAN LOC HOA DAU",
                                   fontsize=11)
        page = doc.new_page()
        if with_heading:
            page.insert_text((40, 60), "BANG CAN DOI KE TOAN", fontsize=13)
        for row, line in enumerate(
                TestATableIsRecognisedByItsShape.BSR_PAGE.splitlines()):
            page.insert_text((40, 90 + row * 13), line, fontsize=9)
        doc.save(path)
        doc.close()
        return path

    def test_a_page_with_no_readable_heading_is_found_by_its_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            parser = BCTCPdfParser(self._build(tmp, False), symbol="BSR")
            found = parser.locate_statement_pages()
        assert found["balance_sheet"] == [1]
        assert parser.located_by[1] == "table"

    def test_a_readable_heading_is_what_locates_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            parser = BCTCPdfParser(self._build(tmp, True), symbol="BSR")
            found = parser.locate_statement_pages()
        assert found["balance_sheet"] == [1]
        assert parser.located_by[1] == "heading"

    def test_a_statement_located_by_heading_is_not_added_to_structurally(self):
        # A document whose headings were read is located by its headings,
        # so a notes page shaped like a table cannot join the list.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mixed.pdf")
            doc = fitz.open()
            head = doc.new_page()
            head.insert_text((40, 60), "BANG CAN DOI KE TOAN", fontsize=13)
            head.insert_text((40, 90), "TONG CONG TAI SAN 270 1.000.000.000.000",
                             fontsize=9)
            notes = doc.new_page()
            for row, line in enumerate(
                    TestATableIsRecognisedByItsShape.BSR_PAGE.splitlines()):
                notes.insert_text((40, 60 + row * 13), line, fontsize=9)
            doc.save(path)
            doc.close()
            found = BCTCPdfParser(path, symbol="BSR").locate_statement_pages()
        assert found["balance_sheet"] == [0]
