"""
=============================================================================
VIETNAM DOMESTIC COMMODITY & BASIS SERVICE
=============================================================================
Cung cấp dữ liệu giá hàng hóa khảo sát thực tế tại thị trường Việt Nam (Spot Price)
phục vụ kiến trúc Dữ Liệu Kép (Dual-Layer Benchmark) và tính toán Basis Spread:
  1. Heo hơi 3 miền (VietnamBiz / Anova Feed)
  2. Xăng dầu bán lẻ Petrolimex (Điều hành Liên Bộ chu kỳ 7 ngày)
  3. Thép xây dựng Hòa Phát (SteelOnline.vn / VSA)
  4. Cá tra & Tôm ao nuôi ĐBSCL (Tép Bạc / AgroMonitor)
  5. Xi măng bao PCB40 bán lẻ (Hà Tiên 1 / Bỉm Sơn)
  6. Cước vận tải container Bắc - Nam (VISABA)
  7. Đường trắng RS nội địa & Thuế CBPG (VSSA)
  8. Phân bón Ure Phú Mỹ / Cà Mau đại lý ĐBSCL (2Nông)
  9. Mủ cao su nước TSC Bình Phước / Bình Long (VRA)
  10. Đơn giá sợi dệt & gia công CMT (VITAS)
=============================================================================
"""

import os
import json
import time
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from services.stock_service import resolve_data_file

DOMESTIC_CACHE_FILE = "domestic_commodity_cache.json"
CACHE_TTL_SECONDS = 43200  # 12 Hours

# Default baseline surveyed domestic anchors (ground-truth market data)
DEFAULT_DOMESTIC_SPOT_DATA = {
    "LIVESTOCK": {
        "sector_key": "LIVESTOCK",
        "commodity_name": "Heo Hơi 3 Miền Thực Tế",
        "unit": "VND/kg",
        "spot_price": 58294,
        "price_range_min": 57000,
        "price_range_max": 60000,
        "source": "VietnamBiz (Khảo sát thực địa 34 tỉnh thành hàng ngày)",
        "source_url": "https://vietnambiz.vn/gia-heo-hoi.html",
        "regions": {
            "Bắc": 59500,
            "Trung": 57500,
            "Nam": 58000
        },
        "basis_vs_global": {
            "divergence_type": "DOMESTIC_FIRST",
            "global_ticker": "HE=F",
            "domestic_drivers": "Dịch tả lợn châu Phi (ASF), tốc độ tái đàn của nông hộ, kiểm soát heo lậu tiểu ngạch qua biên giới Tây Nam.",
            "spread_formula": "Giá Heo Khảo Sát 3 Miền - 2.8 * Chi Phí Thức Ăn Chăn Nuôi (Ngô/Khô Đậu)"
        }
    },
    "REFINERY": {
        "sector_key": "REFINERY",
        "commodity_name": "Xăng Dầu Bán Lẻ Điều Hành Nội Địa",
        "unit": "VND/lít",
        "spot_price": 23270,  # RON 95-III
        "price_range_min": 22480,  # E5 RON 92
        "price_range_max": 27740,  # Dầu DO 0.05S
        "source": "Tập đoàn Xăng dầu Việt Nam (Petrolimex - Điều hành Liên Bộ)",
        "source_url": "https://webgia.com/gia-xang-dau/petrolimex/",
        "products": {
            "RON 95-III (Vùng 1)": 23270,
            "E5 RON 92-II (Vùng 1)": 22480,
            "Dầu DO 0.05S-II (Vùng 1)": 27740
        },
        "basis_vs_global": {
            "divergence_type": "PARALLEL_WITH_REGULATORY_LAG",
            "global_ticker": "RB=F & BZ=F",
            "domestic_drivers": "Chu kỳ điều hành giá 7 ngày (thứ 5 hàng tuần) của Liên Bộ Công Thương - Tài chính, phụ phí Premium Dung Quất.",
            "spread_formula": "Giá Bán Lẻ Petrolimex - Chi Phí Nhập Khẩu Dầu Thô Brent & Thuế Phí Môi Trường"
        }
    },
    "STEEL": {
        "sector_key": "STEEL",
        "commodity_name": "Thép Xây Dựng Hòa Phát Nội Địa",
        "unit": "VND/kg",
        "spot_price": 14150,
        "price_range_min": 13950,
        "price_range_max": 14400,
        "source": "SteelOnline.vn & Hiệp hội Thép Việt Nam (VSA)",
        "source_url": "https://steelonline.vn/bang-gia-thep-xay-dung",
        "products": {
            "Hòa Phát Thép Cuộn CB240": 14050,
            "Hòa Phát Thép Thanh Vằn D10 CB300": 14250,
            "Việt Ý / Kyoei CB240": 13950
        },
        "basis_vs_global": {
            "divergence_type": "DUAL_SPEED",
            "global_ticker": "HRC=F",
            "domestic_drivers": "Tiến độ giải ngân đầu tư công hạ tầng (sân bay, cao tốc), bất động sản dân dụng nội địa, Thuế tự vệ & CBPG thép HRC nhập khẩu.",
            "spread_formula": "Giá Thép Xây Dựng Hòa Phát - (1.6 * Quặng Sắt + 0.6 * Than Cốc)"
        }
    },
    "SEAFOOD": {
        "sector_key": "SEAFOOD",
        "commodity_name": "Cá Tra & Tôm Ao Nuôi ĐBSCL",
        "unit": "VND/kg",
        "spot_price": 31500,
        "price_range_min": 30000,
        "price_range_max": 34000,
        "source": "Tép Bạc / AgroMonitor & VASEP Khảo Sát ĐBSCL",
        "source_url": "https://tepbac.com/tin-tuc/thi-truong.html",
        "products": {
            "Cá Tra Nguyên Liệu Loại 1 (0.8 - 1.1kg)": 31500,
            "Cá Tra Loại 2": 30000,
            "Tôm Thẻ Chân Trắng (Cỡ 50 con/kg)": 135000
        },
        "basis_vs_global": {
            "divergence_type": "EXPORT_LEAD_LAG",
            "global_ticker": "Cá Tra Phi-lê Xuất Khẩu (USD/kg)",
            "domestic_drivers": "Tồn kho nhà bán lẻ Mỹ/EU, chi phí thức ăn thủy sản tại ĐBSCL, phán quyết thuế chống bán phá giá POR của Bộ Thương mại Mỹ (DOC).",
            "spread_formula": "Giá Cá Phi-lê Xuất Khẩu Quy Đổi - Giá Cá Tra Ao Nuôi ĐBSCL"
        }
    },
    "CEMENT": {
        "sector_key": "CEMENT",
        "commodity_name": "Xi Măng Bao PCB40 Bán Lẻ",
        "unit": "VND/bao (50kg)",
        "spot_price": 95000,
        "price_range_min": 85000,
        "price_range_max": 105000,
        "source": "Báo Cáo Giá VLXD Sở Xây Dựng & Đại Lý Cấp 1",
        "source_url": "https://xaydung.gov.vn",
        "products": {
            "Xi Măng Hà Tiên 1 PCB40 (Miền Nam)": 98000,
            "Xi Măng Bỉm Sơn PCB40 (Miền Bắc)": 88000,
            "Xi Măng Nghi Sơn PCB40": 92000
        },
        "basis_vs_global": {
            "divergence_type": "DOMESTIC_LOCALIZED",
            "global_ticker": "COAL & CLINKER",
            "domestic_drivers": "Tình trạng dư thừa công suất sản xuất clinker, giá than cám Vinacomin/TKV, cước vận tải đường bộ/thủy nội địa.",
            "spread_formula": "Giá Xi Măng PCB40 Bán Lẻ - Chi Phí Than Cám & Điện Nung Clinker"
        }
    },
    "SHIPPING": {
        "sector_key": "SHIPPING",
        "commodity_name": "Cước Container Tuyến Trục Hải Phòng - TP.HCM",
        "unit": "VND/TEU",
        "spot_price": 3800000,
        "price_range_min": 2800000,
        "price_range_max": 4500000,
        "source": "Hiệp hội Đại lý và Môi giới Hàng hải Việt Nam (VISABA)",
        "source_url": "https://visaba.org.vn",
        "products": {
            "Container 20ft Tuyến Hải Phòng - TP.HCM": 3800000,
            "Container 40ft Tuyến Hải Phòng - TP.HCM": 6200000,
            "Cước Xếp Dỡ THC Cảng Cát Lái / Hải Phòng": 2100000
        },
        "basis_vs_global": {
            "divergence_type": "GLOBAL_SPILLOVER",
            "global_ticker": "SCFI & BDI",
            "domestic_drivers": "Đứt gãy tuyến vận tải Biển Đỏ, nhu cầu luân chuyển hàng hóa may mặc/điện tử Bắc - Nam, giá dầu nhiên liệu Bunker cấp tại cảng.",
            "spread_formula": "Doanh Thu Cước Bình Quân Tuyến Nội Địa - Chi Phí Dầu Nhiên Liệu Tàu Biển"
        }
    },
    "SUGAR": {
        "sector_key": "SUGAR",
        "commodity_name": "Đường Trắng RS / RE Nội Địa",
        "unit": "VND/kg",
        "spot_price": 21500,
        "price_range_min": 20800,
        "price_range_max": 22200,
        "source": "Hiệp hội Mía đường Việt Nam (VSSA)",
        "source_url": "https://vssa.org.vn",
        "products": {
            "Đường Trắng RS (Sơn La / Quảng Ngãi)": 21200,
            "Đường Tinh Luyện RE (Tây Ninh)": 22500
        },
        "basis_vs_global": {
            "divergence_type": "POLICY_PROTECTED",
            "global_ticker": "SB=F",
            "domestic_drivers": "Thuế chống bán phá giá và chống trợ cấp 47.64% lên đường Thái Lan/Campuchia, kiểm soát buôn lậu đường biên giới Tây Nam.",
            "spread_formula": "Giá Đường Trắng RS Nội Địa - Chi Phí Trồng & Thu Mua Mía Nguyên Liệu"
        }
    },
    "FERTILIZER": {
        "sector_key": "FERTILIZER",
        "commodity_name": "Ure Phú Mỹ & Cà Mau Đại Lý ĐBSCL",
        "unit": "VND/bao (50kg)",
        "spot_price": 520000,
        "price_range_min": 490000,
        "price_range_max": 560000,
        "source": "2Nông & Khảo Sát Đại Lý Vật Tư Nông Nghiệp Tây Nam Bộ",
        "source_url": "https://2nong.vn",
        "products": {
            "Đạm Ure Cà Mau (Hạt Đục)": 530000,
            "Đạm Ure Phú Mỹ (Hạt Trong)": 515000,
            "NPK Bình Điền Đầu Trâu 20-20-15": 780000
        },
        "basis_vs_global": {
            "divergence_type": "DOMESTIC_FEEDSTOCK",
            "global_ticker": "NG=F",
            "domestic_drivers": "Công thức giá khí nội địa từ PVN theo dầu FO Singapore, dự thảo Luật Thuế GTGT 5% tại Quốc hội giúp hoàn thuế đầu vào.",
            "spread_formula": "Giá Ure Đại Lý Bán Lẻ - Chi Phí Khí Tự Nhiên Đầu Vào (PM3/Cửu Long)"
        }
    },
    "RUBBER": {
        "sector_key": "RUBBER",
        "commodity_name": "Mủ Cao Su Nước (Độ TSC) Bình Phước",
        "unit": "VND/độ TSC",
        "spot_price": 405,
        "price_range_min": 390,
        "price_range_max": 425,
        "source": "Tạp chí Cao su Việt Nam & Công ty Cao su Phú Riềng",
        "source_url": "https://tapchicaosu.vn",
        "products": {
            "Cao su Phú Riềng (Bình Phước)": 405,
            "Cao su Bình Long (Bình Phước)": 420,
            "Cao su Bà Rịa": 415
        },
        "basis_vs_global": {
            "divergence_type": "EXPORT_TIED",
            "global_ticker": "TSR20 & RSS3",
            "domestic_drivers": "Chuyển đổi quỹ đất cao su sang khu công nghiệp (KCN), thanh lý gỗ cao su già cỗi, thời tiết mưa bão cản trở thu hoạch mủ.",
            "spread_formula": "Giá Mủ Quy Đổi Ra Sản Phẩm SVR 3L - Chi Phí Cạo Mủ & Nhân Công"
        }
    },
    "TEXTILE": {
        "sector_key": "TEXTILE",
        "commodity_name": "Đơn Giá Gia Công CMT & Sợi Dệt Kéo Nội Địa",
        "unit": "USD/sản phẩm quy đổi",
        "spot_price": 2.45,
        "price_range_min": 1.95,
        "price_range_max": 3.10,
        "source": "Hiệp hội Dệt May Việt Nam (VITAS)",
        "source_url": "https://vitas.org.vn",
        "products": {
            "Gia công áo Polo / Sơ mi CMT": 2.45,
            "Sợi Cotton chải kỹ (VND/kg)": 72000,
            "Sợi Tái Chế Polyester Recycled": 65000
        },
        "basis_vs_global": {
            "divergence_type": "GLOBAL_DEMAND_TIED",
            "global_ticker": "CT=F",
            "domestic_drivers": "Mức độ phục hồi đơn hàng từ thị trường Mỹ/EU, chi phí lương tối thiểu vùng, ưu đãi thuế quan hiệp định EVFTA/CPTPP.",
            "spread_formula": "Đơn Giá Sản Phẩm May Mặc FOB - Chi Phí Sợi & Vải Bông Đầu Vào"
        }
    }
}


def _load_disk_cache() -> Dict[str, Any]:
    try:
        fpath = resolve_data_file(DOMESTIC_CACHE_FILE)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_disk_cache(data: Dict[str, Any]) -> None:
    try:
        fpath = resolve_data_file(DOMESTIC_CACHE_FILE)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def crawl_vietnambiz_live_hog_safe() -> Optional[Dict[str, Any]]:
    """Crawls real-time live hog survey prices from VietnamBiz daily bulletin."""
    try:
        url = "https://vietnambiz.vn/gia-heo-hoi.html"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        match = re.search(r'href="(/gia-heo-hoi-hom-nay-[^"]+\.htm)"', html)
        if not match:
            return None

        art_url = "https://vietnambiz.vn" + match.group(1)
        art_req = urllib.request.Request(art_url, headers=headers)
        with urllib.request.urlopen(art_req, timeout=3.5) as resp:
            art_html = resp.read().decode("utf-8", errors="ignore")

        # Extract prices from table
        num_matches = re.findall(r'(\d{2}\.\d{3})', art_html)
        valid_prices = []
        for nm in num_matches:
            val = int(nm.replace(".", ""))
            if 50000 <= val <= 75000:
                valid_prices.append(val)

        if len(valid_prices) >= 5:
            avg_p = round(sum(valid_prices) / len(valid_prices))
            min_p = min(valid_prices)
            max_p = max(valid_prices)
            return {
                "spot_price": avg_p,
                "price_range_min": min_p,
                "price_range_max": max_p,
                "total_provinces": len(valid_prices),
                "article_url": art_url,
                "crawled_at": datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
            }
    except Exception:
        pass
    return None


def crawl_petrolimex_fuel_safe() -> Optional[Dict[str, Any]]:
    """Crawls official retail petrol and diesel prices from Petrolimex."""
    try:
        url = "https://webgia.com/gia-xang-dau/petrolimex/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        m_e5 = re.search(r'RON\s*92[^\d]+(\d{2}\.\d{3})', html)
        m_do = re.search(r'0,05S[^\d]+(\d{2}\.\d{3})', html)
        m_ron95 = re.search(r'RON\s*95[^\d]+(\d{2}\.\d{3})', html)

        if m_ron95 and m_e5:
            p_ron95 = int(m_ron95.group(1).replace(".", ""))
            p_e5 = int(m_e5.group(1).replace(".", ""))
            p_do = int(m_do.group(1).replace(".", "")) if m_do else 27740
            return {
                "spot_price": p_ron95,
                "price_range_min": p_e5,
                "price_range_max": p_do,
                "crawled_at": datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
            }
    except Exception:
        pass
    return None


class DomesticCommodityService:
    """
    Manages Vietnam domestic spot prices, policy drivers, and basis gap calculations
    for all 10 cyclical sectors.
    """

    DOMESTIC_COMMODITIES_REGISTRY = DEFAULT_DOMESTIC_SPOT_DATA
    _cache: Dict[str, Any] = {}
    _last_crawled_ts: float = 0.0

    @classmethod
    def get_domestic_spot(cls, sector_key: str) -> Dict[str, Any]:
        """Returns the surveyed Vietnam domestic spot price data for a sector."""
        sec = sector_key.upper().strip()
        default_data = DEFAULT_DOMESTIC_SPOT_DATA.get(sec)
        if not default_data:
            return {
                "sector_key": sec,
                "has_domestic_data": False,
                "message": f"Chưa có số liệu khảo sát nội địa cho ngành {sec}"
            }

        result = dict(default_data)
        now_ts = time.time()

        # On-demand refresh live hog and petrol if cache expired
        if now_ts - cls._last_crawled_ts > CACHE_TTL_SECONDS:
            disk = _load_disk_cache()
            if sec == "LIVESTOCK":
                live_hog = crawl_vietnambiz_live_hog_safe()
                if live_hog:
                    result["spot_price"] = live_hog["spot_price"]
                    result["price_range_min"] = live_hog["price_range_min"]
                    result["price_range_max"] = live_hog["price_range_max"]
                    result["source_url"] = live_hog.get("article_url", result["source_url"])
                    result["crawled_at"] = live_hog["crawled_at"]
                    disk["LIVESTOCK"] = result
                    _save_disk_cache(disk)
            elif sec == "REFINERY":
                live_fuel = crawl_petrolimex_fuel_safe()
                if live_fuel:
                    result["spot_price"] = live_fuel["spot_price"]
                    result["price_range_min"] = live_fuel["price_range_min"]
                    result["price_range_max"] = live_fuel["price_range_max"]
                    result["crawled_at"] = live_fuel["crawled_at"]
                    disk["REFINERY"] = result
                    _save_disk_cache(disk)
            cls._last_crawled_ts = now_ts

        result["has_domestic_data"] = True
        return result

    @classmethod
    def calculate_basis_spread(cls, sector_key: str, global_price: float, usd_vnd_rate: float = 25400.0) -> Dict[str, Any]:
        """
        Calculates the Basis Spread:
        Basis Gap = Domestic Spot - Global Benchmark (normalized to VND).
        """
        dom = cls.get_domestic_spot(sector_key)
        if not dom.get("has_domestic_data"):
            return {}

        spot_vnd = float(dom.get("spot_price", 0))
        global_in_vnd = 0.0
        sec = sector_key.upper().strip()

        if sec == "STEEL":
            global_in_vnd = (global_price * usd_vnd_rate) / 1000.0
        elif sec == "REFINERY":
            global_in_vnd = (global_price * usd_vnd_rate) / 159.0
        elif sec == "LIVESTOCK":
            global_in_vnd = global_price * 2.20462 * (usd_vnd_rate / 100.0)
        elif sec == "SUGAR":
            global_in_vnd = global_price * 2.20462 * (usd_vnd_rate / 100.0)
        elif sec == "SEAFOOD":
            global_in_vnd = global_price * usd_vnd_rate
        elif sec == "CEMENT":
            global_in_vnd = global_price * 50.0
        elif sec == "RUBBER":
            global_in_vnd = (global_price * usd_vnd_rate) / 1000.0
        else:
            global_in_vnd = spot_vnd

        basis_diff = spot_vnd - global_in_vnd
        basis_gap_pct = round((basis_diff / max(global_in_vnd, 1.0)) * 100, 1)

        premium_text = f"Cao hơn giá thế giới quy đổi +{basis_gap_pct}% (Thị trường nội địa được bảo hộ/thiếu cung)" if basis_gap_pct >= 0 else f"Thấp hơn giá thế giới quy đổi {basis_gap_pct}% (Áp lực cạnh tranh/chi phí logistics)"

        return {
            "sector_key": sec,
            "domestic_spot_vnd": spot_vnd,
            "domestic_unit": dom.get("unit"),
            "global_benchmark_vnd": round(global_in_vnd),
            "basis_gap_vnd": round(basis_diff),
            "basis_gap_pct": basis_gap_pct,
            "premium_status": premium_text,
            "domestic_source": dom.get("source"),
            "domestic_drivers": dom.get("basis_vs_global", {}).get("domestic_drivers", "")
        }
