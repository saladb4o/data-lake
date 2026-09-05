"""
=============================================================================
BCTC SHARD MERGER
=============================================================================
Combines distributed worker outputs (bctc_shard_*.json) into extracted_bctc_lake.json.
"""

import os
import sys
import json
import re
import argparse
from typing import Dict, Any


def merge_shards(input_dir: str, output_file: str, base_lake_file: str = "") -> Dict[str, Any]:
    merged_data: Dict[str, Any] = {}

    # 1. Base lake if provided
    if base_lake_file and os.path.exists(base_lake_file):
        try:
            with open(base_lake_file, "r", encoding="utf-8") as f:
                merged_data = json.load(f)
            print(f"📚 Loaded base lake with {len(merged_data)} symbols")
        except Exception as err:
            print(f"Warning loading base lake: {err}")

    # 2. Iterate through shards
    shard_count = 0
    if os.path.isdir(input_dir):
        for root, _, files in os.walk(input_dir):
            for fname in files:
                if re.match(r"^bctc_shard_\d+\.json$", fname):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            sdata = json.load(f)
                        if isinstance(sdata, dict):
                            for sym, sinfo in sdata.items():
                                existing_entry = merged_data.get(sym, {})
                                existing_periods = existing_entry.get("periods", [])
                                new_periods = sinfo.get("periods", [])

                                # Calculate quality score: real balance sheet items + footnotes
                                existing_score = sum(
                                    len(p.get("extracted_data", {}).get("balance_sheet", {}).get("items", {})) +
                                    len(p.get("extracted_data", {}).get("footnotes", {}).get("debt_facilities", []))
                                    for p in existing_periods
                                ) if isinstance(existing_entry, dict) else 0

                                new_score = sum(
                                    len(p.get("extracted_data", {}).get("balance_sheet", {}).get("items", {})) +
                                    len(p.get("extracted_data", {}).get("footnotes", {}).get("debt_facilities", []))
                                    for p in new_periods
                                )

                                if sym not in merged_data or new_score > existing_score or (new_score == existing_score and len(new_periods) >= len(existing_periods)):
                                    merged_data[sym] = sinfo
                            shard_count += 1
                            print(f"  ✅ Merged {fname} ({len(sdata)} symbols)")
                    except Exception as err:
                        print(f"Error reading shard {fpath}: {err}")

    print(f"🎯 Successfully merged {shard_count} shards. Total symbols in lake: {len(merged_data)}")

    # 3. Save output
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    tmp_out = output_file + ".tmp"
    with open(tmp_out, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_out, output_file)
    print(f"💾 Saved merged lake to: {output_file} ({round(os.path.getsize(output_file)/(1024*1024), 2)} MB)")
    return merged_data


def merge_corporate_shards(input_dir: str, output_file: str, base_lake_file: str = "") -> Dict[str, Any]:
    merged_data: Dict[str, Any] = {}

    if base_lake_file and os.path.exists(base_lake_file):
        try:
            with open(base_lake_file, "r", encoding="utf-8") as f:
                merged_data = json.load(f)
            print(f"📚 Loaded base corporate actions lake with {len(merged_data)} symbols")
        except Exception as err:
            print(f"Warning loading base corporate lake: {err}")

    shard_count = 0
    if os.path.isdir(input_dir):
        for root, _, files in os.walk(input_dir):
            for fname in files:
                if re.match(r"^corporate_shard_\d+\.json$", fname):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            sdata = json.load(f)
                        if isinstance(sdata, dict):
                            for sym, sinfo in sdata.items():
                                existing_cnt = len(merged_data.get(sym, {}).get("records", []))
                                new_cnt = len(sinfo.get("records", []))
                                if sym not in merged_data or new_cnt >= existing_cnt:
                                    merged_data[sym] = sinfo
                            shard_count += 1
                            print(f"  ✅ Merged {fname} ({len(sdata)} corporate symbols)")
                    except Exception as err:
                        print(f"Error reading corporate shard {fpath}: {err}")

    print(f"🎯 Successfully merged {shard_count} corporate shards. Total symbols: {len(merged_data)}")
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    tmp_out = output_file + ".tmp"
    with open(tmp_out, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_out, output_file)
    print(f"💾 Saved merged corporate lake to: {output_file} ({round(os.path.getsize(output_file)/(1024*1024), 2)} MB)")
    return merged_data


def main():
    parser = argparse.ArgumentParser(description="Merge distributed BCTC & Corporate shards into unified lake")
    parser.add_argument("--input-dir", type=str, default="./shards", help="Directory containing shard JSONs")
    parser.add_argument("--output-file", type=str, default="./data/pdf_lake/extracted_bctc_lake.json", help="BCTC Output JSON path")
    parser.add_argument("--base-lake", type=str, default="", help="Optional base extracted_bctc_lake.json")
    parser.add_argument("--corp-output-file", type=str, default="./data/pdf_lake/extracted_corporate_actions.json", help="Corporate Output JSON path")
    parser.add_argument("--corp-base-lake", type=str, default="", help="Optional base extracted_corporate_actions.json")
    args = parser.parse_args()

    # 1. Merge BCTC Shards
    print("--- MERGING BCTC SHARDS ---")
    merge_shards(args.input_dir, args.output_file, args.base_lake)

    # 2. Merge Corporate Actions Shards
    print("\n--- MERGING CORPORATE DISCLOSURES SHARDS ---")
    merge_corporate_shards(args.input_dir, args.corp_output_file, args.corp_base_lake)


if __name__ == "__main__":
    main()
