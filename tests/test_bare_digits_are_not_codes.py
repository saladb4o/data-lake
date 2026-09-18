"""A bare digit is a code or a page number, and the line cannot say which.

This is the defect behind the misbound cash flow rows. Any one or two
digit line was read as a TT200 code and took whatever figure followed, so
page numbers and note references became rows. The evidence is the order
the items came back in on FPT's Q4 2025 parent-only filing, in run
35220475916's log:

    1, 2, 3, 60, 20, 21

Code 60 bound before code 20 on a statement that prints them the other
way round, and code 1 held 1,905,249,672,046 - which is code 70's closing
cash balance. Both rows counted as extracted, and the opening-balance
identity missed by 1.8 trillion because of them.

What separates a code from a page number is not the digits but what
surrounds them: a statement row prints a label, then its code, then its
figures, while a page number stands alone at the foot of the page.
"""

from services.bctc_pdf_parser import BCTCPdfParser


def _rows(lines):
    """What the OCR parser makes of a page's lines."""
    parser = BCTCPdfParser.__new__(BCTCPdfParser)
    parser.currency_scale = 1.0
    items = {}
    BCTCPdfParser._parse_ocr_lines_for_cash_flow(parser, lines, items)
    return items


class TestARealRowIsStillRead:
    LINES = [
        "III. Luu chuyen tien tu hoat dong tai chinh",
        "Tien thu tu di vay",
        "33",
        "14.269.573.627.370",
        "12.100.000.000.000",
        "Tien chi tra no goc vay",
        "34",
        "(13.444.286.187.170)",
        "(11.900.000.000.000)",
        "Luu chuyen tien thuan trong ky",
        "50",
        "27.455.185.600",
        "19.000.000.000",
        "Ban thuyet minh dinh kem la bo phan hop thanh",
    ]

    def test_the_codes_with_labels_above_them_are_read(self):
        assert set(_rows(self.LINES)) == {33, 34, 50}

    def test_the_figures_are_the_ones_beside_the_code(self):
        assert _rows(self.LINES)[33]["current_val"] == 14269573627370.0
        assert _rows(self.LINES)[50]["current_val"] == 27455185600.0

    def test_the_comparative_column_is_kept(self):
        assert _rows(self.LINES)[50]["previous_val"] == 19000000000.0


class TestAPageNumberIsNotARow:
    def test_a_page_number_at_the_foot_takes_nothing(self):
        # "60" here is the page number of a 100-page audited report, and
        # the figures above it belong to the row before.
        lines = [
            "Luu chuyen tien thuan trong ky",
            "50",
            "27.455.185.600",
            "19.000.000.000",
            "60",
        ]
        assert 60 not in _rows(lines)

    def test_a_digit_with_only_figures_above_it_takes_nothing(self):
        lines = [
            "1.905.249.672.046",
            "1.877.791.791.943",
            "1",
            "42.728.190.111",
            "12.000.000.000",
            "tiep theo trang sau",
            "hai dong nua o day",
        ]
        assert 1 not in _rows(lines)

    def test_the_documented_misbinding_no_longer_happens(self):
        # The shape that produced 1, 2, 3, 60, 20, 21: a footer block of
        # bare digits sitting under the closing balance.
        lines = [
            "Tien va tuong duong tien cuoi ky",
            "70",
            "1.905.249.672.046",
            "1.877.791.791.943",
            "2",
            "3",
            "60",
        ]
        got = _rows(lines)
        assert 70 in got
        assert not ({2, 3, 60} & set(got))

    def test_a_code_needs_a_label_and_not_merely_any_text(self):
        # Two letters is a column header or an artefact, not a row label.
        lines = ["VN", "50", "27.455.185.600", "x", "y", "z"]
        assert 50 not in _rows(lines)


class TestNothingIsInventedFromNothing:
    def test_an_empty_page_produces_no_rows(self):
        assert _rows([]) == {}

    def test_a_label_with_no_figure_after_it_produces_no_row(self):
        lines = ["Luu chuyen tien thuan trong ky", "50", "khong co so lieu",
                 "trang nay de trong", "het"]
        assert _rows(lines) == {}

    def test_a_code_outside_tt200_is_left_alone(self):
        lines = ["Mot dong nhan", "49", "1.000.000.000", "them dong",
                 "va them dong nua"]
        assert 49 not in _rows(lines)
