import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def fast_inspect():
    report_lines = []
    
    def log(msg=""):
        report_lines.append(str(msg))
        
    log("=== FAST INSPECTION REPORT ===")
    
    # 1. Screener Snapshot
    log("\n--- 1. Screener Snapshot (`data/screener_snapshot.json`) ---")
    with open('data/screener_snapshot.json', 'r', encoding='utf-8') as f:
        ss = json.load(f)
    log(f"Screener keys: {list(ss.keys())}")
    log(f"Screener total stocks: {len(ss.get('stocks', {}))}")
    log(f"Updated at: {ss.get('updated_at')}")
    log(f"Source: {ss.get('source')}")
    
    # Check sample stock: VNM
    vnm = ss.get('stocks', {}).get('VNM', {})
    log(f"\nVNM in screener_snapshot total keys: {len(vnm.keys())}")
    log("VNM screener sample fields:")
    for k in sorted(vnm.keys()):
        val = vnm[k]
        if k == 'percentiles':
            log(f"  {k}: {type(val).__name__} = keys: {list(val.keys())[:5]}... ({len(val)} items)")
        elif k == '_metadata':
            log(f"  {k}: {type(val).__name__} = {val}")
        else:
            log(f"  {k}: {type(val).__name__} = {repr(val)[:80]}")

    # 2. Historical Prices Quarters
    log("\n--- 2. Historical Prices Quarters (`data/historical_prices.json`) ---")
    with open('data/historical_prices.json', 'r', encoding='utf-8') as f:
        hp = json.load(f)
    log(f"Historical prices keys: {list(hp.keys())}")
    log(f"Version: {hp.get('version')}, Last updated: {hp.get('last_updated')}, Source: {hp.get('source')}")
    log(f"Symbols count in historical prices: {len(hp.get('symbols', {}))}")
    
    vnm_hp = hp.get('symbols', {}).get('VNM', {})
    log(f"VNM hp metadata: {[f'{k}: {v}' for k, v in vnm_hp.items() if k != 'quarters']}")
    quarters = vnm_hp.get('quarters', {})
    log(f"VNM total quarters: {len(quarters)}")
    quarter_keys = sorted(quarters.keys())
    log(f"Quarter range: {quarter_keys[0] if quarter_keys else 'none'} to {quarter_keys[-1] if quarter_keys else 'none'}")
    if quarter_keys:
        latest_q = quarter_keys[-1]
        log(f"Latest quarter ({latest_q}) fields:")
        for qk, qv in quarters[latest_q].items():
            log(f"  {qk}: {type(qv).__name__} = {repr(qv)[:80]}")
            
    # Check VN30 symbols in historical_prices
    vn30_symbols = [
        "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
        "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
        "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
    ]
    vn30_stats = []
    for sym in vn30_symbols:
        s_hp = hp.get('symbols', {}).get(sym, {})
        sq = s_hp.get('quarters', {})
        vn30_stats.append({
            'symbol': sym,
            'exchange': s_hp.get('exchange', 'N/A'),
            'quarter_count': len(sq),
            'earliest': min(sq.keys()) if sq else 'none',
            'latest': max(sq.keys()) if sq else 'none',
        })
    log(f"\nVN30 Historical Quarter Coverage:")
    for s in vn30_stats:
        log(f"  {s['symbol']} ({s['exchange']}): {s['quarter_count']} quarters ({s['earliest']} -> {s['latest']})")

    # 3. Financial Models (Metadata Schema)
    log("\n--- 3. Financial Models Schema (`data/financial_models.json`) ---")
    with open('data/financial_models.json', 'r', encoding='utf-8') as f:
        fm = json.load(f)
    log(f"Financial models count: {len(fm)}")
    
    # Categorize items by companyForm and modelTypeName
    by_form = {}
    by_type = {}
    forms_and_types = {}
    for item in fm:
        form = item.get('companyForm', 'UNKNOWN')
        mtype = item.get('modelTypeName', 'UNKNOWN')
        by_form[form] = by_form.get(form, 0) + 1
        by_type[mtype] = by_type.get(mtype, 0) + 1
        ft_key = f"{form}_{mtype}"
        if ft_key not in forms_and_types:
            forms_and_types[ft_key] = []
        forms_and_types[ft_key].append(item)
        
    log(f"By companyForm: {by_form}")
    log(f"By modelTypeName: {by_type}")
    log(f"Unique Form + ModelType combinations: {list(forms_and_types.keys())}")

    for ft_key, items in forms_and_types.items():
        log(f"\n[{ft_key}] (Total items: {len(items)}):")
        # List all items in order
        items_sorted = sorted(items, key=lambda x: (x.get('displayOrder') or 0))
        for it in items_sorted[:15]: # Show first 15 line items
            log(f"   Code {it.get('itemCode')} | Level {it.get('displayLevel')} | Order {it.get('displayOrder')} | {it.get('itemVnName')} | {it.get('itemEnName')}")
        if len(items_sorted) > 15:
            log(f"   ... and {len(items_sorted) - 15} more line items")

    # 4. Search for where actual statement time-series numbers live in codebase
    out_txt = "\n".join(report_lines)
    out_file = os.path.join('.agents', 'teamwork_preview_explorer_survey_1', 'fast_inspect_report.txt')
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(out_txt)
    print(f"Report written to {out_file}")

if __name__ == '__main__':
    fast_inspect()
