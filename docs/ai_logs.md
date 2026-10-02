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

---

### [03-10-2026 01:34] | Category: [WEB]
- **Prompt:** "Cái tab AI trace đang bị lỗi nên move menu Nhật ký qua tab này, chỗ tài liệu chỉ nên mô tả chức năng và rule."
- **Xử lý:**
  - Nhận diện lỗi: Next.js báo 404 vì đường dẫn `/docs/ai-logs` trên thanh Menu không hợp lệ (Do thư mục `docs/` dùng Search Params `/docs?doc=` chứ không phải Slug params `/docs/[slug]`).
  - Tạo mới một Page độc lập hoàn toàn tại `apps/web/app/ai-logs/page.tsx` để chuyên render file nhật ký này.
  - Sửa lại đường dẫn Menu trong `apps/web/lib/nav.ts` trỏ tới đúng `/ai-logs`.
  - Sửa lại cấu hình `apps/web/lib/docs.ts`: Ở phần Tài liệu, mục AI Logs giờ đây sẽ render nội dung của file luật `.agents/rules/ai-logger.md` (giải thích chức năng và cơ chế nạp) thay vì hiển thị toàn bộ nội dung nhật ký dài ngoằng.
- **Phản hồi:** Lỗi 404 đã được khắc phục. File tài liệu cũng đã được phân tách rõ ràng giữa "Hiển thị Dữ liệu" và "Hiển thị Luật".

---

### [03-10-2026 01:40] | Category: [API]
- **Prompt:** "Data của trace log này nên lưu theo json và giống data task cần import vào."
- **Xử lý:**
  - Bắt đầu chuyển đổi luồng dữ liệu AI Trace sang hướng Database (DATA_SOURCE).
  - Khởi tạo Data Model `AiLog` và schema chuẩn Pydantic.
  - Xây dựng file Service `ai_log_service.py` hỗ trợ filter, pagination và create.
  - Xây dựng API Route `api/v1/ai_logs.py` chuẩn REST. Đã register vào hệ thống.
  - Thay đổi cấu trúc file `DataFile` ở phía Frontend để chuẩn bị đón file JSON chứa `ai_logs`.
  - Cập nhật tài liệu `AI_DATA_STORAGE.md` bổ sung hướng dẫn cài đặt Docker và Migrate tiếp theo.
- **Phản hồi:** Thông báo User rằng toàn bộ nền móng Backend và cấu trúc JSON đã làm xong, chờ môi trường có Docker chạy lệnh Migrate là sẽ có thể code nốt màn hình UI cho Dữ liệu có cấu trúc.

---

### [03-10-2026 01:43] | Category: [TOOL]
- **Prompt:** "Nên thêm role mỗi khi có app, tool, chức năng, hay api mới hoặc sửa đổi cập nhật thì nên update các trang liên quan."
- **Xử lý:**
  - Cập nhật file System Prompt `AGENTS.md` (Mục 3.3).
  - Bổ sung chỉ thị "Đồng bộ Tài liệu": Bắt buộc AI phải chủ động quét và cập nhật các file như `API_REFERENCE.md`, `PROJECT_STRUCTURE.md` mỗi khi có thay đổi mã nguồn tương ứng.
- **Phản hồi:** Đã thêm Rule vào System Prompt. Từ nay mọi Agent đều sẽ tự động làm thao tác đồng bộ hoá document.

---

### [03-10-2026 01:47] | Category: [WEB]
- **Prompt:** "SCHEMA_VERSION = 4 cái này là sao vậy bạn có mô tả gì chưa."
- **Xử lý:**
  - Phát hiện tài liệu giải thích về cơ chế Local JSON Storage (Data Migration JSON) còn thiếu.
  - Tự động tuân thủ theo rule Đồng bộ Tài liệu: Tạo file `docs/JSON_STORAGE.md` mô tả tường tận tại sao hệ thống không dùng Alembic cho chế độ JSON mà tự viết cơ chế vòng lặp `if schema_version < x` để vá dữ liệu (Backfill).
  - Đăng ký file này vào danh sách `apps/web/lib/docs.ts` để hiển thị trên UI.
- **Phản hồi:** Giải thích ngắn gọn cơ chế Schema Version cho User và hướng dẫn họ xem chi tiết ở mục Tài liệu mới được tự động sinh.

---

### [03-10-2026 01:54] | Category: [TOOL]
- **Prompt:** "Tôi nghĩ bất kể data nào trong này sẽ có 2 dạng local và database, nên đấnh giá và đưa vào rule về việc data lưu ở local dạng json nên tách riêng ra hay để chung mỗi khi phát sinh function data mới."
- **Xử lý:**
  - Nhận thấy đây là một đúc kết cực kỳ giá trị về mặt Kiến trúc phần mềm (Software Architecture).
  - Đã cập nhật file quy tắc `.agents/rules/web-conventions.md` (nơi quản lý các luật của Frontend và Local JSON).
  - Bổ sung rule **Local Storage Split vs Group**: Bắt buộc Agent từ nay về sau khi tạo Data mới, phải tự đánh giá: Nếu data dạng Append-only/kích thước lớn (như Log) thì BẮT BUỘC phải tạo file JSON riêng biệt để tránh thắt cổ chai I/O. Ngược lại, nếu data có tính ràng buộc/cập nhật liên tục (như Task, Notes) thì nhét chung vào `builder-data.json`.
- **Phản hồi:** Đã đưa triết lý này thành một Rule bắt buộc trong hệ thống Agentic.

---

### [03-10-2026 01:58] | Category: [TOOL]
- **Prompt:** "Kiểm tra xem có rule bắt buộc ghi log promt của dự án vào file json chưa?"
- **Xử lý:**
  - Phát hiện rule cũ `.agents/rules/ai-logger.md` mới chỉ yêu cầu AI ghi vào file `.md`.
  - Cập nhật rule: Yêu cầu AI từ nay phải thực hiện **Ghi log kép (Dual Logging)**: Vừa viết vào Markdown (để đọc) vừa bắn vào JSON/Database (để UI render).
  - Tạo một script tiện ích `scripts/add-ai-log.js` giúp các Agent sau này đẩy Data vào file `data/ai-logs.json` một cách an toàn mà không sợ làm hỏng định dạng JSON.
- **Phản hồi:** Báo cáo hoàn tất việc thiết lập Rule và demo luôn bằng cách ghi chính log này vào file JSON.
