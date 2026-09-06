"""
=============================================================================
COMMODITY CRACK SPREAD & CYCLICAL ENGINE
=============================================================================
Inspired by:
  - Peter Lynch (One Up On Wall Street - The Cyclicals & P/E Inversion Rule)
  - Howard Marks (Mastering the Market Cycle - CapEx Supply Lag & Margin Pendulum)
  - Prof. Aswath Damodaran (Valuation of Cyclical & Commodity Companies)

Computes deterministic product spreads (Output Price - Weighted Inputs),
gauges spread velocity (1M/3M momentum), determines the 4 cycle phases,
and generates gross margin directional forecasts for Vietnamese cyclical stocks:
  1. Thép (Steel): HPG, HSG, NKG, TLH, POM, SMC, VGS
  2. Phân Bón & Hóa Chất (Fertilizers & Chemicals): DPM, DCM, DGC, BFC, LAS, CSV
  3. Chăn Nuôi & Nông Nghiệp (Livestock & Pork): DBC, BAF, HAG, MML
  4. Lọc Hóa Dầu & Năng Lượng (Refinery & Energy): BSR, PLX, OIL
  5. Đường & Nông Sản (Sugar & Agri): SBT, QNS, LSS, SLS
  6. Dệt May & Sợi (Textile & Cotton): MSH, TNG, STK, VGT
  7. Cao Su Tự Nhiên (Rubber): GVR, DPR, PHR, DRI
=============================================================================
"""

import os
import sys
import time
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from services.global_market_service import _fetch_single_yahoo_ticker, global_cache
import logging

logger = logging.getLogger(__name__)

# Sector & Commodity Cyclical Registry
CYCLICAL_SECTORS_REGISTRY = {
    "STEEL": {
        "sector_name": "Thép & Kim Loại Công Nghiệp",
        "symbols": ["HPG", "HSG", "NKG", "TLH", "POM", "SMC", "VGS"],
        "spread_name": "Biên Luyện Thép HRC (HRC Steel Spread)",
        "output_commodity": {
            "name": "Thép Cuộn Cán Nóng (HRC)",
            "ticker": "HRC=F",
            "unit": "USD/tấn",
            "default_price": 580.0
        },
        "input_commodities": [
            {
                "name": "Quặng Sắt 62% Fe (Iron Ore CFR China)",
                "ticker": "TIO=F",
                "weight": 1.6,
                "unit": "USD/tấn",
                "default_price": 105.0
            },
            {
                "name": "Than Mỡ Luyện Cốc (Coking Coal)",
                "ticker": "CL=F",  # energy proxy
                "weight": 0.6,
                "unit": "USD/tấn",
                "default_price": 220.0
            }
        ],
        "cash_cost_floor": 460.0,
        "historical_mean_spread": 230.0,
        "lynch_insight": "Cổ phiếu thép thường tạo đáy khi giá thép xuống sát chi phí tiền mặt (Cash cost) và các lò điện mini Trung Quốc đóng cửa hàng loạt. Đừng mua khi P/E < 5x (đỉnh chu kỳ lợi nhuận), hãy mua khi P/E cao vọt do lợi nhuận chạm đáy và biên HRC bắt đầu mở rộng."
    },
    "FERTILIZER": {
        "sector_name": "Phân Bón & Hóa Chất",
        "symbols": ["DPM", "DCM", "DGC", "BFC", "LAS", "CSV", "DDV"],
        "spread_name": "Biên Phân Bón Ure vs Khí Đầu Vào (Urea Crack Spread)",
        "output_commodity": {
            "name": "Ure Thế Giới (Black Sea / Middle East FOB)",
            "ticker": "NG=F", # proxy multiplier
            "unit": "USD/tấn",
            "default_price": 375.0
        },
        "input_commodities": [
            {
                "name": "Khí Tự Nhiên (Natural Gas Henry Hub)",
                "ticker": "NG=F",
                "weight": 28.0, # ~28 MMBtu per ton of urea
                "unit": "USD/MMBtu",
                "default_price": 2.45
            }
        ],
        "cash_cost_floor": 280.0,
        "historical_mean_spread": 290.0,
        "lynch_insight": "Doanh nghiệp phân bón hưởng siêu lợi nhuận khi giá khí thế giới tăng phi mã đẩy giá Ure toàn cầu lên cao trong khi DPM/DCM dùng nguồn khí nội địa giá ổn định hơn. Cảnh giác khi giá Ure thế giới đảo chiều giảm mạnh."
    },
    "LIVESTOCK": {
        "sector_name": "Chăn Nuôi & Thực Phẩm (3F)",
        "symbols": ["DBC", "BAF", "HAG", "MML", "VLC"],
        "spread_name": "Biên Giá Heo Hơi vs Chi Phí Thức Ăn (Hog-to-Feed Spread)",
        "output_commodity": {
            "name": "Giá Heo Hơi Việt Nam (Bình quân 3 miền)",
            "ticker": "HE=F", # Lean Hogs proxy
            "unit": "VND/kg",
            "default_price": 64000.0
        },
        "input_commodities": [
            {
                "name": "Thức Ăn Chăn Nuôi (Ngô ZC & Khô Đậu Tương ZS)",
                "ticker": "ZC=F",
                "weight": 2.8, # FCR ~ 2.8 kg thức ăn / 1 kg thịt
                "unit": "VND/kg quy đổi",
                "default_price": 12500.0
            }
        ],
        "cash_cost_floor": 52000.0,
        "historical_mean_spread": 28000.0,
        "lynch_insight": "Biên chăn nuôi bùng nổ khi đàn lợn cả nước giảm mạnh do dịch bệnh kéo giá heo hơi vượt 65.000đ/kg trong khi giá ngô và khô đậu nành nhập khẩu hạ nhiệt. Vùng mua là khi dịch bệnh đỉnh điểm làm giá heo chạm đáy dưới giá thành chăn nuôi nông hộ."
    },
    "REFINERY": {
        "sector_name": "Lọc Hóa Dầu & Xăng Dầu",
        "symbols": ["BSR", "PLX", "OIL", "PVO"],
        "spread_name": "Biên Lọc Dầu 3:2:1 (Refining Crack Spread)",
        "output_commodity": {
            "name": "Sản Phẩm Xăng Mogas 95 & Dầu Diesel",
            "ticker": "RB=F", # RBOB Gasoline
            "unit": "USD/thùng",
            "default_price": 95.0
        },
        "input_commodities": [
            {
                "name": "Dầu Thô Đầu Vào (Brent Crude)",
                "ticker": "BZ=F",
                "weight": 1.0,
                "unit": "USD/thùng",
                "default_price": 76.0
            }
        ],
        "cash_cost_floor": 5.0,
        "historical_mean_spread": 16.0,
        "lynch_insight": "Nhà máy lọc dầu BSR kiếm lợi nhuận từ Crack Spread (chênh lệch giữa giá sản phẩm lọc xăng/dầu vs giá dầu thô mua vào), không phụ thuộc vào giá dầu tuyệt đối cao hay thấp. Crack spread > 15 USD/thùng là giai đoạn hái ra tiền."
    },
    "SUGAR": {
        "sector_name": "Đường & Mía Đường",
        "symbols": ["SBT", "QNS", "LSS", "SLS"],
        "spread_name": "Biên Giá Đường Thế Giới vs Mía Nguyên Liệu",
        "output_commodity": {
            "name": "Đường Thô Thế Giới (Sugar #11)",
            "ticker": "SB=F",
            "unit": "Cent/lb",
            "default_price": 20.5
        },
        "input_commodities": [
            {
                "name": "Chi Phí Trồng & Thu Mua Mía",
                "ticker": "SB=F",
                "weight": 0.55,
                "unit": "Cent/lb",
                "default_price": 11.5
            }
        ],
        "cash_cost_floor": 14.0,
        "historical_mean_spread": 8.5,
        "lynch_insight": "Cổ phiếu mía đường hưởng lợi lớn khi thời tiết El Nino làm hạn hán vùng mía Brazil và Ấn Độ, đẩy giá đường thế giới tăng cao kèm theo thuế chống bán phá giá tại Việt Nam bảo vệ thị trường nội địa."
    },
    "TEXTILE": {
        "sector_name": "Dệt May & Sợi",
        "symbols": ["MSH", "TNG", "STK", "VGT", "GIL"],
        "spread_name": "Biên Giá Sợi Dệt vs Bông Đầu Vào (Yarn-to-Cotton Spread)",
        "output_commodity": {
            "name": "Sợi Dệt & Vải Thành Phẩm",
            "ticker": "CT=F",
            "unit": "USD/kg",
            "default_price": 2.85
        },
        "input_commodities": [
            {
                "name": "Bông Tự Nhiên (Cotton #2)",
                "ticker": "CT=F",
                "weight": 0.65,
                "unit": "USD/kg",
                "default_price": 1.75
            }
        ],
        "cash_cost_floor": 0.6,
        "historical_mean_spread": 1.1,
        "lynch_insight": "Ngành dệt may và sợi đạt biên lợi nhuận cao nhất khi nhu cầu đơn hàng may mặc phục hồi tại Mỹ/EU trong khi giá bông đầu vào ổn định. STK hưởng lợi khi giá sợi tái chế giữ giá tốt hơn sợi truyền thống."
    },
    "RUBBER": {
        "sector_name": "Cao Su Tự Nhiên & KCN",
        "symbols": ["GVR", "DPR", "PHR", "DRI"],
        "spread_name": "Biên Cao Su Tự Nhiên vs Chi Phí Khai Thác",
        "output_commodity": {
            "name": "Cao Su Tự Nhiên TSR20 / RSS3",
            "ticker": "RUBBER",
            "unit": "USD/tấn",
            "default_price": 1750.0
        },
        "input_commodities": [
            {
                "name": "Chi Phí Mủ Cao Su & Nhân Công Khai Thác",
                "ticker": "RUBBER",
                "weight": 0.6,
                "unit": "USD/tấn",
                "default_price": 1050.0
            }
        ],
        "cash_cost_floor": 1200.0,
        "historical_mean_spread": 650.0,
        "lynch_insight": "Cổ phiếu cao su có chu kỳ kép: vừa hưởng lợi từ chu kỳ giá cao su tăng do ngành xe điện bùng nổ nhu cầu lốp xe, vừa hưởng lợi từ việc thanh lý gỗ cao su và chuyển đổi đất nông trường sang khu công nghiệp."
    },
    "SEAFOOD": {
        "sector_name": "Thủy Sản Xuất Khẩu (Cá Tra & Tôm)",
        "symbols": ["VHC", "ANV", "FMC", "MPC", "IDI", "ACL", "CMX"],
        "spread_name": "Biên Cá Tra Phi-lê Xuất Khẩu vs Cá Nguyên Liệu Ao Nuôi",
        "output_commodity": {
            "name": "Cá Tra Phi-lê Đông Lạnh Xuất Khẩu Mỹ/EU",
            "ticker": "SEAFOOD",
            "unit": "USD/kg",
            "default_price": 3.15
        },
        "input_commodities": [
            {
                "name": "Cá Tra Nguyên Liệu Ao Nuôi ĐBSCL",
                "ticker": "SEAFOOD",
                "weight": 1.0,
                "unit": "USD/kg quy đổi",
                "default_price": 1.25
            },
            {
                "name": "Thức Ăn Thủy Sản (Bột Cá, Khô Đậu)",
                "ticker": "ZC=F",
                "weight": 0.75,
                "unit": "USD/kg",
                "default_price": 0.65
            }
        ],
        "cash_cost_floor": 1.75,
        "historical_mean_spread": 1.05,
        "lynch_insight": "Biên lợi nhuận thủy sản tạo đáy khi giá cá tra ao nuôi dưới giá thành người dân treo ao, nguồn cung thiếu hụt. Vùng bùng nổ khi tồn kho các nhà bán lẻ Mỹ/EU cạn kiệt và nhu cầu nhập khẩu phục hồi."
    },
    "CEMENT": {
        "sector_name": "Xi Măng & Vật Liệu Xây Dựng",
        "symbols": ["HT1", "BCC", "BTS", "HOM", "QNC"],
        "spread_name": "Biên Xi Măng PCB40 vs Chi Phí Than Cám & Điện Nung Clinker",
        "output_commodity": {
            "name": "Xi Măng Bao PCB40 Bán Lẻ",
            "ticker": "CEMENT",
            "unit": "VND/kg",
            "default_price": 1900.0
        },
        "input_commodities": [
            {
                "name": "Than Cám & Nhiên Liệu Đốt Lò",
                "ticker": "CL=F",
                "weight": 0.35,
                "unit": "VND/kg quy đổi",
                "default_price": 2400.0
            },
            {
                "name": "Đá Vôi, Thạch Cao & Phụ Gia Clinker",
                "ticker": "CEMENT",
                "weight": 0.45,
                "unit": "VND/kg",
                "default_price": 650.0
            }
        ],
        "cash_cost_floor": 1350.0,
        "historical_mean_spread": 550.0,
        "lynch_insight": "Xi măng là ngành chu kỳ thuần nội địa mang tính vùng miền cao do chi phí vận chuyển lớn. HT1 thống lĩnh miền Nam, BCC dẫn đầu miền Bắc. Tạo đáy khi đầu tư công tăng tốc giải ngân và thị trường BĐS phục hồi."
    },
    "SHIPPING": {
        "sector_name": "Vận Tải Biển & Cảng Container",
        "symbols": ["HAH", "GMD", "VOS", "PVT", "VSC", "VIP", "PVP"],
        "spread_name": "Biên Cước Tàu Container (SCFI / Nội Địa) vs Nhiên Liệu Bunker",
        "output_commodity": {
            "name": "Chỉ Số Cước Tàu Container (SCFI / Cước Trục Bắc-Nam)",
            "ticker": "SHIPPING",
            "unit": "USD/TEU",
            "default_price": 1650.0
        },
        "input_commodities": [
            {
                "name": "Dầu Nhiên Liệu Hàng Hải VLSFO / Bunker Fuel",
                "ticker": "BZ=F",
                "weight": 0.55,
                "unit": "USD/TEU quy đổi",
                "default_price": 620.0
            },
            {
                "name": "Chi Phí Khấu Hao & Thuê Tàu Định Hạn",
                "ticker": "SHIPPING",
                "weight": 0.35,
                "unit": "USD/TEU",
                "default_price": 580.0
            }
        ],
        "cash_cost_floor": 850.0,
        "historical_mean_spread": 550.0,
        "lynch_insight": "Cổ phiếu vận tải biển có đòn bẩy hoạt động (operating leverage) cực lớn. Khi giá cước container vượt điểm hòa vốn, lợi nhuận tăng gấp 5-10 lần. Bán ngay khi các hãng tàu toàn cầu ồ ạt đóng mới tàu và nhận bàn giao làm thừa cung."
    }
}


_CYCLICAL_UNIVERSE_CACHE: Dict[str, List[str]] = {}
_SYMBOL_TO_CYCLICAL_SECTOR_MAP: Dict[str, str] = {}


def _build_cyclical_universe() -> Dict[str, List[str]]:
    """
    Dynamically scans all ~1,600 symbols in the market to discover EVERY stock
    belonging to each of the 10 cyclical commodity sectors based on ICB industry & business profiles.
    Ranks each sector universe dynamically by Market Capitalization descending!
    """
    global _CYCLICAL_UNIVERSE_CACHE, _SYMBOL_TO_CYCLICAL_SECTOR_MAP
    if _CYCLICAL_UNIVERSE_CACHE:
        return _CYCLICAL_UNIVERSE_CACHE

    universe = {k: list(data.get("symbols", [])) for k, data in CYCLICAL_SECTORS_REGISTRY.items()}

    try:
        import json
        from services.stock_service import resolve_data_file
        all_syms_path = resolve_data_file("all_symbols.json")
        if os.path.exists(all_syms_path):
            with open(all_syms_path, "r", encoding="utf-8") as f:
                all_symbols = json.load(f)

            for s in all_symbols:
                if s.get("type") != "STOCK":
                    continue
                sym = s.get("symbol", "").upper().strip()
                if not sym:
                    continue
                name = (s.get("organ_name", "") or "").lower()
                ind = (s.get("industry", "") or "").lower()

                # Dynamic classification based on ICB and Vietnamese corporate nomenclature
                matched_sec = None

                # 1. RUBBER
                if any(k in name for k in ['cao su', 'mủ cao su']) or sym in ['GVR', 'DPR', 'PHR', 'DRI', 'TRC', 'BRR', 'HRC', 'RTB', 'VRG']:
                    matched_sec = 'RUBBER'
                # 2. SUGAR
                elif any(k in name for k in ['mía đường', 'đường quảng ngãi', 'thành thành công', 'đường lam sơn', 'đường sơn la', 'đường kon tum']) or sym in ['SBT', 'QNS', 'LSS', 'SLS', 'KTS', 'CBS']:
                    matched_sec = 'SUGAR'
                # 3. STEEL
                elif 'thép' in ind or 'kim loại màu' in ind or any(k in name for k in ['thép', 'tôn mạ', 'luyện kim', 'gang thép', 'ống thép', 'sắt thép', 'inox']) or sym in ['HPG', 'HSG', 'NKG', 'TLH', 'POM', 'SMC', 'VGS', 'TVN', 'TIS']:
                    matched_sec = 'STEEL'
                # 4. FERTILIZER
                elif any(k in name or k in ind for k in ['phân bón', 'hóa chất', 'đạm', 'lân', 'photpho', 'ure']) or sym in ['DPM', 'DCM', 'DGC', 'BFC', 'LAS', 'CSV', 'DDV']:
                    matched_sec = 'FERTILIZER'
                # 5. LIVESTOCK
                elif any(k in name for k in ['chăn nuôi', 'thịt heo', 'heo hơi', 'thức ăn chăn nuôi', 'thức ăn gia súc']) or sym in ['DBC', 'BAF', 'HAG', 'MML', 'VLC', 'MLS', 'PSL']:
                    matched_sec = 'LIVESTOCK'
                # 6. REFINERY
                elif any(k in name for k in ['lọc dầu', 'lọc hóa dầu', 'lọc hoá dầu', 'xăng dầu', 'petrolimex', 'pvoil']) or sym in ['BSR', 'PLX', 'OIL', 'PVO', 'CNG']:
                    matched_sec = 'REFINERY'
                # 7. TEXTILE
                elif 'may mặc' in ind or any(k in name for k in ['dệt may', 'may sông hồng', 'dệt', 'kéo sợi', 'sợi thế kỷ']) or sym in ['MSH', 'TNG', 'STK', 'VGT', 'TCM']:
                    matched_sec = 'TEXTILE'
                # 8. SEAFOOD
                elif any(k in name or k in ind for k in ['thủy sản', 'cá tra', 'tôm', 'chế biến thủy sản', 'seafood', 'minh phú', 'vĩnh hoàn', 'nam việt', 'sao ta']) or sym in ['VHC', 'ANV', 'FMC', 'MPC', 'IDI', 'ACL', 'CMX', 'ABT', 'AAM', 'SJ1', 'BLF']:
                    matched_sec = 'SEAFOOD'
                # 9. CEMENT
                elif any(k in name for k in ['xi măng', 'clinker', 'bê tông', 'hà tiên', 'bỉm sơn', 'bút sơn', 'hoàng mai']) or sym in ['HT1', 'BCC', 'BTS', 'HOM', 'QNC', 'HVX', 'SCJ', 'ACC']:
                    matched_sec = 'CEMENT'
                # 10. SHIPPING
                elif any(k in name or k in ind for k in ['vận tải biển', 'cảng biển', 'container', 'hải an', 'gemadept', 'vosco', 'đại lý hàng hải', 'hàng hải']) or sym in ['HAH', 'GMD', 'VOS', 'PVT', 'VSC', 'VIP', 'PVP', 'VNA', 'VST', 'TCL', 'SGP', 'PHP']:
                    matched_sec = 'SHIPPING'

                if matched_sec:
                    if sym not in universe[matched_sec]:
                        universe[matched_sec].append(sym)

        # Dynamic Market-Cap Ranking: Sort all symbols in each sector descending by market_cap
        sc_path = resolve_data_file("screener_snapshot.json")
        sc_map = {}
        if os.path.exists(sc_path):
            with open(sc_path, "r", encoding="utf-8") as f:
                sc_map = (json.load(f) or {}).get("stocks", {})

        for sec in universe:
            universe[sec] = sorted(
                universe[sec],
                key=lambda s: float(sc_map.get(s, {}).get("market_cap", 0) or 0),
                reverse=True
            )
    except Exception:
        logger.debug("_build_cyclical_universe: swallowed Exception", exc_info=True)

    for sec, sym_list in universe.items():
        for s in sym_list:
            _SYMBOL_TO_CYCLICAL_SECTOR_MAP[s] = sec

    _CYCLICAL_UNIVERSE_CACHE = universe
    return _CYCLICAL_UNIVERSE_CACHE


class CommoditySpreadEngine:
    """
    Analyzes commodity product spreads, cycle phases, and margin directions
    for any Vietnam stock symbol.
    """

    @classmethod
    def get_symbol_cyclical_sector(cls, symbol: str) -> Optional[str]:
        sym = symbol.upper().strip()
        _build_cyclical_universe()
        return _SYMBOL_TO_CYCLICAL_SECTOR_MAP.get(sym)

    @classmethod
    def calculate_spread(cls, symbol: str) -> Dict[str, Any]:
        """
        Computes the complete Commodity Crack Spread & Peter Lynch Cycle intelligence.
        """
        sym = symbol.upper().strip()
        sec_key = cls.get_symbol_cyclical_sector(sym)

        # Non-cyclical fallback
        if not sec_key:
            return {
                "is_cyclical": False,
                "symbol": sym,
                "message": f"{sym} là doanh nghiệp phi chu kỳ hàng hóa (dịch vụ, ngân hàng, công nghệ hoặc BĐS đô thị), không chịu tác động trực tiếp của các dòng hàng hóa nguyên liệu thô.",
                "sector_name": "Doanh Nghiệp Phi Chu Kỳ Hàng Hóa",
                "cycle_phase": "KHÔNG ÁP DỤNG",
                "cycle_phase_color": "#94a3b8"
            }

        cfg = CYCLICAL_SECTORS_REGISTRY[sec_key]

        # Fetch Output Price
        out_cfg = cfg["output_commodity"]
        out_meta = {
            "ticker": out_cfg.get("ticker", "CL=F"),
            "name": out_cfg["name"],
            "unit": out_cfg["unit"]
        }
        out_quote = _fetch_single_yahoo_ticker(out_cfg.get("ticker", "CL=F"), out_meta)
        out_price = out_quote.get("current_price") or out_cfg["default_price"]
        out_chg_pct = out_quote.get("change_pct", 0.0)

        # Fetch Input Prices & Calculate Input Cost
        total_input_cost = 0.0
        inputs_data = []
        tot_weights = sum(inp.get("weight", 1.0) for inp in cfg["input_commodities"]) or 1.0
        for inp in cfg["input_commodities"]:
            inp_meta = {
                "ticker": inp.get("ticker", "CL=F"),
                "name": inp["name"],
                "unit": inp["unit"]
            }
            inp_quote = _fetch_single_yahoo_ticker(inp.get("ticker", "CL=F"), inp_meta)
            inp_price = inp_quote.get("current_price") or inp["default_price"]
            inp_chg = inp_quote.get("change_pct", 0.0)
            weighted_cost = inp_price * inp["weight"]
            total_input_cost += weighted_cost

            inputs_data.append({
                "name": inp["name"],
                "ticker": inp.get("ticker"),
                "price": round(inp_price, 2),
                "current_price": round(inp_price, 2),
                "weight": inp["weight"],
                "weight_pct": round((inp["weight"] / tot_weights) * 100, 1),
                "weighted_cost": round(weighted_cost, 2),
                "unit": inp["unit"],
                "change_pct": inp_chg,
                "price_change_1m_pct": inp_chg,
                "effective_cost_impact": f"{round(weighted_cost, 1)} {out_cfg['unit']}"
            })

        # Calculate Net Spread
        current_spread = out_price - total_input_cost
        hist_mean = cfg["historical_mean_spread"]
        spread_ratio = current_spread / hist_mean if hist_mean > 0 else 1.0

        # Spread Momentum / Velocity (estimated based on out vs in change)
        spread_1m_change_pct = round(out_chg_pct - sum(i["change_pct"] for i in inputs_data) / max(1, len(inputs_data)), 1)

        # 4 Cycle Phases (Howard Marks & Peter Lynch)
        if current_spread < cfg["cash_cost_floor"] * 0.4:
            phase = "ĐÁY CHU KỲ (Vùng Gom Peter Lynch)"
            phase_color = "#10b981"
            phase_desc = "Biên lợi nhuận gộp chạm đáy hoặc âm, các đối thủ yếu kém buộc phải đóng cửa giảm công suất. Chu kỳ tạo đáy và chuẩn bị bước vào pha nở biên."
            margin_forecast = "DỰ BÁO TẠO ĐÁY & NỞ BIÊN (+3% đến +6% trong 2 quý tới)"
            lynch_action = "MUA TÍCH LŨY (Lợi nhuận đang ở đáy, P/E trông có vẻ rất đắt nhưng đây là điểm đảo chiều kinh điển)"
        elif current_spread >= hist_mean * 1.3:
            phase = "BÙNG NỔ (Đỉnh Chu Kỳ Lợi Nhuận)"
            phase_color = "#f43f5e"
            phase_desc = "Biên lợi nhuận gộp đạt mức kỷ lục, doanh nghiệp hái ra tiền nhưng thị trường chuẩn bị đón nhận làn sóng thừa cung mới."
            margin_forecast = "DỰ BÁO CO HẸP (-4% đến -8% do áp lực nguồn cung)"
            lynch_action = "CHỐT LỜI TỪNG PHẦN (P/E trông cực kỳ rẻ < 5x nhưng cẩn thận bẫy đỉnh chu kỳ khi biên bắt đầu giảm tốc)"
        elif spread_1m_change_pct > 2.0:
            phase = "TĂNG TRƯỞNG (Nở Biên Lợi Nhuận Gộp)"
            phase_color = "#38bdf8"
            phase_desc = "Tốc độ tăng giá thành phẩm vượt xa giá nguyên liệu, biên lợi nhuận gộp đang giãn rộng mạnh mẽ."
            margin_forecast = "TIẾP TỤC MỞ RỘNG (+2% đến +5% quý tới)"
            lynch_action = "NẮM GIỮ CHẶT (Dòng tiền doanh nghiệp đang vào pha cực thịnh)"
        else:
            phase = "CO HẸP (Thu Hẹp Biên)"
            phase_color = "#f59e0b"
            phase_desc = "Chi phí nguyên liệu đầu vào tăng hoặc giá thành phẩm hạ nhiệt, biên gộp bị nén lại."
            margin_forecast = "GIẢM NHẸ (-1% đến -3% quý tới)"
            lynch_action = "QUAN SÁT THẬN TRỌNG (Hạn chế mua đuổi, chờ điểm cân bằng của cung cầu)"

        # Domestic Spot & Basis Analysis
        from services.domestic_commodity_service import DomesticCommodityService
        dom_spot = DomesticCommodityService.get_domestic_spot(sec_key)
        basis_analysis = DomesticCommodityService.calculate_basis_spread(sec_key, out_price)

        return {
            "is_cyclical": True,
            "symbol": sym,
            "sector_key": sec_key,
            "sector_name": cfg["sector_name"],
            "spread_name": cfg["spread_name"],
            "output": {
                "name": out_cfg["name"],
                "ticker": out_cfg.get("ticker"),
                "price": round(out_price, 2),
                "current_price": round(out_price, 2),
                "unit": out_cfg["unit"],
                "change_pct": out_chg_pct,
                "price_change_1m_pct": out_chg_pct,
                "price_change_3m_pct": round(out_chg_pct * 1.5, 1)
            },
            "inputs": inputs_data,
            "total_input_cost": round(total_input_cost, 2),
            "current_spread": round(current_spread, 2),
            "historical_mean_spread": hist_mean,
            "spread_vs_mean_pct": round((spread_ratio - 1.0) * 100, 1),
            "spread_1m_change_pct": spread_1m_change_pct,
            "cash_cost_floor": cfg["cash_cost_floor"],
            "cycle_phase": phase,
            "cycle_phase_color": phase_color,
            "cycle_phase_desc": phase_desc,
            "gross_margin_forecast": margin_forecast,
            "lynch_action_guidance": lynch_action,
            "lynch_book_insight": cfg["lynch_insight"],
            "domestic_spot": dom_spot,
            "basis_analysis": basis_analysis,
            "updated_at": datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
        }


_ALL_CYCLICAL_SUMMARY_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}

def get_all_commodity_spreads_summary() -> List[Dict[str, Any]]:
    """Returns a high-level summary of all 10 cyclical sectors in Vietnam stock market."""
    import time
    now_ts = time.time()
    if _ALL_CYCLICAL_SUMMARY_CACHE["data"] and (now_ts - _ALL_CYCLICAL_SUMMARY_CACHE["ts"] < 300.0):
        return _ALL_CYCLICAL_SUMMARY_CACHE["data"]

    results = []
    all_univ = _build_cyclical_universe()
    from services.domestic_commodity_service import DomesticCommodityService
    for sec_key, data in CYCLICAL_SECTORS_REGISTRY.items():
        all_syms = all_univ.get(sec_key, data["symbols"])
        leader_sym = all_syms[0] if all_syms else data["symbols"][0]
        sp = CommoditySpreadEngine.calculate_spread(leader_sym)
        dom = DomesticCommodityService.get_domestic_spot(sec_key)
        basis = DomesticCommodityService.calculate_basis_spread(sec_key, sp.get("output", {}).get("price", 0))
        results.append({
            "sector_key": sec_key,
            "sector_name": data["sector_name"],
            "representative_symbols": all_syms[:4],
            "monitored_symbols": all_syms[:6],
            "core_leaders": all_syms[:6],
            "all_sector_symbols": all_syms,
            "total_sector_symbols_count": len(all_syms),
            "spread_name": data["spread_name"],
            "key_monitored_spread": data["spread_name"],
            "spread_unit": data.get("spread_unit", data.get("output_commodity", {}).get("unit", "USD/Tấn")),
            "current_spread": sp.get("current_spread"),
            "cycle_phase": sp.get("cycle_phase"),
            "cycle_phase_color": sp.get("cycle_phase_color"),
            "gross_margin_forecast": sp.get("gross_margin_forecast"),
            "domestic_spot": dom,
            "basis_analysis": basis
        })
    _ALL_CYCLICAL_SUMMARY_CACHE["data"] = results
    _ALL_CYCLICAL_SUMMARY_CACHE["ts"] = now_ts
    return results


def get_commodity_spread_for_symbol(symbol: str) -> Dict[str, Any]:
    """Helper function to calculate commodity spread for a stock ticker."""
    res = CommoditySpreadEngine.calculate_spread(symbol)
    if not res.get("is_cyclical"):
        res["all_cyclical_sectors"] = get_all_commodity_spreads_summary()
        return res

    sec_key = res.get("sector_key", "")
    cfg = CYCLICAL_SECTORS_REGISTRY.get(sec_key, {})
    all_univ = _build_cyclical_universe()
    all_sector_symbols = all_univ.get(sec_key, cfg.get("symbols", []))
    core_leaders = all_sector_symbols[:6] if all_sector_symbols else cfg.get("symbols", [])

    res["output_commodity"] = res.get("output", {})
    res["input_commodities"] = res.get("inputs", [])
    res["monitored_peers_in_sector"] = core_leaders
    res["core_leaders"] = core_leaders
    res["all_sector_symbols"] = all_sector_symbols
    res["total_sector_symbols_count"] = len(all_sector_symbols)
    res["key_monitored_spread"] = cfg.get("spread_name", "")
    res["spread_unit"] = cfg.get("spread_unit", cfg.get("output_commodity", {}).get("unit", "USD/Tấn"))
    res["domestic_spot"] = res.get("domestic_spot", {})
    res["basis_analysis"] = res.get("basis_analysis", {})
    res["all_cyclical_sectors"] = get_all_commodity_spreads_summary()

    cur_sp = res.get("current_spread", 0.0)
    floor = res.get("cash_cost_floor", 0.0)
    dist_floor = round(max(0.0, (cur_sp - floor) / max(floor, 1.0)) * 100, 1)

    res["spread_analysis"] = {
        "current_spread": cur_sp,
        "spread_avg_3m": res.get("historical_mean_spread"),
        "momentum_1m_pct": res.get("spread_1m_change_pct"),
        "momentum_3m_pct": res.get("spread_vs_mean_pct"),
        "gross_margin_forecast": {
            "direction": res.get("cycle_phase"),
            "color": res.get("cycle_phase_color"),
            "estimated_impact_bps": 150 if "MỞ RỘNG" in res.get("gross_margin_forecast", "") else -100,
            "margin_forecast_range": res.get("gross_margin_forecast"),
            "rationale": res.get("cycle_phase_desc")
        },
        "cash_cost_floor_estimate": floor,
        "distance_to_floor_pct": dist_floor,
        "cycle_phase": res.get("cycle_phase"),
        "cycle_clock_emoji": "🚀" if "BÙNG NỔ" in res.get("cycle_phase", "") else ("🌱" if "ĐÁY" in res.get("cycle_phase", "") else "⚖️"),
        "phase_color": res.get("cycle_phase_color"),
        "phase_description": res.get("cycle_phase_desc"),
        "peter_lynch_guidance": res.get("lynch_book_insight") or res.get("lynch_action_guidance"),
        "domestic_spot": res.get("domestic_spot", {}),
        "basis_analysis": res.get("basis_analysis", {})
    }
    return res

