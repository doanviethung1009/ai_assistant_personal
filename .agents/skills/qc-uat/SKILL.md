---
name: qc-uat
description: Quy trình kiểm thử chất lượng (QC) và nghiệm thu người dùng (UAT) cho các tính năng mới trên web, backend và luồng xử lý dữ liệu. Dùng khi hoàn thành một chức năng và cần kiểm tra tổng thể hoặc khi User yêu cầu rà soát lỗi trước khi go-live.
---

# Quy trình QC và UAT Toàn diện

Mục đích: Đảm bảo mọi tính năng được phát triển (Backend, Frontend, Data Sync) hoạt động trơn tru, xử lý tốt ngoại lệ (edge cases), và giữ được thiết kế UX/UI đồng nhất.

Agent cần tuân thủ nghiêm ngặt checklist này TRƯỚC KHI báo cáo hoàn thành chức năng cho User, hoặc dùng nó làm cơ sở kiểm thử khi User gọi lệnh "QC / Kiểm tra hệ thống".

## 1. Kiểm tra Web & Giao diện (Web / Frontend QC)
- [ ] **Giao diện (UI & CSS):** 
  - Tuân thủ thiết kế hiện tại (Premium, Glassmorphism, bóng đổ, gradient).
  - Không bị vỡ khung trên màn hình nhỏ (Responsive).
  - Các state Hover, Active, Disabled của buttons hoạt động mượt mà.
- [ ] **State & Form:**
  - Form phải có thông báo lỗi (Validation error) và chặn submit khi dữ liệu sai.
  - Các Filter/Search phải giữ đúng state trên URL (URL Params) và không làm trôi dữ liệu khi refresh.
- [ ] **Loading & Empty State:**
  - Có hiệu ứng xoay (spinner) hoặc Skeleton khi đang chờ gọi API.
  - Xử lý tốt trường hợp không có dữ liệu (Empty State) — không hiển thị mảng rỗng vô hồn.
- [ ] **Phản hồi hệ thống (Feedback):**
  - Mọi thao tác thành công (Create, Update, Delete) phải có thông báo Toast/Alert cho User.
  - Cập nhật ngầm (Soft Refresh) thông qua `router.refresh()` hoặc state React thay vì `window.location.reload()`.

## 2. Kiểm tra Backend & Chức năng (Functional QC)
- [ ] **Logic Nghiệp vụ:**
  - Đảm bảo tính toán đúng, sắp xếp/lọc (sort/filter) hoạt động theo cả hai chiều ASC/DESC.
  - Xử lý tốt khi trường dữ liệu (fields) là null, rỗng, hoặc undefined.
- [ ] **Bảo mật & Phân quyền (RBAC):**
  - Đảm bảo chức năng được bảo vệ bởi đúng User Role (Admin, Member).
  - Thử các thao tác phá hoại (Xoá data không phải của mình) xem API có chặn (401/403) không.
- [ ] **Hiệu suất & Lỗi (Performance & Errors):**
  - Các thao tác Update, Delete phải cập nhật timestamp (`updated_at`, `deleted_at`).
  - Nếu API lỗi (500) hoặc timeout, Web có hứng được lỗi và báo cho người dùng một cách thân thiện không (không crash trắng trang).

## 3. Kiểm tra Dữ liệu & Đồng bộ (Data & Integration QC)
- [ ] **Tính nhất quán dữ liệu (Data Integrity):**
  - Dữ liệu thêm từ Web có đồng bộ chính xác xuống Engine JSON cục bộ và Postgres (nếu có dùng).
  - Khi xoá dữ liệu, dữ liệu phụ thuộc (cascade) có bị xử lý đúng không.
- [ ] **Đồng bộ bên thứ ba (Jira/Obsidian):**
  - Khi Jira thay đổi (comment, đổi trạng thái), API đồng bộ phải phân tích (parse) an toàn các định dạng text.
  - Kiểm tra trường hợp mất kết nối / Token hết hạn (Graceful degradation).
- [ ] **Timezone & Định dạng ngày tháng:**
  - Đảm bảo lưu UTC ở DB và hiển thị chuẩn định dạng của User ở Web.

## 4. Nghiệm thu E2E (End-To-End UAT Flow)
Để xác nhận tính năng đã pass, Agent hãy đóng vai người dùng thực hiện một luồng khép kín (Happy Path):
1. **Tạo dữ liệu:** Bấm nút thêm mới -> nhập data hợp lệ -> xác nhận có thông báo lưu thành công -> dữ liệu xuất hiện ở đầu bảng (nếu sort newest).
2. **Sửa & Tương tác:** Thay đổi dữ liệu -> đổi bộ lọc -> xác nhận bộ lọc giữ nguyên và dữ liệu sửa không biến mất.
3. **Xoá / Đóng:** Huỷ hoặc hoàn thành -> kiểm tra xem nó có rơi đúng vào tab "Đã hoàn thành / Thùng rác" không.

> **Hành động của AI:** Nếu bạn đang review code cho một file theo chuẩn này, hãy chỉ ra cụ thể code đó thiếu dòng checklist nào và viết script (hoặc patch) để sửa nó luôn!
