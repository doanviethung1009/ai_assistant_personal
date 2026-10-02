# Kịch bản Demo: Làm việc với Multi-Agent (Nhiều AI Agent)

Khi dự án lớn lên, việc nhồi nhét cho một AI (ví dụ: Claude 3.5 hoặc Gemini 1.5) làm từ A-Z (từ Database, Backend, sang Frontend) trong cùng một prompt thường dẫn đến rủi ro: AI bị "ảo giác" (hallucination), quên context, hoặc viết code phá vỡ kiến trúc cũ.

Giải pháp tối ưu là **Multi-Agent Workflow** (Phân chia vai trò): Bạn (đóng vai trò là Product Manager / Orchestrator) sẽ chia task và giao cho từng AI Agent chuyên biệt.

Dưới đây là Demo quy trình thực tế khi phát triển tính năng **"Giỏ Hàng" (Shopping Cart)**.

---

## 🛠 Bước 1: Giao việc cho Backend Agent (Ví dụ: dùng Gemini 1.5 Pro)
**Mục tiêu:** Thiết kế Schema Database và viết API. Agent này không được phép đụng vào Frontend.

**👉 Prompt giao việc cho Backend Agent:**
> "Bạn là Backend Expert. Hãy phát triển tính năng Giỏ hàng (Cart) cho hệ thống. 
> 1. Dùng skill `add-entity` để tạo bảng CartItem trong database. 
> 2. Viết các API CRUD tại route `/api/v1/cart`.
> 3. Cấm tuyệt đối đụng vào thư mục `apps/web/`. Bắt buộc phải tuân thủ `backend-conventions`.
> Khi xong, hãy dùng skill `git-commit` để lưu lại với message 'feat(core): add cart api'."

**Kết quả thu được:**
Backend Agent sẽ sinh ra các file `.py`, chạy migration (Alembic), tự cập nhật docs API và tự động chốt commit. Lúc này API `/api/v1/cart` đã sẵn sàng hoạt động ở `localhost:8000`.

---

## 🎨 Bước 2: Giao việc cho Frontend Agent (Ví dụ: dùng Claude 3.5 Sonnet)
**Mục tiêu:** Viết giao diện React (Next.js) và kết nối vào API vừa được Backend Agent tạo ra. Claude vốn rất mạnh về UI/UX.

**👉 Prompt giao việc cho Frontend Agent:**
> "Bạn là Frontend Expert. Một Backend Agent vừa hoàn thành API Giỏ hàng. 
> 1. Hãy đọc file `docs/API_REFERENCE.md` để hiểu payload của endpoint `/api/v1/cart`.
> 2. Thiết kế trang Giỏ hàng tại route `apps/web/app/cart/page.tsx`. Giao diện cần hiện đại, có hiệu ứng hover.
> 3. Bắt buộc tuân thủ nguyên tắc Server Actions và Client Components trong `web-conventions`.
> Cấm đụng vào thư mục `apps/core/`. Xong việc hãy commit với type 'feat(web)'."

**Kết quả thu được:**
Vì Frontend Agent chỉ đọc `API_REFERENCE.md` (do Backend Agent ghi lại ở Bước 1), nó sẽ hiểu ngay định dạng JSON trả về mà không cần phải đọc code Python. Nó tập trung 100% tài nguyên (context window) vào việc vẽ UI.

---

## 🕵️ Bước 3: Giao việc cho QA / Reviewer Agent (Ví dụ: OpenAI o1 hoặc Cursor)
**Mục tiêu:** Rà soát lại code của cả 2 Agent trên xem có lỗi bảo mật hoặc kiến trúc không.

**👉 Prompt giao việc cho QA Agent:**
> "Bạn là Senior Code Reviewer. Tôi vừa nhờ 2 Agent khác code tính năng Giỏ hàng.
> 1. Hãy xem lại toàn bộ các file đã thay đổi trong 2 commit gần nhất.
> 2. Đọc file `AGENTS.md` và các rules trong `.agents/rules/` để biết chuẩn mực của hệ thống.
> 3. Tìm xem có lỗi hổng bảo mật (ví dụ SQL Injection, lộ API Key) hay lỗi logic nào không. 
> 4. Chạy lệnh `make smoke` để kiểm tra test. 
> Nếu phát hiện lỗi, hãy tự vá (fix) và commit bổ sung."

---

## 💡 Tổng kết sức mạnh của mô hình này:
1. **Phân lập Context:** Backend Agent chỉ focus vào Python, Frontend Agent chỉ focus vào TSX. Không xảy ra tình trạng AI sinh nhầm cú pháp Python vào file TSX.
2. **Giao tiếp qua Tài liệu:** Backend Agent ghi tài liệu vào `docs/`, Frontend Agent đọc từ `docs/` để làm UI. Giống hệt cách con người làm việc với nhau (API Contract).
3. **Kiểm soát bằng Rule:** Dù là Agent nào, khi nó đụng vào `apps/core`, rule Backend sẽ tự kích hoạt. Đụng vào `apps/web`, rule Frontend tự kích hoạt (nhờ cơ chế fileMatchPattern).
