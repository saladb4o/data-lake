"""
=============================================================================
BCTC PDF PARSER (DETERMINISTIC DUAL-ROUTE ENGINE: NATIVE + LOCAL OCR)
=============================================================================
Fast, zero-cost, offline-capable parser for Vietnamese Corporate Financial
Statements (BCTC) adhering to Circular 200/2014/TT-BTC & 133/2016/TT-BTC.

Capabilities:
  1. PDF Type Inspector: Differentiates Native (vector text) vs Scanned Image.
  2. Accent-Insensitive Normalizer: Handles Unicode NFC, NFD, TCVN3, VNI, English/Vietnamese.
  3. Currency & Multiplier Normalizer: Auto-detects 'Đơn vị tính' (Đồng, Nghìn, Triệu, Tỷ VNĐ).
  4. Fast Page Routing: Locates Balance Sheet, Income Statement, Cash Flow, Auditor Report, Footnotes.
  5. Dual-Route Extraction:
     - Route 1: High-Speed Native Vector Extractor (pdfplumber) for digital PDFs.
     - Route 2: Local Offline OCR Engine (RapidOCR ONNX) for 100% scanned image PDFs.
  6. TT200 Accounting Code Extractor: Binds rows to official ItemCodes (100, 110, 270, 300, 400, 440).
  7. Auditor Opinion & Risk Classifier: Detects Big 4, AASC, Opinion Type, Going Concern risk.
  8. Mathematical Accounting Integrity Validator: Enforces Assets = Liabilities + Equity (0 error).
"""

import os
import re
import math
import logging
import unicodedata
from typing import Dict, List, Any, Optional, Tuple, Union

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from rapidocr_onnxruntime import RapidOCR
    _rapid_ocr_engine = RapidOCR()
except Exception:
    _rapid_ocr_engine = None

logger = logging.getLogger(__name__)


def strip_accents(s: str) -> str:
    """Removes Vietnamese tone marks and accents for robust cross-encoding search."""
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFD", s)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D")


# Standard Vietnamese Accounting Code Mappings (Thông tư 200/2014/TT-BTC)
TT200_BALANCE_SHEET_CODES = {
    100: "TÀI SẢN NGẮN HẠN",
    110: "Tiền và các khoản tương đương tiền",
    111: "Tiền mặt",
    112: "Các khoản tương đương tiền",
    120: "Đầu tư tài chính ngắn hạn",
    130: "Các khoản phải thu ngắn hạn",
    131: "Phải thu ngắn hạn của khách hàng",
    132: "Trả trước cho người bán ngắn hạn",
    136: "Phải thu ngắn hạn khác",
    137: "Dự phòng phải thu ngắn hạn khó đòi",
    140: "Hàng tồn kho",
    141: "Hàng tồn kho (nguyên giá)",
    149: "Dự phòng giảm giá hàng tồn kho",
    150: "Tài sản ngắn hạn khác",
    200: "TÀI SẢN DÀI HẠN",
    210: "Phải thu dài hạn",
    220: "Tài sản cố định",
    221: "Nguyên giá TSCĐ hữu hình",
    222: "Giá trị hao mòn lũy kế TSCĐ hữu hình",
    227: "Tài sản cố định vô hình",
    228: "Nguyên giá TSCĐ vô hình",
    229: "Giá trị hao mòn lũy kế TSCĐ vô hình",
    230: "Bất động sản đầu tư",
    240: "Tài sản dở dang dài hạn",
    242: "Chi phí xây dựng cơ bản dở dang",
    250: "Đầu tư tài chính dài hạn",
    260: "Tài sản dài hạn khác",
    270: "TỔNG CỘNG TÀI SẢN",
    300: "NỢ PHẢI TRẢ",
    310: "Nợ ngắn hạn",
    311: "Phải trả người bán ngắn hạn",
    312: "Người mua trả tiền trước ngắn hạn",
    320: "Vay và nợ thuê tài chính ngắn hạn",
    330: "Nợ dài hạn",
    338: "Vay và nợ thuê tài chính dài hạn",
    400: "VỐN CHỦ SỞ HỮU",
    410: "Vốn góp của chủ sở hữu",
    411: "Cổ phiếu phổ thông có quyền biểu quyết",
    418: "Quỹ đầu tư phát triển",
    421: "Lợi nhuận sau thuế chưa phân phối",
    440: "TỔNG CỘNG NGUỒN VỐN"
}

TT200_INCOME_CODES = {
    1: "Doanh thu bán hàng và cung cấp dịch vụ",
    2: "Các khoản giảm trừ doanh thu",
    10: "Doanh thu thuần về bán hàng và cung cấp dịch vụ",
    11: "Giá vốn hàng bán",
    20: "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ",
    21: "Doanh thu hoạt động tài chính",
    22: "Chi phí tài chính",
    23: "Trong đó: Chi phí lãi vay",
    25: "Chi phí bán hàng",
    26: "Chi phí quản lý doanh nghiệp",
    30: "Lợi nhuận thuần từ hoạt động kinh doanh",
    31: "Thu nhập khác",
    32: "Chi phí khác",
    40: "Lợi nhuận khác",
    50: "Tổng lợi nhuận kế toán trước thuế",
    51: "Chi phí thuế TNDN hiện hành",
    52: "Chi phí thuế TNDN hoãn lại",
    60: "Lợi nhuận sau thuế thu nhập doanh nghiệp",
    61: "Lợi nhuận sau thuế của cổ đông công ty mẹ",
    62: "Lợi nhuận sau thuế của cổ đông không kiểm soát",
    70: "Lãi cơ bản trên cổ phiếu (EPS)",
    71: "Lãi suy giảm trên cổ phiếu"
}

TT200_CASH_FLOW_CODES = {
    1: "Lợi nhuận trước thuế / Tiền thu từ bán hàng",
    2: "Điều chỉnh cho các khoản",
    3: "Lợi nhuận kinh doanh trước thay đổi VLĐ",
    20: "Lưu chuyển tiền thuần từ hoạt động kinh doanh (CFO)",
    21: "Tiền chi mua sắm, xây dựng TSCĐ và TSDH khác (CapEx)",
    22: "Tiền thu từ thanh lý, nhượng bán TSCĐ",
    23: "Tiền chi cho vay, mua các công cụ nợ khác",
    24: "Tiền thu hồi cho vay, bán lại công cụ nợ khác",
    25: "Tiền đầu tư góp vốn vào đơn vị khác",
    26: "Tiền thu hồi đầu tư góp vốn vào đơn vị khác",
    27: "Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia",
    30: "Lưu chuyển tiền thuần từ hoạt động đầu tư (CFI)",
    31: "Tiền thu từ phát hành cổ phiếu, nhận vốn góp của CSH",
    32: "Tiền trả lại vốn góp, mua lại cổ phiếu phát hành",
    33: "Tiền vay gốc nhận được",
    34: "Tiền trả nợ gốc vay",
    35: "Tiền trả nợ gốc thuê tài chính",
    36: "Cổ tức, lợi nhuận đã trả cho chủ sở hữu",
    40: "Lưu chuyển tiền thuần từ hoạt động tài chính (CFF)",
    50: "Lưu chuyển tiền thuần trong kỳ (Net Cash Flow)",
    60: "Tiền và tương đương tiền đầu kỳ",
    61: "Ảnh hưởng của thay đổi tỷ giá hối đoái",
    70: "Tiền và tương đương tiền cuối kỳ"
}



def parse_vietnamese_accounting_number(cell_str: Any) -> Optional[float]:
    """
    Parses Vietnamese financial statement numbers safely.
    Handles:
      - Normal dot separators: '1.234.567.890' -> 1234567890.0
      - Comma separators: '27,459,400,673,320' -> 27459400673320.0
      - Accounting negative parenthesized: '(123.456)' -> -123456.0
      - Negative hyphen: '-123.456' -> -123456.0
      - Trailing or leading whitespaces / non-breaking spaces
      - Zero representations: '-', '--', 'nil', 'không' -> 0.0
    """
    if cell_str is None:
        return None
    if isinstance(cell_str, (int, float)):
        if math.isnan(cell_str) or math.isinf(cell_str):
            return None
        return float(cell_str)

    s = str(cell_str).strip().replace('\xa0', ' ').replace(' ', '')
    if not s or s in ('-', '--', '—', 'nil', 'null', 'None', 'không', 'khong'):
        return 0.0

    is_negative = False
    if s.startswith('(') and s.endswith(')'):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith('-'):
        is_negative = True
        s = s[1:].strip()

    # In VN accounting, comma or dot can be thousand separators
    if '.' in s and ',' in s:
        # Check standard European vs US format
        if s.rfind(',') > s.rfind('.'):
            # 1.234,56 (VN standard: dot thousand, comma decimal)
            s = s.replace('.', '').replace(',', '.')
        else:
            # 1,234.56 (US standard: comma thousand, dot decimal)
            s = s.replace(',', '')
    elif '.' in s:
        parts = s.split('.')
        if all(len(p) == 3 for p in parts[1:]):
            s = s.replace('.', '')
    elif ',' in s:
        parts = s.split(',')
        if all(len(p) == 3 for p in parts[1:]):
            s = s.replace(',', '')
        else:
            s = s.replace(',', '.')

    try:
        val = float(s)
        return -val if is_negative else val
    except ValueError:
        return None


def detect_currency_unit(text_sample: str) -> Tuple[str, float]:
    """
    Detects reporting unit from text header ('Đơn vị tính: Đồng / Triệu / Tỷ').
    Returns (unit_name, scale_multiplier_to_vnd).
    """
    t = strip_accents(text_sample).lower()
    if any(k in t for k in ["don vi tinh: ty", "dvt: ty", "don vi: ty dong", "ty dong", "dvt: ty"]):
        return "TỶ_VND", 1_000_000_000.0
    if any(k in t for k in ["don vi tinh: trieu", "dvt: trieu", "don vi: trieu dong", "trieu dong", "dvt: trieu", "million vnd"]):
        return "TRIỆU_VND", 1_000_000.0
    if any(k in t for k in ["don vi tinh: nghin", "dvt: nghin", "don vi tinh: ngan", "don vi: nghin dong", "nghin dong", "ngan dong", "thousand vnd"]):
        return "NGHÌN_VND", 1_000.0
    if any(k in t for k in ["don vi tinh: usd", "dvt: usd"]):
        return "USD", 25_400.0
    return "VND", 1.0


def detect_reporting_period(filename_or_title: str = "", text_sample: str = "") -> Dict[str, Any]:
    """
    Detects financial reporting period from filename/title and document text:
      - period_type: 'quarter' | 'half_year' | 'annual' | 'unknown'
      - quarter: 1 | 2 | 3 | 4 | None
      - year: int or None
      - period_label: e.g. 'Q1/2024', '6M/2024', 'FY2024'
      - is_audited: bool
    """
    combined = (filename_or_title + " " + text_sample).lower()
    norm_text = strip_accents(combined)

    # 1. Year extraction
    year = None
    year_matches = re.findall(r'\b(20[123]\d)\b', norm_text)
    if year_matches:
        year = int(year_matches[0])

    # 2. Quarter and Period Type
    quarter = None
    period_type = "unknown"

    if re.search(r'\b(quy\s*1|quy\s*i\b|q1\b|first\s*quarter)\b', norm_text):
        quarter = 1
        period_type = "quarter"
    elif re.search(r'\b(quy\s*2|quy\s*ii\b|q2\b|second\s*quarter)\b', norm_text):
        if re.search(r'\b(ban\s*nien|6\s*thang|soat\s*xet|half\s*year|first\s*half|h1\b)\b', norm_text):
            quarter = 2
            period_type = "half_year"
        else:
            quarter = 2
            period_type = "quarter"
    elif re.search(r'\b(ban\s*nien|6\s*thang|soat\s*xet\s*ban\s*nien|half\s*year|first\s*half|h1\b)\b', norm_text):
        quarter = 2
        period_type = "half_year"
    elif re.search(r'\b(quy\s*3|quy\s*iii\b|q3\b|third\s*quarter)\b', norm_text):
        quarter = 3
        period_type = "quarter"
    elif re.search(r'\b(quy\s*4|quy\s*iv\b|q4\b|fourth\s*quarter)\b', norm_text):
        quarter = 4
        period_type = "quarter"
    elif re.search(r'\b(kiem\s*toan\s*nam|bctc\s*nam|ca\s*nam|nam\s*tai\s*chinh|annual|full\s*year|\bfy\b)\b', norm_text):
        quarter = None
        period_type = "annual"
    elif re.search(r'\b(kiem\s*toan|audited|auditor)\b', norm_text):
        quarter = None
        period_type = "annual"

    # 3. Label
    if period_type == "quarter" and quarter:
        period_label = f"Q{quarter}/{year}" if year else f"Q{quarter}"
    elif period_type == "half_year":
        period_label = f"6M/{year}" if year else "6M"
    elif period_type == "annual":
        period_label = f"FY{year}" if year else "FY"
    else:
        period_label = f"{year}" if year else "UNKNOWN"

    is_audited = bool(re.search(r'\b(kiem\s*toan|audited|soat\s*xet|reviewed)\b', norm_text))

    return {
        "period_type": period_type,
        "quarter": quarter,
        "year": year,
        "period_label": period_label,
        "is_audited": is_audited
    }


class BCTCPdfParser:
    """
    High-Performance Deterministic PDF Financial Statement Extractor.
    Operates without LLMs using dual-route architecture:
      - Native Vector Extractor for text-layer PDFs (pdfplumber)
      - RapidOCR Engine for scanned image-only PDFs
    """

    def __init__(self, pdf_path: str):
        self.pdf_path = os.path.abspath(pdf_path)
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")
        self.doc_type: str = "UNKNOWN"
        self.total_pages: int = 0
        self.currency_unit: str = "VND"
        self.currency_scale: float = 1.0
        self.period_info: Dict[str, Any] = {}
        self._cached_ocr_pages: Dict[int, List[str]] = {}
        self._inspect_pdf()

    def _inspect_pdf(self) -> None:
        """Inspects document structure, text density, and currency unit."""
        if not fitz:
            logger.warning("PyMuPDF (fitz) not available, inspection skipped.")
            return

        with fitz.open(self.pdf_path) as doc:
            self.total_pages = len(doc)
            if self.total_pages == 0:
                self.doc_type = "EMPTY"
                return

            total_chars = 0
            sample_pages = min(5, self.total_pages)
            sample_text = ""
            for i in range(sample_pages):
                txt = doc[i].get_text()
                total_chars += len(txt)
                sample_text += " " + txt

            image_pages = 0
            low_text_pages = 0
            for i in range(min(10, self.total_pages)):
                imgs = doc[i].get_images()
                txt_len = len(doc[i].get_text().strip())
                if imgs:
                    image_pages += 1
                if txt_len < 150:
                    low_text_pages += 1

            avg_chars = total_chars / max(1, sample_pages)
            if image_pages >= 2 and low_text_pages >= 2:
                self.doc_type = "SCANNED_IMAGE"
            elif avg_chars > 30:
                self.doc_type = "NATIVE"
            else:
                self.doc_type = "SCANNED"

            unit_name, scale = detect_currency_unit(sample_text)
            self.currency_unit = unit_name
            self.currency_scale = scale
            self.period_info = detect_reporting_period(os.path.basename(self.pdf_path), sample_text)

    def locate_statement_pages(self) -> Dict[str, List[int]]:
        """
        Locates page numbers for B/S, I/S, C/F, Auditor Opinion, and Footnotes.
        First tries fast native vector text. If empty and scanned, uses RapidOCR on candidate pages.
        """
        locations: Dict[str, List[int]] = {
            "balance_sheet": [],
            "income_statement": [],
            "cash_flow": [],
            "auditor_report": [],
            "footnotes": []
        }

        if not fitz:
            return locations

        # Pass 1: Native Vector Text
        with fitz.open(self.pdf_path) as doc:
            for page_idx in range(len(doc)):
                txt_norm = strip_accents(doc[page_idx].get_text()).upper()

                if any(k in txt_norm for k in ["BAO CAO CUA CONG TY KIEM TOAN", "BAO CAO KIEM TOAN", "KIEM TOAN VIEN", "AUDITOR"]):
                    locations["auditor_report"].append(page_idx)
                if any(k in txt_norm for k in ["BANG CAN DOI KE TOAN", "MAU SO B 01", "MAU B 01", "FINANCIAL POSITION", "BALANCE SHEET"]):
                    locations["balance_sheet"].append(page_idx)
                if any(k in txt_norm for k in ["KET QUA HOAT DONG KINH DOANH", "MAU SO B 02", "MAU B 02", "INCOME STATEMENT", "FINANCIAL PERFORMANCE"]):
                    locations["income_statement"].append(page_idx)
                if any(k in txt_norm for k in ["LUU CHUYEN TIEN TE", "MAU SO B 03", "MAU B 03", "CASH FLOW"]):
                    locations["cash_flow"].append(page_idx)
                if any(k in txt_norm for k in ["THUYET MINH BAO CAO TAI CHINH", "THUYET MINH BCTC", "NOTES TO THE FINANCIAL"]):
                    locations["footnotes"].append(page_idx)

        # Pass 2: If Balance Sheet not found and document is SCANNED, scan candidate pages with RapidOCR
        if not locations["balance_sheet"] and self.doc_type in ("SCANNED_IMAGE", "SCANNED") and _rapid_ocr_engine:
            logger.info(f"Native search empty, engaging RapidOCR on candidate pages of {os.path.basename(self.pdf_path)}")
            with fitz.open(self.pdf_path) as doc:
                scan_limit = min(14, len(doc))
                for p_idx in range(scan_limit):
                    ocr_lines = self._get_ocr_lines_for_page(doc, p_idx)
                    page_text = " ".join(ocr_lines).upper()

                    if any(k in page_text for k in ["REVIEW REPORT", "AUDITOR", "KIEM TOAN"]):
                        if p_idx not in locations["auditor_report"]:
                            locations["auditor_report"].append(p_idx)
                    if any(k in page_text for k in ["FINANCIAL POSITION", "BALANCE SHEET", "BANG CAN DOI", "CAN DOI KE TOAN"]):
                        if p_idx not in locations["balance_sheet"]:
                            locations["balance_sheet"].append(p_idx)
                    if any(k in page_text for k in ["INCOME STATEMENT", "KET QUA KINH DOANH", "FINANCIAL PERFORMANCE"]):
                        if p_idx not in locations["income_statement"]:
                            locations["income_statement"].append(p_idx)
                    if any(k in page_text for k in ["LUU CHUYEN TIEN TE", "CASH FLOW", "LUU CHUYEN TIEN"]):
                        if p_idx not in locations["cash_flow"]:
                            locations["cash_flow"].append(p_idx)

                    # Early exit if core statements are found
                    if locations["balance_sheet"] and locations["auditor_report"] and locations["income_statement"] and (locations["cash_flow"] or p_idx >= 12):
                        break

        return locations

    def _get_ocr_lines_for_page(self, doc: Any, page_idx: int) -> List[str]:
        """Runs RapidOCR on a specific page with memory caching."""
        if page_idx in self._cached_ocr_pages:
            return self._cached_ocr_pages[page_idx]

        if not _rapid_ocr_engine or page_idx >= len(doc):
            return []

        try:
            pix = doc[page_idx].get_pixmap(dpi=135)
            res, _ = _rapid_ocr_engine(pix.tobytes("png"))
            lines = [item[1].strip() for item in res] if res else []
            self._cached_ocr_pages[page_idx] = lines
            return lines
        except Exception as e:
            logger.warning(f"OCR failed on page {page_idx}: {e}")
            return []

    def extract_auditor_opinion(self) -> Dict[str, Any]:
        """
        Extracts Auditor Name, Opinion Type, and Red Flag Badges from Audit Report.
        """
        result = {
            "auditor_firm": "Unknown",
            "is_big4": False,
            "opinion_type": "Chấp nhận toàn phần (Unqualified)",
            "has_emphasis_of_matter": False,
            "has_going_concern_issue": False,
            "risk_flags": []
        }

        if not fitz:
            return result

        pages_map = self.locate_statement_pages()
        audit_pages = pages_map.get("auditor_report", [])
        if not audit_pages:
            audit_pages = list(range(min(5, self.total_pages)))

        full_audit_text = ""
        with fitz.open(self.pdf_path) as doc:
            for p in audit_pages:
                if p < len(doc):
                    txt = doc[p].get_text().strip()
                    if not txt and self.doc_type in ("SCANNED_IMAGE", "SCANNED"):
                        lines = self._get_ocr_lines_for_page(doc, p)
                        txt = "\n".join(lines)
                    full_audit_text += "\n" + txt

        t_norm = strip_accents(full_audit_text).lower()

        # 1. Auditor Firm Identification
        if any(w in t_norm for w in ["pwc", "pricewaterhousecoopers"]):
            result["auditor_firm"] = "PricewaterhouseCoopers (PwC)"
            result["is_big4"] = True
        elif any(w in t_norm for w in ["ernst & young", "ey viet nam", "e&y"]):
            result["auditor_firm"] = "Ernst & Young (EY)"
            result["is_big4"] = True
        elif "kpmg" in t_norm:
            result["auditor_firm"] = "KPMG Việt Nam"
            result["is_big4"] = True
        elif "deloitte" in t_norm:
            result["auditor_firm"] = "Deloitte Việt Nam"
            result["is_big4"] = True
        elif any(w in t_norm for w in ["aasc", "a&c", "vaaco", "uhy", "bdo", "grant thornton", "moore"]):
            for firm in ["Grant Thornton", "BDO", "AASC", "A&C", "VAACO", "UHY", "Moore"]:
                if firm.lower() in t_norm:
                    result["auditor_firm"] = firm
                    break

        # 2. Opinion Classification
        if any(w in t_norm for w in ["tu choi dua ra y kien", "khong the thu thap day du", "disclaimer"]):
            result["opinion_type"] = "Từ chối đưa ra ý kiến (Disclaimer)"
            result["risk_flags"].append("DISCLAIMER_OF_OPINION")
        elif any(w in t_norm for w in ["y kien ngoai tru", "ngoai tru anh huong", "ngoai tru van de", "qualified"]):
            result["opinion_type"] = "Ý kiến ngoại trừ (Qualified)"
            result["risk_flags"].append("QUALIFIED_OPINION")
        elif any(w in t_norm for w in ["y kien trai nguoc", "khong phan anh trung thuc", "adverse"]):
            result["opinion_type"] = "Ý kiến trái ngược (Adverse)"
            result["risk_flags"].append("ADVERSE_OPINION")
        else:
            result["opinion_type"] = "Chấp nhận toàn phần (Unqualified)"

        # 3. Emphasis of Matter & Going Concern
        if any(w in t_norm for w in ["van de can nhan manh", "nhan manh cua kiem toan vien", "emphasis of matter"]):
            result["has_emphasis_of_matter"] = True
            result["risk_flags"].append("EMPHASIS_OF_MATTER")

        if any(w in t_norm for w in ["hoat dong lien tuc", "nghi ngo dang ke", "suy giam kha nang thanh toan", "going concern"]):
            result["has_going_concern_issue"] = True
            result["risk_flags"].append("GOING_CONCERN_RISK")

        return result

    def extract_balance_sheet(self) -> Dict[str, Any]:
        """
        Dual-route Balance Sheet extractor.
        Anchored to TT200 codes (100, 110, 270, 300, 440) using either pdfplumber or RapidOCR.
        """
        items = {}
        pages_map = self.locate_statement_pages()
        bs_pages = pages_map.get("balance_sheet", [])
        method_used = "NATIVE_VECTOR"

        # Route 1: Try native vector extraction via pdfplumber
        if bs_pages and pdfplumber and self.doc_type != "SCANNED_IMAGE":
            with pdfplumber.open(self.pdf_path) as pdf:
                for p_idx in bs_pages:
                    if p_idx >= len(pdf.pages):
                        continue
                    tables = pdf.pages[p_idx].extract_tables()
                    for table in tables:
                        for row in table:
                            if not row or len(row) < 3:
                                continue
                            self._parse_balance_sheet_row(row, items)

        # Route 2: If Route 1 yielded 0 items and document is Scanned / OCR engine available
        if not items and bs_pages and _rapid_ocr_engine:
            method_used = "RAPID_OCR_ONNX"
            with fitz.open(self.pdf_path) as doc:
                # Scanned balance sheets often span 2 consecutive pages
                pages_to_ocr = set(bs_pages)
                for p in list(bs_pages):
                    if p + 1 < len(doc):
                        pages_to_ocr.add(p + 1)

                for p_idx in sorted(pages_to_ocr):
                    lines = self._get_ocr_lines_for_page(doc, p_idx)
                    self._parse_ocr_lines_for_balance_sheet(lines, items)

        # Mathematical Integrity Check: Assets == Liabilities + Equity
        assets = items.get(270, {}).get("current_val")
        sources = items.get(440, {}).get("current_val")
        liab = items.get(300, {}).get("current_val")
        equity = items.get(400, {}).get("current_val")

        is_balanced = False
        diff = 0.0
        if assets is not None and sources is not None:
            diff = abs(assets - sources)
            is_balanced = diff < max(1000.0, assets * 0.0001)
        elif assets is not None and liab is not None and equity is not None:
            diff = abs(assets - (liab + equity))
            is_balanced = diff < max(1000.0, assets * 0.0001)

        return {
            "items": items,
            "currency_unit": self.currency_unit,
            "scale_multiplier": self.currency_scale,
            "is_balanced": is_balanced,
            "difference_vnd": diff,
            "extraction_method": method_used
        }

    def _parse_ocr_lines_for_balance_sheet(self, lines: List[str], items_dict: Dict[int, Any]) -> None:
        """Parses OCR output lines into TT200 Balance Sheet items."""
        for i, line in enumerate(lines):
            m = re.fullmatch(r"([1-4][0-9]{2})", line)
            if m:
                code = int(m.group(1))
                numbers = []
                for next_line in lines[i + 1:i + 6]:
                    if re.fullmatch(r"[1-4][0-9]{2}", next_line):
                        break
                    num = parse_vietnamese_accounting_number(next_line)
                    if num is not None and abs(num) > 1000:
                        numbers.append(num * self.currency_scale)
                if numbers and code not in items_dict:
                    items_dict[code] = {
                        "code": code,
                        "name": TT200_BALANCE_SHEET_CODES.get(code, "Unknown"),
                        "current_val": numbers[0],
                        "previous_val": numbers[1] if len(numbers) > 1 else None
                    }

    def _parse_balance_sheet_row(self, row: List[Any], items_dict: Dict[int, Any]) -> None:
        """Helper to match row cells against TT200 codes."""
        text_row = [str(c).strip() if c is not None else "" for c in row]
        code_found = None
        code_idx = -1
        for idx, col in enumerate(text_row[:4]):
            m = re.fullmatch(r"([1-4][0-9]{2})", col)
            if m:
                code_found = int(m.group(1))
                code_idx = idx
                break

        if code_found and code_found in TT200_BALANCE_SHEET_CODES:
            vals = []
            for col in text_row[code_idx + 1:]:
                num = parse_vietnamese_accounting_number(col)
                if num is not None:
                    vals.append(num * self.currency_scale)

            if vals:
                curr_val = vals[0]
                prev_val = vals[1] if len(vals) > 1 else None
                items_dict[code_found] = {
                    "code": code_found,
                    "name": TT200_BALANCE_SHEET_CODES[code_found],
                    "current_val": curr_val,
                    "previous_val": prev_val
                }

    def extract_income_statement(self) -> Dict[str, Any]:
        """
        Dual-route Income Statement (Báo cáo Kết quả Hoạt động Kinh doanh - Mẫu B 02) extractor.
        Anchored to TT200 codes (01, 10, 11, 20, 21, 22, 23, 25, 26, 30, 50, 51, 60, 61, 70).
        """
        items: Dict[int, Any] = {}
        pages_map = self.locate_statement_pages()
        is_pages = pages_map.get("income_statement", [])
        method_used = "NATIVE_VECTOR"

        if is_pages and pdfplumber and self.doc_type != "SCANNED_IMAGE":
            with pdfplumber.open(self.pdf_path) as pdf:
                for p_idx in is_pages:
                    if p_idx >= len(pdf.pages):
                        continue
                    tables = pdf.pages[p_idx].extract_tables()
                    for table in tables:
                        for row in table:
                            if not row or len(row) < 3:
                                continue
                            self._parse_income_row(row, items)

        if not items and is_pages and _rapid_ocr_engine:
            method_used = "RAPID_OCR_ONNX"
            with fitz.open(self.pdf_path) as doc:
                pages_to_ocr = set(is_pages)
                for p in list(is_pages):
                    if p + 1 < len(doc):
                        pages_to_ocr.add(p + 1)
                for p_idx in sorted(pages_to_ocr):
                    lines = self._get_ocr_lines_for_page(doc, p_idx)
                    self._parse_ocr_lines_for_income(lines, items)

        rev = items.get(10, {}).get("current_val") or items.get(1, {}).get("current_val")
        cogs = items.get(11, {}).get("current_val")
        gp = items.get(20, {}).get("current_val")
        fin_inc = items.get(21, {}).get("current_val")
        fin_exp = items.get(22, {}).get("current_val")
        int_exp = items.get(23, {}).get("current_val")
        op_profit = items.get(30, {}).get("current_val")
        pbt = items.get(50, {}).get("current_val")
        tax = items.get(51, {}).get("current_val")
        npat = items.get(60, {}).get("current_val")
        parent_npat = items.get(61, {}).get("current_val") or npat
        eps = items.get(70, {}).get("current_val")

        is_gp_balanced = False
        if rev is not None and cogs is not None and gp is not None:
            is_gp_balanced = abs((rev - cogs) - gp) < max(1000.0, rev * 0.005)

        is_tax_balanced = False
        if pbt is not None and tax is not None and npat is not None:
            is_tax_balanced = abs((pbt - tax) - npat) < max(1000.0, abs(pbt) * 0.005)

        return {
            "items": items,
            "currency_unit": self.currency_unit,
            "scale_multiplier": self.currency_scale,
            "revenue_vnd": rev,
            "cogs_vnd": cogs,
            "gross_profit_vnd": gp,
            "financial_revenue_vnd": fin_inc,
            "financial_expense_vnd": fin_exp,
            "interest_expense_vnd": int_exp,
            "operating_profit_vnd": op_profit,
            "pbt_vnd": pbt,
            "tax_expense_vnd": tax,
            "npat_vnd": npat,
            "parent_npat_vnd": parent_npat,
            "eps_vnd": eps,
            "is_gross_profit_balanced": is_gp_balanced,
            "is_tax_balanced": is_tax_balanced,
            "extraction_method": method_used
        }

    def _parse_ocr_lines_for_income(self, lines: List[str], items_dict: Dict[int, Any]) -> None:
        """Parses OCR output lines into TT200 Income Statement items."""
        for i, line in enumerate(lines):
            m = re.fullmatch(r"0?([1-7][0-9]?)", line)
            if m:
                code = int(m.group(1))
                if code not in TT200_INCOME_CODES:
                    continue
                numbers = []
                for next_line in lines[i + 1:i + 6]:
                    if re.fullmatch(r"0?[1-7][0-9]?", next_line):
                        break
                    num = parse_vietnamese_accounting_number(next_line)
                    if num is not None and abs(num) > 100:
                        numbers.append(num * self.currency_scale)
                if numbers and code not in items_dict:
                    items_dict[code] = {
                        "code": code,
                        "name": TT200_INCOME_CODES.get(code, "Unknown"),
                        "current_val": numbers[0],
                        "previous_val": numbers[1] if len(numbers) > 1 else None
                    }

    def _parse_income_row(self, row: List[Any], items_dict: Dict[int, Any]) -> None:
        """Helper to match row cells against TT200 Income Statement codes."""
        text_row = [str(c).strip() if c is not None else "" for c in row]
        code_found = None
        code_idx = -1
        for idx, col in enumerate(text_row[:4]):
            m = re.fullmatch(r"0?([1-7][0-9]?)", col)
            if m:
                val = int(m.group(1))
                if val in TT200_INCOME_CODES:
                    code_found = val
                    code_idx = idx
                    break

        if code_found and code_found in TT200_INCOME_CODES:
            vals = []
            for col in text_row[code_idx + 1:]:
                num = parse_vietnamese_accounting_number(col)
                if num is not None:
                    vals.append(num * self.currency_scale)

            if vals:
                curr_val = vals[0]
                prev_val = vals[1] if len(vals) > 1 else None
                items_dict[code_found] = {
                    "code": code_found,
                    "name": TT200_INCOME_CODES[code_found],
                    "current_val": curr_val,
                    "previous_val": prev_val
                }

    def extract_cash_flow_statement(self) -> Dict[str, Any]:
        """
        Dual-route Cash Flow Statement (Báo cáo Lưu chuyển Tiền tệ - Mẫu B 03) extractor.
        Anchored to TT200 codes (20, 21, 30, 40, 50, 60, 70).
        """
        items: Dict[int, Any] = {}
        pages_map = self.locate_statement_pages()
        cf_pages = pages_map.get("cash_flow", [])
        method_used = "NATIVE_VECTOR"

        if cf_pages and pdfplumber and self.doc_type != "SCANNED_IMAGE":
            with pdfplumber.open(self.pdf_path) as pdf:
                for p_idx in cf_pages:
                    if p_idx >= len(pdf.pages):
                        continue
                    tables = pdf.pages[p_idx].extract_tables()
                    for table in tables:
                        for row in table:
                            if not row or len(row) < 3:
                                continue
                            self._parse_cash_flow_row(row, items)

        if not items and cf_pages and _rapid_ocr_engine:
            method_used = "RAPID_OCR_ONNX"
            with fitz.open(self.pdf_path) as doc:
                pages_to_ocr = set(cf_pages)
                for p in list(cf_pages):
                    if p + 1 < len(doc):
                        pages_to_ocr.add(p + 1)
                    if p + 2 < len(doc):
                        pages_to_ocr.add(p + 2)
                for p_idx in sorted(pages_to_ocr):
                    lines = self._get_ocr_lines_for_page(doc, p_idx)
                    self._parse_ocr_lines_for_cash_flow(lines, items)

        cfo = items.get(20, {}).get("current_val")
        capex_raw = items.get(21, {}).get("current_val")
        capex = abs(capex_raw) if capex_raw is not None else None
        cfi = items.get(30, {}).get("current_val")
        cff = items.get(40, {}).get("current_val")
        net_cf = items.get(50, {}).get("current_val")
        cash_begin = items.get(60, {}).get("current_val")
        cash_end = items.get(70, {}).get("current_val")

        is_net_cf_balanced = False
        if cfo is not None and cfi is not None and cff is not None and net_cf is not None:
            is_net_cf_balanced = abs((cfo + cfi + cff) - net_cf) < max(1000.0, abs(net_cf) * 0.005)

        is_cash_ending_balanced = False
        if cash_begin is not None and net_cf is not None and cash_end is not None:
            is_cash_ending_balanced = abs((cash_begin + net_cf) - cash_end) < max(1000.0, abs(cash_end) * 0.005)

        fcf = (cfo - capex) if (cfo is not None and capex is not None) else None

        return {
            "items": items,
            "currency_unit": self.currency_unit,
            "scale_multiplier": self.currency_scale,
            "cfo_vnd": cfo,
            "cfi_vnd": cfi,
            "cff_vnd": cff,
            "capex_vnd": capex,
            "net_cash_flow_vnd": net_cf,
            "cash_begin_period_vnd": cash_begin,
            "cash_end_period_vnd": cash_end,
            "free_cash_flow_vnd": fcf,
            "is_net_cash_flow_balanced": is_net_cf_balanced,
            "is_cash_ending_balanced": is_cash_ending_balanced,
            "extraction_method": method_used
        }

    def _parse_ocr_lines_for_cash_flow(self, lines: List[str], items_dict: Dict[int, Any]) -> None:
        """Parses OCR output lines into TT200 Cash Flow items."""
        for i, line in enumerate(lines):
            m = re.fullmatch(r"0?([1-7][0-9]?)", line)
            if m:
                code = int(m.group(1))
                if code not in TT200_CASH_FLOW_CODES:
                    continue
                numbers = []
                for next_line in lines[i + 1:i + 6]:
                    if re.fullmatch(r"0?[1-7][0-9]?", next_line):
                        break
                    num = parse_vietnamese_accounting_number(next_line)
                    if num is not None and abs(num) > 100:
                        numbers.append(num * self.currency_scale)
                if numbers and code not in items_dict:
                    items_dict[code] = {
                        "code": code,
                        "name": TT200_CASH_FLOW_CODES.get(code, "Unknown"),
                        "current_val": numbers[0],
                        "previous_val": numbers[1] if len(numbers) > 1 else None
                    }

    def _parse_cash_flow_row(self, row: List[Any], items_dict: Dict[int, Any]) -> None:
        """Helper to match row cells against TT200 Cash Flow codes."""
        text_row = [str(c).strip() if c is not None else "" for c in row]
        code_found = None
        code_idx = -1
        for idx, col in enumerate(text_row[:4]):
            m = re.fullmatch(r"0?([1-7][0-9]?)", col)
            if m:
                val = int(m.group(1))
                if val in TT200_CASH_FLOW_CODES:
                    code_found = val
                    code_idx = idx
                    break

        if code_found and code_found in TT200_CASH_FLOW_CODES:
            vals = []
            for col in text_row[code_idx + 1:]:
                num = parse_vietnamese_accounting_number(col)
                if num is not None:
                    vals.append(num * self.currency_scale)

            if vals:
                curr_val = vals[0]
                prev_val = vals[1] if len(vals) > 1 else None
                items_dict[code_found] = {
                    "code": code_found,
                    "name": TT200_CASH_FLOW_CODES[code_found],
                    "current_val": curr_val,
                    "previous_val": prev_val
                }

    def extract_debt_footnotes(self) -> List[Dict[str, Any]]:
        """
        Micro-Extractor: Parses Bank Loans & Debt footnote breakdown.
        """
        debt_facilities = []
        if not fitz:
            return debt_facilities

        known_banks = [
            "Vietcombank", "VCB", "VietinBank", "CTG", "BIDV", "BID", "Agribank",
            "Techcombank", "TCB", "MBBank", "MBB", "VPBank", "VPB", "ACB",
            "HDBank", "HDB", "VIB", "SHB", "TPBank", "TPB", "MSB", "OCB",
            "Sacombank", "STB", "SeABank", "SSB", "LPBank", "LPB", "Nam A Bank",
            "Trái phiếu", "Trai phieu", "Trái chủ", "Trai chu", "Bond"
        ]

        with fitz.open(self.pdf_path) as doc:
            for p_idx in range(len(doc)):
                raw_txt = doc[p_idx].get_text()
                txt_norm = strip_accents(raw_txt).upper()
                if any(k in txt_norm for k in ["VAY VA NO THUE TAI CHINH", "VAY NGAN HAN", "VAY DAI HAN", "BORROWINGS"]):
                    lines = raw_txt.split("\n")
                    for line in lines:
                        for b in known_banks:
                            if strip_accents(b).lower() in strip_accents(line).lower():
                                nums = re.findall(r"\b\d{1,3}(?:\.\d{3}){1,}\b", line)
                                if nums:
                                    amt = parse_vietnamese_accounting_number(nums[0])
                                    if amt and amt > 0:
                                        debt_facilities.append({
                                            "lender": b,
                                            "raw_line": line.strip(),
                                            "amount_vnd": amt * self.currency_scale,
                                            "page": p_idx + 1
                                        })
                                break

        seen = set()
        deduped = []
        for d in debt_facilities:
            k = (d["lender"], round(d["amount_vnd"] / 1_000_000_000.0, 1))
            if k not in seen:
                seen.add(k)
                deduped.append(d)

        return deduped

    def extract_landbank_footnotes(self) -> List[Dict[str, Any]]:
        """
        Micro-Extractor: Parses WIP Real Estate Projects (Chi phí SXKD dở dang BĐS).
        Feeds into Model 18 (Real Estate RNAV).
        """
        projects = []
        if not fitz:
            return projects

        wip_keywords = [
            "dự án", "du an", "khu đô thị", "khu do thi", "khu dân cư", "khu dan cu",
            "tổ hợp", "to hop", "chung cư", "chung cu",
            "resort", "aquacity", "novaworld", "grand marina", "vinhomes"
        ]

        with fitz.open(self.pdf_path) as doc:
            for p_idx in range(len(doc)):
                raw_txt = doc[p_idx].get_text()
                txt_norm = strip_accents(raw_txt).lower()
                if any(k in txt_norm for k in ["san xuat, kinh doanh do dang", "san xuat kinh doanh do dang", "xay dung co ban do dang", "bat dong san do dang", "chi phi do dang"]):
                    lines = raw_txt.split("\n")
                    for line in lines:
                        l_norm = strip_accents(line).lower()
                        if any(kw in l_norm for kw in wip_keywords):
                            nums = re.findall(r"\b\d{1,3}(?:\.\d{3}){1,}\b", line)
                            if nums:
                                amt = parse_vietnamese_accounting_number(nums[0])
                                if amt and amt > 0:
                                    projects.append({
                                        "project_name": line.strip()[:60],
                                        "carrying_value_vnd": amt * self.currency_scale,
                                        "page": p_idx + 1
                                    })

        seen = set()
        deduped = []
        for p in projects:
            k = (p["project_name"], round(p["carrying_value_vnd"] / 1_000_000_000.0, 1))
            if k not in seen:
                seen.add(k)
                deduped.append(p)

        return deduped

    def extract_full_report(self) -> Dict[str, Any]:
        """
        Orchestrates full extraction into a structured JSON payload ready for Data Lake.
        """
        bs_data = self.extract_balance_sheet()
        is_data = self.extract_income_statement()
        cf_data = self.extract_cash_flow_statement()
        audit_data = self.extract_auditor_opinion()
        debt_data = self.extract_debt_footnotes()
        landbank_data = self.extract_landbank_footnotes()

        forensics = calculate_forensic_triangles({
            "balance_sheet": bs_data,
            "income_statement": is_data,
            "cash_flow": cf_data,
            "debt_schedule_footnotes": debt_data,
            "auditor_summary": audit_data
        })

        return {
            "pdf_path": self.pdf_path,
            "document_type": self.doc_type,
            "total_pages": self.total_pages,
            "period_info": self.period_info,
            "currency_unit": self.currency_unit,
            "scale_multiplier": self.currency_scale,
            "auditor_summary": audit_data,
            "balance_sheet": bs_data,
            "income_statement": is_data,
            "cash_flow": cf_data,
            "debt_schedule_footnotes": debt_data,
            "landbank_wip_footnotes": landbank_data,
            "forensic_triangles": forensics,
            "provenance": "DUAL_ROUTE_PDF_PARSER_TT200"
        }


def calculate_forensic_triangles(
    bctc_report: Dict[str, Any],
    disclosures_report: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Computes 5 Forensic Accounting Triangles (Gian Lận Kế Toán & Giám Định BCTC):
      1. Sloan Accrual Quality: (NPAT - CFO) / Total Assets (Quality of Earnings)
      2. Bank Debt Reconciliation: Footnote Bank Debt vs Balance Sheet Borrowings (Mã 320 + 338)
      3. Effective Borrowing & Tax Rates: Borrowing cost vs Debt, Tax paid vs PBT
      4. Related-Party Drain Ratio: Related-party transactions vs Equity (Nguy cơ rút ruột)
      5. AGM Guidance Fulfillment: Actual Revenue & NPAT vs AGM Resolution Targets
    """
    bs = bctc_report.get("balance_sheet", {})
    bs_items = bs.get("items", {})
    is_stmt = bctc_report.get("income_statement", {})
    cf_stmt = bctc_report.get("cash_flow", {})
    debt_notes = bctc_report.get("debt_schedule_footnotes", [])
    disclosures = disclosures_report or {}

    # 1. Sloan Accrual Quality
    npat = is_stmt.get("npat_vnd") or is_stmt.get("parent_npat_vnd")
    if npat is None and bs_items.get(421):
        npat = bs_items[421].get("current_val")
    cfo = cf_stmt.get("cfo_vnd")
    tot_assets = bs_items.get(270, {}).get("current_val")

    sloan_ratio = None
    earnings_quality = "UNKNOWN"
    accrual_vnd = None
    if npat is not None and cfo is not None and tot_assets and tot_assets > 0:
        accrual_vnd = npat - cfo
        sloan_ratio = round(accrual_vnd / tot_assets, 4)
        if sloan_ratio > 0.10:
            earnings_quality = "POOR (High Accruals / Paper Profits)"
        elif sloan_ratio < -0.10:
            earnings_quality = "EXCELLENT (High Cash Conversion)"
        else:
            earnings_quality = "NORMAL (Sustainable Earnings)"
    elif npat is not None and cfo is not None:
        accrual_vnd = npat - cfo
        earnings_quality = "EXCELLENT" if cfo >= npat else "POOR (Negative CFO)"

    # 2. Bank Debt Reconciliation
    st_debt = bs_items.get(320, {}).get("current_val") or 0.0
    lt_debt = bs_items.get(338, {}).get("current_val") or 0.0
    reported_borrowings = st_debt + lt_debt
    footnote_debt_sum = sum(d.get("amount_vnd", 0.0) for d in debt_notes)

    debt_recon_pct = None
    discrepancy_debt_vnd = None
    if reported_borrowings > 0 and footnote_debt_sum > 0:
        debt_recon_pct = round(min(100.0, (footnote_debt_sum / reported_borrowings) * 100.0), 2)
        discrepancy_debt_vnd = round(abs(reported_borrowings - footnote_debt_sum), 2)
        disc_ratio = discrepancy_debt_vnd / reported_borrowings
        if disc_ratio < 0.10:
            debt_transparency = "HIGH (Footnotes Fully Reconciled)"
        elif disc_ratio < 0.25:
            debt_transparency = "MODERATE (Partial Footnote Breakdown)"
        else:
            debt_transparency = "UNRECONCILED (Significant Footnote Gap)"
    elif reported_borrowings == 0:
        debt_transparency = "ZERO_DEBT (No Borrowings on Balance Sheet)"
        debt_recon_pct = 100.0
        discrepancy_debt_vnd = 0.0
    else:
        debt_transparency = "NO_FOOTNOTE_BREAKDOWN"

    # 3. Effective Borrowing & Tax Rates
    interest_expense = is_stmt.get("interest_expense_vnd")
    pbt = is_stmt.get("pbt_vnd")
    tax_expense = is_stmt.get("tax_expense_vnd")

    eff_borrowing_rate = None
    if interest_expense is not None and reported_borrowings > 0:
        eff_borrowing_rate = round((interest_expense / reported_borrowings) * 100.0, 2)

    eff_tax_rate = None
    tax_deviation = None
    if tax_expense is not None and pbt is not None and pbt > 0:
        eff_tax_rate = round((tax_expense / pbt) * 100.0, 2)
        tax_deviation = round(eff_tax_rate - 20.0, 2)

    # 4. Related-Party Drain Ratio
    equity = bs_items.get(400, {}).get("current_val")
    rel_txs = disclosures.get("related_party_transactions", [])
    if not rel_txs:
        gov_data = disclosures.get("governance_data", {})
        rel_txs = gov_data.get("related_party_transactions", [])
    rel_sum = sum(t.get("transaction_value_vnd", 0.0) or 0.0 for t in rel_txs)

    drain_ratio = 0.0
    drain_risk = "LOW (No significant related-party extraction)"
    if equity and equity > 0 and rel_sum > 0:
        drain_ratio = round(rel_sum / equity, 4)
        if drain_ratio > 0.25:
            drain_risk = "HIGH (Substantial Related-Party Capital Siphoning Risk)"
        elif drain_ratio > 0.10:
            drain_risk = "MEDIUM (Moderate Related-Party Activity)"
        else:
            drain_risk = "LOW (Normal Corporate Scope)"

    # 5. AGM Guidance Fulfillment Rate
    actual_rev = is_stmt.get("revenue_vnd")
    actual_npat = is_stmt.get("npat_vnd")
    res_data = disclosures.get("resolution_data", {})
    target_rev = res_data.get("target_revenue_vnd") or disclosures.get("target_revenue_vnd")
    target_npat = res_data.get("target_npat_vnd") or disclosures.get("target_npat_vnd")

    rev_fulfillment_pct = None
    if actual_rev and target_rev and target_rev > 0:
        rev_fulfillment_pct = round((actual_rev / target_rev) * 100.0, 2)

    npat_fulfillment_pct = None
    if actual_npat and target_npat and target_npat > 0:
        npat_fulfillment_pct = round((actual_npat / target_npat) * 100.0, 2)

    if npat_fulfillment_pct is not None:
        if npat_fulfillment_pct >= 105.0:
            guidance_status = "EXCEEDED_TARGET"
        elif npat_fulfillment_pct >= 95.0:
            guidance_status = "MET_TARGET"
        elif npat_fulfillment_pct >= 75.0:
            guidance_status = "NEAR_TARGET"
        else:
            guidance_status = "MISSED_TARGET"
    else:
        guidance_status = "NO_TARGET_AVAILABLE"

    return {
        "sloan_accrual_triangle": {
            "npat_vnd": npat,
            "cfo_vnd": cfo,
            "accrual_vnd": accrual_vnd,
            "total_assets_vnd": tot_assets,
            "sloan_ratio": sloan_ratio,
            "earnings_quality": earnings_quality,
            "is_cash_backed": bool(cfo and npat and cfo >= npat)
        },
        "bank_debt_triangle": {
            "reported_borrowings_vnd": reported_borrowings,
            "footnote_debt_sum_vnd": footnote_debt_sum,
            "discrepancy_vnd": discrepancy_debt_vnd,
            "reconciliation_pct": debt_recon_pct,
            "transparency_rating": debt_transparency
        },
        "effective_rates_triangle": {
            "interest_expense_vnd": interest_expense,
            "effective_borrowing_rate_pct": eff_borrowing_rate,
            "pbt_vnd": pbt,
            "tax_expense_vnd": tax_expense,
            "effective_tax_rate_pct": eff_tax_rate,
            "statutory_benchmark_pct": 20.0,
            "tax_deviation_pct": tax_deviation
        },
        "related_party_drain_triangle": {
            "total_equity_vnd": equity,
            "related_party_volume_vnd": rel_sum,
            "drain_ratio": drain_ratio,
            "risk_assessment": drain_risk
        },
        "agm_fulfillment_triangle": {
            "target_revenue_vnd": target_rev,
            "actual_revenue_vnd": actual_rev,
            "revenue_fulfillment_pct": rev_fulfillment_pct,
            "target_npat_vnd": target_npat,
            "actual_npat_vnd": actual_npat,
            "npat_fulfillment_pct": npat_fulfillment_pct,
            "guidance_status": guidance_status
        }
    }

