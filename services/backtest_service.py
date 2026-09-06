"""
==============================================================================
VNSTOCK MULTI-FACTOR QUANT SCREENER BACKTESTING ENGINE
==============================================================================
Provides high-performance historical simulation for quantitative stock screeners:
1. Composite Quant Q1 (Top 20% 4-Pillar Score)
2. Hyper-Growth Screener (5Y Rev Growth >= 50%, 3Y PAT CAGR >= 20%)
3. Quality & Moat Screener (ROE >= 20%, High Margins, D/E <= 1.0)
4. Deep Value Screener (Low P/E, Low P/B, High Liquidity)
5. Peter Lynch GARP Screener (PEG <= 1.0, Stable Growth, Low Debt)
6. Quant Q5 Inverse (Bottom 20% - Baseline Validation)
7. VN-Index Benchmark (Buy & Hold)

Includes:
- Point-in-Time financial indicators & price paths across 2021 - 2026
- Friction costs (0.15% fee + 0.10% tax)
- CAGR, Total Return, Max Drawdown, Sharpe Ratio, Sortino Ratio
- Year-by-Year returns matrix
- Rebalance holdings timeline
"""

import os
import json
import math
import zlib
import numpy as np
from typing import Dict, List, Any, Optional

from services.stock_service import ALL_SYMBOLS_MAP, get_quant_screener, SimpleCache, resolve_data_file

# TTL cache for full multi-strategy comparison runs. One run executes 26
# sequential backtests (~30s cold), so identical parameter sets are served
# from this cache instead of recomputing the whole comparison per click.
_compare_cache = SimpleCache()

def _deterministic_hash(key: str) -> int:
    return zlib.crc32(key.encode("utf-8")) % 10000

# Annual risk-free rate assumption used for Sharpe/Sortino excess returns
# (5% p.a. ≈ long-run Vietnamese government bond yield). Exposed as a module
# constant and echoed back in the metrics dict ("rf_annual", as a fraction)
# so UI/API consumers can display the assumption instead of it being hidden.
RF_ANNUAL = 0.05

STRATEGY_DEFINITIONS = {
    "deep_value_klarman": {
        "id": "deep_value_klarman",
        "name": "💎 Deep Value (Seth Klarman)",
        "short_name": "Deep Value (Klarman)",
        "color": "#eab308",
        "accent_glow": "rgba(234, 179, 8, 0.4)",
        "badge_class": "badge-q4",
        "author": "Seth Klarman (Margin of Safety)",
        "description": "Cổ phiếu chiết khấu sâu dưới giá trị thực, bảng CĐKT sạch sẽ: P/B < 1.0, Dòng tiền tự do FCF > 0, Nợ vay D/E < 0.5.",
        "icon": "💎"
    },
    "ps_focus_fisher": {
        "id": "ps_focus_fisher",
        "name": "📊 P/S Focus (Ken Fisher)",
        "short_name": "P/S Focus (Ken Fisher)",
        "color": "#06b6d4",
        "accent_glow": "rgba(6, 182, 212, 0.4)",
        "badge_class": "badge-q2",
        "author": "Ken Fisher (Super Stocks)",
        "description": "Doanh nghiệp định giá rẻ theo doanh thu và tăng trưởng top-line mạnh mẽ: P/S < 1.0, Tăng trưởng DT 1Y > 5%, Tăng trưởng DT 3Y > 25%.",
        "icon": "📊"
    },
    "contrarian_dreman": {
        "id": "contrarian_dreman",
        "name": "🔄 Contrarian Investing (David Dreman)",
        "short_name": "Contrarian (Dreman)",
        "color": "#a855f7",
        "accent_glow": "rgba(168, 85, 247, 0.4)",
        "badge_class": "badge-q3",
        "author": "David Dreman (Contrarian Investment)",
        "description": "Cổ phiếu ngược dòng, sinh lời tốt, cổ tức cao: P/E < 12.0, Tỷ suất cổ tức > 3.0%, ROE > 15.0%.",
        "icon": "🔄"
    },
    "growth_philip_fisher": {
        "id": "growth_philip_fisher",
        "name": "🚀 Growth Investing (Philip Fisher)",
        "short_name": "Tăng Trưởng (Philip Fisher)",
        "color": "#38bdf8",
        "accent_glow": "rgba(56, 189, 248, 0.4)",
        "badge_class": "badge-q2",
        "author": "Philip Fisher (Common Stocks & Uncommon Profits)",
        "description": "Siêu tăng trưởng toàn diện: Tăng trưởng LNST 1Y > 15%, DT 1Y > 10%, DT 3Y > 40%, DT 5Y > 75%, ROE > 20%.",
        "icon": "🚀"
    },
    "peter_lynch_garp": {
        "id": "peter_lynch_garp",
        "name": "🎯 GARP - Tăng Trưởng Giá Hợp Lý (Peter Lynch)",
        "short_name": "GARP (Peter Lynch)",
        "color": "#f97316",
        "accent_glow": "rgba(249, 115, 22, 0.4)",
        "badge_class": "badge-q2",
        "author": "Peter Lynch (Beating the Street / One Up)",
        "description": "Tăng trưởng giá hợp lý: PEG < 1.0, 10 < P/E < 30, Tăng trưởng LNST 1Y > 10%, Tăng trưởng DT 3Y > 20%.",
        "icon": "🎯"
    },
    "defensive_graham": {
        "id": "defensive_graham",
        "name": "🛡️ Defensive Investing (Benjamin Graham)",
        "short_name": "Phòng Thủ (Graham)",
        "color": "#64748b",
        "accent_glow": "rgba(100, 116, 139, 0.4)",
        "badge_class": "badge-neutral",
        "author": "Benjamin Graham (The Intelligent Investor)",
        "description": "Bảo toàn vốn, biên an toàn tối đa: P/E < 10.0, P/B < 1.0, D/E < 0.5, Tỷ suất cổ tức > 2.0%.",
        "icon": "🛡️"
    },
    "value_buffett": {
        "id": "value_buffett",
        "name": "🏰 Quality & Moat Value (Warren Buffett)",
        "short_name": "Moat & Value (Buffett)",
        "color": "#10b981",
        "accent_glow": "rgba(16, 185, 129, 0.4)",
        "badge_class": "badge-q1",
        "author": "Warren Buffett & Charlie Munger",
        "description": "Con hào kinh tế lớn, dòng tiền mạnh, định giá hợp lý: ROE > 20%, D/E < 0.5, FCF > 0, P/E < 25, P/B < 5, DT 5Y > 20%, Cổ tức > 0%.",
        "icon": "🏰"
    },
    "buffetts_alpha": {
        "id": "buffetts_alpha",
        "name": "🏛️ Buffett's Alpha (Quality, Low-Beta & Value)",
        "short_name": "Buffett's Alpha",
        "color": "#0d9488",
        "accent_glow": "rgba(13, 148, 136, 0.45)",
        "badge_class": "badge-q1",
        "author": "Frazzini, Kabiller & Pedersen (AQR / Buffett's Alpha)",
        "description": "Mô hình Buffett's Alpha 3 Trụ Cột: (1) Siêu chất lượng QMJ (ROIC/ROE >= 15-18%, Biên gộp >= 20%, CFO/LNST >= 0.8, FCF > 0), (2) Phòng thủ & Nợ thấp (Net D/E <= 0.5; Nhóm Bank: ROE >= 18%, P/B <= 1.5), (3) Định giá hấp dẫn & Cổ tức (P/E <= 13.5, Cổ tức > 0%).",
        "icon": "🏛️"
    },
    "novy_marx_quality_value": {
        "id": "novy_marx_quality_value",
        "name": "🏛️ Gross Profitability & Value (Robert Novy-Marx)",
        "short_name": "Novy-Marx GP/A",
        "color": "#0284c7",
        "accent_glow": "rgba(2, 132, 199, 0.45)",
        "badge_class": "badge-q1",
        "author": "Robert Novy-Marx (Gross Profitability Premium / JFE)",
        "description": "Mô hình Năng suất Lợi nhuận gộp trên Tài sản (GP/A) kết hợp Định giá rẻ: (1) Top Gross Profitability (GP/A >= 20-25% hoặc Biên gộp >= 25%); (2) Định giá rẻ P/E <= 13.5 hoặc EV/EBIT <= 10; (3) Dòng tiền CFO/LNST >= 0.8 & Net D/E <= 0.60.",
        "icon": "🏛️"
    },
    "gray_quantitative_value_qval": {
        "id": "gray_quantitative_value_qval",
        "name": "🛡️ Quantitative Value - Q-VAL (Wesley Gray / Alpha Architect)",
        "short_name": "Alpha Architect Q-VAL",
        "color": "#10b981",
        "accent_glow": "rgba(16, 185, 129, 0.45)",
        "badge_class": "badge-q1",
        "author": "Wesley Gray & Tobias Carlisle (Quantitative Value / Alpha Architect)",
        "description": "Mô hình Định lượng Giá trị Toàn diện 5 Bước: (1) Vũ trụ thanh khoản Cap >= 250 tỷ; (2) Màng lọc kiểm toán chống gian lận Sloan Accrual CFO >= LNST & chống pha loãng <= 3%; (3) Tường lửa F-Score >= 7 & D/E <= 0.75; (4) Định giá sâu EBIT/EV; (5) Con hào kinh tế FCF > 0 & ROIC >= 12%.",
        "icon": "🛡️"
    },
    "hello_lower_risk": {
        "id": "hello_lower_risk",
        "name": "🌱 Hello Stocks: Rủi Ro Thấp (Lower Risk)",
        "short_name": "Hello - Lower Risk",
        "color": "#22c55e",
        "accent_glow": "rgba(34, 197, 94, 0.4)",
        "badge_class": "badge-q1",
        "author": "Hello Stocks Framework",
        "description": "Loại trừ 5 ngành chu kỳ/tài chính. Tăng trưởng chất lượng cao định giá rẻ: PEG < 1.0, DT 5Y > 50%, DT 1Y > 5%, LN 1Y > 5%, ROE > 15%, D/E < 1.0, FCF > 0.",
        "icon": "🌱"
    },
    "hello_balanced_risk": {
        "id": "hello_balanced_risk",
        "name": "⚖️ Hello Stocks: Cân Bằng (Balanced Risk)",
        "short_name": "Hello - Balanced",
        "color": "#3b82f6",
        "accent_glow": "rgba(59, 130, 246, 0.4)",
        "badge_class": "badge-q2",
        "author": "Hello Stocks Framework",
        "description": "Loại trừ 5 ngành chu kỳ/tài chính. Nền tảng vững chắc, lợi nhuận ổn định: PEG < 2.0, DT 5Y > 50%, DT 1Y > 5%, LN 5Y > 10%, ROE > 15%, D/E < 1.0, FCF > 0.",
        "icon": "⚖️"
    },
    "hello_full_throttle": {
        "id": "hello_full_throttle",
        "name": "🔥 Hello Stocks: Tăng Tốc Toàn Lực (Full Throttle)",
        "short_name": "Hello - Full Throttle",
        "color": "#ec4899",
        "accent_glow": "rgba(236, 72, 153, 0.4)",
        "badge_class": "badge-q3",
        "author": "Hello Stocks Framework",
        "description": "Loại trừ 5 ngành chu kỳ/tài chính. Bùng nổ doanh số mở rộng quy mô: DT 5Y > 100%, DT 1Y > 20%, PEG < 2.0, D/E < 5.0, không giới hạn ROE/FCF.",
        "icon": "🔥"
    },
    "hello_lower_risk_mod": {
        "id": "hello_lower_risk_mod",
        "name": "🌱 Hello Mod: Rủi Ro Thấp (Compounders)",
        "short_name": "Hello Mod - Lower Risk",
        "color": "#10b981",
        "accent_glow": "rgba(16, 185, 129, 0.45)",
        "badge_class": "badge-q1",
        "author": "Two-Tier Hybrid Model",
        "description": "Cổng an toàn T1 (CFO/LNST >= 0.6, Dilution <= 7%, Phi tài chính) + T2: DT 5Y > 40%, Net D/E <= 0.5, Top 25% ROE, PEG_Sales <= 1.25.",
        "icon": "🌱"
    },
    "hello_balanced_risk_mod": {
        "id": "hello_balanced_risk_mod",
        "name": "⚖️ Hello Mod: Cân Bằng (GARP & Margin)",
        "short_name": "Hello Mod - Balanced",
        "color": "#0284c7",
        "accent_glow": "rgba(2, 132, 199, 0.45)",
        "badge_class": "badge-q2",
        "author": "Two-Tier Hybrid Model",
        "description": "Cổng an toàn T1 + T2: DT 5Y > 50%, DT 1Y > 8%, Net D/E <= 0.9, Base Rate Cap 25%, Mở rộng biên EBIT, PEG_Sales <= 1.85.",
        "icon": "⚖️"
    },
    "hello_full_throttle_mod": {
        "id": "hello_full_throttle_mod",
        "name": "🚀 Hello Mod: Tăng Tốc (Operating Leverage)",
        "short_name": "Hello Mod - Throttle",
        "color": "#d946ef",
        "accent_glow": "rgba(217, 70, 239, 0.45)",
        "badge_class": "badge-q3",
        "author": "Two-Tier Hybrid Model",
        "description": "Cổng an toàn T1 + T2: DT 5Y > 80% (hoặc 3Y > 50%), DT 1Y > 18%, D/E <= 2.0, Đòn bẩy hoạt động (LN gộp tăng nhanh hơn SG&A), Top 20% DT.",
        "icon": "🚀"
    },
    "universal_survival_sector_moat": {
        "id": "universal_survival_sector_moat",
        "name": "🛡️ Universal Survival & Sector Moat (Mô Hình 3 Tầng)",
        "short_name": "Survival & Sector Moat",
        "color": "#059669",
        "accent_glow": "rgba(5, 150, 105, 0.45)",
        "badge_class": "badge-q1",
        "author": "Universal Survival & Sector Moat Framework",
        "description": "Tầng 1-2 Chốt chặn Sinh tồn Phi tài chính (ROA >= 10%, Current Ratio >= 1.5, Quick Ratio >= 1.0, ICR >= 2.5, Biên HĐ dương & mở rộng) + Tầng 3 Động cơ 5 nhóm ngành (Bank PB 1-1.8 & ROE > 18%, BĐS D/E < 0.383, IT Rule of 40 & PEG < 0.85, SX Biên Gộp > 14.8% & ROIC > 15%, Tiêu Dùng Cash/Assets > 8% & EPS > 20%).",
        "icon": "🛡️"
    },
    "guru_magic_formula_greenblatt": {
        "id": "guru_magic_formula_greenblatt",
        "name": "🪄 Magic Formula (Joel Greenblatt)",
        "short_name": "Magic Formula (Greenblatt)",
        "color": "#facc15",
        "accent_glow": "rgba(250, 204, 21, 0.4)",
        "badge_class": "badge-q2",
        "author": "Joel Greenblatt (The Little Book That Beats the Market)",
        "description": "Mua công ty tốt với giá rẻ: loại ngành Tài chính & Tiện ích công, Vốn hóa tối thiểu. ROC (ROIC) và Earnings Yield (1/P/E) đều trên trung vị thị trường; xếp hạng Combined Rank = Hạng ROC + Hạng EY.",
        "icon": "🪄"
    },
    "guru_piotroski_fscore": {
        "id": "guru_piotroski_fscore",
        "name": "📋 F-Score 9 Điểm (Joseph Piotroski)",
        "short_name": "F-Score (Piotroski)",
        "color": "#818cf8",
        "accent_glow": "rgba(129, 140, 248, 0.4)",
        "badge_class": "badge-q3",
        "author": "Joseph Piotroski (F-Score Research 2000)",
        "description": "Lượt phục hồi của cổ value: nhóm 20% P/B thấp nhất thị trường + F-Score >= 7/9 (ROA>0, Dòng tiền>0, ROA cải thiện, CFO>LNTT, Nợ vay thấp, Thanh khoản mạnh, Không pha loãng, Biên gộp tốt, Vòng quay TSTS). Thích ứng VN: các tiêu chí so sánh cùng kỳ năm trước được thay bằng chuẩn mức (level-based) do dữ liệu snapshot chỉ có 1 thời điểm.",
        "icon": "📋"
    },
    "guru_zweig_conservative_growth": {
        "id": "guru_zweig_conservative_growth",
        "name": "📈 Conservative Growth (Martin Zweig)",
        "short_name": "Conservative Growth (Zweig)",
        "color": "#2dd4bf",
        "accent_glow": "rgba(45, 212, 191, 0.4)",
        "badge_class": "badge-q1",
        "author": "Martin Zweig (Winning on Wall Street)",
        "description": "Tăng trưởng EPS tăng tốc có nền tảng: LNST 1Y > 0 và cao hơn tốc độ dài hạn >= 15%/năm, DT 5Y & LNST 5Y dương, DT quý xác nhận (DT 1Y > 0), 5 < P/E <= 40, D/E dưới trung vị ngành.",
        "icon": "📈"
    },
    "guru_cornerstone_growth_oshaughnessy": {
        "id": "guru_cornerstone_growth_oshaughnessy",
        "name": "🏛️ Cornerstone Growth (O'Shaughnessy)",
        "short_name": "Cornerstone Growth",
        "color": "#fb923c",
        "accent_glow": "rgba(251, 146, 60, 0.4)",
        "badge_class": "badge-q2",
        "author": "James O'Shaughnessy (What Works on Wall Street)",
        "description": "Value + Momentum: Vốn hóa trên trung vị thị trường, P/S < 1.5, LNST tăng liên tục (1Y/3Y/5Y dương); chọn Top động giá 12 tháng (Relative Strength) từ dữ liệu giá thật TradingView.",
        "icon": "🏛️"
    },
    "guru_cornerstone_value_oshaughnessy": {
        "id": "guru_cornerstone_value_oshaughnessy",
        "name": "🏦 Cornerstone Value (O'Shaughnessy)",
        "short_name": "Cornerstone Value (Div Yield)",
        "color": "#a3e635",
        "accent_glow": "rgba(163, 230, 53, 0.4)",
        "badge_class": "badge-q1",
        "author": "James O'Shaughnessy (What Works on Wall Street)",
        "description": "Large-Cap Value & Cổ tức: Vốn hóa trên trung bình thị trường, Dòng tiền/LNST > 1 (dòng tiền mạnh), trả cổ tức trên trung vị các cổ có cổ tức; chọn Top tỷ suất cổ tức cao nhất.",
        "icon": "🏦"
    },
    "guru_neff_total_return": {
        "id": "guru_neff_total_return",
        "name": "💵 Total Return Low-P/E (John Neff)",
        "short_name": "Total Return (Neff)",
        "color": "#c084fc",
        "accent_glow": "rgba(192, 132, 252, 0.4)",
        "badge_class": "badge-q3",
        "author": "John Neff (Vanguard Windsor Fund)",
        "description": "Tỷ suất Tổng Return / P/E = (Tăng trưởng EPS dài hạn + Cổ tức) / P/E >= 1.0; P/E bằng 40%-70% trung vị thị trường, Tăng trưởng EPS dài hạn 7%-20%, DT 3Y >= 7%, CFO > LNTT.",
        "icon": "💵"
    },
    "guru_consensus_multi_model": {
        "id": "guru_consensus_multi_model",
        "name": "🤝 Multi-Strategy Consensus (Đồng Thuận Đa Chiến Lược)",
        "short_name": "Multi-Strategy Consensus",
        "color": "#f472b6",
        "accent_glow": "rgba(244, 114, 182, 0.45)",
        "badge_class": "badge-q1",
        "author": "The Guru Investor - Consensus Approach (Reese & Forehand)",
        "description": "Mỗi cổ phiếu được chấm điểm bằng số chiến lược CHỌN nó vào rổ cuối (mỗi chiến lược đóng phiếu cho đúng Top N rổ của mình, kể cả cổ lấp chỗ ở chế độ Fill); xếp hạng toàn bộ theo số phiếu giảm dần rồi đến điểm Quant Composite, rót Top N đầu bảng với trọng số bằng nhau.",
        "icon": "🤝"
    },
    "tsmom_moskowitz": {
        "id": "tsmom_moskowitz",
        "name": "⚡ Time Series Momentum (Moskowitz 2012)",
        "short_name": "TSMOM (Moskowitz)",
        "color": "#06b6d4",
        "accent_glow": "rgba(6, 182, 212, 0.45)",
        "badge_class": "badge-q1",
        "author": "Moskowitz, Ooi & Pedersen (JFE 2012)",
        "description": "Mô hình Động lượng Chuỗi Thời gian (Time Series Momentum - JFE 2012): Chỉ mua & nắm giữ cổ phiếu có tỷ suất sinh lời 12 tháng (4 quý) dương (R_12M > 0), xếp hạng & phân bổ tỷ trọng theo độ biến động (Volatility Scaling).",
        "icon": "⚡"
    },
    "quant_q1": {
        "id": "quant_q1",
        "name": "⭐ Quant Q1: Tinh Hoa (P80 - P100)",
        "short_name": "Quant Q1 (Top 20%)",
        "color": "#14b8a6",
        "accent_glow": "rgba(20, 184, 166, 0.4)",
        "badge_class": "badge-q1",
        "author": "Base Rate Framework",
        "description": "Lọc Top 20% cổ phiếu có điểm Composite cao nhất toàn thị trường, hội tụ 4 trụ cột: Tăng trưởng, Chất lượng, Sức khỏe nợ và Định giá.",
        "icon": "⭐"
    },
    "quant_q2": {
        "id": "quant_q2",
        "name": "🔷 Quant Q2: Tốt (P60 - P80)",
        "short_name": "Quant Q2 (Tốt)",
        "color": "#3b82f6",
        "accent_glow": "rgba(59, 130, 246, 0.4)",
        "badge_class": "badge-q2",
        "author": "Base Rate Framework",
        "description": "Nhóm 20% cổ phiếu xếp hạng Tốt (Phân vị 60-80), nền tảng vững chắc và định giá hợp lý.",
        "icon": "🔷"
    },
    "quant_q3": {
        "id": "quant_q3",
        "name": "🟨 Quant Q3: Trung Bình (P40 - P60)",
        "short_name": "Quant Q3 (TB)",
        "color": "#eab308",
        "accent_glow": "rgba(234, 179, 8, 0.4)",
        "badge_class": "badge-q3",
        "author": "Base Rate Framework",
        "description": "Nhóm 20% cổ phiếu mức trung bình thị trường (Phân vị 40-60).",
        "icon": "🟨"
    },
    "quant_q4": {
        "id": "quant_q4",
        "name": "🟧 Quant Q4: Yếu (P20 - P40)",
        "short_name": "Quant Q4 (Yếu)",
        "color": "#f97316",
        "accent_glow": "rgba(249, 115, 22, 0.4)",
        "badge_class": "badge-q4",
        "author": "Base Rate Framework",
        "description": "Nhóm 20% cổ phiếu xếp hạng Yếu (Phân vị 20-40), biên lợi nhuận thấp hoặc nợ cao.",
        "icon": "🟧"
    },
    "quant_q5": {
        "id": "quant_q5",
        "name": "⚠️ Quant Q5: Rủi Ro Cao (P0 - P20)",
        "short_name": "Quant Q5 (Yếu)",
        "color": "#ef4444",
        "accent_glow": "rgba(239, 68, 68, 0.4)",
        "badge_class": "badge-q5",
        "author": "Đối Chứng Phân Vị Ngược",
        "description": "Nhóm 20% cổ phiếu có điểm Composite thấp nhất dùng để kiểm chứng ranh giới phân vị và rủi ro.",
        "icon": "⚠️"
    },
    "vnindex": {
        "id": "vnindex",
        "name": "📈 VN-Index Benchmark (Mua & Nắm Giữ)",
        "short_name": "VN-Index",
        "color": "#94a3b8",
        "accent_glow": "rgba(148, 163, 184, 0.4)",
        "badge_class": "badge-neutral",
        "author": "Thị Trường Chung",
        "description": "Hiệu suất thị trường chung VN-Index mô phỏng theo chiến lược Mua và Nắm giữ toàn bộ chu kỳ.",
        "icon": "📈"
    },
    "custom": {
        "id": "custom",
        "name": "⚙️ Bộ Lọc Tùy Chỉnh (Custom Screener)",
        "short_name": "Bộ Lọc Tùy Chỉnh",
        "color": "#38bdf8",
        "accent_glow": "rgba(56, 189, 248, 0.4)",
        "badge_class": "badge-q2",
        "author": "Người Dùng Tùy Biến",
        "description": "Chiến lược lọc cổ phiếu tùy biến theo các tiêu chí tài chính, ngành, sàn và điểm phân vị người dùng thiết lập.",
        "icon": "⚙️"
    }
}

QUARTERS_TIMELINE = [
    # --- 2016 (VN-Index 570 -> 664, +14.8%) ---
    {"code": "2016-Q1", "date": "2016-03-31", "year": 2016, "quarter": 1, "vni_price": 562.22, "vni_return_pct": -2.9},
    {"code": "2016-Q2", "date": "2016-06-30", "year": 2016, "quarter": 2, "vni_price": 632.26, "vni_return_pct": 12.5},
    {"code": "2016-Q3", "date": "2016-09-30", "year": 2016, "quarter": 3, "vni_price": 685.73, "vni_return_pct": 8.5},
    {"code": "2016-Q4", "date": "2016-12-31", "year": 2016, "quarter": 4, "vni_price": 664.87, "vni_return_pct": -3.0},

    # --- 2017 (VN-Index 664 -> 984, +48.0% Mega Bull Run) ---
    {"code": "2017-Q1", "date": "2017-03-31", "year": 2017, "quarter": 1, "vni_price": 722.31, "vni_return_pct": 8.6},
    {"code": "2017-Q2", "date": "2017-06-30", "year": 2017, "quarter": 2, "vni_price": 776.47, "vni_return_pct": 7.5},
    {"code": "2017-Q3", "date": "2017-09-30", "year": 2017, "quarter": 3, "vni_price": 804.42, "vni_return_pct": 3.6},
    {"code": "2017-Q4", "date": "2017-12-31", "year": 2017, "quarter": 4, "vni_price": 984.24, "vni_return_pct": 22.4},

    # --- 2018 (VN-Index Peak 1204 -> 892 Crash, -9.3%) ---
    {"code": "2018-Q1", "date": "2018-03-31", "year": 2018, "quarter": 1, "vni_price": 1174.46, "vni_return_pct": 19.3},
    {"code": "2018-Q2", "date": "2018-06-30", "year": 2018, "quarter": 2, "vni_price": 960.78, "vni_return_pct": -18.2},
    {"code": "2018-Q3", "date": "2018-09-30", "year": 2018, "quarter": 3, "vni_price": 1017.13, "vni_return_pct": 5.9},
    {"code": "2018-Q4", "date": "2018-12-31", "year": 2018, "quarter": 4, "vni_price": 892.54, "vni_return_pct": -12.2},

    # --- 2019 (VN-Index 892 -> 960 Sideway, +7.7%) ---
    {"code": "2019-Q1", "date": "2019-03-31", "year": 2019, "quarter": 1, "vni_price": 980.76, "vni_return_pct": 9.9},
    {"code": "2019-Q2", "date": "2019-06-30", "year": 2019, "quarter": 2, "vni_price": 949.94, "vni_return_pct": -3.1},
    {"code": "2019-Q3", "date": "2019-09-30", "year": 2019, "quarter": 3, "vni_price": 996.56, "vni_return_pct": 4.9},
    {"code": "2019-Q4", "date": "2019-12-31", "year": 2019, "quarter": 4, "vni_price": 960.99, "vni_return_pct": -3.6},

    # --- 2020 (Covid Crash -> Mega V-Recovery 659 -> 1103, +14.9%) ---
    {"code": "2020-Q1", "date": "2020-03-31", "year": 2020, "quarter": 1, "vni_price": 662.53, "vni_return_pct": -31.1},
    {"code": "2020-Q2", "date": "2020-06-30", "year": 2020, "quarter": 2, "vni_price": 825.11, "vni_return_pct": 24.5},
    {"code": "2020-Q3", "date": "2020-09-30", "year": 2020, "quarter": 3, "vni_price": 905.21, "vni_return_pct": 9.7},
    {"code": "2020-Q4", "date": "2020-12-31", "year": 2020, "quarter": 4, "vni_price": 1103.87, "vni_return_pct": 21.9},

    # --- 2021 (VN-Index 1103 -> 1498, +35.7% F0 Euphoria) ---
    {"code": "2021-Q1", "date": "2021-03-31", "year": 2021, "quarter": 1, "vni_price": 1191.44, "vni_return_pct": 7.9},
    {"code": "2021-Q2", "date": "2021-06-30", "year": 2021, "quarter": 2, "vni_price": 1408.55, "vni_return_pct": 18.2},
    {"code": "2021-Q3", "date": "2021-09-30", "year": 2021, "quarter": 3, "vni_price": 1342.06, "vni_return_pct": -4.7},
    {"code": "2021-Q4", "date": "2021-12-31", "year": 2021, "quarter": 4, "vni_price": 1498.28, "vni_return_pct": 11.6},

    # --- 2022 (VN-Index 1498 -> 1007, -32.8% Bond Crash) ---
    {"code": "2022-Q1", "date": "2022-03-31", "year": 2022, "quarter": 1, "vni_price": 1492.15, "vni_return_pct": -0.4},
    {"code": "2022-Q2", "date": "2022-06-30", "year": 2022, "quarter": 2, "vni_price": 1197.60, "vni_return_pct": -19.7},
    {"code": "2022-Q3", "date": "2022-09-30", "year": 2022, "quarter": 3, "vni_price": 1132.11, "vni_return_pct": -5.5},
    {"code": "2022-Q4", "date": "2022-12-31", "year": 2022, "quarter": 4, "vni_price": 1007.09, "vni_return_pct": -11.0},

    # --- 2023 (VN-Index 1007 -> 1129, +12.2% Recovery) ---
    {"code": "2023-Q1", "date": "2023-03-31", "year": 2023, "quarter": 1, "vni_price": 1064.64, "vni_return_pct": 5.7},
    {"code": "2023-Q2", "date": "2023-06-30", "year": 2023, "quarter": 2, "vni_price": 1120.18, "vni_return_pct": 5.2},
    {"code": "2023-Q3", "date": "2023-09-30", "year": 2023, "quarter": 3, "vni_price": 1154.15, "vni_return_pct": 3.0},
    {"code": "2023-Q4", "date": "2023-12-31", "year": 2023, "quarter": 4, "vni_price": 1129.93, "vni_return_pct": -2.1},

    # --- 2024 (VN-Index 1129 -> 1262, +11.8%) ---
    {"code": "2024-Q1", "date": "2024-03-31", "year": 2024, "quarter": 1, "vni_price": 1284.09, "vni_return_pct": 13.6},
    {"code": "2024-Q2", "date": "2024-06-30", "year": 2024, "quarter": 2, "vni_price": 1245.32, "vni_return_pct": -3.0},
    {"code": "2024-Q3", "date": "2024-09-30", "year": 2024, "quarter": 3, "vni_price": 1287.94, "vni_return_pct": 3.4},
    {"code": "2024-Q4", "date": "2024-12-31", "year": 2024, "quarter": 4, "vni_price": 1262.80, "vni_return_pct": -1.9},

    # --- 2025 (VN-Index 1262 -> 1425, +12.8%) ---
    {"code": "2025-Q1", "date": "2025-03-31", "year": 2025, "quarter": 1, "vni_price": 1318.50, "vni_return_pct": 4.4},
    {"code": "2025-Q2", "date": "2025-06-30", "year": 2025, "quarter": 2, "vni_price": 1365.20, "vni_return_pct": 3.5},
    {"code": "2025-Q3", "date": "2025-09-30", "year": 2025, "quarter": 3, "vni_price": 1398.40, "vni_return_pct": 2.4},
    {"code": "2025-Q4", "date": "2025-12-31", "year": 2025, "quarter": 4, "vni_price": 1425.00, "vni_return_pct": 1.9},

    # --- 2026 YTD ---
    {"code": "2026-Q1", "date": "2026-03-31", "year": 2026, "quarter": 1, "vni_price": 1460.50, "vni_return_pct": 2.5}
]

def get_strategy_definitions() -> Dict[str, Any]:
    return STRATEGY_DEFINITIONS

_REAL_PRICES_CACHE = None
_REAL_PRICES_MTIME = 0
_REAL_PRICES_FROZEN = False

def _freeze_real_price_database() -> None:
    """Pin the price database in memory for the duration of one compare run."""
    global _REAL_PRICES_FROZEN
    _load_real_price_database()
    _REAL_PRICES_FROZEN = True

def _unfreeze_real_price_database() -> None:
    global _REAL_PRICES_FROZEN
    _REAL_PRICES_FROZEN = False

def _load_real_price_database() -> Dict[str, Any]:
    global _REAL_PRICES_CACHE, _REAL_PRICES_MTIME
    if _REAL_PRICES_FROZEN and _REAL_PRICES_CACHE is not None:
        return _REAL_PRICES_CACHE

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_path = os.path.join(base_dir, "data", "historical_prices.json")
    resolved_path = resolve_data_file("historical_prices.json")

    paths_to_check = [local_path]
    if resolved_path and os.path.abspath(resolved_path) != os.path.abspath(local_path) and os.path.exists(resolved_path):
        paths_to_check.append(resolved_path)

    # Check modification time to avoid reloading multi-megabyte JSON on every single stock
    max_mtime = 0.0
    for p in paths_to_check:
        if os.path.exists(p):
            try:
                m = os.path.getmtime(p)
                if m > max_mtime:
                    max_mtime = m
            except Exception:
                pass

    if _REAL_PRICES_CACHE is not None and max_mtime > 0 and max_mtime <= _REAL_PRICES_MTIME:
        return _REAL_PRICES_CACHE

    merged_symbols: Dict[str, Any] = {}

    for target_path in paths_to_check:
        if not os.path.exists(target_path):
            continue
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("symbols", data) if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                for sym, val in raw.items():
                    if isinstance(val, dict) and "quarters" in val and isinstance(val.get("quarters"), dict):
                        # Always keep valid quarterly dataset, preferring richer quarters if available
                        if sym not in merged_symbols or len(val["quarters"]) > len(merged_symbols[sym].get("quarters", {})):
                            merged_symbols[sym] = val
        except Exception:
            pass

    _REAL_PRICES_CACHE = merged_symbols
    _REAL_PRICES_MTIME = max_mtime if max_mtime > 0 else 1.0
    return _REAL_PRICES_CACHE

def _v_above(value, floor):
    if value is None:
        return 1.0
    denom = abs(floor) if abs(floor) > 1e-9 else 1.0
    return min(10.0, max(0.0, (floor - value) / denom))

def _v_below(value, ceiling):
    if value is None:
        return 1.0
    denom = abs(ceiling) if abs(ceiling) > 1e-9 else 1.0
    return min(10.0, max(0.0, (value - ceiling) / denom))

def _v_positive(value):
    if value is None:
        return 1.0
    return 0.0 if value > 0 else 1.0

_QUINTILE_BANDS = {
    "Q1": (80.0, 101.0),
    "Q2": (60.0, 80.0),
    "Q3": (40.0, 60.0),
    "Q4": (20.0, 40.0),
    "Q5": (-1.0, 20.0)
}

def _quintile_band_violation(quintile):
    lo, hi = _QUINTILE_BANDS[quintile]
    # Distance to the band CENTER (not the edge): adjacent quintiles share
    # boundaries, so edge-distance makes e.g. Q3-fill and Q4-fill pick the very
    # same stocks. Center-distance gives every band its own representative.
    center = (lo + hi) / 2.0

    def _inner(c):
        comp = c.get("percentiles", {}).get("composite", 50.0)
        if lo <= comp < hi:
            return 0.0
        return round(abs(comp - center), 4)

    return _inner

def _quintile_fill_signature(quintile):
    """Fill preference for quintile strategies: proximity to the band center.
    Keeps each band's padded basket representative of ITS percentile instead of
    collapsing onto the global top-composite names (which duplicated Q1)."""
    lo, hi = _QUINTILE_BANDS[quintile]
    center = (lo + hi) / 2.0

    def _inner(c):
        comp = c.get("percentiles", {}).get("composite", 50.0)
        return round(abs(comp - center), 4)

    return _inner

HELLO_EXCLUDED_SECTORS_NM = {"VNFIN", "VNMAT", "VNENE", "VNUTI", "VNREAL"}

def _hello_sector_violation(c):
    return 3.0 if c.get("sector_code") in HELLO_EXCLUDED_SECTORS_NM else 0.0

def _mod_tier1_criteria():
    return [
        lambda c: 3.0 if c.get("sector_code") == "VNFIN" else 0.0,
        lambda c: _v_above(c.get("cfo_to_pat", 1.0), 0.6),
        lambda c: _v_above(c.get("gross_margin", 20.0), 0.0),
        lambda c: _v_above(c.get("op_margin", 10.0), 0.0),
        lambda c: _v_below(c.get("share_dilution_3y", 2.0), 7.0),
    ]

def _moat_near_miss_violation(c):
    sec = c.get("sector_code", "")
    pb = c.get("pb", 99.0)
    roe = c.get("roe", 0.0)
    roa = c.get("roa", 0.0)
    de = c.get("de_ratio", 99.0)
    cur_r = c.get("current_ratio", 1.5)
    quick_r = c.get("quick_ratio", cur_r * 0.75)
    icr = c.get("interest_coverage", 3.0)
    c_to_a = c.get("cash_to_assets", 9.0)
    r40 = c.get("rule_of_40", c.get("rev_1y_growth", 10.0) + c.get("net_margin", 10.0))
    s_roic = c.get("roic", roe * 0.8)
    gross_m = c.get("gross_margin", 20.0)
    op_m = c.get("op_margin", 10.0)
    rev_1y = c.get("rev_1y_growth", 0.0)
    pat_1y = c.get("pat_1y_growth", 0.0)
    peg = c.get("peg", 99.0)
    pe = c.get("pe", 99.0)

    if sec == "VNFIN":
        pb_lo = 0.0 if pb >= 1.0 else min(10.0, 1.0 - pb)
        pb_hi = 0.0 if pb <= 1.8 else min(10.0, (pb - 1.8) / 2.0)
        return round(_v_above(roe, 18.0) + pb_lo + pb_hi, 4)

    firewall = (
        _v_above(roa, 9.5)
        + _v_above(cur_r, 1.45)
        + min(_v_above(quick_r, 0.95), _v_above(cur_r, 1.5))
        + _v_above(icr, 2.4)
        + _v_positive(op_m)
    )

    if sec == "VNREAL":
        sub = _v_below(de, 0.383) + _v_below(pb, 1.8)
    elif sec == "VNIT":
        sub = _v_above(r40, 38.0) + _v_below(peg, 0.9) + _v_above(roe, 22.0) + _v_below(de, 0.35)
    elif sec in {"VNMAT", "VNIND", "VNENE", "VNUTI"}:
        sub = _v_above(gross_m, 14.5) + min(_v_above(s_roic, 14.0), _v_above(roe, 15.0)) + _v_below(de, 0.70)
    elif sec in {"VNCOND", "VNCONS", "VNHEAL"}:
        pe_band = max(_v_above(pe, 8.0), _v_below(pe, 16.0))
        sub = (
            min(_v_above(c_to_a, 7.5), _v_above(cur_r, 1.5))
            + min(_v_above(pat_1y, 18.0), _v_above(rev_1y, 15.0))
            + min(pe_band, _v_below(peg, 1.0))
        )
    else:
        sub = _v_above(roe, 16.0) + _v_below(de, 0.8)

    return round(firewall + sub, 4)

def _buffett_alpha_passes(c: Dict[str, Any]) -> bool:
    sec = c.get("sector_code", "")
    pe = c.get("pe", 99.0) or 99.0
    pb = c.get("pb", 99.0) or 99.0
    roe = c.get("roe", 0.0) or 0.0
    roic = c.get("roic", 0.0) or 0.0
    gross_m = c.get("gross_margin", 0.0) or 0.0
    cfo_pat = c.get("cfo_to_pat", 1.0) or 1.0
    de = c.get("de_ratio", 99.0) or 99.0
    net_de = c.get("net_de_ratio", de) or de
    div_y = c.get("dividend_yield", 0.0) or 0.0
    fcf = c.get("fcf_ttm", 0.0) or 0.0

    if sec == "VNFIN":
        return roe >= 18.0 and 0 < pb <= 1.5 and 0 < pe <= 12.0 and div_y > 0
    else:
        return (
            (roic >= 15.0 or roe >= 18.0)
            and gross_m >= 20.0
            and net_de <= 0.5
            and cfo_pat >= 0.8
            and fcf > 0
            and 0 < pe <= 13.5
            and div_y > 0
        )

def _buffett_alpha_violation(c: Dict[str, Any]) -> float:
    sec = c.get("sector_code", "")
    pe = c.get("pe", 99.0) or 99.0
    pb = c.get("pb", 99.0) or 99.0
    roe = c.get("roe", 0.0) or 0.0
    roic = c.get("roic", 0.0) or 0.0
    gross_m = c.get("gross_margin", 0.0) or 0.0
    cfo_pat = c.get("cfo_to_pat", 1.0) or 1.0
    de = c.get("de_ratio", 99.0) or 99.0
    net_de = c.get("net_de_ratio", de) or de
    div_y = c.get("dividend_yield", 0.0) or 0.0
    fcf = c.get("fcf_ttm", 0.0) or 0.0

    if sec == "VNFIN":
        return round(
            _v_above(roe, 18.0)
            + _v_positive(pb) + _v_below(pb, 1.5)
            + _v_positive(pe) + _v_below(pe, 12.0)
            + _v_above(div_y, 0.0),
            4
        )
    else:
        q_score = min(_v_above(roic, 15.0), _v_above(roe, 18.0))
        return round(
            q_score
            + _v_above(gross_m, 20.0)
            + _v_below(net_de, 0.5)
            + _v_above(cfo_pat, 0.8)
            + _v_above(fcf, 0.0)
            + _v_positive(pe) + _v_below(pe, 13.5)
            + _v_above(div_y, 0.0),
            4
        )

# =========================================================================
# 1. ROBERT NOVY-MARX: GROSS PROFITABILITY & VALUE
# =========================================================================
def _novy_marx_passes(c: Dict[str, Any]) -> bool:
    price = c.get("price", 0.0) or 0.0
    mcap = c.get("market_cap", 0.0) or 0.0
    if price < 4.0 or mcap < 200.0:
        return False
    gross_m = c.get("gross_margin", 0.0) or 0.0
    roe = c.get("roe", 0.0) or 0.0
    roic = c.get("roic", 0.0) or 0.0
    if not (gross_m >= 22.0 and (roic >= 13.0 or roe >= 15.0)):
        return False
    pe = c.get("pe", 99.0) or 99.0
    pb = c.get("pb", 99.0) or 99.0
    if not (0 < pe <= 13.5 or 0 < pb <= 1.8):
        return False
    cfo_pat = c.get("cfo_to_pat", 1.0) or 1.0
    if cfo_pat < 0.8:
        return False
    de = c.get("de_ratio", 99.0) or 99.0
    net_de = c.get("net_de_ratio", de) or de
    if net_de > 0.60:
        return False
    if (c.get("fcf_ttm", 0.0) or 0.0) <= 0:
        return False
    return True

def _novy_marx_violation(c: Dict[str, Any]) -> float:
    price = c.get("price", 0.0) or 0.0
    mcap = c.get("market_cap", 0.0) or 0.0
    gross_m = c.get("gross_margin", 0.0) or 0.0
    roe = c.get("roe", 0.0) or 0.0
    roic = c.get("roic", 0.0) or 0.0
    pe = c.get("pe", 99.0) or 99.0
    pb = c.get("pb", 99.0) or 99.0
    cfo_pat = c.get("cfo_to_pat", 1.0) or 1.0
    de = c.get("de_ratio", 99.0) or 99.0
    net_de = c.get("net_de_ratio", de) or de
    fcf = c.get("fcf_ttm", 0.0) or 0.0
    return round(
        _v_above(price, 4.0) + _v_above(mcap, 200.0)
        + _v_above(gross_m, 22.0) + min(_v_above(roic, 13.0), _v_above(roe, 15.0))
        + min(_v_positive(pe) + _v_below(pe, 13.5), _v_positive(pb) + _v_below(pb, 1.8))
        + _v_above(cfo_pat, 0.8)
        + _v_below(net_de, 0.60)
        + _v_above(fcf, 0.0),
        4
    )

# =========================================================================
# 2. TOBIAS CARLISLE: THE ACQUIRER'S MULTIPLE
# =========================================================================
# =========================================================================
# 2. WESLEY GRAY & ALPHA ARCHITECT: QUANTITATIVE VALUE (Q-VAL)
# =========================================================================
def _qval_passes(c: Dict[str, Any]) -> bool:
    if c.get("sector_code") == "VNFIN":
        return False
    price = c.get("price", 0.0) or 0.0
    mcap = c.get("market_cap", 0.0) or 0.0
    if price < 4.0 or mcap < 250.0:
        return False
    # Forensic & Dilution
    cfo_pat = c.get("cfo_to_pat", 1.0) or 1.0
    if cfo_pat < 0.90:
        return False
    dilution = c.get("share_dilution_3y", 2.0) or 2.0
    if dilution > 3.5:
        return False
    # Distress Firewall
    if _piotroski_fscore(c) < 7:
        return False
    cur_r = c.get("current_ratio", 1.5) or 1.5
    if cur_r < 1.30:
        return False
    de = c.get("de_ratio", 99.0) or 99.0
    if de > 0.75:
        return False
    # Valuation & Moat
    pe = c.get("pe", 99.0) or 99.0
    pb = c.get("pb", 99.0) or 99.0
    if not (0 < pe <= 13.0 or 0 < pb <= 1.6):
        return False
    roe = c.get("roe", 0.0) or 0.0
    roic = c.get("roic", 0.0) or 0.0
    if not (roe >= 15.0 or roic >= 12.0):
        return False
    if (c.get("fcf_ttm", 0.0) or 0.0) <= 0:
        return False
    div_y = c.get("dividend_yield", 0.0) or 0.0
    if div_y < 1.5:
        return False
    return True

def _qval_violation(c: Dict[str, Any]) -> float:
    sec_pen = 5.0 if c.get("sector_code") == "VNFIN" else 0.0
    price = c.get("price", 0.0) or 0.0
    mcap = c.get("market_cap", 0.0) or 0.0
    cfo_pat = c.get("cfo_to_pat", 1.0) or 1.0
    dilution = c.get("share_dilution_3y", 2.0) or 2.0
    fscore = _piotroski_fscore(c)
    cur_r = c.get("current_ratio", 1.5) or 1.5
    de = c.get("de_ratio", 99.0) or 99.0
    pe = c.get("pe", 99.0) or 99.0
    pb = c.get("pb", 99.0) or 99.0
    roe = c.get("roe", 0.0) or 0.0
    roic = c.get("roic", 0.0) or 0.0
    fcf = c.get("fcf_ttm", 0.0) or 0.0
    div_y = c.get("dividend_yield", 0.0) or 0.0
    return round(
        sec_pen
        + _v_above(price, 4.0) + _v_above(mcap, 250.0)
        + _v_above(cfo_pat, 0.90) + _v_below(dilution, 3.5)
        + (0.0 if fscore >= 7 else (7 - fscore) * 0.5)
        + _v_above(cur_r, 1.30) + _v_below(de, 0.75)
        + min(_v_positive(pe) + _v_below(pe, 13.0), _v_positive(pb) + _v_below(pb, 1.6))
        + min(_v_above(roe, 15.0), _v_above(roic, 12.0))
        + _v_above(fcf, 0.0) + _v_above(div_y, 1.5),
        4
    )

STRATEGY_NEAR_MISS_CRITERIA = {
    "deep_value_klarman": [
        lambda c: _v_positive(c.get("pb", 99)),
        lambda c: _v_below(c.get("pb", 99), 1.0),
        lambda c: _v_above(c.get("fcf_ttm", 0), 0.0),
        lambda c: _v_above(c.get("de_ratio", 99), 0.0),
        lambda c: _v_below(c.get("de_ratio", 99), 0.5),
    ],
    "ps_focus_fisher": [
        lambda c: _v_positive(c.get("ps", 99)),
        lambda c: _v_below(c.get("ps", 99), 1.0),
        lambda c: _v_above(c.get("rev_1y_growth", 0), 5.0),
        lambda c: _v_above(c.get("rev_3y_cagr", 0), 25.0),
    ],
    "contrarian_dreman": [
        lambda c: _v_positive(c.get("pe", 99)),
        lambda c: _v_below(c.get("pe", 99), 12.0),
        lambda c: _v_above(c.get("dividend_yield", 0), 3.0),
        lambda c: _v_above(c.get("roe", 0), 15.0),
    ],
    "growth_philip_fisher": [
        lambda c: _v_above(c.get("pat_1y_growth", 0), 15.0),
        lambda c: _v_above(c.get("rev_1y_growth", 0), 10.0),
        lambda c: _v_above(c.get("rev_3y_cagr", 0), 40.0),
        lambda c: _v_above(c.get("rev_5y_growth", 0), 75.0),
        lambda c: _v_above(c.get("roe", 0), 20.0),
    ],
    "peter_lynch_garp": [
        lambda c: _v_positive(c.get("peg", 99)),
        lambda c: _v_below(c.get("peg", 99), 1.0),
        lambda c: _v_above(c.get("pe", 99), 10.0),
        lambda c: _v_below(c.get("pe", 99), 30.0),
        lambda c: _v_above(c.get("pat_1y_growth", 0), 10.0),
        lambda c: _v_above(c.get("rev_3y_cagr", 0), 20.0),
    ],
    "defensive_graham": [
        lambda c: _v_positive(c.get("pe", 99)),
        lambda c: _v_below(c.get("pe", 99), 10.0),
        lambda c: _v_positive(c.get("pb", 99)),
        lambda c: _v_below(c.get("pb", 99), 1.0),
        lambda c: _v_above(c.get("de_ratio", 99), 0.0),
        lambda c: _v_below(c.get("de_ratio", 99), 0.5),
        lambda c: _v_above(c.get("dividend_yield", 0), 2.0),
    ],
    "value_buffett": [
        lambda c: _v_above(c.get("roe", 0), 20.0),
        lambda c: _v_above(c.get("de_ratio", 99), 0.0),
        lambda c: _v_below(c.get("de_ratio", 99), 0.5),
        lambda c: _v_above(c.get("fcf_ttm", 0), 0.0),
        lambda c: _v_positive(c.get("pe", 99)),
        lambda c: _v_below(c.get("pe", 99), 25.0),
        lambda c: _v_positive(c.get("pb", 99)),
        lambda c: _v_below(c.get("pb", 99), 5.0),
        lambda c: _v_above(c.get("rev_5y_growth", 0), 20.0),
        lambda c: _v_above(c.get("dividend_yield", 0), 0.0),
    ],
    "buffetts_alpha": [
        lambda c: _buffett_alpha_violation(c),
    ],
    "novy_marx_quality_value": [
        lambda c: _novy_marx_violation(c),
    ],
    "gray_quantitative_value_qval": [
        lambda c: _qval_violation(c),
    ],
    "hello_lower_risk": [
        lambda c: _hello_sector_violation(c),
        lambda c: _v_positive(c.get("peg", 99)),
        lambda c: _v_below(c.get("peg", 99), 1.0),
        lambda c: _v_above(c.get("rev_5y_growth", 0), 50.0),
        lambda c: _v_above(c.get("rev_1y_growth", 0), 5.0),
        lambda c: _v_above(c.get("pat_1y_growth", 0), 5.0),
        lambda c: _v_above(c.get("roe", 0), 15.0),
        lambda c: _v_above(c.get("de_ratio", 99), 0.0),
        lambda c: _v_below(c.get("de_ratio", 99), 1.0),
        lambda c: _v_above(c.get("fcf_ttm", 0), 0.0),
    ],
    "hello_balanced_risk": [
        lambda c: _hello_sector_violation(c),
        lambda c: _v_positive(c.get("peg", 99)),
        lambda c: _v_below(c.get("peg", 99), 2.0),
        lambda c: _v_above(c.get("rev_5y_growth", 0), 50.0),
        lambda c: _v_above(c.get("rev_1y_growth", 0), 5.0),
        lambda c: _v_above(c.get("pat_5y_growth", 0), 10.0),
        lambda c: _v_above(c.get("roe", 0), 15.0),
        lambda c: _v_above(c.get("de_ratio", 99), 0.0),
        lambda c: _v_below(c.get("de_ratio", 99), 1.0),
        lambda c: _v_above(c.get("fcf_ttm", 0), 0.0),
    ],
    "hello_full_throttle": [
        lambda c: _hello_sector_violation(c),
        lambda c: _v_above(c.get("rev_5y_growth", 0), 100.0),
        lambda c: _v_above(c.get("rev_1y_growth", 0), 20.0),
        lambda c: _v_positive(c.get("peg", 99)),
        lambda c: _v_below(c.get("peg", 99), 2.0),
        lambda c: _v_above(c.get("de_ratio", 99), 0.0),
        lambda c: _v_below(c.get("de_ratio", 99), 5.0),
    ],
    "hello_lower_risk_mod": _mod_tier1_criteria() + [
        lambda c: _v_above(c.get("rev_5y_growth", 0), 40.0),
        lambda c: _v_below(c.get("net_de_ratio", c.get("de_ratio", 0.5)), 0.5),
        lambda c: _v_below(c.get("peg_sales", c.get("peg", 1.0)), 1.35),
        lambda c: _v_above(c.get("roe", 0), 16.0),
    ],
    "hello_balanced_risk_mod": _mod_tier1_criteria() + [
        lambda c: _v_above(c.get("rev_5y_growth", 0), 50.0),
        lambda c: _v_above(c.get("rev_1y_growth", 0), 8.0),
        lambda c: _v_below(c.get("net_de_ratio", c.get("de_ratio", 0.8)), 0.9),
        lambda c: _v_above(c.get("roe", 0), 15.0),
        lambda c: _v_below(c.get("peg_sales", c.get("peg", 1.5)), 1.85),
    ],
    "hello_full_throttle_mod": _mod_tier1_criteria() + [
        lambda c: min(_v_above(c.get("rev_5y_growth", 0), 80.0), _v_above(c.get("rev_3y_cagr", 0), 15.0)),
        lambda c: _v_above(c.get("rev_1y_growth", 0), 18.0),
        lambda c: _v_below(c.get("de_ratio", 1.0), 2.0),
        lambda c: _v_above(c.get("fcf_ttm", 1.0), 0.0),
        lambda c: _v_below(c.get("peg_sales", c.get("peg", 2.0)), 2.8),
    ],
    "universal_survival_sector_moat": [
        lambda c: _moat_near_miss_violation(c),
    ],
    "tsmom_moskowitz": [
        lambda c: _v_above(_t12m_momentum(_load_real_price_database(), c.get("symbol")), 0.0),
    ],
    "quant_q1": [_quintile_band_violation("Q1")],
    "quant_q2": [_quintile_band_violation("Q2")],
    "quant_q3": [_quintile_band_violation("Q3")],
    "quant_q4": [_quintile_band_violation("Q4")],
    "quant_q5": [_quintile_band_violation("Q5")],
}

def _safe_sig_component(v):
    """Make signature elements always comparable (None/NaN used to crash sorts
    once the signature is promoted ahead of the violation magnitude)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
        return (0, float(v))
    return (1, 0.0)

def _resolve_basket(passing, candidates, signature_key, criteria, top_k, fill_mode, tiebreak_seed="", fill_signature=None):
    passing_ids = {id(s) for s in passing}
    passing_sorted = sorted(passing, key=signature_key)
    if len(passing_sorted) >= top_k or fill_mode != "fill":
        basket = passing_sorted[:top_k]
    else:
        fsig_fn = fill_signature or signature_key

        def near_miss_key(c):
            vols = [max(0.0, float(crit(c))) for crit in criteria]
            violated = sum(1 for v in vols if v > 1e-9)
            total = round(sum(vols), 6)
            sig = fsig_fn(c)
            sig_tuple = tuple(sig) if isinstance(sig, (tuple, list)) else (sig,)
            safe_sig = tuple(_safe_sig_component(x) for x in sig_tuple)
            # Key order is deliberate:
            #   violated      -> stay as close to qualifying as possible
            #   safe_sig      -> then the FILL preference breaks ties, so two
            #                    strategies sharing criteria no longer collapse
            #                    into one identical filled basket
            #   total         -> raw closeness only decides exact residual ties
            #   jitter        -> stable per-(strategy,symbol) last resort against
            #                    degenerate data clumps (hundreds of equal scores)
            jitter = _deterministic_hash(f"{tiebreak_seed}|{c.get('symbol', '')}")
            return (violated, safe_sig, total, jitter)

        basket = sorted(candidates, key=near_miss_key)[:top_k]

    annotated = []
    for s in basket:
        row = dict(s)
        meets = id(s) in passing_ids
        row["meets_criteria"] = meets
        if criteria and not meets:
            try:
                row["near_miss_score"] = round(sum(max(0.0, float(cr(s))) for cr in criteria), 6)
            except Exception:
                row["near_miss_score"] = None
        annotated.append(row)
    return annotated

GURU_EXCLUDED_SECTORS_GREENBLATT = {"VNFIN", "VNUTI"}

GURU_MODEL_LABELS = {
    "greenblatt_magic_formula": "🪄 Greenblatt Magic Formula",
    "piotroski_f_score": "📋 Piotroski F-Score",
    "zweig_conservative_growth": "📈 Zweig Conservative Growth",
    "osh_cornerstone_growth": "🏛️ O'Shaughnessy Cornerstone Growth",
    "osh_cornerstone_value": "🏦 O'Shaughnessy Cornerstone Value",
    "neff_total_return": "💵 Neff Total Return"
}

def _t12m_momentum(price_db, symbol):
    info = (price_db or {}).get(symbol) if isinstance(price_db, dict) else None
    if not isinstance(info, dict):
        return -999.0
    quarters = info.get("quarters")
    if not isinstance(quarters, dict) or not quarters:
        return -999.0
    codes = sorted(quarters.keys())[-4:]
    if len(codes) < 4:
        return -999.0
    try:
        return round(sum(float(quarters[c].get("return_pct", 0.0)) for c in codes), 2)
    except Exception:
        return -999.0

def _piotroski_fscore(c):
    score = 0
    if (c.get("roa", 0.0) or 0.0) > 0:
        score += 1
    if (c.get("cfo_to_pat", 1.0) or 1.0) >= 0.6:
        score += 1
    if (c.get("pat_1y_growth", 0) or 0) > 0:
        score += 1
    if (c.get("cfo_to_pat", 1.0) or 1.0) >= 1.0:
        score += 1
    if (c.get("de_ratio", 99) or 99) < 1.0:
        score += 1
    if (c.get("current_ratio", 1.5) or 1.5) >= 1.5:
        score += 1
    if (c.get("share_dilution_3y", 2.0) or 2.0) <= 2.0:
        score += 1
    if (c.get("gross_margin", 20.0) or 20.0) >= 20.0:
        score += 1
    if (c.get("rev_1y_growth", 0) or 0) > 0:
        score += 1
    return score

def _guru_market_context(candidates):
    def _num(v):
        return isinstance(v, (int, float))

    caps = sorted([float(c.get("market_cap")) for c in candidates if _num(c.get("market_cap"))])
    cap_median = caps[len(caps) // 2] if caps else 0.0
    cap_mean = round(sum(caps) / len(caps), 2) if caps else 0.0

    pes = sorted([float(c.get("pe")) for c in candidates if _num(c.get("pe")) and c.get("pe", 0) > 0])
    pe_median = pes[len(pes) // 2] if pes else 15.0

    elig_roic = []
    elig_ey = []
    for c in candidates:
        if c.get("sector_code") in GURU_EXCLUDED_SECTORS_GREENBLATT:
            continue
        if not (_num(c.get("market_cap")) and c.get("market_cap", 0) >= cap_median):
            continue
        if _num(c.get("roic")) and c.get("roic", 0) > 0 and _num(c.get("pe")) and c.get("pe", 0) > 0:
            elig_roic.append(float(c["roic"]))
            elig_ey.append(100.0 / float(c["pe"]))
    elig_roic.sort()
    elig_ey.sort()
    roic_median = elig_roic[len(elig_roic) // 2] if elig_roic else 7.0
    ey_median = elig_ey[len(elig_ey) // 2] if elig_ey else 7.0

    pbs = sorted([float(c.get("pb")) for c in candidates if _num(c.get("pb")) and c.get("pb", 0) > 0])
    pb_q20 = pbs[min(len(pbs) - 1, int(len(pbs) * 0.2))] if pbs else 1.0

    divs = sorted([float(c.get("dividend_yield")) for c in candidates if _num(c.get("dividend_yield")) and c.get("dividend_yield", 0) > 0])
    div_median = divs[len(divs) // 2] if divs else 2.0

    by_sector = {}
    for c in candidates:
        sec = c.get("sector_code")
        if sec and _num(c.get("de_ratio")):
            by_sector.setdefault(sec, []).append(float(c["de_ratio"]))
    sector_de_median = {}
    for sec, vals in by_sector.items():
        vals.sort()
        sector_de_median[sec] = vals[len(vals) // 2]

    return {
        "cap_median": cap_median,
        "cap_mean": cap_mean,
        "pe_median": pe_median,
        "roic_median_eligible": roic_median,
        "ey_median_eligible": ey_median,
        "pb_q20": pb_q20,
        "dividend_median_positive": div_median,
        "sector_de_median": sector_de_median
    }

def evaluate_guru_model(model_id, c, ctx, price_db=None):
    def _num(v):
        return isinstance(v, (int, float))

    if model_id == "greenblatt_magic_formula":
        if c.get("sector_code") in GURU_EXCLUDED_SECTORS_GREENBLATT:
            return False
        if not (_num(c.get("market_cap")) and c.get("market_cap", 0) >= ctx["cap_median"]):
            return False
        if not (_num(c.get("roic")) and c.get("roic", 0) > 0):
            return False
        if not (_num(c.get("pe")) and c.get("pe", 0) > 0):
            return False
        return c.get("roic") >= ctx["roic_median_eligible"] and (100.0 / c.get("pe")) >= ctx["ey_median_eligible"]

    if model_id == "piotroski_f_score":
        if not (_num(c.get("pb")) and 0 < c.get("pb", 0) <= ctx["pb_q20"]):
            return False
        return _piotroski_fscore(c) >= 7

    if model_id == "zweig_conservative_growth":
        pat1 = c.get("pat_1y_growth", 0) or 0
        eps3 = c.get("eps_3y_cagr", 0) or 0
        pe_v = c.get("pe")
        de_v = c.get("de_ratio")
        if pat1 <= 0 or pat1 <= eps3 or eps3 < 15.0:
            return False
        if (c.get("pat_5y_growth", 0) or 0) <= 0 or (c.get("rev_5y_growth", 0) or 0) <= 0:
            return False
        if (c.get("rev_1y_growth", 0) or 0) <= 0:
            return False
        if not (_num(pe_v) and 5.0 < pe_v <= 40.0):
            return False
        if not (_num(de_v) and de_v < ctx["sector_de_median"].get(c.get("sector_code", ""), 1.0)):
            return False
        return True

    if model_id == "osh_cornerstone_growth":
        ps_v = c.get("ps")
        if not (_num(c.get("market_cap")) and c.get("market_cap", 0) > ctx["cap_median"]):
            return False
        if not (_num(ps_v) and 0 < ps_v < 1.5):
            return False
        if (c.get("pat_1y_growth", 0) or 0) <= 0 or (c.get("pat_3y_cagr", 0) or 0) <= 0 or (c.get("pat_5y_growth", 0) or 0) <= 0:
            return False
        return True

    if model_id == "osh_cornerstone_value":
        div_v = c.get("dividend_yield")
        if not (_num(c.get("market_cap")) and c.get("market_cap", 0) > ctx["cap_mean"]):
            return False
        if not (_num(c.get("cfo_to_pat")) and c.get("cfo_to_pat", 0) > 1.0):
            return False
        return bool(_num(div_v) and div_v >= ctx["dividend_median_positive"])

    if model_id == "neff_total_return":
        eps3 = c.get("eps_3y_cagr", 0) or 0
        div_v = c.get("dividend_yield", 0) or 0
        pe_v = c.get("pe")
        if not (_num(pe_v) and pe_v > 0):
            return False
        neff_ratio = (eps3 + div_v) / pe_v
        if neff_ratio < 1.0:
            return False
        if not (0.4 * ctx["pe_median"] <= pe_v <= 0.7 * ctx["pe_median"]):
            return False
        if not (7.0 <= eps3 <= 20.0):
            return False
        if (c.get("rev_3y_cagr", 0) or 0) < 7.0:
            return False
        if not (_num(c.get("cfo_to_pat")) and c.get("cfo_to_pat", 0) > 1.0):
            return False
        return True

    return False

GURU_MODEL_IDS = [
    "greenblatt_magic_formula",
    "piotroski_f_score",
    "zweig_conservative_growth",
    "osh_cornerstone_growth",
    "osh_cornerstone_value",
    "neff_total_return"
]

GURU_STRATEGY_TO_MODEL = {
    "guru_magic_formula_greenblatt": "greenblatt_magic_formula",
    "guru_piotroski_fscore": "piotroski_f_score",
    "guru_zweig_conservative_growth": "zweig_conservative_growth",
    "guru_cornerstone_growth_oshaughnessy": "osh_cornerstone_growth",
    "guru_cornerstone_value_oshaughnessy": "osh_cornerstone_value",
    "guru_neff_total_return": "neff_total_return"
}

def count_guru_approvals(c, ctx, price_db=None):
    return sum(1 for m in GURU_MODEL_IDS if evaluate_guru_model(m, c, ctx, price_db))

def _moat_strategy_passes(c):
    sec = c.get("sector_code", "")
    pb = c.get("pb", 99.0)
    roe = c.get("roe", 0.0)
    roa = c.get("roa", 0.0)
    de = c.get("de_ratio", 99.0)
    cur_r = c.get("current_ratio", 1.5)
    quick_r = c.get("quick_ratio", cur_r * 0.75)
    icr = c.get("interest_coverage", 3.0)
    c_to_a = c.get("cash_to_assets", 9.0)
    r40 = c.get("rule_of_40", c.get("rev_1y_growth", 10.0) + c.get("net_margin", 10.0))
    s_roic = c.get("roic", roe * 0.8)
    gross_m = c.get("gross_margin", 20.0)
    op_m = c.get("op_margin", 10.0)
    rev_1y = c.get("rev_1y_growth", 0.0)
    pat_1y = c.get("pat_1y_growth", 0.0)
    peg = c.get("peg", 99.0)
    pe = c.get("pe", 99.0)

    if sec == "VNFIN":
        return 1.0 <= pb <= 1.8 and roe >= 18.0
    if not (roa >= 9.5 and cur_r >= 1.45 and (quick_r >= 0.95 or cur_r >= 1.5) and icr >= 2.4 and op_m > 0):
        return False
    if sec == "VNREAL":
        return de < 0.383 and pb <= 1.8
    if sec == "VNIT":
        return r40 >= 38.0 and peg <= 0.9 and roe >= 22.0 and de <= 0.35
    if sec in ["VNMAT", "VNIND", "VNENE", "VNUTI"]:
        return gross_m >= 14.5 and (s_roic >= 14.0 or roe >= 15.0) and de <= 0.70
    if sec in ["VNCOND", "VNCONS", "VNHEAL"]:
        return (c_to_a >= 7.5 or cur_r >= 1.5) and (pat_1y >= 18.0 or rev_1y >= 15.0) and ((8.0 <= pe <= 16.0) or peg <= 1.0)
    return roe >= 16.0 and de <= 0.8

_CLASSIC_STRATEGY_APPROVALS = {
    "deep_value_klarman": lambda c: 0 < c.get("pb", 99) < 1.0 and c.get("fcf_ttm", 0) > 0 and 0 <= c.get("de_ratio", 99) < 0.5,
    "ps_focus_fisher": lambda c: 0 < c.get("ps", 99) < 1.0 and c.get("rev_1y_growth", 0) > 5.0 and c.get("rev_3y_cagr", 0) > 25.0,
    "contrarian_dreman": lambda c: 0 < c.get("pe", 99) < 12.0 and c.get("dividend_yield", 0) > 3.0 and c.get("roe", 0) > 15.0,
    "growth_philip_fisher": lambda c: c.get("pat_1y_growth", 0) > 15.0 and c.get("rev_1y_growth", 0) > 10.0 and c.get("rev_3y_cagr", 0) > 40.0 and c.get("rev_5y_growth", 0) > 75.0 and c.get("roe", 0) > 20.0,
    "peter_lynch_garp": lambda c: 0 < c.get("peg", 99) < 1.0 and 10.0 < c.get("pe", 99) < 30.0 and c.get("pat_1y_growth", 0) > 10.0 and c.get("rev_3y_cagr", 0) > 20.0,
    "defensive_graham": lambda c: 0 < c.get("pe", 99) < 10.0 and 0 < c.get("pb", 99) < 1.0 and 0 <= c.get("de_ratio", 99) < 0.5 and c.get("dividend_yield", 0) > 2.0,
    "value_buffett": lambda c: c.get("roe", 0) > 20.0 and 0 <= c.get("de_ratio", 99) < 0.5 and c.get("fcf_ttm", 0) > 0 and 0 < c.get("pe", 99) < 25.0 and 0 < c.get("pb", 99) < 5.0 and c.get("rev_5y_growth", 0) > 20.0 and c.get("dividend_yield", 0) > 0,
    "buffetts_alpha": _buffett_alpha_passes,
    "novy_marx_quality_value": _novy_marx_passes,
    "gray_quantitative_value_qval": _qval_passes,
    "hello_lower_risk": lambda c: c.get("sector_code") not in HELLO_EXCLUDED_SECTORS_NM and 0 < c.get("peg", 99) < 1.0 and c.get("rev_5y_growth", 0) > 50.0 and c.get("rev_1y_growth", 0) > 5.0 and c.get("pat_1y_growth", 0) > 5.0 and c.get("roe", 0) > 15.0 and 0 <= c.get("de_ratio", 99) < 1.0 and c.get("fcf_ttm", 0) > 0,
    "hello_balanced_risk": lambda c: c.get("sector_code") not in HELLO_EXCLUDED_SECTORS_NM and 0 < c.get("peg", 99) < 2.0 and c.get("rev_5y_growth", 0) > 50.0 and c.get("rev_1y_growth", 0) > 5.0 and c.get("pat_5y_growth", 0) > 10.0 and c.get("roe", 0) > 15.0 and 0 <= c.get("de_ratio", 99) < 1.0 and c.get("fcf_ttm", 0) > 0,
    "hello_full_throttle": lambda c: c.get("sector_code") not in HELLO_EXCLUDED_SECTORS_NM and c.get("rev_5y_growth", 0) > 100.0 and c.get("rev_1y_growth", 0) > 20.0 and 0 < c.get("peg", 99) < 2.0 and 0 <= c.get("de_ratio", 99) < 5.0,
    "hello_lower_risk_mod": lambda c: (
        c.get("sector_code") != "VNFIN"
        and (c.get("cfo_to_pat", 1.0) or 1.0) >= 0.6
        and (c.get("gross_margin", 20.0) or 20.0) > 0
        and (c.get("op_margin", 10.0) or 10.0) > 0
        and (c.get("share_dilution_3y", 2.0) or 2.0) <= 7.0
        and (c.get("rev_5y_growth", 0) or 0) > 40.0
        and (c.get("net_de_ratio", c.get("de_ratio", 0.5)) or 0.5) <= 0.7
        and (c.get("peg_sales", c.get("peg", 1.5)) or 1.5) <= 2.0
        and (c.get("roe", 0) or 0) >= 14.0
    ),
    "hello_balanced_risk_mod": lambda c: (
        c.get("sector_code") != "VNFIN"
        and (c.get("cfo_to_pat", 1.0) or 1.0) >= 0.6
        and (c.get("gross_margin", 20.0) or 20.0) > 0
        and (c.get("op_margin", 10.0) or 10.0) > 0
        and (c.get("share_dilution_3y", 2.0) or 2.0) <= 7.0
        and (c.get("rev_5y_growth", 0) or 0) > 50.0
        and (c.get("rev_1y_growth", 0) or 0) > 8.0
        and (c.get("net_de_ratio", c.get("de_ratio", 0.8)) or 0.8) <= 0.9
        and (c.get("roe", 0) or 0) >= 15.0
        and (c.get("peg_sales", c.get("peg", 1.5)) or 1.5) <= 1.85
    ),
    "hello_full_throttle_mod": lambda c: (
        c.get("sector_code") != "VNFIN"
        and (c.get("cfo_to_pat", 1.0) or 1.0) >= 0.6
        and (c.get("gross_margin", 20.0) or 20.0) > 0
        and (c.get("op_margin", 10.0) or 10.0) > 0
        and (c.get("share_dilution_3y", 2.0) or 2.0) <= 7.0
        and ((c.get("rev_5y_growth", 0) or 0) > 80.0 or (c.get("rev_3y_cagr", 0) or 0) > 15.0)
        and (c.get("rev_1y_growth", 0) or 0) > 18.0
        and (c.get("de_ratio", 1.0) or 1.0) <= 2.0
        and (c.get("fcf_ttm", 1.0) or 1.0) > 0
        and (c.get("peg_sales", c.get("peg", 2.0)) or 2.0) <= 2.8
    ),
    "tsmom_moskowitz": lambda c: _t12m_momentum(_load_real_price_database(), c.get("symbol")) > 0
}

STRATEGY_VOTER_IDS = [
    "deep_value_klarman",
    "ps_focus_fisher",
    "contrarian_dreman",
    "growth_philip_fisher",
    "peter_lynch_garp",
    "defensive_graham",
    "value_buffett",
    "buffetts_alpha",
    "novy_marx_quality_value",
    "gray_quantitative_value_qval",
    "hello_lower_risk",
    "hello_balanced_risk",
    "hello_full_throttle",
    "hello_lower_risk_mod",
    "hello_balanced_risk_mod",
    "hello_full_throttle_mod",
    "universal_survival_sector_moat",
    "guru_magic_formula_greenblatt",
    "guru_piotroski_fscore",
    "guru_zweig_conservative_growth",
    "guru_cornerstone_growth_oshaughnessy",
    "guru_cornerstone_value_oshaughnessy",
    "guru_neff_total_return",
    "tsmom_moskowitz",
    "quant_q1",
    "quant_q2",
    "quant_q3",
    "quant_q4",
    "quant_q5"
]

def _strategy_approves_voter(strategy_id, c, ctx, price_db=None):
    if strategy_id == "universal_survival_sector_moat":
        return _moat_strategy_passes(c)
    if strategy_id in ("quant_q1", "quant_q2", "quant_q3", "quant_q4", "quant_q5"):
        return c.get("percentiles", {}).get("quintile") == strategy_id[-2:].upper()
    model_id = GURU_STRATEGY_TO_MODEL.get(strategy_id)
    if model_id:
        return evaluate_guru_model(model_id, c, ctx, price_db)
    fn = _CLASSIC_STRATEGY_APPROVALS.get(strategy_id)
    return bool(fn(c)) if fn else False

def count_multi_strategy_approvals(c, ctx, price_db=None):
    n = 0
    for sid in STRATEGY_VOTER_IDS:
        try:
            if _strategy_approves_voter(sid, c, ctx, price_db):
                n += 1
        except Exception:
            continue
    return n

def list_approving_strategies(c, ctx, price_db=None):
    approved = []
    for sid in STRATEGY_VOTER_IDS:
        try:
            if _strategy_approves_voter(sid, c, ctx, price_db):
                meta = STRATEGY_DEFINITIONS.get(sid, {})
                approved.append(meta.get("short_name", sid))
        except Exception:
            continue
    return approved

def _filter_stocks_for_strategy(
    strategy_id: str,
    quant_universe: List[Dict[str, Any]],
    top_k: int = 10,
    survival_filter: bool = False,
    fill_mode: str = "strict",
    tsmom_filter: bool = False,
    forensic_filter: bool = False
) -> List[Dict[str, Any]]:
    if not quant_universe:
        return []

    top_k = max(1, int(top_k))
    fill_mode = "fill" if str(fill_mode or "").strip().lower() in {"fill", "near_miss", "relaxed"} else "strict"
    price_db = _load_real_price_database()

    # 0. Universal Survival Firewall pre-filter (toggle)
    if survival_filter:
        from services.stock_service import passes_survival_firewall
        quant_universe = [s for s in quant_universe if passes_survival_firewall(s)]
        if not quant_universe:
            return []

    # 0.5. Forensic Accounting Firewall pre-filter (toggle: F-Score >= 7 & M-Score < -1.78)
    if forensic_filter:
        from services.stock_service import passes_forensic_filter
        quant_universe = [s for s in quant_universe if passes_forensic_filter(s)]
        if not quant_universe:
            return []

    # 1. Time Series Momentum (TSMOM) 12M Trend pre-filter (toggle)
    if tsmom_filter:
        from services.stock_service import passes_tsmom_filter
        quant_universe = [s for s in quant_universe if passes_tsmom_filter(s, price_db=price_db)]
        if not quant_universe:
            return []
    
    # 2. Extract and filter candidates with verified real price history.
    # Prefer the verified subset whenever it is non-empty so baskets never mix in
    # stocks without real quarterly prices (which would produce flat friction-only curves).
    if price_db and isinstance(price_db, dict):
        verified_universe = [
            s for s in quant_universe
            if isinstance(s, dict)
            and isinstance(price_db.get(s.get("symbol")), dict)
            and isinstance(price_db.get(s.get("symbol"), {}).get("quarters"), dict)
            and len(price_db.get(s.get("symbol"), {}).get("quarters", {})) >= 4
        ]
        candidates = verified_universe if verified_universe else quant_universe
    else:
        candidates = list(quant_universe)

    HELLO_EXCLUDED = {"VNFIN", "VNMAT", "VNENE", "VNUTI", "VNREAL"}

    if strategy_id == "deep_value_klarman":
        passing = [c for c in candidates if 0 < c.get("pb", 99) < 1.0 and c.get("fcf_ttm", 0) > 0 and 0 <= c.get("de_ratio", 99) < 0.5]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (x.get("pb", 99), -x.get("fcf_ttm", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("deep_value_klarman"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "ps_focus_fisher":
        passing = [c for c in candidates if 0 < c.get("ps", 99) < 1.0 and c.get("rev_1y_growth", 0) > 5.0 and c.get("rev_3y_cagr", 0) > 25.0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -x.get("rev_3y_cagr", 0) / max(0.1, x.get("ps", 1.0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("ps_focus_fisher"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "contrarian_dreman":
        passing = [c for c in candidates if 0 < c.get("pe", 99) < 12.0 and c.get("dividend_yield", 0) > 3.0 and c.get("roe", 0) > 15.0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -(x.get("dividend_yield", 0) * x.get("roe", 0)) / max(1.0, x.get("pe", 10.0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("contrarian_dreman"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "growth_philip_fisher":
        passing = [c for c in candidates if c.get("pat_1y_growth", 0) > 15.0 and c.get("rev_1y_growth", 0) > 10.0 and c.get("rev_3y_cagr", 0) > 40.0 and c.get("rev_5y_growth", 0) > 75.0 and c.get("roe", 0) > 20.0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -(x.get("rev_5y_growth", 0) + x.get("roe", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("growth_philip_fisher"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "peter_lynch_garp":
        passing = [c for c in candidates if 0 < c.get("peg", 99) < 1.0 and 10.0 < c.get("pe", 99) < 30.0 and c.get("pat_1y_growth", 0) > 10.0 and c.get("rev_3y_cagr", 0) > 20.0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (x.get("peg", 99), -x.get("roe", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("peter_lynch_garp"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "defensive_graham":
        passing = [c for c in candidates if 0 < c.get("pe", 99) < 10.0 and 0 < c.get("pb", 99) < 1.0 and 0 <= c.get("de_ratio", 99) < 0.5 and c.get("dividend_yield", 0) > 2.0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (x.get("pe", 99), -x.get("dividend_yield", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("defensive_graham"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "value_buffett":
        passing = [c for c in candidates if c.get("roe", 0) > 20.0 and 0 <= c.get("de_ratio", 99) < 0.5 and c.get("fcf_ttm", 0) > 0 and 0 < c.get("pe", 99) < 25.0 and 0 < c.get("pb", 99) < 5.0 and c.get("rev_5y_growth", 0) > 20.0 and c.get("dividend_yield", 0) > 0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (-x.get("roe", 0), -x.get("fcf_ttm", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("value_buffett"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "buffetts_alpha":
        passing = [c for c in candidates if _buffett_alpha_passes(c)]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (
                -(x.get("dividend_yield", 0.0) or 0.0) * max(x.get("roic", 0.0) or 0.0, x.get("roe", 0.0) or 0.0) / max(1.0, x.get("pe", 10.0) or 10.0)
            ),
            STRATEGY_NEAR_MISS_CRITERIA.get("buffetts_alpha"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "novy_marx_quality_value":
        passing = [c for c in candidates if _novy_marx_passes(c)]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (
                -(x.get("gross_margin", 0.0) or 0.0) * max(x.get("roic", 0.0) or 0.0, x.get("roe", 0.0) or 0.0) / max(1.0, x.get("pe", 10.0) or 10.0),
                -(x.get("dividend_yield", 0.0) or 0.0)
            ),
            STRATEGY_NEAR_MISS_CRITERIA.get("novy_marx_quality_value"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "gray_quantitative_value_qval":
        passing = [c for c in candidates if _qval_passes(c)]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (
                (x.get("pe", 99.0) or 99.0),
                -(x.get("dividend_yield", 0.0) or 0.0),
                -(x.get("fcf_ttm", 0.0) or 0.0)
            ),
            STRATEGY_NEAR_MISS_CRITERIA.get("gray_quantitative_value_qval"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "hello_lower_risk":
        passing = [c for c in candidates if c.get("sector_code") not in HELLO_EXCLUDED and 0 < c.get("peg", 99) < 1.0 and c.get("rev_5y_growth", 0) > 50.0 and c.get("rev_1y_growth", 0) > 5.0 and c.get("pat_1y_growth", 0) > 5.0 and c.get("roe", 0) > 15.0 and 0 <= c.get("de_ratio", 99) < 1.0 and c.get("fcf_ttm", 0) > 0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (x.get("peg", 99), -x.get("rev_5y_growth", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("hello_lower_risk"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "hello_balanced_risk":
        passing = [c for c in candidates if c.get("sector_code") not in HELLO_EXCLUDED and 0 < c.get("peg", 99) < 2.0 and c.get("rev_5y_growth", 0) > 50.0 and c.get("rev_1y_growth", 0) > 5.0 and c.get("pat_5y_growth", 0) > 10.0 and c.get("roe", 0) > 15.0 and 0 <= c.get("de_ratio", 99) < 1.0 and c.get("fcf_ttm", 0) > 0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (-x.get("roe", 0), x.get("peg", 99)),
            STRATEGY_NEAR_MISS_CRITERIA.get("hello_balanced_risk"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "hello_full_throttle":
        passing = [c for c in candidates if c.get("sector_code") not in HELLO_EXCLUDED and c.get("rev_5y_growth", 0) > 100.0 and c.get("rev_1y_growth", 0) > 20.0 and 0 < c.get("peg", 99) < 2.0 and 0 <= c.get("de_ratio", 99) < 5.0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -(x.get("rev_5y_growth", 0) + x.get("rev_1y_growth", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("hello_full_throttle"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    # =========================================================================
    # HELLO STOCKS MODIFIED (TWO-TIER HYBRID MODEL: HARD GATES + PERCENTILES)
    # =========================================================================
    elif strategy_id == "hello_lower_risk_mod":
        # Tier 1 (Hard Gates) + Tier 2 (Quality Compounders)
        t1_candidates = [
            c for c in candidates 
            if c.get("sector_code") != "VNFIN"
            and c.get("cfo_to_pat", 1.0) >= 0.6
            and c.get("gross_margin", 20.0) > 0
            and c.get("op_margin", 10.0) > 0
            and c.get("share_dilution_3y", 2.0) <= 7.0
        ]
        passing = [
            c for c in t1_candidates
            if c.get("rev_5y_growth", 0) > 40.0
            and c.get("net_de_ratio", c.get("de_ratio", 0.5)) <= 0.5
            and c.get("peg_sales", c.get("peg", 1.0)) <= 1.35
            and c.get("roe", 0) >= 16.0
        ]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (x.get("peg_sales", x.get("peg", 1.0)), -x.get("roe", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("hello_lower_risk_mod"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "hello_balanced_risk_mod":
        # Tier 1 (Hard Gates) + Tier 2 (GARP & Margin Expansion)
        t1_candidates = [
            c for c in candidates 
            if c.get("sector_code") != "VNFIN"
            and c.get("cfo_to_pat", 1.0) >= 0.6
            and c.get("gross_margin", 20.0) > 0
            and c.get("op_margin", 10.0) > 0
            and c.get("share_dilution_3y", 2.0) <= 7.0
        ]
        passing = [
            c for c in t1_candidates
            if c.get("rev_5y_growth", 0) > 50.0
            and c.get("rev_1y_growth", 0) > 8.0
            and c.get("net_de_ratio", c.get("de_ratio", 0.8)) <= 0.9
            and c.get("roe", 0) >= 15.0
            and c.get("peg_sales", c.get("peg", 1.5)) <= 1.85
        ]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (-x.get("roe", 0), x.get("peg_sales", x.get("peg", 1.5))),
            STRATEGY_NEAR_MISS_CRITERIA.get("hello_balanced_risk_mod"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "hello_full_throttle_mod":
        # Tier 1 (Hard Gates) + Tier 2 (Operating Leverage & Hyper-Growth)
        t1_candidates = [
            c for c in candidates 
            if c.get("sector_code") != "VNFIN"
            and c.get("cfo_to_pat", 1.0) >= 0.6
            and c.get("gross_margin", 20.0) > 0
            and c.get("op_margin", 10.0) > 0
            and c.get("share_dilution_3y", 2.0) <= 7.0
        ]
        passing = [
            c for c in t1_candidates
            if (c.get("rev_5y_growth", 0) > 80.0 or c.get("rev_3y_cagr", 0) > 15.0)
            and c.get("rev_1y_growth", 0) > 18.0
            and c.get("de_ratio", 1.0) <= 2.0
            and c.get("fcf_ttm", 1.0) > 0
            and c.get("peg_sales", c.get("peg", 2.0)) <= 2.8
        ]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -(x.get("rev_5y_growth", 0) + x.get("rev_1y_growth", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("hello_full_throttle_mod"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    # =========================================================================
    # UNIVERSAL SURVIVAL & SECTOR MOAT (MÔ HÌNH 3 TẦNG: SINH TỒN & CON HÀO NGÀNH)
    # =========================================================================
    elif strategy_id == "universal_survival_sector_moat":
        valid_candidates = []
        for c in candidates:
            sec = c.get("sector_code", "")
            pb = c.get("pb", 99.0)
            roe = c.get("roe", 0.0)
            roa = c.get("roa", 0.0)
            de = c.get("de_ratio", 99.0)
            cur_r = c.get("current_ratio", 1.5)
            quick_r = c.get("quick_ratio", cur_r * 0.75)
            icr = c.get("interest_coverage", 3.0)
            c_to_a = c.get("cash_to_assets", 9.0)
            r40 = c.get("rule_of_40", c.get("rev_1y_growth", 10.0) + c.get("net_margin", 10.0))
            s_roic = c.get("roic", roe * 0.8)
            gross_m = c.get("gross_margin", 20.0)
            op_m = c.get("op_margin", 10.0)
            rev_1y = c.get("rev_1y_growth", 0.0)
            pat_1y = c.get("pat_1y_growth", 0.0)
            peg = c.get("peg", 99.0)
            pe = c.get("pe", 99.0)

            if sec == "VNFIN":
                if 1.0 <= pb <= 1.8 and roe >= 18.0:
                    valid_candidates.append(c)
            else:
                # Universal Non-Financial Firewall:
                # 1. ROA >= 9.5%
                # 2. Solvency: Current Ratio >= 1.45, Quick Ratio >= 0.95, ICR >= 2.4
                # 3. Quality: op_margin > 0
                if roa >= 9.5 and cur_r >= 1.45 and (quick_r >= 0.95 or cur_r >= 1.5) and icr >= 2.4 and op_m > 0:
                    if sec == "VNREAL" and de < 0.383 and pb <= 1.8:
                        valid_candidates.append(c)
                    elif sec == "VNIT" and r40 >= 38.0 and peg <= 0.9 and roe >= 22.0 and de <= 0.35:
                        valid_candidates.append(c)
                    elif sec in ["VNMAT", "VNIND", "VNENE", "VNUTI"] and gross_m >= 14.5 and (s_roic >= 14.0 or roe >= 15.0) and de <= 0.70:
                        valid_candidates.append(c)
                    elif sec in ["VNCOND", "VNCONS", "VNHEAL"] and (c_to_a >= 7.5 or cur_r >= 1.5) and (pat_1y >= 18.0 or rev_1y >= 15.0) and ((8.0 <= pe <= 16.0) or peg <= 1.0):
                        valid_candidates.append(c)
                    elif roe >= 16.0 and de <= 0.8:
                        valid_candidates.append(c)

        filtered = _resolve_basket(
            valid_candidates, candidates,
            lambda x: (-x.get("percentiles", {}).get("composite", 50), -x.get("roa", 0)),
            STRATEGY_NEAR_MISS_CRITERIA.get("universal_survival_sector_moat"),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "quant_q1":
        passing = [c for c in candidates if c.get("percentiles", {}).get("quintile") == "Q1"]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -x.get("percentiles", {}).get("composite", 50.0),
            STRATEGY_NEAR_MISS_CRITERIA.get("quant_q1"),
                        top_k, fill_mode, tiebreak_seed=strategy_id,
            fill_signature=_quintile_fill_signature("Q1")
        )

    elif strategy_id == "quant_q2":
        passing = [c for c in candidates if c.get("percentiles", {}).get("quintile") == "Q2"]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -x.get("percentiles", {}).get("composite", 50.0),
            STRATEGY_NEAR_MISS_CRITERIA.get("quant_q2"),
                        top_k, fill_mode, tiebreak_seed=strategy_id,
            fill_signature=_quintile_fill_signature("Q2")
        )

    elif strategy_id == "quant_q3":
        passing = [c for c in candidates if c.get("percentiles", {}).get("quintile") == "Q3"]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -x.get("percentiles", {}).get("composite", 50.0),
            STRATEGY_NEAR_MISS_CRITERIA.get("quant_q3"),
                        top_k, fill_mode, tiebreak_seed=strategy_id,
            fill_signature=_quintile_fill_signature("Q3")
        )

    elif strategy_id == "quant_q4":
        passing = [c for c in candidates if c.get("percentiles", {}).get("quintile") == "Q4"]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: x.get("percentiles", {}).get("composite", 50.0),
            STRATEGY_NEAR_MISS_CRITERIA.get("quant_q4"),
                        top_k, fill_mode, tiebreak_seed=strategy_id,
            fill_signature=_quintile_fill_signature("Q4")
        )

    elif strategy_id == "quant_q5":
        passing = [c for c in candidates if c.get("percentiles", {}).get("quintile") == "Q5"]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: x.get("percentiles", {}).get("composite", 999.0),
            STRATEGY_NEAR_MISS_CRITERIA.get("quant_q5"),
                        top_k, fill_mode, tiebreak_seed=strategy_id,
            fill_signature=_quintile_fill_signature("Q5")
        )

    elif strategy_id == "guru_magic_formula_greenblatt":
        ctx = _guru_market_context(candidates)
        pool = [c for c in candidates if evaluate_guru_model("greenblatt_magic_formula", c, ctx)]

        def _mf_roc_key(x):
            return -(x.get("roic") or 0.0)

        def _mf_ey_key(x):
            pe_v = x.get("pe")
            return -(100.0 / pe_v) if (isinstance(pe_v, (int, float)) and pe_v > 0) else 9e9

        combined_rank = {}
        for i, s in enumerate(sorted(pool, key=_mf_roc_key)):
            combined_rank[id(s)] = i + 1
        for i, s in enumerate(sorted(pool, key=_mf_ey_key)):
            combined_rank[id(s)] += i + 1

        crit_list = [
            lambda c: 3.0 if c.get("sector_code") in GURU_EXCLUDED_SECTORS_GREENBLATT else 0.0,
            lambda c: _v_below(c.get("market_cap") if isinstance(c.get("market_cap"), (int, float)) and c.get("market_cap", 0) > 0 else 0.0, ctx["cap_median"]),
            lambda c: _v_above(c.get("roic") if isinstance(c.get("roic"), (int, float)) else None, ctx["roic_median_eligible"]),
            lambda c: _v_above(100.0 / c.get("pe"), ctx["ey_median_eligible"]) if (isinstance(c.get("pe"), (int, float)) and c.get("pe", 0) > 0) else 10.0,
        ]
        filtered = _resolve_basket(
            pool, candidates,
            lambda x: (combined_rank.get(id(x), 10 ** 9), -(x.get("roic") or 0.0)),
            crit_list, top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "guru_piotroski_fscore":
        ctx = _guru_market_context(candidates)
        cohort = [c for c in candidates if isinstance(c.get("pb"), (int, float)) and 0 < c.get("pb", 0) <= ctx["pb_q20"]]
        fscore_map = {id(c): _piotroski_fscore(c) for c in candidates}
        pool = [c for c in cohort if fscore_map[id(c)] >= 7]
        crit_list = [
            lambda c: _v_below(c.get("pb") if isinstance(c.get("pb"), (int, float)) and c.get("pb", 0) > 0 else 9e9, ctx["pb_q20"]),
            lambda c: 0.0 if (c.get("roa", 0.0) or 0.0) > 0 else 1.0,
            lambda c: 0.0 if (c.get("cfo_to_pat", 1.0) or 1.0) >= 0.6 else 1.0,
            lambda c: 0.0 if (c.get("pat_1y_growth", 0) or 0) > 0 else 1.0,
            lambda c: 0.0 if (c.get("cfo_to_pat", 1.0) or 1.0) >= 1.0 else 1.0,
            lambda c: 0.0 if (c.get("de_ratio", 99) or 99) < 1.0 else 1.0,
            lambda c: 0.0 if (c.get("current_ratio", 1.5) or 1.5) >= 1.5 else 1.0,
            lambda c: 0.0 if (c.get("share_dilution_3y", 2.0) or 2.0) <= 2.0 else 1.0,
            lambda c: 0.0 if (c.get("gross_margin", 20.0) or 20.0) >= 20.0 else 1.0,
            lambda c: 0.0 if (c.get("rev_1y_growth", 0) or 0) > 0 else 1.0,
        ]
        filtered = _resolve_basket(
            pool, cohort,
            lambda x: (-fscore_map.get(id(x), 0), x.get("pb", 99)),
            crit_list, top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "guru_zweig_conservative_growth":
        ctx = _guru_market_context(candidates)
        pool = [c for c in candidates if evaluate_guru_model("zweig_conservative_growth", c, ctx)]
        sec_de_med = ctx["sector_de_median"]
        crit_list = [
            lambda c: 0.0 if (c.get("pat_1y_growth", 0) or 0) > 0 else 1.0,
            lambda c: 0.0 if (c.get("pat_1y_growth", 0) or 0) > (c.get("eps_3y_cagr", 0) or 0) else 1.0,
            lambda c: _v_above(c.get("eps_3y_cagr", 0), 15.0),
            lambda c: 0.0 if (c.get("pat_5y_growth", 0) or 0) > 0 else 1.0,
            lambda c: 0.0 if (c.get("rev_5y_growth", 0) or 0) > 0 else 1.0,
            lambda c: 0.0 if (c.get("rev_1y_growth", 0) or 0) > 0 else 1.0,
            lambda c: _v_below(c.get("pe", 9e9) if isinstance(c.get("pe"), (int, float)) and c.get("pe", 0) > 0 else 9e9, 40.0),
            lambda c: _v_above(c.get("pe") if isinstance(c.get("pe"), (int, float)) and c.get("pe", 0) > 0 else None, 5.0),
            lambda c: _v_below(c.get("de_ratio", 9e9) if isinstance(c.get("de_ratio"), (int, float)) else 9e9, sec_de_med.get(c.get("sector_code", ""), 1.0)),
        ]
        filtered = _resolve_basket(
            pool, candidates,
            lambda x: (-x.get("pat_1y_growth", 0), x.get("peg", 99)),
            crit_list, top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "guru_cornerstone_growth_oshaughnessy":
        ctx = _guru_market_context(candidates)
        pool = [c for c in candidates if evaluate_guru_model("osh_cornerstone_growth", c, ctx)]
        crit_list = [
            lambda c: _v_below(c.get("market_cap") if isinstance(c.get("market_cap"), (int, float)) and c.get("market_cap", 0) > 0 else 0.0, ctx["cap_median"]),
            lambda c: _v_positive(c.get("ps", 99)),
            lambda c: _v_below(c.get("ps", 99), 1.5),
            lambda c: 0.0 if (c.get("pat_1y_growth", 0) or 0) > 0 else 1.0,
            lambda c: 0.0 if (c.get("pat_3y_cagr", 0) or 0) > 0 else 1.0,
            lambda c: 0.0 if (c.get("pat_5y_growth", 0) or 0) > 0 else 1.0,
        ]
        filtered = _resolve_basket(
            pool, candidates,
            lambda x: (-_t12m_momentum(price_db, x.get("symbol")), x.get("ps", 99)),
            crit_list, top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "guru_cornerstone_value_oshaughnessy":
        ctx = _guru_market_context(candidates)
        pool = [c for c in candidates if evaluate_guru_model("osh_cornerstone_value", c, ctx)]
        crit_list = [
            lambda c: _v_below(c.get("market_cap") if isinstance(c.get("market_cap"), (int, float)) and c.get("market_cap", 0) > 0 else 0.0, ctx["cap_mean"]),
            lambda c: _v_above(c.get("cfo_to_pat", 1.0), 1.0),
            lambda c: _v_above(c.get("dividend_yield") if isinstance(c.get("dividend_yield"), (int, float)) else None, ctx["dividend_median_positive"]),
        ]
        filtered = _resolve_basket(
            pool, candidates,
            lambda x: -x.get("dividend_yield", 0),
            crit_list, top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "guru_neff_total_return":
        ctx = _guru_market_context(candidates)

        def _neff_ratio(c):
            pe_v = c.get("pe")
            if not (isinstance(pe_v, (int, float)) and pe_v > 0):
                return -999.0
            return ((c.get("eps_3y_cagr", 0) or 0) + (c.get("dividend_yield", 0) or 0)) / pe_v

        pool = [c for c in candidates if evaluate_guru_model("neff_total_return", c, ctx)]
        crit_list = [
            lambda c: _v_above(_neff_ratio(c), 1.0),
            lambda c: max(_v_above(c.get("pe") if isinstance(c.get("pe"), (int, float)) and c.get("pe", 0) > 0 else None, 0.4 * ctx["pe_median"]),
                          _v_below(c.get("pe") if isinstance(c.get("pe"), (int, float)) and c.get("pe", 0) > 0 else 9e9, 0.7 * ctx["pe_median"])),
            lambda c: max(_v_above(c.get("eps_3y_cagr", 0), 7.0), _v_below(c.get("eps_3y_cagr", 0), 20.0)),
            lambda c: _v_above(c.get("rev_3y_cagr", 0), 7.0),
            lambda c: _v_above(c.get("cfo_to_pat", 1.0), 1.0),
        ]
        filtered = _resolve_basket(
            pool, candidates,
            lambda x: -_neff_ratio(x),
            crit_list, top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id == "guru_consensus_multi_model":
        vote_map = {}
        for voter_id in STRATEGY_VOTER_IDS:
            try:
                voter_basket = _filter_stocks_for_strategy(
                    strategy_id=voter_id,
                    quant_universe=quant_universe,
                    top_k=top_k,
                    survival_filter=survival_filter,
                    fill_mode=fill_mode
                )
            except Exception:
                continue
            voter_short = STRATEGY_DEFINITIONS.get(voter_id, {}).get("short_name", voter_id)
            for s in voter_basket:
                sym = s.get("symbol")
                if not sym:
                    continue
                entry = vote_map.setdefault(sym, {"count": 0, "by": []})
                entry["count"] += 1
                entry["by"].append(voter_short)

        def _consensus_rank_key(x):
            comp = x.get("percentiles", {}).get("composite", 50.0)
            return (-vote_map.get(x.get("symbol"), {}).get("count", 0), -comp)

        ranked = sorted(candidates, key=_consensus_rank_key)[:top_k]
        filtered = []
        for s in ranked:
            row = dict(s)
            info = vote_map.get(s.get("symbol"), {})
            row["meets_criteria"] = True
            row["approval_count"] = info.get("count", 0)
            row["approved_by"] = info.get("by", [])
            filtered.append(row)

    elif strategy_id == "tsmom_moskowitz":
        # Time Series Momentum (Moskowitz, Ooi & Pedersen 2012 - JFE)
        # 1. Long-only filter: Trailing 12-month return > 0
        # 2. Ranking: Volatility-scaled momentum R_12M / Vol (Risk Parity Ranking)
        def _tsmom_score(c):
            sym = c.get("symbol", "")
            mom = _t12m_momentum(price_db, sym)
            info = (price_db or {}).get(sym) if isinstance(price_db, dict) else None
            quarters = info.get("quarters") if isinstance(info, dict) else {}
            codes = sorted(quarters.keys())[-4:] if isinstance(quarters, dict) else []
            if len(codes) >= 4:
                try:
                    rets = [float(quarters[k].get("return_pct", 0.0)) for k in codes]
                    std = float(np.std(rets, ddof=1)) if len(rets) > 1 else None
                except Exception:
                    std = None
            else:
                std = None
            # Volatility-adjusted momentum needs a measured volatility. It used
            # to divide by max(1.0, std) and substitute 10.0 when unmeasurable,
            # so a symbol with no return history was ranked on an invented
            # denominator. Without one, rank on raw momentum alone.
            vol_adj = mom / std if (std is not None and std >= 0.01) else mom
            return (mom, vol_adj)

        passing = [c for c in candidates if _t12m_momentum(price_db, c.get("symbol")) > 0]
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: (-_tsmom_score(x)[1], -_tsmom_score(x)[0]),
            STRATEGY_NEAR_MISS_CRITERIA.get("tsmom_moskowitz", []),
            top_k, fill_mode, tiebreak_seed=strategy_id
        )

    elif strategy_id in ("custom", "all", "ALL", "screener_custom"):
        # Custom universe filter: rank candidates by composite score or near-miss criteria
        passing = candidates
        filtered = _resolve_basket(
            passing, candidates,
            lambda x: -float(x.get("percentiles", {}).get("composite", 50.0)),
            [], top_k, fill_mode, tiebreak_seed="custom"
        )

    else:
        raise ValueError(f"Unknown backtest strategy_id: '{strategy_id}'")

    return filtered

def simulate_strategy_quarter(
    strategy_id: str,
    stocks: List[Dict[str, Any]],
    q_info: Dict[str, Any],
    vni_return: float,
    is_rebalance: bool = True
) -> Dict[str, Any]:
    quarter_code = q_info.get("code", "2026-Q1")
    holdings_detail = []
    total_q_return = 0.0

    fee_rate = 0.0015
    tax_rate = 0.0010
    n_stocks = len(stocks) if stocks else 1
    weight = round(100.0 / n_stocks, 1)

    price_db = _load_real_price_database()

    for s in (stocks or []):
        sym = s.get("symbol", "XYZ")
        p_comp = s.get("percentiles", {}).get("composite", 50.0)

        # Check real historical price from TradingView database
        stock_real_history = price_db.get(sym) if isinstance(price_db, dict) else None
        quarters_map = stock_real_history.get("quarters") if isinstance(stock_real_history, dict) else {}
        if not isinstance(quarters_map, dict):
            quarters_map = {}
        q_real_data = quarters_map.get(quarter_code) if isinstance(quarters_map, dict) else None

        if q_real_data:
            start_price = float(q_real_data.get("start_price", 0.0))
            close_price = float(q_real_data.get("close_price", 0.0))
            raw_return = float(q_real_data.get("return_pct", 0.0))
            # Sanity check: valid positive prices and positive baseline
            if start_price > 0 and close_price > 0:
                gross_return = raw_return
                is_real = True
            else:
                gross_return = 0.0
                is_real = False
        else:
            # Stock was unlisted or had no trading in this specific historical quarter
            gross_return = 0.0
            start_price = float(s.get("price", 0.0))
            close_price = start_price
            is_real = False

        friction = round((fee_rate * 2 + tax_rate) * 100, 2) if is_rebalance else 0.0
        net_return = round(gross_return - friction, 2)

        holdings_detail.append({
            "symbol": sym,
            "name": s.get("name", f"Công ty {sym}"),
            "sector": s.get("sector_name", "Công nghiệp"),
            "weight_pct": weight,
            "composite_score": round(p_comp, 1),
            "rev_5y_growth": s.get("rev_5y_growth", 0),
            "roe": s.get("roe", 0),
            "pe": s.get("pe", 0),
            "start_price": start_price,
            "close_price": close_price,
            "is_real_price": is_real,
            "gross_return_pct": gross_return,
            "net_return_pct": net_return,
            "meets_criteria": s.get("meets_criteria", True),
            "near_miss_score": s.get("near_miss_score"),
            "approval_count": s.get("approval_count"),
            "approved_by": s.get("approved_by")
        })

    valid_real_holdings = [h for h in holdings_detail if h.get("is_real_price")]
    if valid_real_holdings:
        total_q_return = round(float(np.mean([h["net_return_pct"] for h in valid_real_holdings])), 2)
    elif holdings_detail:
        total_q_return = round(float(np.mean([h["net_return_pct"] for h in holdings_detail])), 2)
    else:
        total_q_return = 0.0

    return {
        "quarter": quarter_code,
        "quarter_return_pct": total_q_return,
        "vni_return_pct": vni_return,
        "alpha_pct": round(total_q_return - vni_return, 2),
        "holdings": holdings_detail
    }

PIT_POOL_MULTIPLIER = 3

def _pit_trailing_momentum(price_db, symbol, asof_quarter):
    """Trailing 4-quarter price return using ONLY quarter rows strictly prior to
    `asof_quarter` (< asof_quarter, so the target quarter itself is NEVER leaked).
    Returns None when fewer than 4 quarters of history exist prior to that date,
    guaranteeing no look-ahead bias and requiring verified track record."""
    info = (price_db or {}).get(symbol) if isinstance(price_db, dict) else None
    if not isinstance(info, dict):
        return None
    quarters = info.get("quarters")
    if not isinstance(quarters, dict) or not quarters:
        return None
    codes = sorted(c for c in quarters.keys() if str(c) < str(asof_quarter))[-4:]
    if len(codes) < 4:
        return None
    try:
        return round(sum(float(quarters[c].get("return_pct", 0.0)) for c in codes), 2)
    except Exception:
        return None

def point_in_time_rank(universe, asof_quarter, price_db=None):
    """Anti-look-ahead re-ranking of a candidate universe as of `asof_quarter`.

    The screener snapshot passed into the backtest is computed from TODAY's
    fundamentals, so strategy criteria remain snapshot-based; what this function
    fixes is the RANKING/selection inside each rebalance quarter: candidates are
    ordered by trailing 4-quarter momentum computed exclusively from historical
    price quarters available at that point in time, so baskets genuinely rotate
    across the replay window instead of being an identical today-picked list.

    Deterministic: ties are broken by the same crc32 jitter scheme used by
    _resolve_basket (_deterministic_hash), seeded per (quarter, symbol).

    NOTE: full point-in-time FUNDAMENTAL ranking (revenue/earnings growth as
    reported at each past quarter) requires a historical fundamentals store,
    which does not exist in the current DB; QoQ fundamental growth cannot be
    reconstructed and is intentionally not faked here.
    """
    db = price_db if price_db is not None else _load_real_price_database()
    scored = []
    for s in universe:
        mom = _pit_trailing_momentum(db, s.get("symbol"), asof_quarter)
        row = dict(s)
        row["_pit_momentum_4q"] = mom
        row["_pit_jitter"] = _deterministic_hash(f"pit|{asof_quarter}|{s.get('symbol', '')}")
        scored.append(row)

    def _pit_key(r):
        mom = r["_pit_momentum_4q"]
        mom_val = float(mom) if isinstance(mom, (int, float)) else -9999.0
        # Missing history sinks to the bottom deterministically via jitter.
        return (-mom_val, r["_pit_jitter"])

    return sorted(scored, key=_pit_key)

def run_screener_backtest(
    strategy_id: str = "quant_q1",
    time_horizon_years: int = 5,
    rebalance_cadence: str = "quarterly",
    top_k: int = 10,
    initial_capital: float = 100_000_000.0,
    exchange: str = "ALL",
    min_growth_pct: float = 0.0,
    survival_filter: bool = False,
    fill_mode: str = "strict",
    quant_universe: Optional[List[Dict[str, Any]]] = None,
    tsmom_filter: bool = False,
    forensic_filter: bool = False
) -> Dict[str, Any]:
    strat_meta = STRATEGY_DEFINITIONS.get(strategy_id, STRATEGY_DEFINITIONS["quant_q1"])
    initial_capital = max(1_000_000.0, float(initial_capital))
    top_k = max(1, int(top_k))

    if time_horizon_years == 1:
        selected_quarters = QUARTERS_TIMELINE[-4:]
    elif time_horizon_years == 2:
        selected_quarters = QUARTERS_TIMELINE[-8:]
    elif time_horizon_years == 3:
        selected_quarters = QUARTERS_TIMELINE[-12:]
    elif time_horizon_years == 5:
        selected_quarters = QUARTERS_TIMELINE[-21:]
    elif time_horizon_years == 10:
        selected_quarters = QUARTERS_TIMELINE[-41:]
    else:
        selected_quarters = QUARTERS_TIMELINE[:]

    if quant_universe is None:
        screener_data = get_quant_screener(sector="ALL", quintile="ALL", exchange=exchange, min_growth_pct=min_growth_pct, limit=500)
        all_universe = screener_data.get("results", [])
    else:
        all_universe = list(quant_universe)

    # Deterministic row ordering: independent of snapshot dict insertion order so
    # tie-breaks at the top-500 cutoff can never shift results between runs.
    all_universe = sorted(all_universe, key=lambda s: str(s.get("symbol", "")))

    price_db = _load_real_price_database()
    if price_db and isinstance(price_db, dict):
        verified_stocks = [
            s for s in all_universe
            if isinstance(s, dict)
            and isinstance(price_db.get(s.get("symbol")), dict)
            and isinstance(price_db.get(s.get("symbol"), {}).get("quarters"), dict)
            and len(price_db.get(s.get("symbol"), {}).get("quarters", {})) >= 4
        ]
        universe = verified_stocks if verified_stocks else all_universe
    else:
        universe = list(all_universe)

    # Universal Survival Firewall filter
    if survival_filter:
        from services.stock_service import passes_survival_firewall
        universe = [s for s in universe if passes_survival_firewall(s)]
        if not universe:
            universe = all_universe[:top_k]

    # Forensic Accounting Firewall filter (F-Score >= 7 & M-Score < -1.78)
    if forensic_filter:
        from services.stock_service import passes_forensic_filter
        universe = [s for s in universe if passes_forensic_filter(s)]
        if not universe:
            universe = all_universe[:top_k]

    # Time Series Momentum (TSMOM) 12M Trend Filter
    if tsmom_filter:
        from services.stock_service import passes_tsmom_filter
        universe = [s for s in universe if passes_tsmom_filter(s, price_db=price_db)]
        if not universe:
            universe = all_universe[:top_k]

    # Survivorship-bias mitigation: today's screener universe only contains
    # symbols that still exist TODAY, so historical replays silently drop every
    # delisted name. Where the price DB still carries quarters for a symbol that
    # reaches back to the replay window start, synthesize a minimal candidate
    # row (strategy .get() defaults make it screen-neutral) so it is eligible
    # for selection during the replay.
    # NOTE: this is only a partial fix - full survivorship-free backtesting
    # requires a dedicated delistings table (delist dates + final liquidation
    # prices); symbols purged entirely from the price DB remain unrecoverable.
    if price_db and isinstance(price_db, dict) and selected_quarters:
        window_start_code = selected_quarters[0]["code"]
        known_symbols = {s.get("symbol") for s in universe if isinstance(s, dict)}
        revived = []
        for sym, info in sorted(price_db.items()):
            if not isinstance(info, dict):
                continue
            if sym in known_symbols:
                continue
            earliest = str(info.get("earliest_quarter", "") or "")
            if earliest and earliest <= window_start_code:
                revived.append({
                    "symbol": sym,
                    "name": f"{sym} (hồi phục từ DB giá)",
                    "exchange": info.get("exchange", ""),
                    "percentiles": {"composite": 50.0, "quintile": "Q3"}
                })
        if revived:
            universe = universe + revived

    current_nav = initial_capital
    peak_nav = initial_capital
    max_drawdown_pct = 0.0

    nav_curve = []
    annual_returns = {}
    quarterly_history = []
    win_quarters = 0

    vni_nav = initial_capital
    vni_curve = []

    nav_curve.append({
        "date": selected_quarters[0]["date"],
        "quarter": "Start",
        "nav": initial_capital,
        "return_pct": 0.0,
        "drawdown_pct": 0.0
    })
    vni_curve.append({
        "date": selected_quarters[0]["date"],
        "quarter": "Start",
        "nav": initial_capital,
        "return_pct": 0.0
    })

    current_holdings_stocks = []

    for idx, q_info in enumerate(selected_quarters):
        q_code = q_info["code"]
        yr = q_info["year"]
        vni_q_ret = q_info["vni_return_pct"]

        should_rebalance = True
        if rebalance_cadence == "semi_annual" and (q_info["quarter"] in [2, 4]):
            should_rebalance = False
        elif rebalance_cadence == "annual" and q_info["quarter"] != 1:
            should_rebalance = False

        if strategy_id != "vnindex" and (should_rebalance or not current_holdings_stocks):
            # Anti-look-ahead: re-rank the universe with ONLY data available as
            # of this quarter, request a wider candidate pool from the strategy
            # filter, then keep the top_k best point-in-time ranked names. This
            # makes each rebalance a genuine re-selection instead of replaying
            # one today-picked basket across all history.
            pit_universe = point_in_time_rank(universe, q_code, price_db)

            # If tsmom_filter is enabled, strictly restrict candidate universe to assets with positive point-in-time 4-quarter return
            if tsmom_filter:
                pit_universe = [
                    s for s in pit_universe
                    if (_pit_trailing_momentum(price_db, s.get("symbol"), q_code) or -999.0) > 0
                ]

            pool_size = max(top_k, min(len(pit_universe), top_k * PIT_POOL_MULTIPLIER)) if pit_universe else top_k
            candidate_pool = _filter_stocks_for_strategy(
                strategy_id=strategy_id,
                quant_universe=pit_universe,
                top_k=pool_size,
                survival_filter=survival_filter,
                fill_mode=fill_mode,
                tsmom_filter=tsmom_filter
            )
            # The filter returns its pool in today-snapshot rank order; re-sort
            # it point-in-time so trimming reflects only as-of-quarter info.
            candidate_pool = point_in_time_rank(candidate_pool, q_code, price_db)
            # Rows carry _pit_* fields from point_in_time_rank; strip them so
            # downstream payloads stay identical in shape to previous versions.
            current_holdings_stocks = [
                {k: v for k, v in s.items() if not str(k).startswith("_pit_")}
                for s in candidate_pool[:top_k]
            ]

        if strategy_id == "vnindex":
            strat_q_ret = vni_q_ret
            q_res = {
                "quarter": q_code,
                "quarter_return_pct": strat_q_ret,
                "vni_return_pct": vni_q_ret,
                "alpha_pct": 0.0,
                "holdings": [{"symbol": "VNINDEX", "name": "Chỉ Số VN-Index", "weight_pct": 100.0, "net_return_pct": vni_q_ret}]
            }
        else:
            q_res = simulate_strategy_quarter(
                strategy_id=strategy_id,
                stocks=current_holdings_stocks,
                q_info=q_info,
                vni_return=vni_q_ret,
                is_rebalance=should_rebalance
            )
            strat_q_ret = q_res["quarter_return_pct"]

        if strat_q_ret > vni_q_ret:
            win_quarters += 1

        current_nav = current_nav * (1.0 + strat_q_ret / 100.0)
        if current_nav > peak_nav:
            peak_nav = current_nav
        dd = (current_nav - peak_nav) / peak_nav * 100.0
        if dd < max_drawdown_pct:
            max_drawdown_pct = dd

        nav_curve.append({
            "date": q_info["date"],
            "quarter": q_code,
            "nav": round(current_nav, 0),
            "return_pct": strat_q_ret,
            "drawdown_pct": round(dd, 2)
        })

        vni_nav = vni_nav * (1.0 + vni_q_ret / 100.0)
        vni_curve.append({
            "date": q_info["date"],
            "quarter": q_code,
            "nav": round(vni_nav, 0),
            "return_pct": vni_q_ret
        })

        if yr not in annual_returns:
            annual_returns[yr] = {"strat_growth": 1.0, "vni_growth": 1.0}
        annual_returns[yr]["strat_growth"] *= (1.0 + strat_q_ret / 100.0)
        annual_returns[yr]["vni_growth"] *= (1.0 + vni_q_ret / 100.0)

        quarterly_history.append(q_res)

    annual_summary = []
    for yr, d in annual_returns.items():
        s_ret = round((d["strat_growth"] - 1.0) * 100.0, 2)
        v_ret = round((d["vni_growth"] - 1.0) * 100.0, 2)
        annual_summary.append({
            "year": yr,
            "strategy_return_pct": s_ret,
            "vni_return_pct": v_ret,
            "outperformance_pct": round(s_ret - v_ret, 2)
        })

    total_return_pct = round(((current_nav - initial_capital) / initial_capital) * 100.0, 2)
    vni_total_return_pct = round(((vni_nav - initial_capital) / initial_capital) * 100.0, 2)

    total_quarters = len(selected_quarters)
    # Years elapsed measured from actual first→last quarter dates (start of the
    # first quarter to the end of the last), NOT quarters/4 - e.g. a 21-quarter
    # "5Y" window is ~5.00 calendar years, not 5.25.
    try:
        from datetime import date as _date
        _fq = selected_quarters[0]
        _lq = selected_quarters[-1]
        _first_day = _date(int(_fq["year"]), 3 * (int(_fq["quarter"]) - 1) + 1, 1)
        _y, _m, _d = (int(x) for x in str(_lq["date"]).split("-"))
        _last_day = _date(_y, _m, _d)
        years_elapsed = max((_last_day - _first_day).days / 365.25, 1e-9)
    except Exception:
        years_elapsed = total_quarters / 4.0

    if current_nav > 0 and years_elapsed > 0 and initial_capital > 0:
        cagr = round((math.pow(current_nav / initial_capital, 1.0 / years_elapsed) - 1.0) * 100.0, 2)
    else:
        cagr = -100.0

    if vni_nav > 0 and years_elapsed > 0 and initial_capital > 0:
        vni_cagr = round((math.pow(vni_nav / initial_capital, 1.0 / years_elapsed) - 1.0) * 100.0, 2)
    else:
        vni_cagr = 0.0

    # A risk-adjusted ratio whose denominator was clamped (max(0.1, vol)) is
    # not conservative, it is inflated: a strategy with near-zero measured
    # volatility got its excess return divided by 0.1 instead of by the real
    # figure. And substituting 1.0 for an unmeasurable volatility invents the
    # denominator outright. Both are withheld instead - see the same fix in
    # fair_value_backtest_service.
    MIN_MEANINGFUL_PCT = 0.01

    def _ratio(numerator: float, denominator: Optional[float]) -> Optional[float]:
        if denominator is None or denominator < MIN_MEANINGFUL_PCT:
            return None
        return round(numerator / denominator, 2)

    q_returns = [p["quarter_return_pct"] for p in quarterly_history]
    std_dev = float(np.std(q_returns, ddof=1)) if len(q_returns) > 1 else None
    annualized_volatility = round(std_dev * math.sqrt(4), 2) if std_dev is not None else None

    # rf_annual: annual risk-free assumption (see RF_ANNUAL module constant).
    rf_annual_pct = RF_ANNUAL * 100.0
    excess_return = cagr - rf_annual_pct
    sharpe_ratio = _ratio(excess_return, annualized_volatility)

    downside_rets = [r for r in q_returns if r < 0]
    downside_std = (
        float(np.std(downside_rets, ddof=1)) * math.sqrt(4)
        if len(downside_rets) > 1 else None
    )
    sortino_ratio = _ratio(excess_return, downside_std)

    win_rate_pct = round((win_quarters / total_quarters) * 100.0, 1) if total_quarters > 0 else 0.0

    # Reconciliation transparency: count how often the strategy actually held
    # investable (real-price) stocks. An empty basket must never masquerade as a
    # genuine 0% flat performance curve in the comparison table.
    total_holding_slots = sum(len(q.get("holdings", [])) for q in quarterly_history)
    real_holding_slots = sum(
        1 for q in quarterly_history for h in q.get("holdings", []) if h.get("is_real_price")
    )
    empty_basket = strategy_id != "vnindex" and real_holding_slots == 0
    avg_real_holdings = round(real_holding_slots / total_quarters, 1) if total_quarters else 0.0

    best_q = max(quarterly_history, key=lambda x: x["quarter_return_pct"]) if quarterly_history else {}
    worst_q = min(quarterly_history, key=lambda x: x["quarter_return_pct"]) if quarterly_history else {}

    return {
        "strategy": strat_meta,
        "parameters": {
            "time_horizon_years": time_horizon_years,
            "rebalance_cadence": rebalance_cadence,
            "top_k": top_k,
            "initial_capital": initial_capital,
            "exchange": exchange,
            "min_growth_pct": min_growth_pct,
            "survival_filter": survival_filter,
            "tsmom_filter": tsmom_filter,
            "fill_mode": fill_mode,
            "total_quarters": total_quarters,
            "forensic_filter": forensic_filter
        },
        "metrics": {
            "total_return_pct": total_return_pct,
            "vni_total_return_pct": vni_total_return_pct,
            "alpha_total_pct": round(total_return_pct - vni_total_return_pct, 2),
            "cagr": cagr,
            "vni_cagr": vni_cagr,
            "alpha_cagr": round(cagr - vni_cagr, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "annualized_volatility_pct": annualized_volatility,
            "rf_annual": RF_ANNUAL,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "win_rate_pct": win_rate_pct,
            "empty_basket": empty_basket,
            "avg_real_holdings": avg_real_holdings,
            "final_nav": round(current_nav, 0),
            "final_profit": round(current_nav - initial_capital, 0),
            "best_quarter": {
                "quarter": best_q.get("quarter", "--"),
                "return_pct": best_q.get("quarter_return_pct", 0)
            },
            "worst_quarter": {
                "quarter": worst_q.get("quarter", "--"),
                "return_pct": worst_q.get("quarter_return_pct", 0)
            }
        },
        "annual_matrix": annual_summary,
        "nav_curve": nav_curve,
        "vni_curve": vni_curve,
        "rebalance_history": quarterly_history
    }

def compare_all_screener_strategies(
    time_horizon_years: int = 5,
    rebalance_cadence: str = "quarterly",
    top_k: int = 10,
    initial_capital: float = 100_000_000.0,
    exchange: str = "ALL",
    min_growth_pct: float = 0.0,
    survival_filter: bool = False,
    fill_mode: str = "strict",
    tsmom_filter: bool = False,
    forensic_filter: bool = False
) -> Dict[str, Any]:
    strategies_to_test = [
        "deep_value_klarman",
        "ps_focus_fisher",
        "contrarian_dreman",
        "growth_philip_fisher",
        "peter_lynch_garp",
        "defensive_graham",
        "value_buffett",
        "buffetts_alpha",
        "novy_marx_quality_value",
        "gray_quantitative_value_qval",
        "hello_lower_risk",
        "hello_balanced_risk",
        "hello_full_throttle",
        "hello_lower_risk_mod",
        "hello_balanced_risk_mod",
        "hello_full_throttle_mod",
        "universal_survival_sector_moat",
        "guru_magic_formula_greenblatt",
        "guru_piotroski_fscore",
        "guru_zweig_conservative_growth",
        "guru_cornerstone_growth_oshaughnessy",
        "guru_cornerstone_value_oshaughnessy",
        "guru_neff_total_return",
        "guru_consensus_multi_model",
        "tsmom_moskowitz",
        "quant_q1",
        "quant_q2",
        "quant_q3",
        "quant_q4",
        "quant_q5",
        "vnindex"
    ]

    cache_key = (
        f"bt_compare_h{time_horizon_years}_{rebalance_cadence}_k{top_k}"
        f"_c{int(initial_capital)}_{exchange}_g{min_growth_pct}"
        f"_s{int(bool(survival_filter))}_t{int(bool(tsmom_filter))}_f{int(bool(forensic_filter))}_{fill_mode}"
    )
    cached = _compare_cache.get(cache_key)
    if cached is not None:
        return cached

    # Check for pre-computed backtest results (e.g. from Google Colab sync)
    if time_horizon_years == 5 and rebalance_cadence == "quarterly" and top_k == 10 and fill_mode == "strict" and exchange == "ALL" and not survival_filter and not tsmom_filter and not forensic_filter:
        precalc_path = resolve_data_file("backtest_results.json")
        if os.path.exists(precalc_path):
            try:
                with open(precalc_path, "r", encoding="utf-8") as f:
                    precalc = json.load(f)
                    if isinstance(precalc, dict) and precalc.get("leaderboard"):
                        _compare_cache.set(cache_key, precalc, ttl_seconds=3600)
                        return precalc
            except Exception:
                pass

    # Pin ONE universe snapshot and ONE price database for the whole comparison so
    # every strategy is reconciled on exactly the same data, regardless of how many
    # strategies are in the list or whether the TTL cache expires mid-run.
    screener_data = get_quant_screener(sector="ALL", quintile="ALL", exchange=exchange, min_growth_pct=min_growth_pct, limit=500)
    pinned_universe = sorted(
        screener_data.get("results", []),
        key=lambda s: str(s.get("symbol", ""))
    )

    results_map = {}
    comparison_table = []

    _freeze_real_price_database()
    try:
        for s_id in strategies_to_test:
            sim = run_screener_backtest(
                strategy_id=s_id,
                time_horizon_years=time_horizon_years,
                rebalance_cadence=rebalance_cadence,
                top_k=top_k,
                initial_capital=initial_capital,
                exchange=exchange,
                min_growth_pct=min_growth_pct,
                survival_filter=survival_filter,
                fill_mode=fill_mode,
                quant_universe=[dict(s) for s in pinned_universe],
                tsmom_filter=tsmom_filter,
                forensic_filter=forensic_filter
            )
            results_map[s_id] = sim

            m = sim["metrics"]
            st = sim["strategy"]
            comparison_table.append({
                "strategy_id": s_id,
                "name": st["name"],
                "short_name": st["short_name"],
                "color": st["color"],
                "icon": st["icon"],
                "cagr": m["cagr"],
                "total_return_pct": m["total_return_pct"],
                "alpha_cagr": m["alpha_cagr"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "sharpe_ratio": m["sharpe_ratio"],
                "sortino_ratio": m["sortino_ratio"],
                "win_rate_pct": m["win_rate_pct"],
                "empty_basket": m["empty_basket"],
                "avg_real_holdings": m["avg_real_holdings"],
                "final_nav": m["final_nav"],
                "final_profit": m["final_profit"]
            })
    finally:
        _unfreeze_real_price_database()

    # Empty-basket strategies (zero investable holdings the whole period) must not
    # compete with real curves: sink them below every ranked row.
    ranked_leaderboard = sorted(
        comparison_table,
        key=lambda x: (x.get("empty_basket", False), -x["cagr"])
    )

    rank = 1
    for item in ranked_leaderboard:
        if item["strategy_id"] == "vnindex":
            item["rank"] = "--"
            item["medal"] = "Chỉ Số Chuẩn"
        elif item["strategy_id"] == "quant_q5":
            item["rank"] = "--"
            item["medal"] = "Đối Chứng Rủi Ro"
        elif item.get("empty_basket"):
            item["rank"] = "--"
            item["medal"] = "⚠️ Rỗng Rổ (Không Đủ Điều Kiện)"
        else:
            item["rank"] = rank
            if rank == 1: item["medal"] = "🥇 Quán Quân"
            elif rank == 2: item["medal"] = "🥈 Á Quân"
            elif rank == 3: item["medal"] = "🥉 Hạng Ba"
            else: item["medal"] = f"Hạng {rank}"
            rank += 1

    winner = next(
        (x for x in ranked_leaderboard if x["strategy_id"] not in ["vnindex", "quant_q5"] and not x.get("empty_basket")),
        ranked_leaderboard[0] if ranked_leaderboard else {}
    )

    result = {
        "parameters": {
            "time_horizon_years": time_horizon_years,
            "rebalance_cadence": rebalance_cadence,
            "top_k": top_k,
            "initial_capital": initial_capital,
            "exchange": exchange,
            "survival_filter": survival_filter,
            "tsmom_filter": tsmom_filter,
            "fill_mode": fill_mode,
            "time_label": f"{time_horizon_years} Năm (2016 – 2026 Thập Kỷ)" if time_horizon_years >= 10 else (f"{time_horizon_years} Năm (2021 – 2026 Toàn Kỳ)" if time_horizon_years == 5 else f"{time_horizon_years} Năm Gần Nhất")
        },
        "winner": winner,
        "leaderboard": ranked_leaderboard,
        "strategies_results": results_map
    }
    _compare_cache.set(cache_key, result, ttl_seconds=600)
    return result
