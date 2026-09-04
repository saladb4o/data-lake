import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

snap_path = "data/screener_snapshot.json"
summary = {}
if os.path.exists(snap_path):
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data.get("stocks", {})
    summary["total_stocks"] = len(stocks)
    sample_tickers = ["HPG", "VNM", "FPT", "MWG", "VIC", "VHM", "GAS", "MBB"]
    for t in sample_tickers:
        if t in stocks:
            item = stocks[t]
            summary[f"stock_{t}"] = item

out_path = ".agents/teamwork_preview_explorer_m1_1/stocks_sample.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("Saved stocks sample to", out_path)
