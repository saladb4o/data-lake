# ICB Mapping (industries.json) Encoding Diagnosis & Rebuild Report

Date: 2026-08-23
Script: `scripts/rebuild_industries_mapping.py`
Data: `data/industries.json` — 8186 rows, keys `symbol, organ_name, com_type_code, icb_level, icb_code, icb_name`

## 1. Encoding diagnosis

**Finding: the file was NOT actually corrupted.** Byte-level inspection showed
`data/industries.json` is valid UTF-8 with correct Vietnamese diacritics:

- `"Tài chính"` appears in raw bytes as `b'T\xc3\xa0i ch\xc3\xadnh'` (correct UTF-8
  for U+00E0 à, U+00ED í).
- All 130 distinct `icb_name` values are proper Vietnamese
  (`'Ngân hàng'`, `'Bất động sản'`, `'Chứng chỉ quỹ'`-family names, etc.).
- 2017 of 2046 distinct `organ_name` values contain correct Vietnamese
  Extended Additional characters (U+1EA0–U+1EF9); the remaining 29 are
  legitimately Latin/English fund names (`'VinaCapital Vietnam Access Fund
  Limited'`, `'Global X MSCI Vietnam ETF'`, …).
- Zero occurrences of U+FFFD replacement chars, control characters, or literal
  `?` substitution anywhere in text fields.

Decoding permutations tested against known-good words ("Tài chính", "Ngân hàng"):

| Candidate transform | Result |
|---|---|
| utf-8 → latin-1 roundtrip | Produces garbage (`Tà\x00i`-style); rejected by scoring |
| utf-8 → cp1258 / cp1252 roundtrip | No improvement; input already valid |
| NFC/NFKC normalization | No-op (already composed form) |

**Root cause of the "mojibake" appearance:** a console rendering artifact.
PowerShell on this machine uses a legacy codepage that cannot render Vietnamese
diacritics, so correct strings like `Quỹ đầu tư` display as `Qu??1 ????u t??`
and `Tài chính` as `TAi chA-nh`. Reading via Python with explicit UTF-8
(`python -X utf8`, output redirected to a UTF-8 file) shows the true, intact
text. The earlier "double-encoded UTF-8/Latin-1" hypothesis from an earlier
sync is disproven.

## 2. Fix applied

`scripts/rebuild_industries_mapping.py` implements a defensive repair pass:

- **Detection:** heuristic mojibake fingerprints (`Ã`, stray `Â`, `â€`,
  C1-control bytes, U+FFFD) plus a Vietnamese-diacritic scoring function that
  ranks candidate repairs (`latin-1→utf-8`, `cp1252→utf-8` roundtrips, NFC)
  against reference words.
- **Idempotence:** clean Vietnamese always scores strictly higher than any
  decoding permutation, so clean input is returned unchanged every run.
  Verified: two consecutive runs produce byte-identical output
  (in-script idempotence check: PASS).
- **Safety:** backup written to `data/industries.json.bak` only if absent;
  non-text fields (`com_type_code`, `icb_level`, `icb_code`) asserted unmutated;
  row count / key set / key order / symbol order validated before and after
  write; atomic write via temp file + `os.replace`.

On this dataset the transform found **0 fields needing repair** — as expected
given the diagnosis. The script rewrote the file canonically (UTF-8, 2-space
indent), shrinking it 1,815,647 → 1,750,158 bytes purely from formatting.

## 3. Before/after samples

Because there was nothing to fix, "before" and "after" are identical at the
data level. What changes is only how terminals *display* them:

| Field | File content (true value) | Broken terminal display |
|---|---|---|
| organ_name | `Quỹ Đầu tư A+` | `Qu??1 ????u t?? A+` |
| icb_name | `Tài chính` | `TAi chA-nh` |
| icb_name | `Dịch vụ tài chính` | `DA<ch v??? tAi chA-nh` |

## 4. Coverage stats (level-2 ICB vs SECTOR_ICB_REGISTRY)

File contains 19 distinct L2 `icb_codes`; all 17 registry codes are present.
Extra L2 codes in file not referenced by registry: `5500` (Truyền thông),
`5700` (Du lịch và Giải trí) — both are mapped to sectors inside
`sync_universe_from_vnstock`'s SECTOR_MAP_ICB, so they are intentional.

| Sector | Name | Registry icb_codes | Symbols mapped (L2, funds excluded) |
|---|---|---|---|
| VNREAL | Bất Động Sản | 8600 | 145 |
| VNFIN | Tài Chính & Ngân Hàng | 8300, 8500, 8700 | 97 |
| VNIT | Công Nghệ Thông Tin | 6500, 9500 | 42 |
| VNMAT | Tài Nguyên, Thép & Hóa Chất | 1300, 1700 | 205 |
| VNIND | Công Nghiệp & Xây Dựng | 2300, 2700 | 706 |
| VNCONS | Hàng Tiêu Dùng Thiết Yếu | 3500 | 179 |
| VNCOND | Hàng Tiêu Dùng & Bán Lẻ | 3300, 3700, 5300 | 146 |
| VNENE | Năng Lượng & Dầu Khí | 0500 | 12 |
| VNUTI | Điện, Nước & Tiện Ích | 7500 | 165 |
| VNHEAL | Chăm Sóc Sức Khỏe & Dược | 4500 | 69 |

## 5. Consumer verification

Consumers inventoried (grep `industries.json` over *.py/*.js):
`services/stock_service.py` (:280 read in `sync_universe_from_vnstock`,
:483 read in `load_master_universe`) and `services/sector_index_service.py`
(:125 read in `get_sector_constituents`). Both open the file with
`encoding="utf-8"`. No JS consumers.

Smoke results after rebuild:

- `services.stock_service.load_master_universe()` → ALL_SYMBOLS_MAP built with
  5041 symbols; FPT → sector `VNIT` (icb 9500), VCB → sector `VNFIN`;
  `industry` field carries proper Vietnamese (`Phần mềm`).
- `services.sector_index_service.get_sector_constituents()` → VNFIN=97,
  VNREAL=145, VNIT=42, VNHEAL=69 constituents — exactly matching the coverage
  report above (both icb-code path and Vietnamese name-matching path work).
  Note: this service caches constituents per-process for 900 s and the
  registry for 600 s; restart any long-running server process to pick up the
  rewritten file.
- Tests: `pytest tests/test_universe_cache.py tests/test_normalizer.py -q -x`
  → **26 passed** in ~27 s. Full suite skipped (networked fetcher tests).

## 6. Recommendation

No data repair was needed. If future syncs appear to corrupt text again, check
the terminal codepage first (`chcp 65001` / `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8`) before assuming file corruption; then run
`python scripts/rebuild_industries_mapping.py --dry-run` which will detect and
repair real double-encoding idempotently.
