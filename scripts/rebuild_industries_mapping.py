#!/usr/bin/env python3
"""Rebuild / repair data/industries.json (ICB classification mapping).

What this script does:
  1. Backs up the original to data/industries.json.bak (only if .bak absent).
  2. Fixes mojibake in organ_name / icb_name fields. The transform is
     idempotent: already-clean Vietnamese text is detected and left untouched,
     so running the script twice never double-transforms.
  3. Validates the output schema is preserved exactly (same keys per row,
     same row count, same symbol order).
  4. Prints a coverage report comparing level-2 icb_codes found in the file
     against services.stock_service.SECTOR_ICB_REGISTRY, including symbols
     mapped per registry sector.
  5. Writes atomically (temp file + os.replace).

Diagnosis summary (2026-08):
  Byte-level inspection showed data/industries.json is ALREADY valid UTF-8
  with correct Vietnamese diacritics ("Tài chính" = b'T\xc3\xa0i ch\xc3\xadnh').
  The "mojibake" observed in terminals was a PowerShell console codepage
  rendering artifact, not file corruption. The repair pass below is kept as
  a defensive no-op for clean input so the script remains safe to re-run if
  a future sync reintroduces real double-encoding.

Usage:
    python scripts/rebuild_industries_mapping.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unicodedata
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "industries.json")
BACKUP_PATH = DATA_PATH + ".bak"

EXPECTED_KEYS = ["symbol", "organ_name", "com_type_code", "icb_level", "icb_code", "icb_name"]
TEXT_FIELDS = ("organ_name", "icb_name")

# Known-good Vietnamese reference words used to score candidate decodings.
REFERENCE_WORDS = [
    "Tài chính", "Ngân hàng", "Công ty", "Cổ phần", "Bất động sản",
    "Dược phẩm", "Thực phẩm", "Viễn thông", "Xây dựng", "Quỹ đầu tư",
]

# Characters that appear in properly encoded Vietnamese but NOT in typical
# mojibake artifacts; used together with mojibake signatures below.
MOJIBAKE_SIGNATURES = (
    "Ã",       # utf-8 read as latin-1/cp1252 leaves Ã + continuation byte
    "Â ",      # stray Â from decoded combining bytes
    "â€",      # cp1252 rendering of UTF-8 punctuation bytes
    "å\u008d", # CJK-ish double-encode leftovers
    "\ufffd",  # explicit replacement char
)


def _vn_diacritic_score(text: str) -> int:
    """Count Vietnamese-specific letters in *text*."""
    viet_letters = set("ăâêôơưđĂÂÊÔƠƯĐ")
    score = 0
    for ch in text:
        cp = ord(ch)
        if 0x1EA0 <= cp <= 0x1EF9:  # Latin Extended Additional (VN tones)
            score += 2
        elif ch in viet_letters:
            score += 1
    return score


def _looks_mojibake(text: str) -> bool:
    """Heuristic: does *text* carry classic double-encoding fingerprints?"""
    if not text:
        return False
    if any(sig in text for sig in MOJIBAKE_SIGNATURES):
        return True
    # High ratio of latin-1 supplement chars (0x80-0x9F range is invalid
    # standalone Unicode in sane text) is another tell.
    weird = sum(1 for ch in text if 0x80 <= ord(ch) <= 0x9F)
    return weird > max(1, len(text) // 10)


def fix_mojibake(text: str) -> tuple[str, bool]:
    """Repair double-encoded text; return (fixed_text, changed).

    Idempotent: clean Vietnamese scores strictly better than any decoding
    permutation, so it is returned unchanged on every invocation.
    """
    if not text or not _looks_mojibake(text):
        return text, False

    best = text
    best_score = _vn_diacritic_score(text)

    candidates: list[str] = []
    # utf-8 bytes mis-decoded as latin-1 -> re-encode latin-1, decode utf-8
    try:
        candidates.append(text.encode("latin-1").decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        logger.debug("fix_mojibake: swallowed (UnicodeEncodeError, UnicodeDecodeError)", exc_info=True)
    # utf-8 bytes mis-decoded as cp1252 (Windows) variant
    try:
        candidates.append(text.encode("cp1252").decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        logger.debug("fix_mojibake: swallowed (UnicodeEncodeError, UnicodeDecodeError)", exc_info=True)
    # NFKC normalization helps when combining marks were mangled separately
    candidates.append(unicodedata.normalize("NFC", text))

    for cand in candidates:
        score = sum(1 for w in REFERENCE_WORDS if w in cand) * 10 + _vn_diacritic_score(cand)
        if score > best_score:
            best, best_score = cand, score

    return best, best != text


def validate(original: list[dict], rebuilt: list[dict]) -> list[str]:
    errors: list[str] = []
    if len(original) != len(rebuilt):
        errors.append(f"row count changed: {len(original)} -> {len(rebuilt)}")
        return errors
    for i, (o, n) in enumerate(zip(original, rebuilt)):
        if list(o.keys()) != EXPECTED_KEYS and set(o.keys()) != set(EXPECTED_KEYS):
            errors.append(f"row {i}: unexpected key set {sorted(o.keys())}")
        if set(o.keys()) != set(n.keys()):
            errors.append(f"row {i}: keys changed {sorted(o.keys())} -> {sorted(n.keys())}")
        if o.get("symbol") != n.get("symbol"):
            errors.append(f"row {i}: symbol order changed {o.get('symbol')!r} -> {n.get('symbol')!r}")
        if list(n.keys()) != list(o.keys()):
            errors.append(f"row {i}: key order changed")
        for f in ("com_type_code", "icb_level", "icb_code"):
            if o.get(f) != n.get(f):
                errors.append(f"row {i} ({n.get('symbol')}): non-text field {f} mutated")
        if len(errors) > 20:
            errors.append("...too many errors, aborting validation listing")
            break
    return errors


def coverage_report(data: list[dict]) -> str:
    sys.path.insert(0, BASE_DIR)
    from services.stock_service import SECTOR_ICB_REGISTRY

    l2_codes_found = sorted({str(r["icb_code"]) for r in data if r.get("icb_level") == 2})
    lines: list[str] = []
    lines.append("=== Coverage report ===")
    lines.append(f"rows total           : {len(data)}")
    lines.append(f"distinct L2 icb_codes: {len(l2_codes_found)}")

    reg_codes = {}
    for code, meta in SECTOR_ICB_REGISTRY.items():
        for c in str(meta.get("icb_code", "")).split(","):
            c = c.strip()
            if c:
                reg_codes.setdefault(c, []).append(code)

    missing = [c for c in reg_codes if c not in l2_codes_found]
    extra = [c for c in l2_codes_found if c not in reg_codes]
    lines.append(f"registry icb_codes   : {len(reg_codes)} distinct across {len(SECTOR_ICB_REGISTRY)} sectors")
    lines.append(f"registry codes MISSING from file L2 : {missing or 'none'}")
    lines.append(f"file L2 codes not in registry       : {extra}")

    lines.append("")
    lines.append("Symbols mapped per registry sector (level-2 match, funds excluded):")
    for sector_code, meta in SECTOR_ICB_REGISTRY.items():
        codes = {c.strip() for c in str(meta.get("icb_code", "")).split(",") if c.strip()}
        syms = sorted({
            str(r["symbol"]).upper()
            for r in data
            if r.get("icb_level") == 2
            and str(r["icb_code"]) in codes
            and r.get("com_type_code") != "QU"
        })
        lines.append(f"  {sector_code:<7} ({meta['name']:<32}) icb={','.join(sorted(codes)):<15} symbols={len(syms):>4}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate + report without writing")
    args = parser.parse_args()

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        original = json.load(f)

    if not isinstance(original, list):
        print("FATAL: industries.json root is not an array", file=sys.stderr)
        return 1

    changed_fields = []
    rebuilt = []
    for row in original:
        new_row = dict(row)
        for field in TEXT_FIELDS:
            fixed, changed = fix_mojibake(row.get(field, ""))
            new_row[field] = fixed
            if changed:
                changed_fields.append((row.get("symbol"), field, row.get(field), fixed))
        rebuilt.append(new_row)

    errors = validate(original, rebuilt)
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 1

    report = coverage_report(rebuilt)

    if changed_fields:
        print(f"Repaired {len(changed_fields)} mojibake field(s). Samples:")
        for sym, field, before, after in changed_fields[:10]:
            print(f"  [{sym}] {field}:")
            print(f"    before: {before!r}")
            print(f"    after : {after!r}")
    else:
        print("No mojibake detected - all organ_name/icb_name values are clean UTF-8.")

    print(report)

    if args.dry_run:
        print("[dry-run] no changes written.")
        return 0

    if not os.path.exists(BACKUP_PATH):
        with open(BACKUP_PATH, "wb") as fb:
            with open(DATA_PATH, "rb") as fr:
                fb.write(fr.read())
        print(f"Backup written: {BACKUP_PATH}")
    else:
        print(f"Backup already exists, untouched: {BACKUP_PATH}")

    # Atomic write: serialize first, then temp file + os.replace.
    payload = json.dumps(rebuilt, ensure_ascii=False, indent=2)
    dir_ = os.path.dirname(DATA_PATH)
    fd, tmp_path = tempfile.mkstemp(prefix=".industries_", suffix=".json.tmp", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as ft:
            ft.write(payload)
        os.replace(tmp_path, DATA_PATH)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    print(f"Atomically wrote {DATA_PATH} ({os.path.getsize(DATA_PATH)} bytes)")

    # Idempotence proof: re-run the transform on our own output.
    second_pass, second_changed = [], False
    for row in rebuilt:
        nr = dict(row)
        for field in TEXT_FIELDS:
            fixed, changed = fix_mojibake(row.get(field, ""))
            nr[field] = fixed
            second_changed = second_changed or changed
        second_pass.append(nr)
    stable = json.dumps(second_pass, ensure_ascii=False) == json.dumps(rebuilt, ensure_ascii=False)
    print(f"Idempotence check: {'PASS' if stable and not second_changed else 'FAIL'}")

    # Round-trip verification of what consumers will see.
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        reread = json.load(f)
    ok = (
        len(reread) == len(original)
        and [r["symbol"] for r in reread] == [r["symbol"] for r in original]
        and all(list(r.keys()) == list(o.keys()) for r, o in zip(reread, original))
    )
    print(f"Post-write verification: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
