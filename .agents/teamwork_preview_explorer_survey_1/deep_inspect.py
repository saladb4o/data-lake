import json
import os
import pandas as pd
from collections import defaultdict

def deep_inspect():
    out = {}
    
    # 1. financial_models.json
    fm_path = os.path.join('data', 'financial_models.json')
    with open(fm_path, 'r', encoding='utf-8') as f:
        fm_data = json.load(f)
        
    out['fm_total_items'] = len(fm_data)
    if isinstance(fm_data, list) and len(fm_data) > 0:
        first_item = fm_data[0]
        out['fm_item_keys'] = list(first_item.keys()) if isinstance(first_item, dict) else str(type(first_item))
        out['fm_first_5_items'] = fm_data[:5]
        
        # Check what fields / types exist across all items
        symbols = set()
        model_types = set()
        statement_types = set()
        item_keys_freq = defaultdict(int)
        for item in fm_data:
            if isinstance(item, dict):
                for k in item.keys():
                    item_keys_freq[k] += 1
                if 'symbol' in item:
                    symbols.add(item['symbol'])
                if 'ticker' in item:
                    symbols.add(item['ticker'])
                if 'type' in item:
                    model_types.add(item['type'])
                if 'report_type' in item:
                    statement_types.add(item['report_type'])
                if 'statement' in item:
                    statement_types.add(item['statement'])
                if 'model_name' in item:
                    model_types.add(item['model_name'])
                    
        out['fm_unique_symbols_count'] = len(symbols)
        out['fm_sample_symbols'] = list(symbols)[:30]
        out['fm_keys_frequency'] = dict(item_keys_freq)
        out['fm_model_types'] = list(model_types)
        out['fm_statement_types'] = list(statement_types)
        
        # Check specific symbols like VNM, FPT, HPG, VCB, SSI, MWG, VIC
        sample_targets = ['VNM', 'FPT', 'HPG', 'VCB', 'SSI', 'MWG', 'VIC']
        symbol_records = {s: [] for s in sample_targets}
        for item in fm_data:
            s = item.get('symbol') or item.get('ticker')
            if s in symbol_records:
                symbol_records[s].append(item)
                
        out['sample_target_counts'] = {s: len(recs) for s, recs in symbol_records.items()}
        for s in ['VNM', 'HPG', 'VCB']:
            if symbol_records[s]:
                out[f'{s}_sample_record_keys'] = list(symbol_records[s][0].keys())
                out[f'{s}_sample_record_snippet'] = symbol_records[s][:3]
                
    # 2. historical_prices.json
    hp_path = os.path.join('data', 'historical_prices.json')
    with open(hp_path, 'r', encoding='utf-8') as f:
        hp_data = json.load(f)
    out['hp_keys'] = list(hp_data.keys())
    if 'symbols' in hp_data:
        sym_dict = hp_data['symbols']
        out['hp_symbols_count'] = len(sym_dict)
        out['hp_first_10_symbols'] = list(sym_dict.keys())[:10]
        # Check VN30 in hp
        vn30_symbols = [
            "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
            "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
            "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
        ]
        vn30_in_hp = [s for s in vn30_symbols if s in sym_dict]
        out['hp_vn30_found_count'] = len(vn30_in_hp)
        out['hp_vn30_missing'] = [s for s in vn30_symbols if s not in sym_dict]
        
        # Inspect VNM price history
        if 'VNM' in sym_dict:
            vnm_p = sym_dict['VNM']
            out['hp_VNM_type'] = type(vnm_p).__name__
            if isinstance(vnm_p, list):
                out['hp_VNM_len'] = len(vnm_p)
                out['hp_VNM_first_row'] = vnm_p[0] if vnm_p else None
                out['hp_VNM_last_row'] = vnm_p[-1] if vnm_p else None
            elif isinstance(vnm_p, dict):
                out['hp_VNM_keys'] = list(vnm_p.keys())
                
    # 3. Save deep inspect
    with open('.agents/teamwork_preview_explorer_survey_1/deep_inspect.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Deep inspection written successfully.")

if __name__ == '__main__':
    deep_inspect()
