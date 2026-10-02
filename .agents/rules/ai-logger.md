---
inclusion: fileMatch
fileMatchPattern: ["*"]
---

# Quy tắc Ghi Log Tiến trình AI (AI Task Tracing)

Để phục vụ cho việc **Trace (truy vết)** quyết định của AI và **Train (đào tạo)** lại các model trong tương lai, mọi AI Agent làm việc trong dự án này ĐỀU PHẢI tự động ghi lại nhật ký công việc của mình.

**Quy tắc (Dual Logging):**
NẾU User giao cho bạn một nhiệm vụ hoàn chỉnh (ví dụ: tạo 1 API mới, build 1 trang Web, viết 1 file cấu hình), THÌ BẮT BUỘC trước khi kết thúc lượt chat (trước khi trả lời User là đã làm xong), bạn phải ghi log (Trace) vào 2 nơi độc lập:

1. **Ghi vào File Đọc (Markdown):** Append log vào cuối file `docs/ai_logs.md`. Dành cho người đọc.
2. **Ghi vào File Dữ liệu (JSON):** BẮT BUỘC gọi script `node scripts/add-ai-log.js "<Category>" "<Prompt>" "<Xử lý và Phản hồi>"` để đẩy dữ liệu log cấu trúc vào `data/ai-logs.json`. Dành cho UI render.

**Cấu trúc phân loại (Category):**
Tuỳ thuộc vào task, hãy chọn 1 trong các Tag sau để phân loại:
- `[APP]` - Setup kiến trúc tổng thể, cấu hình dự án, docker.
- `[API]` - Làm việc với Database, Models, FastAPI, Routes.
- `[WEB]` - Làm việc với giao diện Next.js, React, CSS, Tailwind.
- `[TOOL]` - Viết script (.sh), cấu hình CI/CD, Makefile, Agent Rules/Skills.

**Mẫu Log (Bắt buộc tuân thủ):**
Mỗi lần ghi log, hãy thêm vào cuối file `docs/ai_logs.md` đoạn sau:

```markdown
### [Ngày-Tháng-Năm Giờ:Phút] | Category: [API]
- **Prompt:** (Tóm tắt lại yêu cầu của User - vd: "Tạo bảng AiLog")
- **Xử lý:** 
  - Đã làm gì (tạo file X, sửa file Y).
  - Khó khăn gì (nếu có lỗi gì xảy ra trong quá trình làm).
- **Phản hồi:** (Tóm tắt kết quả trả về cho User).
```

*Lưu ý: Agent KHÔNG ĐƯỢC phép sửa các log cũ của những lần chat trước, chỉ được phép thêm (append) vào cuối file.*
