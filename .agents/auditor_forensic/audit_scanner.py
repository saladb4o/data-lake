import os
import re
import sys
import json

def main():
    out_lines = []
    def log(msg=""):
        out_lines.append(msg)
        print(msg, flush=True)

    log("==================================================")
    log("FORENSIC INTEGRITY AUDIT SCANNER")
    log("==================================================")
    
    root_dir = os.path.abspath(".")
    log(f"Project root: {root_dir}")
    
    # 1. Gather all files
    all_files = []
    for root, dirs, files in os.walk(root_dir):
        if any(ignored in root for ignored in ['.git', '.agents', '__pycache__', 'node_modules', '.pytest_cache']):
            continue
        for f in files:
            all_files.append(os.path.join(root, f))
            
    log(f"Total workspace files scanned: {len(all_files)}")
    
    # Target files to audit
    targets = [
        "server.py",
        "services/valuation_engine.py",
        "services/stock_service.py",
        "services/sector_index_service.py",
        "services/fair_value_backtest_service.py",
        "static/js/app.js",
        "static/js/chart.js"
    ]
    
    # 2. Check for hardcoded test intercepts
    log("\n--- PHASE 1: HARDCODED SYMBOL INTERCEPTS ---")
    intercept_patterns = [
        re.compile(r'if\s+(?:symbol|ticker|code)\s*(?:==|\bin\b)\s*[\'\"\[]', re.IGNORECASE),
        re.compile(r'if\s+[\'\"].*?[\'\"]\s*in\s*(?:symbol|ticker|code)', re.IGNORECASE)
    ]
    
    for rel_path in targets:
        full_path = os.path.join(root_dir, rel_path)
        if not os.path.exists(full_path):
            log(f"MISSING FILE: {rel_path}")
            continue
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines, 1):
            for pat in intercept_patterns:
                if pat.search(line):
                    log(f"[{rel_path}:{idx}] INTERCEPT CANDIDATE: {line.strip()}")
                    
    # 3. Check for Facade implementations (empty functions, constant returns)
    log("\n--- PHASE 2: FACADE & DUMMY IMPLEMENTATION DETECTION ---")
    facade_pattern = re.compile(r'def\s+([a-zA-Z0-9_]+)\([^)]*\):\s*(?:pass|\.\.\.|return None|return True|return False|return 0|return 100|raise NotImplementedError)\s*$', re.MULTILINE)
    for rel_path in targets:
        full_path = os.path.join(root_dir, rel_path)
        if not os.path.exists(full_path) or not full_path.endswith('.py'):
            continue
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        matches = facade_pattern.findall(content)
        if matches:
            log(f"[{rel_path}] POTENTIAL FACADES FOUND: {matches}")
        else:
            log(f"[{rel_path}] No trivial facade functions detected.")
            
    # 4. Check for tautological assertions in tests/
    log("\n--- PHASE 3: TEST SUITE INTEGRITY & ASSERTION SANITY ---")
    test_files = [f for f in all_files if "tests" in f and f.endswith(".py")]
    tautology_patterns = [
        (re.compile(r'assert\s+True\b'), "assert True"),
        (re.compile(r'assert\s+1\s*==\s*1\b'), "assert 1 == 1"),
        (re.compile(r'assert\s+not\s+False\b'), "assert not False"),
        (re.compile(r'assert\s+len\([^)]+\)\s*>=\s*0\b'), "assert len >= 0 (always true)"),
        (re.compile(r'assert\s+isinstance\([^,]+,\s*(?:object|Any)\)'), "assert isinstance of object/Any"),
    ]
    
    flagged_assertions = []
    total_assertions = 0
    for tf in test_files:
        rel_tf = os.path.relpath(tf, root_dir)
        with open(tf, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines, 1):
            if "assert" in line:
                total_assertions += 1
                for pat, desc in tautology_patterns:
                    if pat.search(line):
                        flagged_assertions.append((rel_tf, idx, desc, line.strip()))
                        
    log(f"Total assertions analyzed in test suite: {total_assertions}")
    if flagged_assertions:
        log(f"FLAGGED TAUTOLOGICAL ASSERTIONS: {len(flagged_assertions)}")
        for fa in flagged_assertions:
            log(f"  {fa[0]}:{fa[1]} [{fa[2]}] -> {fa[3]}")
    else:
        log("No tautological assertions found in test suite.")
        
    log("\n==================================================")
    log("STATIC FORENSIC SCAN COMPLETE")
    log("==================================================")

    with open(os.path.join(root_dir, ".agents", "auditor_forensic", "audit_results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))

if __name__ == "__main__":
    main()
