"""
=============================================================================
MODANO 3-WAY INTEGRATED MODELING ECOSYSTEM: WORKING CAPITAL & NWC ENGINE
=============================================================================
Institutional-grade Working Capital Days, Net Working Capital (NWC) Analyzer,
and Direct Method Cash Flow Integration Module.

Mathematical Foundations & Architecture:
----------------------------------------
1. Efficiency Activity Ratios:
   - Days Sales Outstanding (DSO / Debtor Days): DSO = (AR / Revenue) * 365
   - Days Inventory Outstanding (DIO / Inventory Days): DIO = (Inv / COGS) * 365
   - Days Payables Outstanding (DPO / Creditor Days): DPO = (AP / COGS) * 365
   - Cash Conversion Cycle (CCC): CCC = DSO + DIO - DPO

2. Balance Sheet NWC Aggregates:
   - Trade / Operating Working Capital: OWC = AR + Inventory - AP
   - Net Working Capital: NWC = (AR + Inventory + Other CA) - (AP + Other CL)
   - Delta NWC Invariant:
     Delta NWC_t = Delta AR_t + Delta Inv_t + Delta OCA_t - Delta AP_t - Delta OCL_t

3. Direct Method Operating Cash Flow Links:
   - Cash Receipts from Customers: Cash_cust,t = Revenue_t - Delta AR_t
   - Cash Paid to Suppliers: Cash_supp,t = COGS_t + Delta Inv_t - Delta AP_t
   - Gross Operating Cash Flow: Cash_cust,t - Cash_supp,t = Gross Profit - Delta Trade NWC

4. Zero-Division & Gating Safeguards:
   - Safe division with fallback hierarchy
   - Negative CCC retail business model acceptance (e.g. MWG)
   - Financial sector (Banking, Securities, Insurance) safe isolation (DIO=0, NWC=0)
   - Bounded days clamping [0, 1095 days] to guard against distorted micro-revenues
=============================================================================
"""

from __future__ import annotations

import re
import math
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# =============================================================================
# ARITHMETIC & SANITIZATION HELPERS
# =============================================================================

def sanitize_float(val: Any, fallback: float = 0.0) -> float:
    """
    Sanitizes arbitrary inputs (strings with commas, None, nan, inf) into safe finite floats.
    """
    if val is None:
        return fallback
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return fallback
        return float(val)
    if isinstance(val, str):
        s = val.strip().replace(",", "").replace(" ", "")
        if s in ("", "-", "--", "N/A", "null", "None", "nan", "NaN", "inf", "-inf"):
            return fallback
        try:
            f = float(s)
            return fallback if (math.isnan(f) or math.isinf(f)) else f
        except ValueError:
            return fallback
    return fallback


def safe_div(
    numerator: Union[float, int, str, None],
    denominator: Union[float, int, str, None],
    fallback: float = 0.0,
) -> float:
    """
    Safely divides numerator by denominator with strict fallback against zero, NaN, and Inf.
    """
    if numerator is None or denominator is None:
        return fallback
    try:
        if isinstance(numerator, (int, float)):
            if math.isnan(numerator) or math.isinf(numerator):
                return fallback
        if isinstance(denominator, (int, float)):
            if math.isnan(denominator) or math.isinf(denominator) or denominator == 0.0:
                return fallback
        num = sanitize_float(numerator, fallback)
        den = sanitize_float(denominator, fallback)
        if den == 0.0 or math.isnan(den) or math.isinf(den):
            return fallback
        if math.isnan(num) or math.isinf(num):
            return fallback
        res = num / den
        return fallback if (math.isnan(res) or math.isinf(res)) else res
    except Exception:
        return fallback


def clamp(
    val: Union[float, int, str, None],
    min_val: float,
    max_val: float,
) -> float:
    """
    Clamps a numeric value between min_val and max_val inclusive.
    """
    try:
        v = sanitize_float(val, min_val)
        if math.isnan(v) or math.isinf(v):
            return min_val
        return max(min_val, min(max_val, v))
    except Exception:
        return min_val


# =============================================================================
# SECTOR WORKING CAPITAL PRIORS & BENCHMARKS
# =============================================================================

# Calibrated sector benchmarks for Vietnamese ICB sectors (HOSE/HNX audited filings)
SECTOR_WC_PRIORS: Dict[str, Dict[str, Any]] = {
    # Consumer Staples (FMCG, Food & Beverage, Agriculture)
    "VNCONS": {"dso": 30.0, "dio": 65.0, "dpo": 45.0, "ccc": 50.0, "oca_pct": 0.05, "ocl_pct": 0.08, "is_financial": False, "name": "Consumer Staples"},
    "3000":   {"dso": 30.0, "dio": 65.0, "dpo": 45.0, "ccc": 50.0, "oca_pct": 0.05, "ocl_pct": 0.08, "is_financial": False, "name": "Consumer Staples"},
    "3500":   {"dso": 30.0, "dio": 65.0, "dpo": 45.0, "ccc": 50.0, "oca_pct": 0.05, "ocl_pct": 0.08, "is_financial": False, "name": "Food & Beverage"},
    "VNFOB":  {"dso": 30.0, "dio": 65.0, "dpo": 45.0, "ccc": 50.0, "oca_pct": 0.05, "ocl_pct": 0.08, "is_financial": False, "name": "Food & Beverage"},
    "STAPLES":{"dso": 30.0, "dio": 65.0, "dpo": 45.0, "ccc": 50.0, "oca_pct": 0.05, "ocl_pct": 0.08, "is_financial": False, "name": "Consumer Staples"},

    # Consumer Discretionary & Retail
    "VNCOND": {"dso": 20.0, "dio": 70.0, "dpo": 55.0, "ccc": 35.0, "oca_pct": 0.04, "ocl_pct": 0.07, "is_financial": False, "name": "Consumer Discretionary"},
    "5000":   {"dso": 20.0, "dio": 70.0, "dpo": 55.0, "ccc": 35.0, "oca_pct": 0.04, "ocl_pct": 0.07, "is_financial": False, "name": "Consumer Discretionary"},
    "3300":   {"dso": 20.0, "dio": 70.0, "dpo": 55.0, "ccc": 35.0, "oca_pct": 0.04, "ocl_pct": 0.07, "is_financial": False, "name": "Automobiles & Parts"},
    "3700":   {"dso": 20.0, "dio": 70.0, "dpo": 55.0, "ccc": 35.0, "oca_pct": 0.04, "ocl_pct": 0.07, "is_financial": False, "name": "Personal & Household Goods"},
    "5300":   {"dso": 15.0, "dio": 85.0, "dpo": 60.0, "ccc": 40.0, "oca_pct": 0.04, "ocl_pct": 0.07, "is_financial": False, "name": "Retail"},
    "RETAIL": {"dso": 15.0, "dio": 85.0, "dpo": 60.0, "ccc": 40.0, "oca_pct": 0.04, "ocl_pct": 0.07, "is_financial": False, "name": "Retail"},
    "DISCRETIONARY": {"dso": 20.0, "dio": 70.0, "dpo": 55.0, "ccc": 35.0, "oca_pct": 0.04, "ocl_pct": 0.07, "is_financial": False, "name": "Consumer Discretionary"},

    # Basic Materials & Steel
    "VNMAT":    {"dso": 25.0, "dio": 95.0, "dpo": 45.0, "ccc": 75.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Basic Materials"},
    "1700":     {"dso": 25.0, "dio": 95.0, "dpo": 45.0, "ccc": 75.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Basic Materials"},
    "1300":     {"dso": 25.0, "dio": 95.0, "dpo": 45.0, "ccc": 75.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Chemicals"},
    "MATERIAL": {"dso": 25.0, "dio": 95.0, "dpo": 45.0, "ccc": 75.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Basic Materials"},
    "MATERIALS":{"dso": 25.0, "dio": 95.0, "dpo": 45.0, "ccc": 75.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Basic Materials"},

    # Industrials & Capital Goods / Construction
    "VNIND":       {"dso": 65.0, "dio": 75.0, "dpo": 50.0, "ccc": 90.0, "oca_pct": 0.08, "ocl_pct": 0.10, "is_financial": False, "name": "Industrials"},
    "2700":        {"dso": 65.0, "dio": 75.0, "dpo": 50.0, "ccc": 90.0, "oca_pct": 0.08, "ocl_pct": 0.10, "is_financial": False, "name": "Industrials"},
    "2300":        {"dso": 65.0, "dio": 75.0, "dpo": 50.0, "ccc": 90.0, "oca_pct": 0.08, "ocl_pct": 0.10, "is_financial": False, "name": "Construction & Materials"},
    "INDUSTRIAL":  {"dso": 65.0, "dio": 75.0, "dpo": 50.0, "ccc": 90.0, "oca_pct": 0.08, "ocl_pct": 0.10, "is_financial": False, "name": "Industrials"},
    "INDUSTRIALS": {"dso": 65.0, "dio": 75.0, "dpo": 50.0, "ccc": 90.0, "oca_pct": 0.08, "ocl_pct": 0.10, "is_financial": False, "name": "Industrials"},

    # Technology & Telecom
    "VNIT":   {"dso": 70.0, "dio": 15.0, "dpo": 45.0, "ccc": 40.0, "oca_pct": 0.07, "ocl_pct": 0.09, "is_financial": False, "name": "Technology"},
    "VNTECH": {"dso": 70.0, "dio": 15.0, "dpo": 45.0, "ccc": 40.0, "oca_pct": 0.07, "ocl_pct": 0.09, "is_financial": False, "name": "Technology"},
    "VNTEC":  {"dso": 70.0, "dio": 15.0, "dpo": 45.0, "ccc": 40.0, "oca_pct": 0.07, "ocl_pct": 0.09, "is_financial": False, "name": "Technology"},
    "9500":   {"dso": 70.0, "dio": 15.0, "dpo": 45.0, "ccc": 40.0, "oca_pct": 0.07, "ocl_pct": 0.09, "is_financial": False, "name": "Technology"},
    "6500":   {"dso": 70.0, "dio": 15.0, "dpo": 45.0, "ccc": 40.0, "oca_pct": 0.07, "ocl_pct": 0.09, "is_financial": False, "name": "Telecommunications"},
    "TECH":   {"dso": 70.0, "dio": 15.0, "dpo": 45.0, "ccc": 40.0, "oca_pct": 0.07, "ocl_pct": 0.09, "is_financial": False, "name": "Technology"},
    "IT":     {"dso": 70.0, "dio": 15.0, "dpo": 45.0, "ccc": 40.0, "oca_pct": 0.07, "ocl_pct": 0.09, "is_financial": False, "name": "Technology"},

    # Real Estate Developers & Land Banks
    "VNREAL": {"dso": 90.0, "dio": 365.0, "dpo": 60.0, "ccc": 395.0, "oca_pct": 0.12, "ocl_pct": 0.18, "is_financial": False, "name": "Real Estate"},
    "VNREA":  {"dso": 90.0, "dio": 365.0, "dpo": 60.0, "ccc": 395.0, "oca_pct": 0.12, "ocl_pct": 0.18, "is_financial": False, "name": "Real Estate"},
    "8600":   {"dso": 90.0, "dio": 365.0, "dpo": 60.0, "ccc": 395.0, "oca_pct": 0.12, "ocl_pct": 0.18, "is_financial": False, "name": "Real Estate"},
    "REAL":   {"dso": 90.0, "dio": 365.0, "dpo": 60.0, "ccc": 395.0, "oca_pct": 0.12, "ocl_pct": 0.18, "is_financial": False, "name": "Real Estate"},

    # Energy & Oil/Gas
    "VNENE":  {"dso": 35.0, "dio": 30.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.05, "ocl_pct": 0.06, "is_financial": False, "name": "Energy"},
    "VNENG":  {"dso": 35.0, "dio": 30.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.05, "ocl_pct": 0.06, "is_financial": False, "name": "Energy"},
    "0500":   {"dso": 35.0, "dio": 30.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.05, "ocl_pct": 0.06, "is_financial": False, "name": "Oil & Gas"},
    "ENERGY": {"dso": 35.0, "dio": 30.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.05, "ocl_pct": 0.06, "is_financial": False, "name": "Energy"},

    # Utilities (Electricity, Gas Distribution, Water)
    "VNUTI":     {"dso": 45.0, "dio": 20.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.04, "ocl_pct": 0.05, "is_financial": False, "name": "Utilities"},
    "7000":      {"dso": 45.0, "dio": 20.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.04, "ocl_pct": 0.05, "is_financial": False, "name": "Utilities"},
    "7500":      {"dso": 45.0, "dio": 20.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.04, "ocl_pct": 0.05, "is_financial": False, "name": "Utilities"},
    "UTILITY":   {"dso": 45.0, "dio": 20.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.04, "ocl_pct": 0.05, "is_financial": False, "name": "Utilities"},
    "UTILITIES": {"dso": 45.0, "dio": 20.0, "dpo": 40.0, "ccc": 25.0, "oca_pct": 0.04, "ocl_pct": 0.05, "is_financial": False, "name": "Utilities"},

    # Healthcare & Pharmaceuticals
    "VNHEAL": {"dso": 60.0, "dio": 90.0, "dpo": 45.0, "ccc": 105.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Healthcare"},
    "VNHEA":  {"dso": 60.0, "dio": 90.0, "dpo": 45.0, "ccc": 105.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Healthcare"},
    "4500":   {"dso": 60.0, "dio": 90.0, "dpo": 45.0, "ccc": 105.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Healthcare"},
    "HEALTH": {"dso": 60.0, "dio": 90.0, "dpo": 45.0, "ccc": 105.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Healthcare"},
    "PHARMA": {"dso": 60.0, "dio": 90.0, "dpo": 45.0, "ccc": 105.0, "oca_pct": 0.06, "ocl_pct": 0.06, "is_financial": False, "name": "Pharmaceuticals"},

    # Financials (Banks, Insurance, Securities) - Gated
    "VNFIN": {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Financials"},
    "VNBNK": {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Banking"},
    "VNSEC": {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Securities"},
    "VNINS": {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Insurance"},
    "FIN":   {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Financials"},
    "BANK":  {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Banking"},
    "8300":  {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Banks"},
    "8500":  {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Insurance"},
    "8700":  {"dso": 0.0, "dio": 0.0, "dpo": 0.0, "ccc": 0.0, "oca_pct": 0.00, "ocl_pct": 0.00, "is_financial": True, "name": "Financial Services / Securities"},

    # Global Safe Fallback
    "DEFAULT": {"dso": 45.0, "dio": 60.0, "dpo": 40.0, "ccc": 65.0, "oca_pct": 0.05, "ocl_pct": 0.07, "is_financial": False, "name": "General"},
}

# Aliases for backward/forward compatibility
SECTOR_PRIORS: Dict[str, Dict[str, Any]] = SECTOR_WC_PRIORS
SECTOR_BENCHMARKS: Dict[str, Dict[str, Any]] = SECTOR_WC_PRIORS


# Comprehensive 42+ Vietnamese Financial Sector Tickers (Banks, Securities, Insurance)
FINANCIAL_SYMBOLS = {
    # 27 Commercial Banks (ICB 8300 / VNBNK)
    "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "HDB", "STB", "VIB",
    "TPB", "SHB", "LPB", "MSB", "OCB", "SSB", "EIB", "BAB", "BVB", "KLB",
    "NAB", "NVB", "PGB", "SGB", "VAB", "VBB", "ABB",
    # 25 Securities Brokerages (ICB 8700 / VNSEC)
    "SSI", "VND", "VCI", "HCM", "SHS", "MBS", "FTS", "BSI", "CTS", "AGR",
    "VDS", "ORS", "TVS", "VIX", "IVS", "BVS", "PSI", "WSS", "APG", "TCI",
    "SBS", "HBS", "EVS", "DSC", "VFS",
    # 11 Insurance Companies (ICB 8500 / VNINS)
    "BVH", "PVI", "BMI", "BIC", "MIG", "PRE", "PTI", "VNR", "ABI", "BLI", "AIC"
}


def resolve_sector_prior(
    sector: Optional[str] = "DEFAULT",
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolves sector string, numeric code, symbol, or alias to corresponding prior benchmark dict.
    Automatically isolates financial institutions (42+ banks, insurers, brokerages).
    """
    if symbol:
        sym_clean = str(symbol).strip().upper()
        if sym_clean in FINANCIAL_SYMBOLS:
            return SECTOR_WC_PRIORS["VNFIN"]

    if not sector:
        return SECTOR_WC_PRIORS["DEFAULT"]
    
    clean_sec = str(sector).strip().upper()
    if clean_sec in FINANCIAL_SYMBOLS:
        return SECTOR_WC_PRIORS["VNFIN"]

    if clean_sec in SECTOR_WC_PRIORS:
        return SECTOR_WC_PRIORS[clean_sec]

    tokens = set(re.split(r'[^A-Z0-9]+', clean_sec))
    
    # Financials (Banks, Insurance, Securities)
    if tokens & (FINANCIAL_SYMBOLS | {"VNFIN", "FIN", "FINANCE", "FINANCIAL", "FINANCIALS", "BANK", "BANKS", "BANKING", "VNBNK", "BNK", "VNSEC", "SECURITIES", "VNINS", "INSURANCE", "INS", "8300", "8500", "8700"}):
        return SECTOR_WC_PRIORS["VNFIN"]
    if any(k in clean_sec for k in ("BANK", "BNK", "SECURITIES", "INSUR", "FINANC")):
        return SECTOR_WC_PRIORS["VNFIN"]
        
    # Technology
    if tokens & {"VNIT", "IT", "TECH", "TECHNOLOGY", "VNTECH", "VNTEC", "TELECOM", "9500", "6500"}:
        return SECTOR_WC_PRIORS["VNIT"]
    if any(k in clean_sec for k in ("TECH", "TELECOM")):
        return SECTOR_WC_PRIORS["VNIT"]

    # Real Estate
    if tokens & {"VNREAL", "REAL", "REALTY", "ESTATE", "LAND", "VNREA", "8600"}:
        return SECTOR_WC_PRIORS["VNREAL"]
    if any(k in clean_sec for k in ("REAL", "ESTATE", "LAND")):
        return SECTOR_WC_PRIORS["VNREAL"]

    # Basic Materials
    if tokens & {"VNMAT", "MATERIAL", "MATERIALS", "STEEL", "CHEMICALS", "CHEM", "1700", "1300"}:
        return SECTOR_WC_PRIORS["VNMAT"]
    if any(k in clean_sec for k in ("STEEL", "MATER", "CHEM")):
        return SECTOR_WC_PRIORS["VNMAT"]

    # Industrials & Construction
    if tokens & {"VNIND", "IND", "INDUSTRIAL", "INDUSTRIALS", "CONST", "CONSTRUCTION", "BUILD", "2700", "2300"}:
        return SECTOR_WC_PRIORS["VNIND"]
    if any(k in clean_sec for k in ("CONST", "INDUS", "BUILD")):
        return SECTOR_WC_PRIORS["VNIND"]

    # Consumer Staples
    if tokens & {"VNCONS", "CONS", "STAPLES", "FOOD", "BEV", "BEVERAGE", "VNFOB", "FOB", "3000", "3500"}:
        return SECTOR_WC_PRIORS["VNCONS"]
    if any(k in clean_sec for k in ("STAPLE", "FOOD", "BEVERAG")):
        return SECTOR_WC_PRIORS["VNCONS"]

    # Consumer Discretionary & Retail
    if tokens & {"VNCOND", "COND", "DISCRETIONARY", "RETAIL", "AUTO", "5000", "5300", "3300", "3700"}:
        return SECTOR_WC_PRIORS["VNCOND"]
    if any(k in clean_sec for k in ("RETAIL", "DISCRET")):
        return SECTOR_WC_PRIORS["VNCOND"]

    # Energy
    if tokens & {"VNENE", "ENE", "ENERGY", "OIL", "GAS", "VNENG", "0500"}:
        return SECTOR_WC_PRIORS["VNENE"]
    if any(k in clean_sec for k in ("ENERGY", "OIL")):
        return SECTOR_WC_PRIORS["VNENE"]

    # Utilities
    if tokens & {"VNUTI", "UTI", "UTILITY", "UTILITIES", "POWER", "WATER", "7000", "7500"}:
        return SECTOR_WC_PRIORS["VNUTI"]
    if any(k in clean_sec for k in ("UTILIT", "POWER", "WATER")):
        return SECTOR_WC_PRIORS["VNUTI"]

    # Healthcare
    if tokens & {"VNHEAL", "HEAL", "HEALTH", "HEALTHCARE", "PHARMA", "PHARMACEUTICAL", "VNHEA", "4500"}:
        return SECTOR_WC_PRIORS["VNHEAL"]
    if any(k in clean_sec for k in ("HEALTH", "PHARMA")):
        return SECTOR_WC_PRIORS["VNHEAL"]

    return SECTOR_WC_PRIORS["DEFAULT"]


# =============================================================================
# PYDANTIC DATA MODELS (Pydantic v1 & v2 Compatible)
# =============================================================================

class WorkingCapitalMetrics(BaseModel):
    """
    Snapshot of working capital efficiency days and balance sheet values for a single period.
    """
    dso: float = Field(..., description="Days Sales Outstanding (Debtor Days)")
    dio: float = Field(..., description="Days Inventory Outstanding (Inventory Days)")
    dpo: float = Field(..., description="Days Payables Outstanding (Creditor Days)")
    ccc: float = Field(..., description="Cash Conversion Cycle (DSO + DIO - DPO)")
    revenue: float = Field(default=0.0, description="Gross Turnover / Net Sales")
    cogs: float = Field(default=0.0, description="Cost of Goods Sold")
    sga: float = Field(default=0.0, description="SG&A Operating Expenses")
    accounts_receivable: float = Field(default=0.0, description="Trade Accounts Receivable")
    inventory: float = Field(default=0.0, description="Inventories")
    accounts_payable: float = Field(default=0.0, description="Trade Accounts Payable")
    other_current_assets: float = Field(default=0.0, description="Other Current Operating Assets")
    other_current_liabilities: float = Field(default=0.0, description="Other Current Operating Liabilities")
    trade_nwc: float = Field(default=0.0, description="Trade Net Working Capital (AR + Inv - AP)")
    trade_working_capital: float = Field(default=0.0, description="Trade Working Capital (AR + Inv - AP)")
    operating_working_capital: float = Field(default=0.0, description="Operating Working Capital (AR + Inv - AP)")
    net_working_capital: float = Field(default=0.0, description="Total Operating Net Working Capital")
    total_operating_nwc: float = Field(default=0.0, description="Total Operating Net Working Capital")
    delta_nwc: float = Field(default=0.0, description="Period Change in Net Working Capital")
    delta_trade_nwc: float = Field(default=0.0, description="Period Change in Trade NWC")
    delta_total_nwc: float = Field(default=0.0, description="Period Change in Total Operating NWC")
    delta_ar: float = Field(default=0.0, description="Period Change in AR")
    delta_inv: float = Field(default=0.0, description="Period Change in Inventory")
    delta_inventory: float = Field(default=0.0, description="Period Change in Inventory (alias)")
    delta_ap: float = Field(default=0.0, description="Period Change in AP")
    delta_oca: float = Field(default=0.0, description="Period Change in Other Current Assets")
    delta_ocl: float = Field(default=0.0, description="Period Change in Other Current Liabilities")
    is_financial_sector: bool = Field(default=False, description="True if financial institution")
    period: str = Field(default="T", description="Period Identifier")
    cash_collected_from_customers: float = Field(default=0.0, description="Direct Cash Collected (Rev - Delta AR)")
    cash_receipts_customers: float = Field(default=0.0, description="Direct Cash Receipts (Rev - Delta AR)")
    cash_from_customers: float = Field(default=0.0, description="Direct Cash Receipts (Rev - Delta AR)")
    cash_from_customers_adjustment: float = Field(default=0.0, description="Direct Cash Receipts (Rev - Delta AR)")
    cash_receipts_from_customers: float = Field(default=0.0, description="Direct Cash Receipts (Rev - Delta AR)")
    cash_paid_to_suppliers: float = Field(default=0.0, description="Direct Cash Paid to Suppliers (COGS + Delta Inv - Delta AP)")
    cash_paid_suppliers: float = Field(default=0.0, description="Direct Cash Paid to Suppliers")
    cash_to_suppliers: float = Field(default=0.0, description="Direct Cash Paid to Suppliers")
    cash_to_suppliers_adjustment: float = Field(default=0.0, description="Direct Cash Paid to Suppliers")
    cash_paid_for_opex: float = Field(default=0.0, description="Direct Cash Paid for OPEX (SGA + Delta OCA - Delta OCL)")
    cash_paid_opex: float = Field(default=0.0, description="Direct Cash Paid for OPEX")
    cash_for_opex: float = Field(default=0.0, description="Direct Cash Paid for OPEX")

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model to dictionary with v1/v2 compatibility."""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


class WorkingCapitalSchedulePeriod(BaseModel):
    """
    Single forecast period in the 5-year working capital forecast schedule.
    """
    year: int = Field(default=0, description="Forecast Period / Year (e.g. 2026)")
    year_index: int = Field(default=1, description="1-based period index")
    revenue: float = Field(default=0.0, description="Period Forecast Revenue")
    cogs: float = Field(default=0.0, description="Period Forecast COGS")
    sga: float = Field(default=0.0, description="Period Forecast SG&A Expense")
    dso: float = Field(default=0.0, description="Projected Debtor Days (DSO)")
    dio: float = Field(default=0.0, description="Projected Inventory Days (DIO)")
    dpo: float = Field(default=0.0, description="Projected Creditor Days (DPO)")
    ccc: float = Field(default=0.0, description="Projected Cash Conversion Cycle (CCC)")
    accounts_receivable: float = Field(default=0.0, description="Ending Accounts Receivable (BS Asset)")
    inventory: float = Field(default=0.0, description="Ending Inventory (BS Asset)")
    accounts_payable: float = Field(default=0.0, description="Ending Accounts Payable (BS Liability)")
    other_current_assets: float = Field(default=0.0, description="Ending Other Current Assets (BS Asset)")
    other_current_liabilities: float = Field(default=0.0, description="Ending Other Current Liabilities (BS Liability)")
    trade_working_capital: float = Field(default=0.0, description="Ending Trade Working Capital (AR + Inv - AP)")
    operating_working_capital: float = Field(default=0.0, description="Ending Operating Working Capital (AR + Inv - AP)")
    trade_nwc: float = Field(default=0.0, description="Ending Trade NWC")
    net_working_capital: float = Field(default=0.0, description="Ending Net Working Capital")
    total_operating_nwc: float = Field(default=0.0, description="Ending Total Operating Net Working Capital")
    delta_ar: float = Field(default=0.0, description="AR Change vs Prior Period (AR_t - AR_{t-1})")
    delta_inventory: float = Field(default=0.0, description="Inventory Change vs Prior Period")
    delta_inv: float = Field(default=0.0, description="Inventory Change vs Prior Period (alias)")
    delta_ap: float = Field(default=0.0, description="AP Change vs Prior Period (AP_t - AP_{t-1})")
    delta_oca: float = Field(default=0.0, description="OCA Change vs Prior Period")
    delta_ocl: float = Field(default=0.0, description="OCL Change vs Prior Period")
    delta_trade_nwc: float = Field(default=0.0, description="Trade NWC Change vs Prior Period")
    delta_total_nwc: float = Field(default=0.0, description="Total Operating NWC Change vs Prior Period")
    delta_nwc: float = Field(default=0.0, description="Net Working Capital Change (NWC_t - NWC_{t-1})")
    cash_collected_from_customers: float = Field(default=0.0, description="Direct Cash Collected (Rev - Delta AR)")
    cash_from_customers: float = Field(default=0.0, description="Direct Cash Collected (Rev - Delta AR)")
    cash_from_customers_adjustment: float = Field(default=0.0, description="Direct Cash Collected (Rev - Delta AR)")
    cash_receipts_from_customers: float = Field(default=0.0, description="Direct Cash Collected (Rev - Delta AR)")
    cash_receipts_customers: float = Field(default=0.0, description="Direct Cash Collected (Rev - Delta AR)")
    cash_paid_to_suppliers: float = Field(default=0.0, description="Direct Cash Paid Suppliers (COGS + Delta Inv - Delta AP)")
    cash_to_suppliers: float = Field(default=0.0, description="Direct Cash Paid Suppliers")
    cash_to_suppliers_adjustment: float = Field(default=0.0, description="Direct Cash Paid Suppliers")
    cash_paid_suppliers: float = Field(default=0.0, description="Direct Cash Paid Suppliers")
    cash_paid_for_opex: float = Field(default=0.0, description="Direct Cash Paid for OPEX (SGA + Delta OCA - Delta OCL)")
    cash_paid_opex: float = Field(default=0.0, description="Direct Cash Paid for OPEX")
    cash_for_opex: float = Field(default=0.0, description="Direct Cash Paid for OPEX")
    is_financial_sector: bool = Field(default=False, description="Whether ticker is a financial institution")

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model to dictionary with v1/v2 compatibility."""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


class WorkingCapitalForecastResult(BaseModel):
    """
    Complete multi-year Working Capital forecast result payload.
    """
    symbol: str = Field(..., description="Stock Symbol")
    sector: str = Field(..., description="Sector Code")
    base_metrics: WorkingCapitalMetrics = Field(..., description="Base historical metrics")
    schedule: List[WorkingCapitalSchedulePeriod] = Field(..., description="5-Year working capital forecast schedule")
    summary: Dict[str, Any] = Field(default_factory=dict, description="Summary stats and metrics")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model to dictionary with v1/v2 compatibility."""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


# =============================================================================
# WORKING CAPITAL ENGINE IMPLEMENTATION
# =============================================================================

class WorkingCapitalEngine:
    """
    Modano-Compliant Working Capital Days & NWC Schedule Analyzer.
    Provides mathematical rigor, direct cash flow adjustments, and zero-crash safeguards.
    """

    # Expose sector benchmark dictionaries as class attributes
    SECTOR_BENCHMARKS = SECTOR_WC_PRIORS
    SECTOR_PRIORS = SECTOR_WC_PRIORS

    @staticmethod
    def calculate_historical_days(
        rev: Union[float, int, str, None],
        cogs: Union[float, int, str, None],
        ar: Union[float, int, str, None],
        inv: Union[float, int, str, None],
        ap: Union[float, int, str, None],
        other_ca: Union[float, int, str, None] = 0.0,
        other_cl: Union[float, int, str, None] = 0.0,
        sga: Union[float, int, str, None] = 0.0,
        sector: str = "DEFAULT",
        days_in_period: int = 365,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates historical efficiency days (DSO, DIO, DPO, CCC) and Net Working Capital (NWC)
        with strict zero-division safeguards, financial sector isolation, and data sanitization.
        """
        sec_info = resolve_sector_prior(sector, symbol=symbol)
        is_financial = sec_info.get("is_financial", False)

        r = sanitize_float(rev, 0.0)
        c = sanitize_float(cogs, 0.0)
        s = sanitize_float(sga, 0.0)
        raw_ar = sanitize_float(ar, 0.0)
        raw_inv = sanitize_float(inv, 0.0)
        raw_ap = sanitize_float(ap, 0.0)
        raw_oca = sanitize_float(other_ca, 0.0)
        raw_ocl = sanitize_float(other_cl, 0.0)

        # Financial Sector Gating (Banks, Insurance, Securities)
        if is_financial:
            return {
                "dso": 0.0,
                "dio": 0.0,
                "dpo": 0.0,
                "ccc": 0.0,
                "revenue": r,
                "cogs": c,
                "sga": s,
                "accounts_receivable": max(0.0, raw_ar),
                "inventory": 0.0,
                "accounts_payable": max(0.0, raw_ap),
                "other_current_assets": max(0.0, raw_oca),
                "other_current_liabilities": max(0.0, raw_ocl),
                "trade_working_capital": 0.0,
                "trade_nwc": 0.0,
                "operating_working_capital": 0.0,
                "net_working_capital": 0.0,
                "total_operating_nwc": 0.0,
                "delta_nwc": 0.0,
                "delta_trade_nwc": 0.0,
                "delta_total_nwc": 0.0,
                "delta_ar": 0.0,
                "delta_inv": 0.0,
                "delta_inventory": 0.0,
                "delta_ap": 0.0,
                "delta_oca": 0.0,
                "delta_ocl": 0.0,
                "is_financial_sector": True,
                "cash_collected_from_customers": r,
                "cash_receipts_customers": r,
                "cash_from_customers": r,
                "cash_from_customers_adjustment": r,
                "cash_receipts_from_customers": r,
                "cash_paid_to_suppliers": c,
                "cash_paid_suppliers": c,
                "cash_to_suppliers": c,
                "cash_to_suppliers_adjustment": c,
                "cash_paid_for_opex": s,
                "cash_paid_opex": s,
                "cash_for_opex": s,
            }

        # Non-Financial Calculations
        # Sanitize negative asset/liability records before computing days
        clean_ar = max(0.0, raw_ar)
        clean_inv = max(0.0, raw_inv)
        clean_ap = max(0.0, raw_ap)
        clean_oca = max(0.0, raw_oca)
        clean_ocl = max(0.0, raw_ocl)

        # 1. DSO Calculation
        if r <= 0.0 or raw_ar < 0.0:
            dso = sec_info["dso"]
        else:
            dso = safe_div(clean_ar * days_in_period, r, fallback=sec_info["dso"])

        # 2. DIO Calculation
        if c <= 0.0 or raw_inv < 0.0:
            # If inventory is 0 and cogs is 0, startup/service firm
            if clean_inv == 0.0 and c == 0.0:
                dio = 0.0 if sec_info["dio"] == 0.0 else sec_info["dio"]
            else:
                dio = sec_info["dio"]
        else:
            dio = safe_div(clean_inv * days_in_period, c, fallback=sec_info["dio"])

        # 3. DPO Calculation
        if c <= 0.0 or raw_ap < 0.0:
            dpo = sec_info["dpo"]
        else:
            dpo = safe_div(clean_ap * days_in_period, c, fallback=sec_info["dpo"])

        # Clamp activity days to sane bounds [0, 1095 days / 3 years]
        dso = clamp(dso, 0.0, 1095.0)
        dio = clamp(dio, 0.0, 1095.0)
        dpo = clamp(dpo, 0.0, 1095.0)

        # Cash Conversion Cycle (Unclamped to preserve valid negative CCC in retail)
        ccc = dso + dio - dpo

        # Working Capital Balances
        trade_nwc = clean_ar + clean_inv - clean_ap
        operating_working_capital = trade_nwc
        trade_working_capital = trade_nwc
        net_working_capital = (clean_ar + clean_inv + clean_oca) - (clean_ap + clean_ocl)
        total_operating_nwc = net_working_capital

        # Startup all-zeros edge case
        if r == 0.0 and c == 0.0 and clean_ar == 0.0 and clean_inv == 0.0 and clean_ap == 0.0:
            trade_nwc = 0.0
            operating_working_capital = 0.0
            trade_working_capital = 0.0
            net_working_capital = 0.0
            total_operating_nwc = 0.0

        return {
            "dso": dso,
            "dio": dio,
            "dpo": dpo,
            "ccc": ccc,
            "revenue": r,
            "cogs": c,
            "sga": s,
            "accounts_receivable": clean_ar,
            "inventory": clean_inv,
            "accounts_payable": clean_ap,
            "other_current_assets": clean_oca,
            "other_current_liabilities": clean_ocl,
            "trade_working_capital": trade_working_capital,
            "trade_nwc": trade_nwc,
            "operating_working_capital": operating_working_capital,
            "net_working_capital": net_working_capital,
            "total_operating_nwc": total_operating_nwc,
            "delta_nwc": 0.0,
            "delta_trade_nwc": 0.0,
            "delta_total_nwc": 0.0,
            "delta_ar": 0.0,
            "delta_inv": 0.0,
            "delta_inventory": 0.0,
            "delta_ap": 0.0,
            "delta_oca": 0.0,
            "delta_ocl": 0.0,
            "is_financial_sector": False,
            "cash_collected_from_customers": r,
            "cash_receipts_customers": r,
            "cash_from_customers": r,
            "cash_from_customers_adjustment": r,
            "cash_receipts_from_customers": r,
            "cash_paid_to_suppliers": c,
            "cash_paid_suppliers": c,
            "cash_to_suppliers": c,
            "cash_to_suppliers_adjustment": c,
            "cash_paid_for_opex": s,
            "cash_paid_opex": s,
            "cash_for_opex": s,
        }

    @staticmethod
    def calculate_working_capital_metrics(
        rev: Union[float, int, str, None],
        cogs: Union[float, int, str, None],
        ar: Union[float, int, str, None],
        inv: Union[float, int, str, None],
        ap: Union[float, int, str, None],
        other_ca: Union[float, int, str, None] = 0.0,
        other_cl: Union[float, int, str, None] = 0.0,
        sga: Union[float, int, str, None] = 0.0,
        prev_nwc: Optional[float] = None,
        sector: str = "DEFAULT",
        days_in_period: int = 365,
        symbol: Optional[str] = None,
    ) -> WorkingCapitalMetrics:
        """
        Calculates and returns a validated WorkingCapitalMetrics Pydantic model instance.
        """
        raw_dict = WorkingCapitalEngine.calculate_historical_days(
            rev=rev,
            cogs=cogs,
            ar=ar,
            inv=inv,
            ap=ap,
            other_ca=other_ca,
            other_cl=other_cl,
            sga=sga,
            sector=sector,
            days_in_period=days_in_period,
            symbol=symbol,
        )
        if prev_nwc is not None:
            delta = raw_dict["net_working_capital"] - sanitize_float(prev_nwc, 0.0)
            raw_dict["delta_nwc"] = delta
            raw_dict["delta_total_nwc"] = delta
        return WorkingCapitalMetrics(**raw_dict)

    @staticmethod
    def project_working_capital_schedule(
        base_metrics: Dict[str, Any],
        revenue_series: List[float],
        cogs_series: List[float],
        sga_series: Optional[List[float]] = None,
        other_ca_series: Optional[List[float]] = None,
        other_cl_series: Optional[List[float]] = None,
        sector: str = "DEFAULT",
        mean_revert_speed: float = 0.0,
        convergence_speed: Optional[float] = None,
        convergence_rate: Optional[float] = None,
        days_in_period: int = 365,
        years: Optional[List[int]] = None,
        start_year: int = 2026,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Projects a multi-period (e.g. 5-Year) dynamic Working Capital Schedule.
        Enforces the exact Delta NWC component additivity invariant:
        Delta NWC_t == Delta AR_t + Delta Inv_t + Delta OCA_t - Delta AP_t - Delta OCL_t
        """
        sec_info = resolve_sector_prior(sector, symbol=symbol)
        is_financial = (
            base_metrics.get("is_financial_sector", False) or
            sec_info.get("is_financial", False)
        )

        # Resolve mean-reversion speed parameter alias
        speed = mean_revert_speed
        if convergence_speed is not None:
            speed = convergence_speed
        elif convergence_rate is not None:
            speed = convergence_rate
        speed = clamp(speed, 0.0, 1.0)

        num_periods = min(len(revenue_series), len(cogs_series))
        schedule: List[Dict[str, Any]] = []

        # If financial institution, emit zeroed schedules cleanly
        if is_financial:
            for t in range(num_periods):
                rev_t = sanitize_float(revenue_series[t], 0.0)
                cogs_t = sanitize_float(cogs_series[t], 0.0)
                sga_t = sanitize_float(sga_series[t], 0.0) if (sga_series and t < len(sga_series)) else 0.0
                yr = years[t] if (years and t < len(years)) else (start_year + t)
                period_dict = {
                    "year": yr,
                    "year_index": t + 1,
                    "revenue": rev_t,
                    "cogs": cogs_t,
                    "sga": sga_t,
                    "dso": 0.0,
                    "dio": 0.0,
                    "dpo": 0.0,
                    "ccc": 0.0,
                    "accounts_receivable": 0.0,
                    "inventory": 0.0,
                    "accounts_payable": 0.0,
                    "other_current_assets": 0.0,
                    "other_current_liabilities": 0.0,
                    "trade_working_capital": 0.0,
                    "operating_working_capital": 0.0,
                    "trade_nwc": 0.0,
                    "net_working_capital": 0.0,
                    "total_operating_nwc": 0.0,
                    "delta_ar": 0.0,
                    "delta_inventory": 0.0,
                    "delta_inv": 0.0,
                    "delta_ap": 0.0,
                    "delta_oca": 0.0,
                    "delta_ocl": 0.0,
                    "delta_trade_nwc": 0.0,
                    "delta_total_nwc": 0.0,
                    "delta_nwc": 0.0,
                    "cash_collected_from_customers": rev_t,
                    "cash_from_customers": rev_t,
                    "cash_from_customers_adjustment": rev_t,
                    "cash_receipts_from_customers": rev_t,
                    "cash_receipts_customers": rev_t,
                    "cash_paid_to_suppliers": cogs_t,
                    "cash_to_suppliers": cogs_t,
                    "cash_to_suppliers_adjustment": cogs_t,
                    "cash_paid_suppliers": cogs_t,
                    "cash_paid_for_opex": sga_t,
                    "cash_paid_opex": sga_t,
                    "cash_for_opex": sga_t,
                    "is_financial_sector": True,
                }
                schedule.append(period_dict)
            return schedule

        # Baseline Days & Balances
        cur_dso = sanitize_float(base_metrics.get("dso"), sec_info["dso"])
        cur_dio = sanitize_float(base_metrics.get("dio"), sec_info["dio"])
        cur_dpo = sanitize_float(base_metrics.get("dpo"), sec_info["dpo"])

        target_dso = sec_info["dso"]
        target_dio = sec_info["dio"]
        target_dpo = sec_info["dpo"]

        prior_ar = sanitize_float(base_metrics.get("accounts_receivable", base_metrics.get("ar", 0.0)))
        prior_inv = sanitize_float(base_metrics.get("inventory", base_metrics.get("inv", 0.0)))
        prior_ap = sanitize_float(base_metrics.get("accounts_payable", base_metrics.get("ap", 0.0)))
        prior_oca = sanitize_float(base_metrics.get("other_current_assets", base_metrics.get("other_ca", 0.0)))
        prior_ocl = sanitize_float(base_metrics.get("other_current_liabilities", base_metrics.get("other_cl", 0.0)))
        prior_nwc = sanitize_float(
            base_metrics.get("net_working_capital"),
            (prior_ar + prior_inv + prior_oca) - (prior_ap + prior_ocl)
        )

        base_rev = sanitize_float(base_metrics.get("revenue", base_metrics.get("rev", 0.0)))
        if base_rev <= 0.0 and len(revenue_series) > 0 and revenue_series[0] > 0:
            base_rev = revenue_series[0]

        base_cogs = sanitize_float(base_metrics.get("cogs", 0.0))
        if base_cogs <= 0.0 and len(cogs_series) > 0 and cogs_series[0] > 0:
            base_cogs = cogs_series[0]

        for t in range(num_periods):
            rev_t = sanitize_float(revenue_series[t], 0.0)
            cogs_t = sanitize_float(cogs_series[t], 0.0)
            sga_t = sanitize_float(sga_series[t], 0.0) if (sga_series and t < len(sga_series)) else 0.0
            yr = years[t] if (years and t < len(years)) else (start_year + t)

            # 1. Update Efficiency Days (Mean Reversion)
            if speed > 0.0:
                cur_dso = cur_dso * (1.0 - speed) + target_dso * speed
                cur_dio = cur_dio * (1.0 - speed) + target_dio * speed
                cur_dpo = cur_dpo * (1.0 - speed) + target_dpo * speed

            cur_dso = clamp(cur_dso, 0.0, 1095.0)
            cur_dio = clamp(cur_dio, 0.0, 1095.0)
            cur_dpo = clamp(cur_dpo, 0.0, 1095.0)
            ccc_t = cur_dso + cur_dio - cur_dpo

            # 2. Project Balance Sheet Asset & Liability Accounts
            ar_t = (cur_dso * rev_t) / days_in_period
            inv_t = (cur_dio * cogs_t) / days_in_period
            ap_t = (cur_dpo * cogs_t) / days_in_period

            # Other Current Assets Projection
            if other_ca_series is not None and t < len(other_ca_series):
                oca_t = sanitize_float(other_ca_series[t], 0.0)
            elif prior_oca != 0.0 and base_rev > 0.0:
                oca_t = (prior_oca / base_rev) * rev_t
            else:
                oca_t = prior_oca

            # Other Current Liabilities Projection
            if other_cl_series is not None and t < len(other_cl_series):
                ocl_t = sanitize_float(other_cl_series[t], 0.0)
            elif prior_ocl != 0.0 and base_cogs > 0.0:
                ocl_t = (prior_ocl / base_cogs) * cogs_t
            else:
                ocl_t = prior_ocl

            # 3. Compute Aggregates & Changes (Deltas)
            trade_nwc_t = ar_t + inv_t - ap_t
            operating_working_capital_t = trade_nwc_t
            trade_working_capital_t = trade_nwc_t
            nwc_t = (ar_t + inv_t + oca_t) - (ap_t + ocl_t)
            total_operating_nwc_t = nwc_t

            delta_ar = ar_t - prior_ar
            delta_inv = inv_t - prior_inv
            delta_ap = ap_t - prior_ap
            delta_oca = oca_t - prior_oca
            delta_ocl = ocl_t - prior_ocl

            delta_trade_nwc = delta_ar + delta_inv - delta_ap

            # Exact Component Additivity Invariant:
            # Delta NWC = Delta AR + Delta Inv + Delta OCA - Delta AP - Delta OCL
            delta_nwc = (delta_ar + delta_inv + delta_oca) - (delta_ap + delta_ocl)
            delta_total_nwc = delta_nwc

            # 4. Direct Method Operating Cash Flows
            cash_cust = rev_t - delta_ar
            cash_supp = cogs_t + delta_inv - delta_ap
            cash_opex = sga_t + delta_oca - delta_ocl

            period_dict = {
                "year": yr,
                "year_index": t + 1,
                "revenue": rev_t,
                "cogs": cogs_t,
                "sga": sga_t,
                "dso": cur_dso,
                "dio": cur_dio,
                "dpo": cur_dpo,
                "ccc": ccc_t,
                "accounts_receivable": ar_t,
                "inventory": inv_t,
                "accounts_payable": ap_t,
                "other_current_assets": oca_t,
                "other_current_liabilities": ocl_t,
                "trade_working_capital": trade_working_capital_t,
                "operating_working_capital": operating_working_capital_t,
                "trade_nwc": trade_nwc_t,
                "net_working_capital": nwc_t,
                "total_operating_nwc": total_operating_nwc_t,
                "delta_ar": delta_ar,
                "delta_inventory": delta_inv,
                "delta_inv": delta_inv,
                "delta_ap": delta_ap,
                "delta_oca": delta_oca,
                "delta_ocl": delta_ocl,
                "delta_trade_nwc": delta_trade_nwc,
                "delta_total_nwc": delta_total_nwc,
                "delta_nwc": delta_nwc,
                "cash_collected_from_customers": cash_cust,
                "cash_from_customers": cash_cust,
                "cash_from_customers_adjustment": cash_cust,
                "cash_receipts_from_customers": cash_cust,
                "cash_receipts_customers": cash_cust,
                "cash_paid_to_suppliers": cash_supp,
                "cash_to_suppliers": cash_supp,
                "cash_to_suppliers_adjustment": cash_supp,
                "cash_paid_suppliers": cash_supp,
                "cash_paid_for_opex": cash_opex,
                "cash_paid_opex": cash_opex,
                "cash_for_opex": cash_opex,
                "is_financial_sector": False,
            }
            schedule.append(period_dict)

            # Advance roll-forward state
            prior_ar = ar_t
            prior_inv = inv_t
            prior_ap = ap_t
            prior_oca = oca_t
            prior_ocl = ocl_t
            prior_nwc = nwc_t

        return schedule

    @staticmethod
    def compute_direct_cash_flow_adjustments(
        current_period: Dict[str, Any],
        prior_period: Dict[str, Any],
        revenue: Union[float, int, str, None],
        cogs: Union[float, int, str, None],
        sga: Union[float, int, str, None] = 0.0,
    ) -> Dict[str, float]:
        """
        Computes Direct Method Cash Flow adjustments for operating customer receipts, supplier payments, and OPEX.
        Satisfies accounting invariants:
        (Cash Collected - Cash Paid Suppliers) == (Gross Profit - Delta Trade NWC)
        (Cash Collected - Cash Paid Suppliers - Cash Paid OPEX) == (EBITDA - Delta Total NWC)
        """
        rev = sanitize_float(revenue, 0.0)
        cg = sanitize_float(cogs, 0.0)
        sg = sanitize_float(sga, 0.0)

        ar_curr = sanitize_float(current_period.get("accounts_receivable", current_period.get("ar", 0.0)))
        ar_prior = sanitize_float(prior_period.get("accounts_receivable", prior_period.get("ar", 0.0)))
        delta_ar = ar_curr - ar_prior

        inv_curr = sanitize_float(current_period.get("inventory", current_period.get("inv", 0.0)))
        inv_prior = sanitize_float(prior_period.get("inventory", prior_period.get("inv", 0.0)))
        delta_inv = inv_curr - inv_prior

        ap_curr = sanitize_float(current_period.get("accounts_payable", current_period.get("ap", 0.0)))
        ap_prior = sanitize_float(prior_period.get("accounts_payable", prior_period.get("ap", 0.0)))
        delta_ap = ap_curr - ap_prior

        oca_curr = sanitize_float(current_period.get("other_current_assets", current_period.get("other_ca", 0.0)))
        oca_prior = sanitize_float(prior_period.get("other_current_assets", prior_period.get("other_ca", 0.0)))
        delta_oca = oca_curr - oca_prior

        ocl_curr = sanitize_float(current_period.get("other_current_liabilities", current_period.get("other_cl", 0.0)))
        ocl_prior = sanitize_float(prior_period.get("other_current_liabilities", prior_period.get("other_cl", 0.0)))
        delta_ocl = ocl_curr - ocl_prior

        trade_nwc_curr = ar_curr + inv_curr - ap_curr
        trade_nwc_prior = ar_prior + inv_prior - ap_prior
        delta_trade_nwc = trade_nwc_curr - trade_nwc_prior

        nwc_curr = (ar_curr + inv_curr + oca_curr) - (ap_curr + ocl_curr)
        nwc_prior = (ar_prior + inv_prior + oca_prior) - (ap_prior + ocl_prior)
        delta_nwc = nwc_curr - nwc_prior

        cash_from_customers = rev - delta_ar
        cash_to_suppliers = cg + delta_inv - delta_ap
        cash_for_opex = sg + delta_oca - delta_ocl
        gross_operating_cash_flow = cash_from_customers - cash_to_suppliers
        net_operating_cash_flow_before_tax_interest = gross_operating_cash_flow - cash_for_opex

        return {
            "cash_collected_from_customers": cash_from_customers,
            "cash_from_customers": cash_from_customers,
            "cash_receipts_from_customers": cash_from_customers,
            "cash_receipts_customers": cash_from_customers,
            "cash_paid_to_suppliers": cash_to_suppliers,
            "cash_to_suppliers": cash_to_suppliers,
            "cash_paid_suppliers": cash_to_suppliers,
            "cash_paid_for_opex": cash_for_opex,
            "cash_paid_opex": cash_for_opex,
            "cash_for_opex": cash_for_opex,
            "gross_operating_cash_flow": gross_operating_cash_flow,
            "net_operating_cash_flow_before_tax_interest": net_operating_cash_flow_before_tax_interest,
            "delta_ar": delta_ar,
            "delta_inv": delta_inv,
            "delta_inventory": delta_inv,
            "delta_ap": delta_ap,
            "delta_oca": delta_oca,
            "delta_ocl": delta_ocl,
            "delta_trade_nwc": delta_trade_nwc,
            "delta_total_nwc": delta_nwc,
            "delta_nwc": delta_nwc,
        }

    @staticmethod
    def build_working_capital_forecast(
        symbol: str,
        base_data: Dict[str, Any],
        revenue_forecast: List[float],
        cogs_forecast: List[float],
        sga_forecast: Optional[List[float]] = None,
        sector: str = "DEFAULT",
        start_year: int = 2026,
        mean_revert_speed: float = 0.20,
        convergence_rate: Optional[float] = None,
    ) -> WorkingCapitalForecastResult:
        """
        Top-level pipeline builder producing a fully validated WorkingCapitalForecastResult.
        """
        base_metrics_dict = WorkingCapitalEngine.calculate_historical_days(
            rev=base_data.get("revenue", base_data.get("rev", 0.0)),
            cogs=base_data.get("cogs", 0.0),
            ar=base_data.get("accounts_receivable", base_data.get("ar", 0.0)),
            inv=base_data.get("inventory", base_data.get("inv", 0.0)),
            ap=base_data.get("accounts_payable", base_data.get("ap", 0.0)),
            other_ca=base_data.get("other_current_assets", base_data.get("other_ca", 0.0)),
            other_cl=base_data.get("other_current_liabilities", base_data.get("other_cl", 0.0)),
            sga=base_data.get("sga", base_data.get("sga_expense", 0.0)),
            sector=sector,
            symbol=symbol,
        )

        base_metrics = WorkingCapitalMetrics(**base_metrics_dict)
        years = [start_year + i for i in range(len(revenue_forecast))]

        speed = convergence_rate if convergence_rate is not None else mean_revert_speed

        schedule_dicts = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base_metrics_dict,
            revenue_series=revenue_forecast,
            cogs_series=cogs_forecast,
            sga_series=sga_forecast,
            sector=sector,
            mean_revert_speed=speed,
            years=years,
            symbol=symbol,
        )

        schedule_periods = [WorkingCapitalSchedulePeriod(**p) for p in schedule_dicts]

        summary = {
            "symbol": symbol.upper(),
            "sector": sector,
            "is_financial": base_metrics.is_financial_sector,
            "avg_projected_ccc": (
                sum(p.ccc for p in schedule_periods) / len(schedule_periods)
                if schedule_periods else 0.0
            ),
            "total_5y_delta_nwc": sum(p.delta_nwc for p in schedule_periods),
        }

        return WorkingCapitalForecastResult(
            symbol=symbol.upper(),
            sector=sector,
            base_metrics=base_metrics,
            schedule=schedule_periods,
            summary=summary,
        )

    @staticmethod
    def build_working_capital_schedule(
        base_data: Dict[str, Any],
        revenue_series: List[float],
        cogs_series: List[float],
        sga_series: Optional[List[float]] = None,
        start_year: int = 2026,
        mean_revert_speed: float = 0.0,
        sector: Optional[str] = None,
        **kwargs: Any,
    ) -> List[WorkingCapitalSchedulePeriod]:
        """
        Class-level alias for build_working_capital_schedule interface contract.
        """
        return build_working_capital_schedule(
            base_data=base_data,
            revenue_series=revenue_series,
            cogs_series=cogs_series,
            sga_series=sga_series,
            start_year=start_year,
            mean_revert_speed=mean_revert_speed,
            sector=sector,
            **kwargs,
        )


def build_working_capital_schedule(
    base_data: Dict[str, Any],
    revenue_series: List[float],
    cogs_series: List[float],
    sga_series: Optional[List[float]] = None,
    start_year: int = 2026,
    mean_revert_speed: float = 0.0,
    sector: Optional[str] = None,
    **kwargs: Any,
) -> List[WorkingCapitalSchedulePeriod]:
    """
    Standard Modano Interface Contract builder function producing a 5-year working capital schedule.
    Accepts base fundamental data and forecast series of Revenue, COGS, and SG&A.
    Returns a List of WorkingCapitalSchedulePeriod pydantic instances.
    """
    sec = sector or base_data.get("sector", "DEFAULT")
    sym = base_data.get("symbol")
    sec_info = resolve_sector_prior(sec, symbol=sym)

    base_metrics_dict = WorkingCapitalEngine.calculate_historical_days(
        rev=base_data.get("revenue", base_data.get("rev", 0.0)),
        cogs=base_data.get("cogs", 0.0),
        ar=base_data.get("accounts_receivable", base_data.get("ar", 0.0)),
        inv=base_data.get("inventory", base_data.get("inv", 0.0)),
        ap=base_data.get("accounts_payable", base_data.get("ap", 0.0)),
        other_ca=base_data.get("other_current_assets", base_data.get("other_ca", 0.0)),
        other_cl=base_data.get("other_current_liabilities", base_data.get("other_cl", 0.0)),
        sga=base_data.get("sga", base_data.get("sga_expense", 0.0)),
        sector=sec,
        symbol=sym,
    )

    years = [start_year + i for i in range(len(revenue_series))]
    speed = kwargs.get("convergence_speed", kwargs.get("convergence_rate", mean_revert_speed))

    schedule_dicts = WorkingCapitalEngine.project_working_capital_schedule(
        base_metrics=base_metrics_dict,
        revenue_series=revenue_series,
        cogs_series=cogs_series,
        sga_series=sga_series,
        other_ca_series=kwargs.get("other_ca_series"),
        other_cl_series=kwargs.get("other_cl_series"),
        sector=sec,
        mean_revert_speed=speed,
        years=years,
        symbol=sym,
    )

    return [WorkingCapitalSchedulePeriod(**p) for p in schedule_dicts]


__all__ = [
    "WorkingCapitalEngine",
    "WorkingCapitalMetrics",
    "WorkingCapitalSchedulePeriod",
    "WorkingCapitalForecastResult",
    "build_working_capital_schedule",
    "SECTOR_WC_PRIORS",
    "SECTOR_PRIORS",
    "SECTOR_BENCHMARKS",
    "FINANCIAL_SYMBOLS",
    "safe_div",
    "clamp",
    "sanitize_float",
    "resolve_sector_prior",
]
