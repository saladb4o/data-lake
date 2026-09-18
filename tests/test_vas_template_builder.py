"""What went wrong while turning the CFI model into a VAS one.

Four defects cost the build, and none of them announced itself. Three were
in the patcher and one was in the layout, and every one of them produced a
file that opened without complaint:

  * a row written as one self-closing tag, which the row pattern ran past,
    swallowing every row after it. The sheet came back truncated at its
    first empty row and the checks read blank rather than wrong.
  * a cell written as a pair of tags, reassembled from a match that stopped
    at the first "/>" inside it, so the closing tag was dropped.
  * a shared formula, stored once on a master cell and referred to by the
    cells repeating it. Overwriting the master left those cells pointing at
    a definition that no longer existed.
  * calcPr, which carries iterate="1" on this workbook because interest
    depends on debt, debt on the funding gap, the gap on cash and cash back
    on interest. Replacing the element to add fullCalcOnLoad dropped the
    flag and every cell on that loop returned #VALUE!.

These tests need no spreadsheet engine and no source workbook. They build
their own file, in the shapes that broke.
"""

import os
import sys
import zipfile

import pytest

openpyxl = pytest.importorskip("openpyxl")

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "xlsxvas"))

import vas_layout as V                      # noqa: E402
from xlsx_patch import (                    # noqa: E402
    WorkbookPatch,
    col_to_index,
    index_to_col,
    shift_formula,
)


@pytest.fixture
def sheet(tmp_path):
    """A workbook with a populated row, an empty row and a later row."""
    path = tmp_path / "src.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws["A1"] = "head"
    ws["B1"] = 1
    ws["A3"] = "tail"
    ws["B3"] = 3
    ws["B5"] = "=B1+B3"
    wb.save(path)
    return str(path)


def read(path, ref, sheet_name="Data", formulas=True):
    wb = openpyxl.load_workbook(path, data_only=not formulas)
    return wb[sheet_name][ref].value


class TestAnEmptyRowDoesNotEatTheRestOfTheSheet:
    def test_rows_after_an_untouched_gap_survive(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.set_value("Data", "B1", 11)
        w.save(out)
        assert read(out, "B1") == 11
        assert read(out, "A3") == "tail"
        assert read(out, "B5") == "=B1+B3"

    def test_a_row_that_did_not_exist_can_be_written(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.set_value("Data", "C9", "new")
        w.save(out)
        assert read(out, "C9") == "new"
        assert read(out, "A3") == "tail"


class TestACellIsRebuiltWhole:
    def test_a_formula_cell_keeps_its_closing_tag(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.set_value("Data", "A1", "changed")
        w.save(out)
        # If </c> were dropped the file would not parse at all, so the
        # assertion that matters is that the untouched neighbour survives
        # with its formula intact.
        assert read(out, "B5") == "=B1+B3"
        # The direct question is whether the sheet is still well formed.
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(out) as z:
            ET.fromstring(z.read("xl/worksheets/sheet1.xml"))


class TestReferencesMoveWithTheFormula:
    def test_a_relative_reference_shifts(self):
        assert shift_formula("D32/C32-1", 1, 0) == "E32/D32-1"

    def test_an_anchored_reference_does_not(self):
        assert shift_formula("SUM(C$5:C10)", 2, 3) == "SUM(E$5:E13)"

    def test_a_defined_name_is_not_a_reference(self):
        assert shift_formula("_TaxRate*-C337", 1, 0) == "_TaxRate*-D337"

    def test_a_function_name_ending_in_digits_is_not_a_reference(self):
        assert shift_formula("LOG10(B2)", 1, 0) == "LOG10(C2)"

    def test_a_reference_on_another_sheet_still_shifts(self):
        assert (shift_formula("'Raw Data'!C21", 1, 0)
                == "'Raw Data'!D21")

    def test_text_inside_the_formula_is_left_alone(self):
        assert (shift_formula('IF(A1="C5","C5",B1)', 1, 0)
                == 'IF(B1="C5","C5",C1)')


class TestColumnNames:
    def test_they_round_trip(self):
        for i in (1, 26, 27, 52, 703):
            assert col_to_index(index_to_col(i)) == i


class TestTheWorkbookKeepsKnowingHowToCalculate:
    def test_iteration_survives_a_patch(self, sheet, tmp_path):
        # Give the source the flag this model carries, then check a patch
        # does not take it away while asking for a recalculation.
        with zipfile.ZipFile(sheet) as z:
            parts = {n: z.read(n) for n in z.namelist()}
        wb = parts["xl/workbook.xml"].decode("utf8")
        wb = wb.replace("</workbook>", '<calcPr calcId="1" iterate="1"/>'
                                       "</workbook>")
        parts["xl/workbook.xml"] = wb.encode("utf8")
        with zipfile.ZipFile(sheet, "w") as z:
            for n, b in parts.items():
                z.writestr(n, b)

        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.set_value("Data", "B1", 2)
        w.save(out)
        with zipfile.ZipFile(out) as z:
            after = z.read("xl/workbook.xml").decode("utf8")
        assert 'iterate="1"' in after
        assert 'fullCalcOnLoad="1"' in after


class TestTheLayoutIsInternallyConsistent:
    def test_no_two_lines_claim_the_same_row(self):
        rows = [line.row for line in V.ALL_LINES]
        assert len(rows) == len(set(rows))

    def test_the_three_statements_do_not_overlap(self):
        spans = [{l.row for l in V.INCOME}, {l.row for l in V.BALANCE},
                 {l.row for l in V.CASHFLOW}, {l.row for l in V.MARKET}]
        for i, a in enumerate(spans):
            for b in spans[i + 1:]:
                assert not (a & b)

    def test_every_code_a_check_names_exists(self):
        # A check that points at an empty row is worse than no check: it
        # reads zero and says the statement closed.
        named = {l.row for l in V.ALL_LINES}
        for line in V.ALL_LINES:
            if line.kind != "check":
                continue
            for row in _rows_in(line.formula):
                assert row in named, f"{line.label} points at empty {row}"

    def test_the_balance_sheet_checks_use_the_official_compositions(self):
        by_row = {l.row: l for l in V.BALANCE}
        assets = by_row[47].formula.format(c="C")
        capital = by_row[64].formula.format(c="C")
        assert _rows_in(assets) == [V.BS_ROW["100"], V.BS_ROW["200"],
                                    V.BS_ROW["270"]]
        assert _rows_in(capital) == [V.BS_ROW["300"], V.BS_ROW["400"],
                                     V.BS_ROW["440"]]

    def test_the_cash_identity_is_the_one_tt200_imposes(self):
        by_row = {l.row: l for l in V.CASHFLOW}
        assert _rows_in(by_row[83].formula.format(c="C")) == [
            V.CF_ROW["50"], V.CF_ROW["60"], V.CF_ROW["61"], V.CF_ROW["70"]]

    def test_the_forecast_reaches_the_column_the_dcf_reads(self):
        # The valuation reads the last four forecast columns directly. A
        # build that stopped at N left those years pointing at nothing.
        assert V.FCST_COLS[-1] == "R"
        assert len(V.HIST_COLS) == 5


def _rows_in(formula):
    import re
    return [int(n) for n in re.findall(r"C(\d+)", formula)]
