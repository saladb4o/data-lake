import os
import sys
sys.path.insert(0, os.path.abspath("."))
import io
import openpyxl
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

print("Starting API Adversarial Audit...")

# 1. Test 3-way forecast endpoint for multiple symbols
symbols = ["HPG", "FPT", "VCB", "MWG", "VIC", "NVL", "GAS", "TCB", "SSI"]
for sym in symbols:
    resp = client.get(f"/api/valuation/3-way-forecast/{sym}")
    assert resp.status_code == 200, f"Failed for {sym}: {resp.text}"
    data = resp.json()
    assert data["status"] == "success"
    fc = data["data"]
    assert fc["symbol"] == sym
    assert len(fc["forecast_years"]) == 5
    assert fc["all_years_balanced"] is True
    assert len(fc["income_statement"]["revenue"]) == 5
    assert len(fc["balance_sheet"]["total_assets"]) == 5
    assert len(fc["cash_flow_statement"]["net_cfo"]) == 5
    assert len(fc["working_capital_schedule"]) == 5
    assert len(fc["debt_schedule"]) == 5
    print(f"[API PASS] 3-Way Forecast JSON valid for {sym} (all_years_balanced={fc['all_years_balanced']})")

# 2. Test query parameter variations
resp = client.get("/api/valuation/3-way-forecast/HPG?start_year=2027&tax_rate=0.25")
assert resp.status_code == 200
data = resp.json()["data"]
assert data["start_year"] == 2027
assert data["forecast_years"] == [2027, 2028, 2029, 2030, 2031]
print("[API PASS] Query parameters (start_year=2027, tax_rate=0.25) correctly handled.")

# 3. Test Export Excel binary streaming for multiple symbols
for sym in ["HPG", "FPT", "VCB", "MWG"]:
    resp = client.get(f"/api/valuation/export-excel/{sym}")
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp.headers.get("content-type", "")
    assert f"{sym}_3Way_Financial_Model.xlsx" in resp.headers.get("content-disposition", "")
    assert len(resp.content) > 10000, f"Excel file too small: {len(resp.content)}"
    
    # Parse in-memory
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert len(wb.sheetnames) == 7
    print(f"[API PASS] Export Excel streaming valid for {sym} ({len(resp.content)} bytes, 7 sheets).")

print("\nALL API ADVERSARIAL CHECKS PASSED SUCCESSFULLY!")
