"""OCR spacing must not decide whether a statement is found.

Run 35219855885 parsed FPT's Q4 2025 parent-company filing: a real BCTC,
29 pages, correctly typed SCANNED_IMAGE, with the OCR engine loaded and
reading well - 189 lines on one page. Every statement list came back empty
and all three extractors returned zero items, because RapidOCR had written
the headings without their spaces and the keyword lists carry spaces.

These are the exact strings from that run's log.
"""

from services.bctc_pdf_parser import squash


class TestSquashMatchesWhatOCRActuallyProduced:

    def test_the_heading_ocr_ran_together_still_matches(self):
        page = squash("CONGTY COPHANFPT BAOCAOTAICHINHRIENG PhurongDichVong")
        assert squash("bao cao tai chinh") in page

    def test_the_same_heading_spaced_normally_also_matches(self):
        page = squash("CONG TY CO PHAN FPT BAO CAO TAI CHINH CONG TYME")
        assert squash("bao cao tai chinh") in page

    def test_accents_and_spacing_are_both_removed(self):
        assert squash("Bảng cân đối kế toán") == "BANGCANDOIKETOAN"

    def test_form_codes_survive_either_spelling(self):
        assert squash("Mẫu số B 01") == squash("MAUSOB01")

    def test_none_and_empty_are_not_errors(self):
        assert squash(None) == ""
        assert squash("") == ""
