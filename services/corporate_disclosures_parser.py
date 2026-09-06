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
            check_pages = min(8, self.total_pages)
            text_rich_pages = 0
            for i in range(check_pages):
                txt = doc[i].get_text().strip()
                chars += len(txt)
                sample_text += " " + txt
                if len(txt) > 150:
                    text_rich_pages += 1

            if text_rich_pages >= 2 or (chars / max(1, check_pages)) > 80:
                self.doc_type = "NATIVE"
            else:
                self.doc_type = "SCANNED_IMAGE"

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
                if (not txt or len(txt) < 120) and _rapid_ocr_engine:
                    lines = self._get_ocr_lines_for_page(doc, p_idx)
                    if lines:
                        txt = txt + "\n" + "\n".join(lines) if txt else "\n".join(lines)
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
        # Normalize frequent OCR misreadings
        norm_text = re.sub(r"l[qg]i\s*nhu[a-z\?]*n", "loi nhuan", norm_text)
        norm_text = re.sub(r"thu[5e]", "thue", norm_text)
        norm_text = re.sub(r"d[6o1]ng", "dong", norm_text)
        norm_text = re.sub(r"c[6o]\s*t[i1u]rc", "co tuc", norm_text)
        norm_text = re.sub(r"k[eê]\s*ho[aạ]ch", "ke hoach", norm_text)

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
            r"(?:tong\s+)?doanh\s+thu(?:\s+thuan)?(?:\s+hop\s+nhat)?\s*(?:ke\s+hoach|\s*\(?\s*kh\s*\)?|\s*nam\s*202\d)?\s*[:\-=]\s*([\d\.,'\s]+)\s*(ty|trieu|dong|vnd)?",
            r"ke\s+hoach\s+(?:tong\s+)?(?:doanh\s+thu|sxkd|kinh\s+doanh)\s*[:\-=]\s*([\d\.,'\s]+)\s*(ty|trieu|dong|vnd)?",
            r"tong\s+doanh\s+thu\s*[:\-=]\s*([\d\.,'\s]+)\s*(ty|trieu|dong|vnd)?"
        ]
        for pat in rev_patterns:
            m = re.search(pat, norm_text)
            if m:
                val = parse_vietnamese_accounting_number(m.group(1))
                unit = m.group(2) if len(m.groups()) > 1 else None
                if val:
                    scale = 1_000_000_000.0 if unit == "ty" else (1_000_000.0 if unit == "trieu" else (1.0 if val > 1_000_000 else self.currency_scale))
                    result["target_revenue_vnd"] = val * scale
                    result["raw_matches"].append(m.group(0))
                    break

        # 2. Profit After Tax Target (LNST kế hoạch)
        npat_patterns = [
            r"loi\s+nhuan\s+sau\s+thue(?:\s+hop\s+nhat)?\s*(?:ke\s+hoach|\s*\(?\s*kh\s*\)?|\s*nam\s*202\d)?\s*[:\-=]\s*([\d\.,'\s]+)\s*(ty|trieu|dong|vnd)?",
            r"lnst(?:\s+hop\s+nhat)?\s*[:\-=]\s*([\d\.,'\s]+)\s*(ty|trieu|dong|vnd)?",
            r"loi\s+nhuan\s+truoc\s+thue(?:\s+hop\s+nhat)?\s*[:\-=]\s*([\d\.,'\s]+)\s*(ty|trieu|dong|vnd)?",
            r"tong\s+loi\s+nhuan\s+(?:sau\s+thue|phan\s+phoi)\s*[:\-=]\s*([\d\.,'\s]+)\s*(ty|trieu|dong|vnd)?"
        ]
        for pat in npat_patterns:
            m = re.search(pat, norm_text)
            if m:
                val = parse_vietnamese_accounting_number(m.group(1))
                unit = m.group(2) if len(m.groups()) > 1 else None
                if val:
                    scale = 1_000_000_000.0 if unit == "ty" else (1_000_000.0 if unit == "trieu" else (1.0 if val > 1_000_000 else self.currency_scale))
                    result["target_npat_vnd"] = val * scale
                    result["raw_matches"].append(m.group(0))
                    break

        # 3. Dividend Target Rate (% cổ tức)
        div_patterns = [
            r"(?:co\s+tuc|ty\s+le\s+co\s+tuc|chi\s+tra\s+co\s+tuc|tra\s+co\s+tuc).*?([\d\.,]+)\s*%",
            r"co\s+tuc.*?(\d{1,2}(?:[\.,]\d+)?)\s*%",
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
        text = self.get_full_text(max_pages=10)
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

        # Micro-extractors: Family Network, Insider Deals, Free Float
        result["family_network"] = self.extract_insider_family_network()
        result["insider_transactions"] = self.extract_insider_trading_history()
        result["free_float_structure"] = self.extract_free_float_breakdown()

        return result

    def extract_insider_family_network(self) -> List[Dict[str, Any]]:
        """
        Micro-Extractor: Parses Insider Related-Persons & Family Network (Biểu VIII - TT96/2020).
        Extracts: Insider Name, Related Person Name, Relation (Vợ, Chồng, Con, Cha/Mẹ, Anh/Em), Shares, Ownership %.
        """
        text = self.get_full_text(max_pages=35)
        lines = text.split("\n")
        family_network = []

        family_relation_keywords = [
            ("vo", "Vợ"), ("chong", "Chồng"), ("con gai", "Con gái"), ("con trai", "Con trai"),
            ("con de", "Con"), ("con", "Con"), ("me de", "Mẹ"), ("cha de", "Bố"),
            ("bo de", "Bố"), ("me", "Mẹ"), ("cha", "Bố"), ("bo", "Bố"),
            ("anh ruot", "Anh ruột"), ("em ruot", "Em ruột"), ("chi ruot", "Chị ruột"),
            ("em trai", "Em trai"), ("em gai", "Em gái"), ("anh trai", "Anh trai"), ("chi gai", "Chị gái")
        ]

        current_insider = ""
        current_role = ""

        for idx, line in enumerate(lines):
            l_norm = strip_accents(line).lower().strip()

            # Detect Insider Section / Leader Name
            for role_kw in ["chu tich", "thanh vien hdqt", "tong giam doc", "pho tong giam doc", "thanh vien bks", "ke toan truong"]:
                if role_kw in l_norm and len(line.strip()) < 80:
                    current_insider = line.strip()
                    current_role = role_kw.title()
                    break

            # Check if line contains family relationship
            for rel_kw, rel_label in family_relation_keywords:
                pattern = rf"\b{rel_kw}\b"
                if re.search(pattern, l_norm):
                    context = " ".join(lines[max(0, idx - 1):min(len(lines), idx + 4)])

                    # Extract shares or percentage
                    shares = None
                    nums = re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", context)
                    if nums:
                        val = parse_vietnamese_accounting_number(nums[0])
                        if val and val > 0:
                            shares = int(val)

                    pct = None
                    pct_m = re.findall(r"\b(\d{1,2}(?:\.\d{1,2})?|100(?:\.0{1,2})?)\s*%", context)
                    if pct_m:
                        try:
                            pct = float(pct_m[0].replace(",", "."))
                        except Exception:
                            pass

                    # Extract Person Name from line
                    person_name = line.strip()
                    for kw_clean in [rel_kw, "ong", "ba", "la"]:
                        person_name = re.sub(rf"(?i)\b{kw_clean}\b", "", person_name).strip(" :-–—")

                    if len(person_name) >= 3 and len(person_name) <= 50:
                        family_network.append({
                            "insider_name": current_insider or "Ban Lãnh Đạo",
                            "insider_role": current_role or "Lãnh đạo",
                            "related_person_name": person_name,
                            "relationship": rel_label,
                            "shares_owned": shares,
                            "ownership_pct": pct
                        })
                    break

        seen = set()
        deduped = []
        for f in family_network:
            k = (f["related_person_name"].lower(), f["relationship"])
            if k not in seen:
                seen.add(k)
                deduped.append(f)

        return deduped

    def extract_insider_trading_history(self) -> List[Dict[str, Any]]:
        """
        Micro-Extractor: Parses Insider & Related-Persons Deal Flow (Biểu VII - TT96/2020).
        Extracts: Trader, Action (Mua/Bán), Registered shares, Executed shares, Completion Rate.
        """
        text = self.get_full_text(max_pages=35)
        lines = text.split("\n")
        deals = []

        for idx, line in enumerate(lines):
            l_norm = strip_accents(line).lower()
            if any(k in l_norm for k in ["mua", "ban", "chuyen nhuong", "nhan chuyen nhuong"]) and any(w in l_norm for w in ["co phieu", "cp", "so luong"]):
                context = " ".join(lines[max(0, idx - 1):min(len(lines), idx + 5)])

                action = "BUY" if "mua" in l_norm or "nhan chuyen nhuong" in l_norm else "SELL"

                nums = re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", context)
                registered = parse_vietnamese_accounting_number(nums[0]) if len(nums) > 0 else None
                executed = parse_vietnamese_accounting_number(nums[1]) if len(nums) > 1 else registered

                completion_rate = None
                if registered and executed and registered > 0:
                    completion_rate = round(min(100.0, (executed / registered) * 100.0), 2)

                deals.append({
                    "trader_name": line.strip()[:60],
                    "action_type": action,
                    "registered_shares": int(registered) if registered else None,
                    "executed_shares": int(executed) if executed else None,
                    "completion_rate_pct": completion_rate,
                    "summary": context[:120]
                })

        seen = set()
        deduped = []
        for d in deals:
            k = (d["trader_name"][:25], d["action_type"], d["executed_shares"])
            if k not in seen:
                seen.add(k)
                deduped.append(d)

        return deduped

    def extract_free_float_breakdown(self) -> Dict[str, Any]:
        """
        Micro-Extractor: Calculates Shareholder Structure & True Free-Float Ratio.
        Analyzes State %, Foreign %, Insiders & Family %, Institutional %, and Free-Float %.
        """
        text = self.get_full_text(max_pages=25)
        norm_text = strip_accents(text).lower()

        state_pct = 0.0
        foreign_pct = 0.0
        insider_pct = 0.0
        institutional_pct = 0.0

        st_match = re.search(r"(?:nha\s+nuoc|co\s+dong\s+nha\s+nuoc|scic).*?(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", norm_text)
        if st_match:
            state_pct = parse_vietnamese_accounting_number(st_match.group(1)) or 0.0

        fn_match = re.search(r"(?:nuoc\s+ngoai|nha\s+dau\s+tu\s+nuoc\s+ngoai|foreign).*?(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", norm_text)
        if fn_match:
            foreign_pct = parse_vietnamese_accounting_number(fn_match.group(1)) or 0.0

        in_match = re.search(r"(?:ban\s+lanh\s+dao|hdqt|nguoi\s+noi\s+bo).*?(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", norm_text)
        if in_match:
            insider_pct = parse_vietnamese_accounting_number(in_match.group(1)) or 0.0

        locked_pct = min(95.0, state_pct + foreign_pct * 0.7 + insider_pct)
        true_free_float_pct = round(max(5.0, 100.0 - locked_pct), 2)

        return {
            "state_ownership_pct": round(state_pct, 2),
            "foreign_ownership_pct": round(foreign_pct, 2),
            "insider_ownership_pct": round(insider_pct, 2),
            "institutional_pct": round(institutional_pct, 2),
            "true_free_float_pct": true_free_float_pct,
            "liquidity_classification": "CAO (Dễ giao dịch)" if true_free_float_pct > 50 else ("TRUNG BÌNH" if true_free_float_pct > 25 else "CÔ ĐẶC (Dễ bị lái / kiểm soát cung)")
        }

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
            rate_match = re.search(r"(?:ty\s+le\s+thuc\s+hien|ty\s+le\s+chi\s+tra|ty\s+le).*?([\d\.,'\s]+)\s*%", norm_text)
            if rate_match:
                pct = parse_vietnamese_accounting_number(rate_match.group(1))
                if pct:
                    result["dividend_rate_pct"] = pct
                    result["cash_value_per_share_vnd"] = pct * 100.0
                    result["cash_payout_per_share_vnd"] = result["cash_value_per_share_vnd"]

            val_match = re.search(r"(\d+(?:[\.,]\d{3})*)\s*(?:dong|vnd)\s*\/\s*(?:co\s+phieu|cp)", norm_text)
            if not val_match:
                val_match = re.search(r"nhan\s*(\d+(?:[\.,]\d{3})*)\s*(?:dong|vnd)", norm_text)
            if val_match:
                val = parse_vietnamese_accounting_number(val_match.group(1))
                if val:
                    result["cash_value_per_share_vnd"] = val
                    result["cash_payout_per_share_vnd"] = val
                    result["dividend_rate_pct"] = (val / 10000.0) * 100.0
        else:
            ratio_match = re.search(r"(?:ty\s+le\s+thuc\s+hien|ty\s+le).*?(\d{1,3}\s*:\s*\d{1,3})", norm_text)
            if ratio_match:
                result["stock_split_ratio"] = ratio_match.group(1).replace(" ", "")
                result["raw_matches"].append(ratio_match.group(0))
            else:
                pct_match = re.search(r"([\d\.,'\s]+)\s*%", norm_text)
                if pct_match:
                    result["dividend_rate_pct"] = parse_vietnamese_accounting_number(pct_match.group(1))

        # Bilingual / English corporate dividend announcement support (e.g. CEO Group)
        if any(re.search(p, norm_text) for p in [r"share\s*issuance\s*for\s*dividend", r"shares?\s*expected\s*to\s*be\s*issued", r"tra\s*co\s*tuc"]):
            if any(k in norm_text for k in ["share", "co phieu"]) and not any(k in norm_text for k in ["tien mat", "cash"]):
                result["payout_form"] = "STOCK"
            m_iss = re.search(r"(?:shares?\s*expected\s*to\s*be\s*issued|so\s*co\s*phieu\s*du\s*kien\s*phat\s*hanh)[^\d]*([\d\.,'\s]+)", norm_text)
            m_tot = re.search(r"(?:total\s*number\s*of\s*issued\s*shares|outstanding\s*shares|tong\s*so\s*co\s*phieu\s*dang\s*luu\s*hanh)[^\d]*([\d\.,'\s]+)", norm_text)
            if m_iss and m_tot:
                iss_val = parse_vietnamese_accounting_number(m_iss.group(1))
                tot_val = parse_vietnamese_accounting_number(m_tot.group(1))
                if iss_val and tot_val and tot_val > 0:
                    pct = round((iss_val / tot_val) * 100.0, 1)
                    result["dividend_rate_pct"] = pct
                    result["stock_split_ratio"] = f"{int(round(pct))}:100"

        # English date support (e.g. Hanoi, May 26, 2026)
        if not result["record_date"] and not result["payment_date"]:
            m_en_date = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{1,2}),?\s*(202\d)", norm_text)
            if m_en_date:
                m_name, day, yr = m_en_date.groups()
                months_map = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                              "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
                m_num = months_map.get(m_name.lower(), 1)
                result["record_date"] = f"{int(day):02d}/{m_num:02d}/{yr}"

        # Filename / title hints fallback (e.g. PVS__15_9_2026__chot_DS_tra_co_tuc)
        fname = os.path.basename(self.pdf_path).lower()
        if not result["record_date"]:
            fn_date = re.search(r"(\d{1,2})[_\.\-](\d{1,2})[_\.\-](202\d)", fname)
            if fn_date:
                d, m, y = fn_date.groups()
                result["record_date"] = f"{int(d):02d}/{int(m):02d}/{y}"
        if "co phieu" in fname and result["payout_form"] == "CASH" and "tien" not in fname:
            result["payout_form"] = "STOCK"

        result["cash_payout_per_share_vnd"] = result.get("cash_value_per_share_vnd")
        return result

    # =========================================================================
    # 4. DISPATCHER & ORCHESTRATION
    # =========================================================================
    def extract_full_report(self, category_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Automatically detects document category or uses category_hint to extract structured payload.
        Both nested and root keys are populated for complete consumer compatibility.
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
            res_data = self.extract_agm_resolution()
            payload["resolution_data"] = res_data
            payload.update(res_data)
        elif detected_type == "GOVERNANCE":
            gov_data = self.extract_governance_report()
            payload["governance_data"] = gov_data
            payload.update(gov_data)
        elif detected_type == "DIVIDEND":
            div_data = self.extract_dividend_announcement()
            payload["dividend_data"] = div_data
            payload.update(div_data)
        else:
            res_data = self.extract_agm_resolution()
            div_data = self.extract_dividend_announcement()
            payload["resolution_data"] = res_data
            payload["dividend_data"] = div_data
            payload.update(res_data)
            payload.update(div_data)

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

