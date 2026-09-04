import json
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "historical_prices.json")
if os.path.exists(db_path):
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    symbols = data.get("symbols", {})
    fixed_count = 0
    for sym, s_data in symbols.items():
        quarters = s_data.get("quarters", {})
        for q_code, q in quarters.items():
            sp = float(q.get("start_price", 0.0))
            cp = float(q.get("close_price", 0.0))
            hi = float(q.get("high", 0.0))
            lo = float(q.get("low", 0.0))

            changed = False
            # Revert any corrupted prices that were mistakenly multiplied by 1000
            # (In VN stock market, almost no stock trades above 350,000 VND, so 300k-500k for penny stocks like NOS, HLA, PXM was 300đ-500đ * 1000)
            if sp >= 300000.0 and sym not in ['VCF', 'WCS']:
                sp /= 1000.0
                q["start_price"] = round(sp, 2)
                changed = True
            if cp >= 300000.0 and sym not in ['VCF', 'WCS']:
                cp /= 1000.0
                q["close_price"] = round(cp, 2)
                changed = True
            if hi >= 300000.0 and sym not in ['VCF', 'WCS']:
                hi /= 1000.0
                q["high"] = round(hi, 2)
            if lo >= 300000.0 and sym not in ['VCF', 'WCS']:
                lo /= 1000.0
                q["low"] = round(lo, 2)

            # Recompute exact return_pct
            if sp > 0 and cp > 0:
                ret = round(((cp - sp) / sp) * 100.0, 2)
                if abs(ret - float(q.get("return_pct", 0.0))) > 0.05:
                    q["return_pct"] = ret
                    changed = True

            if changed:
                fixed_count += 1

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Fixed {fixed_count} quarter rows in historical_prices.json successfully.")
