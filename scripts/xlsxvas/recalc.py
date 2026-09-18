"""Make a spreadsheet engine evaluate the workbook and hand back the numbers.

Writing a formula is an assertion that it computes something. Reading back
what a real engine computed is closer to a measurement, and it is the only
way to catch a reference that survived an edit while pointing at the wrong
row.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
import tempfile
from typing import Dict, Iterable, Optional, Tuple

import openpyxl

SOFFICE = "soffice"
PROFILE = "file:///tmp/loprofile"


_CACHED = re.compile(r'(<c\b[^>]*?>)(.*?)(</c>)', re.S)


def strip_cached_values(src: str, dest: str) -> None:
    """Remove every cached result, so the engine has to compute them all.

    A spreadsheet stores each formula next to the last value someone
    computed for it. Asked to open a file, LibreOffice is entitled to trust
    those cached values and recompute nothing. That turned a verification
    run into a reading of the source workbook's old numbers: cells written
    in this session came back correct because they had no cache, while
    every untouched formula still reported what Amazon's model said. Taking
    the cache out first removes the engine's option to agree with itself.
    """
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        parts = {n: z.read(n) for n in names}
    for name in names:
        if not name.startswith("xl/worksheets/sheet"):
            continue
        xml = parts[name].decode("utf8")

        def drop(m: re.Match) -> str:
            head, body, tail = m.groups()
            if "<f" not in body:
                return m.group(0)
            return head + re.sub(r"<v>.*?</v>", "", body, flags=re.S) + tail

        parts[name] = _CACHED.sub(drop, xml).encode("utf8")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, parts[n])


def recalculate(path: str, timeout: int = 900) -> str:
    """Return the path of a copy whose cached values a real engine wrote."""
    out_dir = tempfile.mkdtemp(prefix="recalc-")
    work = os.path.join(out_dir, "in.xlsx")
    strip_cached_values(path, work)
    res = subprocess.run(
        [SOFFICE, f"-env:UserInstallation={PROFILE}", "--headless",
         "--norestore", "--convert-to", "xlsx", "--outdir",
         os.path.join(out_dir, "out"), work],
        capture_output=True, text=True, timeout=timeout)
    done = os.path.join(out_dir, "out", "in.xlsx")
    if not os.path.exists(done):
        raise RuntimeError(
            f"the engine refused the workbook: {res.stdout.strip()} "
            f"{res.stderr.strip()}")
    return done


def read_cells(path: str, wanted: Iterable[Tuple[str, str]]
               ) -> Dict[Tuple[str, str], object]:
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {}
    for sheet, ref in wanted:
        out[(sheet, ref)] = wb[sheet][ref].value if sheet in wb.sheetnames \
            else "<no such sheet>"
    return out
