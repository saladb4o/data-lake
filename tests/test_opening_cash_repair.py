"""Code 60, the opening cash balance, and the one repair that is provable.

The extractor binds code 60 wrong often enough to be systematic. On FPT's
Q4 2025 parent-only filing it returned 42,728,190,111 against a closing
balance of 1,905,249,672,046, and the identity the statement guarantees -
opening + net + FX = closing - missed by 1.8 trillion. Run 35300394193
showed the same break on both consolidated filings.

The cause is upstream and is not fixed here: a bare one or two digit line
is read as a code, so page numbers and note references become codes and
take whatever figure follows. The order the items came back in is the
tell - 1, 2, 3, 60, 20, 21 - code 60 bound before code 20 on a statement
that prints them the other way round.

What is repairable is one line, on an accounting identity rather than a
guess: cash at the start of a period is cash at the end of the one
before, which the statement prints as code 70's comparative column.
"""

from services.bctc_pdf_parser import BCTCPdfParser


def _row(code, current, previous=None):
    return {"code": code, "name": "x",
            "current_val": current, "previous_val": previous}


# FPT, Q4 2025, parent-only - the figures from run 35220475916's log.
FPT_Q4 = {
    1: _row(1, 1905249672046.0),
    50: _row(50, 27455185600.0),
    60: _row(60, 42728190111.0),
    61: _row(61, 2694503.0),
    70: _row(70, 1905249672046.0, 1877791791943.0),
}


class TestTheRepairOnTheFilingThatFoundIt:
    def test_the_opening_balance_is_taken_from_the_prior_closing(self):
        items = dict(FPT_Q4)
        BCTCPdfParser._repair_opening_cash(items)
        assert items[60]["current_val"] == 1877791791943.0

    def test_the_identity_then_closes_to_the_dong(self):
        items = dict(FPT_Q4)
        BCTCPdfParser._repair_opening_cash(items)
        total = (items[60]["current_val"] + items[50]["current_val"]
                 + items[61]["current_val"])
        assert total == items[70]["current_val"]

    def test_the_substitution_is_recorded_rather_than_silent(self):
        # A repaired figure is not the same kind of thing as a read one,
        # and anything downstream is entitled to know which it has.
        items = dict(FPT_Q4)
        BCTCPdfParser._repair_opening_cash(items)
        assert items[60]["repaired_from"] == "code 70 comparative column"


class TestTheRepairRefusesWhereItCannotHelp:
    def test_a_statement_that_already_closes_is_left_alone(self):
        items = {50: _row(50, 100.0), 60: _row(60, 900.0),
                 61: _row(61, 0.0), 70: _row(70, 1000.0, 555.0)}
        BCTCPdfParser._repair_opening_cash(items)
        assert items[60]["current_val"] == 900.0
        assert "repaired_from" not in items[60]

    def test_a_substitution_that_would_not_close_is_not_made(self):
        # A wrong number left visible beats a different wrong number: the
        # statement keeps reporting itself as broken.
        items = {50: _row(50, 100.0), 60: _row(60, 7.0),
                 61: _row(61, 0.0), 70: _row(70, 1000.0, 42.0)}
        BCTCPdfParser._repair_opening_cash(items)
        assert items[60]["current_val"] == 7.0

    def test_no_comparative_column_means_no_repair(self):
        items = {50: _row(50, 100.0), 70: _row(70, 1000.0)}
        BCTCPdfParser._repair_opening_cash(items)
        assert 60 not in items

    def test_a_missing_closing_balance_is_not_invented(self):
        items = {50: _row(50, 100.0), 60: _row(60, 7.0)}
        BCTCPdfParser._repair_opening_cash(items)
        assert items[60]["current_val"] == 7.0
        assert 70 not in items

    def test_an_absent_fx_line_is_treated_as_zero(self):
        # Code 61 is genuinely absent for companies with no currency
        # exposure, and that must not block the repair. The figures are
        # statement-sized on purpose: the tolerance has a floor of a
        # thousand dong, so toy numbers would sit inside it and the
        # repair would rightly conclude nothing was wrong.
        items = {50: _row(50, 100_000_000_000.0), 60: _row(60, 7_000_000.0),
                 70: _row(70, 1_000_000_000_000.0, 900_000_000_000.0)}
        BCTCPdfParser._repair_opening_cash(items)
        assert items[60]["current_val"] == 900_000_000_000.0

    def test_a_discrepancy_under_a_thousand_dong_is_not_a_break(self):
        # Rounding in the filing itself, not a misbound row.
        items = {50: _row(50, 100_000_000_000.0),
                 60: _row(60, 899_999_999_500.0), 61: _row(61, 0.0),
                 70: _row(70, 1_000_000_000_000.0, 900_000_000_000.0)}
        BCTCPdfParser._repair_opening_cash(items)
        assert items[60]["current_val"] == 899_999_999_500.0

    def test_an_empty_statement_does_not_raise(self):
        items: dict = {}
        BCTCPdfParser._repair_opening_cash(items)
        assert items == {}
