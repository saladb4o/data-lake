import math
import sys
import os
sys.path.insert(0, os.path.abspath("."))

import pytest
from services.valuation_engine import (
    ValuationModelsSuite,
    WACCEngine,
    RiskFirewallEngine,
    AdaptiveWeightingEngine,
    ScenarioEngine,
    DEFAULT_RF,
    DEFAULT_ERP,
)

def test_proof_model_1_blended_pe():
    # Model 1
    eps_ttm = 2500.0
    hist_eps = [2000.0, 2200.0, 2400.0]
    sector_pe = 12.0
    hist_pe = 10.0
    growth = 0.10
    current_price = 25000.0
    
    # Manual calculation:
    peg_pe = 10.0
    target_pe = 0.40 * 12.0 + 0.35 * 10.0 + 0.25 * 10.0 # 10.8
    weights = [0.35, 0.25, 0.20]
    norm_w = [w / sum(weights) for w in weights] # [0.4375, 0.3125, 0.25]
    eps_cyc = sum(w * e for w, e in zip(norm_w, hist_eps)) # 2162.5
    blended_eps = 0.60 * eps_ttm + 0.40 * eps_cyc # 2365.0
    expected_fv = target_pe * blended_eps # 25542.0
    
    actual_fv = ValuationModelsSuite.model_1_blended_pe(
        eps_ttm=eps_ttm,
        historical_eps=hist_eps,
        sector_pe=sector_pe,
        hist_pe=hist_pe,
        eps_growth_rate=growth,
        current_price=current_price
    )
    assert math.isclose(actual_fv, expected_fv, rel_tol=1e-4)

def test_proof_model_2_ps_margin():
    sps = 20000.0
    net_margin = 0.10
    sec_ps = 1.2
    sec_nm = 0.08
    
    expected_target_ps = sec_ps * ((net_margin / sec_nm) ** 0.65)
    expected_fv = expected_target_ps * sps
    
    actual_fv = ValuationModelsSuite.model_2_ps_margin_adjusted(
        sales_per_share=sps,
        net_margin=net_margin,
        sector_ps=sec_ps,
        sector_net_margin=sec_nm,
        current_price=20000.0
    )
    assert math.isclose(actual_fv, expected_fv, rel_tol=1e-4)

def test_proof_model_12_graham():
    eps = 2000.0
    bvps = 20000.0
    g = 10.0
    y = 5.0
    
    classic = math.sqrt(22.5 * eps * bvps) # 30000.0
    growth = eps * (8.5 + 1.5 * g) * (4.4 / y) # 2000 * 23.5 * 0.88 = 41360.0
    expected_fv = 0.5 * classic + 0.5 * growth # 35680.0
    
    actual_fv = ValuationModelsSuite.model_12_graham_growth(
        eps_ttm=eps,
        bvps=bvps,
        expected_growth_pct=g,
        benchmark_bond_yield=y,
        current_price=30000.0
    )
    assert math.isclose(actual_fv, expected_fv, rel_tol=1e-4)

def test_proof_model_22_utilities_ddm():
    d0 = 1000.0
    ke = 0.10
    ga = 0.08
    gn = 0.04
    h = 2.5
    
    numerator = (d0 * (1.0 + gn)) + (d0 * h * (ga - gn)) # 1040 + 100 = 1140
    denom = ke - gn # 0.06
    expected_fv = numerator / denom # 19000.0
    
    actual_fv = ValuationModelsSuite.model_22_utilities_3stage_ddm(
        dividend_per_share=d0,
        ke=ke,
        div_growth_initial=ga,
        g_terminal=gn,
        half_life_h=h,
        current_price=15000.0
    )
    assert math.isclose(actual_fv, expected_fv, rel_tol=1e-4)

def test_proof_wacc_5factor_and_damodaran():
    # Large Cap, ICR = 20000 / 3500 = 5.71 -> Rating A+ (Spread 0.0115)
    # Market Cap = 165,000B (> 25,000B -> SMB = 0.0)
    # Beta raw = 1.0 -> Beta adj = 0.67*1 + 0.33*1 = 1.0
    # Ke = 0.05 + 1.0*0.0815 + SMB(0) + HML(0) + UMD(0) + ILLIQ(0) + RMW(0) = 0.1315
    res = WACCEngine.calculate(
        market_cap=165000e9,
        interest_bearing_debt=50000e9,
        ebit=20000e9,
        interest_expense=3500e9,
        beta_raw=1.0,
        roe=15.0,
        pb=1.5,
        pb_sector_median=1.5,
        adtv=60e9,
        r12m=0.15,
        r1m=0.15,
        rf=0.05,
        erp=0.0815,
        tax_rate=0.20
    )
    assert res.synthetic_rating == "A+"
    assert res.credit_spread == 0.0115
    assert math.isclose(res.cost_of_equity, 0.1315, abs_tol=1e-4)
    # Kd pre tax = 0.05 + 0.0115 = 0.0615
    # Kd after tax = 0.0615 * 0.8 = 0.0492
    assert math.isclose(res.cost_of_debt_pre_tax, 0.0615, abs_tol=1e-4)
    assert math.isclose(res.cost_of_debt_after_tax, 0.0492, abs_tol=1e-4)
    # V = 165000 + 50000 = 215000
    # We = 165000 / 215000 = 0.7674
    # Wd = 50000 / 215000 = 0.2326
    # WACC = 0.7674 * 0.1315 + 0.2326 * 0.0492 = 0.1009 + 0.0114 = 0.1124
    assert math.isclose(res.wacc, 0.1124, abs_tol=1e-3)

def test_proof_altman_z_emerging():
    # Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
    wc, re, ebit, eq, ta, tl = 250.0, 200.0, 120.0, 500.0, 1000.0, 500.0
    x1 = 250.0 / 1000.0 # 0.25
    x2 = 200.0 / 1000.0 # 0.20
    x3 = 120.0 / 1000.0 # 0.12
    x4 = 500.0 / 500.0  # 1.00
    expected_z = 6.56*x1 + 3.26*x2 + 6.72*x3 + 1.05*x4 # 1.64 + 0.652 + 0.8064 + 1.05 = 4.1484
    
    z, zone = RiskFirewallEngine.calculate_altman_z_double_prime(wc, re, ebit, eq, ta, tl)
    assert math.isclose(z, expected_z, abs_tol=1e-4)
    assert zone == "safe"
