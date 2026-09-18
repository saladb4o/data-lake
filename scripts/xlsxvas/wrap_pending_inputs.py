"""Silence the cells that are only waiting for input, and no others.

Emptying Amazon's comparables leaves the valuation sheets dividing by
nothing, which is the right answer to a question nobody has answered yet
but shows up as a wall of #DIV/0! that hides which cells are genuinely
waiting and which are broken.

The list of cells to wrap is not written by hand. The workbook is handed
to a spreadsheet engine with the peer rows empty, and whatever errors is
what gets wrapped - so a cell is quieted only on evidence that it errors
in the empty state, and a cell that computes today is left alone.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openpyxl

from recalc import recalculate
from xlsx_patch import WorkbookPatch

# The accounting core must never be quieted: a broken identity there is the
# whole point of the template and has to stay visible.
PROTECTED: Set[str] = {"Financial Statements", "Raw Data", "Control Panel"}


def find_error_cells(path: str) -> List[Tuple[str, str, str]]:
    done = recalculate(path)
    values = openpyxl.load_workbook(done, data_only=True)
    formulas = openpyxl.load_workbook(done, data_only=False)
    out = []
    for name in values.sheetnames:
        if name in PROTECTED:
            continue
        vs, fs = values[name], formulas[name]
        for row in vs.iter_rows():
            for cell in row:
                v = cell.value
                if not (isinstance(v, str) and v.startswith("#")
                        and v.endswith("!")):
                    continue
                f = fs[cell.coordinate].value
                if isinstance(f, str) and f.startswith("="):
                    out.append((name, cell.coordinate, f.lstrip("=")))
    return out


def wrap(src: str, dest: str) -> int:
    errors = find_error_cells(src)
    w = WorkbookPatch(src)
    wrapped = 0
    for sheet, ref, formula in errors:
        if formula.upper().startswith("IFERROR("):
            continue
        w.set_formula(sheet, ref, f'IFERROR({formula},"")')
        wrapped += 1
    w.save(dest)
    return wrapped


if __name__ == "__main__":
    n = wrap(sys.argv[1], sys.argv[2])
    print(f"wrapped {n} cells awaiting input -> {sys.argv[2]}")
