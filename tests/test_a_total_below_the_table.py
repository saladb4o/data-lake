"""The row that closes a balance sheet is not always in the table.

Run 35314238637 printed BSR's Q4 page 4 in full. It ends:

    (440=300+400)
    440
    85.068.637.113.074
    88.386.867.728.798

The figures were there, correct, and route 1 returned 28 rows without
them. pdfplumber gives back a table's rows, and a total typeset below the
ruled block is not one. Route 2 reads lines and would have found it, but
route 2 only runs when route 1 found nothing at all - and 28 is not
nothing, so the statement stayed open and all three identities read n/a.

The page's own arithmetic is the check: 300 + 400 = 440, to the dong.
"""

from services.bctc_pdf_parser import BCTCPdfParser


def _read(lines):
    p = BCTCPdfParser.__new__(BCTCPdfParser)
    p.currency_scale = 1
    p.active_balance_codes = {100: "a", 200: "b", 270: "c", 300: "d",
                              400: "e", 440: "f", 310: "g"}
    items = {}
    p._parse_ocr_lines_for_balance_sheet(lines, items)
    return items


# Verbatim from the run's dump of page 4.
PAGE_4_TAIL = [
    "C -", "300", "24.583.223.364.493", "32.848.858.696.659",
    "310", "23.726.837.131.723", "31.984.096.504.586",
    "D -", "(400=410+430)", "400", "19",
    "60.485.413.748.581", "55.538.009.032.139",
    "(440=300+400)", "440",
    "85.068.637.113.074", "88.386.867.728.798",
    "Phó", "Ngày .... tháng 01", "2026",
]


class TestTheClosingRowIsRead:
    def test_the_total_is_bound(self):
        assert _read(PAGE_4_TAIL)[440]["current_val"] == 85_068_637_113_074

    def test_the_documents_own_arithmetic_closes(self):
        items = _read(PAGE_4_TAIL)
        assert (items[300]["current_val"] + items[400]["current_val"]
                == items[440]["current_val"])

    def test_the_prior_period_column_closes_too(self):
        items = _read(PAGE_4_TAIL)
        assert (items[300]["previous_val"] + items[400]["previous_val"]
                == items[440]["previous_val"])


class TestNothingElseOnThePageIsMistakenForARow:
    def test_the_composition_formula_is_not_read_as_a_row(self):
        # "(440=300+400)" holds the digits 440, 300 and 400. If the line
        # parser took them, 300 would be bound to 400.
        items = _read(PAGE_4_TAIL)
        assert items[300]["current_val"] == 24_583_223_364_493

    def test_a_note_reference_is_not_a_figure(self):
        # Code 400 is followed by "19", its note number, before the money.
        assert _read(PAGE_4_TAIL)[400]["current_val"] == 60_485_413_748_581

    def test_the_signature_block_binds_nothing(self):
        assert set(_read(["Phó", "Ngày .... tháng 01", "2026"])) == set()
