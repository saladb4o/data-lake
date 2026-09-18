"""The native vector route, which found almost nothing until now.

Run 35222930322 parsed six native documents across REE, PVS and BSR and
got 44 items out of all of them together - two of BSR's produced nothing
at all - while the OCR route was returning forty-plus items per document.
The spacing fix before it had only touched the OCR pass.

The cause is the same bug in a different disguise. A PDF heading is
typeset as separate text runs, so `get_text()` hands back "LUU CHUYEN\\nTIEN
TE" where the page shows one centred line, and a keyword written with a
space matches neither that nor the run-together spelling. On top of it the
two passes had drifted: the native pass demanded the whole of "BANG CAN
DOI KE TOAN" while the OCR pass accepted "BANG CAN DOI", so some headings
were reachable only if the document happened to be a scan.
"""

import os
import tempfile

import pytest

from services.bctc_pdf_parser import (
    FOOTNOTE_HEADINGS,
    STATEMENT_HEADINGS,
    squash,
)

fitz = pytest.importorskip("fitz")


def _matches(page_text: str, key: str) -> bool:
    """The match both passes of the locator now perform."""
    squashed = squash(page_text)
    return any(squash(k) in squashed for k in STATEMENT_HEADINGS[key])


class TestHeadingsBrokenAcrossLines:
    """What get_text() actually returns for a typeset heading."""

    @pytest.mark.parametrize("page,key", [
        ("BAO CAO LUU CHUYEN\nTIEN TE HOP NHAT", "cash_flow"),
        ("BANG CAN DOI\nKE TOAN HOP NHAT", "balance_sheet"),
        ("BAO CAO KET QUA HOAT DONG\nKINH DOANH", "income_statement"),
        ("BAO CAO\nKIEM TOAN DOC LAP", "auditor_report"),
    ])
    def test_a_heading_split_by_a_newline_is_found(self, page, key):
        assert _matches(page, key)

    @pytest.mark.parametrize("page,key", [
        ("BÁO CÁO LƯU CHUYỂN TIỀN TỆ", "cash_flow"),
        ("BẢNG CÂN ĐỐI KẾ TOÁN", "balance_sheet"),
        ("BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH", "income_statement"),
    ])
    def test_accented_headings_are_still_found(self, page, key):
        assert _matches(page, key)

    def test_the_old_spaced_comparison_is_what_missed_them(self):
        # The regression this guards, stated as the code used to state it.
        page = "BAO CAO LUU CHUYEN\nTIEN TE HOP NHAT"
        assert "LUU CHUYEN TIEN TE" not in page.upper()
        assert _matches(page, "cash_flow")

    def test_form_codes_are_reached_however_they_are_spaced(self):
        for spelling in ("Mẫu số B 03 - DN", "MAU SO B03-DN", "B 03 - TCTD"):
            assert _matches(spelling, "cash_flow")


class TestTheTwoPassesShareOneKeywordList:
    """They had drifted, and the drift was invisible from either side."""

    def test_the_partial_balance_sheet_heading_is_available_to_both(self):
        # The OCR pass accepted this and the native pass did not.
        assert _matches("BANG CAN DOI", "balance_sheet")
        assert _matches("CAN DOI KE TOAN", "balance_sheet")

    def test_every_statement_has_a_vietnamese_and_an_english_heading(self):
        for key in ("balance_sheet", "income_statement", "cash_flow"):
            joined = " ".join(STATEMENT_HEADINGS[key])
            assert any(c in joined for c in ("BANG", "KET QUA", "LUU CHUYEN"))
        assert "BALANCE SHEET" in STATEMENT_HEADINGS["balance_sheet"]
        assert "INCOME STATEMENT" in STATEMENT_HEADINGS["income_statement"]
        assert "CASH FLOW" in STATEMENT_HEADINGS["cash_flow"]

    def test_footnote_headings_are_kept_apart_from_the_statements(self):
        # Footnotes are located over the whole document rather than the
        # first 26 pages, so they are deliberately not in the same dict.
        assert "THUYET MINH" in FOOTNOTE_HEADINGS
        for key in STATEMENT_HEADINGS:
            assert "THUYET MINH" not in STATEMENT_HEADINGS[key]


class TestNoHeadingMatchesUnrelatedProse:
    @pytest.mark.parametrize("prose", [
        "Cong ty da ky hop dong voi don vi kiem toan cho nam 2026",
        "Nghi quyet hoi dong quan tri ve viec lua chon don vi",
        "Thong bao ve viec chi tra co tuc bang tien mat",
    ])
    def test_a_disclosure_notice_is_not_a_statement_page(self, prose):
        for key in ("balance_sheet", "income_statement", "cash_flow"):
            assert not _matches(prose, key)


class TestOnARealVectorPdf:
    """End to end, on a PDF built here rather than a described one.

    Unaccented text is used deliberately: the point under test is the
    newline inside the heading, and a base-14 font would not carry
    Vietnamese glyphs to begin with.
    """

    @staticmethod
    def _build(tmpdir: str) -> str:
        path = os.path.join(tmpdir, "native.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "CONG TY CO PHAN MAU", fontsize=12)
        page.insert_text((72, 130), "BANG CAN DOI", fontsize=14)
        page.insert_text((72, 150), "KE TOAN HOP NHAT", fontsize=14)
        page2 = doc.new_page()
        page2.insert_text((72, 100), "BAO CAO LUU CHUYEN", fontsize=14)
        page2.insert_text((72, 120), "TIEN TE HOP NHAT", fontsize=14)
        doc.save(path)
        doc.close()
        return path

    def test_get_text_really_does_break_the_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            with fitz.open(self._build(tmp)) as doc:
                text = doc[1].get_text()
        # The premise of the whole fix, asserted rather than assumed.
        assert "LUU CHUYEN TIEN TE" not in text.upper()
        assert squash("LUU CHUYEN TIEN TE") in squash(text)

    def test_the_locator_finds_both_statements(self):
        from services.bctc_pdf_parser import BCTCPdfParser
        with tempfile.TemporaryDirectory() as tmp:
            parser = BCTCPdfParser(self._build(tmp), symbol="TEST")
            found = parser.locate_statement_pages()
        assert 0 in found["balance_sheet"]
        assert 1 in found["cash_flow"]


class TestTheLateHeadingFallback:
    """Past page 26 a heading counts only when nothing was found before it.

    An audited consolidated report can run past a hundred pages with a long
    bilingual front section. The window that keeps a note's cross-reference
    from being read as the statement is then the thing hiding it.
    """

    @staticmethod
    def _build(tmpdir: str, heading_pages) -> str:
        path = os.path.join(tmpdir, "long.pdf")
        doc = fitz.open()
        for i in range(32):
            page = doc.new_page()
            if i in heading_pages:
                page.insert_text((72, 100), "BAO CAO LUU CHUYEN", fontsize=14)
                page.insert_text((72, 120), "TIEN TE HOP NHAT", fontsize=14)
            else:
                page.insert_text((72, 100), f"trang {i}", fontsize=11)
        doc.save(path)
        doc.close()
        return path

    def _locate(self, tmpdir, heading_pages):
        from services.bctc_pdf_parser import BCTCPdfParser
        parser = BCTCPdfParser(self._build(tmpdir, heading_pages), symbol="TEST")
        return parser.locate_statement_pages()

    def test_a_heading_only_past_the_window_is_still_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = self._locate(tmp, {28})
        assert found["cash_flow"] == [28]

    def test_an_early_heading_keeps_the_late_one_out(self):
        # The ordinary case must not change: the fallback fires only on an
        # empty result, so a cross-reference in the notes stays excluded.
        with tempfile.TemporaryDirectory() as tmp:
            found = self._locate(tmp, {4, 28})
        assert found["cash_flow"] == [4]

    def test_the_fallback_does_not_invent_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = self._locate(tmp, set())
        assert found["cash_flow"] == []
        assert found["balance_sheet"] == []
