#!/usr/bin/env python3
"""Move the per-symbol JSON lakes into the SQLite working store, and back.

The migration is additive and reversible: the JSON files are never modified by
``import``, and ``export`` regenerates them byte-for-byte equivalent. Nothing
downstream (scripts/merge_shards.py, the crawler workflows, the Colab
notebooks) changes, because JSON stays the interchange format.

    # seed the database from the JSON lakes already on disk
    python scripts/migrate_lake_to_sqlite.py import

    # check every symbol survived the round trip
    python scripts/migrate_lake_to_sqlite.py verify

    # regenerate the JSON files from the database
    python scripts/migrate_lake_to_sqlite.py export

Then set DATA_LAKE_BACKEND=sqlite to use it. Unset it to go straight back to
the JSON backend; the JSON files were never taken away.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.lake_store import SQLiteLakeStore  # noqa: E402
from services.stock_service import resolve_data_file  # noqa: E402

# The symbol-keyed lakes. Files with a different shape (screener_snapshot.json
# nests under "stocks", industries.json is not symbol-keyed) are left alone.
LAKE_FILES = (
    "historical_prices.json",
    "financial_statements.json",
    "vndirect_raw_statements.json",
    "precomputed_valuations.json",
    "backtest_results.json",
)


def _lake_name(filename: str) -> str:
    return filename[:-5] if filename.endswith(".json") else filename


def cmd_import(store: SQLiteLakeStore, args) -> int:
    total = 0
    for filename in LAKE_FILES:
        path = resolve_data_file(filename)
        if not os.path.exists(path):
            print(f"  skip   {filename:<32} (not present)")
            continue
        size_mb = os.path.getsize(path) / 1e6
        started = time.time()
        try:
            n = store.import_json(_lake_name(filename), path)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"  FAIL   {filename:<32} {exc}")
            continue
        total += n
        print(f"  import {filename:<32} {n:>6} symbols  {size_mb:7.1f} MB  {time.time()-started:5.2f}s")
    print(f"\n{total} symbols in {store.db_path}")
    return 0


def cmd_export(store: SQLiteLakeStore, args) -> int:
    for filename in LAKE_FILES:
        lake = _lake_name(filename)
        if store.count(lake) == 0:
            continue
        path = resolve_data_file(filename)
        started = time.time()
        n = store.export_json(lake, path, indent=args.indent)
        print(f"  export {filename:<32} {n:>6} symbols  {time.time()-started:5.2f}s -> {path}")
    return 0


def cmd_verify(store: SQLiteLakeStore, args) -> int:
    """Compares every symbol in the database against the JSON on disk."""
    failures = 0
    for filename in LAKE_FILES:
        lake = _lake_name(filename)
        path = resolve_data_file(filename)
        if not os.path.exists(path) or store.count(lake) == 0:
            continue
        with open(path, "r", encoding="utf-8") as fh:
            original = json.load(fh)
        roundtripped = store.get_all(lake)

        missing = set(original) - set(roundtripped)
        extra = set(roundtripped) - set(original)
        differing = [k for k in set(original) & set(roundtripped)
                     if original[k] != roundtripped[k]]

        if missing or extra or differing:
            failures += 1
            print(f"  MISMATCH {filename}")
            if missing:
                print(f"    {len(missing)} missing, e.g. {sorted(missing)[:5]}")
            if extra:
                print(f"    {len(extra)} unexpected, e.g. {sorted(extra)[:5]}")
            if differing:
                print(f"    {len(differing)} differing, e.g. {sorted(differing)[:5]}")
        else:
            print(f"  OK       {filename:<32} {len(original):>6} symbols identical")
    if failures:
        print(f"\n{failures} lake(s) did not round-trip cleanly. Do not switch the backend.")
        return 1
    print("\nEvery lake round-trips identically.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("import", "export", "verify"))
    parser.add_argument("--db", default=None, help="database path (default: data/lake.db)")
    parser.add_argument("--indent", type=int, default=None, help="indent for exported JSON")
    args = parser.parse_args()

    store = SQLiteLakeStore(db_path=args.db)
    print(f"Database: {store.db_path}\n")
    return {"import": cmd_import, "export": cmd_export, "verify": cmd_verify}[args.command](store, args)


if __name__ == "__main__":
    raise SystemExit(main())
