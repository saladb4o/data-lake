"""
=============================================================================
QUANTITATIVE VALUATION ENGINE & RISK FIREWALLS (22 MODELS + 5-FACTOR VN CAPM)
=============================================================================
Institutional-grade Valuation Engine ported and expanded from Pine Script FFV Pro
and Goldman Sachs / McKinsey equity research standards, specifically calibrated
for the Vietnamese equity market (HOSE, HNX, UPCOM).

Architecture & Feature Index:
----------------------------
1. Macro & Capital Cost Engine:
   - 5-Factor Vietnam CAPM (Market Beta, Size SMB, Value HML, Momentum UMD,
     Amihud Illiquidity ILLIQ, Operating Profitability RMW)
   - Aswath Damodaran Synthetic Credit Rating & Cost of Debt Table (ICR -> Rating -> Spread)
   - WACC Calculator & Bounded Cost of Equity (Ke)

2. Risk Firewalls & Anti-Trap Diagnostics:
   - 4-Quadrant Emerging Market Altman Z'' + Beneish M-Score (Safe Institutional,
     Distressed Turnaround, Toxic Exclusion, Forensic Trap)
   - Rhodes-Kropf (RKV) Enterprise Valuation Decomposition (Firm Misvaluation,
     Sector Time-Series Error, Long-Run Sector Growth)
   - Dynamic Margin of Safety (MOS) Scaled by Downside Beta (beta_-) & Risk Penalties

3. 22 Quantitative Valuation Models:
   [Relative Multiples - 8 Models]
   - Model 1: Blended P/E with Shiller Cyclically Adjusted CAPE (3Y/5Y)
   - Model 2: Margin-Adjusted Price-to-Sales (P/S)
   - Model 3: Price-to-Free Cash Flow (P/FCF)
   - Model 4: Price-to-Book (P/B) with Rhodes-Kropf Filter
   - Model 5: Price-to-Tangible Book Value (P/TBV)
   - Model 6: Blended EV/EBITDA Enterprise Multiple
   - Model 7: Price-to-Operating Cash Flow (P/CF)
   - Model 8: Price-to-AFFO Multiple (P/AFFO)

   [Absolute Intrinsic Models - 7 Models]
   - Model 9: Extended 2-Stage Value Driver DCF (McKinsey / ROIC Framework)
   - Model 10: Residual Income Model (RIM / Edwards-Bell-Ohlson)
   - Model 11: Greenwald Earnings Power Value (EPV)
   - Model 12: Benjamin Graham Growth Number & Revised Formula
   - Model 13: Rule of 40 / Rule of X Growth Model
   - Model 14: Acquirer's Multiple (Tobias Carlisle EV/EBIT)
   - Model 15: Warren Buffett Owner's Earnings DCF

   [Sector-Specific Models - 7 Models]
   - Model 16: Risk-Adjusted NPV (rNPV) — Pharma & Biotech Pipeline (ICB 4500)
   - Model 17: Equity Cash Flow & Basel II CAR — Banks & Insurance (ICB 8300 / 8500)
   - Model 18: AFFO DCF & Cap Rate — Real Estate Developers & REITs (ICB 8600)
   - Model 19: Unbundled SOTP & Regulated Asset Base (RAB) — Telecom & Infra (ICB 6500 / 7500)
   - Model 20: Adjusted Present Value (APV) — Industrials & Materials (ICB 2700 / 1700)
   - Model 21: Economic Value Added (EVA & MVA) — Consumer Staples & Retail (ICB 3000 / 5000)
   - Model 22: 3-Stage Dividend Discount Model (DDM / H-Model) — Utilities (ICB 7000 / 7500)

4. Stress-Test Scenarios & 2D Sensitivity Grid:
   - Bear / Base / Bull Parameter Perturbation Matrix
   - 5x5 WACC vs Terminal Growth Sensitivity Grid

5. Multi-Algo Adaptive Error Weighting Engine:
   - Inverse Variance Weighting (IVW)
   - Historical Rolling Error Metrics (SMAPE, MALE, WMAPE, RMSLE)
   - 1.5x IQR Fence Outlier Rejection & Sector Applicability Gating
   - Cold-Start / Zero Track Record Sector Prior Fallback Hierarchy
"""

from __future__ import annotations

import os
import math
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple, Union, Sequence, Callable

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS & CALIBRATED VIETNAM MACRO PARAMETERS
# =============================================================================

DEFAULT_RF: float = 0.0500        # Vietnam 10-Year Government Bond benchmark yield (5.0%)
DEFAULT_ERP: float = 0.0815       # Damodaran Vietnam ERP (Mature ERP 4.60% + Vietnam CRP 3.55%)
DEFAULT_TAX_RATE: float = 0.20    # Standard Vietnam Corporate Income Tax Rate (20%)
DEFAULT_BASE_MOS: float = 0.20    # Base Margin of Safety (20.0%)
DEFAULT_TERMINAL_G: float = 0.035 # Long-term terminal nominal growth rate (3.5%)

# Damodaran Synthetic Credit Rating Table based on Interest Coverage Ratio (ICR)
# Format: (min_icr, rating, spread_over_rf)
DAMODARAN_SPREAD_LARGE_CAP = [
    (8.50, "AAA", 0.0065),
    (6.50, "AA",  0.0090),
    (5.50, "A+",  0.0115),
    (4.25, "A",   0.0135),
    (3.00, "A-",  0.0160),
    (2.50, "BBB", 0.0210),
    (2.25, "BB+", 0.0285),
    (2.00, "BB",  0.0340),
    (1.75, "B+",  0.0425),
    (1.50, "B",   0.0525),
    (1.25, "B-",  0.0650),
    (0.80, "CCC", 0.0850),
    (0.50, "CC",  0.1000),
    (-float("inf"), "D", 0.1250),
]

DAMODARAN_SPREAD_SMALL_CAP = [
    (12.50, "AAA", 0.0065),
    (9.50,  "AA",  0.0090),
    (7.50,  "A+",  0.0115),
    (6.00,  "A",   0.0135),
    (4.50,  "A-",  0.0160),
    (4.00,  "BBB", 0.0210),
    (3.50,  "BB+", 0.0285),
    (3.00,  "BB",  0.0340),
    (2.50,  "B+",  0.0425),
    (2.00,  "B",   0.0525),
    (1.50,  "B-",  0.0650),
    (1.25,  "CCC", 0.0850),
    (0.80,  "CC",  0.1000),
    (-float("inf"), "D", 0.1250),
]

# Sector Model Applicability Mappings (ICB Codes & Sector Prefixes)
SECTOR_MODEL_MAP: Dict[str, List[str]] = {
    # Banks & Financial Services (VNFIN, VNBNK, VNSEC, VNINS, 8300, 8500, 8700)
    "VNFIN": ["pb_rhodes_kropf", "rim_edwards_bell_ohlson", "bank_equity_cash_flow", "blended_pe", "graham_growth", "p_tbv"],
    "VNBNK": ["pb_rhodes_kropf", "rim_edwards_bell_ohlson", "bank_equity_cash_flow", "blended_pe", "graham_growth", "p_tbv"],
    "8300":  ["pb_rhodes_kropf", "rim_edwards_bell_ohlson", "bank_equity_cash_flow", "blended_pe", "graham_growth", "p_tbv"],
    "VNSEC": ["pb_rhodes_kropf", "blended_pe", "rim_edwards_bell_ohlson", "acquirers_multiple_ev_ebit", "graham_growth"],
    "8700":  ["pb_rhodes_kropf", "blended_pe", "rim_edwards_bell_ohlson", "acquirers_multiple_ev_ebit", "graham_growth"],
    "VNINS": ["bank_equity_cash_flow", "pb_rhodes_kropf", "rim_edwards_bell_ohlson", "utilities_3stage_ddm", "blended_pe"],
    "8500":  ["bank_equity_cash_flow", "pb_rhodes_kropf", "rim_edwards_bell_ohlson", "utilities_3stage_ddm", "blended_pe"],
    # Real Estate & REITs (VNREAL, VNREA, 8600)
    "VNREAL": ["reit_affo_dcf", "pb_rhodes_kropf", "p_affo", "dcf_2stage_mckinsey", "rim_edwards_bell_ohlson", "blended_pe"],
    "VNREA": ["reit_affo_dcf", "pb_rhodes_kropf", "p_affo", "dcf_2stage_mckinsey", "rim_edwards_bell_ohlson", "blended_pe"],
    "8600":  ["reit_affo_dcf", "pb_rhodes_kropf", "p_affo", "dcf_2stage_mckinsey", "rim_edwards_bell_ohlson", "blended_pe"],
    # Energy & Oil/Gas (VNENE, VNENG, 0500)
    "VNENE": ["ev_ebitda", "dcf_2stage_mckinsey", "industrial_apv", "blended_pe", "p_fcf", "greenwald_epv"],
    "VNENG": ["ev_ebitda", "dcf_2stage_mckinsey", "industrial_apv", "blended_pe", "p_fcf", "greenwald_epv"],
    "0500":  ["ev_ebitda", "dcf_2stage_mckinsey", "industrial_apv", "blended_pe", "p_fcf", "greenwald_epv"],
    # Utilities (Power, Water: VNUTI, 7500, 7000)
    "VNUTI": ["utilities_3stage_ddm", "telecom_unbundled_sotp", "ev_ebitda", "dcf_2stage_mckinsey", "blended_pe"],
    "7500":  ["utilities_3stage_ddm", "telecom_unbundled_sotp", "ev_ebitda", "dcf_2stage_mckinsey", "blended_pe"],
    "7000":  ["utilities_3stage_ddm", "telecom_unbundled_sotp", "ev_ebitda", "dcf_2stage_mckinsey", "blended_pe"],
    # Basic Materials & Steel (VNMAT, 1700)
    "VNMAT": ["industrial_apv", "ev_ebitda", "blended_pe", "pb_rhodes_kropf", "dcf_2stage_mckinsey", "buffett_owners_earnings"],
    "1700":  ["industrial_apv", "ev_ebitda", "blended_pe", "pb_rhodes_kropf", "dcf_2stage_mckinsey", "buffett_owners_earnings"],
    # Consumer Staples & Retail (VNCONS, VNCOND, VNFOB, 3500, 3000, 5000)
    "VNCONS": ["consumer_eva_mva", "buffett_owners_earnings", "blended_pe", "dcf_2stage_mckinsey", "ps_margin_adj", "p_fcf"],
    "VNCOND": ["consumer_eva_mva", "buffett_owners_earnings", "blended_pe", "dcf_2stage_mckinsey", "ps_margin_adj", "p_fcf"],
    "VNFOB": ["consumer_eva_mva", "buffett_owners_earnings", "blended_pe", "dcf_2stage_mckinsey", "ps_margin_adj", "p_fcf"],
    "3500":  ["consumer_eva_mva", "buffett_owners_earnings", "blended_pe", "dcf_2stage_mckinsey", "ps_margin_adj", "p_fcf"],
    "3000":  ["consumer_eva_mva", "buffett_owners_earnings", "blended_pe", "dcf_2stage_mckinsey", "ps_margin_adj", "p_fcf"],
    "5000":  ["consumer_eva_mva", "buffett_owners_earnings", "blended_pe", "dcf_2stage_mckinsey", "ps_margin_adj", "p_fcf"],
    # Technology & Software (VNIT, VNTEC, 9500)
    "VNIT":  ["rule_of_40_growth", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "ps_margin_adj", "p_fcf"],
    "VNTEC": ["rule_of_40_growth", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "ps_margin_adj", "p_fcf"],
    "9500":  ["rule_of_40_growth", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "ps_margin_adj", "p_fcf"],
    # Healthcare & Pharmaceuticals (VNHEAL, VNHEA, 4500)
    "VNHEAL": ["pharma_rnpv", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "p_fcf", "greenwald_epv"],
    "VNHEA": ["pharma_rnpv", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "p_fcf", "greenwald_epv"],
    "4500":  ["pharma_rnpv", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "p_fcf", "greenwald_epv"],
    # Telecommunications (6500)
    "6500":  ["telecom_unbundled_sotp", "ev_ebitda", "dcf_2stage_mckinsey", "blended_pe", "utilities_3stage_ddm"],
    # Industrials & Capital Goods (VNIND, 2700, 2000)
    "VNIND": ["industrial_apv", "ev_ebitda", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "p_fcf"],
    "2700":  ["industrial_apv", "ev_ebitda", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "p_fcf"],
    "2000":  ["industrial_apv", "ev_ebitda", "dcf_2stage_mckinsey", "buffett_owners_earnings", "blended_pe", "p_fcf"],
}

# Pre-calibrated Sector IVW Model Weight Priors (Tier 1 Fallback)
SECTOR_WEIGHT_PRIORS: Dict[str, Dict[str, float]] = {
    "VNFIN": {"pb_rhodes_kropf": 0.35, "bank_equity_cash_flow": 0.30, "rim_edwards_bell_ohlson": 0.20, "blended_pe": 0.15},
    "VNBNK": {"pb_rhodes_kropf": 0.35, "bank_equity_cash_flow": 0.30, "rim_edwards_bell_ohlson": 0.20, "blended_pe": 0.15},
    "VNSEC": {"pb_rhodes_kropf": 0.40, "blended_pe": 0.30, "rim_edwards_bell_ohlson": 0.20, "acquirers_multiple_ev_ebit": 0.10},
    "VNREAL": {"reit_affo_dcf": 0.35, "p_affo": 0.25, "pb_rhodes_kropf": 0.20, "dcf_2stage_mckinsey": 0.20},
    "VNREA": {"reit_affo_dcf": 0.35, "p_affo": 0.25, "pb_rhodes_kropf": 0.20, "dcf_2stage_mckinsey": 0.20},
    "VNUTI": {"utilities_3stage_ddm": 0.40, "dcf_2stage_mckinsey": 0.30, "ev_ebitda": 0.20, "blended_pe": 0.10},
    "VNIT":  {"rule_of_40_growth": 0.35, "dcf_2stage_mckinsey": 0.30, "buffett_owners_earnings": 0.20, "blended_pe": 0.15},
    "VNTEC": {"rule_of_40_growth": 0.35, "dcf_2stage_mckinsey": 0.30, "buffett_owners_earnings": 0.20, "blended_pe": 0.15},
    "VNCONS": {"consumer_eva_mva": 0.35, "buffett_owners_earnings": 0.25, "dcf_2stage_mckinsey": 0.25, "blended_pe": 0.15},
    "VNCOND": {"consumer_eva_mva": 0.35, "buffett_owners_earnings": 0.25, "dcf_2stage_mckinsey": 0.25, "blended_pe": 0.15},
    "VNFOB": {"consumer_eva_mva": 0.35, "buffett_owners_earnings": 0.25, "dcf_2stage_mckinsey": 0.25, "blended_pe": 0.15},
    "VNIND": {"industrial_apv": 0.35, "ev_ebitda": 0.30, "blended_pe": 0.20, "dcf_2stage_mckinsey": 0.15},
    "VNMAT": {"industrial_apv": 0.35, "ev_ebitda": 0.30, "blended_pe": 0.20, "pb_rhodes_kropf": 0.15},
    "VNENE": {"ev_ebitda": 0.35, "dcf_2stage_mckinsey": 0.30, "industrial_apv": 0.20, "p_fcf": 0.15},
    "VNENG": {"ev_ebitda": 0.35, "dcf_2stage_mckinsey": 0.30, "industrial_apv": 0.20, "p_fcf": 0.15},
    "VNHEAL": {"pharma_rnpv": 0.40, "dcf_2stage_mckinsey": 0.30, "buffett_owners_earnings": 0.20, "blended_pe": 0.10},
    "VNHEA": {"pharma_rnpv": 0.40, "dcf_2stage_mckinsey": 0.30, "buffett_owners_earnings": 0.20, "blended_pe": 0.10},
}


# =============================================================================
# DATA STRUCTURES & DATACLASSES
# =============================================================================

def clamp(val: float, min_val: float, max_val: float) -> float:
    """Clamps a floating point value between min_val and max_val."""
    if math.isnan(val) or math.isinf(val):
        return min_val
    return max(min_val, min(max_val, val))


def safe_div(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    """Safely divides two floats with fallback on zero/NaN/inf."""
    if denominator == 0.0 or math.isnan(denominator) or math.isinf(denominator):
        return fallback
    if math.isnan(numerator) or math.isinf(numerator):
        return fallback
    res = numerator / denominator
    return fallback if (math.isnan(res) or math.isinf(res)) else res



# Sentinel for the 22 model signatures. ``current_price`` caps and floors every
# model output, so a default made the cap arbitrary and let a model run with no
# price at all. It is now required, but kept in its original keyword position so
# existing keyword call sites are unaffected.
_PRICE_REQUIRED = -1.0


def _model_price(current_price: float, model: str) -> float:
    """Validates the price a model was handed."""
    if not math.isfinite(current_price) or current_price <= 0:
        raise ValueError(
            f"{model} requires a positive current_price (got {current_price!r}); "
            "valuation against a default price is disabled."
        )
    return current_price

def _as_rate(value: float) -> float:
    """Normalises a rate given either as a percentage (15.0) or a fraction (0.15)."""
    return value / 100.0 if value > 1.0 else value

# Keys whose values are naturally strings (not numeric) and should be kept as-is.
_STRING_KEYS = frozenset({
    "symbol", "name", "company_name", "exchange", "sector_code", "sector_name",
    "sector", "industry", "category", "description", "source",
})


# Inputs the 22 models actually read. Absence does not stop a valuation - the
# engine substitutes sector or structural defaults - but it does change how much
# the number is worth, which the caller has no other way to know.
CORE_VALUATION_INPUTS: Tuple[str, ...] = (
    "price", "eps", "bvps", "pe", "pb", "roe", "roic",
    "revenue", "net_income", "pat", "ebit", "operating_profit",
    "equity", "total_assets", "debt", "shares_out", "market_cap",
    "rev_1y_growth", "pat_1y_growth", "sector_code",
)

# Below this share of core inputs the composite is structurally driven rather
# than data driven, and should be presented that way.
LOW_COVERAGE_THRESHOLD = 0.40
HIGH_COVERAGE_THRESHOLD = 0.75


def assess_data_quality(fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
    """Reports how much of the valuation rests on real data.

    Every missing input is silently replaced with a sector or structural
    default somewhere in the model suite, so two valuations that look
    identical can be backed by very different amounts of evidence. This makes
    that difference explicit in the payload instead of leaving it implicit in
    the code.

    Coverage is measured over CORE_VALUATION_INPUTS; a field counts as present
    only if it is non-null and, for numerics, finite.
    """
    present, missing = [], []
    for key in CORE_VALUATION_INPUTS:
        value = fundamental_data.get(key)
        if value is None or value == "":
            missing.append(key)
            continue
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            missing.append(key)
            continue
        present.append(key)

    coverage = len(present) / len(CORE_VALUATION_INPUTS)
    if coverage >= HIGH_COVERAGE_THRESHOLD:
        grade = "HIGH"
    elif coverage >= LOW_COVERAGE_THRESHOLD:
        grade = "MEDIUM"
    else:
        grade = "LOW"

    warnings: List[str] = []
    if grade == "LOW":
        warnings.append(
            "Fewer than 40% of core inputs are present; the composite is driven "
            "mainly by sector and structural defaults, not by this company's data."
        )
    for key, label in (
        ("eps", "earnings-based models"),
        ("bvps", "book-value models"),
        ("equity", "return and leverage models"),
        ("revenue", "growth models"),
    ):
        if key in missing:
            warnings.append(f"{key} is missing; {label} fall back to defaults.")

    return {
        "coverage_pct": round(coverage * 100, 1),
        "grade": grade,
        "inputs_present": present,
        "inputs_missing": missing,
        "core_input_count": len(CORE_VALUATION_INPUTS),
        "assumptions_applied": _assumptions_applied(fundamental_data),
        "warnings": warnings,
    }


# Structural stand-ins the model suite uses when an input is absent. These are
# deliberate modelling choices, not accidents - but they were invisible in the
# output, so a number derived from an assumed 40% leverage looked exactly like
# one derived from the company's real balance sheet.
STRUCTURAL_ASSUMPTIONS = (
    ("shares_out", "shares outstanding assumed at 1e8", ("shares_out", "shares")),
    ("market_cap", "market cap derived from price x shares", ("market_cap",)),
    ("debt", "debt assumed at 40% of market cap",
     ("debt", "total_debt_fq", "interest_bearing_debt")),
)


def _assumptions_applied(fundamental_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Names the structural stand-ins that fired for this payload."""
    applied: List[Dict[str, str]] = []
    for field_name, description, sources in STRUCTURAL_ASSUMPTIONS:
        if not any(fundamental_data.get(src) not in (None, "", 0) for src in sources):
            applied.append({"field": field_name, "assumption": description})
    return applied


def _require_price(symbol: str, fundamental_data: Dict[str, Any]) -> float:
    """Returns a usable market price or raises.

    Price anchors every upside, margin-of-safety and risk-firewall figure, so a
    fabricated one produces a confident-looking valuation built on nothing.
    Consistent with the no-silent-fills policy already applied to a missing
    fundamental_data payload, an unusable price is refused rather than defaulted.
    """
    raw = fundamental_data.get("price")
    try:
        price = float(raw)
    except (TypeError, ValueError):
        price = float("nan")
    if not math.isfinite(price) or price <= 0:
        raise ValueError(
            f"A valid market price is required for quantitative valuation of {symbol} "
            f"(got {raw!r}). Fallback to a default price is disabled."
        )
    return price


def _sanitize_fundamental_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize fundamental_data dict: convert NaN, Inf, and unparseable string
    values to None so downstream ``(value or fallback)`` patterns work correctly.
    Preserves naturally-string keys (symbol, name, exchange, etc.) untouched.
    """
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if k in _STRING_KEYS:
            out[k] = v
        elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            out[k] = None
        elif isinstance(v, str):
            # Try to parse numeric strings; discard unparseable ones as None
            try:
                fv = float(v)
                out[k] = None if (math.isnan(fv) or math.isinf(fv)) else fv
            except (ValueError, TypeError):
                out[k] = None
        elif isinstance(v, (list, dict)):
            out[k] = v  # preserve compound types (e.g. historical_eps)
        else:
            out[k] = v
    return out



# =============================================================================
# INPUT PROVENANCE
# =============================================================================
#
# Every model input used to be resolved with ``float(data.get(k) or <default>)``,
# and most of those defaults were a fraction of market cap or price:
# debt = 40% of mcap, revenue = 80% of mcap, equity = 60% of mcap, and so on.
# Because market cap is itself price x shares, a payload missing its financial
# statements produced a full set of "fundamentals" that were all linear in price
# - and every model built on them returned a fixed multiple of the price it was
# handed. The valuation could not disagree with the market because it was
# derived from the market.
#
# The resolver keeps the same defaults available but records where each number
# came from, so a model whose driver was invented can be switched off instead of
# quietly emitting a price echo.

REAL = "real"        # present in the payload
DERIVED = "derived"  # computed from inputs that are themselves real/derived
IMPUTED = "imputed"  # a structural stand-in; carries no company information


class InputResolver:
    """Resolves model inputs while tracking whether each one is real.

    ``resolve`` tries three sources in order: a value in the payload (REAL), a
    definitional derivation whose dependencies are all trustworthy (DERIVED),
    and finally a structural assumption (IMPUTED). Provenance propagates: a
    derivation that reads an imputed field is itself imputed, so a single
    missing statement line marks everything downstream of it.
    """

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.provenance: Dict[str, str] = {}

    # -- lookup ----------------------------------------------------------
    def _lookup(self, keys: Sequence[str]) -> Optional[float]:
        for key in keys:
            raw = self._data.get(key)
            if raw is None or raw == "":
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(val):
                return val
        return None

    # -- provenance queries ----------------------------------------------
    def is_imputed(self, *fields: str) -> bool:
        """True if any named field was invented rather than observed."""
        return any(self.provenance.get(f, IMPUTED) == IMPUTED for f in fields)

    def trustworthy(self, *fields: str) -> bool:
        return not self.is_imputed(*fields)

    @property
    def imputed_fields(self) -> List[str]:
        return sorted(f for f, p in self.provenance.items() if p == IMPUTED)

    @property
    def real_fields(self) -> List[str]:
        return sorted(f for f, p in self.provenance.items() if p == REAL)

    # -- resolution ------------------------------------------------------
    def resolve(
        self,
        field: str,
        keys: Sequence[str],
        derive: Optional[Tuple[Sequence[str], Callable[[], float]]] = None,
        impute: Optional[Callable[[], float]] = None,
        require_positive: bool = False,
    ) -> float:
        """Resolves one input and records its provenance under ``field``.

        ``derive`` is ``(dependencies, fn)``. It is used only when every
        dependency is already REAL or DERIVED - a derivation from invented
        numbers is an assumption wearing a formula, and is recorded as IMPUTED.
        ``require_positive`` rejects a non-positive payload value for fields
        where zero or negative is not a meaningful reading (share counts,
        prices) rather than a real observation (profit, cash flow).
        """
        found = self._lookup(keys)
        if found is not None and not (require_positive and found <= 0):
            self.provenance[field] = REAL
            return found

        if derive is not None:
            deps, fn = derive
            value = fn()
            if math.isfinite(value) and not (require_positive and value <= 0):
                self.provenance[field] = DERIVED if self.trustworthy(*deps) else IMPUTED
                return value

        if impute is None:
            self.provenance[field] = IMPUTED
            return 0.0
        value = impute()
        self.provenance[field] = IMPUTED
        return value

    def mark(self, field: str, provenance: str) -> None:
        """Records provenance for a value resolved outside this helper."""
        self.provenance[field] = provenance


@dataclass
class WACCResult:
    """Detailed output of WACC & 5-Factor Vietnam CAPM calculation."""
    cost_of_equity: float
    cost_of_debt_pre_tax: float
    cost_of_debt_after_tax: float
    synthetic_rating: str
    credit_spread: float
    wacc: float
    equity_weight: float
    debt_weight: float
    rf: float
    erp: float
    beta_adj: float
    smb_premium: float
    hml_premium: float
    umd_premium: float
    illiq_premium: float
    rmw_premium: float
    market_cap: float
    interest_bearing_debt: float
    tax_rate: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskFirewallResult:
    """Diagnostic output of 4-Quadrant Altman/Beneish, Rhodes-Kropf, and Dynamic MOS."""
    altman_z_score: float
    altman_zone: str               # 'safe', 'grey', 'distress'
    beneish_m_score: float
    beneish_status: str             # 'safe', 'manipulator'
    four_quadrant_category: str     # 'safe_institutional', 'distressed_turnaround', 'toxic_exclusion', 'forensic_trap'
    rhodes_kropf: Dict[str, Any]    # firm_misvaluation, sector_drift, long_run_growth, status
    downside_beta: float
    dynamic_margin_of_safety: float
    firewall_passed: bool
    disqualification_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelValuationOutput:
    """Standardized output for an individual valuation model."""
    model_id: str
    model_name: str
    category: str                   # 'relative', 'absolute', 'sector'
    fair_value: float               # Intrinsic price in VND per share
    upside_pct: float               # (fair_value - price) / price * 100
    weight: float                   # Multi-algo weight in composite (0.0 to 1.0)
    active: bool                    # True if used in composite
    status: str                     # 'ACTIVE', 'INACTIVE', 'BYPASSED', 'OUTLIER_REJECTED'
    error_metrics: Dict[str, float] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioResult:
    """Stress-test valuation results across Bear, Base, and Bull scenarios."""
    bear_fair_value: float
    base_fair_value: float
    bull_fair_value: float
    bear_upside_pct: float
    base_upside_pct: float
    bull_upside_pct: float
    scenario_drivers: Dict[str, Any]
    sensitivity_grid_5x5: List[List[float]]
    sensitivity_headers_wacc: List[float]
    sensitivity_headers_growth: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValuationMatrixResult:
    """Comprehensive composite valuation output matching API schema."""
    symbol: str
    company_name: str
    exchange: str
    current_price: float
    composite_fair_value: float
    composite_upside_pct: float
    valuation_status: str          # 'UNDERVALUED', 'FAIRLY_VALUED', 'OVERVALUED'
    margin_of_safety_pct: float
    models: List[ModelValuationOutput]
    wacc_result: WACCResult
    risk_firewall: RiskFirewallResult
    scenarios: ScenarioResult
    timestamp: str
    valuation_width_pct: float = 0.0
    buffett_coupon_spread: Dict[str, Any] = field(default_factory=dict)
    quant_quality_filters: Dict[str, Any] = field(default_factory=dict)
    capital_allocation: Dict[str, Any] = field(default_factory=dict)
    # How much of this valuation rests on real inputs vs defaults.
    data_quality: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["models"] = [m.to_dict() if isinstance(m, ModelValuationOutput) else m for m in self.models]
        d["wacc_result"] = self.wacc_result.to_dict() if isinstance(self.wacc_result, WACCResult) else self.wacc_result
        d["wacc"] = d["wacc_result"]  # frontend compatibility alias
        d["risk_firewall"] = self.risk_firewall.to_dict() if isinstance(self.risk_firewall, RiskFirewallResult) else self.risk_firewall
        sc_dict = self.scenarios.to_dict() if isinstance(self.scenarios, ScenarioResult) else self.scenarios
        d["scenarios"] = sc_dict
        d["composite_status"] = self.valuation_status.lower()
        d["composite_mos_target_price"] = round(self.composite_fair_value * (1.0 - self.margin_of_safety_pct / 100.0), 0)
        d["valuation_width_pct"] = self.valuation_width_pct
        d["buffett_coupon_spread"] = self.buffett_coupon_spread
        d["quant_quality_filters"] = self.quant_quality_filters
        d["capital_allocation"] = self.capital_allocation
        
        # 5x5 sensitivity grid compatibility mapping for UI table renderer
        grid_rows = []
        if isinstance(self.scenarios, ScenarioResult):
            headers_wacc = self.scenarios.sensitivity_headers_wacc
            headers_growth = self.scenarios.sensitivity_headers_growth
            grid_5x5 = self.scenarios.sensitivity_grid_5x5
            for w_val, row in zip(headers_wacc, grid_5x5):
                grid_rows.append({
                    "wacc": w_val,
                    "growth_rates": {str(g_val): cell_val for g_val, cell_val in zip(headers_growth, row)}
                })
        d["sensitivity_grid"] = grid_rows
        return d


# =============================================================================
# WACC & 5-FACTOR VIETNAM CAPM ENGINE
# =============================================================================

class WACCEngine:
    """
    Computes Cost of Equity (Ke) using 5-Factor Vietnam CAPM,
    Cost of Debt (Kd) via Damodaran Synthetic Credit Ratings,
    and the final Weighted Average Cost of Capital (WACC).
    """

    @staticmethod
    def calculate(
        market_cap: float,
        interest_bearing_debt: float,
        ebit: float,
        interest_expense: float,
        beta_raw: float = 1.0,
        roe: float = 15.0,
        pb: float = 1.5,
        pb_sector_median: float = 1.5,
        adtv: float = 15e9,            # Average daily turnover in VND
        r12m: float = 0.15,            # 12-Month Price Return
        r1m: float = 0.02,             # 1-Month Price Return
        rf: float = DEFAULT_RF,
        erp: float = DEFAULT_ERP,
        tax_rate: float = DEFAULT_TAX_RATE,
    ) -> WACCResult:
        """
        Calculates WACC, 5-Factor Vietnam CAPM Ke, Damodaran Kd, and details.
        """
        # 1. Blume / Vasicek Adjusted Beta
        beta_clean = 1.0 if (math.isnan(beta_raw) or beta_raw <= 0) else beta_raw
        beta_adj = 0.67 * beta_clean + 0.33 * 1.0

        # 2. Factor: Size (SMB - Small Minus Big)
        # Market Cap in Billion VND
        mcap_b = market_cap / 1e9 if market_cap > 0 else 5000.0
        if mcap_b > 25000:
            smb_premium = 0.0000
        elif mcap_b > 5000:
            smb_premium = 0.0100  # 1.00% for mid caps (5,000 - 25,000B)
        elif mcap_b > 1000:
            smb_premium = 0.0200  # 2.00% for small caps (1,000 - 5,000B)
        else:
            smb_premium = 0.0300  # 3.00% for micro caps (< 1,000B)

        # 3. Factor: Value (HML - High Minus Low Book-to-Market)
        sec_pb = max(pb_sector_median, 0.1)
        cur_pb = max(pb, 0.1)
        # Value stocks (low PB) have higher fundamental distress risk premium.
        # Glamour stocks (high PB) have lower fundamental distress risk premium.
        h = clamp((sec_pb - cur_pb) / sec_pb, -1.0, 1.0)
        hml_val = 0.0150
        hml_premium = h * hml_val

        # 4. Factor: Momentum (UMD - Up Minus Down 12M-1M)
        mom_spread = r12m - r1m
        m = -clamp(mom_spread / 0.30, -1.0, 1.0) * 0.5 # Contrarian factor premium
        umd_val = 0.0100
        umd_premium = m * umd_val

        # 5. Factor: Amihud Illiquidity (ILLIQ)
        adtv_b = adtv / 1e9 if adtv > 0 else 15.0
        if adtv_b > 50.0:
            illiq_premium = 0.0000
        elif adtv_b > 10.0:
            illiq_premium = 0.0050
        elif adtv_b > 2.0:
            illiq_premium = 0.0125
        else:
            illiq_premium = 0.0250

        # 6. Factor: Profitability (RMW - Robust Minus Weak Operating Profitability)
        clean_roe = 15.0 if math.isnan(roe) else roe
        r = clamp((15.0 - clean_roe) / 10.0, -1.0, 1.0)
        rmw_val = 0.0120
        rmw_premium = r * rmw_val

        # 7. Unbounded & Bounded Cost of Equity (Ke)
        ke_raw = rf + (beta_adj * erp) + smb_premium + hml_premium + umd_premium + illiq_premium + rmw_premium
        ke = clamp(ke_raw, 0.085, 0.220)

        # 8. Cost of Debt (Kd) via Damodaran Synthetic Credit Rating Table
        clean_interest = max(interest_expense, 0.0)
        clean_ebit = ebit if not math.isnan(ebit) else 0.0

        if clean_ebit <= 0:
            # Distressed operating loss -> lowest rating D and distressed spread
            icr = -1.0
        elif clean_interest <= 0:
            # Profitable operations with zero debt interest
            icr = 100.0
        else:
            icr = clean_ebit / max(clean_interest, 1.0)

        table = DAMODARAN_SPREAD_LARGE_CAP if mcap_b > 5000.0 else DAMODARAN_SPREAD_SMALL_CAP
        synth_rating = "D"
        spread = 0.1250
        for min_icr, rating, sp in table:
            if icr >= min_icr:
                synth_rating = rating
                spread = sp
                break

        kd_pre_tax = rf + spread
        kd_after_tax = kd_pre_tax * (1.0 - tax_rate)

        # 9. Capital Structure Weights & WACC
        e_val = max(market_cap, 0.0)
        d_val = max(interest_bearing_debt, 0.0)
        v_val = e_val + d_val

        if v_val > 0:
            we = clamp(e_val / v_val, 0.20, 1.00)
            wd = 1.0 - we
        else:
            we, wd = 1.0, 0.0

        wacc_raw = (we * ke) + (wd * kd_after_tax)
        wacc = clamp(wacc_raw, 0.085, 0.185)

        return WACCResult(
            cost_of_equity=round(ke, 4),
            cost_of_debt_pre_tax=round(kd_pre_tax, 4),
            cost_of_debt_after_tax=round(kd_after_tax, 4),
            synthetic_rating=synth_rating,
            credit_spread=round(spread, 4),
            wacc=round(wacc, 4),
            equity_weight=round(we, 4),
            debt_weight=round(wd, 4),
            rf=round(rf, 4),
            erp=round(erp, 4),
            beta_adj=round(beta_adj, 4),
            smb_premium=round(smb_premium, 4),
            hml_premium=round(hml_premium, 4),
            umd_premium=round(umd_premium, 4),
            illiq_premium=round(illiq_premium, 4),
            rmw_premium=round(rmw_premium, 4),
            market_cap=market_cap,
            interest_bearing_debt=interest_bearing_debt,
            tax_rate=tax_rate,
            details={
                "icr": round(icr, 2),
                "ke_unbounded": round(ke_raw, 4),
                "wacc_unbounded": round(wacc_raw, 4),
            }
        )


# =============================================================================
# RISK FIREWALLS & ANTI-TRAP DIAGNOSTICS ENGINE
# =============================================================================

class RiskFirewallEngine:
    """
    Evaluates institutional risk firewalls:
    1. 4-Quadrant Altman Z'' (Emerging Markets) + Beneish M-Score
    2. Rhodes-Kropf (RKV) Enterprise Valuation Decomposition
    3. Dynamic Margin of Safety scaled by Downside Beta (beta_-)
    """

    @staticmethod
    def calculate_altman_z_double_prime(
        working_capital: float,
        retained_earnings: float,
        ebit: float,
        book_equity: float,
        total_assets: float,
        total_liabilities: float,
    ) -> Tuple[float, str]:
        """
        Emerging Market 4-Factor Altman Z''-Score:
        Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
        """
        ta = max(total_assets, 1.0)
        tl = max(total_liabilities, 1.0)

        x1 = working_capital / ta
        x2 = retained_earnings / ta
        x3 = ebit / ta
        x4 = book_equity / tl

        z_score = (6.56 * x1) + (3.26 * x2) + (6.72 * x3) + (1.05 * x4)

        if z_score >= 2.60:
            zone = "safe"
        elif z_score >= 1.10:
            zone = "grey"
        else:
            zone = "distress"

        return round(z_score, 4), zone

    @staticmethod
    def calculate_beneish_m_score(
        dsri: float = 1.0,
        gmi: float = 1.0,
        aqi: float = 1.0,
        sgi: float = 1.0,
        depi: float = 1.0,
        sgai: float = 1.0,
        tata: float = 0.0,
        lvgi: float = 1.0,
    ) -> Tuple[float, str]:
        """
        Beneish 8-Variable M-Score:
        M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
            + 0.115*DEPI - 0.172*SGAI + 4.037*TATA + 0.0327*LVGI
        Threshold: M < -1.78 is Safe, M >= -1.78 indicates earnings manipulation.
        """
        m_score = (
            -4.84
            + (0.920 * dsri)
            + (0.528 * gmi)
            + (0.404 * aqi)
            + (0.892 * sgi)
            + (0.115 * depi)
            - (0.172 * sgai)
            + (4.037 * tata)
            + (0.0327 * lvgi)
        )

        status = "manipulator" if m_score >= -1.78 else "safe"
        return round(m_score, 4), status

    @staticmethod
    def evaluate_four_quadrants(z_score: float, m_score: float) -> str:
        """
        Assigns one of the 4 diagnostic quadrants:
        - safe_institutional (Q1): Z'' >= 2.60 and M < -1.78
        - distressed_turnaround (Q2): Z'' < 1.10 and M < -1.78
        - toxic_exclusion (Q3): Z'' < 1.10 and M >= -1.78
        - forensic_trap (Q4): Z'' >= 1.10 and M >= -1.78
        """
        is_safe_z = z_score >= 2.60
        is_distress_z = z_score < 1.10
        is_manipulator_m = m_score >= -1.78

        if not is_manipulator_m:
            if is_safe_z or (z_score >= 1.10):
                return "safe_institutional"
            return "distressed_turnaround"
        else:
            if is_distress_z:
                return "toxic_exclusion"
            return "forensic_trap"

    @staticmethod
    def calculate_rhodes_kropf(
        market_cap: float,
        book_equity: float,
        roe: float,
        ke: float,
        sector_pb: float,
    ) -> Dict[str, Any]:
        """
        Rhodes-Kropf Enterprise Valuation Decomposition:
        ln(M/B) = (m - v_i) [Firm Misvaluation] + (v_i - v_j) [Sector Drift] + (v_j - b) [Long-Run Growth]
        """
        m = math.log(max(market_cap, 1.0))
        b = math.log(max(book_equity, 1.0))
        ln_mb = m - b

        # Fundamental justified PB from Gordon Growth model
        g = min(max(roe * 0.5, 0.0), 0.06)
        justified_pb = (roe - g) / max(ke - g, 0.015)
        justified_pb = clamp(justified_pb, 0.2, 8.0)

        v_i = b + math.log(justified_pb)
        v_j = b + math.log(max(sector_pb, 0.2))

        firm_misval = m - v_i
        sector_error = v_i - v_j
        long_run_growth = v_j - b

        v_b = justified_pb
        p_v = math.exp(clamp(firm_misval, -10.0, 10.0))
        current_pb = safe_div(market_cap, max(book_equity, 1.0), 1.0)

        is_firm_overvalued = firm_misval > math.log(1.30)
        is_firm_undervalued = firm_misval < -math.log(1.30)
        is_sector_trap = long_run_growth < 0.0
        is_value_trap = (current_pb < 1.5) and (v_b < 1.0)
        is_deep_value = (current_pb < 1.5) and (p_v < 0.85)

        rkv_verdict = "VALUE TRAP (Deserved Discount)" if is_value_trap else ("TRUE DEEP VALUE" if is_deep_value else ("OVERVALUED" if is_firm_overvalued else ("UNDERVALUED" if is_firm_undervalued else "FAIR")))

        return {
            "ln_mb": round(ln_mb, 4),
            "firm_misvaluation": round(firm_misval, 4),
            "sector_time_series_error": round(sector_error, 4),
            "long_run_sector_growth": round(long_run_growth, 4),
            "justified_pb": round(justified_pb, 2),
            "rkv_growth_vb": round(v_b, 2),
            "rkv_mispricing_mv": round(p_v, 2),
            "is_firm_overvalued": is_firm_overvalued,
            "is_firm_undervalued": is_firm_undervalued,
            "is_sector_trap": is_sector_trap,
            "is_value_trap": is_value_trap,
            "is_deep_value": is_deep_value,
            "rkv_verdict": rkv_verdict,
            "status": "OVERVALUED" if is_firm_overvalued else ("UNDERVALUED" if is_firm_undervalued else "FAIR"),
        }

    @staticmethod
    def calculate_dynamic_mos(
        downside_beta: float = 1.0,
        base_mos: float = DEFAULT_BASE_MOS,
        altman_zone: str = "safe",
        beneish_status: str = "safe",
        de_ratio: float = 0.5,
        liquidity_distress_penalty: float = 0.0,
    ) -> float:
        """
        Dynamic Margin of Safety scaled by Downside Beta and Risk Firewalls (Requirement R3):
        MOS_dynamic = MOS_base * max(0.7, min(2.0, 1.0 + 0.5 * (beta_- - 1.0))) + Delta_Risk + Delta_LiquidityDistress
        """
        beta_scale = clamp(1.0 + 0.5 * (downside_beta - 1.0), 0.70, 2.00)
        dynamic_mos = base_mos * beta_scale

        # Additive Risk Penalties
        if altman_zone == "grey":
            dynamic_mos += 0.05
        elif altman_zone == "distress":
            dynamic_mos += 0.10

        if beneish_status == "manipulator":
            dynamic_mos += 0.10

        if de_ratio > 1.5:
            dynamic_mos += 0.05

        if liquidity_distress_penalty > 0.0:
            dynamic_mos += liquidity_distress_penalty

        return round(clamp(dynamic_mos, 0.10, 0.60), 4)

    @classmethod
    def evaluate(
        cls,
        fundamental_data: Dict[str, Any],
        wacc_res: WACCResult,
        sector_pb: float = 1.5,
        price_returns: Optional[List[float]] = None,
        market_returns: Optional[List[float]] = None,
    ) -> RiskFirewallResult:
        """Runs full risk firewall diagnostic pipeline."""
        price = _require_price(str(fundamental_data.get("symbol") or "?"), fundamental_data)
        shares = max(float(fundamental_data.get("shares_out") or fundamental_data.get("shares") or 1e8), 1.0)
        mcap = float(fundamental_data.get("market_cap") or (price * shares))

        bvps_val = float(fundamental_data.get("bvps") or 0.0)
        equity_from_bvps = bvps_val * shares if bvps_val > 0 else 0.0

        total_liabilities = float(fundamental_data.get("total_liabilities") or fundamental_data.get("debt") or (mcap * 0.5))
        book_equity = float(fundamental_data.get("book_equity") or fundamental_data.get("equity") or (equity_from_bvps if equity_from_bvps > 0 else max(mcap * 0.5, 1.0)))
        total_assets = float(fundamental_data.get("total_assets") or fundamental_data.get("assets") or (book_equity + total_liabilities))

        working_capital = float(fundamental_data.get("working_capital") or ((total_assets - total_liabilities) * 0.25))
        retained_earnings = float(fundamental_data.get("retained_earnings") or ((total_assets - total_liabilities) * 0.20))
        ebit = float(fundamental_data.get("ebit") or fundamental_data.get("operating_profit") or (mcap * 0.12))
        roe_raw = fundamental_data.get("roe") or 15.0
        roe = float(roe_raw) / 100.0 if float(roe_raw) > 1.0 else float(roe_raw)
        de_ratio = float(fundamental_data.get("de_ratio") or safe_div(total_liabilities, book_equity, 0.5))

        # 1. Altman Z''
        z_score, altman_zone = cls.calculate_altman_z_double_prime(
            working_capital=working_capital,
            retained_earnings=retained_earnings,
            ebit=ebit,
            book_equity=book_equity,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
        )

        # 2. Beneish M
        dsri = float(fundamental_data.get("beneish_dsri") or 1.0)
        gmi = float(fundamental_data.get("beneish_gmi") or 1.0)
        aqi = float(fundamental_data.get("beneish_aqi") or 1.0)
        sgi = float(fundamental_data.get("beneish_sgi") or 1.0)
        depi = float(fundamental_data.get("beneish_depi") or 1.0)
        sgai = float(fundamental_data.get("beneish_sgai") or 1.0)
        tata = float(fundamental_data.get("beneish_tata") if fundamental_data.get("beneish_tata") is not None else 0.0)
        lvgi = float(fundamental_data.get("beneish_lvgi") or 1.0)

        # If direct m_score passed in
        if fundamental_data.get("beneish_m_score") is not None:
            m_score = float(fundamental_data["beneish_m_score"])
            beneish_status = "manipulator" if m_score >= -1.78 else "safe"
        else:
            m_score, beneish_status = cls.calculate_beneish_m_score(
                dsri=dsri, gmi=gmi, aqi=aqi, sgi=sgi, depi=depi, sgai=sgai, tata=tata, lvgi=lvgi
            )

        # 3. 4-Quadrant Category
        quadrant = cls.evaluate_four_quadrants(z_score, m_score)

        # 4. Rhodes-Kropf
        rkv = cls.calculate_rhodes_kropf(
            market_cap=mcap,
            book_equity=book_equity,
            roe=roe,
            ke=wacc_res.cost_of_equity,
            sector_pb=sector_pb,
        )

        # 5. Downside Beta
        downside_beta = float(fundamental_data.get("downside_beta") or 1.0)
        if price_returns and market_returns and len(price_returns) == len(market_returns) and len(price_returns) > 20:
            rf_daily = DEFAULT_RF / 252.0
            down_pairs = [(p, m) for p, m in zip(price_returns, market_returns) if m < rf_daily]
            if len(down_pairs) > 5:
                p_down = [p for p, m in down_pairs]
                m_down = [m for p, m in down_pairs]
                m_mean = sum(m_down) / len(m_down)
                p_mean = sum(p_down) / len(p_down)
                var_m = sum((m - m_mean) ** 2 for m in m_down)
                cov_pm = sum((p - p_mean) * (m - m_mean) for p, m in down_pairs)
                if var_m > 1e-9:
                    downside_beta = cov_pm / var_m

        # 6. Liquidity Distress Firewall & Dynamic MOS (Requirement R3)
        distress_penalty = 0.0
        distress_details = fundamental_data.get("liquidity_distress") or fundamental_data.get("liquidity_distress_check")
        if isinstance(distress_details, dict):
            distress_penalty = float(distress_details.get("mos_penalty_pct") or 0.0)
        elif hasattr(distress_details, "mos_penalty_pct"):
            distress_penalty = float(getattr(distress_details, "mos_penalty_pct", 0.0))
        elif fundamental_data.get("has_negative_cash") or fundamental_data.get("is_cash_distressed"):
            distress_penalty = 0.10

        dynamic_mos = cls.calculate_dynamic_mos(
            downside_beta=downside_beta,
            base_mos=DEFAULT_BASE_MOS,
            altman_zone=altman_zone,
            beneish_status=beneish_status,
            de_ratio=de_ratio,
            liquidity_distress_penalty=distress_penalty,
        )

        # Firewall pass/fail rules
        firewall_passed = True
        disqualification_reason = None
        if quadrant == "toxic_exclusion":
            firewall_passed = False
            disqualification_reason = "Toxic Exclusion: High Bankruptcy Distress (Z'' < 1.10) & Accounting Manipulation (M >= -1.78)"
        elif quadrant == "forensic_trap":
            firewall_passed = False
            disqualification_reason = "Forensic Trap: High Earnings Manipulation Risk (M >= -1.78)"

        return RiskFirewallResult(
            altman_z_score=z_score,
            altman_zone=altman_zone,
            beneish_m_score=m_score,
            beneish_status=beneish_status,
            four_quadrant_category=quadrant,
            rhodes_kropf=rkv,
            downside_beta=round(downside_beta, 4),
            dynamic_margin_of_safety=dynamic_mos,
            firewall_passed=firewall_passed,
            disqualification_reason=disqualification_reason,
            details={
                "de_ratio": round(de_ratio, 2),
                "is_sector_trap": rkv["is_sector_trap"],
                "liquidity_distress": distress_details,
                "liquidity_distress_penalty": distress_penalty,
            }
        )


# =============================================================================
# THE 22 QUANTITATIVE VALUATION MODELS ENGINE
# =============================================================================

class ValuationModelsSuite:
    """
    Implements exact mathematical formulas for all 22 intrinsic and relative
    valuation models with strict non-negativity guarantees and boundary caps.
    """

    # -------------------------------------------------------------------------
    # 8 RELATIVE MULTIPLE MODELS
    # -------------------------------------------------------------------------

    @staticmethod
    def model_1_blended_pe(
        eps_ttm: float,
        historical_eps: List[float],
        sector_pe: float = 12.0,
        hist_pe: float = 11.0,
        eps_growth_rate: float = 0.10,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 1: Blended P/E & Cyclically Adjusted CAPE Multiplier.
        Target P/E = 0.40 * sector_pe + 0.35 * hist_pe + 0.25 * peg_derived_pe
        FV = Target P/E * (0.60 * EPS_TTM + 0.40 * EPS_cyclical)
        """
        current_price = _model_price(current_price, "model_1_blended_pe")
        peg_derived_pe = clamp(eps_growth_rate * 100.0 * 1.0, 8.0, 22.0)
        target_pe = (0.40 * max(sector_pe, 2.0)) + (0.35 * max(hist_pe, 2.0)) + (0.25 * peg_derived_pe)
        target_pe = clamp(target_pe, 4.0, 35.0)

        # 5-Year cyclical EPS weighting
        if historical_eps and len(historical_eps) > 0:
            weights = [0.35, 0.25, 0.20, 0.12, 0.08][:len(historical_eps)]
            norm_w = [w / sum(weights) for w in weights]
            eps_cyclical = sum(w * eps for w, eps in zip(norm_w, historical_eps))
        else:
            eps_cyclical = eps_ttm

        blended_eps = 0.60 * eps_ttm + 0.40 * eps_cyclical
        if blended_eps <= 0:
            # A company with no blended earnings cannot be valued on an
            # earnings multiple. Previously earnings were synthesised from the
            # price, so a loss-maker still received a positive P/E valuation.
            return 0.0

        fv = target_pe * blended_eps
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_2_ps_margin_adjusted(
        sales_per_share: float,
        net_margin: float,
        sector_ps: float = 1.2,
        sector_net_margin: float = 0.08,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 2: Margin-Adjusted Price-to-Sales (P/S) Multiplier.
        Target P/S = sector_ps * (net_margin / sector_net_margin)^0.65
        FV = Target P/S * SPS
        """
        current_price = _model_price(current_price, "model_2_ps_margin_adjusted")
        if net_margin <= 0.0:
            # Heavily loss-making firms do not deserve high P/S valuation
            return 0.0

        sec_nm = max(sector_net_margin, 0.01)
        cur_nm = max(net_margin, 0.005)
        margin_factor = (cur_nm / sec_nm) ** 0.65
        target_ps = max(sector_ps, 0.2) * margin_factor
        target_ps = clamp(target_ps, 0.10 * max(sector_ps, 0.2), 3.0 * max(sector_ps, 0.2))

        if sales_per_share <= 0:
            return 0.0
        fv = target_ps * sales_per_share
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_3_p_fcf(
        fcf_per_share: float,
        sales_per_share: float,
        sector_pfcf: float = 14.0,
        hist_pfcf: float = 12.0,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 3: Price-to-Free Cash Flow (P/FCF).
        Target P/FCF = median(sector_pfcf, hist_pfcf, 15.0)
        FV = Target P/FCF * max(FCF_per_share, 0.05 * SPS)
        """
        current_price = _model_price(current_price, "model_3_p_fcf")
        target_pfcf = float(sorted([max(sector_pfcf, 3.0), max(hist_pfcf, 3.0), 15.0])[1])
        target_pfcf = clamp(target_pfcf, 5.0, 30.0)

        if fcf_per_share <= 0:
            # Negative free cash flow has no P/FCF valuation.
            return 0.0
        fv = target_pfcf * fcf_per_share
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_4_pb_rhodes_kropf(
        bvps: float,
        roe: float,
        ke: float,
        sector_pb: float = 1.5,
        rkv_is_overvalued: bool = False,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 4: Price-to-Book (P/B) with Rhodes-Kropf (RKV) Filter.
        Justified P/B = (ROE - g) / (Ke - g)
        Target P/B = 0.50 * Justified P/B + 0.50 * sector_pb
        Haircut by 15% if firm-specific misvaluation exceeds 30%.
        """
        current_price = _model_price(current_price, "model_4_pb_rhodes_kropf")
        if bvps <= 0:
            # Negative book value has no P/B valuation.
            return 0.0
        clean_bvps = bvps
        g = min(max(roe * 0.4, 0.0), 0.06)
        justified_pb = (roe - g) / max(ke - g, 0.015)
        justified_pb = clamp(justified_pb, 0.3, 6.0)

        target_pb = 0.50 * justified_pb + 0.50 * max(sector_pb, 0.3)
        target_pb = clamp(target_pb, 0.4, 8.0)

        haircut = 0.85 if rkv_is_overvalued else 1.00
        fv = target_pb * clean_bvps * haircut
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_5_p_tbv(
        tbv_per_share: float,
        bvps: float,
        roic: float,
        wacc: float,
        sector_ptbv: float = 1.4,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 5: Price-to-Tangible Book Value (P/TBV).
        Target P/TBV = sector_ptbv * clamp(ROIC / WACC, 0.6, 1.8)
        FV = Target P/TBV * TBVPS (fallback to 0.5 * BVPS if TBV <= 0).
        """
        current_price = _model_price(current_price, "model_5_p_tbv")
        if tbv_per_share > 0:
            clean_tbv = tbv_per_share
        elif bvps > 0:
            clean_tbv = 0.50 * bvps
        else:
            return 0.0
        roic_wacc_ratio = clamp(safe_div(roic, wacc, 1.0), 0.60, 1.80)
        target_ptbv = max(sector_ptbv, 0.3) * roic_wacc_ratio
        target_ptbv = clamp(target_ptbv, 0.3, 6.0)

        fv = target_ptbv * clean_tbv
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_6_ev_ebitda(
        ebitda: float,
        total_debt: float,
        cash_and_equiv: float,
        shares_out: float,
        minority_interest: float = 0.0,
        sector_ev_ebitda: float = 8.5,
        hist_ev_ebitda: float = 8.0,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 6: Blended EV/EBITDA Enterprise Multiple.
        Implied EV = Target EV/EBITDA * EBITDA
        Equity Value = EV - Total Debt + Cash - Minority
        """
        current_price = _model_price(current_price, "model_6_ev_ebitda")
        shares = max(shares_out, 1.0)
        target_mult = (0.60 * max(sector_ev_ebitda, 3.0)) + (0.40 * max(hist_ev_ebitda, 3.0))
        target_mult = clamp(target_mult, 4.0, 25.0)

        if ebitda <= 0:
            return 0.0
        implied_ev = target_mult * ebitda
        equity_val = implied_ev - max(total_debt, 0.0) + max(cash_and_equiv, 0.0) - max(minority_interest, 0.0)
        if equity_val <= 0:
            # Debt exceeds enterprise value: the equity is worthless on this
            # multiple, which is a real answer, not a reason to floor at 10%
            # of market cap.
            return 0.0
        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_7_p_cf(
        cfo_per_share: float,
        pat_per_share: float,
        sector_pcf: float = 9.0,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 7: Price-to-Operating Cash Flow (P/CF).
        Target P/CF = median(sector_pcf, 8.5) * (1 + 0.5 * min(CFO_to_PAT - 1.0, 0.5))
        FV = Target P/CF * max(CFO_per_share, 0.03 * Price)
        """
        current_price = _model_price(current_price, "model_7_p_cf")
        cfo_to_pat = safe_div(cfo_per_share, max(pat_per_share, 1.0), 1.0)
        quality_adj = 1.0 + 0.5 * clamp(cfo_to_pat - 1.0, -0.5, 0.5)
        target_pcf = max(sector_pcf, 2.0) * quality_adj
        target_pcf = clamp(target_pcf, 3.5, 25.0)

        if cfo_per_share <= 0:
            return 0.0
        fv = target_pcf * cfo_per_share
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_8_p_affo(
        affo: float,
        net_income: float,
        shares_out: float,
        sector_paffo: float = 12.0,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 8: Price-to-AFFO Multiple (P/AFFO).
        Target P/AFFO = median(sector_paffo, 12.0)
        FV = Target P/AFFO * max(AFFO, 0.5 * Net Income) / Shares
        """
        current_price = _model_price(current_price, "model_8_p_affo")
        shares = max(shares_out, 1.0)
        target_paffo = clamp(max(sector_paffo, 4.0), 5.0, 25.0)
        clean_affo = max(affo, 0.50 * max(net_income, 1.0))
        fv = (target_paffo * clean_affo) / shares
        return clamp(fv, 0.0, current_price * 10.0)

    # -------------------------------------------------------------------------
    # 7 ABSOLUTE INTRINSIC MODELS
    # -------------------------------------------------------------------------

    @staticmethod
    def model_9_dcf_2stage_mckinsey(
        ebit: float,
        roic: float,
        wacc: float,
        shares_out: float,
        cash_and_equiv: float = 0.0,
        total_debt: float = 0.0,
        minority_interest: float = 0.0,
        g_stage1: float = 0.10,
        g_terminal: float = DEFAULT_TERMINAL_G,
        tax_rate: float = DEFAULT_TAX_RATE,
        current_price: float = _PRICE_REQUIRED,
        explicit_fcff_series: Optional[List[float]] = None,
    ) -> float:
        """
        Model 9: Extended 2-Stage Value Driver DCF (McKinsey / ROIC Framework)
        with support for explicit 5-year dynamic cash flows from 3-Way Engine.
        FCFF_t = NOPAT_t * (1 - g_t / ROIC_t)
        Terminal FCFF = NOPAT_5 * (1 + g_n) * (1 - g_n / ROIC_term)
        TV = Terminal FCFF / (WACC - g_n)
        """
        current_price = _model_price(current_price, "model_9_dcf_2stage_mckinsey")
        shares = max(shares_out, 1.0)
        gn = clamp(g_terminal, 0.02, 0.045)
        w = max(wacc, gn + 0.015) # Prevent denominator singularity

        if explicit_fcff_series and len(explicit_fcff_series) >= 5:
            pv_fcff_sum = sum(explicit_fcff_series[t] / ((1.0 + w) ** (t + 1)) for t in range(5))
            last_fcff = explicit_fcff_series[4]
            terminal_fcff = last_fcff * (1.0 + gn)
            tv_5 = terminal_fcff / (w - gn)
            pv_tv = tv_5 / ((1.0 + w) ** 5)
        else:
            nopat_0 = ebit * (1.0 - tax_rate)
            if nopat_0 <= 0:
                return 0.0
            g1 = clamp(g_stage1, 0.03, 0.22)

            clean_roic1 = clamp(roic, 0.08, 0.40)
            clean_roic_term = clamp(min(clean_roic1 * 0.75, max(w + 0.02, clean_roic1 * 0.50)), 0.08, 0.30)

            pv_fcff_sum = 0.0
            nopat_t = nopat_0
            for t in range(1, 6):
                nopat_t = nopat_0 * ((1.0 + g1) ** t)
                reinvestment_rate = clamp(g1 / clean_roic1, 0.10, 0.90)
                fcff_t = nopat_t * (1.0 - reinvestment_rate)
                pv_fcff_sum += fcff_t / ((1.0 + w) ** t)

            reinv_term = clamp(gn / clean_roic_term, 0.10, 0.85)
            terminal_fcff = nopat_t * (1.0 + gn) * (1.0 - reinv_term)
            tv_5 = terminal_fcff / (w - gn)
            pv_tv = tv_5 / ((1.0 + w) ** 5)

        enterprise_value = pv_fcff_sum + pv_tv
        equity_val = enterprise_value + max(cash_and_equiv, 0.0) - max(total_debt, 0.0) - max(minority_interest, 0.0)
        if equity_val <= 0:
            return 0.0

        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_10_rim_edwards_bell_ohlson(
        book_equity: float,
        roe_base: float,
        ke: float,
        shares_out: float,
        payout_ratio: float = 0.30,
        g_terminal: float = DEFAULT_TERMINAL_G,
        omega_fade: float = 0.85,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 10: Residual Income Model (RIM / Edwards-Bell-Ohlson).
        RI_t = (ROE_t - Ke) * Book_Value_{t-1}
        Continuing RI = (RI_5 * (1 + g)) / (1 + Ke - omega)
        Equity Value = BV_0 + sum(PV(RI_t)) + PV(Continuing RI)
        """
        current_price = _model_price(current_price, "model_10_rim_edwards_bell_ohlson")
        shares = max(shares_out, 1.0)
        if book_equity <= 0:
            # Negative book equity has no residual-income anchor.
            return 0.0
        bv_0 = book_equity
        clean_ke = max(ke, 0.085)
        clean_roe = clamp(roe_base, 0.05, 0.40)
        payout = clamp(payout_ratio, 0.0, 0.80)

        pv_ri_sum = 0.0
        bv_prev = bv_0
        ri_5 = 0.0
        target_sustainable_roe = clamp(clean_roe * 0.85, 0.12, 0.22)

        for t in range(1, 6):
            # Gradual convergence toward target sustainable ROE
            roe_t = clean_roe + (target_sustainable_roe - clean_roe) * (t / 10.0)
            ri_t = (roe_t - clean_ke) * bv_prev
            if t == 5:
                ri_5 = ri_t
            pv_ri_sum += ri_t / ((1.0 + clean_ke) ** t)
            bv_prev = bv_prev * (1.0 + roe_t * (1.0 - payout))

        denom = max(1.0 + clean_ke - omega_fade, 0.02)
        continuing_ri = (ri_5 * (1.0 + g_terminal)) / denom
        pv_cont_ri = continuing_ri / ((1.0 + clean_ke) ** 5)

        equity_val = bv_0 + pv_ri_sum + pv_cont_ri
        if equity_val <= 0:
            return 0.0

        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_11_greenwald_epv(
        revenue: float,
        ebit_margin_avg: float,
        wacc: float,
        shares_out: float,
        cash_and_equiv: float = 0.0,
        total_debt: float = 0.0,
        depreciation: float = 0.0,
        maintenance_capex: float = 0.0,
        tax_rate: float = DEFAULT_TAX_RATE,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 11: Greenwald Earnings Power Value (EPV).
        NOPAT_norm = Normalized_EBIT * (1 - tc) + Depr - MaintCapEx
        EPV_firm = NOPAT_norm / WACC
        EPV_equity = EPV_firm + Cash - Debt
        """
        current_price = _model_price(current_price, "model_11_greenwald_epv")
        shares = max(shares_out, 1.0)
        margin = clamp(ebit_margin_avg, 0.03, 0.35)
        if revenue <= 0:
            return 0.0
        norm_ebit = margin * revenue

        nopat_norm = norm_ebit * (1.0 - tax_rate)
        if depreciation > 0 and maintenance_capex > 0:
            nopat_norm += (depreciation - maintenance_capex)
        if nopat_norm <= 0:
            return 0.0

        w = max(wacc, 0.085)
        epv_firm = nopat_norm / w
        epv_equity = epv_firm + max(cash_and_equiv, 0.0) - max(total_debt, 0.0)
        if epv_equity <= 0:
            return 0.0

        fv = epv_equity / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_12_graham_growth(
        eps_ttm: float,
        bvps: float,
        expected_growth_pct: float = 10.0,
        benchmark_bond_yield: float = 5.5,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 12: Benjamin Graham Growth Number & Modern Revised Formula.
        Classic Graham Number = sqrt(22.5 * max(EPS, 0) * max(BVPS, 0))
        Modern Revised Graham = EPS * (8.5 + 1.5g) * (4.4 / Y)
        FV = 0.50 * Classic + 0.50 * Growth
        """
        current_price = _model_price(current_price, "model_12_graham_growth")
        if eps_ttm <= 0.0 or bvps <= 0.0:
            return 0.0

        clean_eps = eps_ttm
        clean_bvps = bvps

        classic_fv = math.sqrt(22.5 * clean_eps * clean_bvps)

        g_val = clamp(expected_growth_pct, 1.0, 20.0)
        y_val = max(benchmark_bond_yield, 2.5)
        growth_fv = clean_eps * (8.5 + (1.5 * g_val)) * (4.4 / y_val)

        fv = 0.50 * classic_fv + 0.50 * growth_fv
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_13_rule_of_40_growth(
        sales_per_share: float,
        rev_growth_pct: float,
        fcf_margin_pct: float,
        base_ps: float = 1.5,
        total_revenue: float = 0.0,
        net_debt: float = 0.0,
        shares_out: float = 1.0,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 13: Rule of 40 & Rule of X (Super-Stock Hyper-Growth) Valuation.
        Rule 40 Score = RevGrowth% + FCFMargin%
        Rule X Score = 2.0 * RevGrowth% + FCFMargin%
        If Rule X >= 65% -> Super Stock EV/Sales multiple unlocked (12x to 25x).
        """
        current_price = _model_price(current_price, "model_13_rule_of_40_growth")
        rule_40_score = rev_growth_pct + fcf_margin_pct
        rule_x_score = (rev_growth_pct * 2.0) + fcf_margin_pct

        if rule_x_score >= 65.0:
            fair_multiple = 12.0 + (rule_x_score - 65.0) * 0.3
        elif rule_40_score < 10.0:
            fair_multiple = 1.5
        else:
            fair_multiple = 1.0 + (rule_40_score * 0.25)

        fair_multiple = clamp(fair_multiple, 1.0, 25.0)

        shares = max(shares_out, 1.0)
        if sales_per_share <= 0 and total_revenue <= 0:
            return 0.0
        sps = sales_per_share
        rev = total_revenue if total_revenue > 0 else sps * shares

        target_ev = fair_multiple * rev
        target_equity = target_ev - net_debt
        if target_equity <= 0:
            return 0.0

        fv = target_equity / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_14_acquirers_multiple(
        ebit: float,
        revenue: float,
        net_debt: float,
        shares_out: float,
        sector_ev_ebit: float = 8.0,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 14: Acquirer's Multiple (Tobias Carlisle EV/EBIT).
        Target Multiple = min(sector_ev_ebit, 10.0)
        Implied EV = Target Multiple * max(EBIT, 0.05 * Revenue)
        FV = max(Implied EV - Net Debt, 0.10 * Market Cap) / Shares
        """
        current_price = _model_price(current_price, "model_14_acquirers_multiple")
        shares = max(shares_out, 1.0)
        target_mult = clamp(sector_ev_ebit, 4.0, 10.0)
        if ebit <= 0:
            return 0.0

        implied_ev = target_mult * ebit
        equity_val = implied_ev - net_debt
        if equity_val <= 0:
            return 0.0

        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_15_buffett_owners_earnings(
        net_income: float,
        depreciation: float,
        maintenance_capex: float,
        delta_working_capital: float,
        ke: float,
        shares_out: float,
        growth_rate: float = 0.08,
        g_terminal: float = DEFAULT_TERMINAL_G,
        total_capex: float = 0.0,
        revenue: float = 0.0,
        prev_revenue: float = 0.0,
        gross_ppe: float = 0.0,
        ocf: float = 0.0,
        rf: float = DEFAULT_RF,
        current_price: float = _PRICE_REQUIRED,
        explicit_oe_series: Optional[List[float]] = None,
    ) -> float:
        """
        Model 15: Warren Buffett Owner's Earnings DCF with CapEx Decomposition
        and support for explicit 5-year dynamic cash flows from 3-Way Engine.
        Growth CapEx = max(0, Delta_Rev * (Gross_PPE / Revenue))
        Maintenance CapEx = max(0, Total_CapEx - Growth_CapEx)
        Owner Earnings = OCF - Maintenance CapEx (or NI + D&A - MaintCapEx - Delta_WC)
        """
        current_price = _model_price(current_price, "model_15_buffett_owners_earnings")
        shares = max(shares_out, 1.0)
        clean_ke = max(ke, g_terminal + 0.02)
        gn = clamp(g_terminal, 0.02, 0.04)

        if explicit_oe_series and len(explicit_oe_series) >= 5:
            pv_oe_sum = sum(explicit_oe_series[t] / ((1.0 + clean_ke) ** (t + 1)) for t in range(5))
            last_oe = explicit_oe_series[4]
            tv = (last_oe * (1.0 + gn)) / (clean_ke - gn)
            pv_tv = tv / ((1.0 + clean_ke) ** 5)
        else:
            # Decompose Growth vs Maintenance CapEx if revenue and PPE available
            if revenue > 0 and gross_ppe > 0 and total_capex > 0:
                clean_prev_rev = prev_revenue if prev_revenue > 0 else revenue * 0.90
                sales_growth_abs = max(0.0, revenue - clean_prev_rev)
                ppe_ratio = clamp(gross_ppe / revenue, 0.10, 3.0)
                growth_capex = min(sales_growth_abs * ppe_ratio, abs(total_capex))
                maint_capex_resolved = max(0.0, abs(total_capex) - growth_capex)
            else:
                maint_capex_resolved = maintenance_capex

            if ocf > 0:
                oe_0 = ocf - maint_capex_resolved
            else:
                oe_0 = net_income + depreciation - maint_capex_resolved - delta_working_capital
            if oe_0 <= 0:
                # Negative owner earnings: no Buffett-style valuation.
                return 0.0

            g = clamp(growth_rate, 0.03, 0.20)

            pv_oe_sum = 0.0
            oe_t = oe_0
            for t in range(1, 6):
                oe_t = oe_0 * ((1.0 + g) ** t)
                pv_oe_sum += oe_t / ((1.0 + clean_ke) ** t)

            tv = (oe_t * (1.0 + gn)) / (clean_ke - gn)
            pv_tv = tv / ((1.0 + clean_ke) ** 5)

        equity_val = pv_oe_sum + pv_tv
        if equity_val <= 0:
            return 0.0
        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    # -------------------------------------------------------------------------
    # 7 SECTOR-SPECIFIC VALUATION MODELS
    # -------------------------------------------------------------------------

    @staticmethod
    def model_16_pharma_rnpv(
        base_epv_per_share: float,
        pipeline_projects: Optional[List[Dict[str, float]]] = None,
        net_cash_per_share: float = 0.0,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 16: Risk-Adjusted NPV (rNPV) — Pharma & Biotech Pipeline (ICB 4500).
        rNPV = sum(p_s,k * NPV_k) + Base Business EPV + Net Cash
        """
        current_price = _model_price(current_price, "model_16_pharma_rnpv")
        if not pipeline_projects:
            pipeline_projects = [
                {"npv_per_share": 0.15 * current_price, "success_prob": 0.70}, # Phase III
                {"npv_per_share": 0.10 * current_price, "success_prob": 0.40}, # Phase II
            ]

        pipeline_rnpv = sum(p.get("npv_per_share", 0.0) * p.get("success_prob", 0.50) for p in pipeline_projects)
        if base_epv_per_share <= 0:
            # rNPV builds on the EPV base; without one there is nothing to
            # risk-adjust. The old floor pinned it at 60% of the market price.
            return 0.0
        fv = base_epv_per_share + pipeline_rnpv + max(net_cash_per_share, 0.0)
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_17_bank_equity_cash_flow(
        net_income: float,
        rwa: float,
        book_equity: float,
        roe: float,
        ke: float,
        shares_out: float,
        rwa_growth: float = 0.12,
        target_car: float = 0.11,
        g_terminal: float = DEFAULT_TERMINAL_G,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 17: Equity Cash Flow & Basel II CAR — Banks & Insurance (ICB 8300 / 8500).
        Required Equity_t = RWA_t * Target CAR
        FCFE_t = Net Income_t - Delta Required Equity_t
        Combined 60% ECF + 40% Justified P/B-ROE.
        """
        current_price = _model_price(current_price, "model_17_bank_equity_cash_flow")
        shares = max(shares_out, 1.0)
        if book_equity <= 0:
            return 0.0
        bvps = book_equity / shares
        clean_ke = max(ke, g_terminal + 0.02)
        gn = clamp(g_terminal, 0.025, 0.045)

        rwa_t = max(rwa, book_equity / target_car)
        ni_t = max(net_income, book_equity * roe)

        pv_fcfe = 0.0
        for t in range(1, 6):
            rwa_next = rwa_t * (1.0 + rwa_growth)
            req_equity_change = (rwa_next - rwa_t) * target_car
            ni_t = ni_t * (1.0 + rwa_growth)
            fcfe_t = max(ni_t - req_equity_change, 0.10 * ni_t)
            pv_fcfe += fcfe_t / ((1.0 + clean_ke) ** t)
            rwa_t = rwa_next

        tv_fcfe = (fcfe_t * (1.0 + gn)) / (clean_ke - gn)
        pv_tv_fcfe = tv_fcfe / ((1.0 + clean_ke) ** 5)

        ecf_per_share = (pv_fcfe + pv_tv_fcfe) / shares

        # P/B-ROE Justified Component
        justified_pb = max((roe - gn) / (clean_ke - gn), 0.5)
        justified_pb_val = bvps * justified_pb

        fv = 0.60 * ecf_per_share + 0.40 * justified_pb_val
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_18_reit_affo_dcf(
        net_operating_income: float,
        landbank_pipeline_val: float,
        cash_and_equiv: float,
        total_debt: float,
        shares_out: float,
        cap_rate_vn: float = 0.085,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 18: AFFO DCF & Cap Rate — Real Estate Developers & REITs (ICB 8600).
        Operating Portfolio Value = NOI / CapRate_VN
        RNAV = Operating Portfolio + Landbank Pipeline (discounted) + Cash - Debt
        """
        current_price = _model_price(current_price, "model_18_reit_affo_dcf")
        shares = max(shares_out, 1.0)
        if net_operating_income <= 0:
            return 0.0
        clean_noi = net_operating_income
        cap_rate = clamp(cap_rate_vn, 0.06, 0.12)
        portfolio_val = clean_noi / cap_rate

        rnav = portfolio_val + max(landbank_pipeline_val, 0.0) + max(cash_and_equiv, 0.0) - max(total_debt, 0.0)
        if rnav <= 0:
            return 0.0

        fv = rnav / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_19_telecom_unbundled_sotp(
        regulated_asset_base: float,
        serveco_ebitda: float,
        net_debt: float,
        shares_out: float,
        allowed_spread: float = 0.03,
        digital_multiple: float = 9.0,
        current_price: float = _PRICE_REQUIRED,
        wacc: float = 0.10,
        g_terminal: float = DEFAULT_TERMINAL_G,
        allowed_return: Optional[float] = None,
    ) -> float:
        """
        Model 19: Regulated Asset Base (RAB) & Unbundled Infrastructure Model (ICB 6500 / 7500).
        A regulated asset is worth its asset base scaled by the ratio of allowed return to required return:
        EV_RAB = RAB * (allowed_return - g) / (wacc - g)
        Equity Value = EV_RAB - Net Debt
        """
        current_price = _model_price(current_price, "model_19_telecom_unbundled_sotp")
        shares = max(shares_out, 1.0)
        clean_wacc = max(wacc, 0.06)
        g = min(max(g_terminal, 0.01), clean_wacc - 0.005)
        
        # Allowed return from regulator (defaults to WACC + allowed_spread or WACC)
        r = allowed_return if (allowed_return is not None and allowed_return > 0) else (clean_wacc + allowed_spread)
        
        # Exact Regulatory Asset Base Multiple
        rab_multiple = (r - g) / (clean_wacc - g)
        rab_multiple = clamp(rab_multiple, 0.50, 2.00)
        
        if regulated_asset_base <= 0:
            return 0.0
        ev_rab = regulated_asset_base * rab_multiple

        equity_val = ev_rab - net_debt
        if equity_val <= 0:
            return 0.0
        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_20_industrial_apv(
        ebit: float,
        total_debt: float,
        cash_and_equiv: float,
        shares_out: float,
        beta_unlevered: float = 0.90,
        rf: float = DEFAULT_RF,
        erp: float = DEFAULT_ERP,
        kd: float = 0.07,
        z_score: float = 2.0,
        tax_rate: float = DEFAULT_TAX_RATE,
        g_terminal: float = DEFAULT_TERMINAL_G,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 20: Adjusted Present Value (APV) — Industrials & Materials (ICB 2700 / 1700).
        APV = V_unlevered + PV(Interest Tax Shield) - PV(Financial Distress)
        """
        current_price = _model_price(current_price, "model_20_industrial_apv")
        shares = max(shares_out, 1.0)
        ku = rf + (max(beta_unlevered, 0.5) * erp)
        ku = max(ku, g_terminal + 0.02)
        nopat_0 = ebit * (1.0 - tax_rate)
        if nopat_0 <= 0:
            return 0.0

        # 1. Unlevered firm value
        v_unlevered = (nopat_0 * (1.0 + g_terminal)) / (ku - g_terminal)

        # 2. PV of Interest Tax Shield
        pv_tax_shield = (tax_rate * kd * max(total_debt, 0.0)) / max(kd, 0.03)

        # 3. PV of Financial Distress
        z_clamped = clamp(z_score - 1.8, -50.0, 50.0)
        prob_default = 1.0 / (1.0 + math.exp(z_clamped))
        distress_cost = 0.25 * v_unlevered
        pv_distress = prob_default * distress_cost

        apv = v_unlevered + pv_tax_shield - pv_distress
        equity_val = apv - max(total_debt, 0.0) + max(cash_and_equiv, 0.0)
        if equity_val <= 0:
            return 0.0

        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_21_consumer_eva_mva(
        ebit: float,
        invested_capital: float,
        wacc: float,
        net_debt: float,
        shares_out: float,
        g_terminal: float = DEFAULT_TERMINAL_G,
        tax_rate: float = DEFAULT_TAX_RATE,
        current_price: float = _PRICE_REQUIRED,
    ) -> float:
        """
        Model 21: Economic Value Added (EVA & MVA) — Consumer Staples & Retail (ICB 3000 / 5000).
        EVA = NOPAT - WACC * Invested Capital
        Total EV = Invested Capital + MVA
        """
        current_price = _model_price(current_price, "model_21_consumer_eva_mva")
        shares = max(shares_out, 1.0)
        nopat = ebit * (1.0 - tax_rate)
        if nopat <= 0 or invested_capital <= 0:
            return 0.0
        ic_0 = invested_capital
        w = max(wacc, g_terminal + 0.02)

        eva_0 = nopat - (w * ic_0)
        # MVA calculation
        mva = (eva_0 * (1.0 + g_terminal)) / (w - g_terminal)
        total_ev = ic_0 + mva
        equity_val = total_ev - net_debt
        if equity_val <= 0:
            return 0.0

        fv = equity_val / shares
        return clamp(fv, 0.0, current_price * 10.0)

    @staticmethod
    def model_22_utilities_3stage_ddm(
        dividend_per_share: float,
        ke: float,
        div_growth_initial: float = 0.08,
        g_terminal: float = 0.040,
        half_life_h: float = 2.5,
        current_price: float = _PRICE_REQUIRED,
        explicit_dividends_series: Optional[List[float]] = None,
    ) -> float:
        """
        Model 22: 3-Stage Dividend Discount Model (DDM / Fuller-Hsia H-Model) — Utilities (ICB 7000 / 7500)
        with support for explicit 5-year forecast dividend stream from 3-Way Engine.
        FV = [D_0 * (1 + g_n) + D_0 * H * (g_a - g_n)] / (Ke - g_n)
        """
        current_price = _model_price(current_price, "model_22_utilities_3stage_ddm")
        clean_ke = max(ke, g_terminal + 0.015)
        gn = clamp(g_terminal, 0.02, 0.05)

        if explicit_dividends_series and len(explicit_dividends_series) >= 5:
            pv_div_sum = sum(explicit_dividends_series[t] / ((1.0 + clean_ke) ** (t + 1)) for t in range(5))
            last_d = explicit_dividends_series[4]
            tv = (last_d * (1.0 + gn)) / (clean_ke - gn)
            pv_tv = tv / ((1.0 + clean_ke) ** 5)
            fv = pv_div_sum + pv_tv
        else:
            if dividend_per_share <= 0:
                # A non-payer cannot be valued by a dividend discount model.
                return 0.0
            d0 = dividend_per_share
            ga = clamp(div_growth_initial, 0.02, 0.20)
            h = max(half_life_h, 1.0)

            numerator = (d0 * (1.0 + gn)) + (d0 * h * (ga - gn))
            denom = clean_ke - gn
            fv = numerator / denom

        return clamp(fv, 0.0, current_price * 10.0)


# =============================================================================
# MULTI-ALGO ADAPTIVE ERROR WEIGHTING ENGINE (IVW & METRICS)
# =============================================================================

class AdaptiveWeightingEngine:
    """
    Computes Inverse Variance Weighting (IVW), evaluates historical prediction
    errors (SMAPE, MALE, WMAPE, RMSLE), applies 1.5x IQR outlier rejection,
    and implements the Cold-Start sector prior fallback hierarchy.
    """

    @staticmethod
    def filter_outliers_iqr(values: List[float]) -> Tuple[List[float], List[int]]:
        """
        Applies 1.5x IQR fence to filter extreme outlier model valuations.
        Returns (kept_values, kept_indices).
        """
        if len(values) < 4:
            return values, list(range(len(values)))

        sorted_pairs = sorted(enumerate(values), key=lambda x: x[1])
        n = len(values)
        q1_idx = int(n * 0.25)
        q3_idx = int(n * 0.75)
        q1 = sorted_pairs[q1_idx][1]
        q3 = sorted_pairs[q3_idx][1]
        iqr = q3 - q1

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        kept_indices = []
        kept_vals = []
        for idx, val in enumerate(values):
            if lower_bound <= val <= upper_bound:
                kept_indices.append(idx)
                kept_vals.append(val)

        if not kept_vals:
            return values, list(range(len(values)))
        return kept_vals, kept_indices

    @staticmethod
    def compute_error_metrics(
        predicted_fv_series: List[float],
        realized_price_series: List[float],
    ) -> Dict[str, float]:
        """
        Calculates SMAPE, MALE, WMAPE, and RMSLE over historical rolling quarters.
        """
        if not predicted_fv_series or not realized_price_series or len(predicted_fv_series) != len(realized_price_series):
            return {"smape": 0.15, "male": 0.15, "wmape": 0.15, "rmsle": 0.15, "variance": 0.0225}

        n = len(predicted_fv_series)
        smape_sum = 0.0
        male_sum = 0.0
        abs_diff_sum = 0.0
        price_sum = sum(realized_price_series)
        rmsle_sq_sum = 0.0
        var_pct_sum = 0.0

        for fv, p in zip(predicted_fv_series, realized_price_series):
            clean_fv = max(fv, 1.0)
            clean_p = max(p, 1.0)

            # SMAPE
            smape_sum += abs(clean_fv - clean_p) / ((abs(clean_fv) + abs(clean_p)) / 2.0)
            # MALE
            male_sum += abs(math.log(clean_fv) - math.log(clean_p))
            # WMAPE
            abs_diff_sum += abs(clean_fv - clean_p)
            # RMSLE
            rmsle_sq_sum += (math.log(clean_fv + 1.0) - math.log(clean_p + 1.0)) ** 2
            # Variance for IVW
            pct_err = (clean_fv - clean_p) / clean_p
            var_pct_sum += pct_err ** 2

        smape = (smape_sum / n) * 100.0
        male = male_sum / n
        wmape = (abs_diff_sum / max(price_sum, 1.0)) * 100.0
        rmsle = math.sqrt(rmsle_sq_sum / n)
        variance = var_pct_sum / n

        return {
            "smape": round(smape, 2),
            "male": round(male, 4),
            "wmape": round(wmape, 2),
            "rmsle": round(rmsle, 4),
            "variance": round(variance, 6),
        }

    @classmethod
    def calculate_weights(
        cls,
        active_models: List[str],
        active_values: List[float],
        sector_code: str = "DEFAULT",
        historical_errors: Optional[Dict[str, Dict[str, float]]] = None,
        composite_mode: str = "blended",
        omnibus_metric: str = "smape",
    ) -> Tuple[Dict[str, float], List[str]]:
        """
        Calculates normalized weights for active models.
        - composite_mode = 'blended' (Default): Uses sector-calibrated fundamental structural weights
          (SECTOR_WEIGHT_PRIORS), zero statistical variance/overfitting risk.
        - composite_mode = 'omnibus': Uses quantitative loss metric weighting:
          - 'smape' (Default): Symmetric Mean Absolute Percentage Error
          - 'male': Mean Absolute Log Error
          - 'wmape': Weighted Mean Absolute Percentage Error
          - 'rmsle': Root Mean Squared Log Error
          - 'ivw': Scale-Free Inverse Variance Weighting
        """
        if not active_models:
            return {}, []

        # 1. Apply IQR Outlier Filter
        kept_vals, kept_indices = cls.filter_outliers_iqr(active_values)
        surviving_models = [active_models[i] for i in kept_indices]
        rejected_models = [active_models[i] for i in range(len(active_models)) if i not in kept_indices]

        # 2. Weight determination
        weights: Dict[str, float] = {}

        mode = str(composite_mode).lower().strip()
        metric = str(omnibus_metric).lower().strip()

        if mode == "blended":
            # --- BLENDED VALUATION (Sector-Calibrated Structural Prior Weights) ---
            sector_prefix = sector_code[:5] if len(sector_code) >= 5 else sector_code
            priors = SECTOR_WEIGHT_PRIORS.get(sector_prefix, SECTOR_WEIGHT_PRIORS.get(sector_code, {}))
            if priors and any(m in priors for m in surviving_models):
                raw_priors = {m: priors.get(m, 0.10) for m in surviving_models}
                total_p = sum(raw_priors.values())
                weights = {m: raw_priors[m] / total_p for m in surviving_models}
            else:
                k = len(surviving_models)
                weights = {m: 1.0 / k for m in surviving_models}
        else:
            # --- OMNIBUS MASTER ENGINE (Loss Metric Weighting) ---
            if historical_errors and len(historical_errors) > 0:
                raw_weights = {}
                for m in surviving_models:
                    err_dict = historical_errors.get(m, {})
                    n_obs = err_dict.get("n_obs", err_dict.get("valid_count", 12))
                    r2 = err_dict.get("r2", 1.0)
                    ramp = min(n_obs / 12.0, 1.0) if n_obs >= 4 else 0.25

                    if metric == "smape":
                        score = err_dict.get("smape", 15.0)
                        raw_weights[m] = (1.0 / max(score, 1.0)) * ramp * max(r2, 0.01)
                    elif metric == "male":
                        score = err_dict.get("male", 0.15)
                        raw_weights[m] = (1.0 / max(score, 0.02)) * ramp * max(r2, 0.01)
                    elif metric == "wmape":
                        score = err_dict.get("wmape", 15.0)
                        raw_weights[m] = (1.0 / max(score, 1.0)) * ramp * max(r2, 0.01)
                    elif metric == "rmsle":
                        score = err_dict.get("rmsle", 0.15)
                        raw_weights[m] = (1.0 / max(score, 0.02)) * ramp * max(r2, 0.01)
                    else:  # 'ivw'
                        var_e = err_dict.get("variance", 0.04)
                        safe_var = max(var_e, 0.0025)
                        raw_weights[m] = (1.0 / safe_var) * ramp * max(r2, 0.01)

                total_raw = sum(raw_weights.values())
                if total_raw > 0:
                    weights = {m: raw_weights[m] / total_raw for m in surviving_models}
                else:
                    k = len(surviving_models)
                    weights = {m: 1.0 / k for m in surviving_models}
            else:
                # Instantaneous loss metric error weighting from model valuations vs benchmark median
                raw_weights = {}
                p_ref = safe_div(sum(kept_vals), len(kept_vals), 10000.0)
                for m, val in zip(surviving_models, kept_vals):
                    clean_v = max(val, 1.0)
                    clean_p = max(p_ref, 1.0)
                    if metric == "smape":
                        score = abs(clean_v - clean_p) / ((clean_v + clean_p) / 2.0) * 100.0
                        raw_weights[m] = 1.0 / max(score, 1.0)
                    elif metric == "male":
                        score = abs(math.log(clean_v) - math.log(clean_p))
                        raw_weights[m] = 1.0 / max(score, 0.02)
                    elif metric == "wmape":
                        score = abs(clean_v - clean_p) / clean_p * 100.0
                        raw_weights[m] = 1.0 / max(score, 1.0)
                    elif metric == "rmsle":
                        score = math.sqrt((math.log(clean_v + 1.0) - math.log(clean_p + 1.0)) ** 2)
                        raw_weights[m] = 1.0 / max(score, 0.02)
                    else:  # ivw
                        score = ((clean_v - clean_p) / clean_p) ** 2
                        raw_weights[m] = 1.0 / max(score, 0.0025)

                total_raw = sum(raw_weights.values())
                if total_raw > 0:
                    weights = {m: raw_weights[m] / total_raw for m in surviving_models}
                else:
                    k = len(surviving_models)
                    weights = {m: 1.0 / k for m in surviving_models}

        return {m: round(weights.get(m, 0.0), 4) for m in surviving_models}, rejected_models


# =============================================================================
# STRESS-TEST SCENARIOS & 2D SENSITIVITY GRID ENGINE
# =============================================================================

class ScenarioEngine:
    """
    Generates Bear, Base, and Bull stress-test scenarios via driver perturbations,
    and computes a 5x5 WACC vs Terminal Growth sensitivity matrix.
    """

    @classmethod
    def generate(
        cls,
        base_composite_fv: float,
        wacc_base: float,
        terminal_g_base: float,
        current_price: float,
        base_models: List[ModelValuationOutput],
    ) -> ScenarioResult:
        """
        Constructs Bear / Base / Bull scenarios and 5x5 Sensitivity Grid.
        """
        # 1. Base spread
        base_spread = max(wacc_base - terminal_g_base, 0.02)

        # 2. Bear Scenario Shifts (Growth -1.0%, WACC +1.5%, Operating Margin 0.85x)
        bear_wacc = wacc_base + 0.015
        bear_g = max(terminal_g_base - 0.010, 0.020)
        bear_spread = max(bear_wacc - bear_g, 0.015)
        bear_factor = (base_spread / bear_spread) * 0.85
        bear_fv = round(clamp(base_composite_fv * bear_factor, 0.10 * base_composite_fv, base_composite_fv), 0)
        bear_upside = safe_div(bear_fv - current_price, current_price) * 100.0

        # 3. Base Scenario
        base_fv = base_composite_fv
        base_upside = safe_div(base_fv - current_price, current_price) * 100.0

        # 4. Bull Scenario Shifts (Growth +1.0%, WACC -1.0%, Operating Margin 1.10x)
        bull_wacc = max(wacc_base - 0.010, 0.060)
        bull_g = terminal_g_base + 0.010
        bull_spread = max(bull_wacc - bull_g, 0.015)
        bull_factor = (base_spread / bull_spread) * 1.10
        bull_fv = round(clamp(base_composite_fv * bull_factor, base_composite_fv, 3.0 * base_composite_fv), 0)
        bull_upside = safe_div(bull_fv - current_price, current_price) * 100.0

        # 4. 5x5 Sensitivity Grid
        # WACC steps: -2.0%, -1.0%, base, +1.0%, +2.0%
        # Growth steps: -1.5%, -0.75%, base, +0.75%, +1.5%
        wacc_deltas = [-0.020, -0.010, 0.000, 0.010, 0.020]
        growth_deltas = [-0.015, -0.0075, 0.000, 0.0075, 0.015]

        headers_wacc = [round(wacc_base + d, 4) for d in wacc_deltas]
        headers_growth = [round(terminal_g_base + d, 4) for d in growth_deltas]

        grid_5x5: List[List[float]] = []
        base_spread = max(wacc_base - terminal_g_base, 0.02)

        for w_val in headers_wacc:
            row: List[float] = []
            for g_val in headers_growth:
                spread = max(w_val - g_val, 0.015)
                # Gordon-growth sensitivity scaling factor
                factor = base_spread / spread
                cell_fv = round(clamp(base_fv * factor, 0.10 * base_fv, 3.0 * base_fv), 0)
                row.append(cell_fv)
            grid_5x5.append(row)

        scenario_drivers = {
            "wacc": {
                "bear": round(wacc_base + 0.015, 4),
                "base": round(wacc_base, 4),
                "bull": round(wacc_base - 0.010, 4),
            },
            "terminal_growth": {
                "bear": round(max(terminal_g_base - 0.010, 0.020), 4),
                "base": round(terminal_g_base, 4),
                "bull": round(terminal_g_base + 0.010, 4),
            },
            "revenue_growth_shift_pct": {
                "bear": -2.5,
                "base": 0.0,
                "bull": 2.5,
            },
            "operating_margin_multiplier": {
                "bear": 0.85,
                "base": 1.00,
                "bull": 1.10,
            }
        }

        return ScenarioResult(
            bear_fair_value=round(bear_fv, 0),
            base_fair_value=round(base_fv, 0),
            bull_fair_value=round(bull_fv, 0),
            bear_upside_pct=round(bear_upside, 2),
            base_upside_pct=round(base_upside, 2),
            bull_upside_pct=round(bull_upside, 2),
            scenario_drivers=scenario_drivers,
            sensitivity_grid_5x5=grid_5x5,
            sensitivity_headers_wacc=headers_wacc,
            sensitivity_headers_growth=headers_growth,
        )


# =============================================================================
# END-TO-END QUANTITATIVE VALUATION ENGINE FACADE
# =============================================================================

class ValuationEngine:
    """
    Unified institutional facade for the 22-Model Quantitative Valuation Engine.
    Provides complete end-to-end evaluation, risk diagnostics, adaptive weighting,
    and stress-testing.
    """

    def __init__(self, data_lake: Optional[Any] = None):
        self.data_lake = data_lake
        self.wacc_engine = WACCEngine()
        self.risk_engine = RiskFirewallEngine()
        self.models_suite = ValuationModelsSuite()
        self.weighting_engine = AdaptiveWeightingEngine()
        self.scenario_engine = ScenarioEngine()
        # Provenance of the most recent calculate_all_models() call, so the
        # comprehensive payload can report which drivers were real.
        self.last_resolver: Optional[InputResolver] = None

    def calculate_wacc(
        self,
        symbol: str,
        fundamental_data: Dict[str, Any],
        rf: float = DEFAULT_RF,
        erp: float = DEFAULT_ERP,
        tax_rate: float = DEFAULT_TAX_RATE,
    ) -> WACCResult:
        """Calculates 5-Factor VN CAPM, Cost of Debt, and WACC."""
        # Sanitize NaN / Inf / invalid string values → None for safe fallbacks
        fundamental_data = _sanitize_fundamental_data(fundamental_data)
        mcap = float(fundamental_data.get("market_cap") or 1e12)
        debt = float(fundamental_data.get("interest_bearing_debt") or fundamental_data.get("debt") or (mcap * 0.4))
        ebit = float(fundamental_data.get("ebit") or fundamental_data.get("operating_profit") or (mcap * 0.12))
        interest = float(fundamental_data.get("interest_expense") or (debt * 0.07))
        beta_raw = float(fundamental_data.get("beta") if fundamental_data.get("beta") is not None else 1.0)
        roe = float(fundamental_data.get("roe") if fundamental_data.get("roe") is not None else 15.0)
        pb = float(fundamental_data.get("pb") if fundamental_data.get("pb") is not None else 1.5)
        pb_sector = float(fundamental_data.get("pb_sector_median") if fundamental_data.get("pb_sector_median") is not None else 1.5)
        adtv = float(fundamental_data.get("adtv") or 15e9)
        r12m = float(fundamental_data.get("r12m") if fundamental_data.get("r12m") is not None else 0.15)
        r1m = float(fundamental_data.get("r1m") if fundamental_data.get("r1m") is not None else 0.02)

        return self.wacc_engine.calculate(
            market_cap=mcap,
            interest_bearing_debt=debt,
            ebit=ebit,
            interest_expense=interest,
            beta_raw=beta_raw,
            roe=roe,
            pb=pb,
            pb_sector_median=pb_sector,
            adtv=adtv,
            r12m=r12m,
            r1m=r1m,
            rf=rf,
            erp=erp,
            tax_rate=tax_rate,
        )

    def evaluate_risk_firewalls(
        self,
        symbol: str,
        fundamental_data: Dict[str, Any],
        wacc_res: Optional[WACCResult] = None,
        sector_pb: float = 1.5,
        price_returns: Optional[List[float]] = None,
        market_returns: Optional[List[float]] = None,
    ) -> RiskFirewallResult:
        """Evaluates Altman Z'', Beneish M, Rhodes-Kropf, and Dynamic MOS."""
        if wacc_res is None:
            wacc_res = self.calculate_wacc(symbol, fundamental_data)

        return self.risk_engine.evaluate(
            fundamental_data=fundamental_data,
            wacc_res=wacc_res,
            sector_pb=sector_pb,
            price_returns=price_returns,
            market_returns=market_returns,
        )

    def calculate_all_models(
        self,
        symbol: str,
        fundamental_data: Dict[str, Any],
        wacc_res: Optional[WACCResult] = None,
        risk_res: Optional[RiskFirewallResult] = None,
    ) -> List[ModelValuationOutput]:
        """Evaluates all 22 quantitative valuation models."""
        if wacc_res is None:
            wacc_res = self.calculate_wacc(symbol, fundamental_data)
        if risk_res is None:
            risk_res = self.evaluate_risk_firewalls(symbol, fundamental_data, wacc_res)

        # Sanitize NaN / Inf / invalid string values → None for safe fallbacks
        fundamental_data = _sanitize_fundamental_data(fundamental_data)

        price = _require_price(symbol, fundamental_data)

        # Resolve every driver through the provenance tracker. The structural
        # stand-ins below are unchanged in value; what is new is that each one
        # is recorded as IMPUTED, so add_model() can refuse to publish a model
        # whose driver is a fraction of market cap rather than a filing.
        res = InputResolver(fundamental_data)
        self.last_resolver = res
        res.mark("price", REAL)

        shares = max(res.resolve("shares", ("shares_out", "shares"),
                                 impute=lambda: 1e8, require_positive=True), 1.0)
        mcap = res.resolve(
            "market_cap", ("market_cap",),
            derive=(("shares",), lambda: price * shares),
            impute=lambda: price * shares, require_positive=True,
        )
        debt = res.resolve("debt", ("debt", "total_debt_fq", "interest_bearing_debt"),
                           impute=lambda: mcap * 0.4)
        cash = res.resolve("cash", ("cash", "cash_fq", "cash_and_equiv"),
                           impute=lambda: mcap * 0.15)
        net_debt = debt - cash
        revenue = res.resolve("revenue", ("revenue", "revenue_ttm"),
                              impute=lambda: mcap * 0.8)
        # The old floor (price * 0.5) made sales-per-share a function of price
        # for every small-revenue company; sales per share is now purely
        # revenue / shares and inherits revenue's provenance.
        sps = safe_div(revenue, shares, 0.0)
        res.mark("sps", res.provenance.get("revenue", IMPUTED))
        ebit = res.resolve("ebit", ("ebit", "ebit_ttm", "operating_profit"),
                           impute=lambda: revenue * 0.15)
        ebitda = res.resolve("ebitda", ("ebitda",),
                             derive=(("ebit",), lambda: ebit * 1.25),
                             impute=lambda: ebit * 1.25)
        net_income = res.resolve("net_income", ("net_income", "net_income_ttm", "pat"),
                                 impute=lambda: ebit * 0.8)
        eps = res.resolve("eps", ("eps",),
                          derive=(("net_income", "shares"), lambda: safe_div(net_income, shares, 0.0)),
                          impute=lambda: safe_div(net_income, shares, 0.0))
        equity_val = res.resolve("equity", ("equity", "total_equity_fq", "book_equity"),
                                 impute=lambda: mcap * 0.6)
        bvps = res.resolve("bvps", ("bvps",),
                           derive=(("equity", "shares"), lambda: safe_div(equity_val, shares, 0.0)),
                           impute=lambda: safe_div(equity_val, shares, 0.0))
        tbvps = res.resolve("tbvps", ("tbvps",),
                            impute=lambda: bvps * 0.9)
        cfo = res.resolve("cfo", ("cfo", "cfo_ttm"), impute=lambda: net_income * 1.1)
        cfo_per_share = safe_div(cfo, shares, 0.0)
        pat_per_share = safe_div(net_income, shares, 0.0)
        fcf = res.resolve("fcf", ("fcf",), impute=lambda: cfo * 0.7)
        fcf_per_share = safe_div(fcf, shares, 0.0)
        affo = res.resolve("affo", ("affo",), impute=lambda: net_income * 0.9)
        dividend_per_share = res.resolve("dividend_per_share", ("dividend_per_share",),
                                         impute=lambda: eps * 0.3)
        roe = _as_rate(res.resolve("roe", ("roe",), impute=lambda: 15.0))
        roic = _as_rate(res.resolve("roic", ("roic",), impute=lambda: 14.0))
        net_margin = res.resolve(
            "net_margin", ("net_margin",),
            derive=(("net_income", "revenue"), lambda: safe_div(net_income, revenue, 0.0)),
            impute=lambda: safe_div(net_income, revenue, 0.0),
        )
        if net_margin > 1.0:
            net_margin /= 100.0

        sector_code = str(fundamental_data.get("sector_code") or "DEFAULT").upper()
        sector_prefix = sector_code[:5] if len(sector_code) >= 5 else sector_code

        # Derive sustainable growth rates from company fundamentals
        pat_growth_raw = fundamental_data.get("pat_1y_growth") or fundamental_data.get("pat_growth") or fundamental_data.get("rev_1y_growth") or 10.0
        try:
            pat_growth_val = float(pat_growth_raw)
            if math.isnan(pat_growth_val):
                pat_growth_val = 10.0
        except (ValueError, TypeError):
            pat_growth_val = 10.0

        g_fundamental_pct = clamp(pat_growth_val, 2.0, 22.0)
        g_stage1 = g_fundamental_pct / 100.0

        # Peer and Sector Multiple medians
        sector_pe = float(fundamental_data.get("sector_pe") or 12.0)
        hist_pe = float(fundamental_data.get("hist_pe") or 11.0)
        sector_ps = float(fundamental_data.get("sector_ps") or 1.2)
        sector_net_margin = float(fundamental_data.get("sector_net_margin") or 0.08)
        sector_pfcf = float(fundamental_data.get("sector_pfcf") or 14.0)
        hist_pfcf = float(fundamental_data.get("hist_pfcf") or 12.0)
        sector_pb = float(fundamental_data.get("sector_pb") or 1.5)
        sector_ptbv = float(fundamental_data.get("sector_ptbv") or 1.4)
        sector_ev_ebitda = float(fundamental_data.get("sector_ev_ebitda") or 8.5)
        hist_ev_ebitda = float(fundamental_data.get("hist_ev_ebitda") or 8.0)
        sector_pcf = float(fundamental_data.get("sector_pcf") or 9.0)
        sector_paffo = float(fundamental_data.get("sector_paffo") or 12.0)
        sector_ev_ebit = float(fundamental_data.get("sector_ev_ebit") or 8.0)
        hist_eps = fundamental_data.get("historical_eps") or [eps * 0.8, eps * 0.9, eps]

        # Sector Applicability Check
        applicable_model_ids = SECTOR_MODEL_MAP.get(sector_prefix, SECTOR_MODEL_MAP.get(sector_code, None))

        results: List[ModelValuationOutput] = []

        def add_model(
            model_id: str,
            name: str,
            category: str,
            val: float,
            diag: Optional[Dict[str, Any]] = None,
            drivers: Sequence[str] = (),
        ):
            """Publishes one model result, unless its drivers were invented.

            ``drivers`` names the inputs the model is actually a function of.
            If any of them was imputed, the model has no company-specific
            information to offer: its output would be some multiple of the
            price that was fed in. Publishing that as a fair value is what let
            a payload with no financial statements produce 22 confident
            valuations, so such a model is marked INSUFFICIENT_DATA and
            excluded from the composite instead.
            """
            missing = [d for d in drivers if res.is_imputed(d)]
            clean_val = round(clamp(val, 0.0, price * 10.0), 0)
            upside = round(safe_div(clean_val - price, price) * 100.0, 2)
            sector_ok = (applicable_model_ids is None) or (model_id in applicable_model_ids)

            diagnostics = dict(diag or {})
            if missing:
                is_active = False
                status = "INSUFFICIENT_DATA"
                diagnostics["imputed_drivers"] = missing
                diagnostics["suppressed_fair_value"] = clean_val
                clean_val = 0.0
                upside = 0.0
            elif clean_val <= 0:
                # The model declined to value this company (no earnings, no
                # book equity, no dividend, equity wiped out by debt...). That
                # is an answer, not a gap to be filled with a floor.
                is_active = False
                status = "NOT_APPLICABLE"
            elif not sector_ok:
                is_active = False
                status = "BYPASSED"
            else:
                is_active = True
                status = "ACTIVE"

            results.append(ModelValuationOutput(
                model_id=model_id,
                model_name=name,
                category=category,
                fair_value=clean_val,
                upside_pct=upside,
                weight=0.0,
                active=is_active,
                status=status,
                diagnostics=diagnostics
            ))

        # --- 8 RELATIVE MULTIPLES ---
        m1 = self.models_suite.model_1_blended_pe(
            eps_ttm=eps, historical_eps=hist_eps, sector_pe=sector_pe, hist_pe=hist_pe,
            eps_growth_rate=g_stage1, current_price=price
        )
        add_model("blended_pe", "Blended P/E with CAPE", "relative", m1,
                  drivers=('eps',))

        m2 = self.models_suite.model_2_ps_margin_adjusted(
            sales_per_share=sps, net_margin=net_margin, sector_ps=sector_ps,
            sector_net_margin=sector_net_margin, current_price=price
        )
        add_model("ps_margin_adj", "Margin-Adjusted P/S", "relative", m2,
                  drivers=('sps', 'net_margin'))

        m3 = self.models_suite.model_3_p_fcf(
            fcf_per_share=fcf_per_share, sales_per_share=sps, sector_pfcf=sector_pfcf,
            hist_pfcf=hist_pfcf, current_price=price
        )
        add_model("p_fcf", "Price-to-FCF Yield", "relative", m3,
                  drivers=('fcf', 'sps'))

        m4 = self.models_suite.model_4_pb_rhodes_kropf(
            bvps=bvps, roe=roe, ke=wacc_res.cost_of_equity, sector_pb=sector_pb,
            rkv_is_overvalued=risk_res.rhodes_kropf.get("is_firm_overvalued", False), current_price=price
        )
        add_model("pb_rhodes_kropf", "P/B with Rhodes-Kropf Filter", "relative", m4,
                  drivers=('bvps', 'roe'))

        m5 = self.models_suite.model_5_p_tbv(
            tbv_per_share=tbvps, bvps=bvps, roic=roic, wacc=wacc_res.wacc,
            sector_ptbv=sector_ptbv, current_price=price
        )
        add_model("p_tbv", "Price-to-Tangible Book (P/TBV)", "relative", m5,
                  drivers=('tbvps', 'bvps', 'roic'))

        m6 = self.models_suite.model_6_ev_ebitda(
            ebitda=ebitda, total_debt=debt, cash_and_equiv=cash, shares_out=shares,
            sector_ev_ebitda=sector_ev_ebitda, hist_ev_ebitda=hist_ev_ebitda, current_price=price
        )
        add_model("ev_ebitda", "Blended EV/EBITDA Enterprise Multiple", "relative", m6,
                  drivers=('ebitda', 'debt', 'cash', 'shares'))

        m7 = self.models_suite.model_7_p_cf(
            cfo_per_share=cfo_per_share, pat_per_share=pat_per_share, sector_pcf=sector_pcf, current_price=price
        )
        add_model("p_cf", "Price-to-Operating Cash Flow (P/CF)", "relative", m7,
                  drivers=('cfo', 'net_income'))

        m8 = self.models_suite.model_8_p_affo(
            affo=affo, net_income=net_income, shares_out=shares, sector_paffo=sector_paffo, current_price=price
        )
        add_model("p_affo", "Price-to-AFFO Multiple (P/AFFO)", "relative", m8,
                  drivers=('affo', 'net_income', 'shares'))

        # --- 7 ABSOLUTE INTRINSIC MODELS ---
        m9 = self.models_suite.model_9_dcf_2stage_mckinsey(
            ebit=ebit, roic=roic, wacc=wacc_res.wacc, shares_out=shares,
            cash_and_equiv=cash, total_debt=debt, g_stage1=g_stage1, current_price=price
        )
        add_model("dcf_2stage_mckinsey", "Extended 2-Stage McKinsey DCF", "absolute", m9,
                  drivers=('ebit', 'roic', 'cash', 'debt', 'shares'))

        m10 = self.models_suite.model_10_rim_edwards_bell_ohlson(
            book_equity=bvps * shares, roe_base=roe, ke=wacc_res.cost_of_equity,
            shares_out=shares, current_price=price
        )
        add_model("rim_edwards_bell_ohlson", "Residual Income Model (RIM / EBO)", "absolute", m10,
                  drivers=('bvps', 'roe', 'shares'))

        m11 = self.models_suite.model_11_greenwald_epv(
            revenue=revenue, ebit_margin_avg=safe_div(ebit, revenue, 0.15),
            wacc=wacc_res.wacc, shares_out=shares, cash_and_equiv=cash, total_debt=debt, current_price=price
        )
        add_model("greenwald_epv", "Greenwald Earnings Power Value (EPV)", "absolute", m11,
                  drivers=('revenue', 'ebit', 'cash', 'debt', 'shares'))

        m12 = self.models_suite.model_12_graham_growth(
            eps_ttm=eps, bvps=bvps, expected_growth_pct=g_fundamental_pct,
            benchmark_bond_yield=wacc_res.rf * 100.0, current_price=price
        )
        add_model("graham_growth", "Benjamin Graham Growth Formula", "absolute", m12,
                  drivers=('eps', 'bvps'))

        m13 = self.models_suite.model_13_rule_of_40_growth(
            sales_per_share=sps,
            rev_growth_pct=float(fundamental_data.get("rev_1y_growth") or 15.0),
            fcf_margin_pct=safe_div(fcf, revenue, 0.10) * 100.0,
            total_revenue=revenue,
            net_debt=net_debt,
            shares_out=shares,
            current_price=price,
        )
        add_model("rule_of_40_growth", "Rule of 40 / Rule of X Valuation", "absolute", m13,
                  drivers=('sps', 'revenue', 'fcf', 'debt', 'cash'))

        m14 = self.models_suite.model_14_acquirers_multiple(
            ebit=ebit, revenue=revenue, net_debt=net_debt, shares_out=shares,
            sector_ev_ebit=sector_ev_ebit, current_price=price
        )
        add_model("acquirers_multiple_ev_ebit", "Acquirer's Multiple (EV/EBIT)", "absolute", m14,
                  drivers=('ebit', 'revenue', 'debt', 'cash', 'shares'))

        total_capex = res.resolve("capex", ("capex", "capex_ttm"),
                                  derive=(("ebitda", "ebit"), lambda: ebitda - ebit),
                                  impute=lambda: ebitda - ebit)
        prev_rev = res.resolve("prev_revenue", ("prev_revenue",),
                               impute=lambda: revenue * (1.0 - g_stage1))
        gross_ppe = res.resolve("gross_ppe", ("gross_ppe_fq", "ppe_gross", "fixed_assets"),
                                impute=lambda: mcap * 0.4)
        delta_wc_val = float(fundamental_data.get("delta_working_capital") or 0.0)
        m15 = self.models_suite.model_15_buffett_owners_earnings(
            net_income=net_income,
            depreciation=ebitda - ebit,
            maintenance_capex=(ebitda - ebit) * 0.8,
            delta_working_capital=delta_wc_val,
            ke=wacc_res.cost_of_equity,
            shares_out=shares,
            growth_rate=g_stage1,
            total_capex=total_capex,
            revenue=revenue,
            prev_revenue=prev_rev,
            gross_ppe=gross_ppe,
            ocf=cfo,
            rf=wacc_res.rf,
            current_price=price,
        )
        add_model("buffett_owners_earnings", "Warren Buffett Owner's Earnings DCF", "absolute", m15,
                  drivers=('net_income', 'ebitda', 'ebit', 'cfo', 'revenue'))

        # --- 7 SECTOR-SPECIFIC MODELS ---
        m16 = self.models_suite.model_16_pharma_rnpv(
            base_epv_per_share=m11, net_cash_per_share=cash / shares, current_price=price
        )
        add_model("pharma_rnpv", "Pharma Risk-Adjusted NPV (rNPV)", "sector", m16,
                  drivers=('revenue', 'ebit', 'cash', 'debt', 'shares'))

        rwa_clean = res.resolve("rwa", ("bank_loans_fq", "rwa"), impute=lambda: mcap * 1.2)
        m17 = self.models_suite.model_17_bank_equity_cash_flow(
            net_income=net_income, rwa=rwa_clean,
            book_equity=bvps * shares, roe=roe, ke=wacc_res.cost_of_equity, shares_out=shares, current_price=price
        )
        add_model("bank_equity_cash_flow", "Banking Equity Cash Flow & Basel II CAR", "sector", m17,
                  drivers=('net_income', 'bvps', 'roe', 'rwa'))

        landbank_clean = res.resolve("landbank", ("landbank_fq",), impute=lambda: mcap * 0.2)
        m18 = self.models_suite.model_18_reit_affo_dcf(
            net_operating_income=ebit, landbank_pipeline_val=landbank_clean, cash_and_equiv=cash,
            total_debt=debt, shares_out=shares, current_price=price
        )
        add_model("reit_affo_dcf", "REIT / Real Estate AFFO & RNAV", "sector", m18,
                  drivers=('ebit', 'cash', 'debt', 'landbank'))

        regulated_asset_base = res.resolve(
            "regulated_asset_base", ("regulated_asset_base", "rab"),
            impute=lambda: mcap * 0.5)
        m19 = self.models_suite.model_19_telecom_unbundled_sotp(
            regulated_asset_base=regulated_asset_base, serveco_ebitda=ebitda * 0.5,
            net_debt=net_debt, shares_out=shares, current_price=price,
            wacc=wacc_res.wacc, g_terminal=DEFAULT_TERMINAL_G
        )
        add_model("telecom_unbundled_sotp", "Unbundled SOTP & Regulated Asset Base", "sector", m19,
                  drivers=('regulated_asset_base', 'ebitda', 'debt', 'cash'))

        m20 = self.models_suite.model_20_industrial_apv(
            ebit=ebit, total_debt=debt, cash_and_equiv=cash, shares_out=shares,
            rf=wacc_res.rf, erp=wacc_res.erp, kd=wacc_res.cost_of_debt_after_tax,
            z_score=risk_res.altman_z_score, current_price=price
        )
        add_model("industrial_apv", "Adjusted Present Value (APV)", "sector", m20,
                  drivers=('ebit', 'debt', 'cash'))

        invested_capital = res.resolve(
            "invested_capital", ("invested_capital", "capital_employed"),
            derive=(("equity", "debt"), lambda: equity_val + debt),
            impute=lambda: mcap * 0.5)
        m21 = self.models_suite.model_21_consumer_eva_mva(
            ebit=ebit, invested_capital=invested_capital, wacc=wacc_res.wacc,
            net_debt=net_debt, shares_out=shares, current_price=price
        )
        add_model("consumer_eva_mva", "Economic Value Added (EVA & MVA)", "sector", m21,
                  drivers=('ebit', 'invested_capital'))

        m22 = self.models_suite.model_22_utilities_3stage_ddm(
            dividend_per_share=dividend_per_share, ke=wacc_res.cost_of_equity, current_price=price
        )
        add_model("utilities_3stage_ddm", "3-Stage Dividend Discount Model (DDM)", "sector", m22,
                  drivers=('dividend_per_share',))

        return results

    def calculate_composite_fair_value(
        self,
        models: List[ModelValuationOutput],
        sector_code: str = "DEFAULT",
        history_errors: Optional[Dict[str, Dict[str, float]]] = None,
        composite_mode: str = "blended",
        omnibus_metric: str = "smape",
    ) -> float:
        """
        Aggregates active models using either:
        - composite_mode='blended' (Default): Sector-calibrated fundamental structural blend
        - composite_mode='omnibus': Dynamic error metric weighting (SMAPE, MALE, WMAPE, RMSLE, IVW)
        """
        active_models = [m.model_id for m in models if m.active and m.fair_value > 0]
        active_vals = [m.fair_value for m in models if m.active and m.fair_value > 0]

        # No usable model means no valuation. The previous behaviour fell back
        # to averaging every model including the ones that had just been
        # rejected, and then to a literal 10,000 VND - so a company with no
        # data still produced a fair value that looked like every other one.
        if not active_models:
            for m in models:
                m.weight = 0.0
            return 0.0

        weights, rejected = self.weighting_engine.calculate_weights(
            active_models=active_models,
            active_values=active_vals,
            sector_code=sector_code,
            historical_errors=history_errors,
            composite_mode=composite_mode,
            omnibus_metric=omnibus_metric,
        )

        composite_fv = 0.0
        total_w = sum(weights.values())

        for m in models:
            if m.model_id in rejected:
                m.active = False
                m.status = "OUTLIER_REJECTED"
                m.weight = 0.0
            elif m.model_id in weights:
                m.weight = weights[m.model_id]
                composite_fv += m.weight * m.fair_value
            else:
                m.weight = 0.0

        if total_w > 0:
            composite_fv = composite_fv / total_w
        else:
            # Every surviving model was filtered out by the weighting stage;
            # fall back to the equal-weight mean of the survivors, never to a
            # hardcoded price.
            composite_fv = sum(active_vals) / len(active_vals) if active_vals else 0.0

        return round(max(composite_fv, 0.0), 0)

    def get_comprehensive_valuation(
        self,
        symbol: str,
        fundamental_data: Optional[Dict[str, Any]] = None,
        composite_mode: str = "blended",
        omnibus_metric: str = "smape",
        history_errors: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> ValuationMatrixResult:
        """
        Complete end-to-end quantitative valuation method returning the full
        structured payload for API serialization and institutional reports.
        """
        if fundamental_data is None:
            # Auto-resolve from data lake screener snapshot if available
            # Go through the shared resolver: reading data/ directly ignored
            # GOOGLE_DRIVE_DATA_DIR and DATA_LOCAL_DIR, so the valuation engine
            # could be reading a different snapshot from the rest of the app.
            try:
                from services.stock_service import resolve_data_file
                local_cand = resolve_data_file("screener_snapshot.json")
            except Exception:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                local_cand = os.path.join(base_dir, "data", "screener_snapshot.json")
            if os.path.exists(local_cand):
                try:
                    with open(local_cand, "r", encoding="utf-8") as f:
                        stocks = json.load(f).get("stocks", {})
                        clean_sym = symbol.strip().upper()
                        if clean_sym in stocks:
                            fundamental_data = stocks[clean_sym]
                except Exception as e:
                    logger.debug("Error loading screener data for valuation of %s: %s", symbol, e)

        if fundamental_data is None:
            raise ValueError(f"Fundamental data is required for quantitative valuation of {symbol}. Fallback to mock data is disabled.")

        # Sanitize NaN / Inf / invalid string values → None for safe fallbacks
        fundamental_data = _sanitize_fundamental_data(fundamental_data)

        price = _require_price(symbol, fundamental_data)
        company_name = str(fundamental_data.get("name") or fundamental_data.get("company_name") or symbol)
        exchange = str(fundamental_data.get("exchange") or "HOSE")
        sector_code = str(fundamental_data.get("sector_code") or "DEFAULT").upper()
        shares = max(float(fundamental_data.get("shares_out") or fundamental_data.get("shares") or 1e8), 1.0)
        mcap = float(fundamental_data.get("market_cap") or (price * shares))
        total_assets = float(fundamental_data.get("total_assets") or fundamental_data.get("assets") or (mcap * 1.5))
        equity_val = float(fundamental_data.get("equity") or (mcap * 0.6))
        bvps = float(fundamental_data.get("bvps") or (equity_val / shares))
        net_income = float(fundamental_data.get("net_income") or fundamental_data.get("pat") or (mcap * 0.08))
        cfo = float(fundamental_data.get("cfo") or (net_income * 1.1))
        revenue = float(fundamental_data.get("revenue") or (mcap * 0.8))
        gross_profit = float(fundamental_data.get("gross_profit") or (revenue * 0.25))
        dividend_ps = float(fundamental_data.get("dividend_per_share") or fundamental_data.get("dps") or 0.0)
        roic_raw = fundamental_data.get("roic") or 14.0
        roic = float(roic_raw) / 100.0 if float(roic_raw) > 1.0 else float(roic_raw)

        # 1. WACC Engine
        wacc_res = self.calculate_wacc(symbol, fundamental_data)

        # 2. Risk Firewalls Engine
        risk_res = self.evaluate_risk_firewalls(symbol, fundamental_data, wacc_res)

        # 3. 22-Model Suite
        models = self.calculate_all_models(symbol, fundamental_data, wacc_res, risk_res)

        # 4. Composite (Blended vs. Omnibus)
        composite_fv = self.calculate_composite_fair_value(
            models=models,
            sector_code=sector_code,
            history_errors=history_errors,
            composite_mode=composite_mode,
            omnibus_metric=omnibus_metric,
        )
        composite_upside = round(safe_div(composite_fv - price, price) * 100.0, 2)

        # Valuation Status Classification
        mos_pct = risk_res.dynamic_margin_of_safety * 100.0
        if composite_upside >= mos_pct:
            val_status = "UNDERVALUED"
        elif composite_upside <= -10.0:
            val_status = "OVERVALUED"
        else:
            val_status = "FAIRLY_VALUED"

        # 5. Stress Scenarios & 2D Grid
        scenarios = self.scenario_engine.generate(
            base_composite_fv=composite_fv,
            wacc_base=wacc_res.wacc,
            terminal_g_base=DEFAULT_TERMINAL_G,
            current_price=price,
            base_models=models,
        )

        valuation_width = round(safe_div(scenarios.bull_fair_value - scenarios.bear_fair_value, composite_fv) * 100.0, 2)

        # 6. Buffett Coupon Spread
        oe_model = next((m for m in models if m.model_id == "buffett_owners_earnings"), None)
        oe_val = oe_model.fair_value if oe_model else composite_fv
        oe_yield_pct = safe_div(oe_val * shares, mcap) * 100.0
        rf_pct = wacc_res.rf * 100.0
        coupon_spread = round(oe_yield_pct - rf_pct, 2)
        coupon_status = "SCREAMING BUY" if coupon_spread >= 3.0 else ("BUY (Positive Carry)" if coupon_spread > 0.0 else "PASS")
        buffett_coupon_spread = {
            "oe_yield_pct": round(oe_yield_pct, 2),
            "rf_pct": round(rf_pct, 2),
            "coupon_spread_pct": coupon_spread,
            "coupon_status": coupon_status,
        }

        # 7. Quant Quality Filters
        gpa = safe_div(gross_profit, total_assets, 0.35)
        sloan = safe_div(net_income - cfo, total_assets, -0.05)
        sh_yield = safe_div(dividend_ps * shares, mcap) * 100.0
        roic_wacc_spread = round((roic - wacc_res.wacc) * 100.0, 2)
        quant_quality_filters = {
            "gpa_ratio_pct": round(gpa * 100.0, 2),
            "gpa_pass": gpa > 0.33,
            "sloan_ratio_pct": round(sloan * 100.0, 2),
            "sloan_pass": sloan < 0.0,
            "shareholder_yield_pct": round(sh_yield, 2),
            "shareholder_yield_pass": sh_yield > 5.0,
            "roic_wacc_spread_pct": roic_wacc_spread,
            "roic_wacc_pass": roic_wacc_spread > 5.0,
        }

        # 8. 3-State Capital Allocation
        asset_growth = fundamental_data.get("asset_growth") or fundamental_data.get("rev_1y_growth") or 8.0
        ebitda_growth = fundamental_data.get("ebitda_growth") or fundamental_data.get("pat_1y_growth") or 10.0
        if ebitda_growth >= asset_growth:
            cap_alloc_status = "Efficient"
            cap_alloc_desc = "Core cash generation (EBITDA) outpaces or matches asset expansion."
        elif asset_growth > 0:
            cap_alloc_status = "Empire Builder"
            cap_alloc_desc = "Asset expansion outpaces core cash generation (potential empire building)."
        else:
            cap_alloc_status = "Deteriorating"
            cap_alloc_desc = "Asset contraction with faster EBITDA collapse."

        capital_allocation = {
            "asset_growth_yoy": round(float(asset_growth), 2),
            "ebitda_growth_yoy": round(float(ebitda_growth), 2),
            "status": cap_alloc_status,
            "description": cap_alloc_desc,
        }

        import datetime
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return ValuationMatrixResult(
            data_quality=assess_data_quality(fundamental_data),
            symbol=symbol,
            company_name=company_name,
            exchange=exchange,
            current_price=price,
            composite_fair_value=composite_fv,
            composite_upside_pct=composite_upside,
            valuation_status=val_status,
            margin_of_safety_pct=round(mos_pct, 2),
            models=models,
            wacc_result=wacc_res,
            risk_firewall=risk_res,
            scenarios=scenarios,
            timestamp=ts,
            valuation_width_pct=valuation_width,
            buffett_coupon_spread=buffett_coupon_spread,
            quant_quality_filters=quant_quality_filters,
            capital_allocation=capital_allocation,
            metadata={
                "engine_version": "2.2.0-dual-mode",
                "composite_mode": composite_mode,
                "omnibus_metric": omnibus_metric if composite_mode == "omnibus" else "N/A (Sector Blended)",
                "active_model_count": sum(1 for m in models if m.active),
                "total_model_count": len(models),
                "firewall_passed": risk_res.firewall_passed,
            }
        )
