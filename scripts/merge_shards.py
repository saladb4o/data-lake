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
                                existing_p = len(merged_data.get(sym, {}).get("periods", []))
                                new_p = len(sinfo.get("periods", []))
                                if sym not in merged_data or new_p >= existing_p:
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


def main():
    parser = argparse.ArgumentParser(description="Merge distributed BCTC shards into unified lake")
    parser.add_argument("--input-dir", type=str, default="./shards", help="Directory containing bctc_shard_*.json")
    parser.add_argument("--output-file", type=str, default="./extracted_bctc_lake.json", help="Output JSON path")
    parser.add_argument("--base-lake", type=str, default="", help="Optional base extracted_bctc_lake.json")
    args = parser.parse_args()

    merge_shards(args.input_dir, args.output_file, args.base_lake)


if __name__ == "__main__":
    main()
