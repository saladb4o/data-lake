import json
import os
import sys

def inspect():
    results = {}
    
    # 1. all_symbols.json
    all_syms_path = os.path.join('data', 'all_symbols.json')
    if os.path.exists(all_syms_path):
        with open(all_syms_path, 'r', encoding='utf-8') as f:
            all_syms_data = json.load(f)
        results['all_symbols'] = {
            'type': type(all_syms_data).__name__,
            'count': len(all_syms_data) if isinstance(all_syms_data, (list, dict)) else 0,
            'sample_item': all_syms_data[0] if isinstance(all_syms_data, list) and len(all_syms_data) > 0 else list(all_syms_data.items())[:2]
        }
        if isinstance(all_syms_data, list):
            exchanges = {}
            for item in all_syms_data:
                exch = item.get('exchange') or item.get('exchange_code') or item.get('comGroupCode') or 'Unknown'
                exchanges[exch] = exchanges.get(exch, 0) + 1
            results['all_symbols']['exchanges'] = exchanges
            
    # VN30 list
    vn30_symbols = [
        "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
        "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
        "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
    ]
    results['vn30_target_symbols'] = vn30_symbols

    # 2. financial_models.json
    fm_path = os.path.join('data', 'financial_models.json')
    if os.path.exists(fm_path):
        with open(fm_path, 'r', encoding='utf-8') as f:
            fm_data = json.load(f)
        results['financial_models'] = {
            'type': type(fm_data).__name__,
            'symbol_count': len(fm_data) if isinstance(fm_data, dict) else (len(fm_data) if isinstance(fm_data, list) else 0),
        }
        
        # Check dict keys
        if isinstance(fm_data, dict):
            syms = list(fm_data.keys())
            results['financial_models']['first_10_symbols'] = syms[:10]
            
            # Check VN30 coverage in financial_models
            vn30_found = [s for s in vn30_symbols if s in fm_data]
            vn30_missing = [s for s in vn30_symbols if s not in fm_data]
            results['financial_models']['vn30_found_count'] = len(vn30_found)
            results['financial_models']['vn30_missing'] = vn30_missing
            
            # Sample detailed inspection for a few diverse stocks: VNM (Consumer/Mfg), FPT (Tech), HPG (Industrial/Materials), VCB (Bank), SSI (Securities), MWG (Retail), VIC (Conglomerate/Real estate)
            sample_syms = ['VNM', 'FPT', 'HPG', 'VCB', 'SSI', 'MWG', 'VIC']
            sample_details = {}
            for sym in sample_syms:
                if sym in fm_data:
                    val = fm_data[sym]
                    sample_details[sym] = {
                        'type': type(val).__name__,
                        'keys': list(val.keys()) if isinstance(val, dict) else None,
                    }
                    if isinstance(val, dict):
                        for subk in ['ratios', 'financial_ratios', 'income_statement', 'balance_sheet', 'cash_flow', 'quarterly', 'yearly', 'annual', 'financials', 'statements']:
                            if subk in val:
                                sample_details[sym][f'{subk}_type'] = type(val[subk]).__name__
                                if isinstance(val[subk], dict):
                                    sample_details[sym][f'{subk}_subkeys'] = list(val[subk].keys())[:10]
                                elif isinstance(val[subk], list):
                                    sample_details[sym][f'{subk}_len'] = len(val[subk])
                                    if len(val[subk]) > 0 and isinstance(val[subk][0], dict):
                                        sample_details[sym][f'{subk}_first_item_keys'] = list(val[subk][0].keys())
            results['financial_models']['sample_details'] = sample_details

            # Let's inspect all top-level keys across all symbols in financial_models
            all_top_keys = set()
            for s, d in fm_data.items():
                if isinstance(d, dict):
                    all_top_keys.update(d.keys())
            results['financial_models']['all_top_level_keys'] = list(all_top_keys)
            
            # Deep dive on structure of one standard symbol (e.g. VNM)
            if 'VNM' in fm_data:
                results['financial_models']['VNM_full_structure'] = {
                    k: (list(v.keys()) if isinstance(v, dict) else (len(v) if isinstance(v, list) else str(type(v))))
                    for k, v in fm_data['VNM'].items()
                } if isinstance(fm_data['VNM'], dict) else type(fm_data['VNM']).__name__

    # 3. historical_prices.json
    hp_path = os.path.join('data', 'historical_prices.json')
    if os.path.exists(hp_path):
        with open(hp_path, 'r', encoding='utf-8') as f:
            hp_data = json.load(f)
        results['historical_prices'] = {
            'type': type(hp_data).__name__,
            'count': len(hp_data) if isinstance(hp_data, (dict, list)) else 0,
        }
        if isinstance(hp_data, dict):
            syms = list(hp_data.keys())
            results['historical_prices']['first_10_symbols'] = syms[:10]
            vn30_found = [s for s in vn30_symbols if s in hp_data]
            results['historical_prices']['vn30_found_count'] = len(vn30_found)
            if 'VNM' in hp_data:
                vnm_p = hp_data['VNM']
                results['historical_prices']['VNM_type'] = type(vnm_p).__name__
                if isinstance(vnm_p, list):
                    results['historical_prices']['VNM_len'] = len(vnm_p)
                    results['historical_prices']['VNM_sample_first'] = vnm_p[0] if len(vnm_p) > 0 else None
                    results['historical_prices']['VNM_sample_last'] = vnm_p[-1] if len(vnm_p) > 0 else None
                elif isinstance(vnm_p, dict):
                    results['historical_prices']['VNM_keys'] = list(vnm_p.keys())[:10]
                    
    # 4. other data files
    for fname in ['industries.json', 'screener_snapshot.json', 'models_summary.txt', 'rrg_disk_cache.json']:
        fpath = os.path.join('data', fname)
        if os.path.exists(fpath):
            if fname.endswith('.json'):
                with open(fpath, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                results[fname] = {
                    'type': type(d).__name__,
                    'count': len(d) if isinstance(d, (dict, list)) else 0,
                    'sample_keys': list(d.keys())[:10] if isinstance(d, dict) else None
                }
            else:
                with open(fpath, 'r', encoding='utf-8') as f:
                    results[fname] = f.read(500)

    out_path = os.path.join('.agents', 'teamwork_preview_explorer_survey_1', 'inspect_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("Done inspection written to", out_path)

if __name__ == '__main__':
    inspect()
