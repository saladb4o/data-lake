import json
import os

def inspect_financials():
    # 1. Inspect historical_prices.json quarterly structure
    with open('data/historical_prices.json', 'r', encoding='utf-8') as f:
        hp = json.load(f)
        
    vnm_data = hp['symbols'].get('VNM', {})
    print("VNM keys in historical_prices:", list(vnm_data.keys()))
    quarters = vnm_data.get('quarters', {})
    print(f"VNM quarters count: {len(quarters)}")
    if quarters:
        sample_q = list(quarters.keys())[-1]
        print(f"Sample quarter ({sample_q}) keys:", list(quarters[sample_q].keys()))
        print(f"Sample quarter ({sample_q}) data:", json.dumps(quarters[sample_q], indent=2, ensure_ascii=False))

    # 2. Inspect screener_snapshot.json
    with open('data/screener_snapshot.json', 'r', encoding='utf-8') as f:
        ss = json.load(f)
    print("\nScreener snapshot keys:", list(ss.keys()))
    stocks = ss.get('stocks', {})
    print(f"Screener snapshot stocks count: {len(stocks)}")
    if 'VNM' in stocks:
        print("VNM screener snapshot keys:", list(stocks['VNM'].keys()))
        print("VNM screener snapshot data:", json.dumps(stocks['VNM'], indent=2, ensure_ascii=False))
        
    # 3. Inspect precomputed_valuations.json
    print("\nChecking precomputed_valuations.json...")
    with open('data/precomputed_valuations.json', 'r', encoding='utf-8') as f:
        pv = json.load(f)
    print(f"Precomputed valuations keys count: {len(pv) if isinstance(pv, dict) else len(pv)}")
    if isinstance(pv, dict):
        sample_k = list(pv.keys())[:5]
        print("Sample keys in precomputed_valuations:", sample_k)
        if 'VNM' in pv:
            print("VNM precomputed valuation keys:", list(pv['VNM'].keys()) if isinstance(pv['VNM'], dict) else type(pv['VNM']))
            print("VNM valuation snippet:", json.dumps({k: v for k, v in pv['VNM'].items() if k != 'scenario_matrix'}, indent=2, ensure_ascii=False)[:1000])

if __name__ == '__main__':
    inspect_financials()
