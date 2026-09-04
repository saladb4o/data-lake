import sys
import os
import traceback
sys.path.insert(0, os.path.abspath("."))

from .agents.auditor_forensic.test_mathematical_proofs import (
    test_proof_model_1_blended_pe,
    test_proof_model_2_ps_margin,
    test_proof_model_12_graham,
    test_proof_model_22_utilities_ddm,
    test_proof_wacc_5factor_and_damodaran,
    test_proof_altman_z_emerging,
)

def run_proofs():
    tests = [
        ("Model 1 (Blended P/E with CAPE)", test_proof_model_1_blended_pe),
        ("Model 2 (P/S Margin Adjusted)", test_proof_model_2_ps_margin),
        ("Model 12 (Graham Growth Formula)", test_proof_model_12_graham),
        ("Model 22 (Utilities 3-Stage DDM)", test_proof_model_22_utilities_ddm),
        ("WACC 5-Factor & Damodaran Spread", test_proof_wacc_5factor_and_damodaran),
        ("Altman Z'' Emerging Market Formula", test_proof_altman_z_emerging),
    ]
    
    passed = 0
    failed = 0
    lines = []
    lines.append("=== DIRECT MATHEMATICAL GROUND-TRUTH VERIFICATION ===")
    
    for name, fn in tests:
        try:
            fn()
            lines.append(f"[PASS] {name}: Exact mathematical match verified against manual ground-truth formula.")
            passed += 1
        except Exception as e:
            lines.append(f"[FAIL] {name}: {e}")
            lines.append(traceback.format_exc())
            failed += 1
            
    lines.append(f"\nResult: {passed} passed, {failed} failed out of {len(tests)} proofs.")
    output = "\n".join(lines)
    print(output)
    
    with open(os.path.join(".agents", "auditor_forensic", "math_proof_results.txt"), "w", encoding="utf-8") as f:
        f.write(output)

if __name__ == "__main__":
    run_proofs()
