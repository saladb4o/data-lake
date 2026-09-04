import json
import os
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def full_data_lake_survey():
    survey_data = {}
    
    # VN30 symbol list
    vn30_symbols = [
        "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
        "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
        "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
    ]
    survey_data['vn30_symbols'] = vn30_symbols

    # 1. financial_models.json
    fm_path = os.path.join('data', 'financial_models.json')
    with open(fm_path, 'r', encoding='utf-8') as f:
        fm_list = json.load(f)
        
    df_fm = pd.DataFrame(fm_list)
    survey_data['financial_models'] = {
        'total_definitions': len(df_fm),
        'columns': list(df_fm.columns),
        'company_forms': df_fm['companyForm'].value_counts().to_dict(),
        'model_type_names': df_fm['modelTypeName'].value_counts().to_dict(),
        'form_and_type_matrix': df_fm.groupby(['companyForm', 'modelTypeName']).size().to_dict(),
        'null_counts': df_fm.isnull().sum().to_dict(),
    }
    
    # Key Statement Line Items for NON_FINANCE
    for cform in ['NON_FINANCE', 'BANK', 'SECURITIES', 'INSURANCE']:
        for mtype in ['INCOME', 'BALANCESHEET', 'CASHFLOW']:
            sub = df_fm[(df_fm['companyForm'] == cform) & (df_fm['modelTypeName'] == mtype)]
            if not sub.empty:
                items = sub[['itemCode', 'itemVnName', 'itemEnName', 'displayLevel', 'displayOrder']].to_dict(orient='records')
                survey_data[f'fm_{cform}_{mtype}'] = items

    # 2. screener_snapshot.json
    ss_path = os.path.join('data', 'screener_snapshot.json')
    with open(ss_path, 'r', encoding='utf-8') as f:
        ss_data = json.load(f)
        
    stocks_dict = ss_data.get('stocks', {})
    stocks_list = list(stocks_dict.values())
    df_stocks = pd.DataFrame(stocks_list)
    
    # Remove nested dicts for null analysis
    flat_cols = [c for c in df_stocks.columns if c not in ['_metadata', 'percentiles']]
    df_flat = df_stocks[flat_cols]
    
    survey_data['screener_snapshot'] = {
        'updated_at': ss_data.get('updated_at'),
        'total_symbols': len(stocks_dict),
        'source': ss_data.get('source'),
        'exchanges': df_stocks['exchange'].value_counts().to_dict() if 'exchange' in df_stocks else {},
        'sectors': df_stocks['sector_code'].value_counts().to_dict() if 'sector_code' in df_stocks else {},
        'size_categories': df_stocks['size_category'].value_counts().to_dict() if 'size_category' in df_stocks else {},
        'columns': list(df_stocks.columns),
        'null_or_none_counts': df_flat.isnull().sum().to_dict(),
        'null_or_none_pct': (df_flat.isnull().sum() / len(df_flat) * 100).round(2).to_dict(),
    }
    
    # Check VN30 in screener_snapshot
    vn30_in_screener = {}
    for s in vn30_symbols:
        if s in stocks_dict:
            st = stocks_dict[s]
            vn30_in_screener[s] = {
                'name': st.get('name'),
                'exchange': st.get('exchange'),
                'sector_code': st.get('sector_code'),
                'price': st.get('price'),
                'pe': st.get('pe'),
                'pb': st.get('pb'),
                'roe': st.get('roe'),
                'roa': st.get('roa'),
                'revenue': st.get('revenue'),
                'net_income': st.get('net_income'),
                'total_assets': st.get('total_assets') or st.get('assets'),
                'total_equity': st.get('total_equity') or st.get('equity'),
                'total_debt': st.get('total_debt') or st.get('debt'),
                'fcf_ttm': st.get('fcf_ttm'),
                'current_ratio': st.get('current_ratio'),
                'quick_ratio': st.get('quick_ratio'),
                'interest_coverage': st.get('interest_coverage'),
                'cfo_to_pat': st.get('cfo_to_pat'),
            }
        else:
            vn30_in_screener[s] = "MISSING"
    survey_data['vn30_screener_details'] = vn30_in_screener

    # 3. historical_prices.json
    hp_path = os.path.join('data', 'historical_prices.json')
    with open(hp_path, 'r', encoding='utf-8') as f:
        hp_data = json.load(f)
        
    hp_symbols = hp_data.get('symbols', {})
    q_counts = []
    earliest_years = []
    latest_years = []
    
    for s, sinfo in hp_symbols.items():
        q_counts.append(sinfo.get('total_quarters', len(sinfo.get('quarters', {}))))
        eq = sinfo.get('earliest_quarter', '')
        lq = sinfo.get('latest_quarter', '')
        if eq: earliest_years.append(eq)
        if lq: latest_years.append(lq)
        
    survey_data['historical_prices'] = {
        'version': hp_data.get('version'),
        'last_updated': hp_data.get('last_updated'),
        'total_symbols': len(hp_symbols),
        'quarter_count_stats': {
            'min': int(np.min(q_counts)) if q_counts else 0,
            'max': int(np.max(q_counts)) if q_counts else 0,
            'mean': float(np.mean(q_counts)) if q_counts else 0,
            'median': float(np.median(q_counts)) if q_counts else 0,
        },
        'earliest_quarter_distribution': pd.Series(earliest_years).value_counts().head(10).to_dict(),
        'latest_quarter_distribution': pd.Series(latest_years).value_counts().head(5).to_dict(),
    }

    # 4. all_symbols.json
    as_path = os.path.join('data', 'all_symbols.json')
    with open(as_path, 'r', encoding='utf-8') as f:
        as_list = json.load(f)
    df_as = pd.DataFrame(as_list)
    survey_data['all_symbols'] = {
        'total_count': len(df_as),
        'columns': list(df_as.columns),
        'exchanges': df_as['exchange'].value_counts().to_dict() if 'exchange' in df_as else {},
        'types': df_as['type'].value_counts().to_dict() if 'type' in df_as else {},
        'sectors': df_as['sector'].value_counts().head(15).to_dict() if 'sector' in df_as else {},
    }

    # Save to JSON
    out_file = os.path.join('.agents', 'teamwork_preview_explorer_survey_1', 'full_survey_data.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        # Convert tuple keys if any
        def convert_keys(obj):
            if isinstance(obj, dict):
                return {str(k): convert_keys(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_keys(i) for i in obj]
            elif isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.float64, np.float32)):
                return float(obj)
            return obj
        json.dump(convert_keys(survey_data), f, indent=2, ensure_ascii=False)
    print(f"Full survey data saved to {out_file}")

if __name__ == '__main__':
    full_data_lake_survey()
