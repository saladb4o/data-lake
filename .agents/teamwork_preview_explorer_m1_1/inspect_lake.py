import json
import os
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

lake_path = "data/financial_models.json"
summary = {}
if os.path.exists(lake_path):
    with open(lake_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    summary["type"] = str(type(data))
    if isinstance(data, list):
        summary["length"] = len(data)
        if len(data) > 0:
            summary["item_0_keys"] = list(data[0].keys())
            summary["item_0_sample"] = {k: data[0][k] for k in list(data[0].keys())[:20]}
            # Check how symbols are represented
            symbols = [item.get("symbol") or item.get("ticker") for item in data if isinstance(item, dict)]
            summary["first_10_symbols"] = symbols[:10]
            # Find a VN30 stock, e.g., VNM, HPG, FPT, VHM, MWG
            for s in ["HPG", "VNM", "FPT", "MWG"]:
                match = [item for item in data if isinstance(item, dict) and (item.get("symbol") == s or item.get("ticker") == s)]
                if match:
                    summary[f"sample_{s}"] = match[0]
    elif isinstance(data, dict):
        summary["keys_count"] = len(data)
        summary["keys_sample"] = list(data.keys())[:10]

out_path = ".agents/teamwork_preview_explorer_m1_1/lake_summary.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("Saved inspection summary to", out_path)
