"""English label -> Vietnamese, for every label the CFI model came with.

Two rules govern what is here.

Translate what a Vietnamese reader would otherwise have to translate in
their head: every line item, every heading, every note. Do not translate
what Vietnamese practice already writes in English. WACC, DCF, EBITDA,
FCFF, NOPAT, EV/EBITDA, P/CF, SOTP, CapEx and beta are read as-is in
Vietnamese equity research; rendering them into Vietnamese would make the
model harder to read, not easier. Those live in KEEP, so the coverage
check can tell a deliberate choice from an oversight.

Keys are matched against the shared string table exactly, so a trailing
space or a footnote digit is part of the key.
"""

# Terms kept in English on purpose (see the module docstring).
# Plain column headings - Low, Mid, High, Median, Acquirer, Target and
# the rest - used to sit here. They were never deliberate: they were
# short enough to look risky to substitute, and a workbook written for
# one Vietnamese reader has no reason to head a column "Acquirer".
KEEP = {
    "WACC", "DCF", "SOTP", "EBITDA", "FCFF", "NOPAT", "EV/EBITDA",
    "EV/Revenue", "P/CF", "EV / EBITDA", "Beta", "CapEx", "Base",
    "Bull", "Bear", "Other", "Total", "Name", "Ticker", "Dates",
    "Price", "Share", "Cash", "Equity", "Capital", "Country", "Debt",
    "Label", "Enterprise", "Levered", "Unlevered", "Subs", "Cloud",
    "Advertising", "Buy", "Notes:", "Source:", "Transaction",
    "Cash Flow", "Market", "BOP", "EOP", "Days", "Time Periods",
    "Defined Name", "Input", "Company Name", "EBIT", "Mua",
    "_CompanyName", "_Vdate", "_YEdate_After", "_RoundBillions",
    "_TaxRate", "_WACC", "_LTGrowth",
}

TERMS = {
    # -- section headings -------------------------------------------------
    "Discounted Cash Flow (DCF) Analysis": "Phân tích chiết khấu dòng tiền (DCF)",
    "Discounted Cash Flow Analysis": "Phân tích chiết khấu dòng tiền",
    "Weighted-Average Cost of Capital (WACC)": "Chi phí vốn bình quân gia quyền (WACC)",
    "Implied Value Summary": "Tổng hợp giá trị ước tính",
    "Key Summary Outputs": "Kết quả tổng hợp",
    "Financial Forecast": "Dự phóng tài chính",
    "General Assumptions": "Giả định chung",
    "Company Overview": "Tổng quan doanh nghiệp",
    "Projections Summary": "Tổng hợp dự phóng",
    "Revenue Summary": "Tổng hợp doanh thu",
    "Valuation Summary": "Tổng hợp định giá",
    "Valuation Summary - Waterfall Chart": "Tổng hợp định giá - biểu đồ thác nước",
    "Comparable Companies Beta": "Beta của doanh nghiệp so sánh",
    "Historical Share Price Performance": "Diễn biến giá cổ phiếu",
    "Football Field Chart": "Biểu đồ khoảng giá trị",
    "Macroeconomic Forecasts": "Dự báo kinh tế vĩ mô",
    "Leverage Multiples": "Hệ số đòn bẩy",
    "Current Capitalization": "Vốn hoá hiện tại",
    "Secondary Value Measures - Enterpise Value Calculation":
        "Thước đo bổ trợ - tính giá trị doanh nghiệp",
    "Revenue Breakdown (2020A vs. 2031E)": "Cơ cấu doanh thu (năm đầu vs. năm cuối)",
    "Revenue By Category (Base Case)": "Doanh thu theo mảng (kịch bản cơ sở)",
    "EBITDA & FCFF (Base Case)": "EBITDA & FCFF (kịch bản cơ sở)",
    "EBITDA &amp; FCFF (Base Case)": "EBITDA & FCFF (kịch bản cơ sở)",
    "Net Earnings (Base Case)": "Lợi nhuận sau thuế (kịch bản cơ sở)",
    "Total Revenues": "Tổng doanh thu",

    # -- DCF ---------------------------------------------------------------
    "Valuation Date / Fiscal Year-End": "Ngày định giá / kết thúc năm tài chính",
    "Date for NPV Calculation": "Ngày quy về hiện giá",
    "Year Fraction": "Phần năm",
    "EBITDA (Excluding SBC)": "EBITDA (không gồm chi phí cổ phiếu thưởng)",
    "Free Cash Flow to Firm (FCFF)": "Dòng tiền tự do của doanh nghiệp (FCFF)",
    "Terminal Value": "Giá trị cuối kỳ",
    "Terminal Value: Exit Multiple": "Giá trị cuối kỳ: theo bội số thoái vốn",
    "Terminal Value: Perpetual Growth": "Giá trị cuối kỳ: theo tăng trưởng vĩnh viễn",
    "Terminal Value: Average": "Giá trị cuối kỳ: bình quân hai phương pháp",
    "Selected Terminal Value": "Giá trị cuối kỳ được chọn",
    "Terminal Value EBITDA Multiple": "Bội số EBITDA cuối kỳ",
    "Terminal Value Methodology Toggle": "Chọn phương pháp giá trị cuối kỳ",
    "Valuation FCFF": "FCFF dùng để định giá",
    "NPV - Future Cash Flows": "Hiện giá dòng tiền dự phóng",
    "NPV - Terminal Value": "Hiện giá giá trị cuối kỳ",
    "Enterprise Value": "Giá trị doanh nghiệp",
    "Equity Value": "Giá trị vốn chủ sở hữu",
    "Less: Net Debt": "Trừ: nợ vay ròng",
    "Plus: Net Debt": "Cộng: nợ vay ròng",
    "Net Debt": "Nợ vay ròng",
    "Discount Rate": "Tỷ lệ chiết khấu",
    "Exit Multiple": "Bội số thoái vốn",
    "Sensitivity Inputs  (Do Not Remove)": "Đầu vào bảng độ nhạy (không xoá)",
    "Base Case Annual Growth Taper": "Hệ số giảm dần tăng trưởng - kịch bản cơ sở",
    "Cost of Sales (% Revenue)": "Giá vốn hàng bán (% doanh thu)",
    "Cost of Sales (% of Revenue)": "Giá vốn hàng bán (% doanh thu)",

    # -- WACC --------------------------------------------------------------
    "Target Capital Structure": "Cơ cấu vốn mục tiêu",
    "Current Capital Structure": "Cơ cấu vốn hiện tại",
    "Proportion of Debt": "Tỷ trọng nợ vay",
    "Proportion of Equity": "Tỷ trọng vốn chủ sở hữu",
    "Market Cap": "Vốn hoá thị trường",
    "Total Debt": "Tổng nợ vay",
    "Debt / Equity": "Nợ vay / vốn chủ sở hữu",
    "Cost of Debt": "Chi phí nợ vay",
    "Pre-Tax Cost of Debt": "Chi phí nợ vay trước thuế",
    "After-Tax Cost of Debt": "Chi phí nợ vay sau thuế",
    "Cost of Equity": "Chi phí vốn chủ sở hữu",
    "Risk Free Rate": "Lãi suất phi rủi ro",
    "Equity Risk Premium": "Phần bù rủi ro vốn cổ phần",
    "Country Risk Premium": "Phần bù rủi ro quốc gia",
    "Size Premium": "Phần bù quy mô",
    "Company Specific Risk Premium": "Phần bù rủi ro riêng của doanh nghiệp",
    "Levered Equity Beta": "Beta vốn chủ sở hữu (có đòn bẩy)",
    "Selected WACC": "WACC được chọn",
    "Tax Rate": "Thuế suất",
    "Mkt. Val.": "Giá trị thị trường",
    "Beta (5-Yr)1": "Beta (5 năm)",
    "5-Yr. Avg.": "Bình quân 5 năm",
    "Debt /": "Nợ vay /",
    "1 Sources: Yahoo Finance, Company Filings.": "",

    # -- financial statements ---------------------------------------------
    "Cash and Cash Equivalents at the Beginning of the period":
        "Tiền và tương đương tiền đầu kỳ",
    "Net Cash Provided by (used in) Operating Activities":
        "Lưu chuyển tiền thuần từ hoạt động kinh doanh",
    "Net Cash Provided by (used in) Investing Activities":
        "Lưu chuyển tiền thuần từ hoạt động đầu tư",
    "Funding Shortfall": "Thiếu hụt nguồn vốn",
    "Additional Common Shares": "Cổ phiếu phổ thông phát hành thêm",
    "Debt Additions Schedule": "Bảng theo dõi vay thêm",
    "Total Long-Term Debt Schedule": "Bảng theo dõi nợ vay dài hạn",
    "Total Long-Term Debt": "Tổng nợ vay dài hạn",
    "Total Proceeds (Repayments) from Long-Term Debt and Other":
        "Tiền vay (trả nợ) dài hạn và khác",
    "Opening Balance": "Số dư đầu kỳ",
    "Closing Balance": "Số dư cuối kỳ",
    "Plus: Additions": "Cộng: vay thêm",
    "Less: Principal Repayments": "Trừ: trả nợ gốc",

    # -- valuation summary / dashboard ------------------------------------
    "Average Implied Value": "Giá trị ước tính bình quân",
    "Average Implied Value:": "Giá trị ước tính bình quân:",
    "Current Share Price": "Giá cổ phiếu hiện tại",
    "Valuation Date:": "Ngày định giá:",
    "Recommendation:": "Khuyến nghị:",
    "Market Capitalization": "Vốn hoá thị trường",
    "Total Debt / Equity": "Tổng nợ vay / vốn chủ sở hữu",
    "Total Debt / Book Capital": "Tổng nợ vay / vốn theo sổ sách",
    "Net Earnings": "Lợi nhuận sau thuế",
    "52-Week Trading": "Vùng giá 52 tuần",
    "52-week Trading": "Vùng giá 52 tuần",
    "52-week Trading Range (per Share)": "Vùng giá 52 tuần (mỗi cổ phiếu)",
    "Consensus Research": "Đồng thuận phân tích",
    "Precedent Transactions": "Giao dịch tiền lệ",
    "Precedent Tx": "Giao dịch tiền lệ",
    "Precedents": "Giao dịch tiền lệ",
    "Equity Analyst Target Prices": "Giá mục tiêu của chuyên viên phân tích",
    "Equity Analyst Target Prices (Per Share)":
        "Giá mục tiêu của chuyên viên phân tích (mỗi cổ phiếu)",
    "Implied Enterprise Value": "Giá trị doanh nghiệp ước tính",
    "Comparable Multiple Range": "Khoảng bội số so sánh",
    "Implied Multiple Range": "Khoảng bội số ước tính",
    "Implied Transaction Multiples (LTM)": "Bội số giao dịch ước tính (12 tháng gần nhất)",
    "Target LTM Financials": "Số liệu 12 tháng gần nhất của bên bị mua",
    "lo (bar)": "cận dưới (cột)",
    "hi (bar)": "cận trên (cột)",
    "Fully Diluted Shares Outstanding (MM)":
        "Số cổ phiếu lưu hành pha loãng hoàn toàn (triệu cp)",
    # the unit pass runs first and turns "(MM)" into "(trieu cp)", which
    # leaves an English head on a Vietnamese tail - a label that looks
    # translated to anything checking for Vietnamese characters
    "Fully Diluted Shares Outstanding":
        "Số cổ phiếu lưu hành pha loãng hoàn toàn",

    # -- comps -------------------------------------------------------------
    "Current Trading Multiples3": "Bội số giao dịch hiện tại",
    "Cap.1": "Vốn hoá",
    "Value2": "Giá trị",
    "Financial Estimates3": "Số liệu dự phóng",
    "Book Cap.": "Vốn theo sổ sách",
    "Cap.1": "Vốn hoá",
    "Shares1": "Số cổ phiếu",
    "Value2": "Giá trị",
    "1.  Fully diluted (treasury stock method)":
        "1. Pha loãng hoàn toàn (phương pháp cổ phiếu quỹ)",
    "2.  Market capitalization plus long term debt net of working capital as at the most recently disclosed quarter, adjusted for subsequent acquisitions and financings":
        "2. Vốn hoá cộng nợ vay dài hạn trừ vốn lưu động tại kỳ báo cáo gần nhất, "
        "điều chỉnh cho các thương vụ và đợt huy động vốn sau đó",
    "3.  Based on Consensus research estimates": "3. Theo số liệu đồng thuận của các công ty chứng khoán",
    "FY+1": "Năm +1",
    "FY+2": "Năm +2",

    # -- control panel / scenarios ----------------------------------------
    "Toggles and Controls (DO NOT DELETE)": "Công tắc điều khiển (không xoá)",
    "Sensitivities Control ": "Điều khiển bảng độ nhạy",
    "Base Case": "Kịch bản cơ sở",
    "Bull Case": "Kịch bản lạc quan",
    "Bear Case": "Kịch bản thận trọng",
    "Base Case EBITDA": "EBITDA - kịch bản cơ sở",
    "Bull Case EBITDA": "EBITDA - kịch bản lạc quan",
    "Bear Case EBITDA": "EBITDA - kịch bản thận trọng",
    "Base Case FCFF": "FCFF - kịch bản cơ sở",
    "Bull Case FCFF": "FCFF - kịch bản lạc quan",
    "Bear Case  FCFF": "FCFF - kịch bản thận trọng",
    "Base Case Net Earnings": "Lợi nhuận sau thuế - kịch bản cơ sở",
    "Bull Case Net Earnings": "Lợi nhuận sau thuế - kịch bản lạc quan",
    "Bear Case  Net Earnings": "Lợi nhuận sau thuế - kịch bản thận trọng",
    "Based on Base Estimates and Demonstrated Historical Growth":
        "Theo dự phóng cơ sở và tăng trưởng lịch sử đã ghi nhận",
    "+ for Bull Case": "(+) cho kịch bản lạc quan",
    "(-) for Bear Case": "(-) cho kịch bản thận trọng",

    # -- market size / macro / consensus ----------------------------------
    "US Market Size": "Quy mô thị trường",
    "US Market Size Growth Rate": "Tốc độ tăng quy mô thị trường",
    "Convert Millions to Billions": "Quy đổi triệu sang tỷ",
    "Global (Purchasing Power Parity (\"PPP\") rate)":
        "Toàn cầu (theo ngang giá sức mua PPP)",
    "GDP Growth": "Tăng trưởng GDP",
    "Inflation": "Lạm phát",
    "Research Contributor": "Đơn vị phân tích",
    "Target Price": "Giá mục tiêu",

    # -- segment memo: the model forecasts one revenue line, so the segment
    # names are placeholders for whatever the user's own segments are
    "Online Stores": "Mảng 1",
    "Physical Stores": "Mảng 2",
    "Retail Third-Party Seller Services": "Mảng 3",
    "Subscription Services": "Mảng 4",
    "Subscription": "Mảng 4",
    "AWS": "Mảng 5",
    "Amazon 1P": "Mảng 1",
    "Amazon 3P": "Mảng 2",
    "Total Amazon Implied Equity Value": "Tổng giá trị vốn chủ sở hữu ước tính",
    "Total Amazon Implied Equity Value per Share ($/sh.)":
        "Giá trị vốn chủ sở hữu ước tính mỗi cổ phiếu (đồng/cp)",

    # -- heads left behind by the unit pass --------------------------------
    # build_units_and_titles replaces "US$MM" and its relatives inside
    # longer headings, which turns an English title with a dollar unit
    # into an English title with a dong unit - a label that reads as
    # translated to anything looking for Vietnamese characters in it.
    "Sensitivities - Instrinsic Value": "Độ nhạy - giá trị nội tại",
    "DCF Value Summary": "Tổng hợp giá trị DCF",
    "Historical and Forecast Financial Performance":
        "Kết quả tài chính lịch sử và dự phóng",

    # -- the copyright line the model stamped on every sheet --------------
    "© Corporate Finance Institute. All rights reserved.": "",
}

# Table headings the audit could not see. The heuristic that found the
# half-translated heads looks for three consecutive words with no
# Vietnamese diacritics, so by construction it is blind to a one-word
# column heading - and a comparables table is almost entirely one-word
# column headings.
ONE_WORD_HEADS = {
    "Low": "Thấp",
    "Mid": "Giữa",
    "High": "Cao",
    "Mean": "Trung bình",
    "Median": "Trung vị",
    "Mode": "Yếu vị",
    "Average": "Bình quân",
    "Revenue": "Doanh thu",
    "Earnings": "Lợi nhuận",
    "Announced": "Công bố",
    "Date": "Ngày",
    "Acquirer": "Bên mua",
    "Target": "Bên bị mua",
    "Type": "Hình thức",
    "Value": "Giá trị",
    "Current": "Hiện tại",
    "Implied": "Ngầm định",
    "Comments": "Ghi chú",
    "Sources:": "Nguồn:",
    "Effective Date": "Ngày hiệu lực",
    "Action": "Hành động",
    "Recommendation": "Khuyến nghị",
}
TERMS.update(ONE_WORD_HEADS)
