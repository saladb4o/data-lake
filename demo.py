import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from vnstock import Company, Quote

print("========================================")
print(" 1. THÔNG TIN CÔNG TY FPT")
print("========================================")
company = Company(symbol="FPT", source="VCI")
overview = company.overview()
print(overview[["symbol", "organ_code", "current_price", "is_bank", "listing"]])

print("\n========================================")
print(" 2. LỊCH SỬ GIÁ CỔ PHIẾU FPT (GẦN NHẤT)")
print("========================================")
quote = Quote(symbol="FPT", source="VCI")
df_history = quote.history(start="2026-08-01", end="2026-08-17")
print(df_history.tail(5))
