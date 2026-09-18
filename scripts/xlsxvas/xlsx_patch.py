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
    """One edit. Exactly one of value / formula / blank / restyle carries it."""
    value: object = None
    formula: Optional[str] = None
    blank: bool = False
    restyle: bool = False         # keep the contents, change only the look
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
        self._hidden: Dict[str, List[Tuple[int, int]]] = {}

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

    def style_of(self, sheet: str, ref: str) -> Optional[str]:
        """The style id a cell currently carries, or None if it has none."""
        part = self._sheet_part[sheet]
        xml = self._parts[part].decode("utf8")
        m = re.search(r'<c\b[^>]*?r="%s"[^>]*?(?:/>|>)' % re.escape(ref), xml)
        if not m:
            return None
        sm = re.search(r'\bs="(\d+)"', m.group(0))
        return sm.group(1) if sm else None

    def copy_style(self, sheet: str, donor: str, targets: List[str]) -> None:
        """Give cells the look of another cell without touching their contents.

        The source model shades a cell to say a human typed it. Clearing
        Amazon's numbers left that shading behind on cells that now hold
        formulas, and left section banners across rows that are no longer
        sections - which is most of what reads as an empty coloured block.
        """
        sid = self.style_of(sheet, donor)
        for ref in targets:
            self._queue(sheet, ref, Cell(restyle=True,
                                         style=int(sid) if sid else 0))

    def copy_row_style(self, sheet: str, donor_row: int, target_row: int,
                       cols: str) -> None:
        """Give a row the look of another row, column by column.

        Column by column matters. Taking one donor cell for a whole row
        hands the label column's formatting to the money columns, which is
        how a row of figures lost its thousands separators while the band
        it was supposed to lose stayed where it was, one column further
        right than the donor could see.
        """
        for col in cols:
            self.copy_style(sheet, f"{col}{donor_row}",
                            [f"{col}{target_row}"])

    def widen_columns(self, sheet: str, first_col: str, last_col: str,
                      width: float) -> None:
        """Raise a span of columns to at least this width, never lower them.

        A figure too wide for its column is shown as ######. In millions of
        dong a large company's total assets run to eight digits and two
        separators, which the source model's twelve-character columns were
        never sized for.
        """
        part = self._sheet_part[sheet]
        xml = self._parts[part].decode("utf8")
        lo, hi = col_to_index(first_col), col_to_index(last_col)
        existing: Dict[int, Dict[str, str]] = {}
        block = re.search(r"<cols>.*?</cols>", xml, re.S)
        if block:
            for tag in re.findall(r"<col\b[^>]*/>", block.group(0)):
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
                a, b = int(attrs.get("min", 1)), int(attrs.get("max", 1))
                for i in range(a, b + 1):
                    existing[i] = dict(attrs)
        for i in range(lo, hi + 1):
            attrs = existing.get(i, {})
            have = float(attrs.get("width", 0) or 0)
            attrs["width"] = f"{max(have, width):.2f}"
            attrs["customWidth"] = "1"
            attrs["min"] = attrs["max"] = str(i)
            existing[i] = attrs
        rebuilt = "<cols>" + "".join(
            "<col " + " ".join(f'{k}="{v}"' for k, v in sorted(a.items()))
            + "/>" for _, a in sorted(existing.items())) + "</cols>"
        if block:
            xml = xml[:block.start()] + rebuilt + xml[block.end():]
        else:
            at = xml.index("<sheetData")
            xml = xml[:at] + rebuilt + xml[at:]
        self._parts[part] = xml.encode("utf8")

    def hide_rows(self, sheet: str, first: int, last: int) -> None:
        """Hide a span of rows, keeping their numbers.

        Rows cannot be deleted here: every formula in the workbook addresses
        its neighbours by row number, so removing one would silently move
        everything below it. Hiding leaves the arithmetic alone.
        """
        self._hidden.setdefault(sheet, []).append((first, last))

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
        """Add an edit, merging a restyle with a content edit for the cell.

        Content and appearance are queued separately and often for the same
        cell. Keyed edits used to overwrite each other, so restyling a row
        after labelling it threw the label away and kept whatever the
        source workbook had said there - which is how a row came back
        reading "General and Administrative".
        """
        if sheet not in self._sheet_part:
            raise KeyError(f"no such sheet: {sheet!r}")
        col, row = split_ref(ref)
        key = f"{col}{row}"
        edits = self._pending.setdefault(sheet, SheetEdits()).edits
        prior = edits.get(key)
        if prior is None:
            edits[key] = cell
            return
        if cell.restyle and not prior.restyle:
            prior.style = cell.style       # keep the content, take the look
            return
        if prior.restyle and not cell.restyle:
            cell.style = prior.style
        edits[key] = cell

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
                if cell.restyle:
                    base = old or f'<c r="{ref}"/>'
                    new_s = f' s="{cell.style}"'
                    if re.search(r'\bs="\d+"', base):
                        base = re.sub(r'\s*\bs="\d+"', new_s, base, count=1)
                    else:
                        base = base.replace(f'r="{ref}"',
                                            f'r="{ref}"{new_s}', 1)
                    cells[ref] = base
                    continue
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

    def replace_shared_strings(self, mapping: Dict[str, str]) -> int:
        """Rewrite label text wherever the workbook stores it once and reuses it.

        Most labels came with the file and live in the shared string table,
        so changing them cell by cell would write dozens of inline copies
        of text that is already shared.

        A shared string is not always one run of text. A label with a
        superscript footnote - "Current Trading Multiples" followed by a
        raised 3 - is stored as two runs, and a plain search for the label
        as the reader sees it finds nothing. So each entry is compared on
        the text it renders to, with its runs joined, and a match replaces
        the whole entry with a single run. The footnote's raised styling is
        lost with it; the footnote itself is part of the translated text.
        """
        part = "xl/sharedStrings.xml"
        if part not in self._parts:
            return 0
        xml = self._parts[part].decode("utf8")
        wanted = {xml_escape(k): v for k, v in mapping.items()}
        changed = 0

        # applied longest first, so a specific phrase is not half-rewritten
        # by a shorter one inside it
        by_length = sorted(wanted, key=len, reverse=True)

        def one_si(m: re.Match) -> str:
            nonlocal changed
            body = m.group(1)
            rendered = "".join(re.findall(r'<t[^>]*>(.*?)</t>', body, re.S))
            if rendered in wanted:
                changed += 1
                new_text = xml_escape(wanted[rendered])
                space = ' xml:space="preserve"' \
                    if new_text != new_text.strip() else ""
                return f"<si><t{space}>{new_text}</t></si>"
            # a unit written inside a longer heading - "(US$MM)" at the end
            # of a title - is a piece of an entry, not the whole of it
            hit = False
            for key in by_length:
                if key and key in rendered:
                    rendered = rendered.replace(key, xml_escape(wanted[key]))
                    hit = True
            if not hit:
                return m.group(0)
            changed += 1
            space = ' xml:space="preserve"' \
                if rendered != rendered.strip() else ""
            return f"<si><t{space}>{rendered}</t></si>"

        xml = re.sub(r'<si>(.*?)</si>', one_si, xml, flags=re.S)
        self._parts[part] = xml.encode("utf8")
        return changed

    def scrub_parts(self, mapping: Dict[str, str],
                    parts: Optional[List[str]] = None) -> int:
        """Replace text in the parts that are not the grid.

        A workbook carries text in more places than its cells: a chart
        title typed as rich text, a series name cached inside the chart, a
        text box on a drawing, a table's column name, the author recorded
        in the document properties, and the absolute path of the folder
        the file was last saved in. None of it is reachable through a
        cell, and all of it survives every edit made to the sheets.
        """
        hits = 0
        for name in (parts if parts is not None else list(self._parts)):
            if name not in self._parts:
                continue
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            text = self._parts[name].decode("utf8", "replace")
            before = text
            for old in sorted(mapping, key=len, reverse=True):
                key = xml_escape(old)
                if key in text:
                    hits += text.count(key)
                    text = text.replace(key, xml_escape(mapping[old]))
            if text != before:
                self._parts[name] = text.encode("utf8")
        return hits

    def strip_stale_string_caches(self) -> int:
        """Drop the remembered result of every formula that returned text.

        A formula cell keeps its last computed value. Where that value is
        text - a label mirrored from another sheet - it is the old label,
        in the old language, and it is what a reader sees until the
        workbook recalculates. Removing it makes the cell show what the
        formula actually says.
        """
        self._flush()
        dropped = 0
        for name in list(self._parts):
            if not name.startswith("xl/worksheets/sheet"):
                continue
            xml = self._parts[name].decode("utf8")

            def one_cell(m: re.Match) -> str:
                nonlocal dropped
                cell = m.group(0)
                if 't="str"' not in cell or "<f" not in cell:
                    return cell
                stripped = re.sub(r'<v>.*?</v>', "", cell, flags=re.S)
                if stripped != cell:
                    dropped += 1
                return stripped

            self._parts[name] = _CELL.sub(one_cell, xml).encode("utf8")
        return dropped

    def blank_orphan_strings(self) -> int:
        """Empty the shared strings no cell points at any more.

        Clearing a cell does not clear the text it used to show: the entry
        stays in the string table, invisible in the grid and perfectly
        visible to anything that reads the file as text. Amazon's company
        name, the publisher's disclaimer and a dozen sheet titles survived
        that way.

        The entries are emptied rather than deleted, because every cell in
        the workbook refers to a string by its POSITION in this table.
        Removing one would shift every entry after it and silently
        relabel the sheet.
        """
        part = "xl/sharedStrings.xml"
        if part not in self._parts:
            return 0
        self._flush()
        used = set()
        for name, blob in self._parts.items():
            if not name.startswith("xl/worksheets/sheet"):
                continue
            xml = blob.decode("utf8", "replace")
            for m in _CELL.finditer(xml):
                cell = m.group(0)
                if 't="s"' not in cell:
                    continue
                v = re.search(r'<v>(\d+)</v>', cell)
                if v:
                    used.add(int(v.group(1)))
        xml = self._parts[part].decode("utf8")
        index = -1
        blanked = 0

        def one_si(m: re.Match) -> str:
            nonlocal index, blanked
            index += 1
            if index in used or not re.search(
                    r'<t[^>]*>[^<]', m.group(0)):
                return m.group(0)
            blanked += 1
            return "<si><t></t></si>"

        xml = re.sub(r'<si>.*?</si>', one_si, xml, flags=re.S)
        self._parts[part] = xml.encode("utf8")
        return blanked

    def strip_currency_symbols(self) -> int:
        """Take the dollar sign out of the number formats.

        The figures themselves carry no currency; the format does. Removing
        the quoted symbol leaves the rest of each pattern - the thousands
        separators, the bracketed negatives, the accounting alignment -
        exactly as it was, and the unit is stated in each sheet's header
        instead. The date format's [$-409] locale token has no quotes and
        is therefore untouched.
        """
        part = "xl/styles.xml"
        xml = self._parts[part].decode("utf8")
        before = xml.count("&quot;$&quot;")
        xml = xml.replace("&quot;$&quot;", "")
        self._parts[part] = xml.encode("utf8")
        return before

    def delete_sheet(self, sheet: str) -> List[str]:
        """Remove a worksheet and everything the package hangs off it.

        A sheet is named in four places at once: the workbook's sheet list,
        the relationship that list points through, the content-type
        override for its part, and the part itself, plus whatever rels the
        part owns (drawings, printer settings). Dropping only the part
        leaves a workbook that names a sheet it no longer has, and Excel
        repairs the file by throwing away more than the sheet.

        The caller is responsible for checking that no formula and no
        defined name still points at it; delete_sheet refuses if one does,
        because a #REF! spread across the model is much harder to find
        later than this exception is now.
        """
        if sheet not in self._sheet_part:
            raise KeyError(f"no such sheet: {sheet}")
        part = self._sheet_part[sheet]
        quoted = f"'{sheet}'!"
        bare = f"{sheet}!"
        for name, blob in self._parts.items():
            if name == part or not name.endswith(".xml"):
                continue
            if not (name.startswith("xl/worksheets/")
                    or name.startswith("xl/charts/")
                    or name == "xl/workbook.xml"):
                continue
            text = blob.decode("utf8", "replace")
            if name == "xl/workbook.xml":
                # the <sheet> entry itself is expected; look only at the
                # defined names, which are what a formula would resolve
                # through
                text = "".join(re.findall(
                    r'<definedName\b[^>]*>.*?</definedName>', text, re.S))
            if quoted in text or bare in text:
                raise ValueError(
                    f"{name} still refers to {sheet}; not deleting")

        removed = [part]
        rels_part = part.replace("worksheets/", "worksheets/_rels/") + ".rels"
        owned: List[str] = []
        if rels_part in self._parts:
            rels = self._parts[rels_part].decode("utf8")
            for tgt in re.findall(r'Target="([^"]*)"', rels):
                if tgt.startswith("../"):
                    owned.append("xl/" + tgt[3:])
            removed.append(rels_part)

        # a drawing or printerSettings part is only ours to delete if no
        # other sheet points at the same file
        for cand in owned:
            others = 0
            for name, blob in self._parts.items():
                if not name.endswith(".rels") or name == rels_part:
                    continue
                if cand.rsplit("/", 1)[-1] in blob.decode("utf8", "replace"):
                    others += 1
            if others == 0:
                removed.append(cand)
                drels = cand.replace("drawings/", "drawings/_rels/") + ".rels"
                if drels in self._parts:
                    removed.append(drels)

        wb = self._parts["xl/workbook.xml"].decode("utf8")
        rid = None
        position = None
        tags = re.findall(r'<sheet\b[^>]*/?>', wb)
        for i, tag in enumerate(tags):
            attrs = dict(re.findall(r'([\w:]+)="([^"]*)"', tag))
            if attrs.get("name") == sheet:
                rid = attrs.get("r:id")
                position = i
                wb = wb.replace(tag, "")
        if position is None:
            raise KeyError(f"{sheet} is not in the workbook's sheet list")

        # A sheet-scoped defined name - a print area, a filter range - does
        # not name its sheet. It carries localSheetId, which is the sheet's
        # POSITION in the list above. Removing a sheet shifts every later
        # position by one, so leaving these alone would quietly re-attach
        # each print area to its neighbour. Names belonging to the sheet
        # that is going are dropped; the rest are renumbered.
        def fix_defined_name(m: re.Match) -> str:
            whole = m.group(0)
            lm = re.search(r'localSheetId="(\d+)"', whole)
            if not lm:
                return whole
            idx = int(lm.group(1))
            if idx == position:
                return ""
            if idx < position:
                return whole
            return whole[:lm.start()] + f'localSheetId="{idx - 1}"' \
                + whole[lm.end():]

        wb = re.sub(r'<definedName\b[^>]*>.*?</definedName>',
                    fix_defined_name, wb, flags=re.S)
        self._parts["xl/workbook.xml"] = wb.encode("utf8")

        # the calculation chain lists cells by sheet index too, and is a
        # cache Excel rebuilds when it is absent
        for chain in ("xl/calcChain.xml",):
            if chain in self._parts:
                removed.append(chain)
                wrels_chain = self._parts[
                    "xl/_rels/workbook.xml.rels"].decode("utf8")
                for tag in re.findall(r'<Relationship\b[^>]*/?>',
                                      wrels_chain):
                    if "calcChain" in tag:
                        wrels_chain = wrels_chain.replace(tag, "")
                self._parts["xl/_rels/workbook.xml.rels"] = \
                    wrels_chain.encode("utf8")

        wrels = self._parts["xl/_rels/workbook.xml.rels"].decode("utf8")
        for tag in re.findall(r'<Relationship\b[^>]*/?>', wrels):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
            if attrs.get("Id") == rid:
                wrels = wrels.replace(tag, "")
        self._parts["xl/_rels/workbook.xml.rels"] = wrels.encode("utf8")

        ct = self._parts["[Content_Types].xml"].decode("utf8")
        for gone in removed:
            for tag in re.findall(r'<Override\b[^>]*/?>', ct):
                if f'PartName="/{gone}"' in tag:
                    ct = ct.replace(tag, "")
        self._parts["[Content_Types].xml"] = ct.encode("utf8")

        # docProps/app.xml lists every sheet and counts them; a list that
        # disagrees with the workbook makes Excel offer to repair the file
        app_part = "docProps/app.xml"
        if app_part in self._parts:
            app = self._parts[app_part].decode("utf8")
            entry = f"<vt:lpstr>{xml_escape(sheet)}</vt:lpstr>"
            if entry in app:
                app = app.replace(entry, "", 1)
                app = re.sub(
                    r'(<vt:vector size=")(\d+)(" baseType="lpstr">)',
                    lambda m: m.group(1) + str(int(m.group(2)) - 1)
                    + m.group(3), app, count=1)
                app = re.sub(
                    r'(<vt:lpstr>Worksheets</vt:lpstr></vt:variant>'
                    r'<vt:variant><vt:i4>)(\d+)(</vt:i4>)',
                    lambda m: m.group(1) + str(int(m.group(2)) - 1)
                    + m.group(3), app, count=1)
                self._parts[app_part] = app.encode("utf8")

        for gone in removed:
            self._parts.pop(gone, None)
            if gone in self._names:
                self._names.remove(gone)
        self._sheet_part.pop(sheet, None)
        self._pending.pop(sheet, None)
        self._hidden.pop(sheet, None)
        return removed

    def remove_pictures(self) -> int:
        """Drop every picture, keeping the charts in the same drawing part.

        A drawing part holds pictures and charts side by side. Deleting the
        part would take the charts with it, so only the <xdr:pic> anchors
        go, along with the image relationships they were the last user of.
        """
        gone = 0
        used: Dict[str, int] = {}
        for name in list(self._parts):
            if not re.fullmatch(r'xl/drawings/drawing\d+\.xml', name):
                continue
            xml = self._parts[name].decode("utf8")
            kept = []
            # the prefix is not fixed: this model writes xdr:, other
            # writers declare the drawing namespace as the default and
            # write the same elements bare
            for m in re.finditer(
                    r'<(xdr:)?(twoCellAnchor|oneCellAnchor|absoluteAnchor)\b'
                    r'.*?</\1?\2>', xml, re.S):
                if re.search(r'<(xdr:)?pic[\s>]', m.group(0)):
                    kept.append(m.group(0))
            for anchor in kept:
                xml = xml.replace(anchor, "")
                gone += 1
            self._parts[name] = xml.encode("utf8")
            rels_name = name.replace("drawings/", "drawings/_rels/") + ".rels"
            if rels_name not in self._parts:
                continue
            rels = self._parts[rels_name].decode("utf8")
            for tag in re.findall(r'<Relationship\b[^>]*/?>', rels):
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
                tgt = attrs.get("Target", "")
                if "media/" not in tgt:
                    continue
                if attrs.get("Id", "") in xml:
                    used[tgt] = used.get(tgt, 0) + 1
                    continue
                rels = rels.replace(tag, "")
            self._parts[rels_name] = rels.encode("utf8")

        for name in list(self._parts):
            if not name.startswith("xl/media/"):
                continue
            if any(name.endswith(t.rsplit("/", 1)[-1]) for t in used):
                continue
            self._parts.pop(name)
            if name in self._names:
                self._names.remove(name)
        return gone

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

    def _apply_hidden(self) -> None:
        for sheet, spans in self._hidden.items():
            part = self._sheet_part[sheet]
            self._expand_shared(part)
            xml = self._parts[part].decode("utf8")

            def one_row(m: re.Match) -> str:
                whole = m.group(0)
                r = int(re.search(r'r="(\d+)"', whole).group(1))
                if not any(a <= r <= b for a, b in spans):
                    return whole
                if 'hidden="1"' in whole:
                    return whole
                head_end = whole.index(">") if m.group(2) is not None \
                    else whole.index("/>")
                return (whole[:head_end] + ' hidden="1"'
                        + whole[head_end:])

            self._parts[part] = _ROW.sub(one_row, xml).encode("utf8")

    def _flush(self) -> None:
        """Write the queued edits into the sheet XML.

        Anything that reads the sheets rather than writing them - counting
        which shared strings are still referenced, say - has to run after
        this, or it reads the file as it was before the edit and reaches
        the opposite conclusion.
        """
        for sheet, se in self._pending.items():
            if se.edits:
                self._patch_sheet(sheet, se.edits)
        self._pending.clear()
        self._apply_hidden()
        self._hidden.clear()

    def save(self, dest: str) -> None:
        self._flush()
        self._force_recalc()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for n in self._names:
                z.writestr(n, self._parts[n])
