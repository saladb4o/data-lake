"""Turn the CFI Amazon model into a VAS (TT200) model, keeping its engine.

What is kept: the whole forecast machinery, the DCF, the WACC build, the
comparables, the dashboard, the charts. What is replaced: everything that
assumes a US GAAP filing.

The three blocks removed outright have no counterpart in Vietnamese
accounting rather than merely a different name for one:

  * the right-of-use asset and lease liability schedules, which exist
    because of ASC 842 / IFRS 16. VAS 06 keeps an operating lease off the
    balance sheet, so there is no asset to depreciate and no liability to
    unwind.
  * the segment revenue build. TT200 does not require a segment note in a
    form a vendor feed carries, so the rows stay as an optional memo the
    user may type into rather than a driver the model depends on.
  * the supplemental cash disclosures (interest paid, tax paid, cash
    acquired) which live in the thuyet minh, not in the three statements.

Run:  python3 scripts/xlsxvas/build_vas_template.py SOURCE.xlsx OUT.xlsx
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vas_layout as V
from xlsx_patch import WorkbookPatch

RD = "Raw Data"
FS = "Financial Statements"
CP = "Control Panel"
SC = "Scenarios"

HIST = V.HIST_COLS          # C..G
LAST_HIST = V.LAST_HIST_COL
FCST = V.FCST_COLS          # H..N
ALL_COLS = HIST + FCST

IS, BS, CF = V.IS_ROW, V.BS_ROW, V.CF_ROW


def prev_col(c: str) -> str:
    return chr(ord(c) - 1)


# ---------------------------------------------------------------- Raw Data
def build_raw_data(w: WorkbookPatch) -> None:
    w.clear_rows(RD, 7, 167)

    w.set_value(RD, "A2", "Số liệu tài chính lịch sử theo TT200")
    w.set_value(RD, "A3", "Đơn vị: triệu đồng, trừ khi ghi chú khác")
    w.set_value(RD, "A4", "Nguồn: (ghi rõ - BCTC kiểm toán hoặc dữ liệu "
                          "nhà cung cấp)")

    for line in V.ALL_LINES:
        if line.code:
            w.set_value(RD, f"A{line.row}", line.code)
        w.set_value(RD, f"B{line.row}", line.label)
        if line.formula:
            for c in HIST:
                w.set_formula(RD, f"{c}{line.row}", line.formula.format(c=c))

    w.set_value(RD, f"B{V.LAST_ROW + 2}", V.EQUITY_SPLIT_UNVERIFIED)
    build_drivers(w)


def build_drivers(w: WorkbookPatch) -> None:
    """The ratio block the Control Panel reads as forecast drivers.

    Column I names the driver, J..N compute it for each historical year and
    O averages them. The row numbers are the ones the Control Panel already
    points at, so the two sheets stay in step.
    """
    w.set_value(RD, "I5", "Chỉ số lịch sử và giả định dự phóng")
    w.set_value(RD, "O5", "Bình quân 5 năm")
    for c in HIST:
        w.set_formula(RD, f"{c}5", f"'{FS}'!{c}5")
    for i, c in enumerate(["J", "K", "L", "M", "N"]):
        w.set_formula(RD, f"{c}5", f"={HIST[i]}5".lstrip("="))

    rev = IS["10"]
    cogs = IS["11"]

    # driver row -> (label, per-year formula template)
    #   {c} is the year's column, {p} the year before it
    drivers = {
        16: ("Tăng trưởng doanh thu thuần",
             'IFERROR({c}%d/{p}%d-1,"na")' % (rev, rev), True),
        17: ("Giá vốn hàng bán (%% doanh thu thuần)",
             "IFERROR({c}%d/{c}%d,0)" % (cogs, rev), False),
        18: ("Chi phí bán hàng (%% doanh thu thuần)",
             "IFERROR({c}%d/{c}%d,0)" % (IS["25"], rev), False),
        19: ("Chi phí quản lý doanh nghiệp (%% doanh thu thuần)",
             "IFERROR({c}%d/{c}%d,0)" % (IS["26"], rev), False),
        20: ("Doanh thu hoạt động tài chính (%% doanh thu thuần)",
             "IFERROR({c}%d/{c}%d,0)" % (IS["21"], rev), False),
        21: ("Chi phí tài chính (%% doanh thu thuần)",
             "IFERROR({c}%d/{c}%d,0)" % (IS["22"], rev), False),
        23: ("Thuế suất hiệu dụng",
             "IFERROR(({c}%d+{c}%d)/{c}%d,0)"
             % (IS["51"], IS["52"], IS["50"]), False),
        26: ("Số ngày tồn kho",
             "IFERROR({c}%d/{c}%d*365,0)" % (BS["140"], cogs), False),
        27: ("Số ngày phải thu",
             "IFERROR({c}%d/{c}%d*365,0)" % (BS["130"], rev), False),
        29: ("Số ngày phải trả",
             "IFERROR({c}%d/{c}%d*365,0)" % (BS["311"], cogs), False),
        30: ("Tài sản ngắn hạn khác (%% doanh thu thuần)",
             "IFERROR({c}%d/{c}%d,0)" % (BS["150"], rev), False),
        31: ("Nợ ngắn hạn khác (%% doanh thu thuần)",
             "IFERROR(({c}%d-{c}%d-{c}%d)/{c}%d,0)"
             % (BS["310"], BS["311"], BS["320"], rev), False),
        33: ("CapEx (%% doanh thu thuần)",
             "IFERROR(-{c}%d/{c}%d,0)" % (CF["21"], rev), False),
        34: ("Khấu hao (%% TSCĐ đầu kỳ)",
             'IFERROR({c}%d/{p}%d,"na")' % (CF["02"], BS["220"]),
             True),
        36: ("Tăng trưởng đầu tư tài chính ngắn hạn",
             'IFERROR({c}%d/{p}%d-1,"na")' % (BS["120"], BS["120"]), True),
        37: ("Cổ tức đã trả (%% lợi nhuận sau thuế)",
             "IFERROR(-{c}%d/{c}%d,0)" % (CF["36"], IS["60"]), False),
    }

    year_cols = list(zip(["J", "K", "L", "M", "N"], HIST))
    for row, (label, tmpl, needs_prior) in drivers.items():
        w.set_value(RD, f"I{row}", label.replace("%%", "%"))
        for out_col, data_col in year_cols:
            if needs_prior and data_col == HIST[0]:
                continue          # the first year has nothing before it
            w.set_formula(RD, f"{out_col}{row}",
                          tmpl.format(c=data_col, p=prev_col(data_col)))
        first = "K" if needs_prior else "J"
        w.set_formula(RD, f"O{row}",
                      f"IFERROR(AVERAGE({first}{row}:N{row}),0)")


# ------------------------------------------------- Financial Statements
# Row numbers other sheets point at, which therefore may not move:
#   5, 8, 9, 10   period headers          (Scenarios, Raw Data, Dashboard)
#   26..31        segment memo            (SOTP, Dashboard)
#   19            total revenue growth    (Scenarios)
#   51            net income              (Dashboard)
#   334           EBITDA                  (DCF, PrecedentsVal, Dashboard)
#   345           FCFF                    (DCF, Dashboard)
#   324           implied interest rate   (Control Panel)
R_REV = 32
R_CHECK = 94
R_CASH_END = 135


def _hist(w, row: str, template: str) -> None:
    """Write a historical formula across C..G. {c} is the column."""
    for c in HIST:
        w.set_formula(FS, f"{c}{row}", template.format(c=c))


def _fcst(w, row: str, template: str) -> None:
    """Write a forecast formula across H..N. {c} column, {p} prior."""
    for c in FCST:
        w.set_formula(FS, f"{c}{row}", template.format(c=c, p=prev_col(c)))


def _both(w, row, hist_t, fcst_t):
    _hist(w, row, hist_t)
    _fcst(w, row, fcst_t)


def _label(w, sheet, row, text, col="B"):
    w.set_value(sheet, f"{col}{row}", text)


def _clear_row(w, sheet, row, cols=None):
    for c in (cols or ALL_COLS):
        w.clear(sheet, f"{c}{row}")


def build_income_statement(w: WorkbookPatch) -> None:
    _label(w, FS, 12, "Tăng trưởng và giả định")
    _label(w, FS, 13, "Tăng trưởng doanh thu thuần")
    for c in HIST[1:]:
        w.set_formula(FS, f"{c}13",
                      f"IFERROR({c}{R_REV}/{prev_col(c)}{R_REV}-1,\"na\")")
    w.clear(FS, f"{HIST[0]}13")
    _fcst(w, 13, f"{SC}!{{c}}14".replace(f"{SC}", f"'{SC}'"))
    for r in (14, 15, 16, 17, 18):
        _clear_row(w, FS, r)
        w.clear(FS, f"B{r}")
    _label(w, FS, 19, "Kiểm chứng: tăng trưởng doanh thu thực tế")
    for c in HIST[1:]:
        w.set_formula(FS, f"{c}19",
                      f"IFERROR({c}{R_REV}/{prev_col(c)}{R_REV}-1,\"na\")")
    w.clear(FS, f"{HIST[0]}19")
    _fcst(w, 19, f"IFERROR({{c}}{R_REV}/{{p}}{R_REV}-1,\"na\")")

    _label(w, FS, 22, "KẾT QUẢ HOẠT ĐỘNG KINH DOANH")
    _label(w, FS, 25, "Doanh thu theo mảng (tùy chọn - nhập tay từ "
                      "thuyết minh; không đưa vào tổng)")
    for i, r in enumerate(range(26, 32), start=1):
        _label(w, FS, r, f"Mảng {i}")
        _clear_row(w, FS, r)

    _label(w, FS, R_REV, "Doanh thu thuần (mã 10)")
    _both(w, R_REV, f"'{RD}'!{{c}}{IS['10']}",
          f"{{p}}{R_REV}*(1+{{c}}13)")

    _label(w, FS, 34, "Chi phí hoạt động:")
    _label(w, FS, 35, "Giá vốn hàng bán (mã 11)")
    _both(w, 35, f"'{RD}'!{{c}}{IS['11']}",
          f"{{c}}{R_REV}*'{CP}'!$W$25")
    _label(w, FS, 36, "Chi phí bán hàng (mã 25)")
    _both(w, 36, f"'{RD}'!{{c}}{IS['25']}",
          f"{{c}}{R_REV}*'{CP}'!$O$16")
    _label(w, FS, 37, "Chi phí quản lý doanh nghiệp (mã 26)")
    _both(w, 37, f"'{RD}'!{{c}}{IS['26']}",
          f"{{c}}{R_REV}*'{CP}'!$O$17")
    for r in (38, 39, 40, 41):
        _clear_row(w, FS, r)
        w.clear(FS, f"B{r}")
    _label(w, FS, 42, "Tổng chi phí hoạt động")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}42", f"SUM({c}35:{c}41)")
    _label(w, FS, 43, "Lợi nhuận từ hoạt động cốt lõi (EBIT)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}43", f"{c}{R_REV}-{c}42")

    _label(w, FS, 44, "Doanh thu hoạt động tài chính (mã 21)")
    _both(w, 44, f"'{RD}'!{{c}}{IS['21']}",
          f"{{c}}{R_REV}*'{CP}'!$O$18")
    _label(w, FS, 45, "Chi phí tài chính (mã 22)")
    _both(w, 45, f"-'{RD}'!{{c}}{IS['22']}", "-{c}323")
    _label(w, FS, 46, "Lợi nhuận khác (mã 40)")
    _both(w, 46, f"'{RD}'!{{c}}{IS['40']}", "0")
    _label(w, FS, 47, "Cộng: thu nhập/chi phí ngoài hoạt động cốt lõi")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}47", f"SUM({c}44:{c}46)")
    _label(w, FS, 48, "Tổng lợi nhuận kế toán trước thuế (mã 50)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}48", f"{c}43+{c}47")
    _label(w, FS, 49, "Chi phí thuế TNDN (mã 51 + 52)")
    _both(w, 49, f"-('{RD}'!{{c}}{IS['51']}+'{RD}'!{{c}}{IS['52']})",
          "{c}48*-_TaxRate")
    _clear_row(w, FS, 50)
    w.clear(FS, "B50")
    _label(w, FS, 51, "Lợi nhuận sau thuế (mã 60)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}51", f"SUM({c}48:{c}50)")
    _label(w, FS, 52, "Lãi cơ bản trên cổ phiếu (đồng)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}52", f"IFERROR({c}$51/{c}55,\"na\")")
    _clear_row(w, FS, 53)
    w.clear(FS, "B53")
    _label(w, FS, 54, "Số lượng cổ phiếu (triệu cp)")
    _label(w, FS, 55, "Bình quân lưu hành")
    _both(w, 55, f"'{RD}'!{{c}}{V.SHARES_AVG_ROW}", "{p}55+{c}$296")
    _label(w, FS, 56, "Đang lưu hành cuối kỳ")
    _both(w, 56, f"'{RD}'!{{c}}{V.SHARES_END_ROW}", "{p}56+{c}$296")


def build_balance_sheet(w: WorkbookPatch) -> None:
    _label(w, FS, 59, "BẢNG CÂN ĐỐI KẾ TOÁN")
    _label(w, FS, 62, "TÀI SẢN")

    _label(w, FS, 63, "Tiền và các khoản tương đương tiền (mã 110)")
    _both(w, 63, f"'{RD}'!{{c}}{BS['110']}", f"{{c}}{R_CASH_END}")
    _label(w, FS, 64, "Đầu tư tài chính ngắn hạn (mã 120)")
    _both(w, 64, f"'{RD}'!{{c}}{BS['120']}",
          f"{{p}}64*(1+'{CP}'!$O$34)")
    _label(w, FS, 65, "Các khoản phải thu ngắn hạn (mã 130)")
    _both(w, 65, f"'{RD}'!{{c}}{BS['130']}",
          f"{{c}}{R_REV}/{{c}}10*'{CP}'!$M$30")
    _label(w, FS, 66, "Hàng tồn kho (mã 140)")
    _both(w, 66, f"'{RD}'!{{c}}{BS['140']}",
          f"{{c}}35/{{c}}10*'{CP}'!$O$30")
    _label(w, FS, 67, "Tài sản ngắn hạn khác (mã 150)")
    _both(w, 67, f"'{RD}'!{{c}}{BS['150']}",
          f"{{c}}{R_REV}*'{CP}'!$O$32")
    _label(w, FS, 68, "TÀI SẢN NGẮN HẠN (mã 100)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}68", f"SUM({c}63:{c}67)")

    _label(w, FS, 69, "Tài sản cố định (mã 220)")
    _both(w, 69, f"'{RD}'!{{c}}{BS['220']}", "{c}171")
    _label(w, FS, 70, "Đầu tư tài chính dài hạn (mã 250)")
    _both(w, 70, f"'{RD}'!{{c}}{BS['250']}", "{p}70")
    _label(w, FS, 71, "Tài sản dài hạn khác "
                      "(mã 210 + 230 + 240 + 260)")
    _both(w, 71,
          f"'{RD}'!{{c}}{BS['210']}+'{RD}'!{{c}}{BS['230']}"
          f"+'{RD}'!{{c}}{BS['240']}+'{RD}'!{{c}}{BS['260']}",
          "{p}71")
    _clear_row(w, FS, 72)
    w.clear(FS, "B72")
    _label(w, FS, 73, "TỔNG CỘNG TÀI SẢN (mã 270)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}73", f"SUM({c}68:{c}72)")

    _label(w, FS, 75, "NGUỒN VỐN")
    _label(w, FS, 76, "Nợ phải trả:")
    _label(w, FS, 77, "Phải trả người bán ngắn hạn (mã 311)")
    _both(w, 77, f"'{RD}'!{{c}}{BS['311']}",
          f"{{c}}35/{{c}}10*'{CP}'!$N$30")
    _label(w, FS, 78, "Vay và nợ thuê tài chính ngắn hạn (mã 320)")
    _both(w, 78, f"'{RD}'!{{c}}{BS['320']}", "{p}78")
    _label(w, FS, 79, "Nợ ngắn hạn khác")
    _both(w, 79,
          f"'{RD}'!{{c}}{BS['310']}-'{RD}'!{{c}}{BS['311']}"
          f"-'{RD}'!{{c}}{BS['320']}",
          f"{{c}}{R_REV}*'{CP}'!$O$33")
    _label(w, FS, 80, "NỢ NGẮN HẠN (mã 310)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}80", f"SUM({c}77:{c}79)")
    _label(w, FS, 81, "Vay và nợ thuê tài chính dài hạn (mã 338)")
    _both(w, 81, f"'{RD}'!{{c}}{BS['338']}", "{c}316")
    _label(w, FS, 82, "Nợ dài hạn khác")
    _both(w, 82, f"'{RD}'!{{c}}{BS['330']}-'{RD}'!{{c}}{BS['338']}",
          "{p}82")
    _clear_row(w, FS, 83)
    w.clear(FS, "B83")
    _label(w, FS, 84, "NỢ PHẢI TRẢ (mã 300)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}84", f"SUM({c}80:{c}83)")

    _label(w, FS, 85, "Vốn chủ sở hữu:")
    _label(w, FS, 86, "Vốn góp của chủ sở hữu (mã 411)")
    _both(w, 86, f"'{RD}'!{{c}}{BS['411']}", "{p}86+{c}295")
    _label(w, FS, 87, "Quỹ đầu tư phát triển (mã 418)")
    _both(w, 87, f"'{RD}'!{{c}}{BS['418']}", "{p}87")
    _label(w, FS, 88, "Lợi nhuận sau thuế chưa phân phối (mã 421)")
    _both(w, 88, f"'{RD}'!{{c}}{BS['421']}", "{p}88+{c}51+{c}129")
    _label(w, FS, 89, "Lợi ích cổ đông không kiểm soát (mã 429)")
    _both(w, 89, f"'{RD}'!{{c}}{BS['429']}", "{p}89")
    _label(w, FS, 90, "Vốn chủ sở hữu khác (mã 410 + 430 − các mục trên)")
    _both(w, 90,
          f"'{RD}'!{{c}}{BS['400']}-'{RD}'!{{c}}{BS['411']}"
          f"-'{RD}'!{{c}}{BS['418']}-'{RD}'!{{c}}{BS['421']}"
          f"-'{RD}'!{{c}}{BS['429']}",
          "{p}90")
    _label(w, FS, 91, "VỐN CHỦ SỞ HỮU (mã 400)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}91", f"SUM({c}86:{c}90)")
    _label(w, FS, 92, "TỔNG CỘNG NGUỒN VỐN (mã 440)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}92", f"{c}91+{c}84")
    _label(w, FS, R_CHECK, "Kiểm tra: nguồn vốn − tài sản")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}{R_CHECK}", f"{c}92-{c}73")


def build_cash_flow(w: WorkbookPatch) -> None:
    _label(w, FS, 97, "LƯU CHUYỂN TIỀN TỆ")
    _label(w, FS, 100, "Tiền và tương đương tiền đầu kỳ (mã 60)")
    _both(w, 100, f"'{RD}'!{{c}}{CF['60']}", f"{{p}}{R_CASH_END}")

    _label(w, FS, 102, "Hoạt động kinh doanh:")
    _label(w, FS, 103, "Lợi nhuận sau thuế (mã 60)")
    _both(w, 103, f"'{RD}'!{{c}}{IS['60']}", "{c}51")
    _clear_row(w, FS, 104)
    w.clear(FS, "B104")
    _label(w, FS, 105, "Khấu hao TSCĐ và BĐS đầu tư")
    _both(w, 105, f"'{RD}'!{{c}}{CF['02']}", "-{c}169")
    _clear_row(w, FS, 106)
    w.clear(FS, "B106")
    # Not a measurement: what is left of reported CFO once the lines above
    # and the working capital lines below are taken out. A large residual
    # means one of those lines is wrong, so it is shown, not buried.
    _label(w, FS, 107, "Điều chỉnh khác (số dư để khớp CFO công bố)")
    _hist(w, 107,
          f"'{RD}'!{{c}}{CF['20']}-{{c}}103-{{c}}105"
          "-SUM({c}110:{c}114)")
    _fcst(w, 107, "0")

    _label(w, FS, 109, "Thay đổi vốn lưu động:")
    _label(w, FS, 110, "Hàng tồn kho")
    _label(w, FS, 111, "Các khoản phải thu ngắn hạn")
    _label(w, FS, 112, "Phải trả người bán ngắn hạn")
    _label(w, FS, 113, "Nợ ngắn hạn khác")
    _label(w, FS, 114, "Tài sản ngắn hạn khác")
    for row, expr in ((110, "-({c}66-{p}66)"), (111, "-({c}65-{p}65)"),
                      (112, "{c}77-{p}77"), (113, "{c}79-{p}79"),
                      (114, "-({c}67-{p}67)")):
        for c in HIST[1:]:
            w.set_formula(FS, f"{c}{row}",
                          expr.format(c=c, p=prev_col(c)))
        w.clear(FS, f"{HIST[0]}{row}")   # no year before the first one
        _fcst(w, row, expr)
    _label(w, FS, 115, "Lưu chuyển tiền thuần từ HĐKD (mã 20)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}115", f"SUM({c}103:{c}114)")

    _label(w, FS, 117, "Hoạt động đầu tư:")
    _label(w, FS, 118, "Tiền chi mua sắm, xây dựng TSCĐ (mã 21)")
    _both(w, 118, f"'{RD}'!{{c}}{CF['21']}", "-{c}150")
    _label(w, FS, 119, "Tiền thu từ thanh lý, nhượng bán TSCĐ (mã 22)")
    _both(w, 119, f"'{RD}'!{{c}}{CF['22']}", "0")
    _label(w, FS, 120, "Đầu tư khác (số dư để khớp CFI công bố)")
    _hist(w, 120, f"'{RD}'!{{c}}{CF['30']}-{{c}}118-{{c}}119")
    _fcst(w, 120, f"-({{c}}64-{{p}}64)")
    _clear_row(w, FS, 121)
    w.clear(FS, "B121")
    _label(w, FS, 122, "Lưu chuyển tiền thuần từ HĐ đầu tư (mã 30)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}122", f"SUM({c}118:{c}121)")

    _label(w, FS, 124, "Hoạt động tài chính:")
    _label(w, FS, 125, "Vay và trả nợ gốc vay (mã 33 + 34)")
    _both(w, 125, f"'{RD}'!{{c}}{CF['33']}+'{RD}'!{{c}}{CF['34']}",
          "{c}317")
    _label(w, FS, 126, "Tiền thu từ phát hành cổ phiếu (mã 31)")
    _both(w, 126, f"'{RD}'!{{c}}{CF['31']}", "{c}295")
    _label(w, FS, 127, "Tài chính khác (số dư để khớp CFF công bố)")
    _hist(w, 127,
          f"'{RD}'!{{c}}{CF['40']}-{{c}}125-{{c}}126-{{c}}129")
    _fcst(w, 127, "0")
    _clear_row(w, FS, 128)
    w.clear(FS, "B128")
    _label(w, FS, 129, "Cổ tức, lợi nhuận đã trả cho chủ sở hữu (mã 36)")
    _both(w, 129, f"'{RD}'!{{c}}{CF['36']}",
          f"-{{c}}51*'{RD}'!$O$37")
    _label(w, FS, 130, "Lưu chuyển tiền thuần từ HĐ tài chính (mã 40)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}130", f"SUM({c}125:{c}129)")

    _label(w, FS, 132, "Ảnh hưởng của thay đổi tỷ giá (mã 61)")
    _both(w, 132, f"'{RD}'!{{c}}{CF['61']}", "0")
    _label(w, FS, 133, "Lưu chuyển tiền thuần trong kỳ (mã 50)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}133",
                      f"{c}115+{c}122+{c}130+{c}132")
    _label(w, FS, R_CASH_END,
           "Tiền và tương đương tiền cuối kỳ (mã 70)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}{R_CASH_END}", f"{c}100+{c}133")
    # A real check: the left side is built up line by line, the right side
    # is what the filing reports. Nothing here is a plug.
    _label(w, FS, 136, "Kiểm tra: tiền cuối kỳ − mã 70 công bố")
    _hist(w, 136, f"{{c}}{R_CASH_END}-'{RD}'!{{c}}{CF['70']}")
    _label(w, FS, 137, "Kiểm tra: tiền cuối kỳ − mã 110 bảng cân đối")
    _hist(w, 137, f"{{c}}{R_CASH_END}-'{RD}'!{{c}}{BS['110']}")


def build_schedules(w: WorkbookPatch) -> None:
    _label(w, FS, 138, "Phụ lục")
    for r in range(141, 146):          # restricted cash: no VAS counterpart
        _clear_row(w, FS, r)
        w.clear(FS, f"B{r}")

    _label(w, FS, 147, "Phụ lục tài sản cố định")
    _label(w, FS, 149, "Nguyên giá ròng đầu kỳ")
    _hist(w, 149, f"'{RD}'!{{c}}{BS['220']}")
    _fcst(w, 149, "{p}171")
    _label(w, FS, 150, "Cộng: CapEx")
    # Historically capex is what the cash flow statement reports; in the
    # forecast it is a share of revenue. Taking it from row 118 in both
    # directions is what made the whole forecast block circular, because
    # row 118 already reads back from here.
    _hist(w, 150, "-{c}118-{c}119")
    _fcst(w, 150, f"{{c}}{R_REV}*'{CP}'!$O$38")
    _clear_row(w, FS, 151)
    w.clear(FS, "B151")

    # The model's original straight-line depreciation triangle needed a
    # vintage per forecast year and fifteen rows to hold them. The ratio of
    # depreciation to opening fixed assets is already measured from the
    # filings on the Raw Data sheet, so one row replaces the fifteen.
    for r in range(152, 169):
        _clear_row(w, FS, r)
        w.clear(FS, f"B{r}")
        w.clear(FS, f"A{r}")
    _label(w, FS, 169, "Trừ: khấu hao trong kỳ")
    _hist(w, 169, "-{c}105")
    _fcst(w, 169, f"-{{c}}149*'{CP}'!$O$40")
    _label(w, FS, 171, "Nguyên giá ròng cuối kỳ")
    _hist(w, 171, f"'{RD}'!{{c}}{BS['220']}")
    _fcst(w, 171, "SUM({c}149:{c}150)+{c}169")

    # VAS 06 keeps an operating lease off the balance sheet. There is no
    # right-of-use asset to depreciate and no lease liability to unwind,
    # so both schedules go rather than sit at zero pretending to apply.
    _label(w, FS, 174, "(Phụ lục thuê tài chính / thuê hoạt động đã bỏ: "
                       "VAS 06 không ghi nhận tài sản quyền sử dụng)")
    for r in range(176, 286):
        _clear_row(w, FS, r)
        w.clear(FS, f"B{r}")
        w.clear(FS, f"A{r}")
    _label(w, FS, 199, "Tổng tài sản cố định")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}199", f"{c}171")

    _label(w, FS, 287, "Phụ lục nhu cầu vốn bổ sung")
    # The original wrote a quoted "0" as the fallback of these two, so a
    # year needing no capital handed a text value to the balance sheet and
    # every total downstream became #VALUE!.
    _label(w, FS, 294, "Vốn bổ sung - nợ vay")
    _label(w, FS, 295, "Vốn bổ sung - vốn góp")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}294",
                      f"IFERROR({c}$292*-'{CP}'!$G$46,0)")
        w.set_formula(FS, f"{c}295",
                      f"IFERROR({c}$292*-'{CP}'!$G$47,0)")
        w.set_formula(FS, f"{c}296",
                      f"IFERROR({c}295/Dashboard!$U$8,0)")

    _label(w, FS, 299, "Phụ lục nợ vay dài hạn hiện hữu")
    _label(w, FS, 301, "Số dư đầu kỳ")
    for c in HIST[1:] + FCST:
        w.set_formula(FS, f"{c}301", f"{prev_col(c)}304")
    w.clear(FS, f"{HIST[0]}301")
    _label(w, FS, 302, "Cộng: vay gốc nhận được (mã 33)")
    _hist(w, 302, f"'{RD}'!{{c}}{CF['33']}")
    _fcst(w, 302, "0")
    _label(w, FS, 303, "Trừ: trả nợ gốc vay (mã 34)")
    _hist(w, 303, f"'{RD}'!{{c}}{CF['34']}")
    _fcst(w, 303, "0")
    # Historically the closing balance is what the balance sheet reports,
    # not what the two movement lines above happen to add up to. In the
    # forecast no new borrowing is assumed: debt stays flat and any funding
    # gap is met by the capital requirements schedule instead.
    _label(w, FS, 304, "Số dư cuối kỳ")
    _hist(w, 304, f"'{RD}'!{{c}}{BS['338']}")
    _fcst(w, 304, "SUM({c}301:{c}303)")
    _label(w, FS, 319, "Vay dài hạn trên bảng cân đối (mã 338)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}319", f"{c}81")
    _label(w, FS, 320, "Vay ngắn hạn (mã 320)")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}320", f"{c}78")
    _label(w, FS, 321, "Tổng nợ vay")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}321", f"SUM({c}319:{c}320)")
    _label(w, FS, 323, "Chi phí lãi vay (mã 23)")
    _hist(w, 323, f"'{RD}'!{{c}}{IS['23']}")
    _fcst(w, 323, f"'{CP}'!$F$22*AVERAGE({{p}}321:{{c}}321)")
    _label(w, FS, 324, "Lãi suất ngầm định trên nợ vay")
    for c in HIST[1:] + FCST:
        w.set_formula(FS, f"{c}324",
                      f"IFERROR({c}323/AVERAGE({prev_col(c)}321:{c}321),0)")
    w.clear(FS, f"{HIST[0]}324")


def build_ebitda_and_fcff(w: WorkbookPatch) -> None:
    _label(w, FS, 327, "EBITDA và dòng tiền tự do")
    _label(w, FS, 329, "EBIT")
    _label(w, FS, 330, "Khấu hao")
    _label(w, FS, 331, "EBITDA")
    _clear_row(w, FS, 333)
    w.clear(FS, "B333")
    _label(w, FS, 334, "EBITDA")
    _label(w, FS, 337, "Lợi nhuận hoạt động")
    _label(w, FS, 338, "Trừ: thuế trên lợi nhuận hoạt động")
    _label(w, FS, 339, "NOPAT")
    _label(w, FS, 340, "Cộng: khấu hao")
    _label(w, FS, 343, "Trừ: CapEx tiền mặt")
    _label(w, FS, 344, "Cộng: thay đổi vốn lưu động")
    _label(w, FS, 345, "Dòng tiền tự do của doanh nghiệp (FCFF)")
    for r in (341, 342):
        _clear_row(w, FS, r)
        w.clear(FS, f"B{r}")
    for c in ALL_COLS:
        w.set_formula(FS, f"{c}329", f"{c}43")
        w.set_formula(FS, f"{c}330", f"{c}105")
        w.set_formula(FS, f"{c}331", f"SUM({c}329:{c}330)")
        w.set_formula(FS, f"{c}334", f"SUM({c}331:{c}333)")
        w.set_formula(FS, f"{c}337", f"{c}43")
        w.set_formula(FS, f"{c}338", f"_TaxRate*-{c}337")
        w.set_formula(FS, f"{c}339", f"SUM({c}337:{c}338)")
        w.set_formula(FS, f"{c}340", f"{c}105")
        w.set_formula(FS, f"{c}343", f"{c}118+{c}119")
        w.set_formula(FS, f"{c}344", f"SUM({c}110:{c}114)")
        w.set_formula(FS, f"{c}345", f"SUM({c}339:{c}344)")


def build_control_panel(w: WorkbookPatch) -> None:
    _label(w, CP, 2, "Giả định và đầu vào", col="A")
    _label(w, CP, 3, "Đơn vị: triệu đồng, trừ khi ghi chú khác", col="A")
    w.set_value(CP, "B10", "Doanh nghiệp")
    w.set_value(CP, "F10", "(nhập tên doanh nghiệp)")
    w.set_value(CP, "B11", "Ngày định giá")
    w.set_value(CP, "B13", "Năm tài chính gần nhất trước ngày định giá")
    w.set_value(CP, "B14", "Năm tài chính kế tiếp")
    w.set_value(CP, "B16", "Làm tròn")
    w.set_value(CP, "B19", "Giả định định giá")
    w.set_value(CP, "B21", "Thuế suất hiệu dụng bình quân 5 năm")
    w.set_formula(CP, "F21", f"IFERROR('{RD}'!O23,0.2)")
    w.set_value(CP, "B22", "Lãi suất vay")
    w.set_formula(CP, "F22", f"IFERROR(AVERAGE('{FS}'!D324:G324),0.08)")

    w.set_value(CP, "I5", "Giả định kết quả kinh doanh")
    w.set_value(CP, "I7", "Giả định doanh thu")
    w.set_value(CP, "I13", "Giả định chi phí (% doanh thu thuần)")
    for cp_row, rd_row, label in (
            (14, 17, "Giá vốn hàng bán"),
            (16, 18, "Chi phí bán hàng"),
            (17, 19, "Chi phí quản lý doanh nghiệp"),
            (18, 20, "Doanh thu hoạt động tài chính"),
            (19, 21, "Chi phí tài chính")):
        w.set_value(CP, f"I{cp_row}", label)
        w.set_formula(CP, f"O{cp_row}", f"'{RD}'!O{rd_row}")
    for r in (20, 22, 23):
        w.clear(CP, f"I{r}")
        w.clear(CP, f"O{r}")

    w.set_value(CP, "I25", "Giả định bảng cân đối kế toán")
    w.set_value(CP, "I27", "Vốn lưu động")
    w.set_value(CP, "M28", "Phải thu")
    w.set_value(CP, "N28", "Phải trả")
    w.set_value(CP, "M29", "(ngày)")
    w.set_value(CP, "N29", "(ngày)")
    w.set_value(CP, "O29", "Tồn kho (ngày)")
    w.set_value(CP, "I30", "Số ngày quay vòng")
    w.set_formula(CP, "M30", f"'{RD}'!O27")
    w.set_formula(CP, "N30", f"'{RD}'!O29")
    w.set_formula(CP, "O30", f"'{RD}'!O26")
    w.set_value(CP, "I32", "Tài sản ngắn hạn khác (% doanh thu thuần)")
    w.set_formula(CP, "O32", f"'{RD}'!O30")
    w.set_value(CP, "I33", "Nợ ngắn hạn khác (% doanh thu thuần)")
    w.set_formula(CP, "O33", f"'{RD}'!O31")
    w.set_value(CP, "I34", "Tăng trưởng đầu tư tài chính ngắn hạn")
    w.set_formula(CP, "O34", f"'{RD}'!O36")

    w.set_value(CP, "I37", "Tài sản cố định")
    w.set_value(CP, "I38", "CapEx (% doanh thu thuần)")
    w.set_formula(CP, "O38", f"'{RD}'!O33")
    w.set_value(CP, "I39", "Thời gian khấu hao bình quân (năm)")
    w.set_formula(CP, "O39", f"IFERROR(1/'{RD}'!O34,10)")
    w.set_value(CP, "I40", "Khấu hao (% TSCĐ đầu kỳ)")
    w.set_formula(CP, "O40", f"'{RD}'!O34")

    # The lease assumption block goes with the lease schedules.
    for r in range(42, 48):
        for col in ("I", "M", "N", "O"):
            w.clear(CP, f"{col}{r}")
    w.set_value(CP, "I42", "(Khối giả định thuê đã bỏ - xem Phụ lục)")

    w.set_value(CP, "B44", "Giả định huy động vốn")
    w.set_value(CP, "B46", "Huy động thêm - tỷ trọng nợ vay")
    w.set_value(CP, "B47", "Huy động thêm - tỷ trọng vốn góp")
    w.set_value(CP, "B49", "Kỳ hạn nợ vay bổ sung (năm)")
    w.set_value(CP, "B24", "Giả định DCF")
    w.set_value(CP, "B25", "Phương pháp giá trị cuối kỳ")
    w.set_value(CP, "B26", "Bội số EV/EBITDA cuối kỳ")
    w.set_value(CP, "B27", "Tốc độ tăng trưởng dài hạn")
    w.set_value(CP, "B28", "WACC")
    w.set_value(CP, "B30", "Giả định WACC")
    w.set_value(CP, "B31", "Lãi suất phi rủi ro")
    w.set_value(CP, "B32", "Phần bù rủi ro vốn cổ phần")
    w.set_value(CP, "B33", "Phần bù rủi ro quốc gia")
    w.set_value(CP, "B34", "Phần bù quy mô")
    w.set_value(CP, "B35", "Phần bù rủi ro riêng của doanh nghiệp")
    w.set_value(CP, "B36", "Cơ cấu vốn mục tiêu (% nợ vay)")
    w.set_value(CP, "B38", "Ngưỡng khuyến nghị so với giá hiện tại")
    w.set_value(CP, "B39", "Bán")
    w.set_value(CP, "B40", "Nắm giữ")
    w.set_value(CP, "B41", "Mua")
    w.set_value(CP, "B7", "Kịch bản")
    w.set_value(CP, "Q7", "Chọn kịch bản")
    w.set_value(CP, "R8", "Theo tăng trưởng lịch sử")
    w.set_value(CP, "R9", "Kịch bản cơ sở cộng 25%")
    w.set_value(CP, "R10", "Kịch bản cơ sở trừ 25%")
    w.set_value(CP, "R11", "Không tăng trưởng")
    w.set_value(CP, "I9", "Hệ số giảm dần tăng trưởng")
    w.set_value(CP, "I10", "Kịch bản cao (cộng % so với cơ sở)")
    w.set_value(CP, "I11", "Kịch bản thấp (trừ % so với cơ sở)")


def build_scenarios(w: WorkbookPatch) -> None:
    w.set_value(SC, "A2", "Kịch bản dự phóng")
    w.set_value(SC, "A3", "Đơn vị: triệu đồng")
    for block_row, title in ((13, "Tăng trưởng doanh thu thuần"),
                             (23, "Tăng trưởng doanh thu thuần"),
                             (33, "Tăng trưởng doanh thu thuần"),
                             (43, "Tăng trưởng doanh thu thuần"),
                             (53, "Tăng trưởng doanh thu thuần")):
        w.set_value(SC, f"B{block_row}", title)
    # one revenue line per scenario instead of six segments
    for first in (14, 24, 34, 44, 54):
        w.set_value(SC, f"B{first}", "Doanh thu thuần")
        for r in range(first + 1, first + 6):
            w.set_value(SC, f"B{r}", None)
            for c in ALL_COLS:
                w.clear(SC, f"{c}{r}")
    w.set_formula(SC, "H24", f"'{RD}'!O16")
    w.set_value(SC, "B20", "Tổng doanh thu thuần")
    w.set_value(SC, "B12", "KỊCH BẢN ĐANG DÙNG")
    w.set_value(SC, "B22", "KỊCH BẢN CƠ SỞ")


def build_sotp(w: WorkbookPatch) -> None:
    w.set_value("SOTP", "A2",
                "Định giá từng phần (tùy chọn - chỉ chạy khi đã nhập "
                "doanh thu theo mảng ở Financial Statements dòng 26-31)")
    for i, (head, item) in enumerate(
            ((9, 10), (14, 15), (18, 19), (22, 23), (26, 27))):
        w.set_value("SOTP", f"B{head}", f"Mảng {i + 1}")
        w.set_value("SOTP", f"B{item}", f"Doanh thu mảng {i + 1}")
    w.set_value("SOTP", "B11", None)
    w.set_value("SOTP", "B12", "Tổng mảng 1")
    w.set_value("SOTP", "B16", "Tổng mảng 2")
    w.set_value("SOTP", "B20", "Tổng mảng 3")
    w.set_value("SOTP", "B24", "Tổng mảng 4")
    w.set_value("SOTP", "B28", "Tổng mảng 5")
    w.set_value("SOTP", "B31", "Tổng giá trị doanh nghiệp ngầm định")
    w.set_value("SOTP", "B33", "Trừ: nợ vay ròng")
    w.set_value("SOTP", "B34", "Giá trị vốn chủ sở hữu ngầm định")
    w.set_value("SOTP", "B36", "Số cổ phiếu pha loãng (triệu cp)")
    w.set_value("SOTP", "B37", "Giá trị mỗi cổ phiếu (đồng)")
    # With the segment memo empty these divide by zero, which is the
    # correct answer to "what multiple does nothing imply" but an ugly one.
    for row in (31, 48):
        for col, num in (("F", "J"), ("G", "K"), ("H", "L")):
            w.set_formula("SOTP", f"{col}{row}",
                          f"IFERROR({num}{row}/D{row},\"\")")


def build_market_sheets(w: WorkbookPatch) -> None:
    """Take Amazon's market data out.

    These sheets are not accounting, so nothing here is wrong in a VAS
    sense - which is exactly the danger. Left alone, the template would
    value a Vietnamese company against Walmart, Alphabet and Netflix, put
    twenty-five American brokers' price targets in its consensus range,
    and read a 52-week band off Amazon's share price, all without saying
    so. The structure is kept and the numbers go.
    """
    # -- Comps: row 10 is the subject company, and it can be computed
    w.set_value("Comps", "A2", "Bội số so sánh (nhập tay các doanh nghiệp "
                               "cùng ngành)")
    w.set_formula("Comps", "B10", "_CompanyName")
    w.set_formula("Comps", "D10", f"'{RD}'!{LAST_HIST}{V.PRICE_ROW}")
    w.set_formula("Comps", "E10", f"'{FS}'!{LAST_HIST}56")
    w.set_formula("Comps", "G10", f"'{FS}'!{LAST_HIST}321")
    w.set_formula("Comps", "H10", f"'{FS}'!{LAST_HIST}63")
    w.set_formula("Comps", "I10", "G10-H10")
    w.set_value("Comps", "D8", "[đồng/cp]")
    w.set_value("Comps", "E8", "[triệu cp]")
    for col in ("F8", "I8", "J8"):
        w.set_value("Comps", col, "[triệu đồng]")
    peer_rows = list(range(13, 17)) + list(range(23, 26)) + \
        list(range(32, 35)) + list(range(41, 45)) + list(range(51, 55))
    for r in peer_rows:
        for col in ("B", "D", "E", "G", "H"):
            w.clear("Comps", f"{col}{r}")
        w.set_formula("Comps", f"I{r}", f"G{r}-H{r}")
    for i, r in enumerate((12, 22, 31, 40, 50), start=1):
        w.set_value("Comps", f"B{r}", f"Nhóm so sánh {i}")
    for i, r in enumerate((17, 26, 35, 45, 55), start=1):
        w.set_value("Comps", f"B{r}", f"Bình quân: nhóm {i}")
    for i, r in enumerate((18, 27, 36, 46, 56), start=1):
        w.set_value("Comps", f"B{r}", f"Trung vị: nhóm {i}")
    for i, r in enumerate((19, 28, 37, 47, 57), start=1):
        w.set_value("Comps", f"B{r}", f"Thấp nhất: nhóm {i}")
    for i, r in enumerate((20, 29, 38, 48, 58), start=1):
        w.set_value("Comps", f"B{r}", f"Cao nhất: nhóm {i}")
    w.set_value("Comps", "B62", "Nguồn: (nhập)")

    # -- Precedent transactions
    w.set_value("Precedents", "A2",
                "Giao dịch M&A tiền lệ (nhập tay)")
    for r in range(10, 20):
        for col in ("C", "D", "E", "F", "G", "H", "I"):
            w.clear("Precedents", f"{col}{r}")

    # -- Analyst consensus
    w.set_value("Consensus", "A2",
                "Khuyến nghị của công ty chứng khoán (nhập tay)")
    for r in range(7, 32):
        for col in ("B", "C", "D", "E", "F"):
            w.clear("Consensus", f"{col}{r}")

    # -- Market size
    w.set_value("Market Size", "A2", "Quy mô thị trường (nhập tay)")
    for i, r in enumerate(range(8, 12), start=1):
        w.set_value("Market Size", f"B{r}", f"Mảng {i}")
        w.set_value("Market Size", f"B{r + 6}", f"Mảng {i}")
        for col in "CDEFGHIJ":
            w.clear("Market Size", f"{col}{r}")
    w.set_value("Market Size", "B24", "(nhập nguồn)")

    # -- Macro
    w.set_value("Macro", "A2", "Giả định vĩ mô (nhập tay)")
    w.set_value("Macro", "B11", "Tỷ lệ thất nghiệp")
    w.set_value("Macro", "B12", "Tiêu dùng hộ gia đình")
    for r in range(9, 13):
        for col in "CDEF":
            w.clear("Macro", f"{col}{r}")
    for r in (15, 16, 17):
        w.clear("Macro", f"B{r}")

    # -- Share price history feeding the 52-week band
    w.set_value("Share Price", "A2",
                "Lịch sử giá cổ phiếu (dán vào cột B: ngày, cột C: giá)")
    w.set_value("Share Price", "B6", "Giá cao nhất 52 tuần")
    w.set_value("Share Price", "B7", "Giá thấp nhất 52 tuần")
    w.set_value("Share Price", "B8", "Giá bình quân 52 tuần")
    w.clear_rows("Share Price", 11, 1382, cols=["B", "C"])


def main(src: str, dest: str) -> None:
    w = WorkbookPatch(src)
    build_raw_data(w)
    build_income_statement(w)
    build_balance_sheet(w)
    build_cash_flow(w)
    build_schedules(w)
    build_ebitda_and_fcff(w)
    build_control_panel(w)
    build_scenarios(w)
    build_sotp(w)
    build_market_sheets(w)
    w.save(dest)
    print(f"wrote {dest}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
