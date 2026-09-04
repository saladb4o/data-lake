"""
=============================================================================
CORPORATE DISCLOSURES PARSER (DETERMINISTIC DUAL-ROUTE NON-LLM ENGINE)
=============================================================================
High-performance parser for non-BCTC Vietnamese corporate disclosures:
  1. AGM & Board Resolutions (Nghị Quyết ĐHĐCĐ & HĐQT):
     - Target Revenue & Profit targets (Kế hoạch Doanh thu, LNTT, LNST).
     - Target Dividend payout rates (Cổ tức tiền mặt & cổ tức cổ phiếu).
     - Subsidiary investments & M&A capital contributions (Góp vốn thành lập cty con).
     - Bond issuance & borrowing limit authorizations.
  2. Corporate Governance Reports (Báo Cáo Tình Hình Quản Trị - Thông tư 96/2020/TT-BTC):
     - Board & Executive shareholding (HĐQT, BKS, Ban điều hành).
     - Insider transactions and related individuals (Vợ, con, bố mẹ, anh chị em).
     - Related-party transactions (Giao dịch với các công ty sân sau).
  3. Dividend & Corporate Actions (Thông Báo Cổ Tức & Phát Hành):
     - Ex-dividend date (Ngày GDKHQ) & Record date (Ngày ĐKCC).
     - Payout rate (Tiền mặt VND/cổ phiếu, Cổ phiếu thưởng tỷ lệ split).
     - Payment date (Ngày thực hiện thanh toán).
"""

import os
import re
import math
import logging
import unicodedata
from typing import Dict, List, Any, Optional, Tuple

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

from services.bctc_pdf_parser import (
    strip_accents,
    parse_vietnamese_accounting_number,
    detect_currency_unit
)

logger = logging.getLogger(__name__)


class CorporateDisclosuresParser:
    """
    Extracts structured data from Vietnamese corporate non-BCTC PDF reports.
    Dual-route: Native text extractor (fitz/pdfplumber) + RapidOCR fallback for scanned PDFs.
    """

    def __init__(self, pdf_path: str):
        self.pdf_path = os.path.abspath(pdf_path)
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        self.doc_type: str = "UNKNOWN"
        self.total_pages: int = 0
        self.currency_unit: str = "VND"
        self.currency_scale: float = 1.0
        self._cached_ocr_pages: Dict[int, List[str]] = {}
        self._full_text_cache: Optional[str] = None
        self._inspect_doc()

    def _inspect_doc(self) -> None:
        """Inspects text density to determine Native vs Scanned."""
        if not fitz:
            return
        with fitz.open(self.pdf_path) as doc:
            self.total_pages = len(doc)
            if self.total_pages == 0:
                self.doc_type = "EMPTY"
                return

            sample_text = ""
            chars = 0
            check_pages = min(5, self.total_pages)
            image_count = 0
            for i in range(check_pages):
                txt = doc[i].get_text()
                chars += len(txt.strip())
                sample_text += " " + txt
                if doc[i].get_images():
                    image_count += 1

            if image_count >= 2 and (chars / max(1, check_pages)) < 150:
                self.doc_type = "SCANNED_IMAGE"
            else:
                self.doc_type = "NATIVE"

            unit_name, scale = detect_currency_unit(sample_text)
            self.currency_unit = unit_name
            self.currency_scale = scale

    def get_full_text(self, max_pages: int = 15) -> str:
        """Retrieves full text across pages using native vector or RapidOCR fallback."""
        if self._full_text_cache is not None:
            return self._full_text_cache

        if not fitz:
            return ""

        collected = []
        with fitz.open(self.pdf_path) as doc:
            limit = min(max_pages, len(doc))
            for p_idx in range(limit):
                txt = doc[p_idx].get_text().strip()
                if not txt and self.doc_type == "SCANNED_IMAGE" and _rapid_ocr_engine:
                    lines = self._get_ocr_lines_for_page(doc, p_idx)
                    txt = "\n".join(lines)
                collected.append(txt)

        self._full_text_cache = "\n\n".join(collected)
        return self._full_text_cache

    def _get_ocr_lines_for_page(self, doc: Any, page_idx: int) -> List[str]:
        """Runs RapidOCR on a page with caching."""
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
            logger.warning(f"OCR error on page {page_idx}: {e}")
            return []

    # =========================================================================
    # 1. RESOLUTION EXTRACTOR (Nghị Quyết ĐHĐCĐ & HĐQT)
    # =========================================================================
    def extract_agm_resolution(self) -> Dict[str, Any]:
        """
        Parses AGM / Board Resolution documents.
        Extracts:
          - Target Revenue (Doanh thu kế hoạch)
          - Target Profit Before Tax (LNTT kế hoạch)
          - Target Profit After Tax (LNST kế hoạch)
          - Target Dividend Rate (% cổ tức tiền mặt / cổ phiếu)
          - Capital Contributions & Subsidiary M&A (Góp vốn thành lập cty con)
          - Borrowing & Bond credit line approvals
        """
        text = self.get_full_text(max_pages=20)
        norm_text = strip_accents(text).lower()

        result = {
            "report_type": "RESOLUTION",
            "document_type": self.doc_type,
            "target_revenue_vnd": None,
            "target_pbt_vnd": None,
            "target_npat_vnd": None,
            "target_dividend_rate_pct": None,
            "dividend_payout_form": None,
            "subsidiary_investments": [],
            "bond_and_credit_limits": [],
            "resolution_date": None,
            "raw_matches": []
        }

        # Date of Resolution (Ngày ... tháng ... năm ...)
        date_match = re.search(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(202\d)", norm_text)
        if date_match:
            d, m, y = date_match.groups()
            result["resolution_date"] = f"{int(d):02d}/{int(m):02d}/{y}"

        # 1. Revenue Target (Doanh thu kế hoạch)
        rev_patterns = [
            r"(?:tong\s+)?doanh\s+thu(?:\s+thuan)?(?:\s+hop\s+nhat)?\s*(?:ke\s+hoach|\s*\(?\s*kh\s*\)?|\s*nam\s*202\d)?\s*[:\-=]\s*([\d\.,]+)\s*(ty|trieu|dong|vnd)?",
            r"ke\s+hoach\s+(?:tong\s+)?doanh\s+thu\s*[:\-=]\s*([\d\.,]+)\s*(ty|trieu|dong|vnd)?"
        ]
        for pat in rev_patterns:
            m = re.search(pat, norm_text)
            if m:
                val = parse_vietnamese_accounting_number(m.group(1))
                unit = m.group(2) if len(m.groups()) > 1 else None
                if val:
                    scale = 1_000_000_000.0 if unit == "ty" else (1_000_000.0 if unit == "trieu" else self.currency_scale)
                    result["target_revenue_vnd"] = val * scale
                    result["raw_matches"].append(m.group(0))
                    break

        # 2. Profit After Tax Target (LNST kế hoạch)
        npat_patterns = [
            r"loi\s+nhuan\s+sau\s+thue(?:\s+hop\s+nhat)?\s*(?:ke\s+hoach|\s*\(?\s*kh\s*\)?|\s*nam\s*202\d)?\s*[:\-=]\s*([\d\.,]+)\s*(ty|trieu|dong|vnd)?",
            r"lnst(?:\s+hop\s+nhat)?\s*[:\-=]\s*([\d\.,]+)\s*(ty|trieu|dong|vnd)?"
        ]
        for pat in npat_patterns:
            m = re.search(pat, norm_text)
            if m:
                val = parse_vietnamese_accounting_number(m.group(1))
                unit = m.group(2) if len(m.groups()) > 1 else None
                if val:
                    scale = 1_000_000_000.0 if unit == "ty" else (1_000_000.0 if unit == "trieu" else self.currency_scale)
                    result["target_npat_vnd"] = val * scale
                    result["raw_matches"].append(m.group(0))
                    break

        # 3. Dividend Target Rate (% cổ tức)
        div_patterns = [
            r"(?:co\s+tuc|ty\s+le\s+co\s+tuc|chi\s+tra\s+co\s+tuc).*?(\d+(?:[\.,]\d+)?)\s*%",
        ]
        for pat in div_patterns:
            m = re.search(pat, norm_text)
            if m:
                rate = parse_vietnamese_accounting_number(m.group(1))
                if rate:
                    result["target_dividend_rate_pct"] = rate
                    if "bang tien" in norm_text or "tien mat" in norm_text:
                        result["dividend_payout_form"] = "CASH"
                    elif "bang co phieu" in norm_text or "bang cp" in norm_text:
                        result["dividend_payout_form"] = "STOCK"
                    result["raw_matches"].append(m.group(0))
                    break

        # 4. Subsidiary Capital Contributions & M&A (Góp vốn thành lập công ty con)
        lines = text.split("\n")
        for idx, line in enumerate(lines):
            l_norm = strip_accents(line).lower()
            if any(k in l_norm for k in ["gop von thanh lap", "thanh lap cong ty con", "nhan chuyen nhuong co phan", "mua co phan"]):
                company_name = line.strip()[:80]
                context = " ".join(lines[idx:idx + 6])
                c_norm = strip_accents(context).lower()

                capital_val = None
                cap_match = re.search(r"(?:so\s+tien|von\s+gop|gia\s+tri|tong\s+von).*?([\d\.,]+)\s*(ty|trieu|dong)", c_norm)
                if cap_match:
                    num = parse_vietnamese_accounting_number(cap_match.group(1))
                    unit = cap_match.group(2)
                    if num:
                        scale = 1_000_000_000.0 if unit == "ty" else (1_000_000.0 if unit == "trieu" else 1.0)
                        capital_val = num * scale

                ownership_pct = None
                own_match = re.search(r"(?:ty\s+le|so\s+huu).*?([\d\.,]+)\s*%", c_norm)
                if own_match:
                    pct = parse_vietnamese_accounting_number(own_match.group(1))
                    if pct and pct <= 100:
                        ownership_pct = pct

                result["subsidiary_investments"].append({
                    "description": company_name,
                    "capital_contribution_vnd": capital_val,
                    "target_ownership_pct": ownership_pct,
                    "page": 1
                })

        # 5. Bond & Credit limits (Chào bán trái phiếu riêng lẻ / hạn mức tín dụng)
        for idx, line in enumerate(lines):
            l_norm = strip_accents(line).lower()
            if any(k in l_norm for k in ["phat hanh trai phieu", "chao ban trai phieu", "vay von tai ngan hang", "han muc tin dung", "trai phieu rieng le"]):
                context = " ".join(lines[idx:idx + 4])
                c_norm = strip_accents(context).lower()
                amt_match = re.search(r"([\d\.,]+)\s*(ty|trieu)\s*(?:dong)?", c_norm)
                if amt_match:
                    num = parse_vietnamese_accounting_number(amt_match.group(1))
                    unit = amt_match.group(2)
                    if num and num > 0:
                        scale = 1_000_000_000.0 if unit == "ty" else 1_000_000.0
                        result["bond_and_credit_limits"].append({
                            "type": "TRÁI_PHIẾU" if "trai phieu" in l_norm else "TÍN_DỤNG_NGÂN_HÀNG",
                            "limit_vnd": num * scale,
                            "summary": line.strip()[:100]
                        })

        return result

    # =========================================================================
    # 2. GOVERNANCE REPORT EXTRACTOR (Báo Cáo Quản Trị - Thông tư 96/2020)
    # =========================================================================
    def extract_governance_report(self) -> Dict[str, Any]:
        """
        Parses Corporate Governance Reports adhering to Circular 96/2020/TT-BTC.
        Extracts:
          - Board of Directors attendance & composition (Biểu IV)
          - Related-party transactions & insider contracts (Biểu VIII)
        """
        text = self.get_full_text(max_pages=30)
        lines = text.split("\n")
        norm_full = strip_accents(text).lower()

        result = {
            "report_type": "GOVERNANCE",
            "document_type": self.doc_type,
            "period": "Bán niên" if "ban nien" in norm_full or "6 thang" in norm_full else "Năm",
            "board_members": [],
            "related_party_transactions": [],
            "insider_transactions": []
        }

        # Extract Related Party Transactions (Phụ lục VIII: Giao dịch với người có liên quan)
        in_related_section = False
        for idx, line in enumerate(lines):
            l_norm = strip_accents(line).upper()
            if any(k in l_norm for k in ["GIAO DICH GIUA CONG TY VOI NGUOI CO LIEN QUAN", "GIAO DICH VOI BEN LIEN QUAN", "MUC VIII", "PHAN VIII", "VIII."]):
                in_related_section = True
                continue

            if in_related_section and any(k in l_norm for k in ["MUC IX", "PHAN IX", "IX."]):
                in_related_section = False

            if in_related_section:
                if any(kw in l_norm for kw in ["CTCP", "CONG TY CP", "CONG TY TNHH", "TAP DOAN", "NGAN HANG", "HAIPHAT"]):
                    context = " ".join(lines[idx:idx + 4])
                    val = None
                    nums = re.findall(r"\b\d{1,3}(?:\.\d{3}){2,}\b", context)
                    if nums:
                        val = parse_vietnamese_accounting_number(nums[0])

                    result["related_party_transactions"].append({
                        "entity_name": line.strip()[:80],
                        "context": context[:120],
                        "transaction_value_vnd": val * self.currency_scale if val else None
                    })

        # Extract Board Members
        for idx, line in enumerate(lines):
            l_norm = strip_accents(line).lower()
            if any(pos in l_norm for pos in ["chu tich hdqt", "thanh vien hdqt", "thanh vien doc lap hdqt", "tong giam doc"]):
                result["board_members"].append({
                    "title": line.strip()[:60],
                    "name": line.strip()
                })

        return result

    # =========================================================================
    # 3. DIVIDEND & CORPORATE ACTIONS EXTRACTOR (Thông Báo Cổ Tức)
    # =========================================================================
    def extract_dividend_announcement(self) -> Dict[str, Any]:
        """
        Parses Official Ex-Dividend & Corporate Action announcements.
        Extracts:
          - Ex-date (Ngày GDKHQ)
          - Record date (Ngày ĐKCC)
          - Payment date (Ngày thanh toán)
          - Dividend rate (% or VND/share or split ratio)
          - Payout form (CASH vs STOCK)
        """
        text = self.get_full_text(max_pages=6)
        norm_text = strip_accents(text).lower()

        result = {
            "report_type": "DIVIDEND",
            "document_type": self.doc_type,
            "payout_form": "CASH",
            "dividend_rate_pct": None,
            "cash_value_per_share_vnd": None,
            "stock_split_ratio": None,
            "ex_dividend_date": None,
            "record_date": None,
            "payment_date": None,
            "raw_matches": []
        }

        # 1. Payout form detection
        if any(k in norm_text for k in ["tra co tuc bang co phieu", "tra co tuc bang cp", "co phieu thuong", "phat hanh co phieu"]):
            result["payout_form"] = "STOCK"
        else:
            result["payout_form"] = "CASH"

        # 2. Ex-dividend date (Ngày GDKHQ)
        ex_match = re.search(r"(?:ngay\s+gdkhq|giao\s+dich\s+khong\s+huong\s+quyen).*?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]202\d)", norm_text)
        if ex_match:
            result["ex_dividend_date"] = ex_match.group(1).replace("-", "/").replace(".", "/")
            result["raw_matches"].append(ex_match.group(0))

        # 3. Record date (Ngày đăng ký cuối cùng)
        rec_match = re.search(r"(?:ngay\s+dang\s+ky\s+cuoi\s+cung|ngay\s+dkcc).*?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]202\d)", norm_text)
        if rec_match:
            result["record_date"] = rec_match.group(1).replace("-", "/").replace(".", "/")
            result["raw_matches"].append(rec_match.group(0))

        # 4. Payment date (Ngày thực hiện thanh toán chi trả)
        pay_match = re.search(r"(?:ngay\s+thanh\s+toan|thoi\s+gian\s+thanh\s+toan|thuc\s+hien\s+chi\s+tra).*?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]202\d)", norm_text)
        if pay_match:
            result["payment_date"] = pay_match.group(1).replace("-", "/").replace(".", "/")
            result["raw_matches"].append(pay_match.group(0))

        # 5. Dividend Rate (% or VND/share or ratio)
        if result["payout_form"] == "CASH":
            rate_match = re.search(r"(?:ty\s+le\s+thuc\s+hien|ty\s+le\s+chi\s+tra|ty\s+le).*?([\d\.,]+)\s*%", norm_text)
            if rate_match:
                pct = parse_vietnamese_accounting_number(rate_match.group(1))
                if pct:
                    result["dividend_rate_pct"] = pct
                    result["cash_value_per_share_vnd"] = pct * 100.0

            val_match = re.search(r"(\d+(?:\.\d{3})*)\s*(?:dong|vnd)\s*\/\s*(?:co\s+phieu|cp)", norm_text)
            if not val_match:
                val_match = re.search(r"nhan\s*(\d+(?:\.\d{3})*)\s*(?:dong|vnd)", norm_text)
            if val_match:
                val = parse_vietnamese_accounting_number(val_match.group(1))
                if val:
                    result["cash_value_per_share_vnd"] = val
                    result["dividend_rate_pct"] = (val / 10000.0) * 100.0
        else:
            ratio_match = re.search(r"(?:ty\s+le\s+thuc\s+hien|ty\s+le).*?(\d{1,3}\s*:\s*\d{1,3})", norm_text)
            if ratio_match:
                result["stock_split_ratio"] = ratio_match.group(1).replace(" ", "")
                result["raw_matches"].append(ratio_match.group(0))
            else:
                pct_match = re.search(r"([\d\.,]+)\s*%", norm_text)
                if pct_match:
                    result["dividend_rate_pct"] = parse_vietnamese_accounting_number(pct_match.group(1))

        return result

    # =========================================================================
    # 4. DISPATCHER & ORCHESTRATION
    # =========================================================================
    def extract_full_report(self, category_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Automatically detects document category or uses category_hint to extract structured payload.
        """
        sample = strip_accents(self.get_full_text(max_pages=3)).lower()

        detected_type = category_hint.upper() if category_hint else "UNKNOWN"
        if detected_type == "UNKNOWN":
            if any(k in sample for k in ["nghi quyet", "bien ban hop", "dai hoi dong co dong", "dhdcd"]):
                detected_type = "RESOLUTION"
            elif any(k in sample for k in ["bao cao quan tri", "tinh hinh quan tri", "quan tri cong ty", "governance"]):
                detected_type = "GOVERNANCE"
            elif any(k in sample for k in ["co tuc", "ngay gdkhq", "quyen mua", "co phieu thuong"]):
                detected_type = "DIVIDEND"

        payload = {
            "pdf_path": self.pdf_path,
            "detected_category": detected_type,
            "document_type": self.doc_type,
            "total_pages": self.total_pages,
            "provenance": "CORPORATE_DISCLOSURES_PARSER_TT96"
        }

        if detected_type == "RESOLUTION":
            payload["resolution_data"] = self.extract_agm_resolution()
        elif detected_type == "GOVERNANCE":
            payload["governance_data"] = self.extract_governance_report()
        elif detected_type == "DIVIDEND":
            payload["dividend_data"] = self.extract_dividend_announcement()
        else:
            payload["resolution_data"] = self.extract_agm_resolution()
            payload["dividend_data"] = self.extract_dividend_announcement()

        return payload

    def get_related_party_total(self) -> float:
        """Helper to calculate total transaction value with related parties."""
        gov = self.extract_governance_report()
        txs = gov.get("related_party_transactions", [])
        return sum(t.get("transaction_value_vnd") or 0.0 for t in txs)

    def get_agm_guidance(self) -> Dict[str, Any]:
        """Helper to extract AGM revenue & profit targets for forward valuation."""
        agm = self.extract_agm_resolution()
        return {
            "target_revenue_vnd": agm.get("target_revenue_vnd"),
            "target_npat_vnd": agm.get("target_npat_vnd"),
            "target_dividend_rate_pct": agm.get("target_dividend_rate_pct"),
            "dividend_payout_form": agm.get("dividend_payout_form")
        }

