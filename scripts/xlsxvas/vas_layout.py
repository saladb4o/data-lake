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
    _L(29, "71", "Lãi suy giảm trên cổ phiếu (đồng)"),
    _L(30, None, "Số cổ phiếu bình quân lưu hành (triệu cp)"),
    _L(31, None, "Số cổ phiếu đang lưu hành cuối kỳ (triệu cp)"),
]

# -- Balance sheet, Mẫu số B 01-DN ---------------------------------------
#
# The compositions here are not recalled, they are the ones BSR's own
# consolidated balance sheet prints about itself and that CI read back
# whole: (100=110+120+130+140+150), (400=410+430), (440=300+400).
BALANCE: List[Line] = [
    _L(33, None, "BẢNG CÂN ĐỐI KẾ TOÁN (Mẫu số B 01-DN)", kind="header"),
    _L(34, "110", "Tiền và các khoản tương đương tiền"),
    _L(35, "120", "Đầu tư tài chính ngắn hạn"),
    _L(36, "130", "Các khoản phải thu ngắn hạn"),
    _L(37, "140", "Hàng tồn kho"),
    _L(38, "150", "Tài sản ngắn hạn khác"),
    _L(39, "100", "TÀI SẢN NGẮN HẠN"),
    _L(40, "210", "Các khoản phải thu dài hạn"),
    _L(41, "220", "Tài sản cố định"),
    # The cost and the accumulated depreciation are printed on the filing,
    # so depreciation can be measured from them instead of assumed from a
    # ratio. Which code is which was settled by arithmetic, not by the
    # label - see tests/test_fixed_asset_codes_are_settled.py.
    _L(42, "221", "Tài sản cố định hữu hình"),
    _L(43, "222", "   Nguyên giá"),
    _L(44, "223", "   Giá trị hao mòn lũy kế (*)"),
    _L(45, None, "Kiểm tra: 221 − (222 + 223)",
       "{c}42-({c}43+{c}44)", "check"),
    # VAS capitalises finance leases; only the IFRS 16 right-of-use asset
    # for operating leases has no home in these forms.
    _L(46, "224", "Tài sản cố định thuê tài chính"),
    _L(47, "227", "Tài sản cố định vô hình"),
    _L(48, None, "Kiểm tra: 220 − (221 + 224 + 227)",
       "{c}41-({c}42+{c}46+{c}47)", "check"),
    _L(49, "230", "Bất động sản đầu tư"),
    _L(50, "240", "Tài sản dở dang dài hạn"),
    _L(51, "250", "Đầu tư tài chính dài hạn"),
    _L(52, "260", "Tài sản dài hạn khác"),
    _L(53, "200", "TÀI SẢN DÀI HẠN"),
    _L(54, "270", "TỔNG CỘNG TÀI SẢN"),
    _L(55, None, "Kiểm tra: 100 + 200 − 270",
       "{c}39+{c}53-{c}54", "check"),
    _L(56, "311", "Phải trả người bán ngắn hạn"),
    _L(57, "312", "Người mua trả tiền trước ngắn hạn"),
    _L(58, "320", "Vay và nợ thuê tài chính ngắn hạn"),
    _L(59, "310", "Nợ ngắn hạn"),
    _L(60, "338", "Vay và nợ thuê tài chính dài hạn"),
    _L(61, "330", "Nợ dài hạn"),
    _L(62, "300", "NỢ PHẢI TRẢ"),
    _L(63, None, "Kiểm tra: 310 + 330 − 300",
       "{c}59+{c}61-{c}62", "check"),
    _L(64, "411", "Vốn góp của chủ sở hữu"),
    _L(65, "418", "Quỹ đầu tư phát triển"),
    _L(66, "421", "Lợi nhuận sau thuế chưa phân phối"),
    _L(67, "429", "Lợi ích cổ đông không kiểm soát"),
    _L(68, "410", "Vốn chủ sở hữu"),
    _L(69, "430", "Nguồn kinh phí và quỹ khác"),
    _L(70, "400", "VỐN CHỦ SỞ HỮU", "{c}68+{c}69", "derived"),
    _L(71, "440", "TỔNG CỘNG NGUỒN VỐN"),
    _L(72, None, "Kiểm tra: 300 + 400 − 440",
       "{c}62+{c}70-{c}71", "check"),
    _L(73, None, "Kiểm tra: 270 − 440", "{c}54-{c}71", "check"),
]

# -- Cash flow, Mẫu số B 03-DN (indirect) --------------------------------
CASHFLOW: List[Line] = [
    _L(75, None, "LƯU CHUYỂN TIỀN TỆ (Mẫu số B 03-DN, gián tiếp)",
       kind="header"),
    _L(76, "01", "Lợi nhuận trước thuế"),
    _L(77, "02", "Trong đó: Khấu hao TSCĐ và BĐS đầu tư"),
    _L(78, "03", "Lợi nhuận kinh doanh trước thay đổi vốn lưu động"),
    _L(79, "20", "Lưu chuyển tiền thuần từ hoạt động kinh doanh (CFO)"),
    # Investing was three lines out of seven, so the total could only be
    # taken on trust. With the components present it is a sum that either
    # closes or does not.
    _L(80, "21", "Tiền chi mua sắm, xây dựng TSCĐ và TSDH khác (CapEx)"),
    _L(81, "22", "Tiền thu từ thanh lý, nhượng bán TSCĐ"),
    _L(82, "23", "Tiền chi cho vay, mua các công cụ nợ của đơn vị khác"),
    _L(83, "24", "Tiền thu hồi cho vay, bán lại công cụ nợ"),
    _L(84, "25", "Tiền chi đầu tư góp vốn vào đơn vị khác"),
    _L(85, "26", "Tiền thu hồi đầu tư góp vốn vào đơn vị khác"),
    _L(86, "27", "Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia"),
    _L(87, "30", "Lưu chuyển tiền thuần từ hoạt động đầu tư (CFI)"),
    _L(88, None, "Kiểm tra: 30 − (21+22+23+24+25+26+27)",
       "{c}87-SUM({c}80:{c}86)", "check"),
    _L(89, "31", "Tiền thu từ phát hành cổ phiếu, nhận vốn góp"),
    _L(90, "32", "Tiền trả lại vốn góp, mua lại cổ phiếu đã phát hành"),
    _L(91, "33", "Tiền vay gốc nhận được"),
    _L(92, "34", "Tiền trả nợ gốc vay"),
    _L(93, "35", "Tiền trả nợ gốc thuê tài chính"),
    _L(94, "36", "Cổ tức, lợi nhuận đã trả cho chủ sở hữu"),
    _L(95, "40", "Lưu chuyển tiền thuần từ hoạt động tài chính (CFF)"),
    _L(96, None, "Kiểm tra: 40 − (31+32+33+34+35+36)",
       "{c}95-SUM({c}89:{c}94)", "check"),
    _L(97, "50", "Lưu chuyển tiền thuần trong kỳ",
       "{c}79+{c}87+{c}95", "derived"),
    _L(98, "60", "Tiền và tương đương tiền đầu kỳ"),
    _L(99, "61", "Ảnh hưởng của thay đổi tỷ giá hối đoái"),
    _L(100, "70", "Tiền và tương đương tiền cuối kỳ"),
    _L(101, None, "Kiểm tra: 50 + 60 + 61 − 70",
       "{c}97+{c}98+{c}99-{c}100", "check"),
    _L(102, None, "Kiểm tra: mã 70 − mã 110 (bảng cân đối)",
       "{c}100-{c}34", "check"),
]

MARKET: List[Line] = [
    _L(104, None, "THÔNG TIN THỊ TRƯỜNG", kind="header"),
    _L(105, None, "Giá cổ phiếu cuối kỳ (đồng)"),
    _L(106, None, "Cổ tức tiền mặt trên mỗi cổ phiếu (đồng)"),
]

ALL_LINES: List[Line] = INCOME + BALANCE + CASHFLOW + MARKET

# row lookup by TT200 code, per statement
IS_ROW: Dict[str, int] = {l.code: l.row for l in INCOME if l.code}
BS_ROW: Dict[str, int] = {l.code: l.row for l in BALANCE if l.code}
CF_ROW: Dict[str, int] = {l.code: l.row for l in CASHFLOW if l.code}

SHARES_AVG_ROW = 30
SHARES_END_ROW = 31
PRICE_ROW = 105
DPS_ROW = 106

LAST_ROW = 106

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
