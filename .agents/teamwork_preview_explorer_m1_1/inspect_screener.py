import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

snap_path = "data/screener_snapshot.json"
summary = {}
if os.path.exists(snap_path):
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    summary["type"] = str(type(data))
    if isinstance(data, dict):
        summary["keys_count"] = len(data)
        keys = list(data.keys())
        summary["sample_keys"] = keys[:10]
        sample_tickers = ["HPG", "VNM", "FPT", "MWG", "VIC", "VHM", "GAS", "MBB"]
        for t in sample_tickers:
            if t in data:
                item = data[t]
                summary[f"sample_{t}"] = {
                    "keys": list(item.keys()) if isinstance(item, dict) else str(type(item)),
                    "data": {k: item[k] for k in list(item.keys()) if any(x in k.lower() for x in [
                        "rev", "cog", "receiv", "inv", "pay", "wc", "ar", "ap", "asset", "liab", "cash", "debt", "ebit", "icb", "sector"
                    ])} if isinstance(item, dict) else {}
                }
    elif isinstance(data, list):
        summary["length"] = len(data)
        summary["sample_item_0"] = data[0] if len(data) > 0 else None

out_path = ".agents/teamwork_preview_explorer_m1_1/screener_summary.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("Saved screener summary to", out_path)
