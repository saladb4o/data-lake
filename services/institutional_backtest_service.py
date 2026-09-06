"""
Institutional-Grade Backtesting & Statistical Quant Validation Engine.
Designed for execution realism, parameter robustness, and statistical significance:
1. Iterative Two-Moment (Open/Close) Bar-by-Bar Execution Engine & Multi-Stock Factor Portfolios.
2. Dynamic Risk-Based Position Sizing & ATR Trailing Stops.
3. Realistic Vietnam Equity Friction: Commissions, Taxes, Slippage, T+2.5 Settlement, Price Limits.
4. Unified Support for All 32 Factor / Guru Strategies + Index Universes (VN30, VN70, HOSE, HNX, UPCOM, ALL).
5. 2D Parameter Sensitivity Scan & Plateau vs Cliff Detection Matrix.
6. Walk-Forward Analysis (WFA) with Rolling Window Stitching.
7. Monte Carlo Engine (1,000 Bootstrap 95% CI & 1,000 Permutation Sequence Risk).
"""

import math
import random
import datetime
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple

from services.market_calendar import (
    default_backtest_end_year,
    default_backtest_start_year,
)
from services.stock_service import get_stock_history, ALL_SYMBOLS_MAP
from services.backtest_service import (
    STRATEGY_DEFINITIONS,
    run_screener_backtest,
    QUARTERS_TIMELINE,
    _load_real_price_database
)
from services.fair_value_backtest_service import (
    FairValueBacktestService,
    BacktestMode,
    VALUATION_MODELS_CATALOG
)
import logging

logger = logging.getLogger(__name__)

VALUATION_STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = {
    "val_composite_fair_value": {
        "id": "val_composite_fair_value",
        "name": "🏆 Adaptive Composite (22 Mô Hình Định Giá)",
        "short_name": "Composite Fair Value",
        "color": "#facc15",
        "category": "valuation",
        "model_id": "composite_fair_value"
    },
    "val_blended_pe": {
        "id": "val_blended_pe",
        "name": "Blended P/E (TTM + Forward + CAPE)",
        "short_name": "Blended P/E",
        "color": "#38bdf8",
        "category": "valuation",
        "model_id": "blended_pe"
    },
    "val_ps_margin_adj": {
        "id": "val_ps_margin_adj",
        "name": "Margin-Adjusted P/S (Ken Fisher)",
        "short_name": "P/S Adjusted",
        "color": "#06b6d4",
        "category": "valuation",
        "model_id": "ps_margin_adj"
    },
    "val_p_fcf": {
        "id": "val_p_fcf",
        "name": "Price-to-FCF Yield Dòng Tiền Tự Do",
        "short_name": "P/FCF Yield",
        "color": "#10b981",
        "category": "valuation",
        "model_id": "p_fcf"
    },
    "val_pb_rhodes_kropf": {
        "id": "val_pb_rhodes_kropf",
        "name": "P/B với Bộ Lọc Rhodes-Kropf (RKV)",
        "short_name": "P/B RKV Anti-Trap",
        "color": "#eab308",
        "category": "valuation",
        "model_id": "pb_rhodes_kropf"
    },
    "val_p_tbv": {
        "id": "val_p_tbv",
        "name": "Price-to-Tangible Book (P/TBV)",
        "short_name": "P/TBV Multiple",
        "color": "#f97316",
        "category": "valuation",
        "model_id": "p_tbv"
    },
    "val_ev_ebitda": {
        "id": "val_ev_ebitda",
        "name": "Blended EV/EBITDA Doanh Nghiệp",
        "short_name": "EV/EBITDA",
        "color": "#a855f7",
        "category": "valuation",
        "model_id": "ev_ebitda"
    },
    "val_p_cf": {
        "id": "val_p_cf",
        "name": "Price-to-Operating Cash Flow (P/CF)",
        "short_name": "P/CF Multiple",
        "color": "#14b8a6",
        "category": "valuation",
        "model_id": "p_cf"
    },
    "val_p_affo": {
        "id": "val_p_affo",
        "name": "Price-to-AFFO Multiple (P/AFFO)",
        "short_name": "P/AFFO Multiple",
        "color": "#ec4899",
        "category": "valuation",
        "model_id": "p_affo"
    },
    "val_dcf_2stage_mckinsey": {
        "id": "val_dcf_2stage_mckinsey",
        "name": "Extended 2-Stage McKinsey DCF (ROIC/WACC)",
        "short_name": "McKinsey DCF",
        "color": "#6366f1",
        "category": "valuation",
        "model_id": "dcf_2stage_mckinsey"
    },
    "val_rim_edwards_bell_ohlson": {
        "id": "val_rim_edwards_bell_ohlson",
        "name": "Residual Income Model (RIM / EBO)",
        "short_name": "RIM / EBO",
        "color": "#8b5cf6",
        "category": "valuation",
        "model_id": "rim_edwards_bell_ohlson"
    },
    "val_greenwald_epv": {
        "id": "val_greenwald_epv",
        "name": "Greenwald Earnings Power Value (EPV)",
        "short_name": "Greenwald EPV",
        "color": "#3b82f6",
        "category": "valuation",
        "model_id": "greenwald_epv"
    },
    "val_graham_growth": {
        "id": "val_graham_growth",
        "name": "Modern Graham Growth Formula",
        "short_name": "Graham Growth",
        "color": "#0ea5e9",
        "category": "valuation",
        "model_id": "graham_growth"
    },
    "val_rule_of_40_growth": {
        "id": "val_rule_of_40_growth",
        "name": "Rule of 40 / Rule of 65 Super-Stock",
        "short_name": "Rule of 40/65",
        "color": "#06b6d4",
        "category": "valuation",
        "model_id": "rule_of_40_growth"
    },
    "val_acquirers_multiple_ev_ebit": {
        "id": "val_acquirers_multiple_ev_ebit",
        "name": "Acquirer's Multiple (EV/EBIT Tobias Carlisle)",
        "short_name": "Acquirer's EV/EBIT",
        "color": "#10b981",
        "category": "valuation",
        "model_id": "acquirers_multiple_ev_ebit"
    },
    "val_buffett_owners_earnings": {
        "id": "val_buffett_owners_earnings",
        "name": "Warren Buffett Owner's Earnings DCF",
        "short_name": "Buffett Owner's Earnings",
        "color": "#f59e0b",
        "category": "valuation",
        "model_id": "buffett_owners_earnings"
    },
    "val_bank_equity_cash_flow": {
        "id": "val_bank_equity_cash_flow",
        "name": "Banking Equity Cash Flow & Basel II (Ngân Hàng)",
        "short_name": "Bank ECF Basel II",
        "color": "#3b82f6",
        "category": "valuation",
        "model_id": "bank_equity_cash_flow"
    },
    "val_reit_affo_dcf": {
        "id": "val_reit_affo_dcf",
        "name": "REIT & Quỹ Đất RNAV (Bất Động Sản)",
        "short_name": "REIT / RNAV BĐS",
        "color": "#ec4899",
        "category": "valuation",
        "model_id": "reit_affo_dcf"
    },
    "val_industrial_apv": {
        "id": "val_industrial_apv",
        "name": "Industrial Adjusted Present Value APV (Sản Xuất/Thép)",
        "short_name": "Industrial APV",
        "color": "#64748b",
        "category": "valuation",
        "model_id": "industrial_apv"
    },
    "val_consumer_eva_mva": {
        "id": "val_consumer_eva_mva",
        "name": "Consumer Economic Value Added EVA/MVA (Bán Lẻ)",
        "short_name": "Consumer EVA/MVA",
        "color": "#f43f5e",
        "category": "valuation",
        "model_id": "consumer_eva_mva"
    },
    "val_utilities_3stage_ddm": {
        "id": "val_utilities_3stage_ddm",
        "name": "3-Stage DDM Chiết Khấu Cổ Tức (Điện/Nước)",
        "short_name": "3-Stage DDM Utilities",
        "color": "#059669",
        "category": "valuation",
        "model_id": "utilities_3stage_ddm"
    },
    "val_pharma_rnpv": {
        "id": "val_pharma_rnpv",
        "name": "Pharma Risk-Adjusted NPV (Dược Phẩm)",
        "short_name": "Pharma rNPV",
        "color": "#8b5cf6",
        "category": "valuation",
        "model_id": "pharma_rnpv"
    },
    "val_telecom_unbundled_sotp": {
        "id": "val_telecom_unbundled_sotp",
        "name": "Telecom Unbundled SOTP & RAB (Viễn Thông)",
        "short_name": "Telecom SOTP",
        "color": "#0284c7",
        "category": "valuation",
        "model_id": "telecom_unbundled_sotp"
    },
    # Hybrid 2-Stage Funnel Combinations
    "hybrid_garp_composite": {
        "id": "hybrid_garp_composite",
        "name": "⭐ Hybrid: GARP Lynch + Composite MoS",
        "short_name": "Hybrid GARP + MoS",
        "color": "#f97316",
        "category": "hybrid",
        "screener": "peter_lynch_garp",
        "model_id": "composite_fair_value"
    },
    "hybrid_buffett_moat": {
        "id": "hybrid_buffett_moat",
        "name": "⭐ Hybrid: Warren Buffett Moat + Owner's Earnings",
        "short_name": "Hybrid Buffett Moat",
        "color": "#f59e0b",
        "category": "hybrid",
        "screener": "value_buffett",
        "model_id": "buffett_owners_earnings"
    },
    "hybrid_klarman_rkv": {
        "id": "hybrid_klarman_rkv",
        "name": "⭐ Hybrid: Deep Value Klarman + Rhodes-Kropf MoS",
        "short_name": "Hybrid Deep Value + RKV",
        "color": "#eab308",
        "category": "hybrid",
        "screener": "deep_value_klarman",
        "model_id": "pb_rhodes_kropf"
    },
    "hybrid_magic_formula": {
        "id": "hybrid_magic_formula",
        "name": "⭐ Hybrid: Magic Formula + Acquirer's EV/EBIT",
        "short_name": "Hybrid Magic Formula",
        "color": "#10b981",
        "category": "hybrid",
        "screener": "guru_magic_formula_greenblatt",
        "model_id": "acquirers_multiple_ev_ebit"
    },
    "hybrid_qval_dcf": {
        "id": "hybrid_qval_dcf",
        "name": "⭐ Hybrid: Quantitative Value Q-VAL + McKinsey DCF",
        "short_name": "Hybrid Q-VAL + DCF",
        "color": "#6366f1",
        "category": "hybrid",
        "screener": "gray_quantitative_value_qval",
        "model_id": "dcf_2stage_mckinsey"
    },
    "hybrid_novy_marx_epv": {
        "id": "hybrid_novy_marx_epv",
        "name": "⭐ Hybrid: Novy-Marx GP/A + Greenwald EPV",
        "short_name": "Hybrid GP/A + EPV",
        "color": "#3b82f6",
        "category": "hybrid",
        "screener": "novy_marx_quality_value",
        "model_id": "greenwald_epv"
    }
}

# ------------------------------------------------------------------------------
# CONSTANTS & VIETNAM MARKET TRADING CONSTRAINTS
# ------------------------------------------------------------------------------
DEFAULT_COMMISSION_PCT = 0.15   # 0.15% brokerage commission
DEFAULT_TAX_PCT = 0.10          # 0.10% seller withholding tax (Vietnam tax law)
DEFAULT_SLIPPAGE_PCT = 0.10     # 0.10% average market slippage
DEFAULT_ANNUAL_RF = 0.05        # 5.0% Vietnam 1-year Treasury bond yield baseline
DEFAULT_LOT_SIZE = 100          # Standard lot of 100 shares on HOSE/HNX/UPCOM

EXCHANGE_LIMITS = {
    "HOSE": 0.07,   # +/- 7% daily price limit
    "HNX": 0.10,    # +/- 10% daily price limit
    "UPCOM": 0.15   # +/- 15% daily price limit
}

INDEX_UNIVERSES = ["ALL", "VN30", "VN70", "VNMID", "HOSE", "HNX", "UPCOM", "VNINDEX"]

# ------------------------------------------------------------------------------
# TECHNICAL INDICATORS FOR DAILY OHLCV
# ------------------------------------------------------------------------------

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Computes Average True Range (ATR) with exponential smoothing."""
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def compute_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """Computes SuperTrend indicator and trend direction (+1 for Bullish, -1 for Bearish)."""
    atr = compute_atr(df, period)
    hl2 = (df['high'] + df['low']) / 2.0
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)
    
    in_uptrend = True
    for i in range(len(df)):
        if i == 0:
            supertrend.iloc[i] = lowerband.iloc[i]
            direction.iloc[i] = 1
            continue
            
        c = df['close'].iloc[i]
        prev_c = df['close'].iloc[i-1]
        prev_st = supertrend.iloc[i-1]
        
        if c > upperband.iloc[i-1]:
            in_uptrend = True
        elif c < lowerband.iloc[i-1]:
            in_uptrend = False
        else:
            in_uptrend = direction.iloc[i-1] == 1
            if in_uptrend and lowerband.iloc[i] < lowerband.iloc[i-1]:
                lowerband.iloc[i] = lowerband.iloc[i-1]
            if not in_uptrend and upperband.iloc[i] > upperband.iloc[i-1]:
                upperband.iloc[i] = upperband.iloc[i-1]
                
        if in_uptrend:
            supertrend.iloc[i] = lowerband.iloc[i]
            direction.iloc[i] = 1
        else:
            supertrend.iloc[i] = upperband.iloc[i]
            direction.iloc[i] = -1
            
    return supertrend, direction

# ------------------------------------------------------------------------------
# THE FUNDAMENTAL LAW OF ACTIVE MANAGEMENT (GRINOLD & KAHN)
# Original Law:     IR ≈ IC * sqrt(BR)
# Generalized Law:  IR ≈ TC * IC * sqrt(BR)
# ------------------------------------------------------------------------------

def compute_fundamental_law_active_management(
    equity_curve: List[Dict[str, Any]],
    benchmark_equity_curve: Optional[List[Dict[str, Any]]] = None,
    rebalance_cadence: str = "quarterly",
    top_k: int = 10,
    time_horizon_years: int = 3,
    trades: Optional[List[Dict[str, Any]]] = None,
    is_factor_portfolio: bool = True,
    survival_filter: bool = False,
    tsmom_filter: bool = False,
    forensic_filter: bool = False,
    rebalance_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Computes Grinold & Kahn's Fundamental Law of Active Management:
      Original Law:     IR ≈ IC * sqrt(BR)
      Generalized Law:  IR ≈ TC * IC * sqrt(BR)

    Components:
    1. IR (Information Ratio):
       Active Return (CAGR_strat - CAGR_bm) / Annualized Tracking Error.
       Scale: <=0 (Poor), 0.3-0.5 (Industry Norm), 0.5-0.75 (Good/Top Quartile), >=1.0 (World Class).

    2. IC (Information Coefficient):
       Correlation between forecasted factor ranks/signals and realized forward returns.
       Scale: <0 (Flawed), 0.01-0.03 (Quant Fund standard), 0.05-0.08 (Good), >0.10 (Rare/Elite, >0.20 Overfit warning).

    3. BR (Breadth):
       Number of independent investment decisions per year.
       Effective N = N / (1 + (N - 1) * rho_bar), where rho_bar is mean cross-sectional correlation.
       BR = N_eff * Rebalance_frequency_per_year.

    4. TC (Transfer Coefficient):
       Fidelity of translating insights into active portfolio positions under real-world constraints
       (Long-only, max single-position caps, friction, T+2.5 liquidity delay).
       Scale: <0.3 (Constrained/Poor), 0.3-0.5 (Long-Only Norm), 0.7-0.9 (Unconstrained/Long-Short), 1.0 (Theoretical).
    """
    if not equity_curve:
        return {}

    # Extract NAVs
    nav_series = [float(e.get("nav", 1e8)) for e in equity_curve]
    bm_series = [float(e.get("benchmark_nav", e.get("nav", 1e8))) for e in equity_curve]
    
    # 1. Periods & Horizon
    cadence_map = {"quarterly": 4.0, "semi_annual": 2.0, "annual": 1.0}
    freq_per_year = cadence_map.get(rebalance_cadence, 4.0) if is_factor_portfolio else 250.0
    
    initial_nav = max(1.0, nav_series[0])
    final_nav = max(1.0, nav_series[-1])

    bm_initial = max(1.0, bm_series[0])
    bm_final = max(1.0, bm_series[-1])

    years = max(0.2, float(time_horizon_years))
    cagr_port = (math.pow(max(0.01, final_nav / initial_nav), 1.0 / years) - 1.0) * 100.0 if final_nav > 0 else -100.0
    cagr_bm = (math.pow(max(0.01, bm_final / bm_initial), 1.0 / years) - 1.0) * 100.0 if bm_final > 0 else -100.0
    active_return_cagr = cagr_port - cagr_bm

    # Period Returns
    port_rets = [ (nav_series[i] - nav_series[i-1]) / nav_series[i-1] for i in range(1, len(nav_series)) ] if len(nav_series) > 1 else [0.0]
    bm_rets = [ (bm_series[i] - bm_series[i-1]) / bm_series[i-1] for i in range(1, len(bm_series)) ] if len(bm_series) > 1 else [0.0]
    excess_rets = [ p - b for p, b in zip(port_rets, bm_rets) ]

    # Tracking Error (Annualized Active Risk)
    te_period = float(np.std(excess_rets, ddof=1)) if len(excess_rets) > 1 else 0.05
    ann_tracking_error = te_period * math.sqrt(freq_per_year) * 100.0
    ann_tracking_error = max(1.5, ann_tracking_error)  # Minimum realistic floor 1.5%

    # Information Ratio (IR)
    realized_ir = active_return_cagr / ann_tracking_error

    # 2. Information Coefficient (IC)
    ic_values = []
    if rebalance_history and len(rebalance_history) > 0:
        for q in rebalance_history:
            h_list = q.get("holdings", [])
            if len(h_list) >= 3:
                actual_rets = [float(h.get("net_return_pct", 0.0)) for h in h_list]
                expected_ranks = list(range(len(h_list), 0, -1))
                try:
                    df_ic = pd.DataFrame({"rank": expected_ranks, "ret": actual_rets})
                    corr = df_ic["rank"].corr(df_ic["ret"], method="spearman")
                    if not math.isnan(corr):
                        ic_values.append(corr)
                except Exception:
                    logger.debug("compute_fundamental_law_active_management: swallowed Exception", exc_info=True)

    # Baseline Bayesian Prior for Vietnam Quant Factor Model
    base_ic = 0.048
    if tsmom_filter:
        base_ic += 0.015  # Trend-following momentum filter bonus
    if forensic_filter:
        base_ic += 0.012  # Anti-fraud Piotroski/Beneish filter bonus
    if survival_filter:
        base_ic += 0.010  # Survival & quality firewall bonus
    if not is_factor_portfolio and trades:
        win_rate = len([t for t in trades if t.get("is_win")]) / max(1, len(trades))
        base_ic = 0.03 + (win_rate - 0.50) * 0.15

    if ic_values:
        empirical_ic = float(np.mean(ic_values))
        ic_mean = 0.60 * empirical_ic + 0.40 * base_ic
        ic_std = float(np.std(ic_values, ddof=1)) if len(ic_values) > 1 else None
    else:
        ic_mean = base_ic
        ic_std = None

    ic_mean = round(float(np.clip(ic_mean, -0.05, 0.25)), 4)
    # The information ratio is IC divided by its own dispersion. With fewer
    # than two IC observations there is no dispersion to divide by; a
    # substituted 0.08 turned a single reading into a confident-looking ratio,
    # and the max(0.001, ...) clamp let a near-zero one produce a huge value.
    ic_ir = (
        round(ic_mean / ic_std, 2)
        if (ic_std is not None and ic_std >= 0.001) else None
    )
    is_overfitted = bool(ic_mean > 0.15)
    ic_warning = "⚠️ Cảnh báo: IC > 0.15 là cực kỳ hiếm trong thực tế, cần kiểm tra nguy cơ Overfitting hoặc Look-ahead bias." if is_overfitted else ""

    # 3. Breadth (BR - Number of independent bets per year)
    if is_factor_portfolio:
        rho_bar = 0.35
        k_val = max(1, int(top_k))
        n_eff = k_val / (1.0 + (k_val - 1.0) * rho_bar)
        br_annual = n_eff * freq_per_year
    else:
        num_trades = len(trades) if trades else 12
        br_annual = max(2.0, float(num_trades) / years)
        n_eff = br_annual

    br_annual = round(br_annual, 2)
    sqrt_br = round(math.sqrt(max(0.1, br_annual)), 3)

    # 4. Transfer Coefficient (TC) & Theoretical IRs
    # Grinold (1989) unconstrained: IR_uncon = IC * sqrt(BR)
    theoretical_ir_unconstrained = round(ic_mean * math.sqrt(max(0.1, br_annual)), 2)

    # Clarke, de Silva & Thorley (2002) Transfer Coefficient: TC = Corr(w_constrained, w_unconstrained)
    # Long-only constraint in Vietnam (no shorting), max allocation cap, and friction
    if theoretical_ir_unconstrained > 0.01 and realized_ir > 0:
        derived_tc = realized_ir / theoretical_ir_unconstrained
        tc_value = float(np.clip(derived_tc, 0.15, 0.95))
    else:
        # Structural baseline for Long-Only Vietnam Equity (penalty for no short-selling ~45%, friction ~10%)
        tc_value = 0.45

    tc_value = round(tc_value, 3)
    theoretical_ir_constrained = round(tc_value * theoretical_ir_unconstrained, 2)
    execution_efficiency_pct = round(min(100.0, max(0.0, tc_value * 100.0)), 1)

    # 5. Qualitative Evaluations & Badges
    if realized_ir >= 1.0:
        ir_eval = "Đẳng Cấp Thế Giới (World-Class)"
        ir_badge = "badge-success"
        ir_desc = "Hiệu quả tạo Alpha vượt trội, thuộc nhóm tinh hoa toàn cầu (Top 1% Hedge Funds)."
    elif realized_ir >= 0.75:
        ir_eval = "Xuất Sắc (Superior Alpha)"
        ir_badge = "badge-success"
        ir_desc = "Tạo Alpha ổn định trên mỗi đơn vị rủi ro chủ động, vượt chuẩn quỹ đầu ngành."
    elif realized_ir >= 0.50:
        ir_eval = "Tốt (Top-Quartile Fund)"
        ir_badge = "badge-blue"
        ir_desc = "Hiệu suất vượt trội nhóm 25% quỹ chủ động tốt nhất thị trường."
    elif realized_ir >= 0.30:
        ir_eval = "Khá / Chuẩn Quỹ (Industry Standard)"
        ir_badge = "badge-yellow"
        ir_desc = "Đạt mức chuẩn trung bình của các quỹ đầu tư chủ động chuyên nghiệp."
    elif realized_ir >= 0.0:
        ir_eval = "Dưới Trung Bình (Sub-Par)"
        ir_badge = "badge-neutral"
        ir_desc = "Alpha tạo ra chưa đủ bù đắp chi phí vận hành và rủi ro chủ động."
    else:
        ir_eval = "Tệ / Bào Mòn Vốn (Negative Alpha)"
        ir_badge = "badge-danger"
        ir_desc = "Lợi nhuận kém hơn Benchmark, rủi ro Tracking Error gây tổn thất vốn."

    if is_overfitted:
        ic_eval = "Rất Cao (Nghi ngờ Overfit / Look-ahead)"
        ic_badge = "badge-danger"
    elif ic_mean >= 0.08:
        ic_eval = "Xuất Sắc (Kỹ năng dự báo vượt trội)"
        ic_badge = "badge-success"
    elif ic_mean >= 0.05:
        ic_eval = "Tốt / Khá (Tín hiệu phân loại mạnh)"
        ic_badge = "badge-blue"
    elif ic_mean >= 0.02:
        ic_eval = "Chuẩn Quỹ Quant (Cần bù đắp bằng Breadth)"
        ic_badge = "badge-yellow"
    elif ic_mean >= 0.0:
        ic_eval = "Yếu / Nhiều Nhiễu"
        ic_badge = "badge-neutral"
    else:
        ic_eval = "Rất Tệ (Dự báo ngược xu hướng)"
        ic_badge = "badge-danger"

    if br_annual >= 30.0:
        br_eval = "Rất Cao (Khai thác luật số lớn tối đa)"
        br_badge = "badge-success"
    elif br_annual >= 15.0:
        br_eval = "Tốt / Đa Dạng Hóa Hiệu Quả"
        br_badge = "badge-blue"
    elif br_annual >= 8.0:
        br_eval = "Trung Bình (Độ rộng vừa phải)"
        br_badge = "badge-yellow"
    else:
        br_eval = "Thấp (Rủi ro tập trung cao)"
        br_badge = "badge-neutral"

    if tc_value >= 0.70:
        tc_eval = "Tối Ưu / Ít Ràng Buộc (Gần Long/Short)"
        tc_badge = "badge-success"
    elif tc_value >= 0.40:
        tc_eval = "Chuẩn Quỹ Long-Only (Chịu giới hạn cấm bán khống)"
        tc_badge = "badge-blue"
    else:
        tc_eval = "Bị Gò Bó Nặng (Ma sát & ràng buộc triệt tiêu Alpha)"
        tc_badge = "badge-danger"

    recommendations = []
    if is_overfitted:
        recommendations.append("Cần kiểm tra kỹ hiện tượng rò rỉ dữ liệu tương lai (Look-ahead bias) do IC > 0.15 quá cao.")
    if tc_value < 0.40:
        recommendations.append("Hệ số chuyển đổi TC thấp: Hãy giảm tần suất đảo danh mục để tiết kiệm phí giao dịch và nới lỏng giới hạn tỷ trọng vị thế.")
    if br_annual < 12.0:
        recommendations.append(f"Độ rộng BR = {br_annual:.1f} cược/năm còn thấp: Hãy mở rộng rổ cổ phiếu (tăng Top K từ 10 lên 15-20) hoặc đa dạng hóa qua nhiều ngành độc lập để tăng căn bậc hai sqrt(BR).")
    if ic_mean < 0.04:
        recommendations.append("Hệ số thông tin IC còn yếu: Kết hợp thêm bộ lọc Xu Hướng Động Lượng (TSMOM) hoặc Tường Lửa Pháp Y (Forensic Firewall) để cải thiện độ chính xác phân loại cổ phiếu.")
    if not recommendations:
        recommendations.append("Chiến lược cân bằng hoàn hảo giữa kỹ năng dự báo (IC), độ rộng cược độc lập (BR) và khả năng chuyển hóa danh mục (TC) theo đúng định luật Grinold & Kahn.")

    return {
        "formula_display": "IR ≈ TC × IC × √BR",
        "realized_information_ratio": round(realized_ir, 2),
        "active_return_cagr_pct": round(active_return_cagr, 2),
        "tracking_error_pct": round(ann_tracking_error, 2),
        "information_coefficient": ic_mean,
        "ic_std": round(ic_std, 4) if ic_std is not None else None,
        "ic_ir": ic_ir,
        "is_overfitted": is_overfitted,
        "ic_warning": ic_warning,
        "breadth_annual_bets": br_annual,
        "effective_independent_assets": round(n_eff, 2),
        "sqrt_breadth": sqrt_br,
        "pairwise_correlation_assumed": 0.35 if is_factor_portfolio else 0.0,
        "transfer_coefficient": tc_value,
        "execution_efficiency_pct": execution_efficiency_pct,
        "theoretical_ir_unconstrained": theoretical_ir_unconstrained,
        "theoretical_ir_constrained": theoretical_ir_constrained,
        "evaluations": {
            "ir": {"grade": ir_eval, "badge": ir_badge, "description": ir_desc},
            "ic": {"grade": ic_eval, "badge": ic_badge},
            "br": {"grade": br_eval, "badge": br_badge},
            "tc": {"grade": tc_eval, "badge": tc_badge}
        },
        "constraints_drag": {
            "short_sale_prohibition_drag_pct": 45.0,
            "transaction_friction_drag_pct": 5.0,
            "liquidity_delay_drag_pct": 5.0
        },
        "recommendations": recommendations,
        "primary_recommendation": recommendations[0] if recommendations else ""
    }

# ------------------------------------------------------------------------------
# STEP 1 & 2: UNIFIED EXECUTION ENGINE (FACTOR PORTFOLIO & BAR-BY-BAR)
# ------------------------------------------------------------------------------

def run_bar_by_bar_backtest(
    symbol: str = "ALL",
    strategy_type: str = "quant_q1",
    time_horizon_years: int = 3,
    initial_capital: float = 100_000_000.0,
    risk_per_trade_pct: float = 1.5,
    max_capital_fraction: float = 0.25,
    top_k: int = 10,
    rebalance_cadence: str = "quarterly",
    survival_filter: bool = False,
    tsmom_filter: bool = False,
    fill_mode: str = "strict",
    forensic_filter: bool = False,
    atr_period: int = 14,
    atr_stop_multiplier: float = 2.5,
    take_profit_atr_multiplier: Optional[float] = 4.0,
    fast_period: int = 20,
    slow_period: int = 50,
    commission_pct: float = DEFAULT_COMMISSION_PCT,
    tax_pct: float = DEFAULT_TAX_PCT,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
    t_plus_settlement: int = 2,
    raw_df: Optional[pd.DataFrame] = None,
    # Valuation, Hybrid, and Margin of Safety parameters
    margin_of_safety_pct: float = 15.0,
    composite_mode: str = "blended",
    omnibus_metric: str = "smape",
    use_dynamic_beta_mos: bool = False,
    filter_rkv_value_trap: bool = True,
    backtest_mode: Optional[str] = None, # "factor", "valuation", "hybrid"
    screening_strategy: Optional[str] = None,
    valuation_model_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Unified Institutional Backtest Execution:
    - If backtest_mode == "valuation" or strategy_type is a Valuation Model:
      Executes 22-Model Intrinsic Valuation Engine with MoS triggers, risk firewalls.
    - If backtest_mode == "hybrid" or strategy_type is a Hybrid Strategy:
      Executes 2-Stage Hybrid Funnel (Stage 1 Screener + Stage 2 Valuation MoS).
    - If backtest_mode == "factor" or strategy_type is a Factor / Guru strategy:
      Executes full portfolio screening with point-in-time pricing and quarterly rebalancing.
    - If symbol is a single ticker (e.g. FPT, HPG) and strategy_type is a technical rule:
      Executes daily two-moment bar-by-bar engine with ATR Trailing Stop, T+2.5 rules, and fixed risk sizing.
    """
    symbol = str(symbol).strip().upper()
    initial_capital = max(10_000_000.0, float(initial_capital))

    # Determine execution mode
    resolved_mode = backtest_mode
    if resolved_mode in ["hybrid_funnel", "hybrid"]:
        resolved_mode = "hybrid"
    elif resolved_mode in ["valuation_only", "valuation"]:
        resolved_mode = "valuation"
    elif resolved_mode in ["factor_only", "factor"]:
        resolved_mode = "factor"
    elif not resolved_mode:
        if (
            strategy_type.startswith("hybrid_") or
            (screening_strategy and valuation_model_id and screening_strategy != "custom")
        ):
            resolved_mode = "hybrid"
        elif (
            strategy_type in VALUATION_STRATEGY_CATALOG or
            strategy_type.startswith("val_") or
            strategy_type in VALUATION_MODELS_CATALOG or
            valuation_model_id
        ):
            resolved_mode = "valuation"
        else:
            resolved_mode = "factor"

    is_valuation_or_hybrid = resolved_mode in ["valuation", "hybrid"]

    # --------------------------------------------------------------------------
    # CASE V: QUANTITATIVE VALUATION & HYBRID FUNNEL EXECUTION
    # --------------------------------------------------------------------------
    if is_valuation_or_hybrid:
        if resolved_mode == "hybrid":
            val_mode = BacktestMode.HYBRID_FUNNEL
            hybrid_map = {
                "hybrid_garp_composite": ("peter_lynch_garp", "composite_fair_value"),
                "hybrid_buffett_moat": ("value_buffett", "buffett_owners_earnings"),
                "hybrid_klarman_rkv": ("deep_value_klarman", "pb_rhodes_kropf"),
                "hybrid_magic_formula": ("guru_magic_formula_greenblatt", "acquirers_multiple_ev_ebit"),
                "hybrid_qval_dcf": ("gray_quantitative_value_qval", "dcf_2stage_mckinsey"),
                "hybrid_novy_marx_epv": ("novy_marx_quality_value", "greenwald_epv"),
            }
            default_s, default_v = hybrid_map.get(strategy_type, ("peter_lynch_garp", "composite_fair_value"))
            s_strat = screening_strategy or default_s
            v_model = valuation_model_id or default_v
        else:
            val_mode = BacktestMode.VALUATION_ONLY
            v_model = valuation_model_id or strategy_type.replace("val_", "")
            s_strat = "custom"

        actual_exchange = symbol if symbol in ["HOSE", "HNX", "UPCOM"] else "ALL"
        custom_syms = None
        if symbol == "VN30":
            from services.stock_service import VN30_SYMBOLS
            custom_syms = list(VN30_SYMBOLS)
        elif symbol in ["VN70", "VNMID"]:
            from services.stock_service import VN70_SYMBOLS
            custom_syms = list(VN70_SYMBOLS)
        elif symbol == "VN100":
            from services.stock_service import VN100_SYMBOLS
            custom_syms = list(VN100_SYMBOLS)
        elif symbol not in INDEX_UNIVERSES:
            custom_syms = [symbol]

        # These were literal 2026s: correct only during 2026, and silently a
        # year short from 1 January 2027 onward.
        end_yr = default_backtest_end_year()
        start_yr = default_backtest_start_year(time_horizon_years)

        fv_service = FairValueBacktestService()
        fv_res = fv_service.run_backtest(
            mode=val_mode,
            screening_strategy=s_strat,
            valuation_model_id=v_model,
            composite_mode=composite_mode,
            omnibus_metric=omnibus_metric,
            margin_of_safety_pct=margin_of_safety_pct,
            use_dynamic_beta_mos=use_dynamic_beta_mos,
            filter_z_score_safe=survival_filter,
            filter_rkv_value_trap=filter_rkv_value_trap,
            start_year=start_yr,
            end_year=end_yr,
            rebalance_cadence=rebalance_cadence,
            top_k=top_k,
            initial_capital=initial_capital,
            exchange=actual_exchange,
            custom_symbols=custom_syms,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            fill_mode=fill_mode,
            forensic_filter=forensic_filter,
        )

        m_raw = fv_res.metrics
        nav_curve_raw = fv_res.equity_curve
        rebalance_hist = None

        trades = []
        for t in fv_res.trades:
            entry_p = float(t.get("entry_price", 0.0))
            exit_p = float(t.get("exit_price", 0.0))
            ret_pct = float(t.get("return_pct", 0.0))
            allocated_capital = initial_capital / max(1, top_k)
            # A zero entry price floored to 1 VND buys an absurd share count
            # and prices the whole position off it. No price, no share count.
            shares = int(allocated_capital / entry_p) if entry_p > 0 else 0
            if shares > 0:
                shares = max(DEFAULT_LOT_SIZE, (shares // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE)
            pnl_vnd = round(shares * (exit_p - entry_p), 0) if (entry_p > 0 and exit_p > 0) else round(allocated_capital * ret_pct / 100.0, 0)

            trades.append({
                "symbol": t.get("symbol", ""),
                "name": t.get("symbol", ""),
                "entry_date": t.get("entry_quarter") or t.get("entry_date", ""),
                "entry_price": round(entry_p, 2),
                "exit_date": t.get("exit_quarter") or t.get("exit_date", ""),
                "exit_price": round(exit_p, 2),
                "shares": shares,
                "holding_days": int(t.get("holding_days", 90)),
                "reason": t.get("exit_reason", "Valuation Exit"),
                "pnl_vnd": pnl_vnd,
                "pnl_pct": round(ret_pct, 2),
                "is_win": bool(ret_pct > 0 or pnl_vnd > 0)
            })

        equity_curve = []
        for item in nav_curve_raw:
            nav_val = item.get("strategy_equity") or item.get("nav", initial_capital)
            bm_nav_val = item.get("benchmark_equity") or item.get("benchmark_nav", initial_capital)
            equity_curve.append({
                "date": item.get("date") or item.get("quarter", ""),
                "nav": round(nav_val, 2),
                "benchmark_nav": round(bm_nav_val, 2),
                "drawdown_pct": item.get("drawdown_pct", 0.0),
                "close_price": round(nav_val / 1e6, 4)
            })

        strat_meta = VALUATION_STRATEGY_CATALOG.get(strategy_type, {})
        strat_title = strat_meta.get("name", f"Định Giá: {v_model}")

        fl_analysis = compute_fundamental_law_active_management(
            equity_curve=equity_curve,
            rebalance_cadence=rebalance_cadence,
            top_k=top_k,
            time_horizon_years=time_horizon_years,
            trades=trades,
            is_factor_portfolio=True,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter,
            rebalance_history=rebalance_hist
        )

        cagr = m_raw.get("cagr_pct", 0.0)
        vni_cagr = m_raw.get("benchmark_cagr_pct", m_raw.get("vni_cagr_pct", 0.0))
        max_dd = m_raw.get("max_drawdown_pct", 0.0)
        calmar = safe_ratio(cagr, abs(max_dd), MIN_MEANINGFUL_PCT)

        winning_trades = [t for t in trades if t["is_win"]]
        losing_trades = [t for t in trades if not t["is_win"]]
        gross_gains = sum(t["pnl_vnd"] for t in winning_trades)
        gross_losses = abs(sum(t["pnl_vnd"] for t in losing_trades))
        # No losing trade leaves the profit factor undefined, not 99.0 - a
        # sentinel that sorts and averages like a real, spectacular result.
        profit_factor = safe_ratio(gross_gains, gross_losses)
        avg_win = (gross_gains / len(winning_trades)) if winning_trades else 0.0
        avg_loss = (gross_losses / len(losing_trades)) if losing_trades else 0.0
        # avg_loss is in VND; clamping it to 1.0 turned a near-flat loss
        # into a payoff ratio in the millions.
        payoff_ratio = safe_ratio(avg_win, avg_loss)
        expectancy_vnd = round((sum(t["pnl_vnd"] for t in trades) / max(1, len(trades))), 0) if trades else 0.0

        dds = [e.get("drawdown_pct", 0.0) / 100.0 for e in equity_curve]
        squared_dds = [d**2 for d in dds]
        ulcer_index = round(math.sqrt(np.mean(squared_dds)) * 100.0, 2) if squared_dds else 0.0

        return {
            "status": "success",
            "symbol": symbol,
            "strategy_type": strategy_type,
            "strategy_name": strat_title,
            "is_factor_portfolio": True,
            "is_valuation_strategy": True,
            "parameters": {
                "time_horizon_years": time_horizon_years,
                "rebalance_cadence": rebalance_cadence,
                "top_k": top_k,
                "initial_capital": initial_capital,
                "exchange": actual_exchange,
                "margin_of_safety_pct": margin_of_safety_pct,
                "composite_mode": composite_mode,
                "omnibus_metric": omnibus_metric,
                "survival_filter": survival_filter,
                "tsmom_filter": tsmom_filter,
                "forensic_filter": forensic_filter,
                "commission_pct": commission_pct,
                "tax_pct": tax_pct,
                "slippage_pct": slippage_pct
            },
            "metrics": {
                "initial_capital": initial_capital,
                "final_nav": round(equity_curve[-1]["nav"] if equity_curve else initial_capital, 0),
                "total_return_pct": m_raw.get("total_return_pct", 0.0),
                "cagr_pct": cagr,
                "benchmark_return_pct": m_raw.get("benchmark_total_return_pct", m_raw.get("vni_total_return_pct", 0.0)),
                "benchmark_cagr_pct": vni_cagr,
                "alpha_cagr_pct": round(cagr - vni_cagr, 2),
                "max_drawdown_pct": abs(max_dd),
                "annualized_volatility_pct": m_raw.get("annualized_volatility_pct", 15.0),
                "sharpe_ratio": m_raw.get("sharpe_ratio", 0.0),
                "sortino_ratio": m_raw.get("sortino_ratio", 0.0),
                "calmar_ratio": calmar,
                "ulcer_index": ulcer_index,
                "profit_factor": profit_factor,
                "win_rate_pct": m_raw.get("win_rate_pct", round(len(winning_trades) / max(1, len(trades)) * 100.0, 2)),
                "total_trades": len(trades),
                "winning_trades_count": len(winning_trades),
                "losing_trades_count": len(losing_trades),
                # Carried up from the underlying fair-value run: whether these
                # numbers rest on filings or on price-derived arithmetic.
                "fundamentals": (fv_res.diagnostics or {}).get("fundamentals", {}),
                "avg_win_vnd": round(avg_win, 0),
                "avg_loss_vnd": round(avg_loss, 0),
                "payoff_ratio": payoff_ratio,
                "expectancy_per_trade_vnd": expectancy_vnd,
                "avg_holding_days": float(m_raw.get("avg_holding_days", 90.0)),
                "total_friction_vnd": float(m_raw.get("total_friction_vnd", 0.0)),
                "fundamental_law": fl_analysis
            },
            "fundamental_law": fl_analysis,
            "equity_curve": equity_curve,
            "trades": trades,
            "signals": [],
            "rebalance_history": rebalance_hist
        }

    is_factor_strategy = (
        strategy_type in STRATEGY_DEFINITIONS or
        strategy_type.startswith("guru_") or
        strategy_type.startswith("quant_") or
        strategy_type.startswith("hello_") or
        strategy_type in [
            "value_buffett", "buffetts_alpha", "novy_marx_quality_value", "gray_quantitative_value_qval",
            "deep_value_klarman", "ps_focus_fisher", "contrarian_dreman", "growth_philip_fisher",
            "peter_lynch_garp", "defensive_graham", "universal_survival_sector_moat", "tsmom_moskowitz", "vnindex"
        ]
    )
    
    is_universe_symbol = symbol in INDEX_UNIVERSES
    
    # --------------------------------------------------------------------------
    # CASE A: FACTOR PORTFOLIO & GURU STRATEGY EXECUTION
    # --------------------------------------------------------------------------
    if is_factor_strategy or is_universe_symbol:
        actual_strategy = strategy_type if is_factor_strategy else "quant_q1"
        
        from services.stock_service import get_quant_screener, VN30_SYMBOLS
        quant_universe = None
        if symbol == "VN30":
            screener_data = get_quant_screener(sector="ALL", quintile="ALL", exchange="HOSE", limit=500)
            quant_universe = [s for s in screener_data.get("results", []) if s.get("symbol") in VN30_SYMBOLS]
            actual_exchange = "HOSE"
        elif symbol in ["VN70", "VNMID"]:
            screener_data = get_quant_screener(sector="ALL", quintile="ALL", exchange="HOSE", limit=500)
            quant_universe = [s for s in screener_data.get("results", []) if s.get("symbol") not in VN30_SYMBOLS]
            actual_exchange = "HOSE"
        elif symbol in ["HOSE", "HNX", "UPCOM"]:
            actual_exchange = symbol
        else:
            actual_exchange = "ALL"
        
        screener_res = run_screener_backtest(
            strategy_id=actual_strategy,
            time_horizon_years=time_horizon_years,
            rebalance_cadence=rebalance_cadence,
            top_k=top_k,
            initial_capital=initial_capital,
            exchange=actual_exchange,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            fill_mode=fill_mode,
            forensic_filter=forensic_filter,
            quant_universe=quant_universe
        )
        
        m_raw = screener_res.get("metrics", {})
        nav_curve_raw = screener_res.get("nav_curve", [])
        vni_curve_raw = screener_res.get("vni_curve", [])
        rebalance_hist = screener_res.get("rebalance_history", [])
        
        # Build individual trade logs from rebalance history
        trades = []
        trade_id = 1
        total_commission_paid = 0.0
        total_tax_paid = 0.0
        total_slippage_paid = 0.0
        
        for q_idx, q_item in enumerate(rebalance_hist):
            q_date = q_item.get("quarter", f"Q{q_idx+1}")
            holdings = q_item.get("holdings", [])
            for h in holdings:
                sym = h.get("symbol", "")
                if not sym or sym == "CASH":
                    continue
                start_p = float(h.get("start_price") or 50.0)
                close_p = float(h.get("close_price") or start_p)
                pnl_pct = float(h.get("net_return_pct") or 0.0)
                weight_pct = float(h.get("weight_pct") or (100.0 / max(1, len(holdings))))
                
                allocated_capital = (initial_capital * (weight_pct / 100.0))
                pnl_vnd = allocated_capital * (pnl_pct / 100.0)
                entry_vnd = start_p * 1000.0
                shares = int(allocated_capital / entry_vnd) if entry_vnd > 0 else 0
                shares = (shares // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
                
                comm = allocated_capital * (commission_pct / 100.0) * 2.0
                tax = allocated_capital * (tax_pct / 100.0)
                slip = allocated_capital * (slippage_pct / 100.0)
                
                total_commission_paid += comm
                total_tax_paid += tax
                total_slippage_paid += slip
                
                trades.append({
                    "symbol": sym,
                    "name": h.get("name", sym),
                    "entry_date": q_date,
                    "entry_price": round(start_p, 2),
                    "exit_date": q_date,
                    "exit_price": round(close_p, 2),
                    "shares": max(DEFAULT_LOT_SIZE, shares),
                    "holding_days": 65, # ~1 Quarter
                    "reason": "Quarterly Factor Rotation" if h.get("meets_criteria") else "Basket Filling",
                    "pnl_vnd": round(pnl_vnd, 0),
                    "pnl_pct": round(pnl_pct, 2),
                    "is_win": pnl_vnd > 0
                })
                trade_id += 1

        # Format equity curve for High-DPI canvas
        equity_curve = []
        for idx, item in enumerate(nav_curve_raw):
            vni_nav_val = vni_curve_raw[idx].get("nav", initial_capital) if idx < len(vni_curve_raw) else initial_capital
            equity_curve.append({
                "date": item.get("date") or item.get("quarter", f"Kỳ {idx}"),
                "nav": item.get("nav", initial_capital),
                "benchmark_nav": vni_nav_val,
                "drawdown_pct": item.get("drawdown_pct", 0.0),
                "close_price": item.get("nav", initial_capital) / 1e6
            })
            
        winning_trades = [t for t in trades if t["is_win"]]
        losing_trades = [t for t in trades if not t["is_win"]]
        gross_gains = sum(t["pnl_vnd"] for t in winning_trades)
        gross_losses = abs(sum(t["pnl_vnd"] for t in losing_trades))
        # No losing trade leaves the profit factor undefined, not 99.0 - a
        # sentinel that sorts and averages like a real, spectacular result.
        profit_factor = safe_ratio(gross_gains, gross_losses)
        
        avg_win = (gross_gains / len(winning_trades)) if winning_trades else 0.0
        avg_loss = (gross_losses / len(losing_trades)) if losing_trades else 0.0
        # avg_loss is in VND; clamping it to 1.0 turned a near-flat loss
        # into a payoff ratio in the millions.
        payoff_ratio = safe_ratio(avg_win, avg_loss)
        
        expectancy_vnd = round((sum(t["pnl_vnd"] for t in trades) / max(1, len(trades))), 0) if trades else 0.0
        
        # Ulcer Index
        dds = [e.get("drawdown_pct", 0.0) / 100.0 for e in equity_curve]
        squared_dds = [d**2 for d in dds]
        ulcer_index = round(math.sqrt(np.mean(squared_dds)) * 100.0, 2) if squared_dds else 0.0

        cagr = m_raw.get("cagr", 0.0)
        vni_cagr = m_raw.get("vni_cagr", 0.0)
        max_dd = m_raw.get("max_drawdown_pct", 0.0)
        calmar = safe_ratio(cagr, abs(max_dd), MIN_MEANINGFUL_PCT)

        strat_title = STRATEGY_DEFINITIONS.get(actual_strategy, {}).get("name", actual_strategy)
        
        fl_analysis = compute_fundamental_law_active_management(
            equity_curve=equity_curve,
            rebalance_cadence=rebalance_cadence,
            top_k=top_k,
            time_horizon_years=time_horizon_years,
            trades=trades,
            is_factor_portfolio=True,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter,
            rebalance_history=rebalance_hist
        )

        return {
            "status": "success",
            "symbol": symbol,
            "strategy_type": actual_strategy,
            "strategy_name": strat_title,
            "is_factor_portfolio": True,
            "parameters": {
                "time_horizon_years": time_horizon_years,
                "rebalance_cadence": rebalance_cadence,
                "top_k": top_k,
                "initial_capital": initial_capital,
                "exchange": actual_exchange,
                "survival_filter": survival_filter,
                "tsmom_filter": tsmom_filter,
                "forensic_filter": forensic_filter,
                "commission_pct": commission_pct,
                "tax_pct": tax_pct,
                "slippage_pct": slippage_pct
            },
            "metrics": {
                "initial_capital": initial_capital,
                "final_nav": round(equity_curve[-1]["nav"] if equity_curve else initial_capital, 0),
                "total_return_pct": m_raw.get("total_return_pct", 0.0),
                "cagr_pct": cagr,
                "benchmark_return_pct": m_raw.get("vni_total_return_pct", 0.0),
                "benchmark_cagr_pct": vni_cagr,
                "alpha_cagr_pct": m_raw.get("alpha_cagr", 0.0),
                "max_drawdown_pct": abs(max_dd),
                "annualized_volatility_pct": m_raw.get("annualized_volatility_pct", 15.0),
                "sharpe_ratio": m_raw.get("sharpe_ratio", 0.0),
                "sortino_ratio": m_raw.get("sortino_ratio", 0.0),
                "calmar_ratio": calmar,
                "ulcer_index": ulcer_index,
                "profit_factor": profit_factor,
                "win_rate_pct": round((len(winning_trades) / max(1, len(trades))) * 100.0, 1),
                "total_trades": len(trades),
                "winning_trades_count": len(winning_trades),
                "losing_trades_count": len(losing_trades),
                "avg_win_vnd": round(avg_win, 0),
                "avg_loss_vnd": round(avg_loss, 0),
                "payoff_ratio": payoff_ratio,
                "expectancy_per_trade_vnd": expectancy_vnd,
                "avg_holding_days": 65.0,
                "total_friction_vnd": round(total_commission_paid + total_tax_paid + total_slippage_paid, 0),
                "fundamental_law": fl_analysis
            },
            "fundamental_law": fl_analysis,
            "equity_curve": equity_curve,
            "trades": trades,
            "signals": []
        }

    # --------------------------------------------------------------------------
    # CASE B: SINGLE STOCK DAILY BAR-BY-BAR WITH DYNAMIC ATR TRAILING STOPS
    # --------------------------------------------------------------------------
    if raw_df is None or raw_df.empty:
        hist = get_stock_history(symbol, interval="1D", timeframe="ALL")
        candles = hist.get("candles", [])
        if not candles or len(candles) < 30:
            return {"status": "error", "message": f"Dữ liệu nến ngày không đủ cho mã {symbol}"}
        df = pd.DataFrame(candles)
    else:
        df = raw_df.copy()
        
    df['open'] = pd.to_numeric(df['open'], errors='coerce')
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna().reset_index(drop=True)
    
    if time_horizon_years == 1:
        df = df.iloc[-250:].reset_index(drop=True)
    elif time_horizon_years == 2:
        df = df.iloc[-500:].reset_index(drop=True)
    elif time_horizon_years == 3:
        df = df.iloc[-750:].reset_index(drop=True)
    elif time_horizon_years == 5:
        df = df.iloc[-1250:].reset_index(drop=True)
    elif time_horizon_years == 10:
        df = df.iloc[-2500:].reset_index(drop=True)
        
    n_bars = len(df)
    if n_bars < 30:
        return {"status": "error", "message": f"Số lượng nến ({n_bars}) quá ngắn để kiểm định"}

    master_info = ALL_SYMBOLS_MAP.get(symbol, {})
    exchange = master_info.get("exchange", "HOSE").upper()
    limit_pct = EXCHANGE_LIMITS.get(exchange, 0.07)
    
    # Pre-calculate Indicators
    df['atr'] = compute_atr(df, atr_period)
    df['fast_ma'] = df['close'].rolling(fast_period, min_periods=1).mean()
    df['slow_ma'] = df['close'].rolling(slow_period, min_periods=1).mean()
    df['donchian_high'] = df['high'].shift(1).rolling(fast_period, min_periods=1).max()
    df['donchian_low'] = df['low'].shift(1).rolling(fast_period, min_periods=1).min()
    
    st_series, st_dir = compute_supertrend(df, period=atr_period, multiplier=atr_stop_multiplier)
    df['supertrend'] = st_series
    df['supertrend_dir'] = st_dir

    cash = initial_capital
    position_shares = 0
    position_entry_price = 0.0
    position_entry_bar = -1
    position_entry_date = ""
    current_stop_price = 0.0
    current_tp_price = 0.0
    peak_price_since_entry = 0.0
    
    trades = []
    equity_curve = []
    daily_signals = []
    
    pending_entry = False
    pending_exit = False
    pending_exit_reason = ""
    
    total_commission_paid = 0.0
    total_tax_paid = 0.0
    total_slippage_paid = 0.0
    
    for i in range(1, n_bars):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        c_time = str(row.get('time', ''))[:10]
        c_open = float(row['open'])
        c_high = float(row['high'])
        c_low = float(row['low'])
        c_close = float(row['close'])
        c_atr = float(row['atr']) if pd.notna(row['atr']) else (c_close * 0.02)
        
        c_ref = float(prev_row['close'])
        floor_p = round(c_ref * (1.0 - limit_pct), 2)
        ceil_p = round(c_ref * (1.0 + limit_pct), 2)
        
        # MOMENT 1: CANDLE OPEN (t)
        if pending_exit and position_shares > 0:
            bars_held = i - position_entry_bar
            if bars_held >= t_plus_settlement:
                exec_price = c_open * (1.0 - slippage_pct / 100.0)
                exec_price = max(floor_p, min(ceil_p, exec_price))
                
                gross_proceeds = position_shares * exec_price * 1000.0
                comm = gross_proceeds * (commission_pct / 100.0)
                tax = gross_proceeds * (tax_pct / 100.0)
                slip = (c_open - exec_price) * position_shares * 1000.0
                net_proceeds = gross_proceeds - comm - tax
                
                cash += net_proceeds
                total_commission_paid += comm
                total_tax_paid += tax
                total_slippage_paid += slip
                
                pnl_vnd = net_proceeds - (position_shares * position_entry_price * 1000.0)
                pnl_pct = ((exec_price - position_entry_price) / position_entry_price) * 100.0
                
                trades.append({
                    "symbol": symbol,
                    "entry_date": position_entry_date,
                    "entry_price": round(position_entry_price, 2),
                    "exit_date": c_time,
                    "exit_price": round(exec_price, 2),
                    "shares": position_shares,
                    "holding_days": bars_held,
                    "reason": pending_exit_reason,
                    "pnl_vnd": round(pnl_vnd, 0),
                    "pnl_pct": round(pnl_pct, 2),
                    "is_win": pnl_vnd > 0
                })
                
                position_shares = 0
                position_entry_price = 0.0
                pending_exit = False
                pending_exit_reason = ""
                
        if pending_entry and position_shares == 0:
            exec_price = c_open * (1.0 + slippage_pct / 100.0)
            exec_price = max(floor_p, min(ceil_p, exec_price))
            
            initial_stop = max(floor_p, exec_price - (atr_stop_multiplier * c_atr))
            risk_per_share = max(exec_price * 0.015, exec_price - initial_stop)
            
            current_equity = cash
            dollar_risk = current_equity * (risk_per_trade_pct / 100.0)
            max_capital = current_equity * max_capital_fraction
            
            shares_by_risk = math.floor(dollar_risk / (risk_per_share * 1000.0))
            shares_by_capital = math.floor(max_capital / (exec_price * 1000.0 * (1.0 + commission_pct / 100.0)))
            target_shares = min(shares_by_risk, shares_by_capital)
            target_shares = (target_shares // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
            
            if target_shares >= DEFAULT_LOT_SIZE:
                gross_cost = target_shares * exec_price * 1000.0
                comm = gross_cost * (commission_pct / 100.0)
                slip = (exec_price - c_open) * target_shares * 1000.0
                total_cost = gross_cost + comm
                
                if cash >= total_cost:
                    cash -= total_cost
                    position_shares = target_shares
                    position_entry_price = exec_price
                    position_entry_bar = i
                    position_entry_date = c_time
                    current_stop_price = initial_stop
                    peak_price_since_entry = exec_price
                    
                    if take_profit_atr_multiplier:
                        current_tp_price = exec_price + (take_profit_atr_multiplier * c_atr)
                    else:
                        current_tp_price = 0.0
                        
                    total_commission_paid += comm
                    total_slippage_paid += slip
                    
            pending_entry = False

        # MOMENT 2: INTRA-CANDLE & CLOSE (t)
        if position_shares > 0:
            bars_held = i - position_entry_bar
            peak_price_since_entry = max(peak_price_since_entry, c_high)
            
            trail_stop = peak_price_since_entry - (atr_stop_multiplier * c_atr)
            current_stop_price = max(current_stop_price, trail_stop)
            
            if c_low <= current_stop_price and bars_held >= t_plus_settlement:
                exit_p = max(floor_p, min(c_open, current_stop_price)) * (1.0 - slippage_pct / 100.0)
                gross_proceeds = position_shares * exit_p * 1000.0
                comm = gross_proceeds * (commission_pct / 100.0)
                tax = gross_proceeds * (tax_pct / 100.0)
                net_proceeds = gross_proceeds - comm - tax
                
                cash += net_proceeds
                total_commission_paid += comm
                total_tax_paid += tax
                
                pnl_vnd = net_proceeds - (position_shares * position_entry_price * 1000.0)
                pnl_pct = ((exit_p - position_entry_price) / position_entry_price) * 100.0
                
                trades.append({
                    "symbol": symbol,
                    "entry_date": position_entry_date,
                    "entry_price": round(position_entry_price, 2),
                    "exit_date": c_time,
                    "exit_price": round(exit_p, 2),
                    "shares": position_shares,
                    "holding_days": bars_held,
                    "reason": "ATR Stop-Loss (Intra-day)",
                    "pnl_vnd": round(pnl_vnd, 0),
                    "pnl_pct": round(pnl_pct, 2),
                    "is_win": pnl_vnd > 0
                })
                position_shares = 0
                position_entry_price = 0.0
                
            elif current_tp_price > 0 and c_high >= current_tp_price and bars_held >= t_plus_settlement:
                exit_p = current_tp_price * (1.0 - slippage_pct / 100.0)
                gross_proceeds = position_shares * exit_p * 1000.0
                comm = gross_proceeds * (commission_pct / 100.0)
                tax = gross_proceeds * (tax_pct / 100.0)
                net_proceeds = gross_proceeds - comm - tax
                
                cash += net_proceeds
                total_commission_paid += comm
                total_tax_paid += tax
                
                pnl_vnd = net_proceeds - (position_shares * position_entry_price * 1000.0)
                pnl_pct = ((exit_p - position_entry_price) / position_entry_price) * 100.0
                
                trades.append({
                    "symbol": symbol,
                    "entry_date": position_entry_date,
                    "entry_price": round(position_entry_price, 2),
                    "exit_date": c_time,
                    "exit_price": round(exit_p, 2),
                    "shares": position_shares,
                    "holding_days": bars_held,
                    "reason": "Take-Profit Target (Intra-day)",
                    "pnl_vnd": round(pnl_vnd, 0),
                    "pnl_pct": round(pnl_pct, 2),
                    "is_win": pnl_vnd > 0
                })
                position_shares = 0
                position_entry_price = 0.0
                
        entry_sig = False
        exit_sig = False
        
        if strategy_type == "trend_following_atr":
            entry_sig = (row['fast_ma'] > row['slow_ma']) and (prev_row['fast_ma'] <= prev_row['slow_ma']) and (c_close > row['fast_ma'])
            exit_sig = (row['fast_ma'] < row['slow_ma']) or (c_close < row['slow_ma'])
        elif strategy_type == "breakout_donchian":
            entry_sig = c_close > row['donchian_high']
            exit_sig = c_close < row['donchian_low']
        elif strategy_type == "supertrend_atr":
            entry_sig = (row['supertrend_dir'] == 1) and (prev_row['supertrend_dir'] == -1)
            exit_sig = (row['supertrend_dir'] == -1)
        elif strategy_type == "tsmom_daily":
            lookback_c = df['close'].iloc[max(0, i-60)]
            entry_sig = (c_close > lookback_c) and (c_close > row['fast_ma'])
            exit_sig = (c_close < lookback_c) or (c_close < row['slow_ma'])
        else:
            entry_sig = (row['fast_ma'] > row['slow_ma']) and (c_close > row['fast_ma'])
            exit_sig = (c_close < row['slow_ma'])
            
        if entry_sig and position_shares == 0:
            pending_entry = True
            daily_signals.append({"time": c_time, "type": "BUY", "price": c_close})
        elif exit_sig and position_shares > 0:
            pending_exit = True
            pending_exit_reason = "Signal Exit (Close)"
            daily_signals.append({"time": c_time, "type": "SELL", "price": c_close})
            
        mtm_pos_val = (position_shares * c_close * 1000.0) if position_shares > 0 else 0.0
        total_equity = cash + mtm_pos_val
        equity_curve.append({
            "date": c_time,
            "nav": round(total_equity, 0),
            "cash": round(cash, 0),
            "position_val": round(mtm_pos_val, 0),
            "close_price": c_close,
            "stop_price": round(current_stop_price, 2) if position_shares > 0 else 0.0,
            "in_position": position_shares > 0
        })

    if position_shares > 0:
        final_row = df.iloc[-1]
        final_close = float(final_row['close'])
        exec_price = final_close * (1.0 - slippage_pct / 100.0)
        gross_proceeds = position_shares * exec_price * 1000.0
        comm = gross_proceeds * (commission_pct / 100.0)
        tax = gross_proceeds * (tax_pct / 100.0)
        net_proceeds = gross_proceeds - comm - tax
        cash += net_proceeds
        
        pnl_vnd = net_proceeds - (position_shares * position_entry_price * 1000.0)
        pnl_pct = ((exec_price - position_entry_price) / position_entry_price) * 100.0
        trades.append({
            "symbol": symbol,
            "entry_date": position_entry_date,
            "entry_price": round(position_entry_price, 2),
            "exit_date": str(final_row.get('time', ''))[:10],
            "exit_price": round(exec_price, 2),
            "shares": position_shares,
            "holding_days": len(df) - position_entry_bar,
            "reason": "Final Bar Liquidation",
            "pnl_vnd": round(pnl_vnd, 0),
            "pnl_pct": round(pnl_pct, 2),
            "is_win": pnl_vnd > 0
        })
        position_shares = 0

    final_nav = cash
    total_return_pct = round(((final_nav - initial_capital) / initial_capital) * 100.0, 2)
    
    days_elapsed = max(1, len(equity_curve))
    years_elapsed = max(days_elapsed / 250.0, 0.1)
    cagr_pct = round((math.pow(max(0.01, final_nav / initial_capital), 1.0 / years_elapsed) - 1.0) * 100.0, 2) if final_nav > 0 else -100.0

    bh_start = float(df['close'].iloc[0])
    bh_end = float(df['close'].iloc[-1])
    bh_return_pct = round(((bh_end - bh_start) / bh_start) * 100.0, 2)
    bh_cagr = round((math.pow(max(0.01, bh_end / bh_start), 1.0 / years_elapsed) - 1.0) * 100.0, 2)

    nav_series = [e['nav'] for e in equity_curve]
    daily_returns = [ (nav_series[j] - nav_series[j-1]) / nav_series[j-1] for j in range(1, len(nav_series)) ] if len(nav_series) > 1 else [0.0]
    
    peaks = []
    drawdowns = []
    current_peak = initial_capital
    for nav_v in nav_series:
        current_peak = max(current_peak, nav_v)
        dd = (nav_v - current_peak) / current_peak
        drawdowns.append(dd)
        
    max_dd_pct = round(abs(min(drawdowns)) * 100.0, 2) if drawdowns else 0.0
    
    # Clamped denominators (max(0.01, vol), max(1.0, drawdown)) inflate the
    # ratio for any low-volatility run rather than reporting that there is no
    # meaningful denominator; a substituted 0.01 volatility invents one. Both
    # are withheld - the same fix applied in the other two backtest services.
    _ratio = safe_ratio

    daily_vol = float(np.std(daily_returns, ddof=1)) if len(daily_returns) > 1 else None
    ann_vol_pct = round(daily_vol * math.sqrt(250) * 100.0, 2) if daily_vol is not None else None

    excess_cagr = (cagr_pct / 100.0) - DEFAULT_ANNUAL_RF
    sharpe_ratio = _ratio(
        excess_cagr,
        None if ann_vol_pct is None else ann_vol_pct / 100.0,
        MIN_MEANINGFUL_FRACTION,
    )

    downside_returns = [r for r in daily_returns if r < 0]
    downside_vol = (
        float(np.std(downside_returns, ddof=1)) * math.sqrt(250)
        if len(downside_returns) > 1 else None
    )
    sortino_ratio = _ratio(excess_cagr, downside_vol, MIN_MEANINGFUL_FRACTION)

    calmar_ratio = _ratio(cagr_pct, max_dd_pct, MIN_MEANINGFUL_PCT)
    
    squared_dds = [dd**2 for dd in drawdowns]
    ulcer_index = round(math.sqrt(np.mean(squared_dds)) * 100.0, 2) if squared_dds else 0.0

    total_trades = len(trades)
    winning_trades = [t for t in trades if t['is_win']]
    losing_trades = [t for t in trades if not t['is_win']]
    
    win_rate_pct = round((len(winning_trades) / max(1, total_trades)) * 100.0, 1)
    
    gross_gains = sum(t['pnl_vnd'] for t in winning_trades)
    gross_losses = abs(sum(t['pnl_vnd'] for t in losing_trades))
    profit_factor = safe_ratio(gross_gains, gross_losses)
    
    avg_win = (gross_gains / len(winning_trades)) if winning_trades else 0.0
    avg_loss = (gross_losses / len(losing_trades)) if losing_trades else 0.0
    payoff_ratio = safe_ratio(avg_win, avg_loss)
    
    expectancy_vnd = round((sum(t['pnl_vnd'] for t in trades) / max(1, total_trades)), 0)
    avg_holding_days = round(sum(t['holding_days'] for t in trades) / max(1, total_trades), 1)

    fl_analysis = compute_fundamental_law_active_management(
        equity_curve=equity_curve,
        rebalance_cadence="daily",
        top_k=1,
        time_horizon_years=time_horizon_years,
        trades=trades,
        is_factor_portfolio=False,
        survival_filter=survival_filter,
        tsmom_filter=tsmom_filter,
        forensic_filter=forensic_filter
    )

    return {
        "status": "success",
        "symbol": symbol,
        "strategy_type": strategy_type,
        "is_factor_portfolio": False,
        "parameters": {
            "time_horizon_years": time_horizon_years,
            "initial_capital": initial_capital,
            "risk_per_trade_pct": risk_per_trade_pct,
            "atr_stop_multiplier": atr_stop_multiplier,
            "take_profit_atr_multiplier": take_profit_atr_multiplier,
            "fast_period": fast_period,
            "slow_period": slow_period,
            "t_plus_settlement": t_plus_settlement,
            "commission_pct": commission_pct,
            "tax_pct": tax_pct,
            "slippage_pct": slippage_pct
        },
        "metrics": {
            "initial_capital": initial_capital,
            "final_nav": round(final_nav, 0),
            "total_return_pct": total_return_pct,
            "cagr_pct": cagr_pct,
            "benchmark_return_pct": bh_return_pct,
            "benchmark_cagr_pct": bh_cagr,
            "alpha_cagr_pct": round(cagr_pct - bh_cagr, 2),
            "max_drawdown_pct": max_dd_pct,
            "annualized_volatility_pct": ann_vol_pct,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "ulcer_index": ulcer_index,
            "profit_factor": profit_factor,
            "win_rate_pct": win_rate_pct,
            "total_trades": total_trades,
            "winning_trades_count": len(winning_trades),
            "losing_trades_count": len(losing_trades),
            "avg_win_vnd": round(avg_win, 0),
            "avg_loss_vnd": round(avg_loss, 0),
            "payoff_ratio": payoff_ratio,
            "expectancy_per_trade_vnd": expectancy_vnd,
            "avg_holding_days": avg_holding_days,
            "total_friction_vnd": round(total_commission_paid + total_tax_paid + total_slippage_paid, 0),
            "fundamental_law": fl_analysis
        },
        "fundamental_law": fl_analysis,
        "equity_curve": equity_curve,
        "trades": trades,
        "signals": daily_signals
    }

# ------------------------------------------------------------------------------
# STEP 4 & 5: 2D PARAMETER SENSITIVITY SCAN & PLATEAU VS CLIFF MATRIX
# ------------------------------------------------------------------------------

def run_parameter_sensitivity(
    symbol: str = "ALL",
    strategy_type: str = "quant_q1",
    param1_name: str = "top_k",
    param1_values: Optional[List[Any]] = None,
    param2_name: str = "cadence",
    param2_values: Optional[List[Any]] = None,
    time_horizon_years: int = 3,
    backtest_mode: Optional[str] = None,
    screening_strategy: Optional[str] = None,
    valuation_model_id: Optional[str] = None,
    composite_mode: str = "blended",
    omnibus_metric: str = "smape"
) -> Dict[str, Any]:
    """
    Executes 2D parameter grid scan to detect robust parameter plateaus vs overfitted cliffs.
    Works seamlessly for both Factor/Guru strategies (scanning Top K x Cadence),
    Valuation / Hybrid models (scanning MoS % x Top K),
    and Technical strategies (scanning Fast MA x ATR Stop Multiple).
    """
    resolved_mode = backtest_mode
    if not resolved_mode:
        if (
            strategy_type.startswith("hybrid_") or
            (screening_strategy and valuation_model_id and screening_strategy != "custom")
        ):
            resolved_mode = "hybrid"
        elif (
            strategy_type in VALUATION_STRATEGY_CATALOG or
            strategy_type.startswith("val_") or
            strategy_type in VALUATION_MODELS_CATALOG or
            valuation_model_id
        ):
            resolved_mode = "valuation"
        else:
            resolved_mode = "factor"

    is_val = resolved_mode in ["valuation", "hybrid"]
    is_factor = resolved_mode == "factor" and (
        strategy_type in STRATEGY_DEFINITIONS or
        strategy_type.startswith("guru_") or
        strategy_type.startswith("quant_") or
        symbol in INDEX_UNIVERSES
    )
    
    if is_val:
        param1_name = "margin_of_safety_pct"
        if param1_values is None:
            param1_values = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
        param2_name = "top_k"
        if param2_values is None:
            param2_values = [5, 10, 15, 20]
    elif is_factor:
        param1_name = "top_k"
        if param1_values is None:
            param1_values = [5, 10, 15, 20]
        param2_name = "cadence"
        if param2_values is None:
            param2_values = ["quarterly", "semi_annual", "annual"]
    else:
        param1_name = "fast_period"
        if param1_values is None:
            param1_values = [10, 15, 20, 25, 30, 40]
        param2_name = "atr_stop_multiplier"
        if param2_values is None:
            param2_values = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

    matrix_sharpe = []
    matrix_cagr = []
    matrix_max_dd = []
    flat_results = []
    
    for p1 in param1_values:
        row_sharpe = []
        row_cagr = []
        row_dd = []
        for p2 in param2_values:
            kwargs = {
                "symbol": symbol,
                "strategy_type": strategy_type,
                "time_horizon_years": time_horizon_years,
                "backtest_mode": resolved_mode,
                "screening_strategy": screening_strategy,
                "valuation_model_id": valuation_model_id,
                "composite_mode": composite_mode,
                "omnibus_metric": omnibus_metric
            }
            if is_val:
                kwargs["margin_of_safety_pct"] = float(p1)
                kwargs["top_k"] = int(p2)
            elif is_factor:
                kwargs["top_k"] = int(p1)
                kwargs["rebalance_cadence"] = str(p2)
            else:
                kwargs["fast_period"] = int(p1)
                kwargs["atr_stop_multiplier"] = float(p2)
                
            sim = run_bar_by_bar_backtest(**kwargs)
            m = sim.get("metrics", {})
            s = m.get("sharpe_ratio", 0.0)
            c = m.get("cagr_pct", 0.0)
            dd = m.get("max_drawdown_pct", 0.0)
            
            row_sharpe.append(s)
            row_cagr.append(c)
            row_dd.append(dd)
            
            flat_results.append({
                "param1": p1,
                "param2": p2,
                "sharpe": s,
                "cagr": c,
                "max_drawdown": dd
            })
            
        matrix_sharpe.append(row_sharpe)
        matrix_cagr.append(row_cagr)
        matrix_max_dd.append(row_dd)
        
    arr_sharpe = np.array(matrix_sharpe)
    overall_mean = float(np.mean(arr_sharpe))
    overall_std = float(np.std(arr_sharpe))
    best_item = max(flat_results, key=lambda x: x["sharpe"])
    is_cliff = (best_item["sharpe"] > (overall_mean + 1.8 * max(0.1, overall_std))) and (overall_mean < 0.5)
    
    return {
        "status": "success",
        "symbol": symbol,
        "strategy_type": strategy_type,
        "param1_name": param1_name,
        "param1_values": param1_values,
        "param2_name": param2_name,
        "param2_values": param2_values,
        "matrix_sharpe": matrix_sharpe,
        "matrix_cagr": matrix_cagr,
        "matrix_max_dd": matrix_max_dd,
        "best_centroid": best_item,
        "robustness": {
            "mean_sharpe": round(overall_mean, 2),
            "std_sharpe": round(overall_std, 2),
            "is_plateau": not is_cliff,
            "plateau_quality": "VÙNG BÌNH NGUYÊN ỔN ĐỊNH (ROBUST PLATEAU) 🟢" if not is_cliff else "CẢNH BÁO: BẪY QUÁ KHỚP ĐỈNH NHỌN (OVERFITTED CLIFF) ⚠️",
            "description": "Các tham số lân cận đều cho hiệu suất ổn định, ít phụ thuộc vào bước nhảy tham số." if not is_cliff else "Hiệu suất đột biến tại một điểm duy nhất trong khi các điểm lân cận sụt giảm mạnh."
        }
    }

# ------------------------------------------------------------------------------
# STEP 6: WALK-FORWARD ANALYSIS (WFA) ROLLING OPTIMIZATION
# ------------------------------------------------------------------------------

def run_walk_forward_analysis(
    symbol: str = "ALL",
    strategy_type: str = "quant_q1",
    train_window_bars: int = 350,
    test_window_bars: int = 100,
    initial_capital: float = 100_000_000.0
) -> Dict[str, Any]:
    """
    Executes Walk-Forward Analysis across rolling multi-period regimes and stitches OOS returns.
    """
    is_val = (
        strategy_type in VALUATION_STRATEGY_CATALOG or
        strategy_type.startswith("val_") or
        strategy_type.startswith("hybrid_") or
        strategy_type in VALUATION_MODELS_CATALOG
    )
    is_factor = (
        strategy_type in STRATEGY_DEFINITIONS or
        strategy_type.startswith("guru_") or
        strategy_type.startswith("quant_") or
        symbol in INDEX_UNIVERSES
    )
    
    splits = []
    stitched_trades = []
    stitched_equity_curve = []
    current_capital = initial_capital
    
    if is_val or is_factor:
        # For Factor & Valuation strategies: roll across quarterly timeline (2021 to 2026)
        all_q_codes = [q["code"] for q in QUARTERS_TIMELINE[-16:]] # 16 quarters (~4 years)
        train_q_len = 8 # 2 years train
        test_q_len = 4  # 1 year test
        step_q = 2      # 6 months roll
        
        split_id = 1
        start_idx = 0
        
        if is_val:
            param_candidates = [
                {"top_k": 5, "margin_of_safety_pct": 10.0, "rebalance_cadence": "quarterly"},
                {"top_k": 10, "margin_of_safety_pct": 15.0, "rebalance_cadence": "quarterly"},
                {"top_k": 10, "margin_of_safety_pct": 20.0, "rebalance_cadence": "quarterly"},
                {"top_k": 15, "margin_of_safety_pct": 15.0, "rebalance_cadence": "quarterly"}
            ]
        else:
            param_candidates = [
                {"top_k": 5, "rebalance_cadence": "quarterly"},
                {"top_k": 10, "rebalance_cadence": "quarterly"},
                {"top_k": 15, "rebalance_cadence": "quarterly"},
                {"top_k": 10, "rebalance_cadence": "semi_annual"}
            ]
        
        while (start_idx + train_q_len + test_q_len) <= len(all_q_codes):
            train_qs = all_q_codes[start_idx : start_idx + train_q_len]
            test_qs = all_q_codes[start_idx + train_q_len : start_idx + train_q_len + test_q_len]
            
            best_param = None
            best_is_sharpe = -999.0
            
            for cand in param_candidates:
                kwargs_is = {
                    "symbol": symbol,
                    "strategy_type": strategy_type,
                    "time_horizon_years": 2,
                    "initial_capital": current_capital,
                    "top_k": cand["top_k"],
                    "rebalance_cadence": cand.get("rebalance_cadence", "quarterly")
                }
                if "margin_of_safety_pct" in cand:
                    kwargs_is["margin_of_safety_pct"] = cand["margin_of_safety_pct"]
                    
                sim_is = run_bar_by_bar_backtest(**kwargs_is)
                # sharpe_ratio is now withheld (None) when there is no
                # meaningful volatility to divide by, and dict.get returns that
                # None rather than the default. A parameter set we could not
                # score does not win the selection.
                sh = sim_is.get("metrics", {}).get("sharpe_ratio")
                if sh is not None and sh > best_is_sharpe:
                    best_is_sharpe = sh
                    best_param = cand
                    
            kwargs_oos = {
                "symbol": symbol,
                "strategy_type": strategy_type,
                "time_horizon_years": 1,
                "initial_capital": current_capital,
                "top_k": best_param["top_k"],
                "rebalance_cadence": best_param.get("rebalance_cadence", "quarterly")
            }
            if "margin_of_safety_pct" in best_param:
                kwargs_oos["margin_of_safety_pct"] = best_param["margin_of_safety_pct"]
                
            sim_oos = run_bar_by_bar_backtest(**kwargs_oos)
            
            oos_m = sim_oos.get("metrics", {})
            oos_trades = sim_oos.get("trades", [])
            oos_curve = sim_oos.get("equity_curve", [])
            
            current_capital = oos_m.get("final_nav", current_capital)
            stitched_trades.extend(oos_trades)
            stitched_equity_curve.extend(oos_curve)
            
            splits.append({
                "split_id": split_id,
                "train_start_date": train_qs[0],
                "train_end_date": train_qs[-1],
                "test_start_date": test_qs[0],
                "test_end_date": test_qs[-1],
                "selected_parameters": best_param,
                "in_sample_sharpe": round(best_is_sharpe, 2),
                "out_of_sample_return_pct": oos_m.get("total_return_pct", 0.0),
                "out_of_sample_sharpe": oos_m.get("sharpe_ratio", 0.0),
                "out_of_sample_max_dd": oos_m.get("max_drawdown_pct", 0.0)
            })
            
            start_idx += step_q
            split_id += 1
    else:
        # Technical strategy on single stock
        hist = get_stock_history(symbol, interval="1D", timeframe="ALL")
        candles = hist.get("candles", [])
        if len(candles) < (train_window_bars + test_window_bars):
            return {"status": "error", "message": f"Dữ liệu lịch sử ({len(candles)} nến) không đủ cho cửa sổ Walk-Forward {train_window_bars}+{test_window_bars}"}
            
        df_all = pd.DataFrame(candles)
        n_bars = len(df_all)
        step_size = test_window_bars
        split_id = 1
        start_idx = 0
        
        param_candidates = [
            {"fast_period": 15, "slow_period": 40, "atr_stop_multiplier": 2.0},
            {"fast_period": 20, "slow_period": 50, "atr_stop_multiplier": 2.5},
            {"fast_period": 25, "slow_period": 60, "atr_stop_multiplier": 3.0},
            {"fast_period": 30, "slow_period": 80, "atr_stop_multiplier": 3.5}
        ]
        
        while (start_idx + train_window_bars + test_window_bars) <= n_bars:
            train_start = start_idx
            train_end = start_idx + train_window_bars
            test_start = train_end
            test_end = test_start + test_window_bars
            
            train_df = df_all.iloc[train_start:train_end].reset_index(drop=True)
            test_df = df_all.iloc[test_start:test_end].reset_index(drop=True)
            
            best_param = None
            best_is_sharpe = -999.0
            
            for cand in param_candidates:
                sim_is = run_bar_by_bar_backtest(
                    symbol=symbol,
                    strategy_type=strategy_type,
                    initial_capital=current_capital,
                    raw_df=train_df,
                    fast_period=cand["fast_period"],
                    slow_period=cand["slow_period"],
                    atr_stop_multiplier=cand["atr_stop_multiplier"]
                )
                # A parameter set whose Sharpe could not be measured (None)
                # does not win the selection.
                sh = sim_is.get("metrics", {}).get("sharpe_ratio")
                if sh is not None and sh > best_is_sharpe:
                    best_is_sharpe = sh
                    best_param = cand
                    
            sim_oos = run_bar_by_bar_backtest(
                symbol=symbol,
                strategy_type=strategy_type,
                initial_capital=current_capital,
                raw_df=test_df,
                fast_period=best_param["fast_period"],
                slow_period=best_param["slow_period"],
                atr_stop_multiplier=best_param["atr_stop_multiplier"]
            )
            
            oos_m = sim_oos.get("metrics", {})
            oos_trades = sim_oos.get("trades", [])
            oos_curve = sim_oos.get("equity_curve", [])
            
            current_capital = oos_m.get("final_nav", current_capital)
            stitched_trades.extend(oos_trades)
            stitched_equity_curve.extend(oos_curve)
            
            splits.append({
                "split_id": split_id,
                "train_start_date": str(train_df['time'].iloc[0])[:10],
                "train_end_date": str(train_df['time'].iloc[-1])[:10],
                "test_start_date": str(test_df['time'].iloc[0])[:10],
                "test_end_date": str(test_df['time'].iloc[-1])[:10],
                "selected_parameters": best_param,
                "in_sample_sharpe": round(best_is_sharpe, 2),
                "out_of_sample_return_pct": oos_m.get("total_return_pct", 0.0),
                "out_of_sample_sharpe": oos_m.get("sharpe_ratio", 0.0),
                "out_of_sample_max_dd": oos_m.get("max_drawdown_pct", 0.0)
            })
            
            start_idx += step_size
            split_id += 1

    wfa_final_nav = current_capital
    wfa_total_return = round(((wfa_final_nav - initial_capital) / initial_capital) * 100.0, 2)
    
    # No splits means nothing was measured; 1.0 for both would report a
    # perfect walk-forward efficiency for a run that never happened.
    avg_is_sharpe = float(np.mean([s["in_sample_sharpe"] for s in splits])) if splits else None
    avg_oos_sharpe = float(np.mean([s["out_of_sample_sharpe"] for s in splits])) if splits else None
    wfe_ratio = (
        None if avg_oos_sharpe is None
        else safe_ratio(avg_oos_sharpe, avg_is_sharpe, MIN_MEANINGFUL_FRACTION)
    )

    return {
        "status": "success",
        "symbol": symbol,
        "strategy_type": strategy_type,
        "splits_count": len(splits),
        "walk_forward_efficiency": wfe_ratio,
        "wfe_rating": "XUẤT SẮC (WFE >= 0.70) 🟢" if wfe_ratio >= 0.70 else "TRUNG BÌNH (0.50 <= WFE < 0.70) 🟡" if wfe_ratio >= 0.50 else "KÉM (WFE < 0.50 - NGUY CƠ OVERFITTING) 🔴",
        "wfa_metrics": {
            "initial_capital": initial_capital,
            "final_nav": round(wfa_final_nav, 0),
            "total_return_pct": wfa_total_return,
            "avg_in_sample_sharpe": round(avg_is_sharpe, 2),
            "avg_out_of_sample_sharpe": round(avg_oos_sharpe, 2),
            "total_oos_trades": len(stitched_trades)
        },
        "splits": splits,
        "stitched_trades": stitched_trades,
        "stitched_equity_curve": stitched_equity_curve
    }

# ------------------------------------------------------------------------------
# STEP 7: STATISTICAL STRESS TESTING (MONTE CARLO BOOTSTRAP & PERMUTATION)
# ------------------------------------------------------------------------------

# One basis point, the smallest denominator worth dividing by. Below it a
# ratio says more about floating-point noise than about the strategy.
MIN_MEANINGFUL_FRACTION = 0.0001   # as a fraction
MIN_MEANINGFUL_PCT = 0.01          # as a percentage


def safe_ratio(
    numerator: float,
    denominator: Optional[float],
    floor: float = MIN_MEANINGFUL_PCT,
    digits: int = 2,
) -> Optional[float]:
    """``numerator / denominator``, or None when the denominator is unusable.

    Clamping a denominator up to a floor (``max(1.0, drawdown)``) does not
    avoid the problem, it hides it: the ratio still gets reported, now
    understated for small denominators and fabricated for zero ones. None is
    the honest answer, and it does not average or sort like a real result.
    """
    if denominator is None:
        return None
    try:
        denominator = float(denominator)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(denominator) or abs(denominator) < floor:
        return None
    value = numerator / denominator
    return round(value, digits) if math.isfinite(value) else None


def _measure_trades_per_year(trades: List[Dict[str, Any]]) -> Optional[float]:
    """Trades per year, measured from the span the trades actually cover.

    Returns None when the trade dates cannot support the measurement (missing,
    unparseable, or all inside the same day), so the caller can skip
    annualising instead of substituting a cadence nobody observed.
    """
    stamps: List[datetime.date] = []
    for trade in trades:
        for key in ("entry_date", "exit_date"):
            raw = str(trade.get(key) or "").strip()
            if not raw:
                continue
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    stamps.append(datetime.datetime.strptime(raw[:10], fmt).date())
                    break
                except ValueError:
                    continue
    if len(stamps) < 2:
        return None
    span_days = (max(stamps) - min(stamps)).days
    if span_days <= 0:
        return None
    per_year = len(trades) * 365.25 / span_days
    return per_year if math.isfinite(per_year) and per_year > 0 else None


def run_monte_carlo_stress_test(
    trades: List[Dict[str, Any]],
    initial_capital: float = 100_000_000.0,
    iterations: int = 1000
) -> Dict[str, Any]:
    """
    Runs 1,000 Bootstrap Resamplings (95% CI) and 1,000 Permutations (Sequence Risk).
    """
    if not trades or len(trades) < 3:
        return {
            "status": "error",
            "message": "Cần tối thiểu 3 lệnh giao dịch để thực hiện mô phỏng Monte Carlo"
        }
        
    pnl_pcts = [t["pnl_pct"] for t in trades]
    n_trades = len(pnl_pcts)

    # Annualisation factor for a per-trade Sharpe: how many of these trades
    # occur in a year. It used to be written `n_trades / max(1, n_trades / 12)`,
    # which is exactly 12.0 for any n_trades >= 12 - a hardcoded "monthly"
    # assumption wearing the shape of a calculation. Measure it from the span
    # the trades actually cover, and when the dates do not support that,
    # decline to annualise rather than invent a cadence.
    trades_per_year = _measure_trades_per_year(trades)
    
    bootstrap_sharpes = []
    bootstrap_returns = []
    bootstrap_max_dds = []
    permutation_max_dds = []
    
    random.seed(42)
    
    for _ in range(iterations):
        # 1. BOOTSTRAP RESAMPLING (With Replacement)
        resampled_pnls = [random.choice(pnl_pcts) for _ in range(n_trades)]
        
        cap = initial_capital
        peak = initial_capital
        mdd = 0.0
        
        for r_pct in resampled_pnls:
            cap *= (1.0 + r_pct / 100.0)
            peak = max(peak, cap)
            dd = (cap - peak) / peak
            mdd = max(mdd, abs(dd))
            
        tot_ret = ((cap - initial_capital) / initial_capital) * 100.0
        # Same clamped-denominator defect as the headline ratios: dividing by
        # max(0.1, std) inflates the bootstrap Sharpe whenever a resample has
        # low dispersion, and substituting 1.0 invents it outright. A draw with
        # no measurable dispersion contributes no Sharpe rather than a large one.
        std_pnl = float(np.std(resampled_pnls, ddof=1)) if len(resampled_pnls) > 1 else None
        if std_pnl is not None and std_pnl >= 0.01:
            sh = np.mean(resampled_pnls) / std_pnl
            if trades_per_year is not None:
                sh *= math.sqrt(trades_per_year)
            bootstrap_sharpes.append(sh)
        bootstrap_returns.append(tot_ret)
        bootstrap_max_dds.append(mdd * 100.0)
        
        # 2. PERMUTATION TEST (Shuffle Sequence)
        shuffled = pnl_pcts.copy()
        random.shuffle(shuffled)
        
        p_cap = initial_capital
        p_peak = initial_capital
        p_mdd = 0.0
        for p_pct in shuffled:
            p_cap *= (1.0 + p_pct / 100.0)
            p_peak = max(p_peak, p_cap)
            p_dd = (p_cap - p_peak) / p_peak
            p_mdd = max(p_mdd, abs(p_dd))
        permutation_max_dds.append(p_mdd * 100.0)

    # Draws with no measurable dispersion contribute no Sharpe, so this can be
    # empty; an interval over nothing is None, not [0, 0].
    ci_sharpe = (
        [round(float(np.percentile(bootstrap_sharpes, 2.5)), 2),
         round(float(np.percentile(bootstrap_sharpes, 97.5)), 2)]
        if bootstrap_sharpes else None
    )
    ci_return = [round(float(np.percentile(bootstrap_returns, 2.5)), 2), round(float(np.percentile(bootstrap_returns, 97.5)), 2)]
    ci_max_dd = [round(float(np.percentile(bootstrap_max_dds, 2.5)), 2), round(float(np.percentile(bootstrap_max_dds, 97.5)), 2)]
    
    perm_worst_dd = round(float(np.percentile(permutation_max_dds, 99.0)), 2)
    perm_median_dd = round(float(np.median(permutation_max_dds)), 2)

    if bootstrap_sharpes:
        hist_sharpe, bin_edges = np.histogram(bootstrap_sharpes, bins=20)
        sharpe_distribution = [
            {"bin": round(float((bin_edges[k] + bin_edges[k+1]) / 2.0), 2), "count": int(hist_sharpe[k])}
            for k in range(len(hist_sharpe))
        ]
    else:
        sharpe_distribution = []

    return {
        "status": "success",
        "iterations": iterations,
        "total_trades_evaluated": n_trades,
        "confidence_intervals_95": {
            "sharpe_ratio": ci_sharpe,
            "total_return_pct": ci_return,
            "max_drawdown_pct": ci_max_dd
        },
        "sequence_risk_permutation": {
            "median_drawdown_pct": perm_median_dd,
            "worst_case_drawdown_99pct": perm_worst_dd,
            "description": f"Trong kịch bản đen đủi nhất về thứ tự chuỗi lệnh, Max Drawdown có thể lên tới {perm_worst_dd}%."
        },
        "sharpe_distribution": sharpe_distribution
    }
