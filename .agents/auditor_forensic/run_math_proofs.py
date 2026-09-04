import os
import sys
sys.path.insert(0, os.path.abspath("."))
import pytest

if __name__ == "__main__":
    ret = pytest.main([".agents/auditor_forensic/test_mathematical_proofs.py", "-v", "-o", "pythonpath=."])
    with open(".agents/auditor_forensic/math_proof_results.txt", "w") as f:
        f.write(f"Pytest return code: {ret}\n")
    print(f"Math proof pytest finished with exit code: {ret}")
    sys.exit(ret)
