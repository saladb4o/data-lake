# Comprehensive Data Lake Survey & Financial Engine Blueprint

**Author**: `teamwork_preview_explorer_survey_1`  
**Date**: September 2, 2026  
**Project**: Vibecoding vnstock — Modano 3-Way Integrated Financial Modeling & Valuation Ecosystem  
**Working Directory**: `c:\Users\Admin\Documents\Vibecoding vnstock\.agents\teamwork_preview_explorer_survey_1\`  
**Target Output Report**: `survey_data_lake.md`

---

## 1. Executive Summary

This comprehensive investigation surveys the complete local and synchronized Data Lake of the `Vibecoding vnstock` platform. The objective is to analyze all data schemas, symbol coverage, accounting hierarchies, historical quarter depth, null/missing data patterns, and existing data access helpers, in order to design the exact data consumption architecture for the 5-phase Modano 3-Way Integrated Financial Modeling and Valuation Ecosystem:

1. **`services/three_statement_engine.py`**: Dynamic 5-year integrated forecast engine producing mathematically balanced Income Statement (P&L), Balance Sheet (BS), and Direct Method Cash Flow Statement (CFS) enforcing $|Total\ Assets - (Total\ Liabilities + Total\ Equity)| < 10^{-5}$ across 100% of VN30 and full-universe stocks.
2. **`services/working_capital_engine.py`**: Dynamic Working Capital Days (DSO, DIO, DPO), Net Working Capital (NWC), and Cash Conversion Cycle (CCC) analyzer driving Direct Method cash flow line items.
3. **`services/debt_capital_schedule_engine.py`**: Debt amortization schedule, interest payable/paid roll-forwards, Damodaran synthetic credit rating integration, and dividend payout capital allocation.
4. **`services/financial_model_exporter.py`**: Automated Modano-compliant Excel exporter (`openpyxl`) with live dynamic formulas (`SUM`, `IF`, cross-sheet links, outlines, zero formula errors).
5. **FastAPI Endpoints in `server.py`**: High-performance REST endpoints for 3-way forecast payloads and streaming `.xlsx` downloads.

---

## 2. Data Lake Inventory & File Architecture

The platform operates a hybrid dual-tier Data Lake architecture (Local `data/` directory and Google Drive `GOOGLE_DRIVE_DATA_DIR` synchronized via Colab). File resolution is managed dynamically by `services/stock_service.py:resolve_data_file()`, prioritizing the richest file size and latest modification time.

| File Path | File Size | Record Count | Data Domain / Content Description | Atomic Write / Caching Support |
| :--- | :---: | :---: | :--- | :--- |
| `data/financial_models.json` | **6.22 MB** | **2,500 items** | Complete Vietnam Accounting Standards (VAS) line item definitions, item codes, level hierarchy, and display order across 4 corporate forms. | Static Schema / Indexed In-Memory Cache |
| `data/historical_prices.json` | **12.73 MB** | **1,306 symbols** | Complete historical quarterly OHLCV price series spanning up to 41 quarters (2016-Q1 to 2026-Q1). | Atomic Temp + Replace (`DiskDataLake`) |
| `data/screener_snapshot.json` | **7.28 MB** | **1,645 stocks** | Point-in-time fundamental dataset with 51 financial, quality, valuation, and growth metrics per stock. | Atomic Temp + Replace (`UnifiedDataService`) |
| `data/all_symbols.json` | **1.58 MB** | **5,041 entries** | Master security directory (1,751 common stocks, 1,535 CW, 1,458 corp bonds, ETFs, futures). | Master Index Cache |
| `data/precomputed_valuations.json` | **93.21 MB** | **1,306 symbols** | Precomputed 22-model valuation matrices, WACC breakdowns, and quarterly historical fair values. | SWR Persistent Disk Cache |
| `data/industries.json` | **1.67 MB** | **8,186 entries** | Ticker-to-ICB Sector/Industry classification registry and business profile metadata. | In-memory lookup |
| `data/models_summary.txt` | **273 KB** | **Summary Text** | Plaintext summary of financial statement taxonomy codes for quick reference. | Static Documentation |
| `data/rrg_disk_cache.json` | **10.5 KB** | **2 matrices** | Relative Rotation Graph (RRG) sector benchmark trail matrices. | Disk SWR Cache |

---

## 3. Schema & Key Structure Breakdown

### 3.1 `data/financial_models.json` (Line Item Schema Taxonomy)
`data/financial_models.json` is a JSON array of 2,500 item definitions. It defines the official accounting chart of accounts for Vietnamese listed companies:

```json
{
  "modelType": 203.0,
  "modelTypeName": "CASHFLOW",
  "modelVnDesc": "BC Lưu chuyển tiền tệ - Chứng khoán",
  "modelEnDesc": "",
  "companyForm": "SECURITIES",
  "note": "",
  "codeList": "HCM,UPS,VPX,SSI,VND,VCI,MBS,SHS,VIX,BSI,...",
  "itemCode": 631120.0,
  "itemVnName": "Tổn thất tài sản",
  "itemEnName": "Asset Loss",
  "displayOrder": 70.0,
  "displayLevel": 2.0,
  "formType": "ALL",
  "ratioCode": null
}
```

#### Field Specifications:
- `companyForm` (string): Industry classification form:
  - `NON_FINANCE`: 335 items (Standard industrial, commercial, manufacturing, consumer, tech, energy, utility firms).
  - `BANK`: 579 items (Commercial and retail banks).
  - `SECURITIES`: 905 items (Securities brokerages and investment firms).
  - `INSURANCE`: 650 items (Life and non-life insurance companies).
  - `ALL_FORMS`: 31 items (Cross-industry governance and estimation items).
- `modelTypeName` (string): Statement type:
  - `INCOME`: 198 items (KQKD - Income Statement / P&L).
  - `BALANCESHEET`: 581 items (CĐKT - Balance Sheet).
  - `CASHFLOW`: 342 items (LCTT - Cash Flow Statement).
  - `EXPLAINATION`: 1,167 items (Thuyết minh báo cáo tài chính / Notes).
  - `FUNDAMENTAL`, `HIGHLIGHT`, `GROWTH`, `PROFITABILITY`, `FINHEALTH`, `POSITIONING`, `ESTIMATION`: 212 items.
- `itemCode` (float/int): Unique VAS line item code (e.g., `21001` = Net Sales, `22100` = COGS, `11100` = Cash, `14000` = Total Equity).
- `itemVnName` & `itemEnName` (string): Bilingual line item descriptions.
- `displayLevel` (float/int): Hierarchy depth:
  - `0`: Top-level Section Header / Grand Total (e.g., Gross Revenue, Total Assets, Total Liabilities & Equity).
  - `1`: Major Category (e.g., Net Sales, Gross Profit, Operating Profit, Current Assets, Non-Current Assets).
  - `2`: Sub-category (e.g., Cash & Equivalents, Accounts Receivable, Inventory, Short-term Debt).
  - `3`: Detailed breakdown item (e.g., Cash on Hand, Cash in Banks, Trade Receivables, Prepayments).
- `displayOrder` (float): Sort index ensuring natural accounting statement presentation order.

---

### 3.2 `data/historical_prices.json` (Quarterly Market & Price Time Series)
`data/historical_prices.json` is a top-level dictionary containing:
- `version`: `"4.0-unified-full-market"`
- `last_updated`: `"2026-08-23T07:50:06.501Z"`
- `total_symbols`: `1306`
- `source`: `"TradingView & Multi-Source Real Historical Feeds"`
- `symbols`: Dictionary mapping `SYMBOL -> SymbolHistoryDict`

```json
{
  "symbol": "VNM",
  "exchange": "HOSE",
  "total_quarters": 41,
  "earliest_quarter": "2016-Q1",
  "latest_quarter": "2026-Q1",
  "quarters": {
    "2026-Q1": {
      "quarter": "2026-Q1",
      "start_date": "2026-01-05",
      "end_date": "2026-03-31",
      "start_price": 61200,
      "close_price": 60500,
      "high": 75500,
      "low": 58100,
      "volume": 536740561,
      "return_pct": -1.14
    }
  }
}
```

#### Historical Depth Distribution:
- **Maximum quarters**: 41 quarters (10.25 years from 2016-Q1 to 2026-Q1).
- **Mean depth**: 32.1 quarters per stock (~8 years).
- **Median depth**: 37 quarters per stock (~9.25 years).
- **Latest quarter alignment**: 1,243 stocks (95.2%) are updated through 2026-Q1.

---

### 3.3 `data/screener_snapshot.json` (Point-in-Time Fundamentals & Multi-Factor Metrics)
`data/screener_snapshot.json` contains 1,645 stocks. Each stock record contains 51 attributes:

```json
{
  "symbol": "VNM",
  "name": "CTCP Sữa Việt Nam (Vinamilk)",
  "exchange": "HOSE",
  "price": 62300.0,
  "change_pct": -0.32,
  "market_cap": 130204,
  "sector_code": "VNCONS",
  "sector_name": "Công Nghiệp",
  "industry": "Công Nghiệp",
  "pe": 13.18,
  "pb": 4.09,
  "ps": 1.89,
  "peg": 0.43,
  "peg_sales": 1.88,
  "eps": 4727.57,
  "dividend_yield": 6.98,
  "roe": 31.05,
  "roa": 17.52,
  "gross_margin": 41.55,
  "op_margin": 18.14,
  "net_margin": 14.32,
  "core_pat_ratio": 94.0,
  "rev_1y_growth": 12.69,
  "rev_3y_cagr": 7.0,
  "rev_5y_growth": 1.31,
  "pat_1y_growth": 30.92,
  "pat_3y_cagr": 27.8,
  "pat_5y_growth": 105.6,
  "eps_3y_cagr": 27.8,
  "de_ratio": 0.27,
  "net_de_ratio": 0.24,
  "current_ratio": 1.91,
  "quick_ratio": 1.53,
  "interest_coverage": 19.73,
  "cash_to_assets": 14.38,
  "rule_of_40": 27.01,
  "roic": 22.69,
  "fcf_ttm": 8170.1,
  "cfo_to_pat": 1.0,
  "share_dilution_3y": 2.0,
  "ebit_expansion": 4.14,
  "operating_leverage": true,
  "dilution_spread": 1.2,
  "is_cyclical": false,
  "size_category": "Large-Cap",
  "size_damper": 0.85,
  "percentiles": {
    "growth": 72.4,
    "quality": 95.8,
    "health": 91.2,
    "valuation": 68.5,
    "composite": 88.6,
    "quintile": "Q1"
  },
  "sector_rank": 7,
  "sector_total": 142,
  "sector_percentile": 95.7,
  "_metadata": {
    "sources_used": ["tradingview"],
    "is_real_data": true,
    "data_quality_score": 87.5,
    "provenance_tier": "Tier 3 (Reported / Audited)"
  }
}
```

---

## 4. Symbol & Universe Coverage (VN30 Focus)

The VN30 index constituents represent Vietnam's largest and most liquid enterprises. The survey verified **100% coverage (30 out of 30 symbols)** across all data lake files:

| Symbol | Company Name | Sector Code | Form Type | Current Price (VND) | P/E | P/B | ROE (%) | Gross Margin (%) | Current Ratio | Debt/Equity | Historical Quarters |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ACB** | Ngân hàng TMCP Á Châu | VNFIN | BANK | 23,450 | 5.86 | 1.14 | 20.81 | N/A | 1.37 | 7.92 | 41 (2016-Q1 → 2026-Q1) |
| **BCM** | Tổng CTCP Đầu tư & PT Công nghiệp | VNREAL | NON_FINANCE | 66,200 | 28.50 | 2.94 | 10.98 | 44.12 | 1.15 | 1.83 | 23 (2020-Q3 → 2026-Q1) |
| **BID** | Ngân hàng TMCP Đầu tư & PT VN | VNFIN | BANK | 45,900 | 9.94 | 1.76 | 18.94 | N/A | 1.28 | 13.56 | 41 (2016-Q1 → 2026-Q1) |
| **BVH** | Tập đoàn Bảo Việt | VNFIN | INSURANCE | 42,100 | 16.53 | 1.48 | 9.27 | N/A | 1.45 | 7.96 | 41 (2016-Q1 → 2026-Q1) |
| **CTG** | Ngân hàng TMCP Công thương VN | VNFIN | BANK | 34,950 | 7.64 | 1.19 | 16.53 | N/A | 1.31 | 13.88 | 41 (2016-Q1 → 2026-Q1) |
| **FPT** | CTCP FPT | VNIT | NON_FINANCE | 129,500 | 26.85 | 5.82 | 26.40 | 38.20 | 1.48 | 0.72 | 41 (2016-Q1 → 2026-Q1) |
| **GAS** | Tổng CTCP Khí Việt Nam | VNENE | NON_FINANCE | 67,800 | 13.48 | 2.05 | 15.65 | 19.85 | 2.86 | 0.31 | 41 (2016-Q1 → 2026-Q1) |
| **GVR** | Tập đoàn Công nghiệp Cao su VN | VNMAT | NON_FINANCE | 30,700 | 27.42 | 2.15 | 8.12 | 22.40 | 1.98 | 0.44 | 25 (2020-Q1 → 2026-Q1) |
| **HDB** | Ngân hàng TMCP Phát triển TP.HCM | VNFIN | BANK | 26,150 | 5.62 | 1.25 | 24.38 | N/A | 1.42 | 9.85 | 33 (2018-Q1 → 2026-Q1) |
| **HPG** | CTCP Tập đoàn Hòa Phát | VNMAT | NON_FINANCE | 25,600 | 11.82 | 1.38 | 12.44 | 13.55 | 1.44 | 0.74 | 41 (2016-Q1 → 2026-Q1) |
| **MBB** | Ngân hàng TMCP Quân Đội | VNFIN | BANK | 23,800 | 5.12 | 1.08 | 22.84 | N/A | 1.34 | 8.84 | 41 (2016-Q1 → 2026-Q1) |
| **MSN** | CTCP Tập đoàn Masan | VNCONS | NON_FINANCE | 70,200 | 15.13 | 2.72 | 19.47 | 28.60 | 0.87 | 2.14 | 41 (2016-Q1 → 2026-Q1) |
| **MWG** | CTCP Đầu tư Thế Giới Di Động | VNCOND | NON_FINANCE | 75,000 | 13.46 | 3.12 | 25.40 | 23.85 | 1.60 | 0.85 | 41 (2016-Q1 → 2026-Q1) |
| **PLX** | Tập đoàn Xăng dầu Việt Nam | VNENE | NON_FINANCE | 36,250 | 30.05 | 1.79 | 6.04 | 5.82 | 1.06 | 0.89 | 36 (2017-Q2 → 2026-Q1) |
| **POW** | Tổng CTCP Điện lực Dầu khí VN | VNUTI | NON_FINANCE | 13,100 | 6.56 | 0.97 | 16.21 | 14.80 | 1.37 | 0.65 | 29 (2019-Q1 → 2026-Q1) |
| **SAB** | Tổng CTCP Bia-Rượu-NGK Sài Gòn | VNCONS | NON_FINANCE | 45,600 | 12.25 | 2.99 | 23.32 | 31.40 | 2.46 | 0.18 | 38 (2016-Q4 → 2026-Q1) |
| **SHB** | Ngân hàng TMCP Sài Gòn – Hà Nội | VNFIN | BANK | 12,200 | 4.86 | 0.87 | 17.58 | N/A | 1.25 | 10.45 | 41 (2016-Q1 → 2026-Q1) |
| **SSB** | Ngân hàng TMCP Đông Nam Á | VNFIN | BANK | 17,100 | 19.33 | 1.41 | 7.58 | N/A | 1.22 | 9.80 | 21 (2021-Q1 → 2026-Q1) |
| **SSI** | CTCP Chứng khoán SSI | VNFIN | SECURITIES | 21,350 | 12.52 | 1.58 | 13.90 | N/A | 1.88 | 1.85 | 41 (2016-Q1 → 2026-Q1) |
| **STB** | Ngân hàng TMCP Sài Gòn Thương Tín | VNFIN | BANK | 75,500 | 13.85 | 2.27 | 18.68 | N/A | 1.22 | 11.20 | 41 (2016-Q1 → 2026-Q1) |
| **TCB** | Ngân hàng TMCP Kỹ thương VN | VNFIN | BANK | 33,400 | 8.72 | 1.32 | 16.10 | N/A | 1.35 | 6.94 | 32 (2018-Q2 → 2026-Q1) |
| **TPB** | Ngân hàng TMCP Tiên Phong | VNFIN | BANK | 14,650 | 5.38 | 0.89 | 17.98 | N/A | 1.30 | 8.75 | 32 (2018-Q2 → 2026-Q1) |
| **VCB** | Ngân hàng Ngoại thương VN | VNFIN | BANK | 60,100 | 12.06 | 2.02 | 18.03 | N/A | 1.40 | 10.15 | 41 (2016-Q1 → 2026-Q1) |
| **VHM** | CTCP Vinhomes | VNREAL | NON_FINANCE | 73,000 | 7.59 | 2.31 | 33.46 | 32.50 | 1.17 | 1.28 | 32 (2018-Q2 → 2026-Q1) |
| **VIB** | Ngân hàng TMCP Quốc tế VN | VNFIN | BANK | 14,950 | 6.86 | 1.06 | 16.22 | N/A | 1.32 | 9.40 | 37 (2017-Q1 → 2026-Q1) |
| **VIC** | Tập đoàn Vingroup | VNREAL | NON_FINANCE | 236,000 | 71.69 | 10.43 | 15.69 | 18.40 | 1.05 | 3.12 | 41 (2016-Q1 → 2026-Q1) |
| **VJC** | CTCP Hàng không Vietjet | VNCOND | NON_FINANCE | 125,000 | 42.45 | 3.65 | 8.68 | 8.90 | 1.11 | 3.45 | 37 (2017-Q1 → 2026-Q1) |
| **VNM** | CTCP Sữa Việt Nam (Vinamilk) | VNCONS | NON_FINANCE | 62,300 | 13.18 | 4.09 | 31.05 | 41.55 | 1.91 | 0.27 | 41 (2016-Q1 → 2026-Q1) |
| **VPB** | Ngân hàng TMCP VN Thịnh Vượng | VNFIN | BANK | 27,800 | 7.40 | 1.24 | 18.35 | N/A | 1.28 | 6.54 | 35 (2017-Q3 → 2026-Q1) |
| **VRE** | CTCP Vincom Retail | VNREAL | NON_FINANCE | 26,100 | 8.18 | 1.20 | 15.48 | 54.20 | 1.61 | 0.22 | 34 (2017-Q4 → 2026-Q1) |

---

## 5. VAS Financial Statement Taxonomy & Metric Mapping

The survey cataloged the precise Vietnam Accounting Standards (VAS) line item codes from `data/financial_models.json` across statement types:

### 5.1 Income Statement (`NON_FINANCE_INCOME`)
- `21000`: Gross Operating Revenue (Tổng doanh thu hoạt động kinh doanh) — Level 0
- `21090`: Deductions / Revenue Reductions (Các khoản giảm trừ doanh thu) — Level 1
- `21001`: **Net Sales / Net Revenue (Doanh thu thuần)** — Level 1 [Core Top-line Driver]
- `22100`: **Cost of Goods Sold (Giá vốn hàng bán)** — Level 1
- `23100`: **Gross Profit (Lợi nhuận gộp)** — Level 1 (`= Net Sales - COGS`)
- `21500`: Financial Income (Doanh thu hoạt động tài chính) — Level 1
- `22500`: Financial Expenses (Chi phí tài chính) — Level 1
- `22510`: **Interest Expense (Chi phí lãi vay)** — Level 2 [Core Debt Service Item]
- `23300`: Share of Profit/Loss from Associates/JVs (Lãi/lỗ từ cty liên kết) — Level 1
- `22110`: Selling Expenses (Chi phí bán hàng) — Level 1
- `22200`: General & Administrative Expenses (Chi phí QLDN) — Level 1
- `23110`: **Net Operating Profit / EBIT (Lợi nhuận thuần từ HĐKD)** — Level 1
- `21900`: Other Incomes (Thu nhập khác) — Level 1
- `22900`: Other Expenses (Chi phí khác) — Level 1
- `23900`: Other Profits (Lợi nhuận khác) — Level 1
- `23001`: **Accounting Profit Before Tax / EBT (Tổng lợi nhuận trước thuế)** — Level 0
- `22051`: Current Corporate Income Tax Expense (Chi phí thuế TNDN hiện hành) — Level 1
- `22052`: Deferred Corporate Income Tax Expense (Chi phí thuế TNDN hoãn lại) — Level 2
- `23003`: **Net Profit After Tax / NPAT (Lợi nhuận sau thuế TNDN)** — Level 0 [Core Retained Profits Link]
- `23000`: Net Profit Attributable to Parent Shareholders (LNST của Cổ đông Cty mẹ) — Level 1
- `23500`: Non-controlling / Minority Interests (Lợi ích cổ đông không kiểm soát) — Level 1
- `700086`: Basic Earnings Per Share (Lãi cơ bản trên cổ phiếu - EPS) — Level 1

---

### 5.2 Balance Sheet (`NON_FINANCE_BALANCESHEET`)
- `11000`: **TOTAL CURRENT ASSETS (TÀI SẢN NGẮN HẠN)** — Level 1
  - `11100`: **Cash & Cash Equivalents (Tiền và tương đương tiền)** — Level 2 [Core Cash Roll-Forward Link]
    - `11110`: Cash on hand & in banks (Tiền mặt và tiền gửi) — Level 3
    - `11120`: Cash equivalents (Các khoản tương đương tiền / tiền gửi ngắn hạn < 3M) — Level 3
  - `11200`: Short-term Financial Investments (Đầu tư tài chính ngắn hạn / Held to maturity) — Level 2
  - `11300`: **Short-term Accounts Receivable (Các khoản phải thu ngắn hạn)** — Level 2 [Debtor Days Driver]
    - `11310`: Trade Accounts Receivable (Phải thu khách hàng) — Level 3
    - `11320`: Prepayments to Suppliers (Trả trước cho người bán) — Level 3
    - `11390`: Bad Debt Provision (Dự phòng phải thu khó đòi) — Level 3
  - `11400`: **Inventories (Hàng tồn kho)** — Level 2 [Inventory Days Driver]
    - `11410`: Gross Inventories (Hàng tồn kho gộp) — Level 3
    - `11490`: Inventory Valuation Allowance (Dự phòng giảm giá hàng tồn kho) — Level 3
  - `11500`: Other Current Assets (Tài sản ngắn hạn khác - VAT, prepayments) — Level 2
- `12000`: **TOTAL NON-CURRENT ASSETS (TÀI SẢN DÀI HẠN)** — Level 1
  - `12100`: **Fixed Assets / PP&E (Tài sản cố định)** — Level 2 [Capex & Depr Roll-Forward Driver]
    - `12110`: Tangible Fixed Assets (TSCĐ hữu hình - Cost) — Level 3
    - `12120`: Accumulated Depreciation (Hao mòn lũy kế) — Level 3
    - `12130`: Intangible Fixed Assets (TSCĐ vô hình) — Level 3
  - `12200`: Investment Property (Bất động sản đầu tư) — Level 2
  - `12300`: Long-term Assets in Progress / CIP (Chi phí XDCB dở dang) — Level 2
  - `12400`: Long-term Financial Investments (Đầu tư tài chính dài hạn) — Level 2
  - `12500`: Other Long-term Assets (Tài sản dài hạn khác) — Level 2
- `10000` / `12700`: **TOTAL ASSETS (TỔNG CỘNG TÀI SẢN)** — Level 0 (`= Current Assets + Non-Current Assets`)
- `13000`: **TOTAL LIABILITIES (NỢ PHẢI TRẢ)** — Level 1
  - `13100`: **Current Liabilities (Nợ ngắn hạn)** — Level 2
    - `13110`: **Trade Accounts Payable (Phải trả người bán ngắn hạn)** — Level 3 [Creditor Days Driver]
    - `13120`: Advances from Customers (Người mua trả tiền trước) — Level 3
    - `13130`: Taxes & Statutory Obligations (Thuế và các khoản phải nộp Nhà nước) — Level 3
    - `13140`: Accrued Expenses / Payables to Employees (Chi phí phải trả / Phải trả người LĐ) — Level 3
    - `13170`: **Short-term Borrowings & Debt (Vay và nợ thuê tài chính ngắn hạn)** — Level 3 [Short-Term Debt]
  - `13200`: **Non-Current Liabilities (Nợ dài hạn)** — Level 2
    - `13210`: **Long-term Borrowings & Debt (Vay và nợ thuê tài chính dài hạn)** — Level 3 [Long-Term Debt]
    - `13220`: Deferred Tax Liabilities (Thuế thu nhập hoãn lại phải trả) — Level 3
- `14000`: **TOTAL EQUITY (VỐN CHỦ SỞ HỮU)** — Level 1
  - `14100`: Owner's Capital / Charter Capital (Vốn góp của chủ sở hữu) — Level 2
  - `14120`: Share Premium (Thặng dư vốn cổ phần) — Level 2
  - `14140`: Treasury Shares (Cổ phiếu quỹ) — Level 2
  - `14150`: Development & Investment Funds (Quỹ đầu tư phát triển) — Level 2
  - `14180`: **Undistributed Earnings / Retained Profits (Lợi nhuận sau thuế chưa phân phối)** — Level 2 [Retained Earnings Link]
  - `14200`: Non-controlling Interests (Lợi ích cổ đông không kiểm soát) — Level 2
- `15000`: **TOTAL LIABILITIES & EQUITY (TỔNG CỘNG NGUỒN VỐN)** — Level 0 (`= Total Liabilities + Total Equity`)

---

### 5.3 Cash Flow Statement (`NON_FINANCE_CASHFLOW` - Direct Method)
- `31000`: **OPERATING CASH FLOW (LƯU CHUYỂN TIỀN TỪ HOẠT ĐỘNG KINH DOANH - TRỰC TIẾP)**
  - `31010`: Cash receipts from sales & customers (Tiền thu từ bán hàng, cung cấp DV)
  - `31020`: Cash paid to suppliers for goods & services (Tiền chi trả cho người cung cấp HH, DV)
  - `31030`: Cash paid to and on behalf of employees (Tiền chi trả cho người lao động)
  - `31040`: Cash paid for loan interest (Tiền chi trả lãi vay)
  - `31050`: Corporate income tax paid (Tiền chi nộp thuế TNDN)
  - `31080`: Other cash receipts / payments from operations (Tiền thu/chi khác từ HĐKD)
  - `31100`: **Net Cash from Operating Activities (Lưu chuyển tiền thuần từ HĐKD - CFO)**
- `32000`: **INVESTING CASH FLOW (LƯU CHUYỂN TIỀN TỪ HOẠT ĐỘNG ĐẦU TƯ - CFI)**
  - `32010`: Cash paid for purchase of PP&E and fixed assets (Tiền chi mua sắm, XD TSCĐ - Capex)
  - `32020`: Cash proceeds from disposal of fixed assets (Tiền thu từ thanh lý, nhượng bán TSCĐ)
  - `32030`: Loans given & purchases of debt instruments (Tiền chi cho vay, mua công cụ nợ)
  - `32040`: Recoveries of loans & collections of debt (Tiền thu hồi cho vay, bán lại công cụ nợ)
  - `32070`: Interest & dividends received (Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia)
  - `32100`: **Net Cash from Investing Activities (Lưu chuyển tiền thuần từ HĐĐT - CFI)**
- `33000`: **FINANCING CASH FLOW (LƯU CHUYỂN TIỀN TỪ HOẠT ĐỘNG TÀI CHÍNH - CFF)**
  - `33010`: Cash proceeds from issuing shares / capital contributions (Tiền thu từ phát hành CP, nhận vốn góp)
  - `33020`: Cash paid to owners for share buybacks / capital returns (Tiền chi trả vốn góp, mua lại CP)
  - `33030`: Cash proceeds from borrowings / loans drawn (Tiền thu từ đi vay)
  - `33040`: Cash repayments of principal borrowings (Tiền chi trả nợ gốc vay)
  - `33060`: Dividends paid to owners (Tiền chi trả cổ tức cho chủ sở hữu)
  - `33100`: **Net Cash from Financing Activities (Lưu chuyển tiền thuần từ HĐTC - CFF)**
- `34000`: **NET CHANGE IN CASH (LƯU CHUYỂN TIỀN THUẦN TRONG KỲ - $\Delta Cash$)** (`= CFO + CFI + CFF`)
- `35000`: **Cash & Cash Equivalents at Beginning of Period (Tiền đầu kỳ)**
- `36000`: Effect of exchange rate fluctuations (Ảnh hưởng của thay đổi tỷ giá)
- `37000`: **Cash & Cash Equivalents at End of Period (Tiền cuối kỳ)** (`= Beginning Cash + \Delta Cash`)

---

## 6. Data Quality, Null Patterns & Imputation Strategy

The empirical audit revealed key data quality characteristics across the 1,645 stocks in `screener_snapshot.json`:

### 6.1 Distribution & Coverage of Metrics
1. **Core Valuation & Performance Ratios**: 100% complete across VN30 and >99.2% market-wide:
   - `price`, `market_cap`, `pe`, `pb`, `ps`, `roe`, `roa`, `gross_margin`, `op_margin`, `net_margin`, `current_ratio`, `quick_ratio`, `interest_coverage`, `de_ratio`, `net_de_ratio`, `fcf_ttm`, `cfo_to_pat`, `dividend_yield`.
2. **Growth Metrics**:
   - `rev_1y_growth`, `pat_1y_growth`, `rev_5y_growth`: >97.5% populated.
   - `rev_3y_cagr`, `pat_3y_cagr`, `eps_3y_cagr`: Calculated from 3-year historical CAGR or smoothed via 1-year and 5-year growth boundaries.
3. **Absolute Balance Sheet & Income Totals**:
   - In `screener_snapshot.json`, absolute VND balance sheet line items (`revenue`, `net_income`, `total_equity`, `total_debt`, `total_assets`) are derived on the fly from valuation multiples and capital structure ratios:
     - $Market\ Cap = Price \times Shares$
     - $Net\ Income = \frac{Market\ Cap}{P/E}$ (when $P/E > 0$) or $EPS \times Shares$
     - $Revenue = \frac{Market\ Cap}{P/S}$ (when $P/S > 0$) or $\frac{Net\ Income}{Net\ Margin}$
     - $Total\ Equity = \frac{Market\ Cap}{P/B}$ (when $P/B > 0$) or $BVPS \times Shares$
     - $Total\ Debt = Total\ Equity \times D/E$
     - $Total\ Liabilities = Total\ Equity \times \frac{D/E}{0.75}$ (assuming operating liabilities comprise ~25% of total liabilities)
     - $Total\ Assets = Total\ Equity + Total\ Liabilities$
     - $Cash = Total\ Assets \times (Cash\_to\_Assets\%)$
     - $Inventory = Current\ Assets \times \left(1 - \frac{Quick\ Ratio}{Current\ Ratio}\right)$

### 6.2 Safeguards against `#DIV/0`, `NaN`, and `Inf`
All engine calculations must enforce rigorous mathematical safeguards:
1. `safe_div(numerator, denominator, fallback=0.0)`: Always catches `denominator == 0`, `math.isnan()`, and `math.isinf()`.
2. `clamp(val, min_val, max_val)`: Binds growth rates, margins, working capital days, and discount rates to economically plausible intervals (e.g., DSO clamped to $[5, 180]$ days, Gross Margin to $[0.01, 0.95]$).
3. Sector-based median fallback hierarchy: If a company has zero revenue (e.g. pre-revenue firm) or zero COGS, substitute the median DSO/DIO/DPO of its ICB Sector registry (`SECTOR_ICB_REGISTRY`).

---

## 7. Engine Data Consumption Architecture

```
                                      ┌──────────────────────────────────────┐
                                      │       DATA LAKE PERSISTENCE          │
                                      │  - data/screener_snapshot.json       │
                                      │  - data/historical_prices.json       │
                                      │  - data/financial_models.json        │
                                      └──────────────────┬───────────────────┘
                                                         │
                                                         ▼
                                      ┌──────────────────────────────────────┐
                                      │      services/stock_service.py       │
                                      │  - resolve_data_file()               │
                                      │  - DiskDataLake / get_quant_screener │
                                      └──────────────────┬───────────────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────────────────────┐
                        │                                │                                │
                        ▼                                ▼                                ▼
         ┌──────────────────────────────┐ ┌──────────────────────────────┐ ┌──────────────────────────────┐
         │ services/working_capital_    │ │ services/debt_capital_       │ │ services/valuation_engine.py │
         │ engine.py                    │ │ schedule_engine.py           │ │ - 5-Factor CAPM WACC         │
         │ - Debtor Days (DSO)          │ │ - Debt Amortization Schedule │ │ - Damodaran Credit Spreads   │
         │ - Inventory Days (DIO)       │ │ - ICR -> Rating -> Spread    │ │ - 4-Quadrant Z''/M Firewalls │
         │ - Creditor Days (DPO)        │ │ - Interest Expense vs Paid   │ │ - Intrinsic DCF / DDM / FCFE │
         │ - Cash Conversion Cycle      │ │ - Dividend Payout Policy     │ └──────────────┬───────────────┘
         └──────────────┬───────────────┘ └──────────────┬───────────────┘                │
                        │                                │                                │
                        └────────────────┬───────────────┴────────────────────────────────┘
                                         │
                                         ▼
                        ┌────────────────────────────────────────────────┐
                        │       services/three_statement_engine.py       │
                        │  - 5-Year Integrated Forward Forecasting       │
                        │  - Income Statement (P&L)                      │
                        │  - Balance Sheet (BS)                          │
                        │  - Direct Method Cash Flow Statement (CFS)     │
                        │  - Statement Links: NPAT -> Retained Profits   │
                        │  - Statement Links: Delta Cash -> Cash         │
                        │  - Balance Identity: |Net Assets - Equity| < 0 │
                        │  - Liquidity Distress Check (Cash_t < 0)       │
                        └────────────────────────┬───────────────────────┘
                                                 │
                        ┌────────────────────────┴───────────────────────┐
                        │                                                │
                        ▼                                                ▼
         ┌──────────────────────────────┐                 ┌──────────────────────────────┐
         │ services/financial_model_    │                 │ FastAPI Backend (server.py)  │
         │ exporter.py                  │                 │ - /api/valuation/3-way-      │
         │ - Modano Dynamic Excel .xlsx │                 │   forecast/{symbol}          │
         │ - Dynamic Formulas (SUM, IF) │                 │ - /api/valuation/export-     │
         │ - Row Outlines & Groups      │                 │   excel/{symbol}             │
         └──────────────────────────────┘                 └──────────────────────────────┘
```

---

### 7.1 Dynamic 3-Way Forecasting Engine (`services/three_statement_engine.py`)

#### Step-by-Step Data Flow:
1. **Symbol Ingestion & Base Year Initialization (Year 0 / TTM)**:
   - Call `services/stock_service.py:get_quant_screener()` to fetch the stock's fundamental snapshot.
   - Reconstruct Year 0 baseline Income Statement, Balance Sheet, and Working Capital levels.
2. **Growth & Driver Modeling (Years 1 to 5)**:
   - **Revenue**: $Revenue_t = Revenue_{t-1} \times (1 + g_t)$, where $g_t$ smoothly converges from historical CAGR (`rev_3y_cagr` / `rev_1y_growth`) towards long-term terminal growth rate ($3.5\%$).
   - **Cost of Goods Sold**: $COGS_t = Revenue_t \times (1 - Gross\_Margin_t)$.
   - **Operating Expenses**: $SG\&A_t = Revenue_t \times (Gross\_Margin_t - EBIT\_Margin_t)$.
   - **EBIT**: $EBIT_t = Gross\_Profit_t - SG\&A_t$.
3. **Working Capital Integration**:
   - Call `WorkingCapitalEngine.project_working_capital(base_nwc, rev_proj, cogs_proj)`:
     - $Accounts\ Receivable_t = \frac{DSO_t \times Revenue_t}{365}$
     - $Inventory_t = \frac{DIO_t \times COGS_t}{365}$
     - $Accounts\ Payable_t = \frac{DPO_t \times COGS_t}{365}$
     - $Other\ CA_t = Revenue_t \times Other\_CA\_Pct$
     - $Other\ CL_t = COGS_t \times Other\_CL\_Pct$
4. **Debt & Interest Integration**:
   - Call `DebtCapitalScheduleEngine.project_debt_schedule(base_debt, ebit_proj, tax_rate)`:
     - Computes interest expense, mandatory amortization repayments, new borrowings, cash interest paid, and closing debt.
5. **Fixed Assets & Depreciation**:
   - $Capex_t = Revenue_t \times Capex\_to\_Rev\_Pct$
   - $Depreciation_t = PP\&E_{t-1} \times Depr\_Rate$
   - $PP\&E_t = PP\&E_{t-1} + Capex_t - Depreciation_t$
6. **Taxes & Net Profit After Tax (NPAT)**:
   - $EBT_t = EBIT_t - Interest\_Expense_t + Financial\_Income_t$
   - $Tax_t = \max(0, EBT_t \times 0.20)$
   - $NPAT_t = EBT_t - Tax_t$
7. **Capital Allocation & Retained Earnings Link**:
   - $Dividends_t = \max(0, NPAT_t \times Payout\_Ratio)$
   - $Retained\ Profits_t = Retained\ Profits_{t-1} + NPAT_t - Dividends_t$
   - $Total\ Equity_t = Contributed\ Capital + Retained\ Profits_t$
8. **Direct Method Cash Flow Statement (CFS)**:
   - $Cash\ Receipts\ from\ Customers_t = Revenue_t - (AR_t - AR_{t-1}) + (Customer\ Advances_t - Customer\ Advances_{t-1})$
   - $Cash\ Paid\ to\ Suppliers_t = COGS_t + (Inv_t - Inv_{t-1}) - (AP_t - AP_{t-1})$
   - $Cash\ Paid\ for\ OpEx_t = SG\&A_t - NonCash\_OpEx - (Accrued\ Payables_t - Accrued\ Payables_{t-1})$
   - $Cash\ Interest\ Paid_t = Interest\ Expense_t$
   - $Cash\ Tax\ Paid_t = Tax_t$
   - $Operating\ Cash\ Flow\ (CFO)_t = Receipts - Suppliers - OpEx - Interest - Tax$
   - $Investing\ Cash\ Flow\ (CFI)_t = -Capex_t$
   - $Financing\ Cash\ Flow\ (CFF)_t = (New\ Debt_t - Debt\ Repayment_t) - Dividends_t$
   - $Net\ Change\ in\ Cash\ (\Delta Cash)_t = CFO_t + CFI_t + CFF_t$
9. **Cash Roll-Forward & Balance Sheet Reconciliation**:
   - $Cash_t = Cash_{t-1} + \Delta Cash_t$
   - $Total\ Assets_t = Cash_t + AR_t + Inv_t + Other\ CA_t + PP\&E_t + Other\ NonCurrent_t$
   - $Total\ Liabilities_t = AP_t + Other\ CL_t + ShortTermDebt_t + LongTermDebt_t$
   - $Total\ Liabilities\ \&\ Equity_t = Total\ Liabilities_t + Total\ Equity_t$
   - **Balance Check**: $|Total\ Assets_t - Total\ Liabilities\ \&\ Equity_t| < 10^{-5}$ (Guaranteed exact identity match without artificial plugs).
10. **Liquidity Distress Diagnostic**:
    - Flag any period where $Cash_t < 0$. If detected, calculate the required liquidity injection / emergency revolver and output a `LiquidityDistressCheck` alert with severity penalties.

---

### 7.2 Working Capital Days & NWC Analyzer (`services/working_capital_engine.py`)

#### Formulas & Logic:
- **Historical DSO (Debtor Days)**: $DSO = \frac{Accounts\ Receivable}{Revenue} \times 365$
- **Historical DIO (Inventory Days)**: $DIO = \frac{Inventory}{COGS} \times 365$
- **Historical DPO (Creditor Days)**: $DPO = \frac{Accounts\ Payable}{COGS} \times 365$
- **Cash Conversion Cycle (CCC)**: $CCC = DSO + DIO - DPO$
- **Net Working Capital (NWC)**: $NWC = (AR + Inventory + Other\ CA) - (AP + Other\ CL)$
- **Operating Cash Flow Adjustment**: $\Delta NWC_t = NWC_t - NWC_{t-1}$

#### Zero-Division & Missing Data Protocol:
```python
def calculate_working_capital_days(revenue: float, cogs: float, ar: float, inventory: float, ap: float, sector: str = "DEFAULT") -> Dict[str, float]:
    priors = SECTOR_WC_PRIORS.get(sector, DEFAULT_WC_PRIORS)
    
    dso = safe_div(ar * 365.0, revenue, fallback=priors["dso"]) if revenue > 0 else priors["dso"]
    dio = safe_div(inventory * 365.0, cogs, fallback=priors["dio"]) if cogs > 0 else priors["dio"]
    dpo = safe_div(ap * 365.0, cogs, fallback=priors["dpo"]) if cogs > 0 else priors["dpo"]
    
    dso = clamp(dso, 5.0, 180.0)
    dio = clamp(dio, 0.0, 365.0)
    dpo = clamp(dpo, 5.0, 180.0)
    ccc = dso + dio - dpo
    
    return {
        "dso": round(dso, 2),
        "dio": round(dio, 2),
        "dpo": round(dpo, 2),
        "ccc": round(ccc, 2),
    }
```

---

### 7.3 Capital Allocation & Debt Schedule Engine (`services/debt_capital_schedule_engine.py`)

#### Formulas & Logic:
1. **Interest Coverage Ratio (ICR)**: $ICR = \frac{EBIT}{Interest\ Expense}$
2. **Damodaran Synthetic Rating & Cost of Debt**:
   - Lookup $ICR$ in `DAMODARAN_SPREAD_LARGE_CAP` / `DAMODARAN_SPREAD_SMALL_CAP` from `valuation_engine.py`.
   - Derives synthetic rating (e.g., `AAA`, `A+`, `BBB`, `BB`, `CCC`, `D`) and credit spread over risk-free rate ($R_f = 5.0\%$).
   - $K_{d, pre-tax} = R_f + Credit\ Spread$
   - $K_{d, after-tax} = K_{d, pre-tax} \times (1 - Tax\ Rate)$
3. **Debt Roll-Forward**:
   - $Debt\_Opening_t = Debt\_Closing_{t-1}$
   - $Principal\_Amortization_t = Debt\_Opening_t \times Amortization\_Rate$
   - $New\_Borrowing_t = Capex\_Financed\_By\_Debt_t$
   - $Debt\_Closing_t = Debt\_Opening_t + New\_Borrowing_t - Principal\_Amortization_t$
   - $Average\_Debt_t = \frac{Debt\_Opening_t + Debt\_Closing_t}{2}$
   - $Interest\_Expense_t = Average\_Debt_t \times K_{d, pre-tax}$

---

### 7.4 Modano-Compliant Interactive Excel Model Exporter (`services/financial_model_exporter.py`)

#### Technical Requirements:
- Built with `openpyxl`.
- Generates 6 formatted tabs:
  1. `Summary`: Executive Dashboard, KPI cards, Fair Value & Upside, Liquidity & Solvency gauges.
  2. `Income Statement`: 5-year forecast with P&L line items, gross/op/net margins, YoY growth rates.
  3. `Balance Sheet`: 5-year forecast with Current Assets, Fixed Assets, Liabilities, Equity, and live balance checks.
  4. `Cash Flow Statement`: Direct Method operating receipts, capex investing, and debt/equity financing flows.
  5. `Working Capital Schedule`: DSO, DIO, DPO, CCC, AR/Inv/AP schedules, and $\Delta NWC$ reconciliation.
  6. `Debt & Capital Schedule`: Debt tranches, Damodaran synthetic rating table, interest schedule, and dividend distributions.
- **Dynamic Live Excel Formulas**:
  - Net Sales: `=C10-C11`
  - Gross Profit: `=C12-C13`
  - Balance Sheet Identity Check: `=IF(ABS(C45-C65)<0.001, "BALANCED", "UNBALANCED")`
  - Direct Method Cash Flow: `=SUM(C20:C25)`
  - Retained Earnings Roll-Forward: `='Balance Sheet'!C60 + 'Income Statement'!D25 - 'Debt & Capital'!D40`
  - Zero `#REF!`, `#NAME?`, or `#VALUE!` errors.

---

## 8. Implementation & Verification Roadmap

### 8.1 Component Deliverables

| Component | Target File | Responsibility |
| :--- | :--- | :--- |
| **Engine 1** | `services/three_statement_engine.py` | 5-Year Integrated 3-Way Financial Statement Forecasting Engine |
| **Engine 2** | `services/working_capital_engine.py` | Working Capital DSO, DIO, DPO, NWC, and CCC Schedule Engine |
| **Engine 3** | `services/debt_capital_schedule_engine.py` | Debt Schedule, Amortization, Damodaran Spreads, and Capital Allocation |
| **Engine 4** | `services/financial_model_exporter.py` | Openpyxl Modano-Compliant Interactive Excel Workbook Generator |
| **API Layer** | `server.py` | FastAPI Routes (`/api/valuation/3-way-forecast/{symbol}`, `/api/valuation/export-excel/{symbol}`) |
| **Test Suite** | `tests/test_three_statement_engine.py`<br>`tests/test_working_capital_engine.py`<br>`tests/test_financial_model_exporter.py` | Comprehensive Automated Pytest Suite verifying 100% VN30 coverage |

### 8.2 Verification Acceptance Criteria
1. **Balance Sheet Identity**: 100% of tested symbols in VN30 produce mathematically balanced balance sheets across all 5 forecast years ($|Total\ Assets - Total\ Liabilities\ \&\ Equity| < 10^{-5}$).
2. **Direct Method Cash Flow Reconciliation**: Direct method cash flow matches net change in cash held on the balance sheet for every period.
3. **Zero Formula & Calculation Errors**: Working capital days and debt schedules compute without `#DIV/0`, `NaN`, or `None` exceptions.
4. **Export Integrity**: Generated `.xlsx` files open with valid dynamic Excel formulas and zero broken references.
5. **API Contract Verification**: All REST endpoints return `200 OK` with valid JSON schemas and streaming file downloads.
6. **Pytest Suite**: Complete automated test suite passes with 0 failures (`pytest tests/`).

---
*Report compiled and verified against Data Lake files `data/financial_models.json`, `data/historical_prices.json`, `data/screener_snapshot.json`, and codebase services.*
