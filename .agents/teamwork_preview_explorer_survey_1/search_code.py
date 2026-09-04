import os
import re

def search_codebase():
    results = []
    services_dir = 'services'
    patterns = [
        r'def get_financial',
        r'def get_fundamental',
        r'def get_balance_sheet',
        r'def get_income_statement',
        r'def get_cash_flow',
        r'def get_company_overview',
        r'def get_stock_data',
        r'class StockService',
        r'class DiskDataLake',
        r'financial_models',
        r'screener_snapshot',
        r'historical_prices',
    ]
    
    for root, dirs, files in os.walk(services_dir):
        for f in files:
            if f.endswith('.py'):
                fpath = os.path.join(root, f)
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fp:
                    for i, line in enumerate(fp, 1):
                        for pat in patterns:
                            if re.search(pat, line, re.IGNORECASE):
                                results.append(f"{fpath}:{i} [{pat}] -> {line.strip()[:120]}")
                                break
                                
    out_file = '.agents/teamwork_preview_explorer_survey_1/code_search_results.txt'
    with open(out_file, 'w', encoding='utf-8') as fp:
        fp.write("\n".join(results))
    print(f"Found {len(results)} matches, written to {out_file}")

if __name__ == '__main__':
    search_codebase()
