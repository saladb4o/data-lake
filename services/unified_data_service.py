"""
=============================================================================
UNIFIED MULTI-SOURCE MARKET & FINANCIAL DATA SERVICE
=============================================================================
Combines and normalizes data from 3 premier financial providers:
  1. TradingView API (Fast Global Market Scanner & Historical Candles)
  2. vnstock (Vietcap VCI / TCBS In-Depth Financial Statements & Ratios)
  3. yfinance (Yahoo Finance .VN Fallback Feed)

Guarantees 100% unified schema format across all sources with an intelligent
Accounting Triangles Imputation Engine & Multi-Tier Provenance System.
"""

import os
import sys
import json
import collections
import time
import logging
import random
import datetime
import requests
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Shared percentile-quintile scoring engine (M4): replaces the former
# inline _percentile closure / fixed-threshold quintile block.
from services.quant_scoring import score_universe

# TLS honesty (M5): single source of truth in services/tls_config.py —
# certificate verification is ON by default; VNSTOCK_INSECURE_TLS=1 set
# BEFORE import opts out (and suppresses InsecureRequestWarning there).
from services.tls_config import TLS_VERIFY, configure_urllib_warnings
from services.stock_service import resolve_data_file
from services.rate_limiter import limit
from services.accounting_identities import solve as solve_accounting_identities

configure_urllib_warnings()

# Resolved on each call, not at import. As module constants these froze before
# anything could configure the environment: a Google Drive mount that appeared
# after startup was never seen, and DATA_LOCAL_DIR could not redirect them,
# which let test runs write into the real data/ directory.
def data_dir() -> str:
    return os.path.dirname(resolve_data_file("screener_snapshot.json"))


def screener_snapshot_file() -> str:
    return resolve_data_file("screener_snapshot.json")


def historical_prices_file() -> str:
    return resolve_data_file("historical_prices.json")

# =============================================================================
# 1. TRADINGVIEW BATCH SCANNER & FINANCIAL EXTRACTOR (TIER 1)
# =============================================================================

logger = logging.getLogger(__name__)

TRADINGVIEW_SCANNER_URL = "https://scanner.tradingview.com/vietnam/scan"

# Shared HTTP session: connection pooling + consistent browser-like headers
# across all provider calls (mirrors OpenBB's reusable provider sessions).
_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
})

# Retry policy modeled on OpenBB's provider layer: bounded attempts with
# exponential backoff + jitter for transient failures only.
FETCH_MAX_ATTEMPTS = 3
FETCH_BACKOFF_BASE_SECONDS = 0.75
TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _sleep_backoff(attempt: int) -> None:
    """Exponential backoff with full jitter for the given 1-based attempt number."""
    delay = FETCH_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, FETCH_BACKOFF_BASE_SECONDS)
    time.sleep(delay)


def _request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float = 10.0,
    max_attempts: int = FETCH_MAX_ATTEMPTS,
    **kwargs: Any
) -> Optional[requests.Response]:
    """
    Perform an HTTP request with bounded retries for transient failures
    (timeouts, connection errors, and HTTP 408/425/429/5xx).

    Returns the final Response on success (<400), or None if all attempts were
    exhausted or a non-retryable HTTP error status was returned. Failures are
    logged as warnings; this function never raises.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            with limit("http"):
                resp = _HTTP_SESSION.request(method, url, timeout=timeout, verify=TLS_VERIFY, **kwargs)
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                logger.warning("Request to %s failed after %d attempt(s): %s", url, max_attempts, exc)
                return None
            logger.warning("Transient network error hitting %s (attempt %d/%d): %s", url, attempt, max_attempts, exc)
            _sleep_backoff(attempt)
            continue
        if resp.status_code < 400:
            return resp
        if resp.status_code in TRANSIENT_HTTP_STATUSES and attempt < max_attempts:
            logger.warning(
                "Transient HTTP %d from %s (attempt %d/%d); retrying with backoff",
                resp.status_code, url, attempt, max_attempts
            )
            _sleep_backoff(attempt)
            continue
        logger.warning("Request to %s gave up after %d attempt(s): HTTP %d", url, attempt, resp.status_code)
        return None
    return None

TRADINGVIEW_COLUMNS = [
    "name", "description", "logoid", "exchange", "close", "change", "change_abs",
    "volume", "Value.Traded", "market_cap_basic",
    
    # Valuation Multiples
    "price_earnings_ttm", "price_book_fq", "price_sales_current", "price_free_cash_flow_ttm",
    "enterprise_value_to_ebit_ttm", "enterprise_value_to_revenue_ttm",
    
    # Profitability & Returns
    "return_on_equity_fq", "return_on_equity_fy", "return_on_assets_fq",
    "gross_margin_fq", "gross_margin_ttm", "operating_margin_fq", "operating_margin_ttm", "net_margin_fq", "net_margin_ttm",
    
    # Growth YoY & CAGR
    "total_revenue_growth_yoy_fq", "total_revenue_growth_yoy_fy",
    "net_income_growth_yoy_fq", "net_income_growth_yoy_fy",
    "total_revenue_growth_3y_cagr", "total_revenue_growth_5y_cagr",
    "total_revenue_yoy_growth_fq", "total_revenue_yoy_growth_fy",
    "net_income_yoy_growth_fq", "net_income_yoy_growth_fy",
    "total_revenue_yoy_growth_ttm", "net_income_yoy_growth_ttm",
    "total_revenue_cagr_3y", "total_revenue_cagr_5y",
    
    # Financial Health & Solvency
    "debt_to_equity_fq", "total_debt_fq", "total_equity_fq", "cash_n_cash_equivalents_fq",
    "current_ratio_fq", "quick_ratio_fq",
    
    # Raw Financial Statements (in VND) - Direct parity with FFV Pro v6 32 Financial Slots
    "total_revenue_fq", "total_revenue_ttm", "total_revenue_fy",
    "cost_of_goods_fq", "cost_of_goods_ttm", "cogs_fq", "cogs_ttm",
    "net_income_fq", "net_income_ttm", "net_income_fy",
    "pretax_income_fq", "pretax_income_ttm",
    "income_tax_fq", "income_tax_ttm",
    "free_cash_flow_fq", "free_cash_flow_ttm",
    "cash_f_operating_activities_fq", "cash_f_operating_activities_ttm",
    "capital_expenditures_fq", "capital_expenditures_ttm", "capex_fq", "capex_ttm",
    "depreciation_and_amortization_fq", "depreciation_and_amortization_ttm",
    "cash_flow_depreciation_n_amortization_fq", "cash_flow_depreciation_n_amortization_ttm",
    "interest_expense_on_debt_fq", "interest_expense_on_debt_ttm",
    "research_and_dev_fq", "research_and_dev_ttm",
    "preferred_dividends_fq", "preferred_dividends_ttm",
    "dps_common_stock_prim_issue_fq", "dps_common_stock_prim_issue_ttm",
    "minority_interest_fq", "minority_interest_ttm",
    "earnings_per_share_basic_ttm", "earnings_per_share_diluted_ttm",
    "dividend_yield_recent", "dividends_yield_current",
    "total_assets_fq", "total_liabilities_fq",
    "total_current_assets_fq", "total_current_liabilities_fq",
    "cash_n_short_term_invest_fq", "total_inventory_fq",
    "accounts_receivables_net_fq", "accounts_payable_fq",
    "retained_earnings_fq", "ppe_total_gross_fq", "accum_deprec_total_fq",
    "goodwill_fq", "intangibles_net_fq",
    "diluted_shares_outstanding_fq", "total_shares_outstanding_fq",
    "ebit_ttm", "ebit_fq", "ebitda_ttm", "ebitda_fq",
    
    # Forward Estimates
    "earnings_estimate_fq", "sales_estimates_fq"
]

#: Columns fetched in a second pass, never mixed into the request every
#: symbol depends on.
#:
#: Checked against TradingView's published financial-identifier catalogue,
#: which turned up two distinct faults in the list above:
#:
#:  * OPERATING_MARGIN, INTEREST_EXPENSE_ON_DEBT, CAPITAL_EXPENDITURES,
#:    RESEARCH_AND_DEV and PREFERRED_DIVIDENDS are published at FH/FQ/FY
#:    only. The "_ttm" forms requested above exist for no company at all.
#:  * "depreciation_and_amortization" is not an identifier. The
#:    income-statement line is DEP_AMORT_EXP_INCOME_S; the cash-flow line is
#:    CASH_FLOW_DEPRECATION_N_AMORTIZATION - the vendor's own spelling of
#:    "deprecation", which the correctly-spelled copy above therefore misses.
#:
#: And OPER_INCOME, operating income at TTM - the same quantity EBIT names -
#: was never requested, while EBIT stood as the largest blocking driver in
#: the universe and the only one the valuation engine cannot derive.
#:
#: A second pass rather than an extension of the first: an identifier this
#: service has never sent before could be rejected, and the batch every
#: symbol depends on must not be what discovers that.
#: Measured, not guessed: the first supplementary pass requested twenty-one
#: identifiers and the log counted how many companies answered each. Six came
#: back null for all 1522 - dep_amort_exp_income_s_ttm and _fq,
#: cash_flow_deprecation_n_amortization_fq, total_oper_expense_ttm,
#: interest_expense_on_debt_fy and cost_of_goods_ttm. A column that answers
#: for nobody is a name the scanner does not serve, not a line no company
#: reports, so translating a Pine fin_id into a scanner column by lowercasing
#: it and appending a period suffix is right for some identifiers and wrong
#: for others. They are dropped rather than left in to be counted again.
#:
#: The consequence worth naming: TradingView serves no interest expense at
#: all - not at TTM, where the catalogue says the line does not exist, and
#: not at FY, where the name returns nothing. Rung 2 of the EBIT ladder has
#: no TradingView route, whatever the pretax line does.
TRADINGVIEW_SUPPLEMENTARY_COLUMNS = [
    "oper_income_ttm", "oper_income_fq", "oper_income_fy",
    "ebitda_margin_ttm", "gross_profit_ttm",
    "operating_margin_fy",
    "capital_expenditures_fy",
    "return_on_invested_capital_fq", "book_tangible_per_share_fq",
]


DEFAULT_SECTOR_MEDIANS = {
    "VNFIN": {"pe": 10.5, "pb": 1.45, "ps": 3.2, "roe": 19.5, "roa": 2.2, "de_ratio": 7.5, "net_de_ratio": 5.2, "gross_margin": 45.0, "op_margin": 35.0, "net_margin": 28.0, "cur_ratio": 1.1},
    "VNREAL": {"pe": 16.5, "pb": 1.70, "ps": 2.5, "roe": 12.0, "roa": 4.5, "de_ratio": 1.25, "net_de_ratio": 0.85, "gross_margin": 32.0, "op_margin": 20.0, "net_margin": 14.0, "cur_ratio": 1.6},
    "VNIT": {"pe": 22.0, "pb": 4.20, "ps": 2.2, "roe": 24.0, "roa": 12.5, "de_ratio": 0.45, "net_de_ratio": 0.15, "gross_margin": 35.0, "op_margin": 18.0, "net_margin": 15.0, "cur_ratio": 1.9},
    "VNMAT": {"pe": 13.5, "pb": 1.65, "ps": 0.95, "roe": 15.5, "roa": 7.5, "de_ratio": 0.65, "net_de_ratio": 0.35, "gross_margin": 18.0, "op_margin": 10.5, "net_margin": 8.0, "cur_ratio": 1.5},
    "VNIND": {"pe": 13.2, "pb": 1.40, "ps": 0.85, "roe": 13.5, "roa": 6.2, "de_ratio": 0.75, "net_de_ratio": 0.45, "gross_margin": 16.5, "op_margin": 9.5, "net_margin": 7.2, "cur_ratio": 1.45},
    "VNCONS": {"pe": 17.5, "pb": 2.60, "ps": 1.50, "roe": 18.0, "roa": 9.5, "de_ratio": 0.45, "net_de_ratio": 0.15, "gross_margin": 28.0, "op_margin": 14.0, "net_margin": 11.0, "cur_ratio": 1.7},
    "VNCOND": {"pe": 18.5, "pb": 2.80, "ps": 0.90, "roe": 17.0, "roa": 8.0, "de_ratio": 0.80, "net_de_ratio": 0.45, "gross_margin": 22.0, "op_margin": 7.5, "net_margin": 5.5, "cur_ratio": 1.4},
    "VNENE": {"pe": 14.5, "pb": 1.60, "ps": 0.80, "roe": 14.0, "roa": 6.8, "de_ratio": 0.55, "net_de_ratio": 0.20, "gross_margin": 15.0, "op_margin": 8.5, "net_margin": 6.5, "cur_ratio": 1.6},
    "VNUTI": {"pe": 12.5, "pb": 1.50, "ps": 1.20, "roe": 15.5, "roa": 7.5, "de_ratio": 0.85, "net_de_ratio": 0.50, "gross_margin": 25.0, "op_margin": 16.0, "net_margin": 12.5, "cur_ratio": 1.3},
    "VNHEAL": {"pe": 17.0, "pb": 2.50, "ps": 1.60, "roe": 18.5, "roa": 11.0, "de_ratio": 0.35, "net_de_ratio": 0.05, "gross_margin": 36.0, "op_margin": 18.5, "net_margin": 15.0, "cur_ratio": 2.1}
}

def fetch_tradingview_batch_by_tickers(
    tickers_list: List[str],
    chunk_size: int = 150,
    columns: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Tier 1 source: fundamental & valuation snapshot via the TradingView scanner,
    fetched in concurrent chunks to stay sub-second without timing out.

    Failure semantics (never raises): a chunk whose request fails after retries
    or whose payload fails shape validation is skipped with a logged warning;
    its symbols are simply absent from the result so callers can fall through
    to Tier 2/3 sources.
    """
    results = {}
    if not tickers_list:
        return results

    request_columns = list(columns) if columns else TRADINGVIEW_COLUMNS
    chunks = [tickers_list[i:i + chunk_size] for i in range(0, len(tickers_list), chunk_size)]

    def _fetch_chunk(chunk_tickers):
        payload = {
            "filter": [],
            "symbols": {
                "query": {"types": []},
                "tickers": list(chunk_tickers)
            },
            "columns": request_columns
        }
        chunk_res = {}
        resp = _request_with_retry("POST", TRADINGVIEW_SCANNER_URL, json=payload, timeout=12)
        if resp is None:
            logger.warning(
                "TradingView scanner fetch failed for chunk of %d tickers after %d attempt(s)",
                len(chunk_tickers), FETCH_MAX_ATTEMPTS
            )
            return chunk_res
        try:
            data = resp.json()
        except ValueError:
            logger.warning("TradingView returned malformed JSON for chunk of %d tickers", len(chunk_tickers))
            return chunk_res
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            logger.warning(
                "TradingView payload has unexpected shape (missing 'data' list) for chunk of %d tickers",
                len(chunk_tickers)
            )
            return chunk_res
        for item in rows:
            if not isinstance(item, dict):
                continue
            ticker_full = item.get("s", "")
            d_values = item.get("d", [])
            if not ticker_full or not d_values:
                continue
            ex, sym = ticker_full.split(":", 1) if ":" in ticker_full else ("", ticker_full)
            if len(d_values) != len(request_columns):
                logger.warning(
                    "TradingView column/value arity mismatch for %s (%d values vs %d columns); skipping",
                    ticker_full, len(d_values), len(request_columns),
                )
                continue
            # Protocol: "d" is positionally aligned with the requested "columns".
            r_dict = dict(zip(request_columns, d_values))
            r_dict["symbol"] = sym.upper().strip()
            r_dict["exchange"] = ex.upper().strip()
            chunk_res[sym.upper().strip()] = r_dict
        return chunk_res

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_fetch_chunk, ch) for ch in chunks]
        for fut in as_completed(futures):
            res = fut.result()
            results.update(res)

    return results

# =============================================================================
# 1.5. VNDIRECT FINFO DEEP FINANCIAL STATEMENTS (TIER 2 WITNESS)
# =============================================================================

def fetch_vndirect_financials(symbol: str, report_type: str = "QUARTER", size: int = 4000) -> Dict[str, Any]:
    """
    Tier 2 Reported Witness: Fetches deep historical statements from VNDIRECT Finfo API with L1/L2 Disk Lake caching.
    Maps 2,500 item codes across Banking, Securities, Insurance, and Non-Finance entities.
    Returns normalized metrics in VND (TTM Revenue, TTM Net Income, Total Assets, Total Equity, etc.).
    """
    symbol = symbol.upper().strip()
    cache_key = f"vndirect_finfo_v6_{symbol}_{report_type}"
    
    # 1. Check L1 Memory Cache
    try:
        from services.stock_service import cache, disk_lake, fetch_vndirect_raw_statements
        cached = cache.get(cache_key)
        if cached:
            return cached
    except Exception:
        cache = None
        disk_lake = None
        fetch_vndirect_raw_statements = None

    raw_items = []
    if fetch_vndirect_raw_statements is not None:
        try:
            raw_items = fetch_vndirect_raw_statements(symbol, report_type=report_type, target_quarters=16)
        except Exception as e:
            logger.debug(f"fetch_vndirect_raw_statements call failed: {e}")

    if not raw_items:
        url = f"https://api-finfo.vndirect.com.vn/v4/financial_statements?q=code:{symbol}~reportType:{report_type}&size={size}&sort=fiscalDate:desc"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*'
        }
        resp = _request_with_retry("GET", url, headers=headers, timeout=10)
        if resp is None:
            return {}
        try:
            data = resp.json()
            raw_items = data.get("data", []) if isinstance(data, dict) else []
        except Exception:
            return {}
    
    if not raw_items:
        return {}
        
    # Build fiscal date index & itemCode lookup
    distinct_dates = sorted(list(set(it.get('fiscalDate') for it in raw_items if it.get('fiscalDate'))), reverse=True)
    if not distinct_dates:
        return {}
        
    val_lookup = {}
    # The vendor names its own line items in every row it sends. Reading the
    # name from the payload rather than from data/financial_models.json
    # matters: nothing in this repository writes that file and data/*.json is
    # gitignored, so the catalogue the item-code census was going to consult
    # may simply not exist wherever the sync runs - and a census that prints
    # 30 codes with no names against them answers nothing.
    name_lookup: Dict[int, str] = {}
    for it in raw_items:
        fdate = it.get('fiscalDate')
        c = int(it.get('itemCode', 0))
        if c not in val_lookup:
            val_lookup[c] = {}
        val_lookup[c][fdate] = it.get('numericValue')
        if c not in name_lookup:
            label = (it.get('itemName') or it.get('itemVnName')
                     or it.get('itemEnName') or "")
            if isinstance(label, str) and label.strip():
                name_lookup[c] = label.strip()

    # Detect entity form
    latest_d = distinct_dates[0]
    ttm_dates = distinct_dates[:4] if len(distinct_dates) >= 4 else distinct_dates
    
    def _sum_ttm(code_list):
        for c in code_list:
            if c in val_lookup:
                vals = [val_lookup[c].get(d) for d in ttm_dates if val_lookup[c].get(d) is not None]
                if vals:
                    # If quarter, multiply by 4/len(vals) if fewer than 4 quarters
                    s = sum(vals)
                    return s * (4.0 / len(vals)) if report_type == "QUARTER" else vals[0]
        return None

    def _latest(code_list):
        for c in code_list:
            if c in val_lookup and val_lookup[c].get(latest_d) is not None:
                return val_lookup[c].get(latest_d)
        return None

    # Extraction across standard & financial sector item codes
    rev_ttm = _sum_ttm([21001, 421900, 21000, 21010]) # Non-finance, Bank, Sec, Ins
    ni_ttm = _sum_ttm([23000, 23800, 23001])
    ebit_ttm = _sum_ttm([21020, 22000])
    da_ttm = _sum_ttm([31110, 31010]) # Depreciation and Amortization from Cash Flow
    capex_ttm = _sum_ttm([32100, 32110, 32010]) # Purchase of Fixed Assets / CapEx (32100 is primary VAS line)
    cfo_ttm = _sum_ttm([31000, 31100]) # Net Cash Flows from Operating Activities
    
    # Granular Working Capital & Industry Items
    delta_ar = _sum_ttm([31130]) # Delta Receivables
    delta_inv = _sum_ttm([31140]) # Delta Inventory
    delta_ap = _sum_ttm([31150]) # Delta Payables
    delta_wc = (delta_ar or 0.0) + (delta_inv or 0.0) - (delta_ap or 0.0)
    
    assets = _latest([12700, 10000, 11000])
    equity = _latest([14000, 14100])
    debt = _latest([13000, 13100])
    curr_assets = _latest([11000])
    curr_liab = _latest([13100])
    cash = _latest([11100])
    gross_ppe = _latest([12110, 12100])
    accum_deprec = _latest([12120])
    # The land bank is inventory, and the numbering is not the vendor's own.
    #
    # A census of all 112 developers that return a coded balance sheet
    # settled both halves of this. 11420 appears in NONE of them and 12510
    # appears in ALL of them with a value of zero in every single case, so
    # the previous pair could never publish anything - which is exactly
    # what the record showed: landbank_fq reached the snapshot for 0 of
    # 112, and the `> 0` guard downstream was right to refuse a zero.
    #
    # The reason is legible once the scheme is: itemCode is 1 + the
    # three-digit VAS balance-sheet code + 0. Confirmed on five independent
    # lines by their median share of total assets -
    #
    #   12700 = 1.0000  VAS 270  TONG CONG TAI SAN
    #   11000 = 0.6349  VAS 100  TAI SAN NGAN HAN
    #   12000 = 0.3929  VAS 200  TAI SAN DAI HAN
    #   11300 = 0.1341  VAS 130  Phai thu ngan han
    #   11100 = 0.0195  VAS 110  Tien
    #
    # - which makes 11420 VAS 142, a line the standard form does not have,
    # and 12510 VAS 251, long-term work in progress. A Vietnamese developer
    # does not hold its pipeline there. It holds it in INVENTORY:
    #
    #   11400 = 0.2045  VAS 140  HANG TON KHO      106 of 112 non-zero
    #   11410 = 0.2046  VAS 141  Hang ton kho      106 of 112 non-zero
    #
    # 11400 first because it is net of the obsolescence provision (VAS 149)
    # and 11410 is gross; the net figure is the conservative one and the
    # two differ by well under a percent of assets at the median.
    #
    # What this is not: inventory is the property pipeline at BOOK COST,
    # including finished units, not a market appraisal of raw land. That is
    # the right direction to be wrong in for model_18, whose rnav adds
    # landbank_pipeline_val to cash and subtracts debt - a cost basis
    # understates the RNAV rather than flattering it.
    landbank = _latest([11400, 11410])
    unearned_revenue = _latest([13130]) # Short-term Customer Prepayments
    bank_loans = _latest([112000]) # Bank Gross Loans
    bank_loan_loss = _latest([112900]) # Bank Loan Loss Reserves
    
    # Detect entity form
    raw_mts = set(float(it.get('modelType')) for it in raw_items if it.get('modelType'))
    if raw_mts & {89.0, 90.0, 91.0, 201.0, 202.0, 203.0}:
        detected_form = "SECURITIES"
    elif raw_mts & {101.0, 102.0, 103.0, 111.0, 112.0, 113.0}:
        detected_form = "BANK"
    elif raw_mts & {411.0, 412.0, 413.0, 414.0, 420.0}:
        detected_form = "INSURANCE"
    elif raw_mts & {1.0, 2.0, 3.0, 11.0, 12.0, 13.0}:
        detected_form = "NON_FINANCE"
    else:
        try:
            from services.stock_service import _FINANCIAL_MODELS_BY_CODE
            code_set = set(int(it.get('itemCode', 0)) for it in raw_items if it.get('itemCode'))
            form_scores = {"NON_FINANCE": 0, "BANK": 0, "SECURITIES": 0, "INSURANCE": 0}
            for c in code_set:
                for meta in _FINANCIAL_MODELS_BY_CODE.get(c, []):
                    cf = meta.get('companyForm')
                    if cf in form_scores:
                        form_scores[cf] += 1
            detected_form = max(form_scores, key=form_scores.get) if any(form_scores.values()) else "NON_FINANCE"
        except Exception:
            detected_form = "NON_FINANCE"

    res = {
        "revenue_ttm": rev_ttm,
        "net_income_ttm": ni_ttm,
        "ebit_ttm": ebit_ttm,
        "da_ttm": da_ttm,
        "capex_ttm": abs(capex_ttm) if capex_ttm is not None else None,
        "cfo_ttm": cfo_ttm,
        "delta_working_capital": delta_wc if (delta_ar or delta_inv or delta_ap) else None,
        "total_assets_fq": assets,
        "total_equity_fq": equity,
        "total_debt_fq": debt,
        "total_current_assets_fq": curr_assets,
        "total_current_liabilities_fq": curr_liab,
        "cash_fq": cash,
        "gross_ppe_fq": gross_ppe,
        "accum_deprec_fq": accum_deprec,
        "landbank_fq": landbank,
        "unearned_revenue_fq": unearned_revenue,
        "bank_loans_fq": bank_loans,
        "bank_loan_loss_fq": bank_loan_loss,
        "latest_fiscal_date": latest_d,
        "company_form": detected_form,
        # The itemCodes this payload actually carries. Kept so the sync can
        # census them without a second round of requests: the EBIT extractor
        # reads codes [21020, 22000] and came back empty for all 619
        # backfilled symbols that have no operating line, which says the
        # codes are wrong rather than the statements absent. Naming the
        # codes that ARE present, against the itemName catalogue, is what
        # settles which line to read. Not published downstream.
        "available_item_codes": sorted(val_lookup.keys()),
        # {itemCode: its TTM value} for the income statement only. The census
        # cannot name a code the vendor never names, and it named none of
        # them - so the codes have to be identified by what their numbers do
        # relative to lines already known (revenue at 21001, net income at
        # 23000), not by a label. Diagnostic only; never read as a number by
        # anything that publishes.
        "income_statement_ttm_by_code": {
            c: _sum_ttm([c]) for c in val_lookup if 20000 <= c < 30000
        },
        # {itemCode: its value at the latest fiscal date} for the balance
        # sheet. The income statement got this treatment because its codes
        # were wrong; the balance sheet never did, and the land bank
        # (11420/12510) and the loan book (112000) are balance-sheet codes.
        # So when those come back empty there is no way to tell a vendor
        # that carries neither line from a pair of codes read wrong - which
        # is exactly the question a run has now failed to answer twice.
        # Diagnostic only; never read as a number by anything that
        # publishes.
        "balance_sheet_fq_by_code": {
            c: val_lookup[c].get(latest_d)
            for c in val_lookup
            # Two numbering schemes live side by side: the non-financial
            # balance sheet runs 10000-19999 (assets 12700, cash 11100),
            # and the bank one runs 100000-199999 (gross loans 112000).
            # A range that covered only the first would have declared the
            # loan book absent for every bank by construction.
            if (10000 <= c < 20000 or 100000 <= c < 200000)
            and val_lookup[c].get(latest_d) is not None
        },
        # {itemCode: the vendor's own name for it}, taken from the rows just
        # parsed. Diagnostic only; never read as a number.
        "item_code_names": name_lookup,
        "source": "VNDIRECT_FINFO"
    }
    
    if cache is not None:
        cache.set(cache_key, res, ttl_seconds=86400) # Cache for 24h
        
    return res

# =============================================================================
# 2. VNSTOCK & TCBS FINANCIAL RATIOS (TIER 2)
# =============================================================================

#: TCBS route candidates, tried in order. The route this module used for
#: the life of the project - /tcanalysis/v1/finance/{sym}/overview - returns
#: 404 for every ticker, large caps included. It is not a real route, so
#: fetch_vnstock_financials() has never returned anything: the failure was
#: swallowed into an empty dict and the "Tier 2 source" was dead the whole
#: time, silently.
#:
#: The replacement is not asserted either, because this environment cannot
#: reach TCBS to check. Instead the candidates are probed once against a
#: reference ticker and the one that answers is used; the probe prints what
#: each returned, so a wrong list is visible in the log rather than
#: swallowed the way the last one was.
_TCBS_ROUTES = (
    "https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{sym}/overview",
    "https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{sym}/financialratio?yearly=0&isAll=true",
    "https://apipubaws.tcbs.com.vn/tcanalysis/v1/finance/{sym}/financialratio?yearly=0&isAll=true",
    "https://apipubaws.tcbs.com.vn/tcanalysis/v1/finance/{sym}/overview",
)

#: Field aliases across the TCBS shapes. Each route returns a different
#: document; rather than hard-coding one, take the first alias present.
_TCBS_FIELD_ALIASES = {
    "market_cap": ("marketCap", "market_cap", "marketcap"),
    "pe": ("pe", "priceToEarning", "price_to_earning"),
    "pb": ("pb", "priceToBook", "price_to_book"),
    "eps": ("eps", "earningPerShare", "earning_per_share"),
    "roe": ("roe", "returnOnEquity"),
    "roa": ("roa", "returnOnAsset"),
    "shares_outstanding": ("outstandingShare", "issueShare", "shareOutstanding",
                           "outstanding_share", "listedShare"),
}

#: A VN listed company has between roughly 100,000 and 20,000,000,000
#: shares. Expressed in millions that is 0.1..20,000. The ranges do not
#: overlap, so - as with the market cap - the unit is readable from the
#: value and the gap between them is discarded rather than guessed.
_SHARES_RAW_FLOOR = 1e5
_SHARES_MILLIONS_CEILING = 5e4


def _tcbs_first_record(payload: Any) -> Dict[str, Any]:
    """TCBS routes return either a document or a series; take the latest."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and row:
                return row
    return {}


def _shares_to_count(value: Any) -> Optional[float]:
    """Normalises a vendor share count to whole shares, or None if unclear."""
    shares = _safe_float(value)
    if shares is None or shares <= 0:
        return None
    if shares >= _SHARES_RAW_FLOOR:
        return shares
    if shares < _SHARES_MILLIONS_CEILING:
        return shares * 1_000_000.0
    logger.debug("share count %r sits between the unit ranges; discarding", value)
    return None


def fetch_vnstock_financials(symbol: str, route: Optional[str] = None) -> Dict[str, Any]:
    """
    Tier 2 source: ratios and a share count via the TCBS public feed.

    `route` is a URL template containing {sym}; pass the one that
    tcbs_probe_routes() found to answer. Without it the first candidate is
    tried, which keeps existing callers working.

    Failure semantics (never raises): returns an empty dict on transport
    failure after retries, non-200 status, or malformed/empty payload, so
    callers fall through to the Tier 3 Yahoo fallback.
    """
    symbol = symbol.upper().strip()
    url = (route or _TCBS_ROUTES[0]).format(sym=symbol)
    resp = _request_with_retry("GET", url, timeout=10)
    if resp is None:
        logger.warning("vnstock/TCBS financials unavailable for %s", symbol)
        return {}
    try:
        payload = resp.json()
    except ValueError:
        logger.warning("vnstock/TCBS returned malformed JSON for %s", symbol)
        return {}
    record = _tcbs_first_record(payload)
    if not record:
        logger.warning("vnstock/TCBS returned empty or invalid payload for %s", symbol)
        return {}
    out: Dict[str, Any] = {}
    for field, aliases in _TCBS_FIELD_ALIASES.items():
        for alias in aliases:
            if record.get(alias) is not None:
                out[field] = record[alias]
                break
        else:
            out[field] = None
    out["shares_outstanding"] = _shares_to_count(out.get("shares_outstanding"))
    return out


def tcbs_probe_routes(reference_symbol: str = "FPT") -> Optional[str]:
    """Finds the TCBS route that answers, printing what each one returned.

    The previous route 404'd for every ticker and nobody knew, because the
    only record of it was a warning inside a swallowed exception path. This
    prints one line per candidate so a dead list cannot hide again.
    """
    for template in _TCBS_ROUTES:
        url = template.format(sym=reference_symbol)
        try:
            resp = _HTTP_SESSION.get(url, timeout=10, verify=TLS_VERIFY)
        except Exception as exc:
            print(f"     {template.split('/tcanalysis/')[-1]:<52} {type(exc).__name__}")
            continue
        label = template.split("/tcanalysis/")[-1]
        if resp.status_code >= 400:
            print(f"     {label:<52} HTTP {resp.status_code}")
            continue
        try:
            record = _tcbs_first_record(resp.json())
        except ValueError:
            print(f"     {label:<52} HTTP 200, not JSON")
            continue
        if not record:
            print(f"     {label:<52} HTTP 200, empty body")
            continue
        print(f"     {label:<52} HTTP 200, fields: {sorted(record)[:12]}")
        return template
    return None

#: Vietcap's insight service, the route the vnstock package itself uses for
#: company details. Note the host: iq.vietcap.com.vn, not the
#: trading.vietcap.com.vn we already query for the listing. The listing
#: payload carries names and reference prices and no share count - that was
#: measured, not assumed - but this route carries numberOfSharesMktCap,
#: which is the one field 565 symbols are missing.
_VIETCAP_DETAILS_URL = (
    "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/details?ticker={sym}"
)

#: vnstock renames numberOfSharesMktCap to issue_share; its own column
#: dictionary labels it "Outstanding Shares (mil)", so the value may arrive
#: in millions. _shares_to_count() reads the unit from the magnitude rather
#: than trusting either label.
_VIETCAP_SHARE_ALIASES = (
    "numberOfSharesMktCap", "number_of_shares_mkt_cap",
    "issueShare", "issue_share",
    "outstandingShare", "outstanding_share",
    "listedShare", "listed_share",
)
_VIETCAP_MCAP_ALIASES = ("marketCap", "market_cap", "marketCapitalization")


def _vietcap_record(payload: Any) -> Dict[str, Any]:
    """Unwraps the service envelope, which nests the document under "data"."""
    if isinstance(payload, dict):
        inner = payload.get("data")
        if isinstance(inner, dict) and inner:
            return inner
        if isinstance(inner, list):
            for row in inner:
                if isinstance(row, dict) and row:
                    return row
        return payload
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and row:
                return row
    return {}


def _first_alias(record: Dict[str, Any], aliases: Tuple[str, ...]) -> Any:
    for alias in aliases:
        if record.get(alias) is not None:
            return record[alias]
    return None


def fetch_vietcap_company_details(symbol: str) -> Dict[str, Any]:
    """
    Share count and market cap for one symbol from Vietcap's insight service.

    Returns the same shape fetch_vnstock_financials() does, so both feed the
    single vnstock_data argument of normalize_stock_data() without the caller
    caring which vendor answered.

    Failure semantics (never raises): an empty dict on transport failure after
    retries, non-200, malformed JSON, or a payload with no share count in it.
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry("GET", _VIETCAP_DETAILS_URL.format(sym=symbol), timeout=10)
    if resp is None:
        logger.debug("Vietcap IQ unavailable for %s", symbol)
        return {}
    try:
        record = _vietcap_record(resp.json())
    except ValueError:
        logger.debug("Vietcap IQ returned malformed JSON for %s", symbol)
        return {}
    if not record:
        return {}
    shares = _shares_to_count(_first_alias(record, _VIETCAP_SHARE_ALIASES))
    mcap = _first_alias(record, _VIETCAP_MCAP_ALIASES)
    if shares is None and mcap is None:
        return {}
    return {"shares_outstanding": shares, "market_cap": mcap}


#: Vietcap's financial-statistics route. Confirmed against the vnstock
#: package installed alongside this service (vnstock/explorer/vci): its
#: RATIO column map lists "ebit", "ebitda", "ebitMargin" and "roic" as
#: fields of this endpoint. Vietcap already answered for 564 of 564 symbols
#: when asked for share counts, which is the same population that has no
#: operating line.
_VIETCAP_STATS_URL = (
    "https://iq.vietcap.com.vn/api/iq-insight-service"
    "/v1/company/{sym}/statistics-financial"
)

#: Deliberately a margin and not the EBIT field beside it.
#:
#: The payload carries "ebit" outright, but nothing in it states a unit, and
#: this vendor is already known to publish share counts in millions under a
#: name that says nothing of the sort. Reading an absolute EBIT of unknown
#: scale risks an operating line wrong by a factor of a billion, which is
#: exactly what the tier system exists to prevent and would not be visible
#: as an error - it would just be a valuation.
#:
#: A margin is a ratio. Multiplied by revenue we already hold, in units we
#: already know, it yields EBIT in our units with no unit assumption at all,
#: through the rung the ladder already has and already tests.
#:
#: "No unit assumption" was too strong: a ratio still has a scale, and this
#: vendor states it as a fraction while the consumer expects a percent. The
#: scaling is done in the fetch, not here - see fetch_vietcap_ebit_margin.
_VIETCAP_EBIT_MARGIN_ALIASES = (
    "ebitMargin", "ebit_margin",
)


def _vietcap_latest_period(payload: Any) -> Dict[str, Any]:
    """The most recent period in a statistics-financial body.

    vnstock reads this route into a frame keyed "years"/"quarters", so the
    document is a series rather than a single record. The shape is not
    pinned by any contract available here, so every plausible arrangement is
    accepted and anything else yields {} - never a guess.
    """
    def _newest(series: List[Any]) -> Dict[str, Any]:
        rows = [r for r in series if isinstance(r, dict) and r]
        if not rows:
            return {}
        # Sort, never take the first. This function was written to take
        # rows[0] under the assumption that the vendor serves newest-first,
        # and the census disproved it outright: across 714 companies the
        # median `year` on the first row is 2018. Every margin this route
        # has ever returned was a seven-year-old period wearing the name of
        # the latest one - the worst kind of wrong, because it is a real
        # number from a real filing and nothing downstream can tell.
        #
        # Rows with no period at all sort last rather than being dropped:
        # a single-record body still has to be returnable.
        def key(row: Dict[str, Any]) -> Tuple[float, float]:
            year = _safe_float(row.get("yearReport") or row.get("year"))
            period = _safe_float(
                row.get("lengthReport") or row.get("quarter")
                or row.get("lengthReportYear")
            )
            return (year if year is not None else float("-inf"),
                    period if period is not None else float("-inf"))

        return max(rows, key=key)

    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        for key_name in ("quarters", "years"):
            series = data.get(key_name)
            if isinstance(series, list) and series:
                newest = _newest(series)
                if newest:
                    return newest
        return data if all(not isinstance(v, (list, dict)) for v in data.values()) else {}
    if isinstance(data, list):
        return _newest(data)
    return {}


def fetch_vietcap_ebit_margin(symbol: str) -> Optional[float]:
    """EBIT margin, as a percentage, for one symbol. None when unavailable.

    Never raises: transport failure, non-200, malformed JSON, an unexpected
    body shape or an absent margin all return None, and the caller simply
    keeps the operating line it already had (which is to say, none).
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry("GET", _VIETCAP_STATS_URL.format(sym=symbol), timeout=10)
    if resp is None:
        return None
    try:
        record = _vietcap_latest_period(resp.json())
    except ValueError:
        return None
    # Scaled inside the conversion, not after it. _safe_float rounds to two
    # decimals, which is harmless for a figure in dong and destroys a
    # fraction: 0.084 becomes 0.08 before anything can multiply it, and a
    # 0.4% margin becomes zero. Its `scale` parameter exists for exactly
    # this and multiplies before rounding, so 0.084 -> 8.4.
    margin = _safe_float(
        _first_alias(record, _VIETCAP_EBIT_MARGIN_ALIASES), scale=100.0)
    if margin is None:
        return None
    # This route states the margin as a FRACTION, and said so all along.
    #
    # The band check below was written to catch a fraction wearing the name
    # of a percent, and could not: 0.04 sits comfortably inside -100..100,
    # so the guard passed every fraction it existed to stop. The consumer
    # then computes revenue * (margin / 100), which for a real 4% margin
    # yields an EBIT a hundred times too small - tier 2, through the gate,
    # and indistinguishable downstream from a small company. Missing data
    # is refused; this was answered, wrongly.
    #
    # Two independent witnesses fix the unit, neither of them a guess:
    #
    #   - The census measured ebit and revenue separately on this same
    #     record and ebit/revenue = 0.0405, while the record's own
    #     ebitMargin reads 0.04. A ratio of two dong figures is a fraction
    #     by construction, so the field beside it carrying the same number
    #     is a fraction too.
    #   - fetch_vietcap_ebit_margin_graphql, feeding the SAME column from
    #     the SAME vendor, computes ebit/revenue*100 and returns a percent.
    #     One consumer was being fed two units under one name.
    #
    # So it is scaled at the boundary, and the band is applied after
    # scaling where it can finally reject something.
    if not (-100.0 <= margin <= 100.0):
        return None
    return margin


#: An operating line in raw dong, as this route serves it. The census
#: measured both the coverage and the unit: ebit answers for 660 of the 720
#: companies with no operating line at a median of 8.12e9, ebitda for 659 at
#: 1.55e10, and dividing each by the revenue already held in dong gives
#: 0.0405 and 0.0766 - the first of which equals the ebitMargin the same
#: record reports independently. Two witnesses to the same unit.
_VIETCAP_EBIT_ALIASES = ("ebit",)
_VIETCAP_EBITDA_ALIASES = ("ebitda",)

#: A VN listed company's operating line, in dong. Below a million the figure
#: is in some other unit or is noise; above 1e15 it is larger than the whole
#: exchange. Negative is ordinary and must survive - a loss-making company
#: has an EBIT, and discarding it would silently turn a real loss into no
#: data at all.
_OPERATING_LINE_FLOOR = 1e6
_OPERATING_LINE_CEILING = 1e15


def _plausible_operating_line(value: Any) -> Optional[float]:
    """The value if it can be an operating line in dong, else None."""
    num = _safe_float(value)
    if num is None or num == 0.0:
        return None
    return num if _OPERATING_LINE_FLOOR <= abs(num) <= _OPERATING_LINE_CEILING else None


#: Return on invested capital, as this route states it.
#:
#: roic is the single largest blocking driver at 185 symbols and the most
#: common reason in the refused list - APT, BT6, DFF and DAG are refused on
#: roic alone, BOT, DSG, DTC and FTM on roic and fcf. Every one of them is
#: tier-3 on its core data. They are not short of a vendor; they were short
#: of a question nobody asked.
#:
#: Because the ladder read only TradingView's return_on_invested_capital_fq,
#: and this route reports roic for 629 of 720 measured companies, named, at
#: a median of 0.06 - measured, named, and connected to nothing. That is the
#: fourteenth instance of this shape in the audit.
#:
#: Stated as a FRACTION, like every ratio on this record: the census read
#: roe 0.08, roa 0.05, ebitMargin 0.04 alongside it, and ebitMargin was
#: proved a fraction against ebit/revenue on the same record. The consumer
#: wants a percentage in -100..100, so it is scaled through _safe_float's
#: own `scale`, which multiplies before rounding - rounding first would turn
#: 0.084 into 0.08 and a 0.4% return into nothing at all.
_VIETCAP_ROIC_ALIASES = ("roic",)


def fetch_vietcap_roic(symbol: str) -> Optional[float]:
    """ROIC as a percentage for one symbol; None when unavailable.

    Never raises; every failure shape yields None.
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry(
        "GET", _VIETCAP_STATS_URL.format(sym=symbol), timeout=10)
    if resp is None:
        return None
    try:
        record = _vietcap_latest_period(resp.json())
    except ValueError:
        return None
    roic = _safe_float(_first_alias(record, _VIETCAP_ROIC_ALIASES), scale=100.0)
    if roic is None or roic == 0.0:
        return None
    # The same band the consumer applies. A return outside it is not a
    # return on capital that this vendor measured; it is discarded rather
    # than reinterpreted.
    return roic if -100.0 <= roic <= 100.0 else None


def fetch_vietcap_operating_lines(symbol: str) -> Dict[str, float]:
    """EBIT and EBITDA in dong for one symbol; {} when unavailable.

    Preferred over the margin route wherever it answers, for a reason that
    is about provenance rather than convenience. A margin has to be
    multiplied by revenue, so the result can be no better than the revenue -
    it inherits that tier, and for a company whose revenue is a sector
    stand-in it is refused outright. A reported EBIT is the vendor stating
    the line itself, which is tier 3 on its own and needs nothing else.

    Never raises; every failure shape yields {}.
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry("GET", _VIETCAP_STATS_URL.format(sym=symbol), timeout=10)
    if resp is None:
        return {}
    try:
        record = _vietcap_latest_period(resp.json())
    except ValueError:
        return {}
    out: Dict[str, float] = {}
    ebit = _plausible_operating_line(_first_alias(record, _VIETCAP_EBIT_ALIASES))
    if ebit is not None:
        out["ebit"] = ebit
    ebitda = _plausible_operating_line(_first_alias(record, _VIETCAP_EBITDA_ALIASES))
    if ebitda is not None:
        out["ebitda"] = ebitda
    # roic comes off the record already in hand. The same request that
    # answers for the operating line answers for the return on capital, so
    # taking it here costs nothing and spares these symbols a second call.
    roic = _safe_float(_first_alias(record, _VIETCAP_ROIC_ALIASES), scale=100.0)
    if roic is not None and roic != 0.0 and -100.0 <= roic <= 100.0:
        out["roic"] = roic
    return out


#: Vietcap's financial-statement route, the same one the census reads.
#: statistics-financial states ratios and a handful of summary lines; this
#: one states the statement itself, row by row, under the vendor's own VAS
#: codes.
_VIETCAP_STATEMENT_URL = (
    "https://iq.vietcap.com.vn/api/iq-insight-service"
    "/v1/company/{sym}/financial-statement"
)

#: The two cash-flow rows, named by the vendor rather than inferred.
#:
#: The census printed Vietcap's own label beside every code, and these two
#: read:
#:
#:   cfa18  "Luu chuyen tien te rong tu cac hoat dong san xuat kinh doanh"
#:          / "Net cash inflows/(outflows) from operating activities"
#:   cfa19  "Tien chi de mua sam, xay dung TSCD va cac tai san dai han khac"
#:          / "Purchase of fixed assets and other long term assets"
#:
#: which is operating cash flow and capital expenditure, stated. An earlier
#: pass had noticed that cfa18 is non-zero for all 198 companies, positive,
#: at +7.6% of revenue, and cfa19 negative for 165 at -3.2% - the shape of
#: CFO and capex. That shape was deliberately not acted on, because shape is
#: what the census exists to stop anyone acting on. These names are.
_VIETCAP_CFO_ALIASES = ("cfa18",)
_VIETCAP_CAPEX_ALIASES = ("cfa19",)


def fetch_vietcap_cash_flow(symbol: str) -> Dict[str, float]:
    """Operating cash flow and capex in dong; {} when unavailable.

    Same plausibility bound and same latest-period rule as the operating
    lines, for the same reasons: a figure below a million dong is in some
    other unit, and the vendor does not serve newest-first.

    Capex keeps whatever sign the vendor gave it. Every consumer downstream
    takes abs() of it, so the sign carries no meaning here and inverting it
    would only invent one.

    Never raises; every failure shape yields {}.
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry(
        "GET", _VIETCAP_STATEMENT_URL.format(sym=symbol),
        params={"section": "CASH_FLOW"}, timeout=10,
    )
    if resp is None:
        return {}
    try:
        record = _vietcap_latest_period(resp.json())
    except ValueError:
        return {}
    out: Dict[str, float] = {}
    cfo = _plausible_operating_line(_first_alias(record, _VIETCAP_CFO_ALIASES))
    if cfo is not None:
        out["cfo"] = cfo
    capex = _plausible_operating_line(_first_alias(record, _VIETCAP_CAPEX_ALIASES))
    if capex is not None:
        out["capex"] = capex
    return out


#: The income-statement rows, named by the vendor rather than inferred.
#:
#: The census printed Vietcap's own label beside every code, and this
#: statement turned out to carry, for 196-199 of the 200 companies that
#: answered, every core line the gate was refusing them for:
#:
#:   isa3   "Doanh thu thuan"          / "Net sales"
#:   isa20  "Lai/(lo) thuan sau thue"  / "Net profit/(loss) after tax"
#:   isa23  "Lai co ban tren co phieu" / "EPS basic (VND)"
#:   isa11  "Lai/(lo) tu HDKD"         / "Operating profit/(loss)"
#:   isa8   "Chi phi lai vay"          / "Interest expenses"
#:
#: The census reported isa3 at 2.224x the revenue already held for these
#: companies, which read at first like a misparsed revenue. It is not. The
#: census divides by the revenue in the snapshot for symbols whose ebit tier
#: is below 2 - which is very largely the tier-1 group, whose revenue is a
#: sector median standing in for a number nobody had. A stand-in smaller
#: than the truth is what a median looks like from the point of view of the
#: companies above it. So isa3 is not contradicting a revenue we hold; it is
#: supplying one we never had.
#:
#: That distinction decides how much this is worth. Revenue is a CORE
#: driver, so unlike the cash-flow pair this does move the tier table: a
#: company whose revenue goes from sector stand-in to vendor reported clears
#: eps, sps, net_margin, roic and ebit in one step.
_VIETCAP_IS_REVENUE_ALIASES = ("isa3",)
_VIETCAP_IS_NET_INCOME_ALIASES = ("isa20",)
_VIETCAP_IS_OPERATING_PROFIT_ALIASES = ("isa11",)
_VIETCAP_IS_INTEREST_ALIASES = ("isa8",)

#: EPS is in dong per share, not in dong, so the operating-line bound does
#: not apply to it. A VN listed share earning less than one dong or more
#: than a million is not an earnings figure.
_VIETCAP_IS_EPS_ALIASES = ("isa23",)
_EPS_FLOOR = 1.0
_EPS_CEILING = 1e6


def _plausible_eps(value: Any) -> Optional[float]:
    """The value if it can be an EPS in dong per share, else None.

    Zero is dropped rather than kept: the census found this column padded
    with zeros for the companies that do not report it, so a zero here says
    "not stated", not "earned nothing". A genuine loss arrives negative and
    survives.
    """
    num = _safe_float(value)
    if num is None or num == 0.0:
        return None
    return num if _EPS_FLOOR <= abs(num) <= _EPS_CEILING else None


def fetch_vietcap_income_statement(symbol: str) -> Dict[str, float]:
    """Core income-statement lines in dong for one symbol; {} when absent.

    EBIT is reconstructed rather than read, because Vietnamese accounting
    standards do not publish one. isa11 is operating profit after financial
    expense, so adding back the interest expense isa8 - which the statement
    states separately, and states negative - gives earnings before interest.
    It is only offered when both halves are present; half a reconstruction
    is not a smaller version of it.

    Never raises; every failure shape yields {}.
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry(
        "GET", _VIETCAP_STATEMENT_URL.format(sym=symbol),
        params={"section": "INCOME_STATEMENT"}, timeout=10,
    )
    if resp is None:
        return {}
    try:
        record = _vietcap_latest_period(resp.json())
    except ValueError:
        return {}

    out: Dict[str, float] = {}
    for key, aliases in (
        ("revenue", _VIETCAP_IS_REVENUE_ALIASES),
        ("net_income", _VIETCAP_IS_NET_INCOME_ALIASES),
        ("operating_profit", _VIETCAP_IS_OPERATING_PROFIT_ALIASES),
    ):
        value = _plausible_operating_line(_first_alias(record, aliases))
        if value is not None:
            out[key] = value

    eps = _plausible_eps(_first_alias(record, _VIETCAP_IS_EPS_ALIASES))
    if eps is not None:
        out["eps"] = eps

    interest = _plausible_operating_line(
        _first_alias(record, _VIETCAP_IS_INTEREST_ALIASES))
    if "operating_profit" in out and interest is not None:
        out["ebit"] = out["operating_profit"] + abs(interest)
    return out


#: The balance-sheet rows, named by the vendor rather than inferred.
#:
#: The census printed Vietcap's own label beside all 122 codes, and only one
#: of them is wired here:
#:
#:   bsa2  "Tien va tuong duong tien" / "Cash and cash equivalents"
#:
#: which it reports for 71 of the 73 companies the gate is still refusing.
#: cash is a CORE driver and the second-largest blocking driver at 150
#: symbols, so this is a tier-table change rather than a cosmetic one.
#:
#: DEBT IS DELIBERATELY NOT WIRED, AND THE REASON CHANGED ON READING.
#:
#: This route was left unread for two runs on the grounds that debt could not
#: be defined without the vendor's names for the borrowing lines. The names
#: arrived - bsa56 "Vay ngan han" / short-term borrowings, bsa71 "Vay dai han"
#: / long-term borrowings - and they do not help: bsa56 carries a figure for
#: 25 of 73 companies and bsa71 for 17. Summing them would produce a real debt
#: for about a third of this group and a zero for the rest, and a zero here is
#: not "no borrowings", it is "not stated". That distinction is invisible
#: downstream: zero is a valid number, it passes the provenance gate at the
#: vendor's own tier, and it lowers enterprise value for every company it
#: touches. Missing data is refused; a fabricated zero is answered, wrongly.
#:
#: The near-complete line beside them is bsa54 "NO PHAI TRA" / Liabilities, at
#: 72 of 73 - but that is TOTAL liabilities, trade payables, taxes and wages
#: included, and the models spend debt on enterprise value as
#: market_cap + debt - cash. Substituting it would overstate EV for every
#: company that buys on credit, which is most of them. It belongs to the
#: resolver's separate total_liabilities field, not to this one.
#:
#: So the obstacle was never the missing name. It was missing data wearing a
#: missing name, and reading the names is what told the two apart.
_VIETCAP_BS_CASH_ALIASES = ("bsa2",)


def fetch_vietcap_balance_sheet(symbol: str) -> Dict[str, float]:
    """Cash and cash equivalents in dong; {} when unavailable.

    Same plausibility bound and same latest-period rule as the other two
    statements, for the same reasons: a figure below a million dong is in
    some other unit, and this vendor does not serve newest-first.

    Only cash is returned. See the note above for why debt is not.

    Never raises; every failure shape yields {}.
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry(
        "GET", _VIETCAP_STATEMENT_URL.format(sym=symbol),
        params={"section": "BALANCE_SHEET"}, timeout=10,
    )
    if resp is None:
        return {}
    try:
        record = _vietcap_latest_period(resp.json())
    except ValueError:
        return {}

    out: Dict[str, float] = {}
    cash = _plausible_operating_line(
        _first_alias(record, _VIETCAP_BS_CASH_ALIASES))
    if cash is not None:
        out["cash"] = cash
    return out


#: Vietcap's GraphQL ratio service. Confirmed twice over: vnstock's own
#: const.py names this host as its _GRAPHQL_URL, and a third-party crawler
#: (github.com/cnhson/DataCrawl) issues exactly this query against it.
_VIETCAP_GRAPHQL_URL = "https://trading.vietcap.com.vn/data-mt/graphql"

_VIETCAP_RATIO_QUERY = """fragment Ratios on CompanyFinancialRatio {
  yearReport
  lengthReport
  revenue
  netProfit
  roe
  roic
  roa
  ev
  issueShare
  eps
  pe
  pb
  ebit
}
query Query($ticker: String!, $period: String!) {
  CompanyFinancialRatio(ticker: $ticker, period: $period) {
    ratio {
      ...Ratios
    }
  }
}"""


def _vietcap_ratio_rows(payload: Any) -> List[Dict[str, Any]]:
    """The ratio rows out of a GraphQL response, newest first.

    Returns [] for any shape that is not the documented one rather than
    reaching into it speculatively.
    """
    if not isinstance(payload, dict):
        return []
    node = ((payload.get("data") or {}).get("CompanyFinancialRatio") or {})
    rows = node.get("ratio") if isinstance(node, dict) else None
    if not isinstance(rows, list):
        return []
    clean = [r for r in rows if isinstance(r, dict) and r]
    clean.sort(
        key=lambda r: (
            _safe_float(r.get("yearReport")) or 0.0,
            _safe_float(r.get("lengthReport")) or 0.0,
        ),
        reverse=True,
    )
    return clean


def fetch_vietcap_ebit_margin_graphql(symbol: str) -> Optional[float]:
    """EBIT margin as a percentage, computed inside one vendor record.

    This route reports EBIT and revenue as absolute figures side by side,
    and that adjacency is the whole point: whatever unit the vendor keeps
    them in, it is the same unit for both, so their ratio carries no unit
    at all. The scale question that makes a bare EBIT unusable simply does
    not arise, and no assumption stands in for the answer.

    A ratio outside [-1, 1] means the two figures are not what they are
    labelled - a company does not earn more operating profit than revenue -
    so it is discarded rather than reinterpreted.

    Never raises. Any failure returns None and the caller keeps the
    operating line it had.
    """
    symbol = symbol.upper().strip()
    resp = _request_with_retry(
        "POST", _VIETCAP_GRAPHQL_URL, timeout=12,
        json={
            "query": _VIETCAP_RATIO_QUERY,
            "variables": {"ticker": symbol, "period": "Q"},
        },
    )
    if resp is None:
        return None
    try:
        rows = _vietcap_ratio_rows(resp.json())
    except ValueError:
        return None
    for row in rows:
        ebit = _safe_float(row.get("ebit"))
        revenue = _safe_float(row.get("revenue"))
        if ebit is None or revenue is None or revenue <= 0:
            continue
        ratio = ebit / revenue
        if not (-1.0 <= ratio <= 1.0):
            continue
        return ratio * 100.0
    return None


def vietcap_graphql_probe(reference_symbol: str = "FPT") -> bool:
    """One request, before spending several hundred."""
    try:
        resp = _HTTP_SESSION.post(
            _VIETCAP_GRAPHQL_URL, timeout=12, verify=TLS_VERIFY,
            json={
                "query": _VIETCAP_RATIO_QUERY,
                "variables": {"ticker": reference_symbol, "period": "Q"},
            },
        )
    except Exception as exc:
        print(f"     vietcap graphql ratio         {type(exc).__name__}: {exc}")
        return False
    if resp.status_code >= 400:
        print(f"     vietcap graphql ratio         HTTP {resp.status_code}")
        return False
    try:
        body = resp.json()
    except ValueError:
        print("     vietcap graphql ratio         HTTP 200, not JSON")
        return False
    if isinstance(body, dict) and body.get("errors"):
        print(f"     vietcap graphql ratio         HTTP 200, GraphQL errors:"
              f" {str(body['errors'])[:160]}")
        return False
    rows = _vietcap_ratio_rows(body)
    print(f"     vietcap graphql ratio         HTTP 200, {len(rows)} ratio rows")
    if not rows:
        return False
    row = rows[0]
    print(f"       newest row fields: {sorted(row)[:16]}")
    ebit, revenue = _safe_float(row.get("ebit")), _safe_float(row.get("revenue"))
    print(f"       ebit={ebit!r} revenue={revenue!r} roic={row.get('roic')!r}")
    if ebit is None or revenue is None or revenue <= 0:
        print("       no usable ebit/revenue pair on the newest row.")
        return False
    print(f"       implied EBIT margin: {ebit / revenue * 100.0:.2f}%")
    return True


def vietcap_stats_probe(reference_symbol: str = "FPT") -> bool:
    """One request, before spending several hundred.

    Four TCBS routes 404'd for the life of the project because the only
    record of it was a warning inside a swallowed except. This prints the
    status, the shape of the body and the field names, so a rename reads as
    a rename and a wrong guess about the envelope reads as a wrong guess.
    """
    url = _VIETCAP_STATS_URL.format(sym=reference_symbol)
    try:
        resp = _HTTP_SESSION.get(url, timeout=10, verify=TLS_VERIFY)
    except Exception as exc:
        print(f"     vietcap statistics-financial  {type(exc).__name__}: {exc}")
        return False
    if resp.status_code >= 400:
        print(f"     vietcap statistics-financial  HTTP {resp.status_code}")
        return False
    try:
        body = resp.json()
    except ValueError:
        print("     vietcap statistics-financial  HTTP 200, not JSON")
        return False
    envelope = body.get("data") if isinstance(body, dict) else body
    shape = (f"dict keys {sorted(envelope)[:8]}" if isinstance(envelope, dict)
             else f"list of {len(envelope)}" if isinstance(envelope, list)
             else type(envelope).__name__)
    record = _vietcap_latest_period(body)
    print(f"     vietcap statistics-financial  HTTP 200, envelope: {shape}")
    if not record:
        print("       no period record found in it; leaving the route unused.")
        return False
    print(f"       latest-period fields: {sorted(record)[:16]}")
    key = next((a for a in _VIETCAP_EBIT_MARGIN_ALIASES if record.get(a) is not None), None)
    if key is None:
        print("       ebit margin: none of the known aliases matched"
              f" (ebit={record.get('ebit')!r}, ebitda={record.get('ebitda')!r},"
              f" roic={record.get('roic')!r})")
        return False
    print(f"       ebit margin: {key} = {record.get(key)!r}")
    return True


def vietcap_probe(reference_symbol: str = "FPT") -> bool:
    """Reports whether the route answers, and with which fields.

    The TCBS list 404'd for every ticker for the life of the project because
    the only trace of the failure was a warning inside a swallowed except.
    This prints the outcome before 558 requests are spent on it, and names
    the top-level keys so a rename shows up as a rename rather than as an
    absence.
    """
    url = _VIETCAP_DETAILS_URL.format(sym=reference_symbol)
    try:
        resp = _HTTP_SESSION.get(url, timeout=10, verify=TLS_VERIFY)
    except Exception as exc:
        print(f"     vietcap iq company/details    {type(exc).__name__}: {exc}")
        return False
    if resp.status_code >= 400:
        print(f"     vietcap iq company/details    HTTP {resp.status_code}")
        return False
    try:
        record = _vietcap_record(resp.json())
    except ValueError:
        print("     vietcap iq company/details    HTTP 200, not JSON")
        return False
    if not record:
        print("     vietcap iq company/details    HTTP 200, empty body")
        return False
    share_key = next((a for a in _VIETCAP_SHARE_ALIASES if record.get(a) is not None), None)
    print(f"     vietcap iq company/details    HTTP 200, fields: {sorted(record)[:14]}")
    if share_key is None:
        print("       share-count field: none of the known aliases matched")
        return False
    print(f"       share-count field: {share_key} = {record.get(share_key)!r}"
          f" -> {_shares_to_count(record.get(share_key))} shares")
    return True


#: Cophieu68 and Vietstock, the two remaining candidates. Unlike every
#: source above they publish HTML pages, not JSON documents, so there is no
#: field name to alias and no envelope to unwrap - the share count sits in
#: markup whose shape cannot be seen from here.
#:
#: Writing a parser against a guessed structure is how the TCBS route came
#: to sit dead in this file for the life of the project. So this is
#: reconnaissance only: one request per candidate, reporting what actually
#: came back. A parser gets written in the round after, against real markup.
_HTML_SHARE_SOURCES = (
    ("cophieu68 summary", "https://www.cophieu68.vn/quote/summary.php?id={sym}"),
    ("cophieu68 profile", "https://www.cophieu68.vn/company/profilesymbol.php?id={sym}"),
    ("vietstock profile", "https://finance.vietstock.vn/{sym}/ho-so-doanh-nghiep.htm"),
    ("vietstock overview", "https://finance.vietstock.vn/{sym}/CTCP.htm"),
)

#: The labels these pages put next to a share count, Vietnamese and English.
#: A page that renders the number only through JavaScript will match none of
#: them, and that is itself the finding: it means the figure is behind an
#: XHR whose URL has to be found before anything can be parsed.
_SHARE_COUNT_LABELS = (
    "cổ phiếu đang lưu hành",
    "khối lượng đang lưu hành",
    "klcp đang lưu hành",
    "cp lưu hành",
    "số lượng cổ phiếu",
    "khối lượng niêm yết",
    "kl niêm yết",
    "outstanding share",
    "shares outstanding",
)


def probe_html_share_sources(reference_symbol: str = "FPT") -> None:
    """Reports what Cophieu68 and Vietstock actually serve, without parsing.

    Prints, per candidate: the HTTP status, the content type, the body size,
    and - when a share-count label appears - the surrounding text, so the
    real markup can be read here rather than imagined. Never raises, never
    returns data, and costs one request per candidate regardless of how many
    symbols are unpinned.
    """
    import re

    print(f"  🔎 Reconnaissance on the HTML sources (reference {reference_symbol}):")
    for label, template in _HTML_SHARE_SOURCES:
        url = template.format(sym=reference_symbol)
        try:
            resp = _HTTP_SESSION.get(url, timeout=15, verify=TLS_VERIFY)
        except Exception as exc:
            print(f"     {label:<20} {type(exc).__name__}: {exc}")
            continue
        ctype = (resp.headers.get("Content-Type") or "?").split(";")[0]
        body = resp.text or ""
        print(f"     {label:<20} HTTP {resp.status_code}  {ctype}  {len(body):,} bytes")
        if resp.status_code >= 400 or not body:
            continue
        lowered = body.lower()
        hit = next((lab for lab in _SHARE_COUNT_LABELS if lab in lowered), None)
        if hit is None:
            # No label in the served HTML. Either the page is rendered
            # client-side or the figure is not on it; both mean a parser
            # would have had nothing to bite on.
            print(f"       no share-count label in the served HTML"
                  f" (checked {len(_SHARE_COUNT_LABELS)} spellings)")
            continue
        at = lowered.index(hit)
        window = body[max(0, at - 120): at + 240]
        window = re.sub(r"<[^>]+>", " ", window)
        window = " ".join(window.split())
        print(f"       matched {hit!r}: ...{window}...")


# =============================================================================
# 3. YFINANCE FALLBACK EXTRACTOR (TIER 3)
# =============================================================================

def fetch_yfinance_financials(symbol: str) -> Dict[str, Any]:
    """
    Tier 3 fallback: last traded price via the Yahoo Finance v8 chart API for
    Vietnamese listings (.VN).

    Uses the shared retrying session; its browser-like headers keep Yahoo's
    cookie/crumb gate satisfied for anonymous chart requests. Failure
    semantics (never raises): returns an empty dict on transport failure after
    retries, non-200 status, malformed JSON, or an empty/invalid chart result.
    """
    symbol = symbol.upper().strip()
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}.VN?interval=1d&range=5d"
    resp = _request_with_retry("GET", url, timeout=10)
    if resp is None:
        logger.warning("yfinance chart unavailable for %s", symbol)
        return {}
    try:
        payload = resp.json()
    except ValueError:
        logger.warning("yfinance returned malformed JSON for %s", symbol)
        return {}
    chart = payload.get("chart") if isinstance(payload, dict) else None
    chart_results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(chart_results, list) or not chart_results:
        logger.warning("yfinance returned empty chart result for %s", symbol)
        return {}
    first = chart_results[0] if isinstance(chart_results[0], dict) else {}
    meta = first.get("meta") if isinstance(first.get("meta"), dict) else {}
    price = meta.get("regularMarketPrice")
    if price is None:
        logger.warning("yfinance meta missing 'regularMarketPrice' for %s", symbol)
        return {}
    return {"price": price}

# =============================================================================
# 4. QUANT IMPUTATION ENGINE (ACCOUNTING TRIANGLES & 4-TIER PROVENANCE)
# =============================================================================

def _safe_float(val: Any, default: Optional[float] = None, scale: float = 1.0) -> Optional[float]:
    if val is None:
        return default
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return round(f * scale, 2)
    except (ValueError, TypeError):
        return default

def reconstruct_financial_triangles(
    symbol: str,
    price: float,
    raw_mcap: float,
    sector_code: str,
    tv_data: Dict[str, Any],
    vn_data: Dict[str, Any],
    yf_data: Dict[str, Any],
    vnd_data: Optional[Dict[str, Any]] = None,
    source0_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Solves Accounting Triangles (Assets-Liab-Equity, Rev-GP-COGS, NI-Pretax-Tax, EBIT-EBITDA-D&A, CFO-CapEx-FCF, Delta_WC).
    Integrates Reported Witnesses from VNDIRECT Finfo (2,500 ItemCodes), TradingView Scanner (32 columns),
    and Tier 0 Ground Truth Official Filings (BCTC & Disclosures PDF Lake).
    Provenance rule: a derived field's tier is min(own rule tier, tiers of ALL upstream inputs).
    Tier 4 = Tier 0 Ground Truth Arbiter (Audited Primary Filing), Tier 3 = Vendor Reported, Tier 2 = Triangulated, Tier 1 = Sector Dynamic, Tier 0 = Fabricated.
    """
    field_provenance = {} # Maps field_name -> tier (4=Tier 0 Ground Truth, 3=Reported, 2=Triangulated, 1=Sector Median, 0=Fabricated)
    vnd = vnd_data or {}
    s0 = source0_data or {}

    def _prop(field: str, own: int, *upstreams: int) -> None:
        # Worst-case provenance: derived value never outranks its weakest input.
        field_provenance[field] = min(own, *upstreams)
    sec_med = DEFAULT_SECTOR_MEDIANS.get(sector_code, DEFAULT_SECTOR_MEDIANS["VNIND"])

    # Effective provenance tier of `price` itself: tier 3 only when a real
    # close/price witness exists; the 10000.0 fallback invented from nothing
    # is tier 0 and must poison every derivation that consumes price.
    price_tier = 3 if (
        _safe_float(tv_data.get("close")) is not None
        or _safe_float(yf_data.get("price")) is not None
    ) else 0

    # -------------------------------------------------------------
    # 0. Witness Ingestion & Firebreak Check
    # -------------------------------------------------------------
    s0_ttm = s0.get("ttm_metrics", {}) or {}
    s0_bs = s0.get("balance_sheet", {})
    s0_items = s0_bs.get("items", {})
    s0_is = s0.get("income_statement", {})
    s0_cf = s0.get("cash_flow", {})

    s0_assets = s0_ttm.get("total_assets") or s0_items.get(270, {}).get("current_val") or _safe_float(s0.get("total_assets"))
    s0_liab = s0_ttm.get("total_liabilities") or s0_items.get(300, {}).get("current_val") or _safe_float(s0.get("total_liabilities"))
    s0_eq = s0_ttm.get("equity") or s0_items.get(400, {}).get("current_val") or _safe_float(s0.get("total_equity"))
    s0_cash = s0_ttm.get("cash_and_equivalents") or s0_items.get(110, {}).get("current_val") or _safe_float(s0.get("cash"))
    s0_debt_st = s0_items.get(320, {}).get("current_val") or 0.0
    s0_debt_lt = s0_items.get(338, {}).get("current_val") or 0.0
    s0_debt = s0_ttm.get("total_debt") or ((s0_debt_st + s0_debt_lt) if (s0_debt_st or s0_debt_lt) else _safe_float(s0.get("total_debt")))
    s0_curr_assets = s0_items.get(100, {}).get("current_val")
    s0_curr_liab = s0_items.get(310, {}).get("current_val")

    s0_rev = s0_ttm.get("revenue_ttm") or s0_is.get("revenue_vnd") or _safe_float(s0.get("revenue"))
    s0_cogs = s0_is.get("cogs_vnd")
    s0_gp = s0_is.get("gross_profit_vnd")
    s0_pbt = s0_is.get("pbt_vnd")
    s0_tax = s0_is.get("tax_expense_vnd")
    s0_npat = s0_ttm.get("net_profit_ttm") or s0_is.get("npat_vnd") or s0_is.get("parent_npat_vnd") or _safe_float(s0.get("net_income"))
    s0_cfo = s0_ttm.get("cfo_ttm") or s0_cf.get("cfo_vnd") or _safe_float(s0.get("cfo"))
    s0_capex = s0_ttm.get("capex_ttm") or s0_cf.get("capex_vnd") or _safe_float(s0.get("capex"))
    s0_fcf = s0_ttm.get("fcf_ttm") or s0_cf.get("free_cash_flow_vnd") or _safe_float(s0.get("fcf"))

    has_real_s0 = bool(s0 and any(v is not None for v in [s0_assets, s0_eq, s0_rev, s0_npat, s0_cfo]))
    has_real_vnd = bool(vnd and any(vnd.get(k) is not None for k in ["revenue_ttm", "net_income_ttm", "total_assets_fq", "total_equity_fq", "cfo_ttm"]))
    has_real_tv = bool(tv_data and any(tv_data.get(k) is not None for k in ["total_revenue_ttm", "net_income_ttm", "total_assets_fq", "close", "price_earnings_ttm"]))
    has_real_vn = bool(vn_data and any(vn_data.get(k) is not None for k in ["pe", "pb", "roe", "eps", "market_cap"]))
    has_any_real_fundamental = has_real_vnd or has_real_tv or has_real_vn or has_real_s0

    # -------------------------------------------------------------
    # 1. Shares Outstanding Witness
    #
    # This ladder decides more than it looks like it does. Because a derived
    # field inherits the worst tier of its inputs, an invented share count
    # drags the market cap to tier 0, and the market cap drags every
    # valuation model down with it - even for a company whose revenue,
    # equity and net income all arrived reported. Measured over the whole
    # universe, 565 of 1,522 symbols were refused with exactly that shape:
    # full VNDIRECT statements at tier 3, and a fabricated share count.
    #
    # Two rungs were missing. TradingView is asked for both share columns
    # (see TV_COLUMNS) but only the diluted one was ever read. And where a
    # vendor reports a total and its per-share twin, the count it used can
    # be recovered by dividing one by the other - price / pe is the vendor's
    # own EPS, price / pb its own book value per share. That is
    # triangulation between two reported witnesses, not a back-solve from
    # price alone, so it is tier 2 and capped by the tier of the price that
    # fed it.
    # -------------------------------------------------------------
    shares_dil = _safe_float(tv_data.get("diluted_shares_outstanding_fq"))
    shares_tot = _safe_float(tv_data.get("total_shares_outstanding_fq"))
    net_inc_raw = _safe_float(tv_data.get("net_income_ttm") or tv_data.get("net_income_fy"))
    eps_raw = _safe_float(tv_data.get("earnings_per_share_basic_ttm") or vn_data.get("eps"))
    equity_raw = _safe_float(tv_data.get("total_equity_fq"))

    def _per_share(multiple: Any) -> Optional[float]:
        """The per-share figure a reported multiple implies at this price."""
        m = _safe_float(multiple)
        if price > 0 and m and m > 0:
            return price / m
        return None

    eps_implied = _per_share(tv_data.get("price_earnings_ttm") or vn_data.get("pe"))
    bvps_implied = _per_share(tv_data.get("price_book_fq") or vn_data.get("pb"))

    #: No listed company has fewer shares than this. A rung that produces
    #: less has divided by a stale or nonsense multiple, and passing it on
    #: would be worse than falling through to the next witness.
    MIN_PLAUSIBLE_SHARES = 100_000.0

    def _ratio(total: Optional[float], per_share: Optional[float]) -> Optional[float]:
        if not total or total <= 0 or not per_share or per_share <= 0:
            return None
        count = total / per_share
        return count if count >= MIN_PLAUSIBLE_SHARES else None

    #: A share count the vendor states outright. TradingView omits it for a
    #: third of the universe; TCBS reports it under outstandingShare, and a
    #: stated figure outranks anything divided out of a multiple.
    shares_vendor = _safe_float(vn_data.get("shares_outstanding"))

    if shares_dil and shares_dil >= MIN_PLAUSIBLE_SHARES:
        shares_out = shares_dil
        field_provenance["shares"] = 3
    elif shares_vendor and shares_vendor >= MIN_PLAUSIBLE_SHARES:
        shares_out = shares_vendor
        field_provenance["shares"] = 3
    elif shares_tot and shares_tot >= MIN_PLAUSIBLE_SHARES:
        shares_out = shares_tot
        field_provenance["shares"] = 3
    elif _ratio(net_inc_raw, eps_raw):
        shares_out = round(_ratio(net_inc_raw, eps_raw))
        field_provenance["shares"] = 2
    elif raw_mcap > 0 and price > 0:
        shares_out = round(raw_mcap / price)
        # Price may be the invented fallback -> poison this derivation too.
        field_provenance["shares"] = min(2, price_tier)
    elif _ratio(net_inc_raw, eps_implied):
        shares_out = round(_ratio(net_inc_raw, eps_implied))
        field_provenance["shares"] = min(2, price_tier)
    elif _ratio(equity_raw, bvps_implied):
        shares_out = round(_ratio(equity_raw, bvps_implied))
        field_provenance["shares"] = min(2, price_tier)
    else:
        shares_out = 50_000_000
        field_provenance["shares"] = 0

    # Market Cap (in Bil VND)
    if raw_mcap > 10_000_000:
        mcap = int(round(raw_mcap / 1_000_000_000.0))
        field_provenance["market_cap"] = 3
    elif price > 0 and shares_out > 0:
        mcap = int(round((price * shares_out) / 1_000_000_000.0))
        # Never derive a tier-2 value from a tier-0 witness: inherit shares provenance
        # (and the effective tier of any price that fed into it).
        field_provenance["market_cap"] = min(2, field_provenance["shares"], price_tier)
    else:
        mcap = int(_safe_float(vn_data.get("market_cap"), 2500.0))
        field_provenance["market_cap"] = 1

    # -------------------------------------------------------------
    # 2. Balance Sheet Triangles (Assets = Liabilities + Equity)
    # -------------------------------------------------------------
    tot_assets = _safe_float(tv_data.get("total_assets_fq"))
    tot_liab = _safe_float(tv_data.get("total_liabilities_fq"))
    tot_eq = _safe_float(tv_data.get("total_equity_fq"))
    tot_debt = _safe_float(tv_data.get("total_debt_fq"))
    cash_equiv = _safe_float(tv_data.get("cash_n_short_term_invest_fq") or tv_data.get("cash_n_cash_equivalents_fq"), default=0.0)
    curr_assets_raw = _safe_float(tv_data.get("total_current_assets_fq"))
    curr_liab_raw = _safe_float(tv_data.get("total_current_liabilities_fq"))
    # retained_earnings_fq is in TV_COLUMNS and was read by no line of code
    # in the repository. It is a reported balance-sheet line and the sole
    # real input Altman Z'' lacked; without it the score rested on an
    # assertion that retained earnings are 20% of book equity for every
    # company listed in Vietnam.
    retained_earnings_raw = _safe_float(tv_data.get("retained_earnings_fq"))
    ppe_gross_raw = _safe_float(tv_data.get("ppe_total_gross_fq"))
    accum_dep_raw = _safe_float(tv_data.get("accum_deprec_total_fq"))
    goodwill_raw = _safe_float(tv_data.get("goodwill_fq"), default=0.0)
    intangibles_raw = _safe_float(tv_data.get("intangibles_net_fq"), default=0.0)

    # --- TIER 0 ARBITER: SOURCE 0 GROUND TRUTH OVERRIDE ---
    if s0_assets is not None:
        tot_assets = s0_assets
        field_provenance["total_assets"] = 4
    elif tot_assets is not None:
        field_provenance["total_assets"] = 3

    if s0_liab is not None:
        tot_liab = s0_liab
        field_provenance["total_liabilities"] = 4

    if s0_eq is not None:
        tot_eq = s0_eq
        field_provenance["total_equity"] = 4

    if s0_debt is not None:
        tot_debt = s0_debt
        field_provenance["total_debt"] = 4

    if s0_cash is not None and s0_cash > 0:
        cash_equiv = s0_cash
        field_provenance["cash"] = 4
    elif cash_equiv > 0:
        field_provenance["cash"] = 3

    if s0_curr_liab is not None:
        curr_liab_raw = s0_curr_liab
        field_provenance["current_liabilities"] = 4
    elif curr_liab_raw is not None:
        # total_current_liabilities_fq has been requested from the vendor and
        # read into curr_liab_raw since the beginning, and the only rung that
        # ever tiered it was the Source-0 override above. Everywhere else the
        # figure was a reported number with no provenance, which under the
        # fail-closed rule is indistinguishable from a number nobody has -
        # so current liabilities could never be published, and every identity
        # standing on them (working capital first among them) had to fall
        # back on a fabricated fraction of the balance sheet.
        field_provenance["current_liabilities"] = 3

    # Calculate Net PPE using accumulated depreciation if reported
    if ppe_gross_raw is not None and accum_dep_raw is not None:
        ppe_net = max(0.0, ppe_gross_raw - abs(accum_dep_raw))
    elif ppe_gross_raw is not None:
        ppe_net = ppe_gross_raw * 0.80
    else:
        ppe_net = None

    # Triangle 1 & 1.5: Equity & Liabilities
    if tot_eq is not None:
        if "total_equity" not in field_provenance:
            field_provenance["total_equity"] = 3
    elif tot_assets is not None and tot_liab is not None:
        tot_eq = tot_assets - tot_liab
        field_provenance["total_equity"] = 2
    elif tot_assets is not None and tot_debt is not None:
        tot_eq = tot_assets - tot_debt
        field_provenance["total_equity"] = 2
    elif has_any_real_fundamental and mcap > 0:
        tot_eq = mcap * 1_000_000_000.0 / max(0.5, sec_med["pb"])
        _prop("total_equity", 1, field_provenance["market_cap"])

    if tot_liab is not None:
        if "total_liabilities" not in field_provenance:
            field_provenance["total_liabilities"] = 3
    elif tot_assets is not None and tot_eq is not None:
        tot_liab = tot_assets - tot_eq
        field_provenance["total_liabilities"] = 2

    if tot_debt is not None:
        if "total_debt" not in field_provenance:
            field_provenance["total_debt"] = 3
    elif tot_liab is not None:
        tot_debt = tot_liab * 0.70
        _prop("total_debt", 2, field_provenance.get("total_liabilities", 3))
    elif tot_eq is not None:
        tot_debt = tot_eq * sec_med["de_ratio"]
        _prop("total_debt", 1, field_provenance["total_equity"])

    # Triangle 1.6: Current Assets Reconstitution
    if curr_assets_raw is not None:
        curr_assets = curr_assets_raw
        field_provenance["current_assets"] = 3
    elif tot_assets is not None and ppe_net is not None:
        inferred_non_current = ppe_net + goodwill_raw + intangibles_raw
        if 0 < inferred_non_current < tot_assets:
            curr_assets = tot_assets - inferred_non_current
            field_provenance["current_assets"] = 2
        else:
            curr_assets = tot_assets * 0.40
            field_provenance["current_assets"] = 1
    elif tot_assets is not None:
        curr_assets = tot_assets * 0.40
        field_provenance["current_assets"] = 1
    else:
        curr_assets = None

    # Retained earnings. Reported or nothing: a company's accumulated
    # profits cannot be inferred from the rest of the balance sheet without
    # assuming the very thing Altman Z'' is asked to measure, so there is no
    # second rung here on purpose. Where the vendor is silent the line is
    # not published, working_capital and retained_earnings resolve imputed,
    # and the score is labelled unreliable - which is the honest answer.
    if retained_earnings_raw is not None:
        field_provenance["retained_earnings"] = 3

    # D/E and Net D/E
    raw_de = _safe_float(tv_data.get("debt_to_equity_fq"))
    if raw_de is not None:
        de_ratio = raw_de
        field_provenance["de_ratio"] = 3
    elif tot_eq and tot_eq > 0 and tot_debt is not None:
        de_ratio = round(tot_debt / tot_eq, 2)
        _prop("de_ratio", 2, field_provenance["total_debt"], field_provenance["total_equity"])
    else:
        de_ratio = sec_med["de_ratio"]
        field_provenance["de_ratio"] = 1

    if tot_eq and tot_eq > 0 and tot_debt is not None:
        net_de_ratio = round(max(0.0, (tot_debt - cash_equiv) / tot_eq), 2)
        _prop("net_de_ratio", 2, field_provenance["total_debt"], field_provenance["total_equity"])
    else:
        net_de_ratio = round(max(0.0, de_ratio - 0.22), 2)
        field_provenance["net_de_ratio"] = 1

    cur_ratio_raw = _safe_float(tv_data.get("current_ratio_fq"))
    if cur_ratio_raw is not None:
        cur_ratio = cur_ratio_raw
        field_provenance["current_ratio"] = 3
    elif curr_assets and curr_liab_raw and curr_liab_raw > 0:
        cur_ratio = round(curr_assets / curr_liab_raw, 2)
        field_provenance["current_ratio"] = 2
    else:
        cur_ratio = sec_med["cur_ratio"]
        field_provenance["current_ratio"] = 1

    # -------------------------------------------------------------
    # 3. Income Statement Triangles (Rev, COGS, GP, EBIT, Pretax, Tax, NI)
    # -------------------------------------------------------------
    rev_raw = _safe_float(tv_data.get("total_revenue_ttm") or tv_data.get("total_revenue_fy") or tv_data.get("total_revenue_fq"))
    cogs_raw = _safe_float(tv_data.get("cost_of_goods_ttm") or tv_data.get("cost_of_goods_fq") or tv_data.get("cogs_ttm") or tv_data.get("cogs_fq"))
    gp_raw = _safe_float(tv_data.get("gross_profit_ttm") or tv_data.get("gross_profit_fq"))
    ebit_raw = _safe_float(tv_data.get("ebit_ttm") or tv_data.get("ebit_fq"))
    ebitda_raw = _safe_float(tv_data.get("ebitda_ttm") or tv_data.get("ebitda_fq"))
    pretax_raw = _safe_float(tv_data.get("pretax_income_ttm") or tv_data.get("pretax_income_fq"))
    tax_raw = _safe_float(tv_data.get("income_tax_ttm") or tv_data.get("income_tax_fq"))
    interest_raw = _safe_float(tv_data.get("interest_expense_on_debt_ttm") or tv_data.get("interest_expense_on_debt_fq"))

    # Triangle 3: Pretax & Tax -> Net Income
    if s0_npat is not None:
        net_income = s0_npat
        field_provenance["net_income"] = 4
    elif net_inc_raw is not None:
        net_income = net_inc_raw
        field_provenance["net_income"] = 3
    elif pretax_raw is not None and tax_raw is not None:
        net_income = pretax_raw - tax_raw
        field_provenance["net_income"] = 2
    elif eps_raw and shares_out > 0:
        net_income = eps_raw * shares_out
        _prop("net_income", 2, field_provenance["shares"])
    elif rev_raw is not None:
        net_income = rev_raw * (sec_med["net_margin"] / 100.0)
        field_provenance["net_income"] = 1
    elif has_any_real_fundamental and mcap > 0:
        net_income = (mcap * 1_000_000_000.0) / max(1.0, sec_med["pe"])
        _prop("net_income", 1, field_provenance["market_cap"])
    else:
        net_income = 0.0
        field_provenance["net_income"] = 0

    # Triangle 2: Rev, GP, COGS
    if s0_rev is not None:
        revenue = s0_rev
        field_provenance["revenue"] = 4
    elif rev_raw is not None:
        revenue = rev_raw
        field_provenance["revenue"] = 3
    elif gp_raw is not None and cogs_raw is not None:
        revenue = gp_raw + cogs_raw
        field_provenance["revenue"] = 2
    elif net_income > 0 and sec_med["net_margin"] > 0:
        revenue = net_income / (sec_med["net_margin"] / 100.0)
        _prop("revenue", 2, field_provenance["net_income"])
    elif has_any_real_fundamental and mcap > 0:
        revenue = (mcap * 1_000_000_000.0) / max(0.1, sec_med["ps"])
        _prop("revenue", 1, field_provenance["market_cap"])
    else:
        revenue = 0.0
        field_provenance["revenue"] = 0

    # -------------------------------------------------------------
    # 6. Cash Flow & D&A Triangles (FFV Pro 4-Way Reconstitution)
    # -------------------------------------------------------------
    fcf_raw = _safe_float(tv_data.get("free_cash_flow_ttm") or tv_data.get("free_cash_flow_fq"))
    cfo_raw = _safe_float(tv_data.get("cash_f_operating_activities_ttm") or tv_data.get("cash_f_operating_activities_fq"))
    # "depreciation_and_amortization_*" and
    # "cash_flow_depreciation_n_amortization_*" are not TradingView
    # identifiers: the income-statement line is DEP_AMORT_EXP_INCOME_S and
    # the cash-flow line spells it CASH_FLOW_DEPRECATION_N_AMORTIZATION.
    # The four names read here first have therefore never once matched.
    # They stay, harmlessly, in case another vendor's overlay writes them.
    da_raw = _safe_float(
        tv_data.get("dep_amort_exp_income_s_ttm")
        or tv_data.get("dep_amort_exp_income_s_fq")
        or tv_data.get("cash_flow_deprecation_n_amortization_fq")
        or tv_data.get("depreciation_and_amortization_ttm")
        or tv_data.get("depreciation_and_amortization_fq")
        or tv_data.get("cash_flow_depreciation_n_amortization_ttm")
        or tv_data.get("cash_flow_depreciation_n_amortization_fq")
    )
    # CAPITAL_EXPENDITURES is published at FH/FQ/FY only, so the "_ttm"
    # form read first here exists for no company; "capex_*" is not an
    # identifier at all. The annual figure is the one that answers.
    capex_raw = _safe_float(
        tv_data.get("capital_expenditures_ttm")
        or tv_data.get("capital_expenditures_fy")
        or tv_data.get("capital_expenditures_fq")
        or tv_data.get("capex_ttm") or tv_data.get("capex_fq")
    )

    # Triangle 6: D&A Reconstitution
    if da_raw is not None:
        calc_da = da_raw
        field_provenance["da"] = 3
    elif ebitda_raw is not None and ebit_raw is not None:
        calc_da = max(0.0, ebitda_raw - ebit_raw)
        field_provenance["da"] = 2
    elif cfo_raw is not None and net_income > 0:
        calc_da = max(0.0, cfo_raw - net_income)
        _prop("da", 2, field_provenance["net_income"])
    elif revenue > 0:
        calc_da = revenue * 0.04
        field_provenance["da"] = 1
    else:
        calc_da = 0.0

    # Triangle 7: EBITDA
    #
    # The margin rung exists because D&A is the weak link: where it is not
    # reported, calc_da falls to revenue * 0.04 - a sector assumption - and
    # EBITDA inherits tier 1 and is refused for 630 symbols. A reported
    # EBITDA margin needs no D&A at all. It is a ratio, so it carries no
    # unit assumption, and multiplied by revenue we already hold it lands
    # in our units; it propagates revenue's own tier, so a company whose
    # revenue is a sector stand-in is still refused.
    #
    # ebitda_margin_ttm was added to the supplementary request in a3d3799,
    # answered for 672 symbols, and was read by nothing. That is the tenth
    # instance in this audit of a value fetched, tiered and never connected
    # to its user - and the first one I introduced myself.
    ebitda_margin_raw = _safe_float(tv_data.get("ebitda_margin_ttm"))
    if ebitda_margin_raw is not None and not (-100.0 <= ebitda_margin_raw <= 100.0):
        ebitda_margin_raw = None
    if ebitda_raw is not None:
        calc_ebitda = ebitda_raw
        field_provenance["ebitda"] = 3
    elif ebitda_margin_raw is not None and revenue > 0:
        calc_ebitda = revenue * (ebitda_margin_raw / 100.0)
        _prop("ebitda", 3, field_provenance.get("revenue", 0))
    elif ebit_raw is not None and calc_da > 0:
        calc_ebitda = ebit_raw + calc_da
        _prop("ebitda", 2, field_provenance.get("da", 0))
    elif revenue > 0:
        calc_ebitda = revenue * (sec_med["op_margin"] / 100.0) + calc_da
        field_provenance["ebitda"] = 1
    else:
        calc_ebitda = 0.0

    # Triangle 7.5: EBIT
    # EBIT is a driver for six of the 22 valuation models (EPV, the DCFs, the
    # acquirer's multiple). It was being computed nowhere and emitted nowhere,
    # so every one of those models saw it as missing and refused to publish.
    # Operating income is the same quantity, reported under TradingView's
    # other identifier for it (OPER_INCOME). It is a reading, not a
    # derivation, so it sits alongside the reported EBIT rather than below
    # the triangulations - and it was never requested until now.
    oper_income_raw = _safe_float(
        tv_data.get("oper_income_ttm") or tv_data.get("oper_income_fq")
        or tv_data.get("oper_income_fy")
    )
    if ebit_raw is not None:
        calc_ebit = ebit_raw
        field_provenance["ebit"] = 3
    elif oper_income_raw is not None:
        calc_ebit = oper_income_raw
        field_provenance["ebit"] = 3
    elif pretax_raw is not None and interest_raw is not None:
        # EBIT = pretax income + interest expense, the textbook identity.
        # Both lines are reported and both were already being read a hundred
        # lines above for net income, then left unused - so the operating
        # line was declared missing for companies whose income statement
        # states everything needed to compute it.
        #
        # abs() because the sign convention is not fixed: TradingView
        # reports the expense as a positive magnitude in some rows and as a
        # negative adjustment in others, and what the identity needs is the
        # magnitude added back. Interest income, were it netted in here,
        # would be the one case this reads wrong, and it is not separable
        # from this column.
        calc_ebit = pretax_raw + abs(interest_raw)
        field_provenance["ebit"] = 2
    elif calc_ebitda and calc_da > 0 and field_provenance.get("ebitda", 0) >= 2:
        calc_ebit = calc_ebitda - calc_da
        _prop("ebit", 2, field_provenance["ebitda"], field_provenance.get("da", 0))
    elif revenue > 0 and field_provenance.get("revenue", 0) >= 2 and _safe_float(
        tv_data.get("operating_margin_ttm") or tv_data.get("operating_margin_fq")
        or tv_data.get("operating_margin_fy")
    ) is not None:
        # Revenue times the reported operating margin. Two reported figures
        # multiplied together, which is triangulation; it is not the sector
        # median below, which would be the market cap talking.
        op_margin = _safe_float(
            tv_data.get("operating_margin_ttm") or tv_data.get("operating_margin_fq")
        or tv_data.get("operating_margin_fy")
        )
        calc_ebit = revenue * (op_margin / 100.0)
        # Never better than the revenue it multiplies. Testing `revenue > 0`
        # alone let this fire on a revenue imputed from a sector median,
        # which would have dressed a stand-in up as a triangulated operating
        # line - the exact fabrication the gate exists to catch.
        _prop("ebit", 2, field_provenance["revenue"])
    else:
        # No reported operating line and nothing to reconstruct it from. Leave
        # it absent rather than back-solving it from revenue times a sector
        # margin: that would be the market cap talking, not the company.
        calc_ebit = None

    # Triangle 8: OCF / CFO
    if s0_cfo is not None:
        calc_cfo = s0_cfo
        field_provenance["cfo"] = 4
    elif cfo_raw is not None:
        calc_cfo = cfo_raw
        field_provenance["cfo"] = 3
    elif net_income > 0 and calc_da > 0:
        calc_cfo = net_income + calc_da
        _prop("cfo", 2, field_provenance["net_income"], field_provenance.get("da", 0))
    elif net_income > 0:
        calc_cfo = net_income * 1.10
        field_provenance["cfo"] = 1
    else:
        calc_cfo = 0.0

    # Triangle 9: CapEx & True FCF
    if s0_capex is not None:
        calc_capex = abs(s0_capex)
        field_provenance["capex"] = 4
    elif capex_raw is not None:
        calc_capex = abs(capex_raw)
        field_provenance["capex"] = 3
    elif calc_da > 0:
        calc_capex = calc_da * 0.85
        _prop("capex", 1, field_provenance.get("da", 0))
    else:
        calc_capex = 0.0
        field_provenance["capex"] = 0

    if s0_fcf is not None:
        fcf_ttm = round(s0_fcf / 1_000_000_000.0, 1) if abs(s0_fcf) > 10_000_000 else round(s0_fcf, 1)
        field_provenance["fcf_ttm"] = 4
    elif s0_cfo is not None and s0_capex is not None:
        fcf_ttm = round(max(0.0, (s0_cfo - abs(s0_capex))) / 1_000_000_000.0, 1)
        field_provenance["fcf_ttm"] = 4
    elif fcf_raw is not None:
        fcf_ttm = round(fcf_raw / 1_000_000_000.0, 1) if abs(fcf_raw) > 10_000_000 else round(fcf_raw, 1)
        field_provenance["fcf_ttm"] = 3
    elif calc_cfo > 0:
        fcf_ttm = round(max(0.0, (calc_cfo - calc_capex)) / 1_000_000_000.0, 1) if abs(calc_cfo) > 10_000_000 else round(max(0.0, calc_cfo - calc_capex), 1)
        _prop("fcf_ttm", 2, field_provenance.get("cfo", 0), field_provenance.get("capex", 0))
    else:
        fcf_ttm = round(max(0.0, (net_income * 0.70) / 1_000_000_000.0), 1)
        _prop("fcf_ttm", 1, field_provenance.get("net_income", 0))

    # Margins
    gross_m_raw = _safe_float(tv_data.get("gross_margin_ttm") or tv_data.get("gross_margin_fq"))
    # _fy included because it is the one that answers: the catalogue does
    # not publish OPERATING_MARGIN at TTM at all, and the measured run put
    # operating_margin_fy at 795 non-null of 1522. _ttm is kept first
    # because that is the key the Vietcap margin is written under.
    op_m_raw = _safe_float(tv_data.get("operating_margin_ttm")
                           or tv_data.get("operating_margin_fq")
                           or tv_data.get("operating_margin_fy"))
    net_m_raw = _safe_float(tv_data.get("net_margin_ttm") or tv_data.get("net_margin_fq"))

    # Scale normalization: if decimal (e.g. 0.25 -> 25.0%)
    if gross_m_raw is not None and 0 < abs(gross_m_raw) <= 1.0:
        gross_m_raw = round(gross_m_raw * 100.0, 2)
    if op_m_raw is not None and 0 < abs(op_m_raw) <= 1.0:
        op_m_raw = round(op_m_raw * 100.0, 2)
    if net_m_raw is not None and 0 < abs(net_m_raw) <= 1.0:
        net_m_raw = round(net_m_raw * 100.0, 2)

    if gross_m_raw is not None:
        gross_margin = gross_m_raw
        field_provenance["gross_margin"] = 3
    else:
        gross_margin = sec_med["gross_margin"]
        field_provenance["gross_margin"] = 1

    if op_m_raw is not None:
        op_margin = op_m_raw
        field_provenance["op_margin"] = 3
    elif ebit_raw is not None and revenue > 0:
        op_margin = round((ebit_raw / revenue) * 100.0, 2)
        _prop("op_margin", 2, field_provenance["revenue"])
    else:
        op_margin = sec_med["op_margin"]
        field_provenance["op_margin"] = 1

    if net_m_raw is not None:
        net_margin = net_m_raw
        field_provenance["net_margin"] = 3
    elif net_income is not None and revenue > 0:
        net_margin = round((net_income / revenue) * 100.0, 2)
        _prop("net_margin", 2, field_provenance["net_income"], field_provenance["revenue"])
    else:
        net_margin = sec_med["net_margin"]
        field_provenance["net_margin"] = 1

    # -------------------------------------------------------------
    # 4. Profitability & Returns (ROE, ROA)
    # -------------------------------------------------------------
    roe_raw = _safe_float(tv_data.get("return_on_equity_fq") or tv_data.get("return_on_equity_fy") or vn_data.get("roe"))
    roa_raw = _safe_float(tv_data.get("return_on_assets_fq") or vn_data.get("roa"))

    # Scale normalization for fallback sources returning decimal (e.g. 0.18 -> 18.0%)
    if roe_raw is not None and 0 < abs(roe_raw) <= 1.0:
        roe_raw = round(roe_raw * 100.0, 2)
    if roa_raw is not None and 0 < abs(roa_raw) <= 1.0:
        roa_raw = round(roa_raw * 100.0, 2)

    if roe_raw is not None:
        roe = roe_raw
        field_provenance["roe"] = 3
    elif net_income is not None and tot_eq and tot_eq > 0:
        roe = round((net_income / tot_eq) * 100.0, 2)
        _prop("roe", 2, field_provenance["net_income"], field_provenance["total_equity"])
    else:
        roe = sec_med["roe"]
        field_provenance["roe"] = 1

    if roa_raw is not None:
        roa = roa_raw
        field_provenance["roa"] = 3
    elif tot_assets and tot_assets > 0 and net_income is not None:
        roa = round((net_income / tot_assets) * 100.0, 2)
        _prop("roa", 2, field_provenance["net_income"], 3)
    else:
        roa = sec_med["roa"]
        field_provenance["roa"] = 1

    # -------------------------------------------------------------
    # 5. Valuation Multiples (P/E, P/B, P/S, PEG, EPS, Dividend Yield)
    # -------------------------------------------------------------
    pe_raw = _safe_float(tv_data.get("price_earnings_ttm") or vn_data.get("pe"))
    pb_raw = _safe_float(tv_data.get("price_book_fq") or vn_data.get("pb"))
    ps_raw = _safe_float(tv_data.get("price_sales_current"))
    div_yield_raw = _safe_float(tv_data.get("dividend_yield_recent"))
    if div_yield_raw is None:
        div_yield_raw = _safe_float(tv_data.get("dividends_yield_current"))
    if div_yield_raw is not None and 0 < abs(div_yield_raw) <= 1.0:
        div_yield_raw = round(div_yield_raw * 100.0, 2)

    if pe_raw is not None:
        pe = pe_raw
        field_provenance["pe"] = 3
    elif price > 0 and eps_raw and eps_raw > 0:
        pe = round(price / eps_raw, 2)
        # price is an input here: an invented fallback price must poison it.
        _prop("pe", 2, price_tier)
    elif mcap > 0 and net_income > 0:
        pe = round((mcap * 1_000_000_000.0) / net_income, 2)
        _prop("pe", 2, field_provenance["market_cap"], field_provenance["net_income"])
    else:
        pe = sec_med["pe"]
        field_provenance["pe"] = 1

    if pb_raw is not None:
        pb = pb_raw
        field_provenance["pb"] = 3
    elif mcap > 0 and tot_eq and tot_eq > 0:
        pb = round((mcap * 1_000_000_000.0) / tot_eq, 2)
        _prop("pb", 2, field_provenance["market_cap"], field_provenance["total_equity"])
    else:
        pb = sec_med["pb"]
        field_provenance["pb"] = 1

    if ps_raw is not None:
        ps = ps_raw
        field_provenance["ps"] = 3
    elif mcap > 0 and revenue > 0:
        ps = round((mcap * 1_000_000_000.0) / revenue, 2)
        _prop("ps", 2, field_provenance["market_cap"], field_provenance["revenue"])
    else:
        ps = sec_med["ps"]
        field_provenance["ps"] = 1

    # EPS: explicit 3-way branch so the 2000.0 placeholder is never silently reported
    if eps_raw is not None:
        eps = eps_raw
        field_provenance["eps"] = 3
    elif price > 0:
        eps = round(price / max(1.0, pe), 0)
        # price is an input: empty-input eps can never exceed tier 1 (in
        # fact inherits the fallback price's tier 0).
        _prop("eps", 2, field_provenance["pe"], price_tier)
    else:
        eps = 2000.0
        field_provenance["eps"] = 0

    # Dividend Yield: silent 0.0 default flagged as fabricated
    if div_yield_raw is not None:
        div_yield = div_yield_raw
        field_provenance["dividend_yield"] = 3
    else:
        div_yield = 0.0
        field_provenance["dividend_yield"] = 0

    # Dividend per share, from the yield that was already here.
    #
    # dividend_per_share is the largest blocking driver at 162 symbols, and
    # nothing in this file has ever written it. The resolver asks
    # res.resolve("dividend_per_share", ("dividend_per_share",)) - one key,
    # no aliases - and no producer emits that key, so the ask has never once
    # been answered and utilities_3stage_ddm has been suppressed for every
    # company in the universe since it was written.
    #
    # The ingredient was never missing. div_yield is measured above, carries
    # its own provenance tier, and is normalised to a percentage two lines
    # up: the vendor sends either 5.0 or 0.05 for a 5% yield, and the
    # `0 < abs(x) <= 1.0` branch settles which. So the dividend is
    # price * yield / 100, in dong per share, from two figures already held.
    # Measured, tiered, connected to nothing - the fifteenth time in this
    # audit, and the purest: a consumer asking by a name no producer writes.
    #
    # Offered only for a yield that was actually reported and is positive.
    # The else-branch above sets div_yield to 0.0 at tier 0, and a zero
    # dividend is not a small dividend - it means the vendor said nothing.
    # Emitting 0.0 would hand the DDM a number to divide by and turn a
    # refusal into an answer, which is the failure this whole gate exists to
    # prevent. Absent, the resolver imputes it and the model stays suppressed,
    # exactly as it does today.
    #
    # price is an input, so the fabricated 10000.0 fallback poisons this the
    # same way it poisons pe and eps above.
    if div_yield_raw is not None and div_yield > 0 and price > 0:
        dividend_per_share = round(price * div_yield / 100.0, 2)
        _prop("dividend_per_share", 2,
              field_provenance["dividend_yield"], price_tier)
    else:
        dividend_per_share = None

    # -------------------------------------------------------------
    # 6. CFO to PAT Ratio (Cash Conversion Ratio)
    # -------------------------------------------------------------
    if calc_cfo > 0 and net_income > 0:
        cfo_to_pat = round(calc_cfo / max(1.0, net_income), 2)
        _prop("cfo_to_pat", field_provenance.get("cfo", 2), field_provenance["net_income"])
    elif fcf_ttm > 0 and net_income > 0:
        cfo_to_pat = round((fcf_ttm * 1_000_000_000.0 * 1.35) / max(1.0, net_income), 2)
        _prop("cfo_to_pat", 2, field_provenance["fcf_ttm"], field_provenance["net_income"])
    else:
        cfo_to_pat = 1.05
        field_provenance["cfo_to_pat"] = 1

    # -------------------------------------------------------------
    # 7. Growth YoY & CAGRs
    # (TradingView renamed growth columns ~08/2026: *_growth_yoy_* -> *_yoy_growth_*)
    # -------------------------------------------------------------
    def _tv_first(*keys):
        for k in keys:
            v = _safe_float(tv_data.get(k))
            if v is not None:
                return v
        return None

    rev_1y = _tv_first(
        "total_revenue_yoy_growth_fq", "total_revenue_yoy_growth_fy",
        "total_revenue_growth_yoy_fq", "total_revenue_growth_yoy_fy",
        "total_revenue_yoy_growth_ttm"
    )
    if rev_1y is None:
        rev_1y = 10.0
        field_provenance["rev_1y_growth"] = 1  # Constant fill, not reported
    else:
        field_provenance["rev_1y_growth"] = 3

    # Last year's revenue, recovered from this year's and the growth rate
    # the vendor reports against it. Both numbers are already here; the
    # engine's DCF asked for prev_revenue, no producer had ever written it,
    # and the impute standing in its place was revenue * (1 - g) using the
    # engine's OWN forecast growth - which makes the historical base a
    # function of the forecast, and the forecast then reads as confirmed by
    # history. Recovering it from the reported growth breaks that loop.
    #
    # Guarded below -100%: a growth rate of exactly -100% means revenue went
    # to zero, and anything past it would produce a negative prior year.
    if revenue is not None and revenue > 0 and rev_1y is not None and rev_1y > -100.0:
        prev_revenue = round(revenue / (1.0 + rev_1y / 100.0), 2)
        _prop("prev_revenue", 2,
              field_provenance["revenue"], field_provenance["rev_1y_growth"])
    else:
        prev_revenue = None

    pat_1y = _tv_first(
        "net_income_yoy_growth_fq", "net_income_yoy_growth_fy",
        "net_income_growth_yoy_fq", "net_income_growth_yoy_fy",
        "net_income_yoy_growth_ttm"
    )
    if pat_1y is None:
        pat_1y = 12.0
        field_provenance["pat_1y_growth"] = 1  # Constant fill, not reported
    else:
        field_provenance["pat_1y_growth"] = 3

    rev_5y_growth = _tv_first(
        "total_revenue_cagr_5y", "total_revenue_growth_5y_cagr"
    )
    if rev_5y_growth is not None:
        field_provenance["rev_5y_growth"] = 3

    rev_3y_cagr = _tv_first(
        "total_revenue_cagr_3y", "total_revenue_growth_3y_cagr"
    )
    if rev_3y_cagr is None:
        if rev_5y_growth is not None:
            rev_3y_cagr = round((rev_1y + rev_5y_growth) / 2.0, 1)
            _prop("rev_3y_cagr", 2, field_provenance["rev_1y_growth"], field_provenance["rev_5y_growth"])
        else:
            rev_3y_cagr = round(rev_1y * 0.88, 1)
            _prop("rev_3y_cagr", 1, field_provenance["rev_1y_growth"])
    else:
        field_provenance["rev_3y_cagr"] = 3
    if rev_5y_growth is None:
        rev_5y_growth = round(rev_3y_cagr * 3.6, 1)
        _prop("rev_5y_growth", 1, field_provenance["rev_3y_cagr"])

    pat_3y_cagr = round(pat_1y * 0.90, 1)
    pat_5y_growth = round(pat_3y_cagr * 3.8, 1)
    _prop("pat_3y_cagr", 2, field_provenance["pat_1y_growth"])
    _prop("pat_5y_growth", 2, field_provenance["pat_3y_cagr"])

    peg = round(pe / max(2.0, pat_1y), 2) if pat_1y > 0 else 2.5
    peg_sales = round(pe / max(2.0, rev_3y_cagr), 2) if rev_3y_cagr > 0 else 2.5
    _prop("peg", 2, field_provenance["pe"], field_provenance["pat_1y_growth"])
    _prop("peg_sales", 2, field_provenance["pe"], field_provenance["rev_3y_cagr"])

    # Quick Ratio
    quick_ratio_raw = _safe_float(tv_data.get("quick_ratio_fq"))
    if quick_ratio_raw is not None:
        quick_ratio = quick_ratio_raw
        field_provenance["quick_ratio"] = 3
    else:
        # Fallback: estimate from current ratio (quick ~= current * 0.75 for manufacturing, ~0.85 for services)
        is_asset_heavy = sector_code in ["VNMAT", "VNIND", "VNENE", "VNREAL"]
        quick_ratio = round(cur_ratio * (0.70 if is_asset_heavy else 0.82), 2)
        _prop("quick_ratio", 1, field_provenance["current_ratio"])

    # Cash to Assets Ratio (%)
    # TradingView does NOT return cash_n_cash_equivalents_fq for Vietnam stocks
    # So we estimate from balance sheet: Cash ≈ (Current Assets - Inventory) proxy
    # Current Assets ≈ Total Assets * Current Ratio / (1 + Current Ratio) for non-banks
    # Cash portion ≈ Quick Ratio / Current Ratio * Current Assets
    if tot_assets and tot_assets > 0 and cash_equiv > 0:
        # Real data available (unlikely for VN)
        cash_to_assets = round((cash_equiv / tot_assets) * 100.0, 2)
        field_provenance["cash_to_assets"] = 3
    elif tot_assets and tot_assets > 0 and tot_liab is not None and cur_ratio > 0:
        # Estimate: Current Assets ≈ Current Liabilities * Current Ratio
        # Current Liabilities ≈ Total Liabilities * 0.55 (short-term portion)
        est_current_liab = (tot_liab if tot_liab else tot_debt * 1.3) * 0.55
        est_current_assets = est_current_liab * cur_ratio
        # Cash ≈ Quick Assets - Receivables ≈ Quick Ratio * Current Liabilities * 0.45
        qr = quick_ratio if quick_ratio > 0 else cur_ratio * 0.75
        est_cash = est_current_liab * qr * 0.45
        cash_to_assets = round(max(0.5, min(50.0, (est_cash / tot_assets) * 100.0)), 2)
        _prop("cash_to_assets", 2, field_provenance["quick_ratio"])
    elif tot_assets and tot_assets > 0 and tot_debt is not None:
        # Cruder estimate: low debt → more cash; high debt → less cash
        est_cash_pct = max(2.0, 15.0 - de_ratio * 8.0)
        cash_to_assets = round(est_cash_pct, 2)
        _prop("cash_to_assets", 2, field_provenance["de_ratio"])
    else:
        cash_to_assets = round(9.0 if cur_ratio >= 1.5 else 5.5, 2)
        _prop("cash_to_assets", 1, field_provenance["current_ratio"])

    # Interest Coverage Ratio (ICR)
    # Priority: EBIT / estimated interest expense
    ebitda_raw = _safe_float(tv_data.get("ebitda_ttm"))
    if ebit_raw is not None and tot_debt and tot_debt > 0:
        # Use average VN corporate borrowing rate ~7.5% for interest estimation
        est_interest = max(1.0, tot_debt * 0.075)
        interest_coverage = round(max(0.0, ebit_raw / est_interest), 2)
        _prop("interest_coverage", 2, field_provenance["total_debt"])
    elif ebitda_raw is not None and tot_debt and tot_debt > 0:
        # EBITDA fallback (slightly overestimates ICR but more available)
        est_interest = max(1.0, tot_debt * 0.075)
        interest_coverage = round(max(0.0, ebitda_raw * 0.85 / est_interest), 2)
        _prop("interest_coverage", 2, field_provenance["total_debt"])
    elif net_income > 0 and tot_debt and tot_debt > 0:
        # Net Income proxy: NI ≈ (EBIT - Interest) * (1 - Tax), so EBIT ≈ NI/0.8 + Interest
        est_interest = max(1.0, tot_debt * 0.075)
        est_ebit = net_income / 0.80 + est_interest
        interest_coverage = round(max(0.5, est_ebit / est_interest), 2)
        _prop("interest_coverage", 2, field_provenance["net_income"], field_provenance["total_debt"])
    elif de_ratio < 0.1:
        # Nearly zero debt → very high coverage
        interest_coverage = 25.0
        field_provenance["interest_coverage"] = 1
    elif de_ratio < 0.3:
        interest_coverage = 12.0
        field_provenance["interest_coverage"] = 1
    else:
        interest_coverage = round(max(1.0, 8.0 / max(0.5, de_ratio)), 2)
        field_provenance["interest_coverage"] = 1

    # Rule of 40 (Growth + Margin) — pure formula, no fetch needed
    rule_of_40 = round(rev_1y + net_margin, 2)
    _prop("rule_of_40", 2, field_provenance["rev_1y_growth"], field_provenance["net_margin"])

    # ROIC (Return on Invested Capital) — proxy from available data
    # ROIC = NOPAT / Invested Capital
    # NOPAT ≈ EBIT * (1 - tax_rate), Invested Capital ≈ Total Equity + Total Debt - Cash
    # A reported ROIC outranks every proxy below it. return_on_invested_
    # capital_fq was added to the supplementary request in a3d3799,
    # answered for 744 symbols, and - like the EBITDA margin above - was
    # read by nothing, while roic blocked 155 symbols. It is a percentage,
    # so there is no unit to get wrong; a value outside the band is
    # discarded rather than reinterpreted, and a fraction the vendor
    # labelled a percent would land inside it, so the |x| <= 1 rescale the
    # neighbouring ratios use is deliberately not applied here - it cannot
    # be told apart from a genuine sub-1% return.
    roic_raw = _safe_float(tv_data.get("return_on_invested_capital_fq"))
    if roic_raw is not None and not (-100.0 <= roic_raw <= 100.0):
        roic_raw = None

    if roic_raw is not None:
        roic = round(roic_raw, 2)
        field_provenance["roic"] = 3
    elif ebit_raw is not None and tot_eq and tot_eq > 0 and tot_debt is not None:
        nopat = ebit_raw * 0.80  # assume 20% effective tax rate
        invested_capital = tot_eq + tot_debt - cash_equiv
        roic = round((nopat / max(1.0, invested_capital)) * 100.0, 2) if invested_capital > 0 else round(roe * 0.85, 2)
        _prop("roic", 2, field_provenance["total_equity"], field_provenance["total_debt"])
    elif net_income > 0 and tot_eq and tot_eq > 0 and tot_debt is not None:
        # NI-based proxy: ROIC ≈ NI / (Equity + Debt)
        invested_capital = tot_eq + tot_debt
        roic = round((net_income / max(1.0, invested_capital)) * 100.0, 2) if invested_capital > 0 else round(roe * 0.85, 2)
        _prop("roic", 2, field_provenance["net_income"], field_provenance["total_equity"], field_provenance["total_debt"])
    else:
        # Pure proxy from ROE adjusted for leverage
        roic = round((roe / max(1.0, 1.0 + de_ratio * 0.65)) * 1.05, 2)
        field_provenance["roic"] = 1

    # -------------------------------------------------------------
    # 8. Data Quality Score & Provenance Tier Assessment
    # -------------------------------------------------------------
    # Placeholder constants kept for downstream compatibility but flagged
    # as fabricated (tier 0) so consumers can exclude them via is_imputed.
    core_pat_ratio = 94.0 if sector_code != "VNREAL" else 82.0
    field_provenance["core_pat_ratio"] = 0
    field_provenance["share_dilution_3y"] = 0
    field_provenance["dilution_spread"] = 0

    # Composite fields: tier follows the worst real input used to derive them.
    ebit_expansion = round(op_margin - sec_med["op_margin"], 2)
    field_provenance["ebit_expansion"] = 2 if field_provenance["op_margin"] == 3 else 1
    operating_leverage = bool(pat_1y >= rev_1y * 0.9)
    field_provenance["operating_leverage"] = 2 if (field_provenance["pat_1y_growth"] == 3 and field_provenance["rev_1y_growth"] == 3) else 1
    # eps_3y_cagr is an alias of pat_3y_cagr -> identical provenance.
    field_provenance["eps_3y_cagr"] = field_provenance["pat_3y_cagr"]

    # Align internal witness names with output scalar names so is_imputed
    # below has a provenance entry for every returned field (fail-closed:
    # any missing entry defaults to tier 0, i.e. imputed).
    field_provenance.setdefault("mcap", field_provenance.get("market_cap", 0))
    field_provenance.setdefault("shares_out", field_provenance.get("shares", 0))

    provenance_values = list(field_provenance.values())
    tier4_count = provenance_values.count(4)
    tier3_count = provenance_values.count(3)
    tier2_count = provenance_values.count(2)
    tier1_count = provenance_values.count(1)
    total_fields = max(1, len(provenance_values))

    data_quality_score = round(((tier4_count * 1.0 + tier3_count * 0.95 + tier2_count * 0.85 + tier1_count * 0.50) / total_fields) * 100.0, 1)

    if not has_any_real_fundamental:
        provenance_tier = "Tier 0 (Discarded / Shell)"
        data_quality_score = 15.0
        is_valid_fundamental = False
    elif tier4_count >= 5:
        provenance_tier = "Tier 0 (Ground Truth Audited)"
        is_valid_fundamental = True
    elif (tier4_count + tier3_count) >= 8:
        provenance_tier = "Tier 3 (Reported / Audited)"
        is_valid_fundamental = True
    elif (tier4_count + tier3_count + tier2_count) >= 6:
        provenance_tier = "Tier 2 (Triangulated)"
        is_valid_fundamental = True
    else:
        provenance_tier = "Tier 1 (Sector Dynamic)"
        is_valid_fundamental = True

    # Compute or attach Forensic Triangles
    forensics = s0.get("forensic_triangles")
    if not forensics and (has_real_s0 or s0_bs):
        try:
            from services.bctc_pdf_parser import calculate_forensic_triangles
            forensics = calculate_forensic_triangles(s0, s0.get("disclosures"))
        except Exception:
            forensics = None

    # -------------------------------------------------------------
    # 8.5 Absolute statement lines
    #
    # Everything above reconstructs the balance sheet, income statement and
    # cash flow, tiers each line, and then - until now - threw the lines away
    # and published only the ratios derived from them. The valuation engine
    # looks up "debt", "cash", "ebit", "equity", "revenue": absent, all five
    # resolved as imputed, and the provenance gate refused every per-share
    # model for every symbol in the universe. The numbers existed the whole
    # time. Emit them, each carrying the tier of the witness it came from, so
    # the gate judges the evidence rather than its absence.
    #
    # Units: raw VND, matching what the engine derives internally as
    # price * shares. "mcap" above stays in billions - it is a display field
    # and the engine does not read it.
    # -------------------------------------------------------------
    _absolute_lines = {
        "total_assets": (tot_assets, "total_assets"),
        "total_liabilities": (tot_liab, "total_liabilities"),
        "equity": (tot_eq, "total_equity"),
        "debt": (tot_debt, "total_debt"),
        "cash": (cash_equiv, "cash"),
        "revenue": (revenue, "revenue"),
        "net_income": (net_income, "net_income"),
        "ebit": (calc_ebit, "ebit"),
        "ebitda": (calc_ebitda, "ebitda"),
        "cfo": (calc_cfo, "cfo"),
        "capex": (calc_capex, "capex"),
        # Depreciation and amortisation. Tiered here since the beginning and
        # never published, so the engine could not compute EBITDA = EBIT +
        # D&A and fell back on asserting D&A is 25% of EBIT for every
        # company on earth.
        "da": (calc_da, "da"),
        # The current halves of the balance sheet. Both were reconstructed
        # and tiered here from the start and neither was ever published, so
        # working capital - a subtraction of two numbers already in this
        # function - had no derivation available downstream and stood on
        # (assets - liabilities) * 0.25.
        "current_assets": (curr_assets, "current_assets"),
        "current_liabilities": (curr_liab_raw, "current_liabilities"),
        "retained_earnings": (retained_earnings_raw, "retained_earnings"),
        "prev_revenue": (prev_revenue, "prev_revenue"),
        # Working capital itself, so the identity is computed once, here,
        # where both halves carry their tiers, rather than reassembled by
        # each consumer.
        "working_capital": (
            None if curr_assets is None or curr_liab_raw is None
            else curr_assets - curr_liab_raw,
            "current_assets",
        ),
    }

    # Tangible book equity, for p_tbv - the model tbvps blocks for all 1,177
    # symbols that carry it.
    #
    # TBV = equity - goodwill - intangibles. The trap is that TradingView
    # omits a null column entirely, so an absent goodwill_fq means either
    # "this company has no goodwill" or "the vendor does not report the line
    # for it", and those are not distinguishable from the payload. Assuming
    # the first inflates tangible book above the truth, which for a floor
    # valuation is the wrong direction to be wrong in.
    #
    # So the line is published only when the vendor reports at least one of
    # the two, which is evidence that it reports this part of the balance
    # sheet for this company; a zero alongside it is then a reading rather
    # than an assumption. Where neither is reported, nothing is emitted and
    # p_tbv stays refused, as it should be.
    # A reported tangible book value per share settles it outright, and
    # needs neither of those columns. book_tangible_per_share_fq was added
    # to the supplementary request in a3d3799, answered for 785 symbols,
    # and was read by nothing.
    #
    # It is a per-share figure, and this vendor's per-share figures are in
    # the listing currency - the same units as close, which the whole
    # engine already runs on. That is an inference rather than a statement,
    # so it is checked rather than trusted: tangible book cannot exceed
    # total book, and a figure in the wrong units misses that bound by
    # three orders of magnitude. Anything failing it falls through to the
    # subtraction below.
    _tbvps_raw = _safe_float(tv_data.get("book_tangible_per_share_fq"))
    _goodwill_reported = tv_data.get("goodwill_fq") is not None
    _intangibles_reported = tv_data.get("intangibles_net_fq") is not None
    if (_tbvps_raw is not None and shares_out > 0 and tot_eq and tot_eq > 0
            and 0.0 < _tbvps_raw * shares_out <= tot_eq * 1.02
            and "total_equity" in field_provenance):
        _absolute_lines["tangible_equity"] = (
            _tbvps_raw * shares_out, "total_equity",
        )
    elif (_goodwill_reported or _intangibles_reported) and "total_equity" in field_provenance:
        _absolute_lines["tangible_equity"] = (
            tot_eq - goodwill_raw - intangibles_raw, "total_equity",
        )
    absolute_lines: Dict[str, float] = {}
    for _name, (_value, _witness) in _absolute_lines.items():
        if _value is None or _witness not in field_provenance:
            # Fail closed: a line with no tier is a line with no provenance,
            # and publishing it untiered would let it read as observed.
            continue
        absolute_lines[_name] = float(_value)
        field_provenance[_name] = field_provenance[_witness]

    # working_capital stands on two witnesses, and the single-witness rule
    # above can only copy one of them. A reconstruction is tier 2 at best,
    # and it inherits the weaker of the two halves it was subtracted from -
    # a current-assets figure guessed at 40% of total assets must not let a
    # working capital derived from it read as observed.
    if "working_capital" in absolute_lines:
        _prop("working_capital", 2,
              field_provenance["current_assets"],
              field_provenance["current_liabilities"])

    # -------------------------------------------------------------
    # Close the system.
    #
    # Every ladder above has now run. Each knows the two or three routes
    # somebody thought of while writing that field; none of them knows that
    # the same number may be recoverable from a fourth direction that
    # happens to be available for this particular company. The identity
    # catalogue does, and it runs last so that it can only fill gaps: a
    # field a ladder answered is never overwritten, because the ladder knew
    # which vendor column to prefer and this table does not.
    #
    # It adds no information. Everything it produces was already implied by
    # figures the vendors stated, and where an identity has two unknowns it
    # declines - which is why fcf stays blocked for the companies whose
    # payload carries neither cfo nor capex. See services/accounting_
    # identities.py for the two guards that make a catalogue safe rather
    # than merely complete: lineage, so a value can never help compute its
    # own ancestor and a pair of identities cannot manufacture a balance
    # sheet that balances by construction; and depth, so a figure recovered
    # through a long chain degrades to a stand-in instead of inheriting the
    # tier of the strongest evidence anywhere behind it.
    # -------------------------------------------------------------
    _solver_inputs = {
        "total_assets": tot_assets,
        "total_liabilities": tot_liab,
        "total_equity": tot_eq,
        "current_assets": curr_assets,
        "current_liabilities": curr_liab_raw,
        "working_capital": absolute_lines.get("working_capital"),
        "ebit": calc_ebit,
        "ebitda": calc_ebitda,
        "da": calc_da,
        "cfo": calc_cfo,
        "capex": calc_capex,
        "fcf_ttm": fcf_ttm,
        "net_income": net_income,
        "revenue": revenue,
        "prev_revenue": prev_revenue,
        "eps": eps,
        "shares": shares_out,
        "rev_1y_growth": rev_1y,
    }
    # A field with a value but no tier is not evidence and must not seed a
    # derivation; dropping it here makes the solver inherit only from lines
    # this service has already vouched for.
    _solver_inputs = {
        name: value for name, value in _solver_inputs.items()
        if value is not None and name in field_provenance
    }
    _recovered = solve_accounting_identities(_solver_inputs, field_provenance)

    #: Which published line each solver field is emitted as. A name absent
    #: here is recovered for the sake of the identities that consume it and
    #: is not itself a published statement line.
    _SOLVED_LINE_NAMES = {
        "total_assets": "total_assets",
        "total_liabilities": "total_liabilities",
        "total_equity": "equity",
        "current_assets": "current_assets",
        "current_liabilities": "current_liabilities",
        "working_capital": "working_capital",
        "ebit": "ebit",
        "ebitda": "ebitda",
        "da": "da",
        "cfo": "cfo",
        "capex": "capex",
        "net_income": "net_income",
        "revenue": "revenue",
        "prev_revenue": "prev_revenue",
    }
    for _name, (_value, _tier, _depth, _note) in _recovered.items():
        field_provenance[_name] = _tier
        _line = _SOLVED_LINE_NAMES.get(_name)
        if _line is not None and _line not in absolute_lines:
            absolute_lines[_line] = float(_value)
            field_provenance[_line] = _tier

    result = {
        "mcap": mcap,
        "shares_out": shares_out,
        "pe": pe,
        "pb": pb,
        "ps": ps,
        "peg": peg,
        "peg_sales": peg_sales,
        "eps": eps,
        "dividend_yield": div_yield,
        # Omitted entirely when the yield was not reported: the resolver
        # treats an absent key as missing and imputes it, which is the
        # behaviour a fabricated zero would destroy.
        **({"dividend_per_share": dividend_per_share}
           if dividend_per_share is not None else {}),
        "roe": roe,
        "roa": roa,
        "gross_margin": gross_margin,
        "op_margin": op_margin,
        "net_margin": net_margin,
        "core_pat_ratio": core_pat_ratio,
        "rev_1y_growth": rev_1y,
        "rev_3y_cagr": rev_3y_cagr,
        "rev_5y_growth": rev_5y_growth,
        "pat_1y_growth": pat_1y,
        "pat_3y_cagr": pat_3y_cagr,
        "pat_5y_growth": pat_5y_growth,
        "eps_3y_cagr": pat_3y_cagr,
        "de_ratio": de_ratio,
        "net_de_ratio": net_de_ratio,
        "current_ratio": cur_ratio,
        "quick_ratio": quick_ratio,
        "interest_coverage": interest_coverage,
        "cash_to_assets": cash_to_assets,
        "rule_of_40": rule_of_40,
        "roic": roic,
        "fcf_ttm": fcf_ttm,
        "cfo_to_pat": cfo_to_pat,
        "share_dilution_3y": 2.0,
        "ebit_expansion": ebit_expansion,
        "operating_leverage": operating_leverage,
        "dilution_spread": 1.2,
        "field_provenance": field_provenance,
        "data_quality_score": data_quality_score,
        "provenance_tier": provenance_tier,
        "is_valid_fundamental": is_valid_fundamental
    }
    result.update(absolute_lines)

    # -------------------------------------------------------------
    # 9. Consumer-Facing Imputation Flags (no silent fills)
    # Mirrors OpenBB's convention: every field is either reported (tier 3,
    # is_imputed=False) or explicitly flagged as imputed/fabricated.
    # The map is a SUPERSET: it covers every scalar result key AND every
    # key of field_provenance -- including internal witness names
    # ("shares", "total_equity", "total_debt", "net_income", "revenue",
    # "market_cap") that never appear as output scalars but DO feed
    # derived fields. Fail-closed: any key missing from field_provenance
    # defaults to tier 0 => is_imputed=True.
    # -------------------------------------------------------------
    _imputation_excluded = (
        "field_provenance", "data_quality_score",
        "provenance_tier", "is_valid_fundamental",
    )
    result["is_imputed"] = {
        key: field_provenance.get(key, 0) < 3
        for key in sorted(set(result) | set(field_provenance))
        if key not in _imputation_excluded
    }
    return result

def load_source0_symbol_data(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Loads L2 extracted filings (BCTC + Corporate Actions) for a symbol from PDF Lake.
    Assembles balance sheet, income statement, cash flow, auditor opinions,
    and computes the 5 Forensic Accounting Triangles.
    """
    try:
        from services.bctc_batch_processor import (
            _get_lake_data,
            _get_corporate_actions_lake,
            calculate_source0_ttm,
            extract_records_from_lake
        )
        from services.bctc_pdf_parser import calculate_forensic_triangles

        symbol_clean = symbol.upper().strip()
        cache_key = f"source0_data_v2_{symbol_clean}"
        cache_engine = None
        try:
            from services.stock_service import cache as cache_engine
            cached = cache_engine.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            cache_engine = None

        bctc_lake = _get_lake_data()
        corp_lake = _get_corporate_actions_lake()

        matching_bctc = extract_records_from_lake(bctc_lake, symbol_clean, key_field="periods")
        matching_corp = extract_records_from_lake(corp_lake, symbol_clean, key_field="records")

        if not matching_bctc and not matching_corp:
            return None

        latest_bctc = None
        if matching_bctc:
            matching_bctc.sort(key=lambda x: (str(x.get("year", "")), x.get("filing_timestamp", 0)), reverse=True)
            latest_bctc = matching_bctc[0]

        bctc_extracted = latest_bctc.get("extracted_data", {}) if latest_bctc else {}
        ttm_metrics = calculate_source0_ttm(symbol_clean, bctc_lake)

        disclosures_combined = {
            "resolution_data": {},
            "governance_data": {},
            "dividend_data": {},
            "related_party_transactions": []
        }
        for c in matching_corp:
            cat = c.get("category")
            ext = c.get("extracted_data", {})
            if cat == "resolution" and not disclosures_combined["resolution_data"]:
                disclosures_combined["resolution_data"] = ext.get("resolution_data", {})
            elif cat == "governance" and not disclosures_combined["governance_data"]:
                disclosures_combined["governance_data"] = ext.get("governance_data", {})
                disclosures_combined["related_party_transactions"].extend(
                    ext.get("governance_data", {}).get("related_party_transactions", [])
                )
            elif cat == "dividend" and not disclosures_combined["dividend_data"]:
                disclosures_combined["dividend_data"] = ext.get("dividend_data", {})

        from services.bctc_pdf_parser import calculate_forensic_triangles, detect_accounting_regime
        company_form = detect_accounting_regime(symbol=symbol_clean)
        forensics = calculate_forensic_triangles(bctc_extracted, disclosures_combined, company_form=company_form)

        res = {
            "symbol": symbol_clean,
            "company_form": company_form,
            "doc_id": latest_bctc.get("doc_id") if latest_bctc else None,
            "filing_date": latest_bctc.get("filing_date") if latest_bctc else None,
            "filing_timestamp": latest_bctc.get("filing_timestamp") if latest_bctc else None,
            "balance_sheet": bctc_extracted.get("balance_sheet", {}),
            "income_statement": bctc_extracted.get("income_statement", {}),
            "cash_flow": bctc_extracted.get("cash_flow", {}),
            "ttm_metrics": ttm_metrics,
            "auditor_summary": bctc_extracted.get("auditor_summary", {}),
            "debt_schedule_footnotes": bctc_extracted.get("debt_schedule_footnotes", []),
            "landbank_wip_footnotes": bctc_extracted.get("landbank_wip_footnotes", []),
            "bank_npl_footnotes": bctc_extracted.get("bank_npl_footnotes", {}),
            "securities_margin_footnotes": bctc_extracted.get("securities_margin_footnotes", {}),
            "real_estate_wip_footnotes": bctc_extracted.get("real_estate_wip_footnotes", {}),
            "disclosures": disclosures_combined,
            "forensic_triangles": forensics,
            "provenance": f"SOURCE_0_GROUND_TRUTH_PDF_LAKE_{company_form}"
        }
        if cache_engine is not None:
            cache_engine.set(cache_key, res, ttl_seconds=900)
        return res
    except Exception as e:
        logger.warning(f"Could not load Source 0 data for {symbol}: {e}")
        return None

def normalize_stock_data(
    symbol: str,
    exchange: str = "HOSE",
    name: str = "",
    sector_code: str = "VNIND",
    sector_name: str = "Công Nghiệp",
    tv_data: Optional[Dict[str, Any]] = None,
    vnstock_data: Optional[Dict[str, Any]] = None,
    yf_data: Optional[Dict[str, Any]] = None,
    vndirect_data: Optional[Dict[str, Any]] = None,
    source0_data: Optional[Dict[str, Any]] = None,
    enable_source0_fallback: bool = True
) -> Dict[str, Any]:
    """
    Merges and normalizes stock metrics from multiple sources (TradingView, VNDIRECT, TCBS, Yahoo, PDF Lake)
    using the Accounting Triangles Solver with full mathematical integrity and provenance tracking.
    """
    sources_used = []
    tv = tv_data or {}
    vn = vnstock_data or {}
    yf = yf_data or {}
    vnd = vndirect_data or {}

    s0 = source0_data
    if s0 is None:
        try:
            s0 = load_source0_symbol_data(symbol)
        except Exception:
            s0 = None

        # On-demand missing data fallback (Bước 2):
        # If enabled, Source 0 is not yet cached locally, and primary sources miss critical fundamental fields,
        # trigger an on-demand download & parse of official BCTC as a high-authority ground-truth fallback.
        if enable_source0_fallback and s0 is None:
            cfo_missing = not bool(tv.get("cash_f_operating_activities_ttm") or tv.get("cash_f_operating_activities_fq") or vnd.get("cfo_ttm") or vnd.get("cfo"))
            fcf_missing = not bool(tv.get("free_cash_flow_ttm") or tv.get("free_cash_flow_fq") or (vnd.get("cfo_ttm") and vnd.get("capex_ttm")))
            eq_missing = not bool(tv.get("total_equity_fq") or vnd.get("total_equity_fq") or vn.get("equity"))
            assets_missing = not bool(tv.get("total_assets_fq") or vnd.get("total_assets_fq") or vn.get("total_assets"))

            if cfo_missing or fcf_missing or eq_missing or assets_missing:
                try:
                    from services.bctc_batch_processor import BCTCBatchProcessor
                    batch_proc = BCTCBatchProcessor()
                    res = batch_proc.process_single_company(symbol, max_reports=2)
                    if res.get("reports_processed", 0) > 0:
                        s0 = load_source0_symbol_data(symbol)
                except Exception as e:
                    logger.debug(f"On-demand Source 0 fallback fetch for {symbol} skipped: {e}")

    if s0: sources_used.append("source_0_lake")
    if tv: sources_used.append("tradingview")
    if vnd: sources_used.append("vndirect_finfo")
    if vn: sources_used.append("vnstock")
    if yf: sources_used.append("yfinance")
    if not sources_used: sources_used.append("fallback")

    resolved_name = name or tv.get("description") or f"Công ty Cổ phần {symbol}"
    resolved_ex = exchange or tv.get("exchange") or "HOSE"

    price = _safe_float(tv.get("close"), default=_safe_float(yf.get("price"), default=10000.0))
    raw_mcap = tv.get("market_cap_basic") or vn.get("market_cap") or 0.0

    # Overlay reported VNDIRECT statements onto tv data if fields missing
    if vnd:
        if not tv.get("total_revenue_ttm") and vnd.get("revenue_ttm"):
            tv["total_revenue_ttm"] = vnd["revenue_ttm"]
        if not tv.get("net_income_ttm") and vnd.get("net_income_ttm"):
            tv["net_income_ttm"] = vnd["net_income_ttm"]
        if not tv.get("ebit_ttm") and vnd.get("ebit_ttm"):
            tv["ebit_ttm"] = vnd["ebit_ttm"]
        if not tv.get("total_assets_fq") and vnd.get("total_assets_fq"):
            tv["total_assets_fq"] = vnd["total_assets_fq"]
        if not tv.get("total_equity_fq") and vnd.get("total_equity_fq"):
            tv["total_equity_fq"] = vnd["total_equity_fq"]
        if not tv.get("total_debt_fq") and vnd.get("total_debt_fq"):
            tv["total_debt_fq"] = vnd["total_debt_fq"]
        if not tv.get("free_cash_flow_ttm") and vnd.get("cfo_ttm") and vnd.get("capex_ttm"):
            tv["free_cash_flow_ttm"] = max(0.0, vnd["cfo_ttm"] - vnd["capex_ttm"])
        # Cash, operating cash flow and D&A were missing from this overlay.
        # VNDIRECT reports all three, and without them a backfilled symbol
        # still lost every cash-flow and enterprise-value model: cash gates
        # net debt, cfo gates P/CF and owner earnings, and D&A is what turns
        # a reported EBIT into EBITDA. Measured on a symbol with no
        # TradingView statements, adding them takes the overlay from 2
        # published models to a full sector house.
        if not tv.get("cash_n_short_term_invest_fq") and vnd.get("cash_fq"):
            tv["cash_n_short_term_invest_fq"] = vnd["cash_fq"]
        if not tv.get("cash_f_operating_activities_ttm") and vnd.get("cfo_ttm"):
            tv["cash_f_operating_activities_ttm"] = vnd["cfo_ttm"]
        if not tv.get("depreciation_and_amortization_ttm") and vnd.get("da_ttm"):
            tv["depreciation_and_amortization_ttm"] = vnd["da_ttm"]
        if not tv.get("capital_expenditures_ttm") and vnd.get("capex_ttm"):
            tv["capital_expenditures_ttm"] = vnd["capex_ttm"]
        if not tv.get("total_current_assets_fq") and vnd.get("total_current_assets_fq"):
            tv["total_current_assets_fq"] = vnd["total_current_assets_fq"]
        if not tv.get("total_current_liabilities_fq") and vnd.get("total_current_liabilities_fq"):
            tv["total_current_liabilities_fq"] = vnd["total_current_liabilities_fq"]

    # Solve Accounting Triangles & Missing Data Imputation with Tier 0 Arbiter
    tri = reconstruct_financial_triangles(
        symbol=symbol,
        price=price,
        raw_mcap=raw_mcap,
        sector_code=sector_code,
        tv_data=tv,
        vn_data=vn,
        yf_data=yf,
        vnd_data=vnd,
        source0_data=s0
    )

    # Attach granular VNDIRECT metrics directly to normalized record if present
    #
    # These three lines are parsed by fetch_vndirect_financials from item
    # codes 11420/12510, 112000 and 12110/12100, attached to the record here,
    # and given NO provenance tier - so the copy to the top level, which
    # admits a line only on the evidence of a tier, dropped every one of
    # them. The engine asks for them by exactly these names:
    #
    #   landbank_fq   -> res.resolve("landbank",  ("landbank_fq",))    reit_affo_dcf
    #   bank_loans_fq -> res.resolve("rwa", ("bank_loans_fq", "rwa"))  bank_equity_cash_flow
    #   gross_ppe_fq  -> res.resolve("gross_ppe", ("gross_ppe_fq", ...))
    #
    # landbank blocks 123 symbols and rwa 41. Both were reported as
    # sector-specific data no route carries, on the evidence of the blocking
    # table - which cannot tell "nobody has this" apart from "somebody has
    # this and it was never wired". A census of every company in both
    # sectors has since separated them, and the two answers are different:
    #
    #   landbank  the vendor carries it, under item codes nobody here had
    #             read correctly. See the decoding note at fetch time.
    #   rwa       the vendor does NOT carry it. 28 of the 41 companies in
    #             these sectors return roughly ten top-level aggregates and
    #             no asset-side detail at all, and no code in any of the 41
    #             payloads sits anywhere near the 60-75% of total assets a
    #             loan book occupies. Not wired, and not guessed at: the
    #             model stays refused for want of a figure that is genuinely
    #             absent, which is the correct outcome.
    #
    # Tier 3 for a line the vendor states outright. Fail-closed by
    # construction - a code the payload does not carry comes back None, is
    # not tiered, and is not published, so the model stays refused rather
    # than valuing a company on an absent land bank.
    if vnd:
        tri["capex_ttm"] = vnd.get("capex_ttm")
        # delta_working_capital was attached untiered and read straight off
        # the record by the engine as
        #   float(fundamental_data.get("delta_working_capital") or 0.0)
        # so it was never refused - it silently read as zero for every
        # company, in
        #   owners' earnings = NI + D&A - maintenance capex - dWC
        # which overstates the earnings of any company whose receivables and
        # inventory are growing. Not a refusal: a wrong number, published.
        #
        # It is computed by the vendor fetch only when at least one of the
        # three working-capital deltas is present, so a None here means the
        # payload could not support it and the engine's own zero stands - as
        # an admitted fallback rather than as a figure.
        _delta_wc = _safe_float(vnd.get("delta_working_capital"))
        if _delta_wc is not None:
            tri["delta_working_capital"] = _delta_wc
            tri["field_provenance"]["delta_working_capital"] = 3
        for _key in ("landbank_fq", "bank_loans_fq", "gross_ppe_fq"):
            _value = _safe_float(vnd.get(_key))
            if _value is not None and _value > 0:
                tri[_key] = _value
                # Tier 2, not 3, for the land bank alone. The vendor states
                # an inventory balance; reading that balance as the land
                # bank is this project's inference, sound for a developer
                # and not something the vendor asserted. Tier 2 still
                # clears the resolver's gate, so the distinction costs no
                # coverage - it records that a judgement was made here,
                # where tier 3 would claim the vendor made it.
                tri["field_provenance"][_key] = (
                    2 if _key == "landbank_fq" else 3
                )

    mcap = tri["mcap"]
    if mcap >= 30000:
        size_category = "Large-Cap"
        size_damper = 0.85
    elif mcap >= 4000:
        size_category = "Mid-Cap"
        size_damper = 0.95
    else:
        size_category = "Small-Cap"
        size_damper = 1.05

    # Propagate the imputation map under the record's own field naming
    # (record exposes "market_cap"; engine tracks it internally as "mcap").
    # Since the engine-side map became a superset (all field_provenance keys
    # incl. witnesses + all scalar keys), the propagated map covers every
    # top-level fundamental scalar AND every witness name. "market_cap" is
    # already provenance-tracked by the engine, but keep the fail-closed
    # alias as a belt-and-braces guarantee for consumers.
    is_imputed = dict(tri["is_imputed"])
    is_imputed.setdefault("market_cap", is_imputed.get("mcap", True))

    # ---------------------------------------------------------------
    # Carry the evidence to the top level.
    #
    # reconstruct_financial_triangles() publishes the absolute statement
    # lines and a tier for each. This function used to rebuild the record
    # from a hand-written list of ratio keys and bury the provenance inside
    # "_metadata", so both were dropped a second time, one layer further
    # down: ValuationEngine reads data["field_provenance"] and looks up
    # "debt"/"cash"/"ebit"/"equity" at the top level, and found neither.
    #
    # A hand-written key list is what caused this twice. Copy whatever the
    # triangles published instead, so a line added upstream arrives here on
    # its own rather than waiting to be noticed.
    # ---------------------------------------------------------------
    # The copy is mechanical now, not a list. A triangle key reaches the top
    # level when it is a number that carries a tier, and it stops there when
    # a key of the same name is already spelled out in the record below -
    # the explicit spelling always wins, so nothing here can quietly
    # redefine a field the record already publishes.
    #
    # Requiring a tier is what makes this safe rather than merely automatic.
    # An untiered value copied up would read as observed, which is the one
    # failure this whole gate exists to prevent; field_provenance membership
    # is the same admission test reconstruct_financial_triangles() already
    # applies to its own absolute lines.
    #
    # Measured against the hand-written list it replaces, this carries up
    # exactly two lines that were being dropped, both consumed by models
    # that were refusing for want of them:
    #   da              -> ebitda = ebit + da, which the engine otherwise
    #                      approximates by asserting D&A is 25% of EBIT
    #   tangible_equity -> tbvps, a declared driver of p_tbv
    #
    # _NOT_A_TOP_LEVEL_LINE is not a convenience. "mcap" is tiered and
    # numeric, so it passes every test above, and it is denominated in
    # BILLIONS while every other absolute line here is in raw VND. It
    # already reaches the record as "market_cap" (billions, for the
    # screener UI) and as "market_cap_vnd" (raw, for the engine). Letting a
    # third spelling through in a third place is how a unit error gets
    # made, so it is named and excluded here rather than left to be
    # noticed later.
    _NOT_A_TOP_LEVEL_LINE = {"mcap"}
    absolute_lines = {
        key: value
        for key, value in tri.items()
        if key not in _NOT_A_TOP_LEVEL_LINE
        and not key.startswith("_")
        and value is not None
        and not isinstance(value, bool)
        and isinstance(value, (int, float))
        and key in tri["field_provenance"]
    }

    # "market_cap" below is in BILLIONS - it is a display field, read by the
    # screener UI, and changing its unit would silently rescale the whole
    # front end. The engine works in raw VND (it derives market cap as
    # price * shares), so publish the raw figure under its own unambiguous
    # name rather than overloading one key with two units.
    market_cap_vnd = float(mcap) * 1_000_000_000.0
    # Same value, same evidence: it must carry market_cap's tier or it reads
    # as untiered and fails closed.
    tri["field_provenance"]["market_cap_vnd"] = tri["field_provenance"].get("market_cap", 0)
    is_imputed["market_cap_vnd"] = is_imputed.get("market_cap", True)

    return {
        # Absolute statement lines, raw VND, each tiered in field_provenance.
        # First, so that every explicit key below overrides it: the spread is
        # a floor of whatever the triangles published, never a replacement
        # for a field this record spells out on its own terms.
        **absolute_lines,

        "symbol": symbol,
        "name": resolved_name,
        "exchange": resolved_ex,
        "price": price,
        "change_pct": _safe_float(tv.get("change"), 0.0),
        "market_cap": mcap,
        "sector_code": sector_code,
        "sector_name": sector_name,
        "industry": sector_name,
        
        # Valuation Multiples
        "pe": tri["pe"],
        "pb": tri["pb"],
        "ps": tri["ps"],
        "peg": tri["peg"],
        "peg_sales": tri["peg_sales"],
        "eps": tri["eps"],
        "dividend_yield": tri["dividend_yield"],
        
        # Quality & Returns
        "roe": tri["roe"],
        "roa": tri["roa"],
        "gross_margin": tri["gross_margin"],
        "op_margin": tri["op_margin"],
        "net_margin": tri["net_margin"],
        "core_pat_ratio": tri["core_pat_ratio"],
        
        # Growth
        "rev_1y_growth": tri["rev_1y_growth"],
        "rev_3y_cagr": tri["rev_3y_cagr"],
        "rev_5y_growth": tri["rev_5y_growth"],
        "pat_1y_growth": tri["pat_1y_growth"],
        "pat_3y_cagr": tri["pat_3y_cagr"],
        "pat_5y_growth": tri["pat_5y_growth"],
        "eps_3y_cagr": tri["eps_3y_cagr"],
        
        # Solvency & Cashflow
        "de_ratio": tri["de_ratio"],
        "net_de_ratio": tri["net_de_ratio"],
        "current_ratio": tri["current_ratio"],
        "quick_ratio": tri["quick_ratio"],
        "interest_coverage": tri["interest_coverage"],
        "cash_to_assets": tri["cash_to_assets"],
        "rule_of_40": tri["rule_of_40"],
        "roic": tri["roic"],
        "fcf_ttm": tri["fcf_ttm"],
        "cfo_to_pat": tri["cfo_to_pat"],
        "share_dilution_3y": tri["share_dilution_3y"],
        "ebit_expansion": tri["ebit_expansion"],
        "operating_leverage": tri["operating_leverage"],
        "dilution_spread": tri["dilution_spread"],
        "is_cyclical": sector_code in ["VNMAT", "VNREAL", "VNENE"],
        "size_category": size_category,
        "size_damper": size_damper,

        "market_cap_vnd": market_cap_vnd,

        # Provenance at the top level, where every consumer reads it:
        # ValuationEngine.InputResolver, the coverage audit, and the API.
        # The copies under "_metadata" stay for backwards compatibility.
        "field_provenance": tri["field_provenance"],
        "is_imputed": is_imputed,

        "_metadata": {
            "sources_used": sources_used,
            "has_source0_lake": bool(s0),
            "forensic_triangles": s0.get("forensic_triangles") if s0 else None,
            "auditor_summary": s0.get("auditor_summary") if s0 else None,
            "debt_schedule_footnotes": s0.get("debt_schedule_footnotes") if s0 else None,
            "landbank_wip_footnotes": s0.get("landbank_wip_footnotes") if s0 else None,
            # Honest flag: only claim real data when fundamentals were valid
            # AND at least one actual source (not the pure fallback) fed it.
            "is_real_data": bool(tri["is_valid_fundamental"]) and any(s != "fallback" for s in sources_used),
            "data_quality_score": tri["data_quality_score"],
            "provenance_tier": tri["provenance_tier"],
            "is_valid_fundamental": tri["is_valid_fundamental"],
            "field_provenance": tri["field_provenance"],
            "is_imputed": is_imputed,
            "imputed_field_count": sum(1 for v in is_imputed.values() if v),
            "synced_at": datetime.datetime.now().isoformat()
        }
    }

# =============================================================================
# 5. UNIFIED MARKET UNIVERSE SYNC
# =============================================================================

#: The statement lines the valuation models need and TradingView often omits.
#: Each maps to the VNDIRECT key that normalize_stock_data() overlays.
_VND_BACKFILL_KEYS = (
    "revenue_ttm", "net_income_ttm", "ebit_ttm",
    "total_assets_fq", "total_equity_fq", "total_debt_fq",
)

#: The TradingView fields whose absence makes a symbol worth a VNDIRECT call.
#: A TradingView row missing any of these sends the symbol to VNDIRECT.
#:
#: The cash-flow pair was absent from this list for the whole life of the
#: overlay, and the audit measured what that cost: fcf blocks 306 symbols
#: and cfo 166, together the two largest remaining drivers, while the
#: VNDIRECT payload has carried cfo_ttm and capex_ttm all along. A company
#: whose TradingView row held all six income and balance lines but no cash
#: flow was never asked - the one vendor that could answer was skipped
#: because the other six questions had already been answered.
#:
#: Adding them widens the overlay towards asking every company rather than
#: only the visibly incomplete ones. That is the intended direction: a
#: second opinion on a line already held is not waste, it is the only way
#: two sources can ever disagree in front of us.
_TV_REQUIRED_LINES = (
    "total_revenue_ttm", "net_income_ttm", "ebit_ttm",
    "total_assets_fq", "total_equity_fq", "total_debt_fq",
    "cash_f_operating_activities_ttm", "capital_expenditures_ttm",
)


def recover_item_code_relations(
    by_code_rows: List[Dict[int, Optional[float]]],
    income_codes: List[int],
    min_companies: int = 200,
    max_codes: int = 24,
    max_terms: int = 6,
) -> List[Tuple[int, List[Tuple[int, float]], float, int]]:
    """Find, per item code, the codes that reproduce it arithmetically.

    VNDIRECT names none of its own item codes and the local catalogue that
    was supposed to name them holds nothing, so which line is the operating
    one cannot be looked up. It can be measured. Two codes are known good -
    the extractor reads revenue at 21001 and net income at 23000 and gets
    sensible numbers for hundreds of companies - and an income statement is
    a set of exact arithmetic relations, so the rest can be identified by
    what their values do.

    Three generations of this got here, and the first two were wrong:

    1. Four identities under one proposed reading of the numbering. Every
       one came back at 0.0%. The reading was wrong - in the log rather
       than in a published valuation, which is what stating it as something
       falsifiable was for.
    2. An exhaustive pair search, which solved much of the statement at
       100% but returned "no pair reproduces it" for the codes that matter,
       22200 among them. That is the signature of a subtotal: an operating
       line is gross profit plus financial income less financial expense,
       selling and administration, and no pair will ever reproduce five
       terms.
    3. Greedy term-by-term, which fails for a reason worth recording: a
       term that genuinely belongs can increase the residual. On a
       synthetic statement with a known five-term operating line, greedy
       gets three terms right, finds that subtracting the fourth true term
       makes the median residual worse, stops, and reports 7.3% for a
       relation that is exact. On another sample it reported 0.2%.

    Orthogonal matching pursuit re-solves the whole selected set at each
    step rather than subtracting once and moving on, so no single term has
    to justify itself alone. It recovers that same relation with
    coefficients of 1.000 and a 100% hit rate.

    A fourth correction came from the first run against real payloads
    rather than a synthetic statement: a candidate column that is
    negligible at the target's scale is dropped before selection. See the
    comment at that step - it is the difference between a search and a
    curve fit.

    Returns (target, [(code, coefficient)], hit rate as a percentage, n).
    Coefficients are returned as found: one that is not close to a whole
    number is itself the finding, because no line of a statement is 0.83 of
    another line. Nothing here is proposed and nothing is published - the
    payloads decide which codes appear and in which direction, and the
    caller prints the answer.
    """
    try:
        import numpy as np
    except Exception:  # pragma: no cover - numpy is a hard dependency of pandas
        return []

    cols = {
        c: [row.get(c) for row in by_code_rows] for c in income_codes
    }
    covered = sorted(
        (c for c in income_codes
         if sum(v is not None for v in cols[c]) >= min_companies),
        key=lambda c: -sum(v is not None for v in cols[c]),
    )[:max_codes]
    if len(covered) < 4:
        return []

    out: List[Tuple[int, List[Tuple[int, float]], float, int]] = []
    for target in covered:
        pool = [c for c in covered if c != target]
        matrix = y = None
        while len(pool) >= 3:
            m = np.array(
                [[r.get(c, np.nan) for c in pool] for r in by_code_rows],
                dtype=float,
            )
            v = np.array(
                [r.get(target, np.nan) for r in by_code_rows], dtype=float,
            )
            keep = ~np.isnan(v) & ~np.isnan(m).any(axis=1)
            if int(keep.sum()) >= min_companies:
                matrix, y = m[keep], v[keep]
                break
            # Complete cases only. A code present for a handful of
            # companies would otherwise decide which rows the whole search
            # sees, so drop the sparsest and try again.
            pool.pop()
        if matrix is None:
            continue

        # Drop candidates that are negligible at the target's scale before
        # any of them can be selected.
        #
        # This is not tidiness, it is a defect the first real run exposed.
        # 23001 is a fraction of a millionth of the statement's scale for
        # every company that reports it, and least squares handed it
        # coefficients of 724675, 893536 and -644184 across five different
        # targets. A column that small cannot explain a statement line; it
        # can only act as a free parameter with no cost, absorbing whatever
        # the real terms left over. Every relation it appeared in was noise
        # wearing the shape of an answer.
        #
        # The test is scale, not centre. A column whose *median* is zero is
        # ordinary - most companies report no other income - and 23900 is
        # median-zero while participating in two exact relations. So this
        # asks how large the column ever gets: if its 95th percentile is
        # below a ten-thousandth of the target's typical magnitude, it has
        # no accounting content at this scale and is removed from the pool
        # rather than left available to be fitted.
        scale = float(np.median(np.abs(y)))
        if scale > 0:
            big_enough = (
                np.percentile(np.abs(matrix), 95, axis=0) >= 1e-4 * scale
            )
            if 3 <= int(big_enough.sum()) < len(pool):
                pool = [c for c, k in zip(pool, big_enough) if k]
                matrix = matrix[:, big_enough]

        selected: List[int] = []
        resid = y.copy()
        for _ in range(max_terms):
            norms = np.linalg.norm(matrix, axis=0)
            norms[norms == 0] = 1.0
            score = np.abs(matrix.T @ resid) / norms
            if selected:
                score[selected] = -1.0
            selected.append(int(np.argmax(score)))
            beta, *_rest = np.linalg.lstsq(matrix[:, selected], y, rcond=None)
            resid = y - matrix[:, selected] @ beta
            if float(np.median(np.abs(resid))) <= 1e-9 * max(
                    float(np.median(np.abs(y))), 1.0):
                break
        beta, *_rest = np.linalg.lstsq(matrix[:, selected], y, rcond=None)
        terms = [
            (pool[j], float(b)) for j, b in zip(selected, beta)
            if abs(b) > 0.05
        ]
        if not terms:
            out.append((target, [], 0.0, int(len(y))))
            continue
        pred = sum(b * matrix[:, pool.index(c)] for c, b in terms)
        rate = 100.0 * float(
            np.mean(np.abs(pred - y) <= 0.01 * np.maximum(np.abs(y), 1.0))
        )
        out.append((target, terms, rate, int(len(y))))
    return out


def _has_no_ebit_rung(entry: Optional[Dict[str, Any]]) -> bool:
    """True when not one rung of the EBIT ladder can fire for this row.

    Mirrors Triangle 7.5 exactly: a reported EBIT, pretax plus interest,
    EBITDA less D&A, or revenue times a reported operating margin. A symbol
    with any of them needs no vendor call; asking anyway spends a request to
    learn nothing.
    """
    if not entry:
        return True
    if entry.get("ebit_ttm") is not None or entry.get("ebit_fq") is not None:
        return False
    if (entry.get("pretax_income_ttm") is not None
            and entry.get("interest_expense_on_debt_ttm") is not None):
        return False
    if (entry.get("ebitda_ttm") is not None
            and entry.get("depreciation_and_amortization_ttm") is not None):
        return False
    return not (entry.get("operating_margin_ttm") is not None
                or entry.get("operating_margin_fq") is not None
                or entry.get("operating_margin_fy") is not None)


#: Sectors whose valuation model needs a line TradingView has no column for
#: at all. ICB 8600 real estate is valued on its land bank and ICB 8300/8500
#: banks and insurers on their gross loans, and neither figure exists
#: anywhere in TV_COLUMNS - only VNDIRECT parses them, from item codes
#: 11420/12510 and 112000.
#:
#: The completeness test below cannot see that. It asks whether TradingView
#: filled the eight general statement lines, and for a real estate company
#: whose income statement and balance sheet are fully covered the answer is
#: yes, so the one vendor that could state its land bank is never called.
#: The company is then refused for want of a number nobody asked for.
#:
#: This is the same shape as the cash-flow pair that was missing from
#: _TV_REQUIRED_LINES: a question not asked, read downstream as an answer of
#: no. Membership here does not assert the vendor has the line - a symbol
#: whose payload lacks the item code comes back with nothing, is not tiered,
#: and stays refused.
_SECTORS_NEEDING_A_LINE_TRADINGVIEW_LACKS = frozenset({
    "VNREAL", "VNREA", "8600",          # land bank -> reit_affo_dcf, p_affo
    "VNFIN", "VNBNK", "VNINS", "8300", "8500",  # gross loans -> bank_equity_cash_flow
})


def _needs_vndirect_backfill(
    tv_entry: Optional[Dict[str, Any]],
    sector_code: Optional[str] = None,
) -> bool:
    """True when only VNDIRECT can answer something this symbol needs.

    Either TradingView left one of the general statement lines empty, or the
    symbol's sector is valued on a line TradingView does not carry at any
    level of completeness - see the frozenset above.
    """
    if sector_code and str(sector_code).strip().upper() in \
            _SECTORS_NEEDING_A_LINE_TRADINGVIEW_LACKS:
        return True
    if not tv_entry:
        return True
    return any(tv_entry.get(key) is None for key in _TV_REQUIRED_LINES)


#: The TradingView columns any one of which yields a share count. A row
#: carrying none of them sends the symbol to the fabricated 50,000,000 and
#: takes its market cap, and therefore every valuation model, to tier 0.
#: Columns that state the count outright. A market cap is deliberately not
#: among them: it is a witness only in company with a price, because the
#: rung that reads it divides one by the other.
_TV_SHARE_WITNESSES = (
    "diluted_shares_outstanding_fq",
    "total_shares_outstanding_fq",
)


def _needs_share_count(tv_entry: Optional[Dict[str, Any]]) -> bool:
    """True when TradingView gives no way to arrive at a share count."""
    if not tv_entry:
        return True
    if any(tv_entry.get(key) is not None for key in _TV_SHARE_WITNESSES):
        return False
    # A market cap pins the count only when divided by a price. Counting it
    # as a witness on its own excluded seven symbols from the vendor pass
    # that carries the number outright, and then left them at tier 0 anyway
    # because no price ever arrived. A witness that cannot testify is not
    # a witness.
    if (tv_entry.get("market_cap_basic") is not None
            and tv_entry.get("close") is not None):
        return False
    # A reported total and its per-share twin also pin the count down.
    return not (
        tv_entry.get("net_income_ttm") is not None
        and tv_entry.get("earnings_per_share_basic_ttm") is not None
    )


#: A VN listed company is worth between roughly 10 billion and 500,000
#: billion VND. Expressed in raw dong that is 1e10..5e14; expressed in
#: billions it is 10..5e5. The two ranges are five orders of magnitude
#: apart, so a market cap can be assigned to one or the other without
#: guessing - and anything landing in the gap between them is ambiguous and
#: gets dropped rather than published under a unit nobody verified. The
#: engine already carries one scar from a market cap read in the wrong
#: unit; it will not carry a second.
_MCAP_RAW_VND_FLOOR = 1e9
_MCAP_BILLIONS_CEILING = 1e7


def _market_cap_to_vnd(value: Any) -> Optional[float]:
    """Normalises a vendor market cap to raw VND, or None if ambiguous."""
    mcap = _safe_float(value)
    if mcap is None or mcap <= 0:
        return None
    if mcap >= _MCAP_RAW_VND_FLOOR:
        return mcap
    if mcap < _MCAP_BILLIONS_CEILING:
        return mcap * 1_000_000_000.0
    logger.debug("market cap %r sits between the unit ranges; discarding", value)
    return None


def sync_unified_screener_universe(master_symbols_map: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes full multi-source synchronization for all symbols in master universe.
    100% Real verified metrics, zero random numbers.
    """
    print(f"🚀 [UnifiedDataService] Initiating Multi-Source Sync for {len(master_symbols_map)} symbols...")
    start_t = time.time()

    # Form formatted tickers list (e.g. "HOSE:FPT", "HNX:PVS", "UPCOM:BSR")
    tv_tickers = []
    for sym, meta in master_symbols_map.items():
        ex = meta.get("exchange", "HOSE").upper()
        if ex in ["HOSE", "HNX", "UPCOM"]:
            tv_tickers.append(f"{ex}:{sym.upper()}")

    # Batch fetch from TradingView
    tv_batch = fetch_tradingview_batch_by_tickers(tv_tickers, chunk_size=150)
    print(f"  ✓ Fetched {len(tv_batch)} symbols directly from TradingView Scanner API")

    # Second pass for the identifiers the primary list gets wrong or omits;
    # see TRADINGVIEW_SUPPLEMENTARY_COLUMNS. Kept separate so a rejected
    # identifier costs these columns and not the universe.
    try:
        tv_extra = fetch_tradingview_batch_by_tickers(
            tv_tickers, chunk_size=150,
            columns=TRADINGVIEW_SUPPLEMENTARY_COLUMNS,
        )
    except Exception:
        logger.debug("TradingView supplementary pass failed", exc_info=True)
        tv_extra = {}
    filled = collections.Counter()
    for sym, extra in tv_extra.items():
        row = tv_batch.setdefault(sym, {})
        for key, value in extra.items():
            if key in ("symbol", "exchange") or value is None:
                continue
            row.setdefault(key, value)
            filled[key] += 1
    if tv_extra:
        print(f"  ✓ Supplementary columns for {len(tv_extra)} symbols;"
              " non-null counts:")
        for key in TRADINGVIEW_SUPPLEMENTARY_COLUMNS:
            print(f"       {key:<44} {filled.get(key, 0):>5}")
    else:
        print("  ⚠ Supplementary column pass returned nothing;"
              " the identifiers may have been rejected.")

    # -----------------------------------------------------------------
    # VNDIRECT backfill for the statement lines TradingView does not carry.
    #
    # Measured across all 1,526 listed symbols, TradingView returns a balance
    # sheet for roughly half: total_debt_fq 52.5%, ebit_ttm 47.5%,
    # capital_expenditures_ttm 44.4%. The rest have no reported lines, so the
    # provenance gate refuses to value them - correctly, because anything it
    # could produce would be a function of the price it is judging.
    #
    # normalize_stock_data() has always known how to fill those gaps from
    # VNDIRECT Finfo: it accepts vndirect_data and overlays revenue, net
    # income, EBIT, assets, equity, debt and FCF wherever TradingView is
    # silent. Nothing ever passed it. The fetch function, the overlay and the
    # tier accounting were all written and all dead.
    #
    # Only symbols actually missing a line are fetched, so a full TradingView
    # response costs nothing.
    # -----------------------------------------------------------------
    vnd_by_symbol: Dict[str, Dict[str, Any]] = {}
    needs_vnd = [
        sym.upper().strip() for sym, meta in master_symbols_map.items()
        if _needs_vndirect_backfill(
            tv_batch.get(sym.upper().strip()),
            (meta or {}).get("sector_code"),
        )
    ]
    if needs_vnd:
        print(f"  🔎 {len(needs_vnd)} symbols missing statement lines; querying VNDIRECT Finfo...")

        def _vnd_worker(sym: str):
            try:
                return sym, fetch_vndirect_financials(sym)
            except Exception:
                logger.debug("VNDIRECT backfill failed for %s", sym, exc_info=True)
                return sym, {}

        with ThreadPoolExecutor(max_workers=8) as executor:
            for fut in as_completed([executor.submit(_vnd_worker, s) for s in needs_vnd]):
                sym, payload = fut.result()
                if payload:
                    vnd_by_symbol[sym] = payload
        filled = sum(
            1 for p in vnd_by_symbol.values()
            if any(p.get(k) is not None for k in _VND_BACKFILL_KEYS)
        )
        print(f"  ✓ VNDIRECT returned statements for {filled}/{len(needs_vnd)} of them")

    # -----------------------------------------------------------------
    # TCBS for the share count TradingView and VNDIRECT both leave out.
    #
    # fetch_vnstock_financials() has always returned marketCap, pe, pb and
    # eps from the TCBS public feed, and any one of those pins the share
    # count down: market cap over price directly, or a reported total over
    # the per-share figure a multiple implies. It was wired into
    # _fallback_worker alone - the path taken only by symbols TradingView
    # omits entirely. The 565 symbols that need it are not on that path:
    # TradingView returns a row for them, near-empty but present, so they
    # go through the main loop and never reach TCBS at all. The source was
    # written, working, and connected to the one branch its users never
    # take.
    # -----------------------------------------------------------------
    tcbs_by_symbol: Dict[str, Dict[str, Any]] = {}
    needs_shares = [
        sym.upper().strip() for sym in master_symbols_map
        if _needs_share_count(tv_batch.get(sym.upper().strip()))
    ]
    # Keep the full list: the TCBS branch below empties `needs_shares` when
    # no route answers, and the Vietcap pass still has to cover every one of
    # them. Without this, a dead TCBS silently cancels its successor too.
    needs_shares_all = list(needs_shares)
    if needs_shares:
        print(f"  🔎 {len(needs_shares)} symbols have no share-count witness; probing TCBS routes...")
        tcbs_route = tcbs_probe_routes()
        if tcbs_route is None:
            print("     no TCBS route answered; skipping the fetch entirely.")
            needs_shares = []

        def _tcbs_worker(sym: str):
            try:
                return sym, fetch_vnstock_financials(sym, route=tcbs_route)
            except Exception:
                logger.debug("TCBS fetch failed for %s", sym, exc_info=True)
                return sym, {}

        # Count the two failure modes apart. "TCBS answered for 0" conflates
        # a vendor that never replied - blocked, moved, timing out, ours to
        # fix - with one that replied and had nothing, which is the vendor's
        # ceiling and sends us elsewhere. They need opposite responses, so a
        # single zero is not a measurement.
        replied = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            for fut in as_completed([executor.submit(_tcbs_worker, s) for s in needs_shares]):
                sym, payload = fut.result()
                if not payload:
                    continue
                replied += 1
                payload = dict(payload)
                payload["market_cap"] = _market_cap_to_vnd(payload.get("market_cap"))
                if any(payload.get(k) is not None
                       for k in ("shares_outstanding", "market_cap", "eps", "pe", "pb")):
                    tcbs_by_symbol[sym] = payload
        usable = sum(
            1 for p in tcbs_by_symbol.values()
            if p.get("shares_outstanding") is not None
            or p.get("market_cap") is not None
            or p.get("eps") is not None
        )
        print(f"  ✓ TCBS replied for {replied}/{len(needs_shares)};"
              f" {len(tcbs_by_symbol)} carried any field;"
              f" {usable} carried a market cap or EPS that pins the share count")
        if replied == 0 and needs_shares:
            # Nobody replied at all. That is transport, not absence: name it
            # here rather than leaving a bare zero to be misread as "the
            # vendor has no data for these symbols".
            probe = needs_shares[0]
            probe_url = f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/finance/{probe}/overview"
            try:
                resp = _HTTP_SESSION.get(probe_url, timeout=10, verify=TLS_VERIFY)
                snippet = (resp.text or "")[:200].replace("\n", " ")
                print(f"     probe {probe}: HTTP {resp.status_code} body={snippet!r}")
            except Exception as exc:
                print(f"     probe {probe}: {type(exc).__name__}: {exc}")

    # -----------------------------------------------------------------
    # Vietcap's insight service, for the share count nothing else carries.
    #
    # Every cheaper option is now measured and closed. The two listing
    # payloads that build the universe hold names, sectors and reference
    # prices only. VNDIRECT answers for 438 of these symbols and reports no
    # share count at all. All four TCBS routes return 404. TradingView
    # returns the totals - equity for 435 of them, net income for 398 - but
    # no market cap and no multiple to divide them by, which is why the
    # ladder's implied rungs cannot fire.
    #
    # This route is the one the vnstock package itself reads for company
    # details, and it is the only place seen so far that carries
    # numberOfSharesMktCap. One request per symbol, on a host we have not
    # queried before, so probe it once before spending 558 of them.
    # -----------------------------------------------------------------
    still_unpinned = [
        sym for sym in needs_shares_all
        if not tcbs_by_symbol.get(sym)
    ]
    if still_unpinned:
        print(f"  🔎 {len(still_unpinned)} symbols still unpinned; probing Vietcap IQ...")
        if not vietcap_probe():
            print("     Vietcap IQ carried no share count; skipping the fetch entirely.")
            still_unpinned = []

        def _vietcap_worker(sym: str):
            try:
                return sym, fetch_vietcap_company_details(sym)
            except Exception:
                logger.debug("Vietcap IQ fetch failed for %s", sym, exc_info=True)
                return sym, {}

        vc_replied = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_vietcap_worker, s) for s in still_unpinned]
            for fut in as_completed(futures):
                sym, payload = fut.result()
                if not payload:
                    continue
                vc_replied += 1
                payload = dict(payload)
                payload["market_cap"] = _market_cap_to_vnd(payload.get("market_cap"))
                # A payload that answered but pins nothing is not a witness;
                # storing it would make the census count it as coverage.
                if payload.get("shares_outstanding") is None and payload.get("market_cap") is None:
                    continue
                tcbs_by_symbol.setdefault(sym, {}).update(
                    {k: v for k, v in payload.items() if v is not None}
                )
        pinned = sum(
            1 for sym in still_unpinned
            if (tcbs_by_symbol.get(sym) or {}).get("shares_outstanding") is not None
        )
        print(f"  ✓ Vietcap IQ replied for {vc_replied}/{len(still_unpinned)};"
              f" {pinned} carried a share count outright")
        if pinned < len(still_unpinned):
            # Still a gap, so look at the two HTML sources before writing
            # anything against them. Four requests total, not four per
            # symbol, and no data is taken from the result - the next round
            # writes a parser against markup that has actually been read.
            probe_html_share_sources()

    # -----------------------------------------------------------------
    # The operating line, for the symbols whose ladder has no rung to
    # stand on.
    #
    # EBIT is the largest blocking driver in the universe (755 symbols) and
    # the only one the valuation engine cannot derive - the operating line
    # comes out of Triangle 7.5 or it does not exist. The census showed all
    # four of its rungs empty for those symbols: TradingView serves the EBIT
    # family to about 760 symbols and thin coverage to the rest.
    #
    # Vietcap answered for 564 of 564 when asked for share counts, and its
    # statistics-financial route carries an EBIT margin. A margin, not the
    # EBIT beside it: see _VIETCAP_EBIT_MARGIN_ALIASES for why an absolute
    # figure of unstated unit is refused. Multiplied by revenue we already
    # hold, it feeds the rung the ladder already has, which propagates
    # revenue's own tier and refuses outright where revenue is a sector
    # stand-in.
    # -----------------------------------------------------------------
    needs_margin = [
        sym.upper().strip() for sym in master_symbols_map
        # An EBIT rung is not the only thing this route answers for.
        #
        # Gating on the EBIT rung alone made the probe unreachable for every
        # company that has an operating line and no EBITDA - and Vietcap
        # reports an EBITDA for 659 of the 720 measured. ebitda blocked 134
        # symbols after the route serving it was already being called, for
        # companies it was never asked about. Same shape as the fcf gate
        # below: a question narrower than the thing it was built to fix.
        if (_has_no_ebit_rung(tv_batch.get(sym.upper().strip()))
            or _safe_float(
                (tv_batch.get(sym.upper().strip()) or {}).get("ebitda_ttm")
            ) is None)
        # Revenue from either source, because the rung multiplies the
        # margin by whatever revenue the triangle resolves - and that
        # resolution already reads the VNDIRECT overlay.
        #
        # Gating on TradingView's revenue alone made this probe unreachable
        # for exactly the companies it was built for. A company with no
        # EBIT rung is, overwhelmingly, a company TradingView carries
        # nothing for; its revenue arrives from VNDIRECT, which by this
        # point is sitting in vnd_by_symbol. The census measured what that
        # cost: Vietcap reports a non-zero EBIT margin for 615 of the 720
        # companies with no operating line, at a median of 4%, and not one
        # of them was ever asked.
        and (
            _safe_float(
                (tv_batch.get(sym.upper().strip()) or {}).get(
                    "total_revenue_ttm")
            ) is not None
            or _safe_float(
                (vnd_by_symbol.get(sym.upper().strip()) or {}).get(
                    "revenue_ttm")
            ) is not None
        )
    ]
    if needs_margin:
        print(f"  🔎 {len(needs_margin)} symbols have no EBIT rung but do have"
              " revenue; probing Vietcap statistics-financial...")
        # Two independent routes to the same number. The GraphQL one is
        # preferred: it reports EBIT and revenue side by side, so the margin
        # is computed inside a single vendor record and carries no unit
        # assumption whatsoever. statistics-financial states a margin
        # directly and stands behind it.
        use_graphql = vietcap_graphql_probe()
        use_stats = vietcap_stats_probe()
        if not (use_graphql or use_stats):
            print("     neither route yielded an EBIT margin; skipping the fetch.")
            needs_margin = []

        def _margin_worker(sym: str):
            # The reported line first, the margin only as a fallback. The
            # census settled the order: this route states ebit and ebitda
            # outright in dong for 660 and 659 of these companies. A
            # reported line is tier 3 on its own; a margin has to be
            # multiplied by revenue and can be no better than that revenue,
            # which for a sector stand-in means refused. Same request,
            # strictly better answer.
            if use_stats:
                try:
                    lines = fetch_vietcap_operating_lines(sym)
                except Exception:
                    logger.debug("Vietcap operating lines failed for %s", sym,
                                 exc_info=True)
                    lines = {}
                if lines:
                    return sym, lines
            for enabled, fetch in ((use_graphql, fetch_vietcap_ebit_margin_graphql),
                                   (use_stats, fetch_vietcap_ebit_margin)):
                if not enabled:
                    continue
                try:
                    margin = fetch(sym)
                except Exception:
                    logger.debug("Vietcap margin fetch failed for %s via %s",
                                 sym, fetch.__name__, exc_info=True)
                    continue
                if margin is not None:
                    return sym, {"margin": margin}
            return sym, None

        margin_filled = 0
        line_filled = 0
        ebitda_filled = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_margin_worker, s) for s in needs_margin]
            for fut in as_completed(futures):
                sym, answer = fut.result()
                if not answer:
                    continue
                # Written under TradingView's own column names so the ladder
                # reads them through the rungs already in place and already
                # tested, rather than through a second code path.
                row = tv_batch.setdefault(sym, {})
                # Now that this probe also serves companies that already
                # have an operating line - asked for their EBITDA - it must
                # not overwrite the line they came with.
                if "ebit" in answer and _safe_float(
                        row.get("ebit_ttm")) is None:
                    row["ebit_ttm"] = answer["ebit"]
                    line_filled += 1
                if "ebitda" in answer and _safe_float(
                        row.get("ebitda_ttm")) is None:
                    row["ebitda_ttm"] = answer["ebitda"]
                    ebitda_filled += 1
                if "margin" in answer and _safe_float(
                        row.get("operating_margin_ttm")) is None:
                    row["operating_margin_ttm"] = answer["margin"]
                    margin_filled += 1
                if "roic" in answer and _safe_float(
                        row.get("return_on_invested_capital_fq")) is None:
                    row["return_on_invested_capital_fq"] = answer["roic"]
        if needs_margin:
            print(f"  ✓ Vietcap answered for {len(needs_margin)} asked:"
                  f" {line_filled} reported an EBIT outright,"
                  f" {ebitda_filled} an EBITDA,"
                  f" {margin_filled} only a margin")

    # ROIC, on its own gate, because the existing one asks the wrong
    # question for it.
    #
    # needs_margin selects symbols with no EBIT rung. A company with a
    # perfectly good operating line and no return on capital is invisible to
    # it, and that is most of the 185 symbols roic blocks - they are tier-3
    # companies refused, or stripped of models, over one derived ratio. Four
    # of the first twenty refusals are blocked by roic alone.
    #
    # Symbols already asked above arrive here with the column filled, so
    # this gate naturally covers only the remainder.
    needs_roic = [
        sym.upper().strip() for sym in master_symbols_map
        if _safe_float(
            (tv_batch.get(sym.upper().strip()) or {}).get(
                "return_on_invested_capital_fq")
        ) is None
    ]
    if needs_roic and vietcap_stats_probe():
        print(f"  🔎 {len(needs_roic)} symbols have no ROIC; probing Vietcap"
              " statistics-financial...")

        def _roic_worker(sym: str):
            try:
                return sym, fetch_vietcap_roic(sym)
            except Exception:
                logger.debug("Vietcap roic failed for %s", sym, exc_info=True)
                return sym, None

        roic_filled = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_roic_worker, s) for s in needs_roic]
            for fut in as_completed(futures):
                sym, roic = fut.result()
                if roic is None:
                    continue
                tv_batch.setdefault(sym, {})[
                    "return_on_invested_capital_fq"] = roic
                roic_filled += 1
        print(f"  ✓ Vietcap answered a ROIC for {roic_filled} of"
              f" {len(needs_roic)} asked")

    # The income statement, asked first because it feeds the core.
    #
    # 205 symbols are refused on a tier-1 core driver - a sector median
    # standing in for a number nobody had - and that is now the largest
    # remaining pool by a distance. The census found this route answering
    # for 200 of 203 such companies with net sales, net profit, a reported
    # EPS in dong per share, and an operating profit, each under the
    # vendor's own name.
    #
    # Unlike the cash-flow pair, these are CORE drivers, so a company moved
    # here moves the tier table itself and clears eps, sps, net_margin,
    # roic and ebit together.
    #
    # Nothing already held is overwritten. A value present in tv_batch came
    # from TradingView, which is a vendor stating its own figure; replacing
    # it with a second vendor's would not raise the tier and would silently
    # decide a disagreement neither of them knows about. This fills holes
    # only.
    needs_income = [
        sym.upper().strip() for sym in master_symbols_map
        if _safe_float(
            (tv_batch.get(sym.upper().strip()) or {}).get("total_revenue_ttm")
        ) is None
        and _safe_float(
            (vnd_by_symbol.get(sym.upper().strip()) or {}).get("revenue_ttm")
        ) is None
    ]
    if needs_income and vietcap_stats_probe():
        print(f"  🔎 {len(needs_income)} symbols have no revenue from any"
              " source; probing Vietcap income-statement...")

        def _income_worker(sym: str):
            try:
                return sym, fetch_vietcap_income_statement(sym)
            except Exception:
                logger.debug("Vietcap income statement failed for %s", sym,
                             exc_info=True)
                return sym, {}

        #: answer key -> TradingView column the ladder already reads.
        _INCOME_COLUMNS = (
            ("revenue", "total_revenue_ttm"),
            ("net_income", "net_income_ttm"),
            ("eps", "earnings_per_share_basic_ttm"),
            ("ebit", "ebit_ttm"),
        )
        income_filled = {name: 0 for _, name in _INCOME_COLUMNS}
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_income_worker, s) for s in needs_income]
            for fut in as_completed(futures):
                sym, answer = fut.result()
                if not answer:
                    continue
                row = tv_batch.setdefault(sym, {})
                for key, column in _INCOME_COLUMNS:
                    if key in answer and _safe_float(row.get(column)) is None:
                        row[column] = answer[key]
                        income_filled[column] += 1
        print(f"  ✓ Vietcap income statement answered for {len(needs_income)}"
              " asked: "
              + ", ".join(f"{n} {income_filled[n]}"
                          for _, n in _INCOME_COLUMNS))

    # The cash-flow statement, asked separately and gated separately.
    #
    # Reading Vietcap's reported operating line moved ebit and ebitda off
    # the top of the blocking table and left fcf (304 symbols) and cfo (166)
    # as the two largest, with no route serving either. VNDIRECT's cash flow
    # was already wired and answers for almost none of them - widening the
    # required-lines set to include the pair moved fcf by two symbols, which
    # is what "the path works, the vendor simply has nothing" looks like.
    #
    # This is a different gate from the EBIT one on purpose. A company can
    # have a perfectly good operating line and no cash flow at all, so
    # reusing needs_margin would ask the wrong companies and skip the right
    # ones.
    # Either half missing, not just the first.
    #
    # As first written this gate asked "has no operating cash flow", and a
    # company holding a CFO but no capex was never asked - while fcf, which
    # is cfo minus capex, needs both. The gate asked a question narrower
    # than the thing it was built to fix, so fcf stayed the second-largest
    # blocker at 149 symbols after the route that answers it was wired.
    #
    # Same defect shape as the one this audit keeps finding, and this one
    # was introduced by the audit rather than found by it.
    needs_cash_flow = [
        sym.upper().strip() for sym in master_symbols_map
        if _safe_float(
            (tv_batch.get(sym.upper().strip()) or {}).get(
                "cash_f_operating_activities_ttm")
        ) is None
        or _safe_float(
            (tv_batch.get(sym.upper().strip()) or {}).get(
                "capital_expenditures_ttm")
        ) is None
    ]
    if needs_cash_flow and vietcap_stats_probe():
        print(f"  🔎 {len(needs_cash_flow)} symbols have no operating cash"
              " flow; probing Vietcap financial-statement...")

        def _cash_flow_worker(sym: str):
            try:
                return sym, fetch_vietcap_cash_flow(sym)
            except Exception:
                logger.debug("Vietcap cash flow failed for %s", sym,
                             exc_info=True)
                return sym, {}

        cfo_filled = 0
        capex_filled = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_cash_flow_worker, s)
                       for s in needs_cash_flow]
            for fut in as_completed(futures):
                sym, answer = fut.result()
                if not answer:
                    continue
                # TradingView's column names again, so the ladder reads these
                # through the rungs already in place rather than a second
                # code path. Neither is overwritten if already present: this
                # gate only fires where CFO is absent, but capex may not be.
                row = tv_batch.setdefault(sym, {})
                if "cfo" in answer and _safe_float(
                        row.get("cash_f_operating_activities_ttm")) is None:
                    row["cash_f_operating_activities_ttm"] = answer["cfo"]
                    cfo_filled += 1
                if "capex" in answer and _safe_float(
                        row.get("capital_expenditures_ttm")) is None:
                    row["capital_expenditures_ttm"] = answer["capex"]
                    capex_filled += 1
        print(f"  ✓ Vietcap cash flow answered for {len(needs_cash_flow)}"
              f" asked: {cfo_filled} an operating cash flow,"
              f" {capex_filled} a capex")

    # Cash, from the balance sheet the census finally named.
    #
    # cash is a CORE driver and blocks 150 symbols, second only to
    # dividend_per_share, and no route asked for it: the balance sheet was
    # added to the census two runs ago and deliberately left unread until the
    # vendor's own labels arrived. bsa2 "Tien va tuong duong tien" / "Cash and
    # cash equivalents" carries a figure for 71 of the 73 companies still
    # being refused.
    #
    # It is written to cash_n_cash_equivalents_fq rather than to
    # cash_n_short_term_invest_fq, which the ladder tries first. The two are
    # not the same quantity - the first column is cash, the second is cash
    # PLUS short-term investments, which this vendor states separately as
    # bsa5 - and writing a narrower figure into the wider column would report
    # a number that is quietly missing a leg. The narrow column is read as
    # the fallback it is.
    #
    # The gate asks for both columns, not one. A symbol holding the wide
    # column already has a cash figure and does not need this.
    needs_cash = [
        sym.upper().strip() for sym in master_symbols_map
        if _safe_float(
            (tv_batch.get(sym.upper().strip()) or {}).get(
                "cash_n_short_term_invest_fq")
        ) is None
        and _safe_float(
            (tv_batch.get(sym.upper().strip()) or {}).get(
                "cash_n_cash_equivalents_fq")
        ) is None
    ]
    if needs_cash and vietcap_stats_probe():
        print(f"  🔎 {len(needs_cash)} symbols have no cash figure; probing"
              " Vietcap balance-sheet...")

        def _cash_worker(sym: str):
            try:
                return sym, fetch_vietcap_balance_sheet(sym)
            except Exception:
                logger.debug("Vietcap balance sheet failed for %s", sym,
                             exc_info=True)
                return sym, {}

        cash_filled = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_cash_worker, s) for s in needs_cash]
            for fut in as_completed(futures):
                sym, answer = fut.result()
                if not answer:
                    continue
                row = tv_batch.setdefault(sym, {})
                if "cash" in answer and _safe_float(
                        row.get("cash_n_cash_equivalents_fq")) is None:
                    row["cash_n_cash_equivalents_fq"] = answer["cash"]
                    cash_filled += 1
        print(f"  ✓ Vietcap balance sheet answered for {len(needs_cash)}"
              f" asked: {cash_filled} a cash figure")

    unified_stocks = {}
    missing_symbols = []

    for sym, meta in master_symbols_map.items():
        sym_clean = sym.upper().strip()
        ex = meta.get("exchange", "HOSE").upper()
        sec_code = meta.get("sector_code", "VNIND")
        sec_name = meta.get("sector_name", "Công Nghiệp")
        name = meta.get("name") or f"Công ty Cổ phần {sym}"

        tv_entry = tv_batch.get(sym_clean)
        if tv_entry:
            unified_stock = normalize_stock_data(
                symbol=sym_clean,
                exchange=ex,
                name=name,
                sector_code=sec_code,
                sector_name=sec_name,
                tv_data=tv_entry,
                vnstock_data=tcbs_by_symbol.get(sym_clean),
                vndirect_data=vnd_by_symbol.get(sym_clean),
                enable_source0_fallback=False
            )
            unified_stocks[sym_clean] = unified_stock
        else:
            missing_symbols.append(sym_clean)

    # Fallback for missing tickers via vnstock / yfinance
    if missing_symbols:
        print(f"  ⚡ Running fallback for {len(missing_symbols)} missing symbols via vnstock / TCBS...")
        def _fallback_worker(s):
            meta = master_symbols_map.get(s, {})
            vn_data = fetch_vnstock_financials(s)
            yf_data = fetch_yfinance_financials(s) if not vn_data else {}
            # TradingView returned nothing at all for these, so they need the
            # VNDIRECT statements more than anyone.
            vnd_data = vnd_by_symbol.get(s)
            if vnd_data is None:
                try:
                    vnd_data = fetch_vndirect_financials(s)
                except Exception:
                    logger.debug("VNDIRECT fetch failed for %s", s, exc_info=True)
                    vnd_data = None
            return s, normalize_stock_data(
                symbol=s,
                exchange=meta.get("exchange", "HOSE"),
                name=meta.get("name", f"Công ty Cổ phần {s}"),
                sector_code=meta.get("sector_code", "VNIND"),
                sector_name=meta.get("sector_name", "Công Nghiệp"),
                vnstock_data=vn_data,
                yf_data=yf_data,
                vndirect_data=vnd_data,
                enable_source0_fallback=False
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_fallback_worker, s) for s in missing_symbols[:100]]
            for fut in as_completed(futures):
                s, normalized = fut.result()
                unified_stocks[s] = normalized

    # -----------------------------------------------------------------
    # Share-count census.
    #
    # A fabricated share count caps the market cap at tier 0 and every
    # valuation model with it, so this one field decides more of the
    # coverage number than any other. Three rungs were added to the ladder
    # on the strength of a guess about which TradingView columns these rows
    # carry; the coverage report did not move by a single symbol, and there
    # was no way to see why from the outside.
    #
    # So: report it. This prints what the symbols with no share witness
    # actually received, which says whether the next rung should read
    # another column, call another vendor, or whether these rows are empty
    # and no ladder will ever reach them. It changes no behaviour.
    # -----------------------------------------------------------------
    no_witness = [
        sym for sym, rec in unified_stocks.items()
        if (rec.get("field_provenance") or {}).get("shares", 0) == 0
    ]
    print(f"\n  📊 Share-count witness: {len(unified_stocks) - len(no_witness)}"
          f"/{len(unified_stocks)} symbols have one, {len(no_witness)} do not.")
    if no_witness:
        census = collections.Counter()
        for sym in no_witness:
            for key, value in (tv_batch.get(sym) or {}).items():
                if value is not None:
                    census[key] += 1
        if census:
            print(f"     TradingView columns present on those {len(no_witness)} rows:")
            for key, count in census.most_common(20):
                print(f"       {key:<40} {count:>5}")
        else:
            print("     TradingView returned empty rows for every one of them;")
            print("     the share count has to come from another vendor.")
        vnd_have = sum(1 for sym in no_witness if vnd_by_symbol.get(sym))
        print(f"     VNDIRECT statements on hand for {vnd_have} of them"
              " (VNDIRECT reports no share count).")
        tcbs_have = sum(1 for sym in no_witness if tcbs_by_symbol.get(sym))
        print(f"     TCBS or Vietcap answered for {tcbs_have} of them and still"
              " left no usable share count, market cap, EPS or multiple.")

        # The top-20 census above is ranked, so it silently hides any column
        # that falls below the cut - and the columns that matter most here
        # are exactly the rare ones. Each ladder rung needs a specific pair
        # of columns; a rung that is one column away from firing for 400
        # symbols is worth a request to a vendor, and a rung whose both
        # halves are absent is not. So name them outright rather than
        # inferring their absence from a ranking.
        def _have(*columns: str) -> int:
            return sum(
                1 for sym in no_witness
                if all((tv_batch.get(sym) or {}).get(c) is not None for c in columns)
            )

        print(f"     Ladder rungs on those {len(no_witness)} rows"
              " (each needs every column listed):")
        for label, columns in (
            ("price (every implied rung needs it)", ("close",)),
            ("reported EPS", ("net_income_ttm", "earnings_per_share_basic_ttm")),
            ("implied EPS", ("close", "net_income_ttm", "price_earnings_ttm")),
            ("implied BVPS", ("close", "total_equity_fq", "price_book_fq")),
        ):
            print(f"       {label:<40} {_have(*columns):>5}")

    # -----------------------------------------------------------------
    # EBIT ladder census.
    #
    # EBIT is now the single largest blocking driver in the universe: it
    # gates six of the 22 models, and the coverage audit reports it short
    # for 755 symbols. Unlike every other blocked driver it has no
    # derivation inside the valuation engine - the operating line either
    # comes out of the upstream ladder or it does not exist - so the whole
    # of that 755 is decided by the four rungs in Triangle 7.5.
    #
    # Which rung is failing is not inferable from the coverage report, and
    # the four call for entirely different remedies: a missing pretax or
    # interest column is a vendor request, a missing operating margin is a
    # column to add to the TradingView query, and rows where none of the
    # ingredients exist are simply empty and no ladder will reach them.
    # Guessing between those has been wrong every time it was tried, so
    # count them. This changes no behaviour.
    # -----------------------------------------------------------------
    no_ebit = [
        sym for sym, rec in unified_stocks.items()
        if "ebit" not in (rec.get("field_provenance") or {})
    ]
    print(f"\n  📊 EBIT witness: {len(unified_stocks) - len(no_ebit)}"
          f"/{len(unified_stocks)} symbols have one, {len(no_ebit)} do not.")
    if no_ebit:
        def _rung(*columns: str) -> int:
            return sum(
                1 for sym in no_ebit
                if all((tv_batch.get(sym) or {}).get(c) is not None for c in columns)
            )

        # Each rung is counted over the same alternatives Triangle 7.5
        # actually reads. The first version of this census counted the
        # "_ttm" name alone, and five of those do not exist at any company:
        # TradingView publishes OPERATING_MARGIN, INTEREST_EXPENSE_ON_DEBT
        # and CAPITAL_EXPENDITURES at FH/FQ/FY only, and
        # "depreciation_and_amortization" is not an identifier at all. So
        # the table read zero across the board and was taken as evidence
        # about the vendor's coverage, when it was evidence about the names
        # the census itself was passing.
        def _rung_any(*groups: Tuple[str, ...]) -> int:
            return sum(
                1 for sym in no_ebit
                if all(
                    any((tv_batch.get(sym) or {}).get(c) is not None for c in group)
                    for group in groups
                )
            )

        _EBIT = ("ebit_ttm", "ebit_fq")
        _OPER = ("oper_income_ttm", "oper_income_fq", "oper_income_fy")
        _PRETAX = ("pretax_income_ttm", "pretax_income_fq")
        _INT = ("interest_expense_on_debt_fq", "interest_expense_on_debt_fy",
                "interest_expense_on_debt_ttm")
        _EBITDA = ("ebitda_ttm", "ebitda_fq")
        _DA = ("dep_amort_exp_income_s_ttm", "dep_amort_exp_income_s_fq",
               "cash_flow_deprecation_n_amortization_fq")
        _OPM = ("operating_margin_fq", "operating_margin_fy",
                "operating_margin_ttm")
        _REV = ("total_revenue_ttm", "total_revenue_fq")

        print(f"     Ladder rungs on those {len(no_ebit)} rows"
              " (each counted over the names the ladder really reads):")
        for label, groups in (
            ("1. reported EBIT", (_EBIT,)),
            ("1b. operating income", (_OPER,)),
            ("2a. pretax income", (_PRETAX,)),
            ("2b. interest expense", (_INT,)),
            ("2. pretax + interest", (_PRETAX, _INT)),
            ("3a. reported EBITDA", (_EBITDA,)),
            ("3b. D&A", (_DA,)),
            ("3. EBITDA - D&A", (_EBITDA, _DA)),
            ("4a. operating margin", (_OPM,)),
            ("4. revenue x operating margin", (_REV, _OPM)),
            ("-- revenue (for reference)", (_REV,)),
            ("-- net income (for reference)", (("net_income_ttm",),)),
        ):
            print(f"       {label:<40} {_rung_any(*groups):>5}")
        vnd_ebit = sum(
            1 for sym in no_ebit
            if (vnd_by_symbol.get(sym) or {}).get("ebit_ttm") is not None
        )
        vnd_any = sum(1 for sym in no_ebit if vnd_by_symbol.get(sym))
        print(f"     VNDIRECT answered for {vnd_any} of them;"
              f" {vnd_ebit} of those carried an ebit_ttm.")
        print("     (The VNDIRECT overlay carries no pretax or interest line"
              " at all, so rung 2 is unreachable for a backfilled symbol"
              " however the vendor reports it.)")

        # VNDIRECT has the statements - it answered with revenue, net income,
        # assets and equity for these very symbols. Only the operating line
        # comes back empty, which points at the itemCodes the extractor
        # reads ([21020, 22000]) rather than at the vendor. So census the
        # codes that ARE present on the income statement, with the names the
        # itemName catalogue gives them, and let the log say outright which
        # line is EBIT, which is pretax, and which is interest expense.
        # Costs no requests: the codes come from payloads already fetched.
        code_census: "collections.Counter[int]" = collections.Counter()
        for sym in no_ebit:
            for code in (vnd_by_symbol.get(sym) or {}).get("available_item_codes", ()):
                code_census[code] += 1
        if code_census:
            # The vendor's own names, carried on the rows it sent. The
            # local catalogue is consulted only as a second opinion: nothing
            # in this repository writes data/financial_models.json and
            # data/*.json is gitignored, so it may not exist here at all.
            vendor_names: Dict[int, str] = {}
            for sym in no_ebit:
                for code, label in ((vnd_by_symbol.get(sym) or {})
                                    .get("item_code_names") or {}).items():
                    vendor_names.setdefault(int(code), label)
            try:
                from services.stock_service import _FINANCIAL_MODELS_BY_CODE
            except Exception:
                _FINANCIAL_MODELS_BY_CODE = {}
            print(f"     (vendor named {len(vendor_names)} of these codes;"
                  f" the local catalogue holds"
                  f" {len(_FINANCIAL_MODELS_BY_CODE)} definitions)")

            def _name_of(code: int) -> str:
                if code in vendor_names:
                    return vendor_names[code]
                for meta in _FINANCIAL_MODELS_BY_CODE.get(code) or []:
                    label = (meta.get("name_vn") or meta.get("name_en") or "").strip()
                    if label:
                        return label
                return "(unnamed by vendor and absent from the local catalogue)"

            # 2xxxx is the income statement in the VAS chart of accounts;
            # that is where EBIT, pretax income and interest expense live.
            income_codes = sorted(
                (c for c in code_census if 20000 <= c < 30000),
                key=lambda c: -code_census[c],
            )
            print(f"     Income-statement itemCodes present across those"
                  f" {len(no_ebit)} rows (top 30 by coverage):")
            for code in income_codes[:30]:
                marker = "  <-- read today" if code in (21020, 22000) else ""
                print(f"       {code:<8} {code_census[code]:>5}  "
                      f"{_name_of(code)[:52]}{marker}")
            if not income_codes:
                print("       none: VNDIRECT returns no income statement for"
                      " these symbols, and the operating line has to come"
                      " from somewhere else entirely.")

            # The vendor named none of its own codes, so no lookup can say
            # which line is the operating one. But two lines ARE known: the
            # extractor already reads revenue at 21001 and net income at
            # 23000 and gets sensible numbers for hundreds of companies. That
            # is enough to identify the rest arithmetically instead of by
            # guessing at a numbering scheme - which is how [21020, 22000]
            # got into the extractor in the first place, and neither code
            # exists in any payload the vendor sent.
            #
            # Two things are printed. First, each code's median value as a
            # fraction of revenue: cost of goods sits near 0.8, gross profit
            # near 0.2, the operating line between net income and gross
            # profit, and taxes are small and negative. Second, the hit rate
            # of the VAS income-statement identities under one specific
            # reading of the codes. An identity that holds for nearly every
            # company confirms every label in its chain at once; one that
            # does not, refutes the reading. Neither is a number the engine
            # can read - this block only prints.
            by_code_rows = [
                (vnd_by_symbol.get(sym) or {}).get(
                    "income_statement_ttm_by_code") or {}
                for sym in no_ebit
            ]
            by_code_rows = [r for r in by_code_rows if r]

            def _rev_of(row):
                for c in (21001, 21000, 21010):
                    v = row.get(c)
                    if v is not None and v > 0:
                        return v
                return None

            if by_code_rows:
                print("     Median value as a fraction of revenue, per code"
                      " (n = companies where both are present):")
                shape: Dict[int, List[float]] = {}
                for row in by_code_rows:
                    rev = _rev_of(row)
                    if not rev:
                        continue
                    for code, val in row.items():
                        if val is None:
                            continue
                        shape.setdefault(int(code), []).append(val / rev)
                for code in income_codes[:30]:
                    ratios = sorted(shape.get(code) or [])
                    if not ratios:
                        continue
                    med = ratios[len(ratios) // 2]
                    print(f"       {code:<8} {med:>+9.3f} x revenue"
                          f"   (n={len(ratios)})")

                # Three generations of this probe, each correcting the one
                # before.
                #
                # First it stated a reading of the numbering as four
                # identities. All four came back at 0.0%: the reading was
                # wrong, and it was wrong in the log rather than in a
                # published valuation, which is what stating it that way
                # was for.
                #
                # Then it searched pairs instead of proposing anything, and
                # that solved most of the statement outright - 21900 =
                # 22900 + 23900, 22070 = 22051 + 22052, 23003 = 23000 +
                # 23500, 23800 = 22070 + 23003, all at 100% over 520-odd
                # companies. But the codes that matter most came back
                # "no pair reproduces it", 22200 among them at 3.6%.
                #
                # That is the signature of a subtotal, not of a missing
                # code. Operating profit is gross profit plus financial
                # income less financial expense, selling and administration
                # - five terms, and no pair will ever reproduce it. So the
                # search is greedy and multi-term: start from the target,
                # repeatedly subtract or add whichever remaining code most
                # reduces the median residual, and report the expression
                # with the share of companies it reproduces to within 1%.
                #
                # It still proposes nothing. Which codes appear, and in
                # which direction, is decided by the payloads.
                cols = {
                    c: [row.get(c) for row in by_code_rows] for c in income_codes
                }
                relations = recover_item_code_relations(
                    by_code_rows, income_codes,
                )
                if not relations:
                    print("     (no arithmetic search: numpy unavailable or"
                          " too few codes carry enough companies)")
                else:
                    print("     Arithmetic relations recovered per code, by"
                          " orthogonal matching pursuit over the payloads"
                          " (nothing proposed; up to 6 terms):")
                    for target, terms, rate, n in relations:
                        if not terms:
                            print(f"       {target:<8}   nothing reproduces it")
                            continue
                        expr = " ".join(
                            (f"{'+' if b > 0 else '-'} "
                             f"{'' if abs(abs(b) - 1.0) < 0.02 else f'{abs(b):.3f}*'}"
                             f"{c}")
                            for c, b in terms
                        ).lstrip("+ ")
                        print(f"       {target:<8} = {expr}")
                        print(f"                    {rate:5.1f}%  (n={n})")

    # Compute Empirical Percentiles & rank-based quintiles via the shared
    # scoring engine (M4). Mutates each record in place with a full
    # "percentiles" block; see services/quant_scoring.py for semantics.
    score_universe(unified_stocks)

    # Sector grouping (still required by downstream sector analytics).
    sector_groups = {}
    for sym, s in unified_stocks.items():
        sec = s["sector_code"]
        if sec not in sector_groups: sector_groups[sec] = []
        sector_groups[sec].append(s)

    # Sector Analytics
    sector_analytics = {}
    for sec_code, group in sector_groups.items():
        sorted_grp = sorted(group, key=lambda x: x["percentiles"]["composite"], reverse=True)
        sec_n = len(sorted_grp)
        sector_analytics[sec_code] = {
            "code": sec_code,
            "name": sorted_grp[0]["sector_name"],
            "count": sec_n,
            "median_gross_margin": round(float(np.median([x["gross_margin"] for x in sorted_grp])), 1),
            "median_op_margin": round(float(np.median([x["op_margin"] for x in sorted_grp])), 1),
            "median_roe": round(float(np.median([x["roe"] for x in sorted_grp])), 1),
            "median_pe": round(float(np.median([x["pe"] for x in sorted_grp])), 1)
        }
        for idx, item in enumerate(sorted_grp):
            rank = idx + 1
            pct = round(((sec_n - rank) / max(1, sec_n - 1)) * 100.0, 1) if sec_n > 1 else 100.0
            item["sector_rank"] = rank
            item["sector_total"] = sec_n
            item["sector_percentile"] = pct

    # Provenance Summary Breakdown
    prov_counts = {
        "Tier 0 (Ground Truth Audited)": 0,
        "Tier 3 (Reported)": 0,
        "Tier 2 (Triangulated)": 0,
        "Tier 1 (Sector Dynamic)": 0,
        "Tier 0 (Discarded)": 0
    }
    for s in unified_stocks.values():
        t = s.get("_metadata", {}).get("provenance_tier", "")
        if "Tier 0 (Ground Truth" in t: prov_counts["Tier 0 (Ground Truth Audited)"] += 1
        elif "Tier 3" in t: prov_counts["Tier 3 (Reported)"] += 1
        elif "Tier 2" in t: prov_counts["Tier 2 (Triangulated)"] += 1
        elif "Tier 1" in t: prov_counts["Tier 1 (Sector Dynamic)"] += 1
        else: prov_counts["Tier 0 (Discarded)"] += 1

    payload = {
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_symbols": len(unified_stocks),
        "source": "Unified Multi-Source (TradingView, vnstock, yfinance)",
        "provenance_summary": prov_counts,
        "sectors": sector_analytics,
        "stocks": unified_stocks
    }

    # Atomic snapshot write (M5): dump to a .tmp sibling then os.replace()
    # so a crash mid-write can never corrupt the published cache file.
    snapshot_file = screener_snapshot_file()
    os.makedirs(os.path.dirname(snapshot_file), exist_ok=True)
    tmp_path = snapshot_file + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, snapshot_file)

    elapsed = round(time.time() - start_t, 2)
    print(f"✨ [UnifiedDataService] Successfully synced {len(unified_stocks)} stocks in {elapsed}s to {snapshot_file}")
    print(f"📊 Provenance Summary: {prov_counts}")
    return payload
