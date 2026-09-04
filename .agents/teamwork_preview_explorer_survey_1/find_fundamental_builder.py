import os
import re

def search_fundamental_builder():
    patterns = [
        r'def get_fundamental_data',
        r'def _build_fundamental',
        r'def get_stock_overview',
        r'def get_valuation_payload',
        r'def get_screener_stock',
        r'def _extract_fundamental',
        r'ValuationEngine().get_comprehensive_valuation',
        r'get_comprehensive_valuation'
    ]
    with open('services/stock_service.py', 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        for i, line in enumerate(lines, 1):
            for p in patterns:
                if re.search(p, line):
                    print(f"stock_service.py:{i} -> {line.strip()[:100]}")
                    
    with open('services/fair_value_backtest_service.py', 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        for i, line in enumerate(lines, 1):
            for p in patterns:
                if re.search(p, line):
                    print(f"fair_value_backtest_service.py:{i} -> {line.strip()[:100]}")

if __name__ == '__main__':
    search_fundamental_builder()
