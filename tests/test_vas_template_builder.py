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


class TestAppearanceAndContentAreQueuedSeparately:
    """A row was relabelled, then restyled, and came back with the source
    workbook's label. Both edits were keyed by cell, so the second threw
    the first away and the restyle kept whatever had been there - which is
    how a line reading "Lợi nhuận sau thuế" reverted to "General and
    Administrative" while reporting success."""

    def test_a_restyle_after_a_value_keeps_the_value(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.set_value("Data", "A1", "nhãn mới")
        w.copy_style("Data", "A3", ["A1"])
        w.save(out)
        assert read(out, "A1") == "nhãn mới"

    def test_a_value_after_a_restyle_keeps_the_value(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.copy_style("Data", "A3", ["A1"])
        w.set_value("Data", "A1", "nhãn mới")
        w.save(out)
        assert read(out, "A1") == "nhãn mới"

    def test_a_restyle_leaves_a_formula_alone(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.copy_style("Data", "A1", ["B5"])
        w.save(out)
        assert read(out, "B5") == "=B1+B3"


class TestStyleIsCopiedColumnByColumn:
    def test_each_column_takes_its_own_column_s_style(self, sheet,
                                                      tmp_path):
        # One donor cell for a whole row hands the label column's format to
        # the money columns. The per-row helper must not do that.
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.copy_row_style("Data", 1, 3, "AB")
        w.save(out)
        wb = openpyxl.load_workbook(out)["Data"]
        src = openpyxl.load_workbook(sheet)["Data"]
        assert wb["A3"]._style == src["A1"]._style
        assert wb["B3"]._style == src["B1"]._style
        assert wb["A3"].value == "tail"
        assert wb["B3"].value == 3


class TestRowsAreHiddenRatherThanDeleted:
    def test_hidden_rows_keep_their_numbers(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.hide_rows("Data", 2, 3)
        w.save(out)
        ws = openpyxl.load_workbook(out)["Data"]
        assert ws.row_dimensions[3].hidden
        assert not ws.row_dimensions[1].hidden
        # the formula below still points at the same cells
        assert ws["B5"].value == "=B1+B3"
        assert ws["B3"].value == 3


class TestColumnsAreOnlyEverWidened:
    def test_a_wider_column_is_not_narrowed(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        first = WorkbookPatch(sheet)
        first.widen_columns("Data", "A", "B", 30.0)
        first.save(out)
        second = WorkbookPatch(out)
        second.widen_columns("Data", "A", "B", 12.0)
        out2 = str(tmp_path / "out2.xlsx")
        second.save(out2)
        ws = openpyxl.load_workbook(out2)["Data"]
        assert ws.column_dimensions["A"].width >= 30.0

    def test_a_narrow_column_is_widened(self, sheet, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(sheet)
        w.widen_columns("Data", "C", "D", 15.5)
        w.save(out)
        ws = openpyxl.load_workbook(out)["Data"]
        assert round(ws.column_dimensions["C"].width, 1) == 15.5
        assert round(ws.column_dimensions["D"].width, 1) == 15.5


@pytest.fixture
def two_sheets(tmp_path):
    """Two sheets, where only one is referenced from elsewhere."""
    path = tmp_path / "two.xlsx"
    wb = openpyxl.Workbook()
    keep = wb.active
    keep.title = "Keep"
    keep["A1"] = 1
    gone = wb.create_sheet("Gone")
    gone["A1"] = 2
    wb.save(path)
    return str(path)


class TestDeletingASheetLeavesNoTraceOfIt:
    def test_the_sheet_and_its_part_are_both_gone(self, two_sheets, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(two_sheets)
        removed = w.delete_sheet("Gone")
        w.save(out)
        wb = openpyxl.load_workbook(out)
        assert wb.sheetnames == ["Keep"]
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            assert not any(r in names for r in removed)
            ct = z.read("[Content_Types].xml").decode()
            for r in removed:
                assert f'PartName="/{r}"' not in ct
            rels = z.read("xl/_rels/workbook.xml.rels").decode()
            book = z.read("xl/workbook.xml").decode()
            import re
            rids = set(re.findall(r'Id="([^"]+)"', rels))
            for rid in re.findall(r'r:id="([^"]+)"', book):
                assert rid in rids

    def test_a_sheet_something_still_points_at_is_refused(
            self, two_sheets, tmp_path):
        wb = openpyxl.load_workbook(two_sheets)
        wb["Keep"]["B1"] = "=Gone!A1"
        src = str(tmp_path / "linked.xlsx")
        wb.save(src)
        w = WorkbookPatch(src)
        with pytest.raises(ValueError):
            w.delete_sheet("Gone")
        assert "Gone" in w.sheets()

    def test_the_part_count_in_app_xml_follows(self, two_sheets, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(two_sheets)
        before = w._parts.get("docProps/app.xml", b"").decode()
        w.delete_sheet("Gone")
        w.save(out)
        if not before:
            pytest.skip("this writer stores no app.xml")
        with zipfile.ZipFile(out) as z:
            app = z.read("docProps/app.xml").decode()
        assert "<vt:lpstr>Gone</vt:lpstr>" not in app


class TestRemovingPicturesKeepsTheCharts:
    """A picture and a chart can share one drawing part.

    Deleting the part would take the chart with it, so only the picture
    anchors go. The element prefix is not fixed: this model writes xdr:,
    while openpyxl declares the drawing namespace as the default and
    writes the same elements bare. A pattern that knows only one of the
    two removes nothing and says so by returning zero, which is exactly
    what a caller reads as "there were no pictures".
    """

    @pytest.mark.parametrize("prefix", ["", "xdr:"])
    def test_a_chart_survives_its_neighbour_being_removed(
            self, tmp_path, prefix):
        import re
        src = tmp_path / "chart.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"
        for i, v in enumerate([1, 2, 3], start=1):
            ws.cell(row=i, column=1, value=v)
        chart = openpyxl.chart.BarChart()
        chart.add_data(openpyxl.chart.Reference(
            ws, min_col=1, min_row=1, max_row=3))
        ws.add_chart(chart, "C1")
        wb.save(src)

        raw = {}
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                raw[n] = z.read(n)
        target = next(n for n in raw
                      if re.fullmatch(r"xl/drawings/drawing\d+\.xml", n))
        p = prefix
        pic = (f"<{p}twoCellAnchor><{p}from><{p}col>8</{p}col>"
               f"<{p}row>0</{p}row></{p}from>"
               f"<{p}pic><{p}nvPicPr/><{p}blipFill/></{p}pic>"
               f"<{p}clientData/></{p}twoCellAnchor>")
        d = raw[target].decode()
        if prefix:
            d = d.replace(
                "<wsDr ",
                '<wsDr xmlns:xdr="http://schemas.openxmlformats.org/'
                'drawingml/2006/spreadsheetDrawing" ', 1)
        raw[target] = d.replace("</wsDr>", pic + "</wsDr>").encode()
        patched = tmp_path / "withpic.xlsx"
        with zipfile.ZipFile(patched, "w") as z:
            for n, b in raw.items():
                z.writestr(n, b)

        w = WorkbookPatch(str(patched))
        assert w.remove_pictures() == 1
        out = str(tmp_path / "out.xlsx")
        w.save(out)
        with zipfile.ZipFile(out) as z:
            after = z.read(target).decode()
        assert f"<{p}pic>" not in after
        assert "graphicFrame" in after


class TestASheetScopedNameFollowsItsSheet:
    """localSheetId is a position, not a name.

    A print area, a filter range or any sheet-scoped defined name does not
    say which sheet it belongs to; it carries the sheet's index in the
    workbook's list. Remove a sheet and every later index means a
    different sheet than it did - so each print area would quietly attach
    itself to its neighbour. Nothing about the file would look wrong.
    """

    @pytest.fixture
    def scoped(self, tmp_path):
        path = tmp_path / "scoped.xlsx"
        wb = openpyxl.Workbook()
        first = wb.active
        first.title = "Gone"
        second = wb.create_sheet("Middle")
        third = wb.create_sheet("Last")
        second.print_area = "A1:C3"
        third.print_area = "A1:D4"
        wb.save(path)
        return str(path)

    def test_indices_after_the_deleted_sheet_move_down(
            self, scoped, tmp_path):
        import re
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(scoped)
        w.delete_sheet("Gone")
        w.save(out)
        with zipfile.ZipFile(out) as z:
            book = z.read("xl/workbook.xml").decode()
        order = [m for m in re.findall(r'<sheet\b[^>]*name="([^"]+)"', book)]
        assert order == ["Middle", "Last"]
        areas = {}
        for m in re.finditer(
                r'<definedName\b([^>]*)>(.*?)</definedName>', book, re.S):
            attrs = dict(re.findall(r'([\w:.]+)="([^"]*)"', m.group(1)))
            if attrs.get("name") == "_xlnm.Print_Area":
                areas[int(attrs["localSheetId"])] = m.group(2)
        assert set(areas) == {0, 1}
        assert "Middle" in areas[0]
        assert "Last" in areas[1]

    def test_the_calculation_chain_is_dropped(self, scoped, tmp_path):
        out = str(tmp_path / "out.xlsx")
        w = WorkbookPatch(scoped)
        w._parts["xl/calcChain.xml"] = b"<calcChain/>"
        w._names.append("xl/calcChain.xml")
        w.delete_sheet("Gone")
        w.save(out)
        with zipfile.ZipFile(out) as z:
            assert "xl/calcChain.xml" not in z.namelist()
            rels = z.read("xl/_rels/workbook.xml.rels").decode()
        assert "calcChain" not in rels


class TestALabelSplitAcrossRunsIsStillFound:
    def test_a_superscript_footnote_does_not_hide_the_label(self, tmp_path):
        """"Current Trading Multiples" with a raised 3 is two runs.

        Searched for as the reader sees it, the label is in neither run,
        so a plain text search finds nothing and reports success.
        """
        src = tmp_path / "rich.xlsx"
        wb = openpyxl.Workbook()
        wb.active["A1"] = "placeholder"
        wb.save(src)
        raw = {}
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                raw[n] = z.read(n)
        raw["xl/sharedStrings.xml"] = (
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats'
            '.org/spreadsheetml/2006/main" count="1" uniqueCount="1">'
            '<si><r><t>Current Trading Multiples</t></r>'
            '<r><rPr><vertAlign val="superscript"/></rPr><t>3</t></r></si>'
            "</sst>").encode()
        patched = tmp_path / "patched.xlsx"
        with zipfile.ZipFile(patched, "w") as z:
            for n, b in raw.items():
                z.writestr(n, b)

        w = WorkbookPatch(str(patched))
        assert w.replace_shared_strings(
            {"Current Trading Multiples3": "Bội số giao dịch hiện tại"}) == 1
        assert b"B\xe1\xbb\x99i s\xe1\xbb\x91" in w._parts[
            "xl/sharedStrings.xml"]

    def test_a_unit_inside_a_longer_heading_is_replaced(self, tmp_path):
        """The unit is a piece of the heading, not the whole of it."""
        src = tmp_path / "u.xlsx"
        wb = openpyxl.Workbook()
        wb.active["A1"] = "placeholder"
        wb.save(src)
        raw = {}
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                raw[n] = z.read(n)
        raw["xl/sharedStrings.xml"] = (
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats'
            '.org/spreadsheetml/2006/main" count="1" uniqueCount="1">'
            "<si><t>Revenue Summary (US$MM)</t></si></sst>").encode()
        patched = tmp_path / "patched.xlsx"
        with zipfile.ZipFile(patched, "w") as z:
            for n, b in raw.items():
                z.writestr(n, b)
        w = WorkbookPatch(str(patched))
        assert w.replace_shared_strings({"US$MM": "triệu đồng"}) == 1
        assert "triệu đồng" in w._parts["xl/sharedStrings.xml"].decode()
        assert "Revenue Summary" in w._parts["xl/sharedStrings.xml"].decode()


class TestReadingTheSheetsBackWaitsForTheEdits:
    def test_a_string_freed_by_a_queued_edit_counts_as_unused(
            self, tmp_path):
        """Edits are queued, not written when they are asked for.

        Counting which shared strings are still referenced before the
        queue is written reads the sheet as it was, so a label the edit
        just removed still looks used and survives in the table - visible
        to anything that reads the file as text, invisible in the grid.
        """
        src = tmp_path / "s.xlsx"
        wb = openpyxl.Workbook()
        wb.active["A1"] = "placeholder"
        wb.save(src)
        raw = {}
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                raw[n] = z.read(n)
        raw["xl/sharedStrings.xml"] = (
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats'
            '.org/spreadsheetml/2006/main" count="1" uniqueCount="1">'
            "<si><t>Amazon.com, Inc.</t></si></sst>").encode()
        target = next(n for n in raw if n.startswith("xl/worksheets/sheet"))
        body = raw[target].decode()
        body = body.replace(
            "</sheetData>",
            '<row r="9"><c r="A9" t="s"><v>0</v></c></row></sheetData>')
        raw[target] = body.encode()
        patched = tmp_path / "p.xlsx"
        with zipfile.ZipFile(patched, "w") as z:
            for n, b in raw.items():
                z.writestr(n, b)

        w = WorkbookPatch(str(patched))
        name = w.sheets()[0]
        w.clear(name, "A9")
        assert w.blank_orphan_strings() == 1
        out = str(tmp_path / "out.xlsx")
        w.save(out)
        with zipfile.ZipFile(out) as z:
            assert b"Amazon" not in z.read("xl/sharedStrings.xml")
