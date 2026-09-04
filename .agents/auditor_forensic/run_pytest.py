import sys
import subprocess
import os

def run_tests():
    print("Running pytest on tests/...")
    cmd = [sys.executable, "-m", "pytest", "tests", "-v"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.abspath("."))
    
    out_path = os.path.join(".agents", "auditor_forensic", "pytest_results.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Return code: {res.returncode}\n\n")
        f.write("=== STDOUT ===\n")
        f.write(res.stdout)
        f.write("\n=== STDERR ===\n")
        f.write(res.stderr)
        
    print(f"Pytest completed with exit code: {res.returncode}")
    print("Sample stdout:")
    lines = res.stdout.splitlines()
    for l in lines[-20:]:
        print(l)

if __name__ == "__main__":
    run_tests()
