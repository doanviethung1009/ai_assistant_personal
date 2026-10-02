# Nhật ký hoạt động của AI (AI Task Trace)

File này lưu trữ vết (trace) toàn bộ các quyết định, xử lý và phản hồi của các AI Agent khi thao tác trên dự án này. Dữ liệu này dùng để kiểm toán (audit), gỡ lỗi (debug) và huấn luyện lại (fine-tune/train) các mô hình trong tương lai.

---

### [03-10-2026 01:24] | Category: [TOOL]
- **Prompt:** "Tôi muốn bổ sung thêm function ghi log khi prompt và xử lý và trả lời của AI theo flow chia từng đầu mục như tạo app hay api hay tool hay web để trace và train."
- **Xử lý:** 
  - Giao tiếp với User để chốt phương án: Tạo Luật ngầm (Rule) bắt buộc AI ghi log vào file Markdown.
  - Tạo mới file `.agents/rules/ai-logger.md` cấu hình regex `*` để bắt AI tự nạp luật này trong mọi tình huống.
  - Định nghĩa 4 danh mục chuẩn: `[APP]`, `[API]`, `[WEB]`, `[TOOL]`.
  - Khởi tạo file `docs/ai_logs.md` này để làm mẫu cho con AI bắt đầu ghi log từ bây giờ.
- **Phản hồi:** Thông báo cho User rằng cơ chế Auto-Logging đã được thiết lập thành công thông qua Hệ thống Rule, sẵn sàng phục vụ việc truy vết và training.

---

### [03-10-2026 01:30] | Category: [TOOL]
- **Prompt:** "Lưu toàn bộ quy trình update của git theo flow trong tài liệu và update khi có update hay fix mới."
- **Xử lý:**
  - Nhận diện yêu cầu tự động hoá việc sinh file `CHANGELOG.md` từ các commit (feat, fix, docs).
  - Khám phá lỗi trên script `scripts/changelog.sh` (không tương thích Bash 3.2 trên macOS do dùng mảng kết hợp `declare -A`).
  - Sửa lỗi script tương thích mọi HĐH, và thay thế đường dẫn `.kiro` cũ thành `.agents`.
  - Thực thi lệnh `make changelog` để cập nhật toàn bộ quá trình làm việc của mình nãy giờ vào `CHANGELOG.md`.
  - Lưu Commit & Đẩy code lên. Tự động tuân thủ rule `ai-logger.md` để ghi nhận báo cáo này.
- **Phản hồi:** Thông báo User rằng kịch bản tạo Changelog tự động đã được bảo trì và chạy thành công.

---

### [03-10-2026 01:32] | Category: [APP]
- **Prompt:** "Thêm vào rule về việc ghi nhật ký AI trace và đưa thành 1 tab chức năng đi."
- **Xử lý:**
  - Bổ sung luật Ghi nhật ký (AI Task Trace) vào mục 3.4 của file `AGENTS.md` (Root Protocol) để bắt buộc tất cả các AI đều phải biết quy tắc này từ khi mới vào dự án. Đánh số lại các mục.
  - Cập nhật file `apps/web/lib/nav.ts`, bổ sung một Menu Tab mới có tên là **AI Trace** điều hướng thẳng tới `/docs/ai-logs`.
- **Phản hồi:** Tính năng truy vết đã lên sóng dưới dạng một Tab độc lập trên giao diện người dùng.
