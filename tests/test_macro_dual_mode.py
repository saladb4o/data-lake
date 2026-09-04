import os
import sys
import unittest
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

client = TestClient(app)

class TestMacroDualMode(unittest.TestCase):

    def test_01_macro_board_summary(self):
        resp = client.get('/api/market/macro-board')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'success')
        items = data.get('data', [])
        self.assertGreaterEqual(len(items), 9)

        symbols = [item['symbol'] for item in items]
        self.assertIn('USDVND', symbols)
        self.assertIn('VN10Y', symbols)
        self.assertIn('SBV_OMO', symbols)
        self.assertIn('CPI_VN', symbols)
        self.assertIn('GDP_VN', symbols)
        self.assertIn('PMI_VN', symbols)
        self.assertIn('FDI_VN', symbols)
        self.assertIn('DXY', symbols)
        self.assertIn('BRENT', symbols)

        first = items[0]
        for key in ['symbol', 'name', 'category', 'current_val', 'change_pct', 'status_badge', 'target_desc', 'is_macro']:
            self.assertIn(key, first)

        # Verify /api/trading-board?group=Macro returns 9 macro items without fallback
        resp_tb = client.get('/api/trading-board?group=Macro')
        self.assertEqual(resp_tb.status_code, 200)
        data_tb = resp_tb.json()
        self.assertEqual(data_tb.get('status'), 'success')
        self.assertEqual(len(data_tb.get('data', [])), 9)
        self.assertTrue(data_tb.get('data', [])[0].get('is_macro', False))

    def test_02_macro_detail_usdvnd(self):
        resp = client.get('/api/market/macro-detail?indicator=USDVND')
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertEqual(json_data.get('status'), 'success')
        data = json_data.get('data', {})

        self.assertIn('indicator_info', data)
        self.assertIn('historical_series', data)
        self.assertIn('impact_matrix', data)
        self.assertIn('breakdown', data)
        self.assertIn('policy_news', data)
        self.assertIn('economic_calendar', data)

        impact = data['impact_matrix']
        self.assertIn('beneficiaries', impact)
        self.assertIn('adversely_impacted', impact)
        self.assertGreater(len(impact['beneficiaries']), 0)

    def test_03_macro_detail_cpi_and_gdp(self):
        resp_cpi = client.get('/api/market/macro-detail?indicator=CPI_VN')
        self.assertEqual(resp_cpi.status_code, 200)
        cpi_data = resp_cpi.json().get('data', {})
        self.assertEqual(cpi_data['indicator_info']['symbol'], 'CPI_VN')
        self.assertGreater(len(cpi_data['breakdown']['items']), 3)

        resp_gdp = client.get('/api/market/macro-detail?indicator=GDP_VN')
        self.assertEqual(resp_gdp.status_code, 200)
        gdp_data = resp_gdp.json().get('data', {})
        self.assertEqual(gdp_data['indicator_info']['symbol'], 'GDP_VN')
        self.assertGreater(len(gdp_data['historical_series']), 0)

    def test_04_macro_documents_library(self):
        resp_all = client.get('/api/market/macro-documents')
        self.assertEqual(resp_all.status_code, 200)
        data_all = resp_all.json().get('data', {})
        self.assertGreaterEqual(data_all.get('total', 0), 6)
        docs = data_all.get('documents', [])
        self.assertGreater(len(docs), 0)

        doc1 = docs[0]
        for key in ['title', 'publisher', 'publish_date', 'category', 'language', 'url', 'summary']:
            self.assertIn(key, doc1)

        resp_gso = client.get('/api/market/macro-documents?category=GSO')
        self.assertEqual(resp_gso.status_code, 200)
        gso_docs = resp_gso.json().get('data', {}).get('documents', [])
        self.assertGreater(len(gso_docs), 0)

        resp_kw = client.get('/api/market/macro-documents?keyword=World')
        self.assertEqual(resp_kw.status_code, 200)
        wb_docs = resp_kw.json().get('data', {}).get('documents', [])
        self.assertGreater(len(wb_docs), 0)

    def test_05_macro_global_search_aliases(self):
        test_queries = [
            ("usd", "USDVND"),
            ("cpi", "CPI_VN"),
            ("gdp", "GDP_VN"),
            ("pmi", "PMI_VN"),
            ("lãi suất", "VN10Y"),
            ("lai suat", "VN10Y"),
            ("dầu", "BRENT"),
            ("dau", "BRENT"),
            ("fdi", "FDI_VN"),
            ("dxy", "DXY"),
            ("tín phiếu", "SBV_OMO"),
            ("tỷ giá", "USDVND"),
            ("trái phiếu", "VN10Y")
        ]
        for query, expected_sym in test_queries:
            resp = client.get(f'/api/search?q={query}')
            self.assertEqual(resp.status_code, 200, f"Failed for search query '{query}'")
            results = resp.json().get('data', [])
            macro_results = [r for r in results if r.get('type') == 'MACRO']
            self.assertGreater(len(macro_results), 0, f"No MACRO results found for query '{query}'")
            matched_syms = [r['symbol'] for r in macro_results]
            self.assertIn(expected_sym, matched_syms, f"Expected {expected_sym} in search results for '{query}', got {matched_syms}")

    def test_06_all_9_indicators_deep_validation(self):
        core_symbols = ['USDVND', 'VN10Y', 'SBV_OMO', 'CPI_VN', 'GDP_VN', 'PMI_VN', 'FDI_VN', 'DXY', 'BRENT']
        for sym in core_symbols:
            resp = client.get(f'/api/market/macro-detail?indicator={sym}')
            self.assertEqual(resp.status_code, 200, f"Detail endpoint failed for {sym}")
            data = resp.json().get('data', {})
            self.assertEqual(data.get('indicator_code'), sym)
            
            # Check 6 pillars
            self.assertIn('indicator_info', data)
            self.assertIn('historical_series', data)
            self.assertIn('impact_matrix', data)
            self.assertIn('breakdown', data)
            self.assertIn('policy_news', data)
            self.assertIn('economic_calendar', data)
            
            # Historical series
            self.assertGreater(len(data['historical_series']), 0)
            
            # Breakdown
            self.assertGreater(len(data['breakdown'].get('items', [])), 0)
            
            # Impact matrix
            impact = data['impact_matrix']
            self.assertIn('beneficiaries', impact)
            self.assertIn('adversely_impacted', impact)
            
            # Verify beneficiaries tickers are uppercase symbols without spaces
            for b in impact['beneficiaries']:
                for s in b.get('symbols', []):
                    self.assertTrue(s.isupper() or s in ['VNINDEX', 'VN30'], f"Invalid ticker format '{s}' in {sym}")

if __name__ == '__main__':
    unittest.main()