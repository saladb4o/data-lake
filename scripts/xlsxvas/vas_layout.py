"""Where each TT200 line lives on the VAS Raw Data sheet.

One module, one job: say what row a code is on. Every other part of the
build asks this instead of writing a row number of its own, because a row
number written twice is a row number that will drift.

Codes follow TT200 as the repository's own tables in
services/bctc_pdf_parser.py record them, with one exception noted at
EQUITY_SPLIT below, which the balance sheets read in CI settle directly.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional

FIRST_HIST_COL = "C"   # five historical years, C..G
LAST_HIST_COL = "G"
HIST_COLS = ["C", "D", "E", "F", "G"]
# The forecast runs eleven years, H through R. The DCF reads the last
# four of them directly, so a build that stopped at N left four years
# of the valuation reading rows that no longer existed.
FCST_COLS = ["H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R"]


class Line(NamedTuple):
    row: int
    code: Optional[str]      # TT200 item code, as printed on the filing
    label: str
    formula: Optional[str]   # a column template, "{c}" for the column letter
    kind: str                # input | derived | check | header | note


def _L(row, code, label, formula=None, kind="input") -> Line:
    return Line(row, code, label, formula, kind)


# -- Income statement, Mẫu số B 02-DN ------------------------------------
INCOME: List[Line] = [
    _L(7, None, "KẾT QUẢ HOẠT ĐỘNG KINH DOANH (Mẫu số B 02-DN)",
       kind="header"),
    _L(8, "01", "Doanh thu bán hàng và cung cấp dịch vụ"),
    _L(9, "02", "Các khoản giảm trừ doanh thu"),
    _L(10, "10", "Doanh thu thuần về bán hàng và cung cấp dịch vụ",
       "{c}8-{c}9", "derived"),
    _L(11, "11", "Giá vốn hàng bán"),
    _L(12, "20", "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ",
       "{c}10-{c}11", "derived"),
    _L(13, "21", "Doanh thu hoạt động tài chính"),
    _L(14, "22", "Chi phí tài chính"),
    _L(15, "23", "Trong đó: Chi phí lãi vay"),
    _L(16, "25", "Chi phí bán hàng"),
    _L(17, "26", "Chi phí quản lý doanh nghiệp"),
    _L(18, "30", "Lợi nhuận thuần từ hoạt động kinh doanh",
       "{c}12+{c}13-{c}14-{c}16-{c}17", "derived"),
    _L(19, "31", "Thu nhập khác"),
    _L(20, "32", "Chi phí khác"),
    _L(21, "40", "Lợi nhuận khác", "{c}19-{c}20", "derived"),
    _L(22, "50", "Tổng lợi nhuận kế toán trước thuế",
       "{c}18+{c}21", "derived"),
    _L(23, "51", "Chi phí thuế TNDN hiện hành"),
    _L(24, "52", "Chi phí thuế TNDN hoãn lại"),
    _L(25, "60", "Lợi nhuận sau thuế thu nhập doanh nghiệp",
       "{c}22-{c}23-{c}24", "derived"),
    _L(26, "61", "Lợi nhuận sau thuế của cổ đông công ty mẹ"),
    _L(27, "62", "Lợi nhuận sau thuế của cổ đông không kiểm soát"),
    _L(28, "70", "Lãi cơ bản trên cổ phiếu (đồng)"),
    _L(29, None, "Số cổ phiếu bình quân lưu hành (triệu cp)"),
    _L(30, None, "Số cổ phiếu đang lưu hành cuối kỳ (triệu cp)"),
]

# -- Balance sheet, Mẫu số B 01-DN ---------------------------------------
#
# The compositions here are not recalled, they are the ones BSR's own
# consolidated balance sheet prints about itself and that CI read back
# whole: (100=110+120+130+140+150), (400=410+430), (440=300+400).
BALANCE: List[Line] = [
    _L(32, None, "BẢNG CÂN ĐỐI KẾ TOÁN (Mẫu số B 01-DN)", kind="header"),
    _L(33, "110", "Tiền và các khoản tương đương tiền"),
    _L(34, "120", "Đầu tư tài chính ngắn hạn"),
    _L(35, "130", "Các khoản phải thu ngắn hạn"),
    _L(36, "140", "Hàng tồn kho"),
    _L(37, "150", "Tài sản ngắn hạn khác"),
    _L(38, "100", "TÀI SẢN NGẮN HẠN"),
    _L(39, "210", "Các khoản phải thu dài hạn"),
    _L(40, "220", "Tài sản cố định"),
    _L(41, "230", "Bất động sản đầu tư"),
    _L(42, "240", "Tài sản dở dang dài hạn"),
    _L(43, "250", "Đầu tư tài chính dài hạn"),
    _L(44, "260", "Tài sản dài hạn khác"),
    _L(45, "200", "TÀI SẢN DÀI HẠN"),
    _L(46, "270", "TỔNG CỘNG TÀI SẢN"),
    _L(47, None, "Kiểm tra: 100 + 200 − 270",
       "{c}38+{c}45-{c}46", "check"),
    _L(48, "311", "Phải trả người bán ngắn hạn"),
    _L(49, "312", "Người mua trả tiền trước ngắn hạn"),
    _L(50, "320", "Vay và nợ thuê tài chính ngắn hạn"),
    _L(51, "310", "Nợ ngắn hạn"),
    _L(52, "338", "Vay và nợ thuê tài chính dài hạn"),
    _L(53, "330", "Nợ dài hạn"),
    _L(54, "300", "NỢ PHẢI TRẢ"),
    _L(55, None, "Kiểm tra: 310 + 330 − 300",
       "{c}51+{c}53-{c}54", "check"),
    _L(56, "411", "Vốn góp của chủ sở hữu"),
    _L(57, "418", "Quỹ đầu tư phát triển"),
    _L(58, "421", "Lợi nhuận sau thuế chưa phân phối"),
    _L(59, "429", "Lợi ích cổ đông không kiểm soát"),
    _L(60, "410", "Vốn chủ sở hữu"),
    _L(61, "430", "Nguồn kinh phí và quỹ khác"),
    _L(62, "400", "VỐN CHỦ SỞ HỮU", "{c}60+{c}61", "derived"),
    _L(63, "440", "TỔNG CỘNG NGUỒN VỐN"),
    _L(64, None, "Kiểm tra: 300 + 400 − 440",
       "{c}54+{c}62-{c}63", "check"),
    _L(65, None, "Kiểm tra: 270 − 440", "{c}46-{c}63", "check"),
]

# -- Cash flow, Mẫu số B 03-DN (indirect) --------------------------------
CASHFLOW: List[Line] = [
    _L(67, None, "LƯU CHUYỂN TIỀN TỆ (Mẫu số B 03-DN, gián tiếp)",
       kind="header"),
    _L(68, "01", "Lợi nhuận trước thuế"),
    _L(69, "02", "Trong đó: Khấu hao TSCĐ và BĐS đầu tư"),
    _L(70, "20", "Lưu chuyển tiền thuần từ hoạt động kinh doanh (CFO)"),
    _L(71, "21", "Tiền chi mua sắm, xây dựng TSCĐ và TSDH khác (CapEx)"),
    _L(72, "22", "Tiền thu từ thanh lý, nhượng bán TSCĐ"),
    _L(73, "30", "Lưu chuyển tiền thuần từ hoạt động đầu tư (CFI)"),
    _L(74, "31", "Tiền thu từ phát hành cổ phiếu, nhận vốn góp"),
    _L(75, "33", "Tiền vay gốc nhận được"),
    _L(76, "34", "Tiền trả nợ gốc vay"),
    _L(77, "36", "Cổ tức, lợi nhuận đã trả cho chủ sở hữu"),
    _L(78, "40", "Lưu chuyển tiền thuần từ hoạt động tài chính (CFF)"),
    _L(79, "50", "Lưu chuyển tiền thuần trong kỳ",
       "{c}70+{c}73+{c}78", "derived"),
    _L(80, "60", "Tiền và tương đương tiền đầu kỳ"),
    _L(81, "61", "Ảnh hưởng của thay đổi tỷ giá hối đoái"),
    _L(82, "70", "Tiền và tương đương tiền cuối kỳ"),
    _L(83, None, "Kiểm tra: 50 + 60 + 61 − 70",
       "{c}79+{c}80+{c}81-{c}82", "check"),
    _L(84, None, "Kiểm tra: mã 70 − mã 110 (bảng cân đối)",
       "{c}82-{c}33", "check"),
]

MARKET: List[Line] = [
    _L(86, None, "THÔNG TIN THỊ TRƯỜNG", kind="header"),
    _L(87, None, "Giá cổ phiếu cuối kỳ (đồng)"),
    _L(88, None, "Cổ tức tiền mặt trên mỗi cổ phiếu (đồng)"),
]

ALL_LINES: List[Line] = INCOME + BALANCE + CASHFLOW + MARKET

# row lookup by TT200 code, per statement
IS_ROW: Dict[str, int] = {l.code: l.row for l in INCOME if l.code}
BS_ROW: Dict[str, int] = {l.code: l.row for l in BALANCE if l.code}
CF_ROW: Dict[str, int] = {l.code: l.row for l in CASHFLOW if l.code}

SHARES_AVG_ROW = 29
SHARES_END_ROW = 30
PRICE_ROW = 87
DPS_ROW = 88

LAST_ROW = 88

# The one place the equity split is asserted rather than read. TT200 numbers
# the two children of 400 as 410 and 430; which of 61 / 62 is the parent's
# share and which the minority's is recorded one way in this repository's
# code tables and the other way in some printings of Mẫu số B 02-DN/HN.
# Nothing in this repository is anchored to a filing on that point, so the
# template follows the repository's own tables and says so on its face.
EQUITY_SPLIT_UNVERIFIED = (
    "Mã 61/62: theo bảng mã của repo (61 = công ty mẹ, 62 = cổ đông "
    "không kiểm soát). Chưa đối chiếu với BCTC thật - kiểm tra trước "
    "khi dùng số phân bổ."
)
