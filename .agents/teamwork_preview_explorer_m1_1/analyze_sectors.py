import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

with open(".agents/teamwork_preview_explorer_m1_1/vn30_wc_audit.json", "r", encoding="utf-8") as f:
    vn30 = json.load(f)

sector_counts = {}
for sym, d in vn30.items():
    sec = d.get("sector", "DEFAULT")
    sector_counts[sec] = sector_counts.get(sec, 0) + 1

print("VN30 Sector Distribution:")
for s, c in sorted(sector_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {s}: {c} symbols")
