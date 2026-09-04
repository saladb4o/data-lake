# Roadmap: Bơm Toàn Bộ Metric Chuyên Sâu Từ VNDIRECT Finfo Vào 22 Mô Hình Định Giá

## 1. Hiện Trạng & Khả Năng Khai Thác
Kho từ điển `financial_models.json` của VNDIRECT Finfo chứa tới **2,500 mã mục kế toán (ItemCodes)** bóc tách chi tiết từng dòng trong 4 báo cáo:
1. **Báo cáo Kết quả Hoạt động Kinh doanh (Income Statement)**
2. **Bảng Cân đối Kế toán (Balance Sheet)**
3. **Báo cáo Lưu chuyển Tiền tệ Trực tiếp & Gián tiếp (Cash Flow Statement)**
4. **Thuyết minh BCTC & Chỉ tiêu Đặc thù Ngành (Banking, Securities, Insurance)**

---

## 2. Bảng Phân Bổ Metric VNDIRECT Bơm Vào Từng Mô Hình Định Giá Cụ Thể

| Mô hình Định giá | Metric hiện tại (Ước lượng) | Metric VNDIRECT Finfo sẽ bơm trực tiếp (Chính xác 100%) | Lợi ích mang lại |
| :--- | :--- | :--- | :--- |
| **Model 15: Buffett Owner's Earnings** | $\Delta\text{Working Capital} = 0.0$<br>$\text{Maintenance CapEx} = \text{D\&A} \times 0.8$ | • `31120`: Lợi nhuận trước thay đổi VLĐ<br>• `31130`: Biến động phải thu ($\Delta\text{AR}$)<br>• `31140`: Biến động hàng tồn kho ($\Delta\text{Inv}$)<br>• `31150`: Biến động phải trả ($\Delta\text{AP}$)<br>• `32110`: Tiền mua sắm TSCĐ (CapEx thực) | Tính chính xác dòng tiền thặng dư thực tế của Warren Buffett mà không cần ước lượng $\Delta\text{WC}$. |
| **Model 17: Bank Equity Cash Flow & Basel II** | $\text{RWA} = \text{MCap} \times 1.2$<br>$\text{Target CAR} = 11\%$ | • `112000`: Cho vay khách hàng thuần<br>• `112900`: Dự phòng rủi ro cho vay<br>• `14100`: Vốn điều lệ & Các quỹ dự trữ ngân hàng<br>• `421100`: Thu nhập lãi thuần | Tính chính xác Tỷ lệ An toàn vốn CAR và dòng tiền FCFE cho nhóm Ngân hàng (VCB, TCB, MBB, BID, CTG,...). |
| **Model 18: REIT / Real Estate AFFO & RNAV** | $\text{Landbank} = \text{MCap} \times 0.2$ | • `11420`: Chi phí SXKD dở dang BĐS<br>• `12510`: BĐS Đầu tư nguyên giá<br>• `12520`: Khấu hao BĐS đầu tư<br>• `13130`: Người mua trả tiền trước ngắn hạn | Định giá chuẩn xác giá trị quỹ đất (Landbank) và số tiền khách hàng đóng tiền trước theo tiến độ dự án (VHM, NVL, KDH, NLG, DXG,...). |
| **Model 21: Consumer EVA & MVA** | $\text{Invested Capital} = \text{MCap} \times 0.5$ | • $\text{Invested Capital} = \text{Equity (14000)} + \text{Vay ngắn/dài hạn} - \text{Tiền mặt (11100)}$<br>• $\text{NOPAT} = \text{EBIT} \times (1 - \text{Thuế thực tế } \frac{21025}{\text{Pretax}})$ | Đo lường chính xác Giá trị Kinh tế Gia tăng (Economic Value Added) cho nhóm Tiêu dùng & Bán lẻ (MWG, MSN, PNJ, VNM,...). |
| **Model 16: Pharma & R&D rNPV** | Pipeline giả định | • `21023`: Chi phí Nghiên cứu & Phát triển (R&D)<br>• `12300`: Tài sản vô hình (Bằng sáng chế, Bản quyền dược) | Chiết khấu chuẩn xác giá trị danh mục thuốc cho ngành Dược phẩm (DHG, IMP, TRA, DBD,...). |

---

## 3. Lộ Trình Triển Khai (Kế hoạch 2 Giai đoạn)

### Giai đoạn 1: Đã hoàn tất và đang vận hành ổn định
- ✅ Kết nối trực tiếp VNDIRECT Finfo API vào `UnifiedDataService`.
- ✅ Chuẩn hóa $100\%$ các trường BCTC cốt lõi về VNĐ (Doanh thu, LNST, EBIT, Tổng tài sản, Vốn CSH, Nợ vay, Tiền mặt).
- ✅ Đồng bộ hóa sang hệ thống 9 Tam giác Kế toán Kép và bộ 22 mô hình định giá.

### Giai đoạn 2: Bơm sâu các trường vi mô (Granular Items)
- Khi gọi định giá chuyên sâu cho từng cổ phiếu riêng lẻ tại màn hình *"Biểu đồ & Phân tích"*:
  1. Tự động kéo toàn bộ 120 dòng BCTC chi tiết từ Finfo.
  2. Bơm trực tiếp các ItemCodes đặc thù (`31130`, `31140`, `11420`, `13130`, `112000`) vào Model 15, Model 17, Model 18 và Model 21.
  3. Cập nhật bảng điểm Forensic (Beneish M-Score & Altman Z'') với tỷ lệ tài sản dở dang và khoản phải thu chính xác tuyệt đối từ kiểm toán.
