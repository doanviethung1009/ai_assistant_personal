# Thư viện Prompt mẫu cho AI Agent

Tài liệu này tổng hợp các mẫu câu lệnh (Prompt) "chuẩn bài" để giao tiếp với các AI Agent (Gemini, Claude, Cursor...) hoạt động trong dự án này. 

Do dự án đã được trang bị kiến trúc **AI Agent Rules & Skills**, bạn không cần phải viết những prompt dài hàng trang A4 để giải thích cấu trúc. Hãy tận dụng sức mạnh của các **từ khoá kích hoạt**.

---

## 1. Tình huống: Phát triển chức năng mới hoàn toàn
Thay vì bảo: *"Làm cho tôi chức năng quản lý khách hàng gồm cả backend lẫn frontend"*, hãy ép AI sử dụng quy trình (Skill) đã được định nghĩa sẵn.

**👉 Prompt khuyên dùng:**
> "Tôi muốn làm tính năng Quản lý Khách hàng (Customer). Hãy dùng skill `add-entity` để thực hiện toàn bộ quy trình từ Database, Backend API cho đến Frontend Next.js. Chú ý bảng Customer cần có các trường: tên, email, và số điện thoại."

**💡 Vì sao nó hiệu quả?**
AI sẽ lập tức mở file `.agents/skills/add-entity/SKILL.md` ra đọc, và nó sẽ tự động chạy qua 15 bước chuẩn (tạo model SQLAlchemy, tạo Pydantic schema, tạo endpoint FastAPI, cập nhật docs, và tạo giao diện Web) mà không bỏ sót bước nào.

---

## 2. Tình huống: Sửa lỗi (Fix bug) hoặc Refactor
Khi nhờ AI sửa lỗi, hãy ép nó tuân thủ các quy định (Rules) đang có để tránh việc AI viết code theo bản năng.

**👉 Prompt khuyên dùng:**
> "Đang có lỗi ở trang Danh sách Project trên Web (không hiện đủ dữ liệu). Hãy check file `apps/web/app/projects/page.tsx` và API tương ứng ở backend. Trong lúc fix lỗi, nhớ tuân thủ nghiêm ngặt rule `web-conventions` và nguyên tắc phân trang."

**💡 Vì sao nó hiệu quả?**
AI sẽ tự động nạp file `.agents/rules/web-conventions.md` và tuân thủ các quy tắc về Fetch data, Server Actions hay Pagination thay vì tự ý cài thêm một thư viện bừa bãi nào đó.

---

## 3. Tình huống: Lưu lại code và Commit
Đừng tự tay gõ lệnh git add commit dài dòng, hãy giao cho Agent làm việc đó một cách chuyên nghiệp.

**👉 Prompt khuyên dùng:**
> "Tôi đã test xong. Hãy dùng skill `git-commit` để đóng gói toàn bộ các thay đổi vừa rồi và đẩy lên nhánh hiện tại nhé."

**💡 Vì sao nó hiệu quả?**
Skill `git-commit` bắt buộc AI phải dùng chuẩn *Conventional Commits* (feat, fix, chore...), kiểm tra lại danh sách file đã sửa, và viết một commit message rất rõ ràng và chuẩn kỹ thuật.

---

## 4. Tình huống: Debugging nâng cao (Tìm lỗi hệ thống)
Khi server báo lỗi 500 nhưng bạn lười mở terminal để tìm log.

**👉 Prompt khuyên dùng:**
> "Backend đang báo lỗi 500 khi gọi API `/api/v1/tasks/1/complete`. Hãy vào container `api` đọc log hoặc tìm xem lỗi nằm ở đâu, sau đó tự vá lỗi và viết comment giải thích tại sao lại lỗi nhé (tuân thủ `comment-style`)."

**💡 Vì sao nó hiệu quả?**
AI có công cụ thực thi lệnh Terminal (bash). Nó sẽ tự chạy lệnh check log docker, tự tìm file, tự fix lỗi và khi fix xong nó sẽ nhớ nạp rule `comment-style` để viết docstring ghi chú lại nguyên nhân lỗi ngay trong code để bạn dễ đọc sau này.

---

## 5. Tình huống: Review Code
Trước khi gộp nhánh, bạn có thể yêu cầu AI review lại code của chính bạn (hoặc của nó) dựa trên tiêu chuẩn kiến trúc dự án.

**👉 Prompt khuyên dùng:**
> "Hãy review lại toàn bộ những thay đổi trong commit gần nhất (hoặc file `xyz.py`). Đối chiếu với `backend-conventions` và `PROJECT_STRUCTURE.md` xem tôi có đang viết sai kiến trúc hay vi phạm chuẩn RESTful API không."

---

## 🔥 Công thức Prompt thần thánh trong dự án này:
1. **Bối cảnh (Context):** Đang bị gì, muốn làm gì?
2. **Trỏ file (Pointer):** Gợi ý cho AI biết file nào liên quan (nếu biết).
3. **Gọi Skill (Skill Trigger):** *"Hãy dùng skill..."*
4. **Ép Rule (Rule Enforcer):** *"Nhớ tuân thủ rule..."*
