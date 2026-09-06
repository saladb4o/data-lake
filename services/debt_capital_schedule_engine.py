"""
=============================================================================
MODANO 3-WAY INTEGRATED MODELING ECOSYSTEM: DEBT & CAPITAL SCHEDULE ENGINE
=============================================================================
Institutional-grade Debt Amortization Roll-Forward, Damodaran Synthetic Credit
Rating Engine, Cost of Debt (Kd) Calculator, and Solvency-Guarded Capital
Allocation & Payout Waterfall Module (Requirement R4).

Mathematical Foundations & Architecture:
----------------------------------------
1. Debt Amortization Schedule & Invariants:
   - Opening Debt: Debt_Opening_t = Base_Debt for t=1, Debt_Closing_{t-1} for t>1
   - Principal Amortization: Principal_Amort_t = min(Debt_Opening_t, Debt_Opening_t * r_amort)
   - New Borrowings: New_Borrowings_t = max(0, CapEx_t * delta_debt)
   - Closing Debt Identity: Debt_Closing_t = Debt_Opening_t + New_Borrowings_t - Principal_Amort_t
   - Midpoint Average Debt: Average_Debt_t = (Debt_Opening_t + Debt_Closing_t) / 2
   - Net Debt Drawdown: Net_Debt_Drawdown_t = New_Borrowings_t - Principal_Amort_t

2. Damodaran Synthetic Credit Rating & Credit Spread:
   - ICR = EBIT_t / max(Interest_Expense_t, 1.0) (Gated: EBIT<=0 -> -1.0 / D, Int<=0 -> 100.0 / AAA)
   - Large-Cap (> 5,000B VND) & Small-Cap (<= 5,000B VND) Damodaran spread tables (AAA to D)
   - Pre-Tax Cost of Debt: Kd_pre_tax = Rf + Spread (Rf = 5.0%)
   - After-Tax Cost of Debt: Kd_after_tax = Kd_pre_tax * (1 - Tax_Rate) (Tax = 20.0%)

3. Iterative Fixed-Point Convergence Algorithm:
   - Resolves circularity between Interest Expense, Average Debt, and Kd(ICR) in <= 5 iterations.

4. Solvency-Guarded Capital Allocation & Waterfall:
   - Statutory Retained Earnings & Profitability Gating: NPAT_t <= 0 -> Dividends = 0.0
   - Debt Covenant Firewall: ICR_t < 1.20 -> 100% Dividend Freeze (Dividends = 0.0, is_covenant_breached = True)
   - Actual Dividends Paid: Dividends_Paid_t = min(NPAT_t, NPAT_t * Payout_Ratio) when solvent
   - Share Repurchases: Model repurchase allocation when ICR >= min_icr and NPAT > 0.
=============================================================================
"""

from __future__ import annotations

import math
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from pydantic import BaseModel, Field

from services.market_calendar import default_forecast_start_year

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS & DAMODARAN SPREAD TABLES
# =============================================================================

DEFAULT_RF: float = 0.0500        # Vietnam 10-Year Government Bond benchmark yield (5.0%)
DEFAULT_TAX_RATE: float = 0.20    # Standard Vietnam Corporate Income Tax Rate (20%)

# Damodaran Synthetic Credit Rating Table based on Interest Coverage Ratio (ICR)
# Format: (min_icr: float, rating: str, spread_over_rf: float)
DAMODARAN_SPREAD_LARGE_CAP: List[Tuple[float, str, float]] = [
    (8.50, "AAA", 0.0065), # 65 bps
    (6.50, "AA",  0.0090), # 90 bps
    (5.50, "A+",  0.0115), # 115 bps
    (4.25, "A",   0.0135), # 135 bps
    (3.00, "A-",  0.0160), # 160 bps
    (2.50, "BBB", 0.0210), # 210 bps (Investment Grade boundary)
    (2.25, "BB+", 0.0285), # 285 bps
    (2.00, "BB",  0.0340), # 340 bps
    (1.75, "B+",  0.0425), # 425 bps
    (1.50, "B",   0.0525), # 525 bps
    (1.25, "B-",  0.0650), # 650 bps (Distress Gating Threshold)
    (0.80, "CCC", 0.0850), # 850 bps
    (0.50, "CC",  0.1000), # 1000 bps
    (-float("inf"), "D", 0.1250), # 1250 bps (Default/Distressed Loss)
]

DAMODARAN_SPREAD_SMALL_CAP: List[Tuple[float, str, float]] = [
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


# =============================================================================
# ARITHMETIC & SANITIZATION HELPERS
# =============================================================================

def sanitize_float(val: Any, fallback: float = 0.0) -> float:
    """
    Sanitizes arbitrary inputs (strings with commas, $, None, nan, inf) into safe finite floats.
    """
    if val is None:
        return fallback
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return fallback
        return float(val)
    if isinstance(val, str):
        s = val.strip().replace(",", "").replace(" ", "").replace("$", "")
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
# PYDANTIC DATA CONTRACTS (Pydantic v1 & v2 Compatible)
# =============================================================================

class CapitalAllocationPolicy(BaseModel):
    """
    Policy governing dividend distribution, share repurchases, and debt financing.
    """
    target_dividend_payout_ratio: float = Field(
        default=0.30,
        description="Target dividend payout as fraction of NPAT (0.0 to 1.0)"
    )
    dividend_payout_ratio: float = Field(
        default=0.30,
        description="Target dividend payout as fraction of NPAT (alias)"
    )
    min_icr_for_dividend: float = Field(
        default=1.20,
        description="Minimum ICR threshold before dividends are legally blocked"
    )
    icr_covenant_threshold: float = Field(
        default=1.20,
        description="Minimum ICR threshold before dividends are legally blocked (alias)"
    )
    debt_funded_capex_ratio: float = Field(
        default=0.40,
        description="Fraction of annual CapEx financed via new debt drawdowns"
    )
    debt_financing_ratio: float = Field(
        default=0.40,
        description="Fraction of annual CapEx financed via new debt drawdowns (alias)"
    )
    annual_amortization_rate: float = Field(
        default=0.20,
        description="Annual straight-line principal amortization rate"
    )
    mandatory_amortization_rate: float = Field(
        default=0.20,
        description="Annual straight-line principal amortization rate (alias)"
    )
    enable_share_repurchases: bool = Field(
        default=False,
        description="Whether share repurchases are enabled"
    )
    max_share_repurchase_pct_npat: float = Field(
        default=0.10,
        description="Maximum fraction of NPAT allocated to share buybacks"
    )
    share_repurchase_ratio: float = Field(
        default=0.00,
        description="Target share repurchase ratio (alias)"
    )
    min_cash_buffer_ratio: float = Field(
        default=0.02,
        description="Minimum operating cash buffer as % of Revenue"
    )
    min_cash_buffer_abs: float = Field(
        default=0.0,
        description="Absolute minimum cash floor in VND"
    )
    tax_rate: float = Field(
        default=0.20,
        description="Corporate Income Tax rate"
    )
    risk_free_rate: float = Field(
        default=0.0500,
        description="Benchmark 10Y Government Bond yield"
    )
    is_large_cap: bool = Field(
        default=True,
        description="True if Market Cap > 5,000 Billion VND"
    )
    enable_excess_cash_sweep: bool = Field(
        default=False,
        description="Whether excess cash is used for early debt amortization"
    )

    def __init__(self, **data: Any):
        # Synchronize aliases in input data if one is provided but not the other
        if "dividend_payout_ratio" in data and "target_dividend_payout_ratio" not in data:
            data["target_dividend_payout_ratio"] = data["dividend_payout_ratio"]
        elif "target_dividend_payout_ratio" in data and "dividend_payout_ratio" not in data:
            data["dividend_payout_ratio"] = data["target_dividend_payout_ratio"]

        if "icr_covenant_threshold" in data and "min_icr_for_dividend" not in data:
            data["min_icr_for_dividend"] = data["icr_covenant_threshold"]
        elif "min_icr_for_dividend" in data and "icr_covenant_threshold" not in data:
            data["icr_covenant_threshold"] = data["min_icr_for_dividend"]

        if "debt_financing_ratio" in data and "debt_funded_capex_ratio" not in data:
            data["debt_funded_capex_ratio"] = data["debt_financing_ratio"]
        elif "debt_funded_capex_ratio" in data and "debt_financing_ratio" not in data:
            data["debt_financing_ratio"] = data["debt_funded_capex_ratio"]

        if "mandatory_amortization_rate" in data and "annual_amortization_rate" not in data:
            data["annual_amortization_rate"] = data["mandatory_amortization_rate"]
        elif "annual_amortization_rate" in data and "mandatory_amortization_rate" not in data:
            data["mandatory_amortization_rate"] = data["annual_amortization_rate"]

        if "share_repurchase_ratio" in data and "max_share_repurchase_pct_npat" not in data:
            data["max_share_repurchase_pct_npat"] = data["share_repurchase_ratio"]
            if data.get("share_repurchase_ratio", 0.0) > 0 and "enable_share_repurchases" not in data:
                data["enable_share_repurchases"] = True

        super().__init__(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model to dictionary with v1/v2 compatibility."""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


class DebtSchedulePeriod(BaseModel):
    """
    Complete Debt, Capital Allocation, and Solvency Metrics for a single forecast period.
    """
    year: int = Field(default_factory=default_forecast_start_year,
                      description="Forecast Year; defaults to the current year")
    year_index: int = Field(default=1, description="1-based period index (1 to 5)")

    # Debt Balances & Roll-Forward
    opening_debt: float = Field(default=0.0, description="Opening Interest-Bearing Debt")
    principal_amortization: float = Field(default=0.0, description="Mandatory Principal Amortization Repaid")
    new_borrowings: float = Field(default=0.0, description="New Debt Drawdowns (CapEx/Expansion)")
    closing_debt: float = Field(default=0.0, description="Closing Total Debt (Opening + Borrow - Amort)")
    average_debt: float = Field(default=0.0, description="Average Debt Balance ((Opening + Closing) / 2)")
    short_term_debt: float = Field(default=0.0, description="Current / Short-Term Portion of Debt")
    long_term_debt: float = Field(default=0.0, description="Non-Current / Long-Term Debt")
    net_debt_drawdown: float = Field(default=0.0, description="Net Debt Drawdown in CFF (New Borrow - Amort)")

    # Operating Earnings & Coverage
    ebit: float = Field(default=0.0, description="Operating Profit (EBIT)")
    interest_coverage_ratio: float = Field(default=0.0, description="Interest Coverage Ratio (EBIT / Interest Expense)")
    synthetic_rating: str = Field(default="BBB", description="Damodaran Synthetic Rating (AAA to D)")
    credit_spread_bps: float = Field(default=210.0, description="Credit Spread in Basis Points")
    credit_spread: float = Field(default=0.0210, description="Credit Spread as Decimal")
    cost_of_debt_pre_tax: float = Field(default=0.0710, description="Pre-Tax Cost of Debt (Rf + Spread)")
    pre_tax_kd: float = Field(default=0.0710, description="Pre-Tax Cost of Debt (alias)")
    cost_of_debt_after_tax: float = Field(default=0.0568, description="After-Tax Cost of Debt (Kd * (1 - Tax))")
    after_tax_kd: float = Field(default=0.0568, description="After-Tax Cost of Debt (alias)")

    # Financial Statement P&L / CFS Flow Items
    interest_expense: float = Field(default=0.0, description="Income Statement Interest Expense")
    interest_income: float = Field(default=0.0, description="Interest Income on Cash Assets")
    cash_interest_paid: float = Field(default=0.0, description="Cash Flow Statement Interest Outflow")

    # Profitability & Capital Allocation Distributions
    npat: float = Field(default=0.0, description="Net Profit After Tax")
    target_dividends: float = Field(default=0.0, description="Target Dividends before Solvency Guard")
    dividends_paid: float = Field(default=0.0, description="Actual Cash Dividends Paid (CFF Outflow)")
    target_repurchases: float = Field(default=0.0, description="Target Share Repurchases")
    share_repurchases: float = Field(default=0.0, description="Actual Share Repurchases Paid (CFF Outflow)")
    total_shareholder_distributions: float = Field(default=0.0, description="Total Dividends + Repurchases")
    total_capital_returned: float = Field(default=0.0, description="Total Capital Returned (Dividends + Repurchases)")
    effective_payout_ratio: float = Field(default=0.0, description="Effective Payout Ratio (Dividends / NPAT)")

    # Solvency & Diagnostic Firewalls
    is_covenant_breached: bool = Field(default=False, description="True if ICR < Covenant Threshold")
    is_dividend_curtailed: bool = Field(default=False, description="True if Dividends were reduced by Solvency Guard")
    curtailment_reason: Optional[str] = Field(default=None, description="Reason code if dividends curtailed")
    covenant_notes: Optional[str] = Field(default=None, description="Covenant diagnostic notes")

    def __init__(self, **data: Any):
        # Synchronize pre_tax_kd and cost_of_debt_pre_tax
        if "cost_of_debt_pre_tax" in data and "pre_tax_kd" not in data:
            data["pre_tax_kd"] = data["cost_of_debt_pre_tax"]
        elif "pre_tax_kd" in data and "cost_of_debt_pre_tax" not in data:
            data["cost_of_debt_pre_tax"] = data["pre_tax_kd"]

        # Synchronize after_tax_kd and cost_of_debt_after_tax
        if "cost_of_debt_after_tax" in data and "after_tax_kd" not in data:
            data["after_tax_kd"] = data["cost_of_debt_after_tax"]
        elif "after_tax_kd" in data and "cost_of_debt_after_tax" not in data:
            data["cost_of_debt_after_tax"] = data["after_tax_kd"]

        # Synchronize total_capital_returned and total_shareholder_distributions
        if "total_shareholder_distributions" in data and "total_capital_returned" not in data:
            data["total_capital_returned"] = data["total_shareholder_distributions"]
        elif "total_capital_returned" in data and "total_shareholder_distributions" not in data:
            data["total_shareholder_distributions"] = data["total_capital_returned"]
        elif "total_shareholder_distributions" not in data and "total_capital_returned" not in data:
            div = data.get("dividends_paid", 0.0)
            rep = data.get("share_repurchases", 0.0)
            data["total_shareholder_distributions"] = div + rep
            data["total_capital_returned"] = div + rep

        if "covenant_notes" in data and "curtailment_reason" not in data:
            data["curtailment_reason"] = data["covenant_notes"]
        elif "curtailment_reason" in data and "covenant_notes" not in data:
            data["covenant_notes"] = data["curtailment_reason"]

        super().__init__(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model to dictionary with v1/v2 compatibility."""
        if hasattr(self, "model_dump"):
            d = self.model_dump()
        else:
            d = self.dict()
        d["pre_tax_kd"] = self.pre_tax_kd
        d["after_tax_kd"] = self.after_tax_kd
        return d


class DebtCapitalScheduleResult(BaseModel):
    """
    Complete Multi-Period Debt & Capital Allocation Schedule Result.
    """
    symbol: str = Field(default="", description="Stock Ticker Symbol")
    sector: str = Field(default="DEFAULT", description="Sector classification")
    market_cap: float = Field(default=10_000e9, description="Market Capitalization in VND")
    base_debt: float = Field(default=0.0, description="Base Historical Debt")
    is_large_cap: bool = Field(default=True, description="Market Cap Category (> 5,000B VND)")
    policy: CapitalAllocationPolicy = Field(default_factory=CapitalAllocationPolicy)
    schedule: List[DebtSchedulePeriod] = Field(default_factory=list, description="5-Year Period Schedules")
    periods: List[DebtSchedulePeriod] = Field(default_factory=list, description="5-Year Period Schedules (alias)")

    # 5-Year Cumulative Totals
    total_interest_expense_5y: float = Field(default=0.0, description="Cumulative 5Y Interest Expense")
    total_principal_paid_5y: float = Field(default=0.0, description="Cumulative 5Y Principal Amortization")
    total_new_borrowings_5y: float = Field(default=0.0, description="Cumulative 5Y New Borrowings")
    total_net_debt_change_5y: float = Field(default=0.0, description="Cumulative 5Y Net Debt Change")
    total_dividends_paid_5y: float = Field(default=0.0, description="Cumulative 5Y Dividends Paid")
    total_share_repurchases_5y: float = Field(default=0.0, description="Cumulative 5Y Share Repurchases")

    # Terminal Metrics (for DCF/WACC/DDM Linkage)
    terminal_cost_of_debt_pre_tax: float = Field(default=0.0710, description="Year 5 Pre-Tax Kd")
    terminal_cost_of_debt_after_tax: float = Field(default=0.0568, description="Year 5 After-Tax Kd")
    terminal_synthetic_rating: str = Field(default="BBB", description="Year 5 Credit Rating")
    terminal_credit_spread_bps: float = Field(default=210.0, description="Year 5 Credit Spread Bps")

    summary: Dict[str, Any] = Field(default_factory=dict, description="Summary aggregates")
    summary_metrics: Dict[str, Any] = Field(default_factory=dict, description="Summary metrics (alias)")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Audit and Diagnostic Summary")

    def __init__(self, **data: Any):
        if "periods" in data and "schedule" not in data:
            data["schedule"] = data["periods"]
        elif "schedule" in data and "periods" not in data:
            data["periods"] = data["schedule"]

        if "summary_metrics" in data and "summary" not in data:
            data["summary"] = data["summary_metrics"]
        elif "summary" in data and "summary_metrics" not in data:
            data["summary_metrics"] = data["summary"]

        super().__init__(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model to dictionary with v1/v2 compatibility."""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


# Backward / Forward Compatibility Alias
DebtCapitalForecastResult = DebtCapitalScheduleResult


# =============================================================================
# DEBT & CAPITAL SCHEDULE ENGINE
# =============================================================================

class DebtCapitalScheduleEngine:
    """
    Comprehensive Institutional Engine for Debt Amortization, Synthetic Ratings,
    Cost of Debt (Kd), and Solvency-Guarded Capital Allocation.
    """

    @staticmethod
    def calculate_icr(ebit: float, interest_expense: float) -> float:
        """
        Computes Interest Coverage Ratio (ICR = EBIT / Interest Expense).
        Handles edge cases:
        - If ebit <= 0: returns -1.0 (operating loss / distressed)
        - If interest_expense <= 0: returns 100.0 (debt-free firm)
        - Otherwise: returns ebit / max(interest_expense, 1.0)
        """
        clean_ebit = sanitize_float(ebit, 0.0)
        clean_int = max(0.0, sanitize_float(interest_expense, 0.0))

        if clean_ebit <= 0.0:
            return -1.0
        if clean_int <= 0.0:
            return 100.0
        return safe_div(clean_ebit, max(clean_int, 1.0), fallback=100.0)

    @staticmethod
    def calculate_synthetic_rating(
        icr: float,
        is_large_cap: bool = True,
    ) -> Tuple[str, float]:
        """
        Maps Interest Coverage Ratio (ICR) to Damodaran synthetic credit rating and credit spread.
        Returns (rating: str, spread: float).
        """
        clean_icr = sanitize_float(icr, -1.0)
        table = DAMODARAN_SPREAD_LARGE_CAP if is_large_cap else DAMODARAN_SPREAD_SMALL_CAP

        synth_rating = "D"
        spread = 0.1250
        for min_icr, rating, sp in table:
            if clean_icr >= min_icr:
                synth_rating = rating
                spread = sp
                break

        return synth_rating, spread

    @staticmethod
    def calculate_cost_of_debt(
        icr: float,
        is_large_cap: bool = True,
        rf: float = DEFAULT_RF,
        tax_rate: float = DEFAULT_TAX_RATE,
    ) -> Tuple[str, float, float, float]:
        """
        Computes (synthetic_rating, credit_spread, cost_of_debt_pre_tax, cost_of_debt_after_tax).
        """
        clean_rf = sanitize_float(rf, DEFAULT_RF)
        clean_tax = sanitize_float(tax_rate, DEFAULT_TAX_RATE)

        rating, spread = DebtCapitalScheduleEngine.calculate_synthetic_rating(icr, is_large_cap)
        kd_pre_tax = clean_rf + spread
        kd_after_tax = kd_pre_tax * (1.0 - clean_tax)

        return rating, spread, kd_pre_tax, kd_after_tax

    @staticmethod
    def project_debt_and_capital_schedule(
        base_debt: float,
        ebit_series: List[float],
        npat_series: List[float],
        capex_series: List[float],
        market_cap: float = 10_000e9,
        policy: Optional[CapitalAllocationPolicy] = None,
        rf: float = DEFAULT_RF,
        tax_rate: float = DEFAULT_TAX_RATE,
        start_year: Optional[int] = None,
    ) -> List[DebtSchedulePeriod]:
        """
        Projects 5-year debt roll-forward schedule and solvency-guarded capital allocation.
        """
        start_year = start_year if start_year is not None else default_forecast_start_year()
        pol = policy if policy is not None else CapitalAllocationPolicy()
        clean_base_debt = max(0.0, sanitize_float(base_debt, 0.0))
        clean_mcap = sanitize_float(market_cap, 10_000e9)
        if hasattr(pol, "model_fields_set"):
            fields_set = pol.model_fields_set
        else:
            fields_set = getattr(pol, "__fields_set__", set())
        is_large_cap = (clean_mcap / 1e9) > 5000.0 if "is_large_cap" not in fields_set else pol.is_large_cap

        clean_rf = sanitize_float(rf, pol.risk_free_rate)
        clean_tax = sanitize_float(tax_rate, pol.tax_rate)

        # Extract policy rates and clamp safely
        amort_rate = clamp(getattr(pol, "annual_amortization_rate", getattr(pol, "mandatory_amortization_rate", 0.20)), 0.0, 1.0)
        capex_debt_ratio = clamp(getattr(pol, "debt_funded_capex_ratio", getattr(pol, "debt_financing_ratio", 0.40)), 0.0, 1.0)
        payout_ratio = clamp(getattr(pol, "target_dividend_payout_ratio", getattr(pol, "dividend_payout_ratio", 0.30)), 0.0, 1.0)
        min_icr = sanitize_float(getattr(pol, "min_icr_for_dividend", getattr(pol, "icr_covenant_threshold", 1.20)), 1.20)
        enable_repurchases = bool(getattr(pol, "enable_share_repurchases", False))
        repurchase_ratio = clamp(getattr(pol, "max_share_repurchase_pct_npat", getattr(pol, "share_repurchase_ratio", 0.0)), 0.0, 1.0)

        num_periods = max(5, len(ebit_series), len(npat_series), len(capex_series))
        schedule: List[DebtSchedulePeriod] = []

        current_opening_debt = clean_base_debt

        for idx in range(num_periods):
            yr = start_year + idx
            yr_idx = idx + 1

            ebit_val = sanitize_float(ebit_series[idx]) if idx < len(ebit_series) else 0.0
            npat_val = sanitize_float(npat_series[idx]) if idx < len(npat_series) else 0.0
            capex_val = max(0.0, sanitize_float(capex_series[idx])) if idx < len(capex_series) else 0.0

            # 1. Debt Roll-Forward
            # Principal amortization clamped between 0 and opening debt
            amort = min(current_opening_debt, current_opening_debt * amort_rate)
            amort = max(0.0, amort)

            # New borrowings from CapEx debt financing
            new_borrowings = max(0.0, capex_val * capex_debt_ratio)

            # Closing debt
            closing_debt = max(0.0, current_opening_debt + new_borrowings - amort)

            # Average debt
            avg_debt = (current_opening_debt + closing_debt) / 2.0

            # Short-term and Long-term debt breakdown
            st_debt = min(closing_debt, closing_debt * 0.35)
            lt_debt = max(0.0, closing_debt - st_debt)

            # Net debt drawdown in CFF
            net_drawdown = new_borrowings - amort

            # 2. Fixed-Point Iteration for Interest Expense, ICR, and Synthetic Rating
            if avg_debt <= 0.0:
                rating = "AAA"
                spread = 0.0065
                kd_pre = clean_rf + spread
                kd_after = kd_pre * (1.0 - clean_tax)
                int_exp = 0.0
                icr = 100.0
            elif ebit_val <= 0.0:
                rating = "D"
                spread = 0.1250
                kd_pre = clean_rf + spread
                kd_after = kd_pre * (1.0 - clean_tax)
                int_exp = avg_debt * kd_pre
                icr = -1.0
            else:
                # Iterative convergence solver
                current_spread = 0.0210  # Initial guess (BBB)
                rating = "BBB"
                for _ in range(5):
                    kd_pre = clean_rf + current_spread
                    trial_int = avg_debt * kd_pre
                    trial_icr = DebtCapitalScheduleEngine.calculate_icr(ebit_val, trial_int)
                    new_rating, new_spread = DebtCapitalScheduleEngine.calculate_synthetic_rating(trial_icr, is_large_cap)
                    if new_rating == rating and math.isclose(new_spread, current_spread, abs_tol=1e-5):
                        break
                    rating = new_rating
                    current_spread = new_spread
                spread = current_spread
                kd_pre = clean_rf + spread
                kd_after = kd_pre * (1.0 - clean_tax)
                int_exp = avg_debt * kd_pre
                icr = DebtCapitalScheduleEngine.calculate_icr(ebit_val, int_exp)

            cash_int_paid = int_exp
            spread_bps = spread * 10_000.0

            # 3. Solvency-Guarded Dividend and Capital Allocation
            target_div = max(0.0, npat_val * payout_ratio) if npat_val > 0.0 else 0.0

            is_cov_breached = False
            curtailment_reason = None
            covenant_notes = None

            if avg_debt > 0.0 and int_exp > 0.0:
                if icr < min_icr:
                    is_cov_breached = True
                    covenant_notes = f"ICR {icr:.2f} below {min_icr:.2f} threshold"
            elif ebit_val <= 0.0 and (current_opening_debt > 0.0 or new_borrowings > 0.0):
                is_cov_breached = True
                covenant_notes = f"Operating loss with debt burden (ICR {icr:.2f})"

            if npat_val <= 0.0:
                div_paid = 0.0
                is_curtailed = target_div > 0.0 or payout_ratio > 0.0
                curtailment_reason = "NEGATIVE_OR_ZERO_NPAT"
            elif is_cov_breached:
                div_paid = 0.0
                is_curtailed = True
                curtailment_reason = "COVENANT_BREACH_ICR_BELOW_1_2"
                if not covenant_notes:
                    covenant_notes = "ICR below 1.20 threshold"
            else:
                div_paid = min(npat_val, target_div)
                is_curtailed = False

            # 4. Share Repurchases
            if enable_repurchases and not is_cov_breached and npat_val > 0.0 and icr >= min_icr:
                target_rep = max(0.0, npat_val * repurchase_ratio)
                repurchases_paid = target_rep
            else:
                target_rep = 0.0
                repurchases_paid = 0.0

            total_dist = div_paid + repurchases_paid
            eff_payout = safe_div(div_paid, npat_val, fallback=0.0) if npat_val > 0.0 else 0.0

            period = DebtSchedulePeriod(
                year=yr,
                year_index=yr_idx,
                opening_debt=current_opening_debt,
                principal_amortization=amort,
                new_borrowings=new_borrowings,
                closing_debt=closing_debt,
                average_debt=avg_debt,
                short_term_debt=st_debt,
                long_term_debt=lt_debt,
                net_debt_drawdown=net_drawdown,
                ebit=ebit_val,
                interest_coverage_ratio=icr,
                synthetic_rating=rating,
                credit_spread_bps=spread_bps,
                credit_spread=spread,
                cost_of_debt_pre_tax=kd_pre,
                cost_of_debt_after_tax=kd_after,
                interest_expense=int_exp,
                cash_interest_paid=cash_int_paid,
                npat=npat_val,
                target_dividends=target_div,
                dividends_paid=div_paid,
                target_repurchases=target_rep,
                share_repurchases=repurchases_paid,
                total_shareholder_distributions=total_dist,
                total_capital_returned=total_dist,
                effective_payout_ratio=eff_payout,
                is_covenant_breached=is_cov_breached,
                is_dividend_curtailed=is_curtailed,
                curtailment_reason=curtailment_reason,
                covenant_notes=covenant_notes,
            )

            schedule.append(period)
            # Roll forward opening debt for next period
            current_opening_debt = closing_debt

        return schedule

    @staticmethod
    def build_debt_schedule_forecast(
        symbol: str,
        base_data: Dict[str, Any],
        ebit_forecast: List[float],
        npat_forecast: List[float],
        capex_forecast: List[float],
        policy: Optional[CapitalAllocationPolicy] = None,
        start_year: Optional[int] = None,
    ) -> DebtCapitalScheduleResult:
        """
        Builds complete 5-year debt & capital allocation forecast result from base fundamentals.
        """
        start_year = start_year if start_year is not None else default_forecast_start_year()
        clean_symbol = str(symbol).strip().upper()
        sector = str(base_data.get("sector") or base_data.get("sector_code") or "DEFAULT").strip().upper()

        # Extract fundamentals safely with robust sanitization
        base_debt = sanitize_float(
            base_data.get("total_debt") or 
            base_data.get("interest_bearing_debt") or 
            base_data.get("base_debt") or 
            0.0
        )
        market_cap = sanitize_float(
            base_data.get("market_cap") or 
            base_data.get("mcap") or 
            10_000e9
        )
        rf = sanitize_float(
            base_data.get("rf") or 
            base_data.get("risk_free_rate") or 
            DEFAULT_RF
        )
        tax_rate = sanitize_float(
            base_data.get("tax_rate") or 
            DEFAULT_TAX_RATE
        )

        # Determine Large-Cap status (> 5,000 Billion VND)
        is_large_cap = (market_cap / 1e9) > 5000.0

        # Financial sector identification
        financial_tickers = {
            "VCB", "TCB", "MBB", "ACB", "BID", "CTG", "VPB", "STB", "HDB", "VIB",
            "TPB", "SSB", "MSB", "OCB", "EIB", "LPB", "SHB", "NAB", "BAB", "BVB",
            "KLB", "PGB", "SGB", "VBB", "NVB", "SSI", "VND", "VCI", "HCM", "SHS",
            "MBS", "FTS", "BSI", "CTS", "VIX", "AGR", "BVH", "PVI", "BMI", "MIG",
            "BIC", "VNR"
        }
        is_financial = clean_symbol in financial_tickers or any(
            k in sector for k in ("BANK", "BNK", "FIN", "SEC", "INS", "8300", "8500", "8700")
        )

        pol = policy if policy is not None else CapitalAllocationPolicy(is_large_cap=is_large_cap)

        schedule = DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
            base_debt=base_debt,
            ebit_series=ebit_forecast,
            npat_series=npat_forecast,
            capex_series=capex_forecast,
            market_cap=market_cap,
            policy=pol,
            rf=rf,
            tax_rate=tax_rate,
            start_year=start_year,
        )

        # 5-Year Cumulative Totals
        tot_int = sum(p.interest_expense for p in schedule)
        tot_amort = sum(p.principal_amortization for p in schedule)
        tot_borrow = sum(p.new_borrowings for p in schedule)
        tot_net_debt_change = sum(p.net_debt_drawdown for p in schedule)
        tot_div = sum(p.dividends_paid for p in schedule)
        tot_rep = sum(p.share_repurchases for p in schedule)
        tot_cap_returned = tot_div + tot_rep

        # Terminal Metrics
        last_period = schedule[-1] if schedule else DebtSchedulePeriod(year=start_year)
        term_kd_pre = last_period.cost_of_debt_pre_tax
        term_kd_after = last_period.cost_of_debt_after_tax
        term_rating = last_period.synthetic_rating
        term_spread_bps = last_period.credit_spread_bps

        # Weighted Average Kd
        tot_avg_debt = sum(p.average_debt for p in schedule)
        if tot_avg_debt > 0:
            weighted_kd_pre = tot_int / tot_avg_debt
        else:
            weighted_kd_pre = term_kd_pre

        cov_breach_count = sum(1 for p in schedule if p.is_covenant_breached)

        summary = {
            "symbol": clean_symbol,
            "sector": sector,
            "is_financial_sector": is_financial,
            "is_large_cap": is_large_cap,
            "market_cap": market_cap,
            "base_debt": base_debt,
            "total_interest_expense_5y": tot_int,
            "total_principal_paid_5y": tot_amort,
            "total_new_borrowings_5y": tot_borrow,
            "total_net_debt_change_5y": tot_net_debt_change,
            "total_dividends_5y": tot_div,
            "total_dividends_paid_5y": tot_div,
            "total_repurchases_5y": tot_rep,
            "total_capital_returned_5y": tot_cap_returned,
            "weighted_average_kd_pre_tax": weighted_kd_pre,
            "terminal_synthetic_rating": term_rating,
            "terminal_credit_spread_bps": term_spread_bps,
            "terminal_kd_pre_tax": term_kd_pre,
            "terminal_kd_after_tax": term_kd_after,
            "covenant_breach_count": cov_breach_count,
        }

        diagnostics = {
            "is_financial_isolated": is_financial,
            "covenant_breached_periods": [p.year for p in schedule if p.is_covenant_breached],
            "dividend_curtailed_periods": [p.year for p in schedule if p.is_dividend_curtailed],
        }

        return DebtCapitalScheduleResult(
            symbol=clean_symbol,
            sector=sector,
            market_cap=market_cap,
            base_debt=base_debt,
            is_large_cap=is_large_cap,
            policy=pol,
            schedule=schedule,
            periods=schedule,
            total_interest_expense_5y=tot_int,
            total_principal_paid_5y=tot_amort,
            total_new_borrowings_5y=tot_borrow,
            total_net_debt_change_5y=tot_net_debt_change,
            total_dividends_paid_5y=tot_div,
            total_share_repurchases_5y=tot_rep,
            terminal_cost_of_debt_pre_tax=term_kd_pre,
            terminal_cost_of_debt_after_tax=term_kd_after,
            terminal_synthetic_rating=term_rating,
            terminal_credit_spread_bps=term_spread_bps,
            summary=summary,
            summary_metrics=summary,
            diagnostics=diagnostics,
        )


# =============================================================================
# MODULE-LEVEL INTERFACE CONTRACT 2 FUNCTION
# =============================================================================

def build_debt_schedule(
    base_debt: float,
    ebit_series: List[float],
    capex_series: List[float],
    npat_series: List[float],
    start_year: Optional[int] = None,
    market_cap: float = 10_000e9,
    rf: float = DEFAULT_RF,
    tax_rate: float = DEFAULT_TAX_RATE,
    payout_ratio: float = 0.30,
) -> List[DebtSchedulePeriod]:
    """
    Interface Contract 2: Builds 5-Year Debt Schedule & Capital Allocation Roll-Forward.
    """
    start_year = start_year if start_year is not None else default_forecast_start_year()
    policy = CapitalAllocationPolicy(
        target_dividend_payout_ratio=payout_ratio,
        risk_free_rate=rf,
        tax_rate=tax_rate,
    )
    return DebtCapitalScheduleEngine.project_debt_and_capital_schedule(
        base_debt=base_debt,
        ebit_series=ebit_series,
        npat_series=npat_series,
        capex_series=capex_series,
        market_cap=market_cap,
        policy=policy,
        rf=rf,
        tax_rate=tax_rate,
        start_year=start_year,
    )

