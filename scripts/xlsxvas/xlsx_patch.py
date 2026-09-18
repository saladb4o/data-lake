"""Edit cells in an .xlsx without disturbing anything else in it.

openpyxl cannot be used here. It re-serialises the whole workbook on save
and drops every chart, drawing and image it did not create itself; the
model this operates on carries sixteen charts and five images, so a
round-trip through openpyxl would silently destroy most of the file's
visible output while reporting success.

So the zip is patched part by part. Only the worksheet XML of the sheets
actually touched is rewritten; every other member is copied byte for byte.
Strings are written inline rather than through the shared string table,
which keeps the edit local to one part.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_CELL_REF = re.compile(r"^([A-Z]{1,3})(\d+)$")

# A row is written either as a pair of tags around its cells or, when it
# carries only formatting, as one self-closing tag. Matching just the first
# shape lets the body pattern run past a self-closing row and swallow every
# row after it, which is how a patched sheet came back truncated at the
# first empty row.
_ROW = re.compile(r'<row\b[^>]*?/>|(<row\b[^>]*?>)(.*?)</row>', re.S)
_CELL = re.compile(r'<c\b[^>]*?/>|<c\b[^>]*?>.*?</c>', re.S)
_CELL_R = re.compile(r'r="([A-Z]{1,3}\d+)"')

# A shared formula is stored once, on a master cell, and referred to by the
# cells that repeat it. Overwriting the master would leave those cells
# pointing at a definition that no longer exists, so every group is written
# out in full before any edit lands.
_SHARED_MASTER = re.compile(
    r'<f([^>]*?)\bt="shared"([^>]*?)\bsi="(\d+)"([^>]*?)>(.*?)</f>', re.S)
_SHARED_SLAVE = re.compile(
    r'<f[^>]*?\bt="shared"[^>]*?\bsi="(\d+)"[^>]*?/>')
_TOKEN = re.compile(r'"[^"]*"|\'[^\']*\'|'
                    r'(?<![A-Za-z0-9_.$])(\$?)([A-Z]{1,3})(\$?)(\d+)'
                    r'(?![A-Za-z0-9_(])')


def shift_formula(formula: str, dcol: int, drow: int) -> str:
    """Move every relative reference in a formula by a column/row offset."""
    def one(m: re.Match) -> str:
        if m.group(2) is None:           # a quoted string or sheet name
            return m.group(0)
        cdollar, col, rdollar, row = m.groups()
        if not cdollar:
            col = index_to_col(max(1, col_to_index(col) + dcol))
        if not rdollar:
            row = str(max(1, int(row) + drow))
        return f"{cdollar}{col}{rdollar}{row}"
    return _TOKEN.sub(one, formula)


def col_to_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def index_to_col(idx: int) -> str:
    out = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def split_ref(ref: str) -> Tuple[str, int]:
    m = _CELL_REF.match(ref.replace("$", "").upper())
    if not m:
        raise ValueError(f"not a cell reference: {ref!r}")
    return m.group(1), int(m.group(2))


def xml_escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


@dataclass
class Cell:
    """One edit. Exactly one of value / formula / blank carries the intent."""
    value: object = None
    formula: Optional[str] = None
    blank: bool = False
    style: Optional[int] = None   # keep the cell's own style when None


@dataclass
class SheetEdits:
    edits: Dict[str, Cell] = field(default_factory=dict)


class WorkbookPatch:
    def __init__(self, src: str):
        self.src = src
        with zipfile.ZipFile(src) as z:
            self._names = z.namelist()
            self._parts = {n: z.read(n) for n in self._names}
        self._sheet_part = self._map_sheets()
        self._pending: Dict[str, SheetEdits] = {}
        self._expanded: set = set()

    # -- sheet name -> zip part -------------------------------------------
    def _map_sheets(self) -> Dict[str, str]:
        wb = self._parts["xl/workbook.xml"].decode("utf8")
        rels = self._parts["xl/_rels/workbook.xml.rels"].decode("utf8")
        # Attribute order is not guaranteed: some writers put Target before
        # Id, and a pattern that assumes one order silently maps nothing.
        target = {}
        for rel in re.findall(r'<Relationship\b[^>]*/?>', rels):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', rel))
            if "Id" in attrs and "Target" in attrs:
                target[attrs["Id"]] = attrs["Target"]
        out = {}
        for sheet_tag in re.findall(r'<sheet\b[^>]*/?>', wb):
            attrs = dict(re.findall(r'([\w:]+)="([^"]*)"', sheet_tag))
            name = attrs.get("name")
            rid = attrs.get("r:id") or attrs.get("relationshipId")
            if not name or rid not in target:
                continue
            tgt = target[rid].lstrip("/")
            if not tgt.startswith("xl/"):
                tgt = "xl/" + tgt
            out[name] = tgt
        return out

    def sheets(self) -> List[str]:
        return list(self._sheet_part)

    # -- queue edits -------------------------------------------------------
    def set_value(self, sheet: str, ref: str, value) -> None:
        self._queue(sheet, ref, Cell(value=value))

    def set_formula(self, sheet: str, ref: str, formula: str) -> None:
        self._queue(sheet, ref, Cell(formula=formula.lstrip("=")))

    def clear(self, sheet: str, ref: str) -> None:
        self._queue(sheet, ref, Cell(blank=True))

    def clear_rows(self, sheet: str, first: int, last: int,
                   cols: Optional[List[str]] = None) -> None:
        """Blank whole rows, keeping the rows themselves and their styles."""
        part = self._sheet_part[sheet]
        self._expand_shared(part)
        xml = self._parts[part].decode("utf8")
        for rm in _ROW.finditer(xml):
            r = int(re.search(r'r="(\d+)"', rm.group(0)).group(1))
            if not (first <= r <= last):
                continue
            body = rm.group(2) or ""
            for cm in re.finditer(r'<c [^>]*r="([A-Z]{1,3}\d+)"', body):
                ref = cm.group(1)
                if cols and split_ref(ref)[0] not in cols:
                    continue
                self._queue(sheet, ref, Cell(blank=True))

    def _queue(self, sheet: str, ref: str, cell: Cell) -> None:
        if sheet not in self._sheet_part:
            raise KeyError(f"no such sheet: {sheet!r}")
        col, row = split_ref(ref)
        self._pending.setdefault(sheet, SheetEdits()).edits[
            f"{col}{row}"] = cell

    # -- render ------------------------------------------------------------
    @staticmethod
    def _render(ref: str, cell: Cell, style: Optional[str]) -> str:
        s = f' s="{style}"' if style is not None else ""
        if cell.style is not None:
            s = f' s="{cell.style}"'
        if cell.blank:
            return f'<c r="{ref}"{s}/>'
        if cell.formula is not None:
            # The cached value is dropped on purpose: a stale cached number
            # next to a new formula is the one way this edit could lie.
            return f'<c r="{ref}"{s}><f>{xml_escape(cell.formula)}</f></c>'
        v = cell.value
        if v is None:
            return f'<c r="{ref}"{s}/>'
        if isinstance(v, bool):
            return f'<c r="{ref}"{s} t="b"><v>{int(v)}</v></c>'
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"{s}><v>{v!r}</v></c>'
        return (f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">'
                f'{xml_escape(v)}</t></is></c>')

    def _expand_shared(self, part: str) -> None:
        """Write every shared formula out in full, once, for one sheet."""
        if part in self._expanded:
            return
        self._expanded.add(part)
        xml = self._parts[part].decode("utf8")
        masters: Dict[str, Tuple[str, int, int]] = {}

        def note_master(cell_xml: str) -> str:
            m = _SHARED_MASTER.search(cell_xml)
            if not m:
                return cell_xml
            rm = _CELL_R.search(cell_xml)
            if not rm:
                return cell_xml
            col, row = split_ref(rm.group(1))
            masters[m.group(3)] = (m.group(5), col_to_index(col), row)
            return cell_xml[:m.start()] + f"<f>{m.group(5)}</f>" + \
                cell_xml[m.end():]

        def fill_slave(cell_xml: str) -> str:
            m = _SHARED_SLAVE.search(cell_xml)
            if not m or m.group(1) not in masters:
                return cell_xml
            rm = _CELL_R.search(cell_xml)
            if not rm:
                return cell_xml
            formula, mcol, mrow = masters[m.group(1)]
            col, row = split_ref(rm.group(1))
            shifted = shift_formula(formula, col_to_index(col) - mcol,
                                    row - mrow)
            return cell_xml[:m.start()] + f"<f>{shifted}</f>" + \
                cell_xml[m.end():]

        def one_cell(m: re.Match) -> str:
            return fill_slave(note_master(m.group(0)))

        self._parts[part] = _CELL.sub(one_cell, xml).encode("utf8")

    def _patch_sheet(self, sheet: str, edits: Dict[str, Cell]) -> None:
        part = self._sheet_part[sheet]
        self._expand_shared(part)
        xml = self._parts[part].decode("utf8")
        by_row: Dict[int, Dict[str, Cell]] = {}
        for ref, cell in edits.items():
            by_row.setdefault(split_ref(ref)[1], {})[ref] = cell

        def fix_row(m: re.Match) -> str:
            whole = m.group(0)
            if m.group(2) is None:            # <row .../>, no cells yet
                head = whole[:-2] + ">"
                body, tail = "", "</row>"
            else:
                head, body, tail = m.group(1), m.group(2), "</row>"
            r = int(re.search(r'r="(\d+)"', whole).group(1))
            want = by_row.pop(r, None)
            if not want:
                return m.group(0)
            cells: Dict[str, str] = {}
            for cm in _CELL.finditer(body):
                rm = _CELL_R.search(cm.group(0))
                if rm:
                    cells[rm.group(1)] = cm.group(0)
            for ref, cell in want.items():
                old = cells.get(ref)
                style = None
                if old:
                    sm = re.search(r'\bs="(\d+)"', old)
                    style = sm.group(1) if sm else None
                cells[ref] = self._render(ref, cell, style)
            ordered = sorted(cells, key=lambda k: col_to_index(split_ref(k)[0]))
            # spans is advisory; a wrong one makes Excel repair the file.
            head = re.sub(r'\s+spans="[^"]*"', "", head)
            return head + "".join(cells[k] for k in ordered) + tail

        xml = _ROW.sub(fix_row, xml)

        if by_row:  # rows that do not exist yet
            new_rows = []
            for r in sorted(by_row):
                cells = by_row[r]
                ordered = sorted(cells,
                                 key=lambda k: col_to_index(split_ref(k)[0]))
                inner = "".join(self._render(k, cells[k], None)
                                for k in ordered)
                new_rows.append((r, f'<row r="{r}">{inner}</row>'))
            xml = self._insert_rows(xml, new_rows)
        self._parts[part] = xml.encode("utf8")

    @staticmethod
    def _insert_rows(xml: str, new_rows: List[Tuple[int, str]]) -> str:
        positions = [(int(m.group(1)), m.start())
                     for m in re.finditer(r'<row [^>]*r="(\d+)"', xml)]
        for r, frag in sorted(new_rows, reverse=True):
            at = None
            for rr, pos in positions:
                if rr > r:
                    at = pos
                    break
            if at is None:
                at = xml.index("</sheetData>")
            xml = xml[:at] + frag + xml[at:]
            positions = [(int(m.group(1)), m.start())
                         for m in re.finditer(r'<row [^>]*r="(\d+)"', xml)]
        return xml

    def _force_recalc(self) -> None:
        """Ask for a recalculation without discarding how to calculate.

        calcPr carries more than a cache marker. This model sets
        iterate="1" on it, because interest depends on debt, debt on the
        funding gap, the funding gap on cash and cash back on interest -
        a loop the workbook is meant to settle by iteration. Replacing the
        whole element to add fullCalcOnLoad dropped that flag, and every
        cell on the loop came back #VALUE!. So the attributes already
        there are kept and only the ones needed are set.
        """
        wb = self._parts["xl/workbook.xml"].decode("utf8")
        m = re.search(r'<calcPr\b([^>]*?)/?>', wb)
        if m:
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            attrs["fullCalcOnLoad"] = "1"
            attrs["calcId"] = "0"
            rebuilt = "<calcPr " + " ".join(
                f'{k}="{v}"' for k, v in attrs.items()) + "/>"
            wb = wb[:m.start()] + rebuilt + wb[m.end():]
        else:
            wb = wb.replace("</workbook>",
                            '<calcPr calcId="0" fullCalcOnLoad="1"/>'
                            "</workbook>")
        self._parts["xl/workbook.xml"] = wb.encode("utf8")

    def save(self, dest: str) -> None:
        for sheet, se in self._pending.items():
            if se.edits:
                self._patch_sheet(sheet, se.edits)
        self._force_recalc()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for n in self._names:
                z.writestr(n, self._parts[n])
        self._pending.clear()
