import pytest
from services.stock_service import get_company_financial_statements, fetch_vndirect_raw_statements
from services.unified_data_service import fetch_vndirect_financials

def test_vndirect_raw_statements_depth():
    raw_items = fetch_vndirect_raw_statements('VNM', report_type='QUARTER', target_quarters=40)
    assert len(raw_items) > 1000
    distinct_dates = set(it.get('fiscalDate') for it in raw_items if it.get('fiscalDate'))
    assert len(distinct_dates) >= 40

def test_financial_statements_40_quarters_non_finance():
    for st_type in ['income', 'balance', 'cashflow', 'ratios']:
        res = get_company_financial_statements('VNM', statement_type=st_type, period='quarter', periods_count='40')
        assert res['symbol'] == 'VNM'
        assert res['company_form'] == 'NON_FINANCE'
        assert len(res['periods']) == 40
        assert res['periods'][0] == 'Q2/2026'
        assert res['periods'][-1] == 'Q3/2016'
        assert len(res['rows']) > 10
        first_row = res['rows'][0]
        assert len(first_row['values']) == 40

def test_financial_statements_40_quarters_banking():
    res = get_company_financial_statements('VCB', statement_type='income', period='quarter', periods_count='40')
    assert res['company_form'] == 'BANK'
    assert len(res['periods']) == 40
    assert res['periods'][0] == 'Q2/2026'

def test_financial_statements_40_quarters_securities():
    res = get_company_financial_statements('SSI', statement_type='balance', period='quarter', periods_count='40')
    assert res['company_form'] == 'SECURITIES'
    assert len(res['periods']) == 40
    assert res['periods'][0] == 'Q2/2026'

def test_financial_statements_40_quarters_insurance():
    res = get_company_financial_statements('BVH', statement_type='cashflow', period='quarter', periods_count='40')
    assert res['company_form'] == 'INSURANCE'
    assert len(res['periods']) == 40
    assert res['periods'][0] == 'Q2/2026'

def test_financial_ratios_calculation_and_growth_yoy():
    res = get_company_financial_statements('VNM', statement_type='ratios', period='quarter', periods_count='40')
    assert len(res['periods']) == 40
    rows = res['rows']
    row_titles = [r['item_name'] for r in rows]
    assert any('P/E' in t for t in row_titles)
    assert any('ROE' in t for t in row_titles)
    assert any('Biên Lợi Nhuận Gộp' in t for t in row_titles)
    for r in rows:
        if not r.get('is_header'):
            assert len(r['values']) == 40

def test_periods_slicing_behavior():
    res_4 = get_company_financial_statements('VNM', statement_type='income', period='quarter', periods_count=4)
    assert len(res_4['periods']) == 4
    res_8 = get_company_financial_statements('VNM', statement_type='income', period='quarter', periods_count=8)
    assert len(res_8['periods']) == 8
    res_16 = get_company_financial_statements('VNM', statement_type='income', period='quarter', periods_count=16)
    assert len(res_16['periods']) == 16
    res_all = get_company_financial_statements('VNM', statement_type='income', period='quarter', periods_count='all')
    assert len(res_all['periods']) >= 40

def test_annual_period_support():
    res = get_company_financial_statements('VNM', statement_type='income', period='year', periods_count=10)
    assert len(res['periods']) >= 10
    assert '2025' in res['periods'][0]

def test_unified_data_service_vndirect_witness():
    res = fetch_vndirect_financials('VNM', report_type='QUARTER')
    assert res.get('revenue_ttm') and res['revenue_ttm'] > 1e12
    assert res.get('net_income_ttm') and res['net_income_ttm'] > 1e12
    assert res.get('capex_ttm') is not None
    assert res.get('total_assets_fq') and res['total_assets_fq'] > 1e12
    assert res.get('company_form') == 'NON_FINANCE'
    assert res.get('source') == 'VNDIRECT_FINFO'
