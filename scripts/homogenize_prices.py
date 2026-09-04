import json
import os
import numpy as np

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "historical_prices.json")
if os.path.exists(db_path):
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    symbols = data.get("symbols", {})
    fixed_count = 0

    for sym, s_data in symbols.items():
        quarters = s_data.get("quarters", {})
        if not quarters:
            continue

        # Find median positive price for this symbol across all quarters
        all_prices = []
        for q in quarters.values():
            sp = float(q.get("start_price", 0.0))
            cp = float(q.get("close_price", 0.0))
            if sp > 0:
                all_prices.append(sp)
            if cp > 0:
                all_prices.append(cp)

        if not all_prices:
            continue

        # If most prices are in full VND (> 1000), any price < 1000 that is clearly a 1/1000 scale should be scaled up
        high_prices = [p for p in all_prices if p >= 1000]
        is_vnd_stock = len(high_prices) > len(all_prices) * 0.4
        normal_level = np.median(high_prices) if high_prices else np.median(all_prices)

        prev_c = None
        for q_code in sorted(quarters.keys()):
            q = quarters[q_code]
            sp = float(q.get("start_price", 0.0))
            cp = float(q.get("close_price", 0.0))
            hi = float(q.get("high", 0.0))
            lo = float(q.get("low", 0.0))

            changed = False
            if is_vnd_stock:
                # If normal level is e.g. 50,000 or 250,000, and this quarter price is < 1000 (e.g. 50.0 or 250.0)
                if 0 < sp < 1000 and (sp * 1000 <= normal_level * 5.0 or normal_level > 5000):
                    sp *= 1000.0
                    q["start_price"] = round(sp, 2)
                    changed = True
                if 0 < cp < 1000 and (cp * 1000 <= normal_level * 5.0 or normal_level > 5000):
                    cp *= 1000.0
                    q["close_price"] = round(cp, 2)
                    changed = True
                if 0 < hi < 1000 and (hi * 1000 <= normal_level * 5.0 or normal_level > 5000):
                    hi *= 1000.0
                    q["high"] = round(hi, 2)
                    changed = True
                if 0 < lo < 1000 and (lo * 1000 <= normal_level * 5.0 or normal_level > 5000):
                    lo *= 1000.0
                    q["low"] = round(lo, 2)
                    changed = True

            # If start_price doesn't match prev close (e.g. step gap due to different source), align with prev_c if sensible
            if prev_c is not None and prev_c > 0:
                if sp <= 0 or abs(sp - prev_c) / prev_c > 3.0:
                    # Likely a jump or missing start price, anchor to prev_c
                    sp = prev_c
                    q["start_price"] = round(sp, 2)
                    changed = True

            if sp > 0 and cp > 0:
                ret = round(((cp - sp) / sp) * 100.0, 2)
                # Cap impossible extreme quarterly return jumps (> 300% on normal stocks with no split)
                if ret > 300.0 and len(quarters) > 8 and is_vnd_stock:
                    # Sanitize outlier
                    ret = min(ret, 150.0)
                if abs(ret - float(q.get("return_pct", 0.0))) > 0.05:
                    q["return_pct"] = ret
                    changed = True
                prev_c = cp
            else:
                prev_c = None

            if changed:
                fixed_count += 1

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Homogenized and cleaned {fixed_count} quarter rows in historical_prices.json successfully.")
