"""
Independent Forensic Verification & Stress-Testing Script for Milestone 1: Working Capital Engine
"""
import sys
import os
import ast
import math
import random
from typing import Dict, List, Any

# Ensure project root is in sys.path
sys.path.insert(0, r"c:\Users\Admin\Documents\Vibecoding vnstock")

from services.working_capital_engine import (
    WorkingCapitalEngine,
    WorkingCapitalMetrics,
    WorkingCapitalSchedulePeriod,
    WorkingCapitalForecastResult,
    SECTOR_WC_PRIORS,
    safe_div,
    clamp,
    sanitize_float,
    resolve_sector_prior,
)

def run_ast_forensic_checks(filepath: str) -> Dict[str, Any]:
    with open(filepath, "r", encoding="utf-8") as f:
        code_str = f.read()
    
    tree = ast.parse(code_str, filename=filepath)
    
    num_classes = 0
    num_functions = 0
    num_bin_ops = 0
    num_if_branches = 0
    hardcoded_symbol_checks = []
    suspicious_constant_returns = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            num_classes += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            num_functions += 1
            # Check if function body is just a constant return or pass
            if len(node.body) == 1:
                stmt = node.body[0]
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant):
                    suspicious_constant_returns.append((node.name, stmt.value.value))
                elif isinstance(stmt, ast.Pass):
                    suspicious_constant_returns.append((node.name, "pass"))
        elif isinstance(node, ast.BinOp):
            num_bin_ops += 1
        elif isinstance(node, ast.If):
            num_if_branches += 1
            # Check if comparing against specific symbol names like "HPG", "VNM" etc. in engine
            for sub in ast.walk(node.test):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    if sub.value in ["HPG", "VNM", "MWG", "FPT", "MSN", "GAS", "VCB", "TCB"]:
                        hardcoded_symbol_checks.append(sub.value)

    return {
        "num_classes": num_classes,
        "num_functions": num_functions,
        "num_bin_ops": num_bin_ops,
        "num_if_branches": num_if_branches,
        "hardcoded_symbol_checks": hardcoded_symbol_checks,
        "suspicious_constant_returns": suspicious_constant_returns,
        "lines_of_code": len(code_str.splitlines()),
    }

def run_dynamic_stress_fuzzing(num_trials: int = 50000) -> Dict[str, Any]:
    sectors = list(SECTOR_WC_PRIORS.keys()) + ["UNKNOWN_SEC", "", None, 12345]
    failures = []
    
    for i in range(num_trials):
        rev = random.choice([0.0, -100.0, 1e-6, 1e12, random.uniform(-1000, 100000), "10,000", "N/A", None, float("nan"), float("inf")])
        cogs = random.choice([0.0, -50.0, 1e-6, 1e12, random.uniform(-1000, 80000), "7,000", "-", None, float("nan"), float("inf")])
        ar = random.choice([0.0, -500.0, 1e-6, random.uniform(-100, 20000), "1,500", "null", None])
        inv = random.choice([0.0, -500.0, 1e-6, random.uniform(-100, 20000), "2,000", "--", None])
        ap = random.choice([0.0, -500.0, 1e-6, random.uniform(-100, 20000), "1,000", "nan", None])
        oca = random.choice([0.0, -100.0, random.uniform(-50, 5000), None])
        ocl = random.choice([0.0, -100.0, random.uniform(-50, 5000), None])
        sec = random.choice(sectors)

        try:
            res = WorkingCapitalEngine.calculate_historical_days(
                rev=rev, cogs=cogs, ar=ar, inv=inv, ap=ap, other_ca=oca, other_cl=ocl, sector=sec
            )
            # Verify no NaN or Inf in outputs
            for k, v in res.items():
                if isinstance(v, (int, float)):
                    if math.isnan(v) or math.isinf(v):
                        failures.append(f"Trial {i} produced NaN/Inf in {k} for inputs: rev={rev}, cogs={cogs}, ar={ar}, inv={inv}, ap={ap}")
                        break
            
            # Verify Days Clamping [0, 1095]
            if not res["is_financial_sector"]:
                if not (0.0 <= res["dso"] <= 1095.0):
                    failures.append(f"Trial {i} DSO out of bounds: {res['dso']}")
                if not (0.0 <= res["dio"] <= 1095.0):
                    failures.append(f"Trial {i} DIO out of bounds: {res['dio']}")
                if not (0.0 <= res["dpo"] <= 1095.0):
                    failures.append(f"Trial {i} DPO out of bounds: {res['dpo']}")
            else:
                if res["dso"] != 0.0 or res["dio"] != 0.0 or res["dpo"] != 0.0 or res["net_working_capital"] != 0.0:
                    failures.append(f"Trial {i} Financial sector non-zero metrics: {res}")

        except Exception as e:
            failures.append(f"Trial {i} Crashed with Exception: {type(e).__name__}: {e}")

        if len(failures) >= 10:
            break

    return {
        "trials_run": num_trials,
        "failures_count": len(failures),
        "sample_failures": failures[:5],
    }

def run_invariant_stress_checks(num_scenarios: int = 10000) -> Dict[str, Any]:
    invariant_failures = []
    
    for i in range(num_scenarios):
        revs = [max(100.0, random.uniform(1000, 1000000)) for _ in range(5)]
        cogss = [r * random.uniform(0.4, 0.9) for r in revs]
        base_dso = random.uniform(10, 120)
        base_dio = random.uniform(10, 180)
        base_dpo = random.uniform(10, 90)
        base_ar = (base_dso * revs[0]) / 365.0
        base_inv = (base_dio * cogss[0]) / 365.0
        base_ap = (base_dpo * cogss[0]) / 365.0
        base_oca = random.uniform(100, 5000)
        base_ocl = random.uniform(100, 5000)
        
        base_metrics = {
            "dso": base_dso, "dio": base_dio, "dpo": base_dpo,
            "ar": base_ar, "inv": base_inv, "ap": base_ap,
            "other_ca": base_oca, "other_cl": base_ocl,
            "net_working_capital": (base_ar + base_inv + base_oca) - (base_ap + base_ocl),
            "revenue": revs[0], "cogs": cogss[0],
        }

        speed = random.choice([0.0, 0.1, 0.25, 0.5, 1.0])
        sec = random.choice(["VNMAT", "VNCONS", "VNIT", "VNREAL", "VNCOND", "DEFAULT"])

        sched = WorkingCapitalEngine.project_working_capital_schedule(
            base_metrics=base_metrics,
            revenue_series=revs,
            cogs_series=cogss,
            sector=sec,
            mean_revert_speed=speed,
        )

        # Check invariant for each period:
        # Delta NWC == Delta AR + Delta Inv + Delta OCA - Delta AP - Delta OCL
        # Gross CFO == Gross Profit - Delta Trade NWC
        prior_p = base_metrics
        for t, p in enumerate(sched):
            # Invariant 1: Delta NWC component additivity
            expected_sum_deltas = (p["delta_ar"] + p["delta_inv"] + p["delta_oca"]) - (p["delta_ap"] + p["delta_ocl"])
            if not math.isclose(p["delta_nwc"], expected_sum_deltas, abs_tol=1e-4):
                invariant_failures.append(f"Scenario {i} Period {t}: Delta NWC {p['delta_nwc']} != {expected_sum_deltas}")
                break

            # Invariant 2: CCC definition
            expected_ccc = p["dso"] + p["dio"] - p["dpo"]
            if not math.isclose(p["ccc"], expected_ccc, abs_tol=1e-4):
                invariant_failures.append(f"Scenario {i} Period {t}: CCC {p['ccc']} != {expected_ccc}")
                break

            # Invariant 3: Direct Method Cash Flows
            # Cash collected = Rev - Delta AR
            if not math.isclose(p["cash_from_customers"], p["revenue"] - p["delta_ar"], abs_tol=1e-4):
                invariant_failures.append(f"Scenario {i} Period {t}: Cash receipts mismatch")
                break
            # Cash paid suppliers = COGS + Delta Inv - Delta AP
            if not math.isclose(p["cash_to_suppliers"], p["cogs"] + p["delta_inv"] - p["delta_ap"], abs_tol=1e-4):
                invariant_failures.append(f"Scenario {i} Period {t}: Cash payments mismatch")
                break

            # Invariant 4: Gross CFO == Gross Profit - Delta Trade NWC
            gross_profit = p["revenue"] - p["cogs"]
            delta_trade_nwc = p["delta_ar"] + p["delta_inv"] - p["delta_ap"]
            gross_cfo = p["cash_from_customers"] - p["cash_to_suppliers"]
            if not math.isclose(gross_cfo, gross_profit - delta_trade_nwc, abs_tol=1e-4):
                invariant_failures.append(f"Scenario {i} Period {t}: Gross CFO reconciliation violated")
                break

            prior_p = p

        if len(invariant_failures) >= 10:
            break

    return {
        "scenarios_tested": num_scenarios,
        "invariant_violations": len(invariant_failures),
        "sample_failures": invariant_failures[:5],
    }

if __name__ == "__main__":
    print("=================================================================")
    print("FORENSIC AUDIT: AST & STATIC CODE ANALYSIS")
    print("=================================================================")
    engine_ast = run_ast_forensic_checks(r"c:\Users\Admin\Documents\Vibecoding vnstock\services\working_capital_engine.py")
    test_ast = run_ast_forensic_checks(r"c:\Users\Admin\Documents\Vibecoding vnstock\tests\test_working_capital_engine.py")
    print("Engine AST:", engine_ast)
    print("Test AST:", test_ast)

    print("\n=================================================================")
    print("FORENSIC AUDIT: ADVERSARIAL FUZZING (50,000 SCENARIOS)")
    print("=================================================================")
    fuzz_res = run_dynamic_stress_fuzzing(50000)
    print("Fuzzing Results:", fuzz_res)

    print("\n=================================================================")
    print("FORENSIC AUDIT: MATHEMATICAL INVARIANT TESTING (10,000 SCENARIOS)")
    print("=================================================================")
    inv_res = run_invariant_stress_checks(10000)
    print("Invariant Results:", inv_res)

    print("\n=================================================================")
    print("ALL FORENSIC VERIFICATIONS EXECUTED SUCCESSFULLY.")
    print("=================================================================")
