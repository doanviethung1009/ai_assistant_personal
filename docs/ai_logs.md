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
