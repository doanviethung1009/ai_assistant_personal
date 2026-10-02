# Lưu trữ Dữ liệu AI: Database vs. Markdown

Hệ thống Builder AI Assistant hiện tại thiết kế 2 luồng lưu trữ hoàn toàn khác biệt dành cho dữ liệu sinh ra từ AI, phục vụ 2 mục đích khác nhau. Việc hiểu rõ 2 luồng này giúp bạn quyết định xem khi nào nên dùng Database, khi nào nên dùng Markdown.

---

## 1. Luồng 1: Lưu trữ dạng Nhật ký (Markdown Trace)
**Ví dụ thực tế:** File `docs/ai_logs.md`

- **Định dạng:** Văn bản thuần (Markdown).
- **Mục đích:** Dùng để "truy vết" (Trace) tiến độ công việc hằng ngày của Agent (nó đã sửa file nào, gặp lỗi gì).
- **Cách thức hoạt động:** AI dùng công cụ Edit/Write File để trực tiếp chèn thêm (append) văn bản vào cuối file.
- **Ưu điểm:**
  - Rất nhẹ, không tốn chi phí gọi API hay setup Database.
  - Con người đọc cực kỳ dễ hiểu.
  - Khi một AI mới được đưa vào dự án, nó có thể đọc lướt qua file Markdown này và lập tức lấy được toàn bộ "Context" lịch sử dự án để làm việc tiếp.
- **Nhược điểm:** Khó truy vấn (Ví dụ: Không thể filter "Lọc tất cả prompt vào ngày 10/10").

---

## 2. Luồng 2: Lưu trữ dạng Cấu trúc (Database / JSON)
**Ví dụ thực tế:** Chức năng ghi lịch sử Chat (Sắp tới nếu phát triển)

Nếu dữ liệu Prompt và Trả lời của AI được xây dựng thành một **Tính năng Hệ thống (Entity)**, nó **BẮT BUỘC** phải tuân thủ kiến trúc lưu trữ đa nguồn (Multi-Source Storage) giống hệt như tính năng `Task` hay `Note`.

Nghĩa là, dữ liệu sẽ được chia làm 3 hướng lưu trữ dựa trên biến môi trường `DATA_SOURCE`:

1. **`DATA_SOURCE=api` (PostgreSQL Database):** 
   - Dữ liệu prompt/response sẽ được gửi xuống Backend FastAPI.
   - Lưu trữ an toàn trong bảng `AiLog` của database PostgreSQL. Phù hợp cho môi trường Production, có thể chia trang, lọc theo ngày tháng, phân tích Dữ liệu lớn (Big Data) để Train model.
2. **`DATA_SOURCE=file` (Lưu JSON cục bộ):** 
   - Dữ liệu không gọi API, mà được ghi thẳng vào một file `data/ailogs.json` trên ổ cứng máy chủ thông qua Next.js Server Actions.
   - Phù hợp khi bạn chạy App cục bộ không muốn cài cắm Database phức tạp.
3. **`DATA_SOURCE=memory` (Bộ nhớ tạm RAM):**
   - Lưu vào biến Global của Node.js. Mất sạch khi khởi động lại server.
   - Phục vụ riêng cho việc chạy Smoke Test CI/CD.

---

## Khi nào dùng hướng nào?

- **Dùng Luồng 1 (Markdown):** Khi bạn chỉ muốn ghi chép quá trình sửa code của Agent để người khác/model khác vào đọc lại dễ hiểu.
- **Dùng Luồng 2 (Database/JSON):** Khi bạn xây dựng một giao diện "Khung Chat AI" (Giống ChatGPT) ngay trên Web UI, cần lưu lại hàng ngàn câu hỏi của User, có chức năng tìm kiếm, phân trang và xoá lịch sử chat. (Để làm được điều này, bạn cần gọi skill `add-entity`).

---

## 3. Lộ trình chuyển đổi AI Trace Logs sang Database
Hệ thống hiện tại đang trong quá trình chuyển đổi (Refactor) hệ thống lưu vết AI Logs từ Luồng 1 (Markdown) sang Luồng 2 (Database/JSON) giống như thực thể `Task` để phục vụ Import/Export.

**Các bước đã hoàn thành:**
1. Đã tạo Database Model `AiLog` (`apps/core/app/models/ai_log.py`).
2. Đã tạo Enum, Schema (`apps/core/app/schemas/ai_log.py`).
3. Đã tạo Service xử lý logic (`apps/core/app/services/ai_log_service.py`).
4. Đã định nghĩa API Router (`apps/core/app/api/v1/ai_logs.py`) và gắn vào app.
5. Đã khai báo schema `ai_logs: any[]` vào `DataFile` ở thư mục frontend (`apps/web/lib/store/types.ts`) và nâng `SCHEMA_VERSION` lên 4.

**Các bước cần làm tiếp theo (Người dùng thực hiện):**
Để hoàn thiện tính năng, hãy mở Terminal (ở nơi có cài đặt Docker/Python) và chạy các lệnh sau:
1. Chạy `make migration m="add_ai_logs"` và `make migrate` để tạo bảng trong CSDL Postgres.
2. Chạy `make gen-types` để tự động sinh file `openapi.d.ts` ở Frontend, giúp map kiểu dữ liệu cho giao diện.
3. Cài đặt các hàm thao tác file tại Frontend (ví dụ: `apps/web/lib/store/json-file.ts`) để hỗ trợ Export file JSON cho `AiLogs`.
