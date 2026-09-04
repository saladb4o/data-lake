import json
import os

with open('data/screener_snapshot.json', 'r', encoding='utf-8') as f:
    snap = json.load(f)

stocks = snap.get('stocks', {})
vn30_sample = ['HPG', 'VHM', 'VNM', 'FPT', 'MWG', 'MSN', 'VIC', 'GAS', 'TCB', 'VCB']

for sym in vn30_sample:
    if sym in stocks:
        st = stocks[sym]
        print(f"=== {sym} ({st.get('name')}) ===")
        print(f"Sector: {st.get('sector_code')}, Price: {st.get('price')}, MCap: {st.get('market_cap')}")
        print(f"PE: {st.get('pe')}, PB: {st.get('pb')}, ROE: {st.get('roe')}, ROA: {st.get('roa')}")
        print(f"Current Ratio: {st.get('current_ratio')}, Quick Ratio: {st.get('quick_ratio')}")
        print(f"Gross Margin: {st.get('gross_margin')}, Op Margin: {st.get('op_margin')}, Net Margin: {st.get('net_margin')}")
        print(f"Rev 1Y Growth: {st.get('rev_1y_growth')}, D/E: {st.get('de_ratio')}")
        print(f"Metadata sources: {st.get('_metadata', {}).get('sources_used')}")
        print()
    else:
        print(f"Symbol {sym} not found in screener_snapshot.json!")
